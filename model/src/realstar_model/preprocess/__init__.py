"""전처리 — 서비스 추론용. service도 이 함수를 그대로 import한다(D-009).

  from realstar_model.preprocess import clean_review
  res = clean_review(title="좋아요", content="본 리뷰는 쿠팡캐시를 지급받기 위해 작성한 것입니다. 배송 빨라요 ㅋㅋ")
  res.clean_text      # "배송 빨라요 ㅋㅋ"   (상투 문구 제거, 줄바꿈→공백, NFC)
  res.text_for_model  # "좋아요 / 배송 빨라요 ㅋㅋ"
  res.is_cash_event   # True
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

ZERO_WIDTH = re.compile("[​‌‍﻿]")
_HANGUL = re.compile("[가-힣ㄱ-ㅎㅏ-ㅣ]")
_SPACES = re.compile(r"[ \t\f\v ]+")
MIN_CHARS = 20  # 이보다 짧으면 판단 보류(4.10.3)


@dataclass
class CleanResult:
    clean_text: str          # 상투 문구 제거·공백 정규화한 본문
    text_for_model: str      # 모델 입력: "제목 / 본문" (제목 없으면 본문)
    len_chars: int           # 전처리 후 본문 문자 수
    len_eojeol: int
    len_bucket: str          # S < 30자, M < 100자, L ≥ 100자
    newline_count: int
    zw_count: int
    is_sponsored: bool
    is_cash_event: bool
    hangul_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # service 어댑터는 dict처럼도 읽는다
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


@lru_cache(maxsize=1)
def _patterns() -> dict[str, list[re.Pattern[str]]]:
    raw = json.loads((Path(__file__).with_name("boilerplate_patterns.json")).read_text(encoding="utf-8"))
    return {k: [re.compile(p) for p in raw[k]] for k in ("cash_event", "sponsored")}


def patterns_version() -> str:
    return str(json.loads((Path(__file__).with_name("boilerplate_patterns.json")).read_text(encoding="utf-8"))["version"])


def length_bucket(n: int) -> str:
    return "S" if n < 30 else "M" if n < 100 else "L"


def _normalize(text: str) -> tuple[str, int, int]:
    text = unicodedata.normalize("NFC", text or "")
    zw = len(ZERO_WIDTH.findall(text))
    text = ZERO_WIDTH.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    newlines = text.count("\n")
    text = _SPACES.sub(" ", text.replace("\n", " "))  # D-006: 줄바꿈은 공백으로, 개수는 특징으로만
    return re.sub(r" {2,}", " ", text).strip(), newlines, zw


def clean_review(title: str | None = None, content: str = "") -> CleanResult:
    body, newlines, zw = _normalize(content)
    head, _, zw_t = _normalize(title or "")
    pats = _patterns()
    cash = sponsored = False
    for p in pats["cash_event"]:
        body, n = p.subn(" ", body)
        cash = cash or n > 0
    for p in pats["sponsored"]:
        body, n = p.subn(" ", body)
        sponsored = sponsored or n > 0
    body = re.sub(r" {2,}", " ", body).strip(" .")  if (cash or sponsored) else body
    text_for_model = f"{head} / {body}" if head else body
    n = len(body)
    return CleanResult(
        clean_text=body, text_for_model=text_for_model, len_chars=n, len_eojeol=len(body.split()),
        len_bucket=length_bucket(n), newline_count=newlines, zw_count=zw + zw_t,
        is_sponsored=sponsored, is_cash_event=cash,
        hangul_ratio=round(len(_HANGUL.findall(body)) / max(1, len(body.replace(" ", ""))), 4),
    )


__all__ = ["MIN_CHARS", "CleanResult", "clean_review", "length_bucket", "patterns_version"]
