"""전처리 어댑터.

README 5.3 / 7.1: service는 전처리를 다시 구현하지 않고 `realstar_model.preprocess.clean_review`를 import한다.
model 패키지가 아직 없으므로(모델 개발 진행 중) 다음 순서로 동작한다.

1. `realstar_model.preprocess`가 설치돼 있으면 그대로 쓴다. ← 모델 완성 후 기본 경로
2. 없으면 "임시 통과(pass-through)" 모드: 텍스트를 바꾸지 않고 길이만 잰다.
   상투 문구 제거·체험단 플래그·근접 중복 판정은 하지 않으며, 결과 warnings에 `preprocess_unavailable`을 남긴다.
   (전처리 규칙 자체를 service에 복제하지 않기 위함. docs/decisions.md D-S03)

clean_review 반환값은 dict 또는 속성 객체 모두 받는다. 기대하는 필드는 docs/model-integration.md 참고.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class CleanedReview:
    clean_text: str
    len_chars: int
    is_sponsored: bool
    is_cash_event: bool
    source: str  # "realstar_model" | "passthrough"


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def model_preprocess_available() -> bool:
    try:
        import realstar_model.preprocess  # type: ignore[import-not-found]  # noqa: F401

        return True
    except Exception:
        return False


def clean(title: str | None, content: str) -> CleanedReview:
    try:
        from realstar_model.preprocess import clean_review  # type: ignore[import-not-found]
    except Exception:
        text = content if not title else f"{title}\n{content}"
        return CleanedReview(clean_text=text, len_chars=len(text), is_sponsored=False, is_cash_event=False, source="passthrough")
    res = clean_review(title=title, content=content)
    text = _get(res, "text_for_model") or _get(res, "clean_text") or ""
    return CleanedReview(
        clean_text=str(_get(res, "clean_text") or text),
        len_chars=int(_get(res, "len_chars", len(text))),
        is_sponsored=bool(_get(res, "is_sponsored", False)),
        is_cash_event=bool(_get(res, "is_cash_event", False)),
        source="realstar_model",
    )


def assign_dup_groups(texts: list[str]) -> tuple[list[str | None], str]:
    """상품 안 완전 중복·근접 중복 그룹 ID (README 5.3-3). 삭제하지 않고 기록만 한다.

    model 패키지의 dedup 함수가 있으면 쓴다. 없으면 완전 중복(정규화 문자열 해시)만 묶는다.
    """
    try:
        from realstar_model.preprocess.dedup import assign_dup_groups as model_assign  # type: ignore[import-not-found]

        return list(model_assign(texts)), "realstar_model"
    except Exception:
        pass
    groups: dict[str, list[int]] = {}
    for i, t in enumerate(texts):
        key = hashlib.sha1(" ".join(t.split()).encode()).hexdigest()[:12]
        groups.setdefault(key, []).append(i)
    out: list[str | None] = [None] * len(texts)
    for key, idx in groups.items():
        if len(idx) > 1:
            for i in idx:
                out[i] = f"dup_{key}"
    return out, "exact_only"
