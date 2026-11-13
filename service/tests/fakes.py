"""Selenium 없이 BrowserSession·ReviewCollector를 시험하는 가짜 쿠팡 화면.

실제 사이트에 접속하지 않는다(README 10: CI에서는 실제 쿠팡에 접속하지 않는다).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup


def review_article(rid: str, star: int, text: str, date: str = "2026.10.01") -> str:
    return (
        f'<article class="sdp-review__article__list" data-review-id="{rid}">'
        f'<div class="sdp-review__article__list__info__product-info__star-orange" data-rating="{star}"></div>'
        f'<div class="sdp-review__article__list__info__product-info__reg-date">{date}</div>'
        f'<div class="sdp-review__article__list__review__content">{text}</div></article>'
    )


@dataclass
class FakeElement:
    site: FakeCoupangSite
    css: str
    attrs: dict[str, Any]

    def click(self) -> None:
        self.site.on_click(self.css, self.attrs)


@dataclass
class FakeCoupangSite:
    counts: dict[int, int]
    page_size: int = 5
    star: int | None = None
    page: int = 1
    sorted_latest: bool = False
    current_url: str = "about:blank"
    title: str = ""
    visited: list[str] = field(default_factory=list)
    clicks: list[str] = field(default_factory=list)
    block_after_visits: int | None = None
    empty_reviews: bool = False
    redirect: dict[str, str] = field(default_factory=dict)

    # ── WebDriver 흉내 ────────────────────────────────────
    def get(self, url: str) -> None:
        self.visited.append(url)
        self.current_url = self.redirect.get(url, url)
        if "/vp/products/" in url:
            self.star, self.page = None, 1

    def set_page_load_timeout(self, s: float) -> None: ...

    def quit(self) -> None: ...

    def execute_script(self, script: str, *args: Any) -> None: ...

    def find_elements(self, by: str, css: str) -> list[FakeElement]:
        soup = BeautifulSoup(self.page_source, "lxml")
        return [FakeElement(self, css, dict(el.attrs)) for el in soup.select(css)]

    def on_click(self, css: str, attrs: dict[str, Any]) -> None:
        self.clicks.append(css)
        if "newest-btn" in css:
            self.sorted_latest = True
        elif "star__list__item" in css and attrs.get("data-rating"):
            self.star, self.page = int(attrs["data-rating"]), 1
        elif "page__num" in css and attrs.get("data-page"):
            self.page = int(attrs["data-page"])

    # ── 화면 렌더링 ──────────────────────────────────────
    def _reviews_html(self, star: int, page: int) -> str:
        if self.empty_reviews:
            return ""
        n = self.counts.get(star, 0)
        start = (page - 1) * self.page_size
        return "".join(review_article(f"{star}-{i}", star, f"{star}점 리뷰 {i}번 본문입니다 {'최신' if self.sorted_latest else '기본'}") for i in range(start, min(n, start + self.page_size)))

    @property
    def page_source(self) -> str:
        if self.block_after_visits is not None and len(self.visited) > self.block_after_visits:
            self.title = "Access Denied"
            return "<html><head><title>Access Denied</title></head><body>Access Denied</body></html>"
        self.title = "쿠팡!"
        u = urlparse(self.current_url)
        if u.path.startswith("/vp/product/reviews"):
            q = parse_qs(u.query)
            body = self._reviews_html(int(q["ratings"][0]), int(q["page"][0]))
            return f"<html><body><div class='sdp-review'>{body}</div></body></html>"
        if u.path.startswith("/np/search"):
            return "<html><body><ul id='productList'><li class='search-product'><a href='/vp/products/1?itemId=2'><div class='name'>상품</div></a></li></ul></body></html>"
        if not u.path.startswith("/vp/products/"):
            return "<html><body>other</body></html>"
        total = sum(self.counts.values())
        rows = "".join(
            f'<div class="sdp-review__article__order__star__list__item" data-rating="{s}"><span class="sdp-review__article__order__star__list__item__count">{c}</span></div>'
            for s, c in self.counts.items()
        )
        listing = ""
        pages = ""
        if self.star is not None:
            listing = self._reviews_html(self.star, self.page)
            n_pages = -(-self.counts.get(self.star, 0) // self.page_size)
            pages = "".join(f'<button class="sdp-review__article__page__num" data-page="{p}">{p}</button>' for p in range(1, n_pages + 1))
        elif total:
            listing = review_article("default-1", 5, "기본 목록 첫 리뷰")
        return (
            "<html><head><title>쿠팡!</title></head><body>"
            '<h2 class="prod-buy-header__title">가짜 상품</h2>'
            f'<span class="rating-star-num" style="width: 90%"></span><span class="count">{total:,}개 상품평</span>'
            '<div id="sdpReview" class="sdp-review">'
            '<button class="sdp-review__article__order__sort__newest-btn">최신순</button>'
            f'<div class="sdp-review__article__order__star__all">전체</div><div class="sdp-review__article__order__star__list">{rows}</div>'
            f'<div class="js_reviewArticleListContainer">{listing}</div><div class="sdp-review__article__page">{pages}</div>'
            "</div></body></html>"
        )
