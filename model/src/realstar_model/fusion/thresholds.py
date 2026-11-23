"""확률 보정(Platt)과 길이 구간별 임계값 (MODEL_DEV.md 4.10.2·4.10.3, D-004)."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike
from sklearn.linear_model import LogisticRegression


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_platt(scores: ArrayLike, y: ArrayLike) -> dict[str, float]:
    """원점수(로짓) → 보정 확률. val 분할로만 맞춘다."""
    lr = LogisticRegression(C=1e6, max_iter=1000)
    lr.fit(np.asarray(scores, dtype=float).reshape(-1, 1), np.asarray(y))
    return {"a": float(lr.coef_[0][0]), "b": float(lr.intercept_[0])}


def apply_platt(scores: ArrayLike, cal: dict[str, float]) -> np.ndarray:
    z = cal["a"] * np.asarray(scores, dtype=float) + cal["b"]
    return 1.0 / (1.0 + np.exp(-z))


def fit_thresholds(p: ArrayLike, y: ArrayLike, buckets: ArrayLike, *, human_fpr: float = 0.02,
                   ai_pass: float = 0.05, min_n: int = 300) -> dict[str, Any]:
    """T_AI[b] = 사람 p_ai의 (1-human_fpr) 분위수, T_HUMAN[b] = AI p_ai의 ai_pass 분위수.
    구간 표본이 min_n 미만이면 전체(모든 구간 합)로 정하고 표시한다."""
    p_a, y_a, b_a = np.asarray(p, dtype=float), np.asarray(y), np.asarray(buckets)

    def one(mask: np.ndarray) -> dict[str, float]:
        hum, ai = p_a[mask & (y_a == 0)], p_a[mask & (y_a == 1)]
        t_ai = float(np.quantile(hum, 1 - human_fpr)) if len(hum) else 0.9
        t_h = float(np.quantile(ai, ai_pass)) if len(ai) else 0.1
        merged = False
        if t_h >= t_ai:  # 보류 구간이 없으면 중간값으로 같게(4.10.3)
            t_ai = t_h = (t_ai + t_h) / 2
            merged = True
        return {"T_AI": round(t_ai, 4), "T_HUMAN": round(t_h, 4), "n_human": int(len(hum)), "n_ai": int(len(ai)), "merged": merged}

    overall = one(np.ones_like(y_a, dtype=bool))
    out: dict[str, Any] = {}
    for b in ("S", "M", "L"):
        m = b_a == b
        n_h, n_ai = int((m & (y_a == 0)).sum()), int((m & (y_a == 1)).sum())
        out[b] = {**overall, "pooled": True} if min(n_h, n_ai) < min_n else {**one(m), "pooled": False}
    out["ALL"] = overall
    return out


def decide(p_ai: float, bucket: str, len_chars: int, thresholds: dict[str, Any], min_chars: int = 20) -> str:
    if len_chars < min_chars:
        return "uncertain"  # 4.10.3: 짧은 리뷰는 무조건 판단 보류
    t = thresholds.get(bucket) or thresholds.get("ALL") or {"T_AI": 0.9, "T_HUMAN": 0.1}
    if p_ai >= t["T_AI"]:
        return "ai"
    if p_ai <= t["T_HUMAN"]:
        return "human"
    return "uncertain"
