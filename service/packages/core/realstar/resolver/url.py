"""쿠팡 상품 URL 파싱 (README 5.1 (a), F1).

- 정규식으로 바로 추출되면 브라우저를 열지 않는다.
- 공유·단축 링크만 브라우저로 열어 최종 URL을 얻은 뒤 다시 파싱한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from realstar.errors import InvalidInputError

COUPANG_HOSTS = {"coupang.com", "www.coupang.com", "m.coupang.com"}
SHORT_LINK_HOSTS = {"link.coupang.com", "coupa.ng", "www.coupa.ng"}

_PRODUCT_PATH = re.compile(r"^/(?:vp|vm)/products/(\d+)(?:/|$)")
_ITEMS_PATH = re.compile(r"/items/(\d+)")
_VENDOR_ITEMS_PATH = re.compile(r"/vendoritems/(\d+)", re.I)
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+|(?:www\.|m\.|link\.)?coupang\.com/[^\s<>\"']+|coupa\.ng/[^\s<>\"']+", re.I)


@dataclass(frozen=True)
class ParsedProductUrl:
    product_id: str
    item_id: str | None
    vendor_item_id: str | None

    @property
    def canonical_url(self) -> str:
        url = f"https://www.coupang.com/vp/products/{self.product_id}"
        params = []
        if self.item_id:
            params.append(f"itemId={self.item_id}")
        if self.vendor_item_id:
            params.append(f"vendorItemId={self.vendor_item_id}")
        return url + ("?" + "&".join(params) if params else "")


def extract_url(text: str) -> str:
    """공유 문구("[쿠팡] 상품명 https://link.coupang.com/a/abc")에서 URL만 꺼낸다."""
    text = (text or "").strip()
    m = _URL_IN_TEXT.search(text)
    if not m:
        raise InvalidInputError("no url", "쿠팡 상품 링크를 붙여 넣어 주세요.")
    url = m.group(0).rstrip(").,]")
    if not url.lower().startswith("http"):
        url = "https://" + url
    return url


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_short_link(url: str) -> bool:
    return _host(url) in SHORT_LINK_HOSTS


def parse_product_url(url: str) -> ParsedProductUrl | None:
    """PC·모바일 상품 URL이면 ID를 돌려준다. 쿠팡 상품 URL이 아니면 None."""
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in COUPANG_HOSTS:
        return None
    m = _PRODUCT_PATH.match(parsed.path)
    if not m:
        return None
    qs = {k.lower(): v for k, v in parse_qs(parsed.query).items()}
    item: str | None = (qs.get("itemid") or [""])[0] or None
    vendor: str | None = (qs.get("vendoritemid") or [""])[0] or None
    if item is None and (mi := _ITEMS_PATH.search(parsed.path)):
        item = mi.group(1)
    if vendor is None and (mv := _VENDOR_ITEMS_PATH.search(parsed.path)):
        vendor = mv.group(1)
    item = item if item and item.isdigit() else None
    vendor = vendor if vendor and vendor.isdigit() else None
    return ParsedProductUrl(m.group(1), item, vendor)


def classify(text: str) -> tuple[str, ParsedProductUrl | None]:
    """입력 텍스트를 ('product', parsed) | ('short', None)으로 분류한다. 그 외는 InvalidInputError."""
    url = extract_url(text)
    if is_short_link(url):
        return url, None
    parsed = parse_product_url(url)
    if parsed is None:
        host = _host(url)
        if host.endswith("coupang.com"):
            raise InvalidInputError(f"not a product url: {url}", "상품 상세 페이지 링크를 넣어 주세요. (검색·장바구니 페이지는 분석할 수 없어요)")
        raise InvalidInputError(f"not coupang: {url}", "지금은 쿠팡 상품 링크만 분석할 수 있어요.")
    return url, parsed
