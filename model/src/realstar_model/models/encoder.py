"""① 한국어 인코더 분류기 (MODEL_DEV.md 4.6). GPU 권장(없으면 CPU·Apple MPS로도 돌지만 느리다).

  pip install -e ".[encoder]"
  python -m realstar_model train-encoder                                  # 기본 beomi/KcELECTRA-base-v2022 (MIT)
  python -m realstar_model train-encoder --encoder klue/roberta-base --epochs 3
  python -m realstar_model train-encoder --limit 2000 --epochs 1          # 빠른 시험

- 조기 종료 기준: 검증셋 TPR@1%FPR (4.6). 최고 시점 가중치를 아티팩트 encoder/에 저장한다.
- 점수 = logit(ai) − logit(human). val로 Platt 보정·길이 구간별 임계값을 정한다.
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path
from typing import Any

import numpy as np

from realstar_model.datasets.build import read_dataset
from realstar_model.eval.metrics import report, tpr_at_fpr
from realstar_model.fusion.thresholds import apply_platt, fit_platt, fit_thresholds
from realstar_model.models.artifact import default_art_dir, log_experiment, new_experiment_dir, write_manifest
from realstar_model.paths import PROCESSED
from realstar_model.preprocess import clean_review

DEFAULT_ENCODER = "beomi/KcELECTRA-base-v2022"


def pick_device() -> Any:
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class EncoderScorer:
    """저장된 인코더로 원점수(logit_ai − logit_human)를 낸다. Detector가 쓴다."""

    batch_call = True

    def __init__(self, path: Path, max_length: int = 256, device: Any = None) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.device = device or pick_device()
        self.tok = AutoTokenizer.from_pretrained(str(path))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(path)).to(self.device).eval()
        self.max_length = max_length

    def __call__(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        return score_texts(self.model, self.tok, texts, self.max_length, batch_size, self.device)


def score_texts(model: Any, tok: Any, texts: list[str], max_length: int, batch_size: int, device: Any) -> np.ndarray:
    import torch

    out: list[float] = []
    model.eval()
    with torch.no_grad():
        for k in range(0, len(texts), batch_size):
            enc = tok(texts[k:k + batch_size], truncation=True, max_length=max_length, padding=True, return_tensors="pt").to(device)
            logits = model(**enc).logits.float()
            out.extend((logits[:, 1] - logits[:, 0]).cpu().tolist())
    return np.asarray(out)


def train(*, version: str = "det-ko-review-v0.2", encoder_id: str = DEFAULT_ENCODER, dataset: Path = PROCESSED / "dataset.jsonl",
          art_dir: Path | None = None, max_length: int = 256, epochs: int = 3, batch_size: int = 32, lr: float = 3e-5,
          warmup: float = 0.1, weight_decay: float = 0.01, patience: int = 1, seed: int = 42, limit: int = 0) -> dict[str, Any]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    rows = read_dataset(dataset)
    man_path = dataset.parent / "dataset_manifest.json"
    data_version = json.loads(man_path.read_text(encoding="utf-8")).get("data_version", "unknown") if man_path.exists() else "unknown"
    split = {s: [r for r in rows if r.split == s] for s in ("train", "val", "test")}
    if limit:
        split = {s: v[: limit if s == "train" else max(200, limit // 4)] for s, v in split.items()}
    cl = {s: [clean_review(r.title, r.text) for r in v] for s, v in split.items()}
    X = {s: [c.text_for_model for c in v] for s, v in cl.items()}
    Y = {s: np.asarray([r.label for r in v]) for s, v in split.items()}
    B = {s: [c.len_bucket for c in v] for s, v in cl.items()}
    device = pick_device()
    print(f"데이터 {data_version}: train {len(X['train']):,} / val {len(X['val']):,} / test {len(X['test']):,} · 인코더 {encoder_id} · 장치 {device}")

    tok = AutoTokenizer.from_pretrained(encoder_id)
    model = AutoModelForSequenceClassification.from_pretrained(encoder_id, num_labels=2).to(device)
    pos = float(Y["train"].mean())
    weight = None
    if abs(pos - 0.5) > 0.05:  # 1:1에서 ±10% 이상 벗어나면 class weight(4.6)
        weight = torch.tensor([0.5 / (1 - pos), 0.5 / pos], dtype=torch.float, device=device)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weight)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    steps = math.ceil(len(X["train"]) / batch_size) * epochs
    sched = get_linear_schedule_with_warmup(opt, int(steps * warmup), steps)
    use_amp = device.type == "cuda"
    amp_dtype = torch.bfloat16 if use_amp and torch.cuda.is_bf16_supported() else torch.float16
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp and amp_dtype == torch.float16)

    art = art_dir or default_art_dir(version)
    enc_dir = art / "encoder"
    best, bad, history = -1.0, 0, []
    idx = list(range(len(X["train"])))
    for ep in range(1, epochs + 1):
        model.train()
        random.shuffle(idx)
        t0, total = time.time(), 0.0
        for b, k in enumerate(range(0, len(idx), batch_size), 1):
            sel = idx[k:k + batch_size]
            enc = tok([X["train"][i] for i in sel], truncation=True, max_length=max_length, padding=True, return_tensors="pt").to(device)
            y = torch.tensor(Y["train"][sel], dtype=torch.long, device=device)
            with torch.autocast(device_type=device.type, dtype=amp_dtype, enabled=use_amp):
                loss = loss_fn(model(**enc).logits.float(), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            total += loss.item()
            if b % 50 == 0:
                print(f"  epoch {ep} step {b} loss {total / b:.4f} ({time.time() - t0:.0f}초)", flush=True)
        s_val = score_texts(model, tok, X["val"], max_length, batch_size * 2, device)
        tpr = tpr_at_fpr(Y["val"], s_val, 0.01) or 0.0
        history.append({"epoch": ep, "train_loss": round(total / max(1, b), 4), "val_tpr@1%fpr": round(tpr, 4)})
        print(f"  epoch {ep} 끝: train loss {total / max(1, b):.4f} · val TPR@1%FPR {tpr:.4f}", flush=True)
        if tpr > best:
            best, bad = tpr, 0
            enc_dir.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(str(enc_dir))
            tok.save_pretrained(str(enc_dir))
        else:
            bad += 1
            if bad >= patience:
                print(f"  조기 종료(patience {patience})")
                break

    scorer = EncoderScorer(enc_dir, max_length, device)  # 최고 시점 가중치로 다시 평가
    s_val, s_test = scorer(X["val"], batch_size * 2), scorer(X["test"], batch_size * 2)
    cal = fit_platt(s_val, Y["val"])
    p_val, p_test = apply_platt(s_val, cal), apply_platt(s_test, cal)
    thr = fit_thresholds(p_val, Y["val"], B["val"])
    metrics: dict[str, Any] = {"val": report(Y["val"], p_val, B["val"]), "test": report(Y["test"], p_test, B["test"]), "history": history}
    tgen = [i for i, r in enumerate(split["test"]) if r.meta.get("t_gen") or r.label == 0]
    if any(split["test"][i].meta.get("t_gen") for i in tgen):
        metrics["test_t_gen"] = report(Y["test"][tgen], p_test[tgen], [B["test"][i] for i in tgen])
    write_manifest(art, model_version=version, model_type="encoder", data_version=data_version, thresholds=thr,
                   calibration=cal, metrics=metrics,
                   extra={"encoder_id": encoder_id, "max_length": max_length,
                          "params": {"epochs": epochs, "batch_size": batch_size, "lr": lr, "warmup": warmup, "seed": seed, "limit": limit},
                          "notes": "① 한국어 인코더 분류기 단독(B3). 실험용."})
    exp, exp_dir = new_experiment_dir()
    (exp_dir / "metrics.json").write_text(json.dumps({"artifact": str(art), **metrics}, ensure_ascii=False, indent=2), encoding="utf-8")
    t = metrics["test"]["all"]
    log_experiment(exp, {"model_type": "encoder", "model_version": version, "data_version": data_version, "test_auroc": t.get("auroc"),
                         "test_tpr@1%fpr": t.get("tpr@1%fpr"), "test_tpr@2%fpr": t.get("tpr@2%fpr"), "test_ece": t.get("ece"),
                         "notes": f"encoder {encoder_id}"})
    return {"artifact": str(art), "experiment": exp, "metrics": metrics, "thresholds": thr}
