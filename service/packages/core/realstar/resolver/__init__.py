"""상품 식별: 링크 / 상품명 / 캡처 이미지 (README 5.1)."""

from __future__ import annotations

from realstar.collectors.base import ReviewProvider, SearchCandidate
from realstar.errors import InvalidInputError
from realstar.resolver.models import ResolveResult
from realstar.resolver.url import classify, parse_product_url


def resolve_url(text: str, provider: ReviewProvider | None) -> ResolveResult:
    """정규식으로 추출되면 브라우저를 열지 않는다. 단축 링크만 provider(브라우저)로 연다."""
    url, parsed = classify(text)
    if parsed is None:
        if provider is None:
            raise InvalidInputError("short link needs browser")
        final = provider.resolve_short_url(url)
        parsed = parse_product_url(final)
        if parsed is None:
            raise InvalidInputError(f"short link resolved to non-product {final}", "링크가 상품 페이지로 연결되지 않아요. 상품 페이지 주소를 넣어 주세요.")
    cand = SearchCandidate(
        product_id=parsed.product_id,
        item_id=parsed.item_id,
        vendor_item_id=parsed.vendor_item_id,
        url=parsed.canonical_url,
        match_score=1.0,
    )
    return ResolveResult(status="resolved", candidates=[cand], input_type="url", query=url)


__all__ = ["ResolveResult", "resolve_url"]
