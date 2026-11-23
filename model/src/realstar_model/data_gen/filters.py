"""생성 후 필터 (MODEL_DEV.md 4.5.3)."""

from __future__ import annotations

import re

from realstar_model.preprocess import clean_review

_META_PREFIX = re.compile(
    r"^\s*(?:물론(?:이죠|입니다)?[!.,]?|네[,!.]\s*|다음은[^\n]{0,40}?(?:리뷰|후기)[^\n]{0,20}?[:：]|"
    r"(?:리뷰|후기)(?:를)?\s*(?:작성해\s*드릴게요|써\s*드릴게요|입니다)[!.:：]?|\[?(?:리뷰|후기)\]?\s*[:：])\s*",
)
_META_ANYWHERE = re.compile(r"(?:작성해\s*드릴게요|써\s*드릴게요|도움이\s*되셨으면|AI\s*(?:로서|언어\s*모델)|요청하신)")
_MD = re.compile(r"(\*\*|__|^#{1,6}\s|^\s*[-*]\s)", re.M)


def clean_generated(text: str) -> str:
    t = (text or "").strip()
    for _ in range(2):
        t = _META_PREFIX.sub("", t).strip()
    if len(t) >= 2 and t[0] in "\"'“‘「" and t[-1] in "\"'”’」":
        t = t[1:-1].strip()
    t = _MD.sub("", t)
    return t.strip()


def char_ngrams(text: str, n: int = 8) -> set[str]:
    t = re.sub(r"\s+", "", text or "")
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def overlap_ratio(text: str, refs: list[str], n: int = 8) -> float:
    g = char_ngrams(text, n)
    if not g:
        return 0.0
    ref = set().union(*(char_ngrams(r, n) for r in refs)) if refs else set()
    return len(g & ref) / len(g)


def check(text: str, target_chars: int, refs: list[str], mode: str) -> str | None:
    """통과하면 None, 아니면 탈락 이유."""
    if not text:
        return "empty"
    if _META_ANYWHERE.search(text):
        return "meta_phrase"
    c = clean_review(None, text)
    if c.hangul_ratio < 0.7:
        return "low_hangul"
    ratio = c.len_chars / max(1, target_chars)
    if not 0.5 <= ratio <= 1.8:
        return "length"
    if mode == "write" and overlap_ratio(text, refs) >= 0.3:
        return "copied_reference"
    return None
