"""HTML 스냅샷 기반 파서 테스트 (README 0-6). 스냅샷은 tests/fixtures/html/README.md 참고."""

from __future__ import annotations

import pytest

from realstar.collectors.coupang.block_detector import BlockDetector
from realstar.collectors.coupang.product_page import parse_product_page
from realstar.collectors.coupang.review_page import check_parse_health, has_no_review_marker, parse_reviews
from realstar.collectors.coupang.search_page import parse_search_page
from realstar.collectors.coupang.selectors import load_selectors
from realstar.errors import BlockedError, ForbiddenAreaError, ParserBrokenError
from tests.conftest import read_html

SEL = load_selectors()


def test_selectors_have_version() -> None:
    assert SEL.version
    for section in ("urls", "block", "search", "product", "reviews"):
        assert SEL.section(section)


def test_search_page() -> None:
    cands = parse_search_page(read_html("search_synthetic.html"), SEL)
    assert [c.product_id for c in cands] == ["1000000001", "1000000012", "1000000011"]
    first, ad, third = cands
    assert first.name == "[예시] 무선 청소기 A100 화이트"
    assert first.price == 189000 and first.item_id == "111" and first.vendor_item_id == "222"
    assert first.image_url == "https://thumbnail6.coupangcdn.com/thumbnails/a100.jpg"
    assert first.url and first.url.startswith("https://www.coupang.com/vp/products/1000000001")
    assert first.rating == 4.5 and first.review_count == 2000
    assert ad.is_ad and not first.is_ad
    assert ad.image_url == "https://thumbnail7.coupangcdn.com/thumbnails/mini.jpg"  # lazy-load data-img-src
    assert third.rating is None and third.review_count == 812


def test_product_page_counts() -> None:
    meta = parse_product_page(read_html("product_synthetic.html"), SEL, "1000000001")
    assert meta.name == "[예시] 무선 청소기 A100 화이트"
    assert meta.displayed_avg == 4.2  # width 84%
    assert meta.total_reviews == 2000
    assert meta.star_counts == {5: 1200, 4: 400, 3: 160, 2: 100, 1: 140}
    assert meta.resolved_star_counts() == {5: 1200, 4: 400, 3: 160, 2: 100, 1: 140}
    assert meta.image_url == "https://thumbnail9.coupangcdn.com/thumbnails/a100_main.jpg"
    assert meta.category == "청소기"


def test_product_page_ratio_only() -> None:
    meta = parse_product_page(read_html("product_ratio_synthetic.html"), SEL, "2")
    assert meta.star_counts is None and meta.star_ratio is not None
    assert meta.displayed_avg == 4.5 and meta.total_reviews == 1234
    n = meta.resolved_star_counts()  # N_s = round(total × ratio)
    assert n == {5: round(1234 * 0.70), 4: round(1234 * 0.15), 3: round(1234 * 0.07), 2: round(1234 * 0.03), 1: round(1234 * 0.05)}


def test_product_page_broken() -> None:
    with pytest.raises(ParserBrokenError) as e:
        parse_product_page("<html><body><div>바뀐 화면</div></body></html>", SEL, "1")
    assert "name" in e.value.failed_selectors


def test_reviews_page() -> None:
    reviews, stats = parse_reviews(read_html("reviews_synthetic_p1.html"), SEL, "1000000001", expected_star=5, salt="s")
    assert stats.items == 3 and len(reviews) == 3
    r1, r2, r3 = reviews
    assert r1.review_id == "900001" and r1.star == 5 and r1.created_at == "2026-10-01"
    assert r1.title == "한 달 써본 후기"
    assert r1.content == "흡입력 좋아요 ㅋㅋ\n배터리도 오래가요.\n강추!"  # <br> → 줄바꿈 유지, ㅋㅋ 보존
    assert r1.has_photo and r1.helpful_count == 7
    assert r1.option_name and "기본형" in r1.option_name
    assert r1.author_hash and r1.author_hash.startswith("sha256:") and "김" not in r1.author_hash  # 닉네임 원문 저장 안 함
    assert r2.review_id.startswith("h_") and r2.created_at == "2026-09-28"  # ID 없으면 내용 해시
    assert not r2.has_photo and r3.author_hash is None
    check_parse_health(stats, SEL, 0.2)


def test_reviews_page_broken_selectors() -> None:
    reviews, stats = parse_reviews(read_html("reviews_broken_synthetic.html"), SEL, "1", expected_star=5)
    assert reviews == [] and stats.items == 3
    with pytest.raises(ParserBrokenError) as e:
        check_parse_health(stats, SEL, 0.2)
    assert "reviews.content" in e.value.failed_selectors


def test_reviews_empty_marker() -> None:
    html = read_html("reviews_empty_synthetic.html")
    assert has_no_review_marker(html, SEL)
    assert parse_reviews(html, SEL, "1")[0] == []


@pytest.mark.parametrize(
    ("name", "signal"),
    [
        ("blocked_access_denied.html", "block_title"),
        ("blocked_captcha.html", "captcha_or_challenge"),
        ("blocked_permission_ko.html", "access_denied"),  # 실제 쿠팡 응답(2026-11-13, Ref 값 제거)
    ],
)
def test_block_pages(name: str, signal: str) -> None:
    with pytest.raises(BlockedError) as e:
        BlockDetector(SEL).check_page(read_html(name))
    assert e.value.signal == signal


def test_block_body_pattern_without_title() -> None:
    html = "<html><head><title>쿠팡</title></head><body>Access Denied. Reference #18.ab.12</body></html>"
    with pytest.raises(BlockedError) as e:
        BlockDetector(SEL).check_page(html)
    assert e.value.signal == "access_denied"


@pytest.mark.parametrize("name", ["product_synthetic.html", "reviews_synthetic_p1.html", "search_synthetic.html"])
def test_normal_pages_not_blocked(name: str) -> None:
    BlockDetector(SEL).check_page(read_html(name), "https://www.coupang.com/vp/products/1")


def test_forbidden_redirect() -> None:
    with pytest.raises(ForbiddenAreaError):
        BlockDetector(SEL).check_page("<html></html>", "https://login.coupang.com/login/login.pang?rtnUrl=x")


def test_empty_streak() -> None:
    bd = BlockDetector(SEL, empty_streak_limit=3)
    bd.record_review_page(0, expected_more=True)
    bd.record_review_page(0, expected_more=True)
    bd.record_review_page(5, expected_more=True)  # 정상 페이지가 나오면 초기화
    bd.record_review_page(0, expected_more=True)
    bd.record_review_page(0, expected_more=True)
    with pytest.raises(BlockedError) as e:
        bd.record_review_page(0, expected_more=True)
    assert e.value.signal == "empty_streak"
