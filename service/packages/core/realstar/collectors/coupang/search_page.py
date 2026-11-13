"""검색 결과 페이지 파서 (README 5.1 (b)). 첫 페이지만 사용한다."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from realstar.collectors.base import SearchCandidate
from realstar.collectors.coupang.selectors import (
    Selectors,
    make_soup,
    parse_float,
    parse_int,
    select_all,
    select_first,
    text_of,
)
from realstar.errors import ParserBrokenError

PRODUCT_PATH_RE = re.compile(r"/vp/products/(\d+)")


def _abs_url(base: str, href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("//"):
        return "https:" + href
    return urljoin(base, href)


def parse_search_page(html: str, selectors: Selectors, fail_threshold: float = 0.2) -> list[SearchCandidate]:
    sel = selectors.section("search")
    base = selectors.get("urls", "base", "https://www.coupang.com")
    soup = make_soup(html)
    items = select_all(soup, sel.get("item", []))
    ad_class_patterns = [re.compile(p) for p in sel.get("ad_item_class_patterns", [])]
    out: list[SearchCandidate] = []
    seen: set[str] = set()
    missing_name = 0
    for li in items:
        link = select_first(li, sel.get("link", []))
        href = str(link.get("href")) if link is not None and link.get("href") else None
        m = PRODUCT_PATH_RE.search(href or "")
        if not m:
            continue
        product_id = m.group(1)
        qs = parse_qs(urlparse(href or "").query)
        img = select_first(li, sel.get("image", []))
        img_src = None
        if img is not None:
            for attr in ("data-img-src", "data-src", "src"):
                v = img.get(attr)
                if v and not str(v).startswith("data:"):
                    img_src = _abs_url(base, str(v))
                    break
        name = text_of(select_first(li, sel.get("name", [])))
        if not name:
            missing_name += 1
        raw_cls = li.get("class")
        classes = " ".join(raw_cls) if isinstance(raw_cls, list) else str(raw_cls or "")
        is_ad = select_first(li, sel.get("ad_badge", [])) is not None or any(rx.search(classes) for rx in ad_class_patterns)
        key = f"{product_id}:{(qs.get('itemId') or [''])[0]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            SearchCandidate(
                product_id=product_id,
                item_id=(qs.get("itemId") or [""])[0] or None,
                vendor_item_id=(qs.get("vendorItemId") or [""])[0] or None,
                name=name,
                price=parse_int(text_of(select_first(li, sel.get("price", [])))),
                image_url=img_src,
                url=_abs_url(base, href),
                is_ad=is_ad,
                rating=parse_float(text_of(select_first(li, sel.get("rating", [])))),
                review_count=parse_int(text_of(select_first(li, sel.get("review_count", [])))),
            )
        )
    if out and missing_name / max(1, len(out)) > fail_threshold:
        raise ParserBrokenError("search", {"name": missing_name / len(out)})
    return out
