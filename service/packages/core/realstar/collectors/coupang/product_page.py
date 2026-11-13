"""상품 페이지 메타 파서: 상품명, 표시 평균, 총 리뷰 수, 별점별 개수/비율 (README 5.2)."""

from __future__ import annotations

import re

from realstar.collectors.base import STARS, ProductMeta
from realstar.collectors.coupang.selectors import (
    Selectors,
    make_soup,
    parse_float,
    parse_int,
    parse_width_percent,
    select_all,
    select_first,
    text_of,
)
from realstar.errors import ParserBrokenError


def _parse_star_rows(soup, sel: dict) -> tuple[dict[int, int] | None, dict[int, float] | None]:  # type: ignore[no-untyped-def]
    rows = select_all(soup, sel.get("star_rows", []))
    counts: dict[int, int] = {}
    ratios: dict[int, float] = {}
    attr = sel.get("star_row_star_attr", "data-rating")
    for row in rows:
        star: int | None = None
        if row.get(attr):
            star = parse_int(str(row.get(attr)))
        if star is None:
            star = parse_int(text_of(select_first(row, sel.get("star_row_star_text", []))))
        if star is None or star not in STARS:
            continue
        cnt_node = select_first(row, sel.get("star_row_count", []))
        cnt_text = text_of(cnt_node)
        if cnt_text and "%" not in cnt_text:
            c = parse_int(cnt_text)
            if c is not None:
                counts[star] = c
        pct_node = select_first(row, sel.get("star_row_percent", []))
        pct = parse_float(text_of(pct_node)) if pct_node is not None and "%" in (text_of(pct_node) or "") else None
        if pct is None:
            pct = parse_width_percent(pct_node)
        if pct is None and cnt_text and "%" in cnt_text:
            pct = parse_float(cnt_text)
        if pct is not None:
            ratios[star] = pct / 100.0
    full_counts = counts if len(counts) == 5 else None
    full_ratios = ratios if len(ratios) == 5 else None
    return full_counts, full_ratios


def parse_product_page(html: str, selectors: Selectors, product_id: str, url: str | None = None) -> ProductMeta:
    sel = selectors.section("product")
    soup = make_soup(html)
    name = text_of(select_first(soup, sel.get("name", [])))

    displayed_avg = None
    avg_node = select_first(soup, sel.get("avg_text", []))
    avg_text = text_of(avg_node)
    if avg_text:
        v = parse_float(avg_text)
        if v is not None and 0 <= v <= 5:
            displayed_avg = v
    if displayed_avg is None:
        width = parse_width_percent(select_first(soup, sel.get("avg_width", [])))
        if width is not None:
            displayed_avg = round(width / 20.0, 2)

    total_reviews = None
    total_node = select_first(soup, sel.get("total_reviews", []))
    total_text = text_of(total_node)
    if total_text:
        m = re.search(sel.get("total_reviews_pattern", r"([\d,]+)"), total_text)
        total_reviews = int(m.group(1).replace(",", "")) if m else parse_int(total_text)

    star_counts, star_ratio = _parse_star_rows(soup, sel)
    if total_reviews is None and star_counts:
        total_reviews = sum(star_counts.values())

    img = select_first(soup, sel.get("image", []))
    image_url = None
    if img is not None:
        src = img.get("src") or img.get("data-src")
        if src:
            image_url = "https:" + str(src) if str(src).startswith("//") else str(src)

    failed: dict[str, float] = {}
    if not name:
        failed["name"] = 1.0
    if total_reviews is None:
        failed["total_reviews"] = 1.0
    if total_reviews and not (star_counts or star_ratio):
        failed["star_distribution"] = 1.0
    if failed:
        raise ParserBrokenError("product", failed)

    return ProductMeta(
        product_id=product_id,
        name=name or "",
        image_url=image_url,
        url=url,
        category=text_of(select_first(soup, sel.get("category", []))),
        displayed_avg=displayed_avg,
        total_reviews=int(total_reviews or 0),
        star_counts=star_counts,
        star_ratio=star_ratio,
    )
