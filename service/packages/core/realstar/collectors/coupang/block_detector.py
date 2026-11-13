from __future__ import annotations

import re

from realstar.collectors.coupang.selectors import Selectors, make_soup
from realstar.errors import BlockedError, ForbiddenAreaError


class BlockDetector:
    def __init__(self, selectors: Selectors, empty_streak_limit: int = 3) -> None:
        self.selectors = selectors
        block = selectors.section("block")
        self._title_res = [re.compile(p, re.I) for p in block.get("title_patterns", [])]
        self._body_res = [re.compile(p, re.I) for p in block.get("body_patterns", [])]
        self._element_css = list(block.get("element_selectors", []))
        urls = selectors.section("urls")
        self._forbidden_res = [re.compile(p, re.I) for p in urls.get("forbidden_patterns", [])]
        self.empty_streak_limit = empty_streak_limit
        self._empty_streak = 0

    # ── 페이지 단위 판정 ──────────────────────────────────
    def check_page(self, html: str, current_url: str | None = None, title: str | None = None) -> None:
        if current_url:
            self.check_url(current_url)
        soup = make_soup(html or "")
        page_title = title if title is not None else (soup.title.get_text(strip=True) if soup.title else "")
        for rx in self._title_res:
            if rx.search(page_title or ""):
                raise BlockedError("block_title", f"title matched {rx.pattern!r}: {page_title[:80]}")
        for css in self._element_css:
            if soup.select_one(css) is not None:
                raise BlockedError("captcha_or_challenge", f"element {css!r} present")
        body_text = soup.get_text(" ", strip=True)[:20000]
        # 본문이 매우 짧은 페이지에서만 본문 문구를 검사한다(정상 페이지의 리뷰 본문 오탐 방지).
        if len(body_text) < 3000:
            for rx in self._body_res:
                if rx.search(body_text):
                    raise BlockedError("access_denied", f"body matched {rx.pattern!r}")

    def check_url(self, url: str) -> None:
        for rx in self._forbidden_res:
            if rx.search(url):
                raise ForbiddenAreaError(f"redirected to forbidden area: {url}")

    # ── 연속 빈 결과 판정 ──────────────────────────────────
    def record_review_page(self, n_reviews: int, expected_more: bool) -> None:
        """리뷰가 더 있어야 하는데 빈 페이지가 연속으로 나오면 차단으로 본다."""
        if n_reviews > 0 or not expected_more:
            self._empty_streak = 0
            return
        self._empty_streak += 1
        if self._empty_streak >= self.empty_streak_limit:
            raise BlockedError("empty_streak", f"{self._empty_streak} consecutive empty review pages")

    def reset_streak(self) -> None:
        self._empty_streak = 0
