"""model ↔ service 계약 테스트 (MODEL_DEV.md 4.12.2, M9).

realstar_model 패키지와 모델 아티팩트가 준비되면 자동으로 실행된다. 그 전에는 skip.
  pip install -e ../model
  MODEL_ARTIFACT_PATH=../model/artifacts/det-ko-review-v1.0 pytest -m contract
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from realstar.config import REPO_ROOT
from realstar.detection.backends import RealstarModelBackend
from realstar.detection.schemas import DetectInput

pytestmark = pytest.mark.contract
realstar_model = pytest.importorskip("realstar_model", reason="realstar_model 미설치(모델 개발 중)")
ARTIFACT = Path(os.environ.get("MODEL_ARTIFACT_PATH", REPO_ROOT / "model" / "artifacts" / "det-ko-review-v1.0"))


def test_preprocess_clean_review_contract() -> None:
    from realstar_model.preprocess import clean_review

    res = clean_review(title="좋아요", content="본 리뷰는 쿠팡캐시를 지급받기 위해 작성한 것입니다. 배송 빨라요 ㅋㅋ")
    get = (lambda k: res[k]) if isinstance(res, dict) else (lambda k: getattr(res, k))
    for field in ("clean_text", "len_chars", "is_sponsored", "is_cash_event"):
        get(field)
    assert "ㅋㅋ" in get("clean_text")


@pytest.mark.skipif(not (ARTIFACT / "manifest.json").exists(), reason="모델 아티팩트 없음")
def test_detector_predict_contract() -> None:
    b = RealstarModelBackend(ARTIFACT)
    info = b.info()
    assert info.ready, info.error
    assert info.model_version and info.model_version.startswith("det-ko-review-v")
    preds = b.predict([DetectInput(review_id="c1", title=None, content="배송 빠르고 좋아요. 가격 대비 만족합니다.", star=5)])
    assert len(preds) == 1 and preds[0].review_id == "c1" and preds[0].label in ("human", "ai", "uncertain")
