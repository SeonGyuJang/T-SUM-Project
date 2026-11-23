"""추론 API — service ↔ model 계약 (MODEL_DEV.md 4.12.2).

  from realstar_model.inference import Detector, ReviewInput
  det = Detector.load("artifacts/det-ko-review-v0.1")
  preds = det.predict([ReviewInput(review_id="r1", title=None, content="배송 빠르고 좋아요", star=5)], batch_size=64)

predict는 내부에서 반드시 4.4 전처리(clean_review)를 적용한다. service는 전처리를 다시 구현하지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from realstar_model.fusion.thresholds import apply_platt, decide
from realstar_model.preprocess import MIN_CHARS, clean_review


@dataclass
class ReviewInput:
    review_id: str
    title: str | None = None
    content: str = ""
    star: int | None = None
    category: str | None = None


@dataclass
class Prediction:
    review_id: str
    p_ai: float
    p_human: float
    label: str               # ai | human | uncertain
    len_bucket: str
    model_version: str
    features: dict[str, Any] = field(default_factory=dict)
    reason_tags: list[str] = field(default_factory=list)


class Detector:
    def __init__(self, path: Path, manifest: dict[str, Any], scorer: Any) -> None:
        self.path = path
        self.manifest = manifest
        self.scorer = scorer  # texts -> 원점수(보정 전 로짓)
        self.model_version = str(manifest["model_version"])
        self.thresholds = manifest["thresholds"]
        self.calibration = manifest["calibration"]
        self.min_chars = int(manifest.get("min_chars", MIN_CHARS))

    @classmethod
    def load(cls, path: str | Path) -> Detector:
        p = Path(path)
        manifest = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
        kind = manifest.get("model_type")
        if kind == "tfidf_lr":
            import joblib

            pipe = joblib.load(p / "tfidf_lr.joblib")
            scorer = pipe.decision_function
        elif kind == "encoder":
            from realstar_model.models.encoder import EncoderScorer

            scorer = EncoderScorer(p / "encoder", max_length=int(manifest.get("max_length", 256)))
        else:
            raise ValueError(f"알 수 없는 model_type: {kind!r} ({p}/manifest.json)")
        return cls(p, manifest, scorer)

    def predict(self, inputs: list[ReviewInput], batch_size: int = 64) -> list[Prediction]:
        if not inputs:
            return []
        cleaned = [clean_review(i.title, i.content) for i in inputs]
        texts = [c.text_for_model for c in cleaned]
        scores: list[float] = []
        for k in range(0, len(texts), max(1, batch_size)):
            chunk = texts[k:k + batch_size]
            out = self.scorer(chunk, batch_size=batch_size) if hasattr(self.scorer, "batch_call") else self.scorer(chunk)
            scores.extend(float(s) for s in np.asarray(out).ravel())
        probs = apply_platt(scores, self.calibration)
        preds = []
        for inp, c, s, p in zip(inputs, cleaned, scores, probs, strict=True):
            p = float(np.clip(p, 0.0, 1.0))
            label = decide(p, c.len_bucket, c.len_chars, self.thresholds, self.min_chars)
            tags = ["짧은 리뷰(판단 보류)"] if c.len_chars < self.min_chars else []
            preds.append(Prediction(
                review_id=inp.review_id, p_ai=round(p, 4), p_human=round(1 - p, 4), label=label, len_bucket=c.len_bucket,
                model_version=self.model_version, reason_tags=tags,
                features={"raw_score": round(s, 4), "len_chars": c.len_chars, "newline_count": c.newline_count,
                          "is_sponsored": c.is_sponsored, "is_cash_event": c.is_cash_event},
            ))
        return preds


__all__ = ["Detector", "Prediction", "ReviewInput"]
