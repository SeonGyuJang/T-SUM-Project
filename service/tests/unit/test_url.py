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


# 오너가 준 실제 상품 링크(2026-11-13, 시연 후보). 광고·검색 추적 파라미터가 붙어 있다.
REAL_LINKS = [
    ("https://www.coupang.com/vp/products/9727152538?itemId=29108761203&vendorItemId=96027261679&sourceType=srp_product_ads&clickEventId=a61ba9f0-df4e-11f1-b948-e3a3976c00ad&clickEventId=a61ba9f0-df4e-11f1-b948-e3a3976c00ad&korePlacement=15&korePlacement=15&koreSubPlacement=5&koreSubPlacement=5&q=%EC%A0%84%EA%B8%B0%EC%9E%A5%ED%8C%90&searchId=2ec5ff423648677&searchRank=1&traceId=mweuirws",
     ("9727152538", "29108761203", "96027261679")),
    ("https://www.coupang.com/vp/products/9751850127?itemId=29200410159&vendorItemId=96120828949&q=%EB%B9%84%ED%83%80%EB%AF%BC&searchId=b8384a8f3672714&sourceType=search&rank=16&itemsCount=60&searchRank=16&traceId=mweumu2g",
     ("9751850127", "29200410159", "96120828949")),
    ("https://www.coupang.com/vp/products/6495672127?itemId=23899285883&vendorItemId=90883714958&pickType=COU_PICK&q=%EB%B3%B4%ED%98%B8%ED%95%84%EB%A6%84&searchId=837fe5303680191&sourceType=search&rank=3&itemsCount=60&searchRank=3&traceId=mweuneub",
     ("6495672127", "23899285883", "90883714958")),
    ("https://www.coupang.com/vp/products/9413318168?itemId=28069822700&vendorItemId=95026426105&q=%EB%A7%A5%EB%B6%81&searchId=798ee2a13079849&sourceType=search&rank=0&itemsCount=60&searchRank=0&traceId=mweunspn",
     ("9413318168", "28069822700", "95026426105")),
]


@pytest.mark.parametrize(("url", "expected"), CASES + REAL_LINKS)
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
