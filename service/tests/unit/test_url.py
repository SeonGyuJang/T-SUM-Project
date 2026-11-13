from __future__ import annotations

import pytest

from realstar.errors import InvalidInputError
from realstar.resolver.url import classify, extract_url, is_short_link, parse_product_url

CASES = [
    ("https://www.coupang.com/vp/products/7335597976?itemId=18741704367&vendorItemId=85873964906", ("7335597976", "18741704367", "85873964906")),
    ("https://www.coupang.com/vp/products/7335597976", ("7335597976", None, None)),
    ("http://coupang.com/vp/products/123456?vendorItemId=99", ("123456", None, "99")),
    ("https://m.coupang.com/vm/products/123456?itemId=1&vendorItemId=2", ("123456", "1", "2")),
    ("https://m.coupang.com/vm/products/123456/items/777/vendoritems/888", ("123456", "777", "888")),
    ("https://m.coupang.com/vp/products/42", ("42", None, None)),
    ("https://www.coupang.com/vp/products/555?itemId=10&vendorItemId=20&sourceType=srp_product_ads&clickEventId=abc&q=%EC%B2%AD%EC%86%8C%EA%B8%B0", ("555", "10", "20")),
    ("https://www.coupang.com/vp/products/555/?ItemId=10", ("555", "10", None)),
    ("https://www.coupang.com/vp/products/555?itemId=abc", ("555", None, None)),
    ("https://www.coupang.com/vp/products/555#sdpReview", ("555", None, None)),
]


@pytest.mark.parametrize(("url", "expected"), CASES)
def test_parse_product_url(url: str, expected: tuple[str, str | None, str | None]) -> None:
    p = parse_product_url(url)
    assert p is not None
    assert (p.product_id, p.item_id, p.vendor_item_id) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://www.coupang.com/np/search?q=청소기",
        "https://www.coupang.com/vp/products/",
        "https://coupang.com.evil.example/vp/products/123",
        "https://www.gmarket.co.kr/vp/products/123",
        "https://cart.coupang.com/cartView.pang",
    ],
)
def test_not_product_urls(url: str) -> None:
    assert parse_product_url(url) is None


def test_short_links() -> None:
    assert is_short_link("https://link.coupang.com/a/bXyZ12")
    assert is_short_link("https://coupa.ng/abcd")
    url, parsed = classify("https://link.coupang.com/a/bXyZ12")
    assert parsed is None and url.endswith("bXyZ12")


def test_extract_from_share_text() -> None:
    text = "[쿠팡] 무선 청소기 A100 화이트\nhttps://link.coupang.com/a/demo01 지금 할인 중!"
    assert extract_url(text) == "https://link.coupang.com/a/demo01"
    assert extract_url("www.coupang.com/vp/products/1?itemId=2") == "https://www.coupang.com/vp/products/1?itemId=2"


def test_canonical_url() -> None:
    p = parse_product_url("https://m.coupang.com/vm/products/9?itemId=1&vendorItemId=2")
    assert p is not None and p.canonical_url == "https://www.coupang.com/vp/products/9?itemId=1&vendorItemId=2"


def test_classify_errors() -> None:
    with pytest.raises(InvalidInputError):
        classify("그냥 텍스트")
    with pytest.raises(InvalidInputError) as e:
        classify("https://www.coupang.com/np/search?q=a")
    assert "상품 상세" in e.value.user_message
    with pytest.raises(InvalidInputError) as e2:
        classify("https://www.11st.co.kr/products/1")
    assert "쿠팡" in e2.value.user_message
