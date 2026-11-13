"""CoupangScraperProvider: ReviewProvider 운영 구현 (Selenium + BeautifulSoup)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import quote_plus

from realstar.collectors.base import ProductMeta, ProgressCallback, RawReview, SearchCandidate, SortOrder
from realstar.collectors.coupang.browser import BrowserSession, DriverLike, default_driver_factory
from realstar.collectors.coupang.product_page import parse_product_page
from realstar.collectors.coupang.review_page import DebugHtmlStore, ReviewCollector
from realstar.collectors.coupang.search_page import parse_search_page
from realstar.collectors.coupang.selectors import Selectors, load_selectors
from realstar.config import Settings
from realstar.state.store import StateStore

log = logging.getLogger(__name__)


class CoupangScraperProvider:
    """분석 1건 동안 브라우저 1개를 재사용한다. 전역 동시 실행 1개 제한은 호출자(파이프라인)가 락으로 보장한다."""

    def __init__(
        self,
        settings: Settings,
        state: StateStore,
        *,
        selectors: Selectors | None = None,
        driver_factory: Callable[[Settings], DriverLike] = default_driver_factory,
        browser: BrowserSession | None = None,
        training: bool = False,
    ) -> None:
        self.settings = settings
        self.selectors = selectors or load_selectors()
        if browser is None:
            kwargs = {}
            if training:
                kwargs = {
                    "delay_range": (settings.training_delay_min_sec, settings.training_delay_max_sec),
                    "max_pages_per_day": settings.training_max_pages_per_day,
                    "max_pages": 10_000,
                    "budget_scope": "training",
                }
            browser = BrowserSession(settings, self.selectors, state, driver_factory=driver_factory, **kwargs)  # type: ignore[arg-type]
        self.browser = browser
        self.collector = ReviewCollector(
            self.browser,
            self.selectors,
            salt=settings.author_hash_salt,
            fail_threshold=settings.scraper_parser_fail_threshold,
            debug_store=DebugHtmlStore(settings.scraper_debug_html_dir, settings.scraper_debug_html_keep),
        )
        self._product_loaded: str | None = None
        self._meta_cache: dict[str, ProductMeta] = {}

    @property
    def selectors_version(self) -> str:
        return self.selectors.version

    @property
    def pages_loaded(self) -> int:
        return self.browser.pages_loaded

    def _product_url(self, product_id: str) -> str:
        return str(self.selectors.get("urls", "product")).format(product_id=product_id)

    def _open_product(self, product_id: str) -> str:
        url = self._product_url(product_id)
        self.browser.get(url)
        self.browser.wait_for_any(self.selectors.css_list("product", "ready"))
        # 리뷰 요약(별점 분포)이 지연 로딩되므로 리뷰 영역까지 스크롤하고 기다린다
        self.collector.prepare_review_area()
        self._product_loaded = product_id
        return self.browser.after_navigation()

    def get_product_meta(self, product_id: str) -> ProductMeta:
        if product_id in self._meta_cache:
            return self._meta_cache[product_id]
        html = self._open_product(product_id)
        meta = parse_product_page(html, self.selectors, product_id, url=self._product_url(product_id))
        self._meta_cache[product_id] = meta
        return meta

    def get_reviews(
        self,
        product_id: str,
        star: int,
        limit: int,
        sort: SortOrder = "latest",
        on_progress: ProgressCallback | None = None,
    ) -> list[RawReview]:
        meta = self._meta_cache.get(product_id)
        expected = None
        if meta is not None and meta.total_reviews:
            try:
                expected = meta.resolved_star_counts()[star]
            except ValueError:
                expected = None
        if self.collector.mode == "interactive" and self._product_loaded != product_id:
            self._open_product(product_id)
        return self.collector.collect(product_id, star, limit, sort, expected_total=expected, on_progress=on_progress)

    def search(self, query: str) -> list[SearchCandidate]:
        url = str(self.selectors.get("urls", "search")).format(query=quote_plus(query))
        self.browser.get(url)
        self.browser.wait_for_any(self.selectors.css_list("search", "ready"))
        html = self.browser.after_navigation()
        self._product_loaded = None
        return parse_search_page(html, self.selectors, self.settings.scraper_parser_fail_threshold)

    def resolve_short_url(self, url: str) -> str:
        """공유·단축 링크를 브라우저로 열어 최종 URL을 얻는다(README 5.1 (a))."""
        self.browser.get(url)
        final = self.browser.current_url
        self.browser.block_detector.check_url(final)
        self._product_loaded = None
        return final

    def close(self) -> None:
        self.browser.close()
