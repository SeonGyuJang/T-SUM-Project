"""확률 보정(Platt) 적용과 길이 구간별 임계값 판정. 값은 아티팩트 manifest.json(export_for_service.py가 씀)에서 온다."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def apply_platt(scores: ArrayLike, cal: dict[str, float]) -> np.ndarray:
    z = cal["a"] * np.asarray(scores, dtype=float) + cal["b"]
    return 1.0 / (1.0 + np.exp(-z))


def decide(p_ai: float, bucket: str, len_chars: int, thresholds: dict[str, Any], min_chars: int = 20) -> str:
    if len_chars < min_chars:
        return "uncertain"  # 짧은 리뷰는 무조건 판단 보류
    t = thresholds.get(bucket) or thresholds.get("ALL") or {"T_AI": 0.9, "T_HUMAN": 0.1}
    if p_ai >= t["T_AI"]:
        return "ai"
    if p_ai < t["T_HUMAN"]:  # 서비스 기준과 같게: T_HUMAN 미만이 사람
        return "human"
    return "uncertain"
