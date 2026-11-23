"""서비스용 추론 런타임: Detector가 manifest의 보정·임계값으로 판정하는지 (인코더 없이 가짜 점수기로)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from realstar_model.fusion.thresholds import apply_platt, decide
from realstar_model.inference import Detector, ReviewInput

MANIFEST = {
    "model_version": "det-ko-review-test",
    "model_type": "encoder",
    "calibration": {"a": 1.0, "b": 0.0},
    "thresholds": {"ALL": {"T_AI": 0.8, "T_HUMAN": 0.3}},
    "min_chars": 20,
}


def test_platt_and_decide() -> None:
    assert np.allclose(apply_platt([0.0], {"a": 1.0, "b": 0.0}), [0.5])
    th = MANIFEST["thresholds"]
    assert decide(0.9, "M", 50, th) == "ai"
    assert decide(0.1, "M", 50, th) == "human"
    assert decide(0.5, "M", 50, th) == "uncertain"
    assert decide(0.99, "S", 5, th) == "uncertain"  # 짧은 리뷰는 판단 보류


def test_detector_uses_manifest(tmp_path: Path) -> None:
    det = Detector(tmp_path, MANIFEST, scorer=lambda texts: np.array([4.0 if "AI" in t else -4.0 for t in texts]))
    preds = det.predict([
        ReviewInput("a", content="이 리뷰는 AI가 쓴 것 같은 아주 매끄러운 문장입니다."),
        ReviewInput("h", content="배송 빨라요 ㅋㅋ 생각보다 괜찮네요 재구매 의사 있어요"),
        ReviewInput("s", content="좋아요"),
    ])
    assert [p.label for p in preds] == ["ai", "human", "uncertain"]
    assert preds[0].model_version == "det-ko-review-test" and 0.0 <= preds[0].p_ai <= 1.0
