"""캡처 이미지 입력 → 상품명 추출 → 검색 (README 5.1 (c), F3).

개인정보가 담길 수 있으므로 원본 이미지는 디스크에 저장하지 않는다. 메모리에서만 처리한다.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from realstar.collectors.base import SearchCandidate
from realstar.config import Settings
from realstar.errors import InvalidInputError
from realstar.resolver.models import ResolveResult
from realstar.vision.ocr import OcrEngine
from realstar.vision.product_text_heuristics import guess_product_text
from realstar.vision.vlm import VlmExtractor

log = logging.getLogger(__name__)

ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "BMP"}
LOW_CONFIDENCE = 0.45


def load_image(data: bytes, max_bytes: int, max_side: int) -> Image.Image:
    """크기 제한 + EXIF 제거(픽셀만 새 이미지로 복사). 디스크에 쓰지 않는다."""
    if not data:
        raise InvalidInputError("empty image", "이미지 파일을 올려 주세요.")
    if len(data) > max_bytes:
        raise InvalidInputError("image too large", f"이미지는 {max_bytes // (1024 * 1024)}MB 이하만 올릴 수 있어요.")
    try:
        opened = Image.open(io.BytesIO(data))
        fmt = opened.format
        opened.load()
    except (UnidentifiedImageError, OSError) as e:
        raise InvalidInputError(f"bad image: {e}", "이미지를 읽지 못했어요. PNG나 JPG 파일로 다시 올려 주세요.") from e
    if fmt not in ALLOWED_FORMATS:
        raise InvalidInputError(f"format {fmt}", "PNG, JPG, WEBP 이미지만 올릴 수 있어요.")
    img: Image.Image = ImageOps.exif_transpose(opened) or opened  # 회전 정보만 반영
    img = img.convert("RGB")
    clean = Image.new("RGB", img.size)
    clean.paste(img)  # EXIF·메타데이터 없는 새 이미지
    if max(clean.size) > max_side:
        clean.thumbnail((max_side, max_side))
    return clean


def _merge_candidates(lists: list[list[SearchCandidate]], limit: int) -> list[SearchCandidate]:
    best: dict[str, SearchCandidate] = {}
    for lst in lists:
        for c in lst:
            prev = best.get(c.product_id)
            if prev is None or (c.match_score or 0) > (prev.match_score or 0):
                best[c.product_id] = c
    return sorted(best.values(), key=lambda c: c.match_score or 0, reverse=True)[:limit]


SearchFn = Callable[[str, "str | None", bool], ResolveResult]


def resolve_by_image(data: bytes, search: SearchFn, settings: Settings, ocr: OcrEngine, vlm: VlmExtractor) -> ResolveResult:
    """search(query, brand, force_selection)는 상품명 검색(F2)을 수행한다. 이미지는 이 함수 밖으로 나가지 않는다."""
    img = load_image(data, settings.image_max_bytes, settings.image_max_side)
    extracted: dict[str, Any] = {"ocr_engine": ocr.name, "vlm_used": False}

    lines = ocr.read(img)
    guess = guess_product_text(lines, img.height)
    extracted.update(
        has_text=guess.has_text,
        product_name=guess.product_name,
        brand=guess.brand,
        model_number=guess.model_number,
        spec=guess.spec,
        is_coupang_screenshot=guess.is_coupang_screenshot,
        confidence=guess.confidence,
    )

    queries: list[str] = []
    force_selection = False
    if guess.query and guess.confidence >= LOW_CONFIDENCE:
        queries = [guess.query]
    elif vlm.available:
        v = vlm.extract(img)
        if v:
            extracted.update({k: v.get(k) for k in ("brand", "product_name", "model_number", "spec", "category_guess") if v.get(k)})
            extracted["vlm_used"] = True
            extracted["confidence"] = max(float(extracted.get("confidence") or 0), float(v.get("confidence") or 0))
            if v.get("has_text") and v.get("product_name"):
                queries = [" ".join(x for x in (v.get("brand"), v.get("product_name"), v.get("model_number")) if x)]
            else:
                # 글자가 없는 상품 사진: 시각 정보로 만든 검색어 2~3개, 항상 사용자 선택(README 5.1 (c) 4)
                queries = list(v.get("search_queries") or [])[:3]
                force_selection = True
    if not queries and guess.query:
        queries = [guess.query]  # 저신뢰여도 OCR 결과로 시도하되 사용자 선택을 받는다
        force_selection = True

    if not queries:
        return ResolveResult(
            status="not_found",
            input_type="image",
            extracted=extracted,
            message="이미지에서 상품명을 찾지 못했어요. 상품명이 보이게 캡처하거나 상품명을 직접 입력해 주세요.",
        )

    results = []
    for q in queries:
        r = search(q, extracted.get("brand"), force_selection)
        r.input_type = "image"
        results.append(r)
    if any(r.status == "blocked" for r in results):
        return ResolveResult(status="blocked", input_type="image", extracted=extracted, query=queries[0])
    if len(results) == 1:
        r = results[0]
        r.extracted = extracted
        return r
    merged = _merge_candidates([r.candidates for r in results], settings.resolve_max_candidates)
    return ResolveResult(
        status="needs_selection" if merged else "not_found",
        candidates=merged,
        input_type="image",
        query=" / ".join(queries),
        extracted=extracted,
        message=None if merged else "비슷한 상품을 찾지 못했어요. 상품명을 직접 입력해 주세요.",
    )
