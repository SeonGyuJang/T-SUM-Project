"""검색 질의 정규화와 후보 점수 (README 5.1 (b))."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from realstar.collectors.base import SearchCandidate

_UNIT_ALIASES = {
    "ml": "ml", "mℓ": "ml", "㎖": "ml", "밀리리터": "ml",
    "l": "l", "ℓ": "l", "리터": "l",
    "g": "g", "그램": "g", "kg": "kg", "㎏": "kg", "킬로그램": "kg", "mg": "mg",
    "개": "개", "개입": "개입", "입": "입", "매": "매", "팩": "팩", "봉": "봉", "병": "병", "캔": "캔", "롤": "롤",
    "p": "p", "ea": "ea", "인치": "인치", "cm": "cm", "mm": "mm", "m": "m", "w": "w", "mah": "mah", "gb": "gb", "tb": "tb",
}
_UNIT_PATTERN = "|".join(sorted((re.escape(u) for u in _UNIT_ALIASES), key=len, reverse=True))
_SPEC_RE = re.compile(rf"(\d+(?:\.\d+)?)\s*({_UNIT_PATTERN})(?![a-z])", re.I)
_MULT_RE = re.compile(r"\s*[x×*]\s*(\d+)", re.I)
_MODEL_RE = re.compile(r"(?<![a-z0-9])(?=[a-z0-9-]*[a-z])(?=[a-z0-9-]*\d)[a-z0-9]+(?:-[a-z0-9]+)*(?![a-z0-9])", re.I)
_STOPWORDS = {"쿠팡", "로켓배송", "무료배송", "정품", "공식", "신상", "특가", "할인", "세트", "1+1"}

WEIGHTS = {"jaccard": 0.35, "model": 0.35, "brand": 0.15, "spec": 0.15}
AD_PENALTY = 0.1


def normalize_query(text: str) -> str:
    """공백·특수문자 정리, 단위 표기 통일(`500 mL` → `500ml`), 곱셈 기호 통일."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = re.sub(r"[\[\]\(\){}<>【】「」『』\"'`|,/\\·•~!?#$%^&+=:;]", " ", t)
    t = _SPEC_RE.sub(lambda m: f"{m.group(1)}{_UNIT_ALIASES.get(m.group(2).lower(), m.group(2).lower())}", t)
    t = _MULT_RE.sub(lambda m: f" x{m.group(1)}", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def tokens(text: str) -> set[str]:
    return {tok for tok in normalize_query(text).split() if tok not in _STOPWORDS and len(tok) >= 1}


def model_numbers(text: str) -> set[str]:
    """영문+숫자 조합 모델명(예: SM-S928N, WH1000XM5). 단위 표기(500ml)는 제외한다."""
    norm = normalize_query(text)
    specs = {f"{a}{b}" for a, b in _SPEC_RE.findall(norm)}
    out = set()
    for m in _MODEL_RE.findall(norm):
        compact = m.replace("-", "")
        if len(compact) < 3 or m in specs or _SPEC_RE.fullmatch(m) or re.fullmatch(r"x\d+", m):
            continue
        out.add(compact)
    return out


def specs(text: str) -> set[str]:
    norm = normalize_query(text)
    out = {f"{float(a):g}{_UNIT_ALIASES.get(b.lower(), b.lower())}" for a, b in _SPEC_RE.findall(norm)}
    out |= {f"x{n}" for n in re.findall(r"x(\d+)", norm)}
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class QueryFeatures:
    raw: str
    norm: str
    tokens: set[str]
    models: set[str]
    specs: set[str]
    brand: str | None


def query_features(query: str, brand: str | None = None) -> QueryFeatures:
    norm = normalize_query(query)
    toks = tokens(query)
    # 브랜드가 따로 주어지지 않으면 첫 토큰을 브랜드 후보로 본다(이미지 판독은 brand를 따로 준다)
    b = normalize_query(brand) if brand else (norm.split()[0] if norm else None)
    return QueryFeatures(query, norm, toks, model_numbers(query), specs(query), b)


def score_candidate(q: QueryFeatures, cand: SearchCandidate) -> float:
    name = cand.name or ""
    c_tokens = tokens(name)
    parts: dict[str, float | None] = {
        "jaccard": jaccard(q.tokens, c_tokens),
        "model": (1.0 if q.models & model_numbers(name) else 0.0) if q.models else None,
        "brand": (1.0 if q.brand and q.brand.replace(" ", "") in normalize_query(name).replace(" ", "") else 0.0) if q.brand else None,
        "spec": (len(q.specs & specs(name)) / len(q.specs)) if q.specs else None,
    }
    # 질의에 없는 요소(모델명·규격 등)는 가중치를 나머지에 비례 배분한다
    active = {k: v for k, v in parts.items() if v is not None}
    total_w = sum(WEIGHTS[k] for k in active)
    score = sum(WEIGHTS[k] * v for k, v in active.items()) / total_w if total_w else 0.0
    # 상품명 안에 질의 토큰이 모두 들어 있으면(부분집합) jaccard의 길이 편향을 보정
    if q.tokens and q.tokens <= c_tokens:
        score = max(score, 0.6 + 0.4 * score)
    if cand.is_ad:
        score -= AD_PENALTY
    return round(min(1.0, max(0.0, score)), 4)


def rank_candidates(query: str, candidates: list[SearchCandidate], brand: str | None = None) -> list[SearchCandidate]:
    q = query_features(query, brand)
    scored = [c.model_copy(update={"match_score": score_candidate(q, c)}) for c in candidates]
    scored.sort(key=lambda c: (c.match_score or 0.0, not c.is_ad, c.review_count or 0), reverse=True)
    return scored


def decide_auto(candidates: list[SearchCandidate], top1_min: float, gap_min: float) -> bool:
    """`top1 ≥ 0.85` 이고 `top1 − top2 ≥ 0.15`이면 자동 선택(TBD-4: 기본값 사용)."""
    if not candidates:
        return False
    top1 = candidates[0].match_score or 0.0
    top2 = (candidates[1].match_score or 0.0) if len(candidates) > 1 else 0.0
    return top1 >= top1_min and (top1 - top2) >= gap_min
