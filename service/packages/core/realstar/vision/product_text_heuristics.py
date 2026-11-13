"""OCR 줄에서 상품명 후보를 고르는 휴리스틱 (README 5.1 (c) 2).

점수 요소
- 글자 크기(줄 높이)와 위치(상단, 큰 글씨)
- 가격 줄(`원`, 숫자+쉼표) 바로 위의 줄
- 브랜드·모델명 패턴이 포함된 줄
- 쇼핑몰 UI 고정 문구 줄은 제거
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from realstar.resolver.scoring import model_numbers, specs
from realstar.vision.ocr import OcrLine

PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{3,})\s*원")
PERCENT_RE = re.compile(r"^\s*\d+\s*%")
HANGUL_OR_LATIN = re.compile(r"[가-힣A-Za-z]")


@lru_cache(maxsize=1)
def _phrases() -> tuple[list[str], list[str]]:
    data = yaml.safe_load(Path(__file__).with_name("ui_phrases.yaml").read_text(encoding="utf-8"))
    return list(data.get("ui_phrases", [])), [m.lower() for m in data.get("coupang_markers", [])]


@dataclass
class ProductTextGuess:
    query: str | None
    product_name: str | None
    brand: str | None
    model_number: str | None
    spec: str | None
    is_coupang_screenshot: bool
    has_text: bool
    confidence: float
    candidates: list[tuple[str, float]] = field(default_factory=list)


def is_ui_line(text: str) -> bool:
    ui, _ = _phrases()
    t = text.replace(" ", "")
    if PRICE_RE.search(text) or PERCENT_RE.match(text):
        return True
    if len(t) <= 12 and any(p.replace(" ", "") in t for p in ui):
        return True
    return not HANGUL_OR_LATIN.search(text)


def guess_product_text(lines: list[OcrLine], image_height: float) -> ProductTextGuess:
    _, markers = _phrases()
    joined = " ".join(ln.text for ln in lines).lower()
    is_coupang = any(m in joined for m in markers)
    usable = [ln for ln in lines if ln.confidence >= 0.5 and len(ln.text.strip()) >= 2]
    if not usable:
        return ProductTextGuess(None, None, None, None, None, is_coupang, bool(lines), 0.0)

    max_h = max(ln.height for ln in usable) or 1.0
    ordered = sorted(usable, key=lambda ln: (ln.top, ln.bbox[0]))
    # 가격 줄 바로 위의 상품명 블록: 가격 줄 앞의 UI 아닌 줄 최대 3개에 가까운 순으로 가산점
    price_bonus: dict[int, float] = {}
    for j, ln in enumerate(ordered):
        if not PRICE_RE.search(ln.text):
            continue
        k, bonus = j - 1, [0.15, 0.2, 0.25]
        while k >= 0 and bonus:
            if not is_ui_line(ordered[k].text):
                price_bonus[k] = max(price_bonus.get(k, 0.0), bonus.pop())
            k -= 1
    scored: list[tuple[str, float]] = []
    for i, ln in enumerate(ordered):
        if is_ui_line(ln.text):
            continue
        s = 0.0
        s += 0.35 * (ln.height / max_h)  # 큰 글씨
        s += 0.15 * (1.0 - min(1.0, ln.top / max(1.0, image_height)))  # 상단
        s += price_bonus.get(i, 0.0)
        if model_numbers(ln.text):
            s += 0.15
        if specs(ln.text):
            s += 0.05
        compact = len(ln.text.replace(" ", ""))
        s += 0.1 * min(1.0, compact / 15)
        if compact < 4:
            s *= 0.5  # 색상·옵션 같은 짧은 줄
        s *= ln.confidence
        scored.append((ln.text.strip(), round(s, 4)))
    scored.sort(key=lambda x: x[1], reverse=True)
    if not scored:
        return ProductTextGuess(None, None, None, None, None, is_coupang, True, 0.0)

    best_text, best_score = scored[0]
    # 같은 상품명이 두 줄로 나뉜 경우: 바로 아래 줄이 비슷한 크기면 합친다
    best_line = next(ln for ln in ordered if ln.text.strip() == best_text)
    idx = ordered.index(best_line)
    if idx + 1 < len(ordered):
        nxt = ordered[idx + 1]
        if not is_ui_line(nxt.text) and abs(nxt.height - best_line.height) <= 0.15 * best_line.height and nxt.top - best_line.bbox[3] < best_line.height:
            best_text = f"{best_text} {nxt.text.strip()}"
    models = sorted(model_numbers(best_text))
    sp = sorted(specs(best_text))
    brand = best_text.split()[0] if best_text.split() else None
    confidence = min(1.0, best_score + (0.1 if len(scored) == 1 or best_score - scored[1][1] > 0.1 else 0.0))
    return ProductTextGuess(
        query=best_text,
        product_name=best_text,
        brand=brand,
        model_number=models[0] if models else None,
        spec=" ".join(sp) if sp else None,
        is_coupang_screenshot=is_coupang,
        has_text=True,
        confidence=round(confidence, 3),
        candidates=scored[:5],
    )
