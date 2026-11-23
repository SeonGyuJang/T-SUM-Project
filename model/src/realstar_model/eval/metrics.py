"""평가 지표 (MODEL_DEV.md 4.11.2). 주 지표 TPR@FPR=1%·2%(D-003), 보조 AUROC·AUPRC·ECE."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve


def tpr_at_fpr(y: ArrayLike, p: ArrayLike, fpr_target: float) -> float | None:
    y_a, p_a = np.asarray(y), np.asarray(p)
    if len(set(y_a.tolist())) < 2:
        return None
    fpr, tpr, _ = roc_curve(y_a, p_a)
    ok = tpr[fpr <= fpr_target]
    return float(ok.max()) if len(ok) else 0.0


def ece(y: ArrayLike, p: ArrayLike, bins: int = 10) -> float:
    y_a, p_a = np.asarray(y, dtype=float), np.clip(np.asarray(p, dtype=float), 0, 1)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p_a >= lo) & ((p_a < hi) if hi < 1 else (p_a <= hi))
        if m.any():
            total += m.mean() * abs(p_a[m].mean() - y_a[m].mean())
    return float(total)


def summarize(y: ArrayLike, p: ArrayLike) -> dict[str, Any]:
    y_a, p_a = np.asarray(y), np.asarray(p)
    out: dict[str, Any] = {"n": int(len(y_a)), "n_ai": int(y_a.sum()), "n_human": int(len(y_a) - y_a.sum())}
    if len(set(y_a.tolist())) < 2:
        return out
    out.update({
        "auroc": round(float(roc_auc_score(y_a, p_a)), 4),
        "auprc": round(float(average_precision_score(y_a, p_a)), 4),
        "tpr@1%fpr": round(tpr_at_fpr(y_a, p_a, 0.01) or 0.0, 4),
        "tpr@2%fpr": round(tpr_at_fpr(y_a, p_a, 0.02) or 0.0, 4),
        "ece": round(ece(y_a, p_a), 4),
        "acc@0.5": round(float(((p_a >= 0.5) == (y_a == 1)).mean()), 4),
    })
    return out


def report(y: ArrayLike, p: ArrayLike, buckets: ArrayLike) -> dict[str, Any]:
    """전체 + 길이 구간(S/M/L)별."""
    y_a, p_a, b_a = np.asarray(y), np.asarray(p), np.asarray(buckets)
    out = {"all": summarize(y_a, p_a)}
    for b in ("S", "M", "L"):
        m = b_a == b
        if m.any():
            out[b] = summarize(y_a[m], p_a[m])
    return out
