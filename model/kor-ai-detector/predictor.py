"""학습된 모델로 P(AI)와 판정을 내는 공용 모듈 (evaluate.py · app.py · export_for_service.py가 함께 씀).

  from predictor import Predictor
  pred = Predictor("models/stage2", report="reports/stage2/report.json")
  pred.judge(["배송 빠르고 포장도 꼼꼼해요 ㅎㅎ"])  # → [{"p_ai": 0.03, "verdict": "사람", ...}]

판정 규칙 (임계값은 evaluate.py가 검증셋으로 정해 report.json에 저장):
  P(AI) >  T_AI     → AI       (검증셋 사람 리뷰 중 target_fpr(1%)만 이 위로 올라감)
  P(AI) <= T_HUMAN  → 사람     (검증셋 AI 리뷰 중 ai_miss(5%)만 이 아래로 내려감)
  그 사이           → 판단 보류
  글자 수 < min_chars(20) → 판단 보류 (정보가 너무 적음)
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
MIN_CHARS = 20


def thresholds_from_val(labels, scores, target_fpr=0.01, ai_miss=0.05):
    """검증셋 점수 → (T_AI, T_HUMAN). T_HUMAN >= T_AI면 보류 구간 없이 T_HUMAN = T_AI."""
    from metrics import threshold_at_fpr

    human = [s for s, y in zip(scores, labels) if y == 0]
    ai = sorted(s for s, y in zip(scores, labels) if y == 1)
    t_ai = threshold_at_fpr(human, target_fpr)
    if ai:
        k = min(int(ai_miss * len(ai)), len(ai) - 1)
        t_human = ai[k - 1] if k > 0 else min(ai) - 1e-9  # <= T_HUMAN 인 AI가 k개 이하
    else:
        t_human = 0.0
    return t_ai, min(t_human, t_ai)


def verdict(p_ai, t_ai, t_human, n_chars=None, min_chars=MIN_CHARS):
    if n_chars is not None and n_chars < min_chars:
        return "판단 보류"
    if p_ai > t_ai:
        return "AI"
    if p_ai <= t_human:
        return "사람"
    return "판단 보류"


def pick_device(name=None):
    import torch

    if name:
        return name
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class Predictor:
    def __init__(self, model_dir, report=None, max_len=None, batch_size=64, device=None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.model_dir = model_dir
        cfg_path = os.path.join(model_dir, "train_config.json")
        self.train_config = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
        self.newlines = self.train_config.get("preprocess", {}).get("newlines", "keep")
        self.max_len = max_len or int(self.train_config.get("max_len") or self.train_config.get("args", {}).get("max_len", 256))
        self.bs = batch_size
        self.device = pick_device(device)
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(self.device).eval()
        self.report = json.load(open(report, encoding="utf-8")) if report and os.path.exists(report) else None
        th = (self.report or {}).get("thresholds") or {}
        if not th and self.report and "threshold" in self.report:  # 예전 report.json
            th = {"T_AI": self.report["threshold"], "T_HUMAN": self.report["threshold"]}
        self.t_ai = float(th.get("T_AI", 0.5))
        self.t_human = float(th.get("T_HUMAN", 0.5))
        self.calibrated = bool(th)

    def preprocess(self, text):
        """prepare_data.py와 같은 정규화(NFC, 보이지 않는 문자 제거, 학습 때 줄바꿈을 지웠으면 똑같이)."""
        t = ZERO_WIDTH.sub("", unicodedata.normalize("NFC", str(text))).strip()
        if self.newlines == "space":
            t = re.sub(r"[ \t]*\n+[ \t]*", " ", t).strip()
        return t

    def score(self, texts):
        texts = [self.preprocess(t) for t in texts]
        out = []
        for i in range(0, len(texts), self.bs):
            enc = self.tok(texts[i:i + self.bs], truncation=True, max_length=self.max_len,
                           padding=True, return_tensors="pt").to(self.device)
            with self.torch.no_grad():
                p = self.torch.softmax(self.model(**enc).logits.float(), dim=-1)[:, 1]
            out.extend(p.cpu().tolist())
        return out

    def judge(self, texts):
        scores = self.score(texts)
        res = []
        for t, p in zip(texts, scores):
            n = len(self.preprocess(t))
            res.append({"text": t, "p_ai": round(p, 4), "verdict": verdict(p, self.t_ai, self.t_human, n), "chars": n})
        return res

    def info(self):
        return {
            "model_dir": os.path.abspath(self.model_dir), "device": str(self.device), "max_len": self.max_len,
            "newlines": self.newlines, "T_AI": self.t_ai, "T_HUMAN": self.t_human, "calibrated": self.calibrated,
            "target_fpr": (self.report or {}).get("target_fpr"), "ai_miss": (self.report or {}).get("ai_miss"),
            "base_model": self.train_config.get("args", {}).get("model"),
            "val_metrics": {k: v for k, v in (self.train_config.get("val_metrics") or {}).items() if isinstance(v, (int, float))},
        }
