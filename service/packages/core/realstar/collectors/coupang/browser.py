"""WebDriver 생성·재사용, 속도 제한, 페이지 로드 상한 (README 0-3, 5.2).

규칙
- 브라우저 1개. 페이지 이동·조작 사이 무작위 대기(기본 3~7초).
- 분석 1건당 페이지 로드 상한, 일일 상한.
- 공개 영역(selectors.yaml urls.allowed_patterns)만 연다. 로그인·장바구니·주문 페이지는 금지.
- 차단 우회 기능 없음: stealth 패치, 프록시, User-Agent 위조, CAPTCHA 풀이를 하지 않는다.
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

from realstar.collectors.coupang.block_detector import BlockDetector
from realstar.collectors.coupang.selectors import Selectors
from realstar.config import Settings
from realstar.errors import ForbiddenAreaError, PageBudgetExceededError
from realstar.state.store import StateStore, daily_pages_key

log = logging.getLogger(__name__)


class DriverLike(Protocol):
    """테스트용 가짜 드라이버도 구현할 수 있는 최소 WebDriver 인터페이스."""

    page_source: str
    current_url: str
    title: str

    def get(self, url: str) -> None: ...
    def find_elements(self, by: str, value: str) -> list[Any]: ...
    def execute_script(self, script: str, *args: Any) -> Any: ...
    def set_page_load_timeout(self, seconds: float) -> None: ...
    def quit(self) -> None: ...


def default_driver_factory(settings: Settings) -> DriverLike:
    """Selenium 4 + Selenium Manager로 Chrome을 띄운다. 기본 프로필, 기본 User-Agent 그대로."""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service

    options = webdriver.ChromeOptions()
    if settings.scraper_headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--lang=ko-KR")
    if settings.scraper_chrome_container:
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
    if settings.scraper_chrome_binary:
        options.binary_location = settings.scraper_chrome_binary
    service = Service(executable_path=settings.scraper_chromedriver_path) if settings.scraper_chromedriver_path else Service()
    driver = webdriver.Chrome(options=options, service=service)
    driver.set_page_load_timeout(settings.scraper_page_load_timeout_sec)
    return driver  # type: ignore[return-value]


class BrowserSession:
    """분석 1건(또는 학습용 배치 1건) 동안 쓰는 단일 브라우저 세션."""

    def __init__(
        self,
        settings: Settings,
        selectors: Selectors,
        state: StateStore,
        *,
        driver_factory: Callable[[Settings], DriverLike] = default_driver_factory,
        sleeper: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        max_pages: int | None = None,
        max_pages_per_day: int | None = None,
        delay_range: tuple[float, float] | None = None,
        budget_scope: str = "service",
    ) -> None:
        self.settings = settings
        self.selectors = selectors
        self.state = state
        self._driver_factory = driver_factory
        self._driver: DriverLike | None = None
        self._sleep = sleeper
        self._rng = rng or random.Random()
        self.max_pages = max_pages or settings.scraper_max_pages_per_analysis
        self.max_pages_per_day = max_pages_per_day or settings.scraper_max_pages_per_day
        self.delay_range = delay_range or (settings.scraper_delay_min_sec, settings.scraper_delay_max_sec)
        self.budget_scope = budget_scope
        self.pages_loaded = 0
        self.actions = 0
        self._last_action_at: float | None = None
        urls = selectors.section("urls")
        self._allowed = [re.compile(p) for p in urls.get("allowed_patterns", [])]
        self.block_detector = BlockDetector(selectors, settings.scraper_empty_streak_limit)

    # ── 드라이버 ──────────────────────────────────────────
    @property
    def driver(self) -> DriverLike:
        if self._driver is None:
            self._driver = self._driver_factory(self.settings)
        return self._driver

    @property
    def started(self) -> bool:
        return self._driver is not None

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:  # pragma: no cover - 종료 실패는 로그만
                log.warning("driver quit failed", exc_info=True)
            self._driver = None

    def __enter__(self) -> BrowserSession:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── 속도 제한 ──────────────────────────────────────────
    def human_delay(self) -> float:
        """첫 동작을 제외하고, 직전 동작 이후 무작위 대기 시간이 지나도록 기다린다."""
        if self._last_action_at is None:
            self._last_action_at = time.monotonic()
            return 0.0
        lo, hi = self.delay_range
        wait = self._rng.uniform(lo, hi)
        elapsed = time.monotonic() - self._last_action_at
        remaining = max(0.0, wait - elapsed)
        if remaining > 0:
            self._sleep(remaining)
        self._last_action_at = time.monotonic()
        return remaining

    def consume_page_budget(self) -> None:
        if self.pages_loaded >= self.max_pages:
            raise PageBudgetExceededError("analysis", self.max_pages)
        used = self.state.incr(daily_pages_key(self.budget_scope), 1, ttl_sec=26 * 3600)
        if used > self.max_pages_per_day:
            raise PageBudgetExceededError("daily", self.max_pages_per_day)
        self.pages_loaded += 1

    # ── 탐색 ──────────────────────────────────────────────
    def assert_allowed(self, url: str) -> None:
        self.block_detector.check_url(url)
        if not any(rx.search(url) for rx in self._allowed):
            raise ForbiddenAreaError(f"url not in allowed public areas: {url}")

    def get(self, url: str) -> str:
        """공개 페이지를 열고 차단 여부를 검사한 뒤 page_source를 돌려준다."""
        self.assert_allowed(url)
        self.consume_page_budget()
        self.human_delay()
        log.info("open page #%d %s", self.pages_loaded, url)
        self.driver.get(url)
        return self.after_navigation()

    def after_navigation(self) -> str:
        html = self.driver.page_source
        self.block_detector.check_page(html, self.driver.current_url, self.driver.title)
        return html

    def wait_for_any(self, css_candidates: list[str], timeout: float | None = None) -> bool:
        """명시적 대기(WebDriverWait). 후보 중 하나라도 나타나면 True."""
        if not css_candidates:
            return True
        timeout = timeout if timeout is not None else self.settings.scraper_page_load_timeout_sec
        deadline = time.monotonic() + timeout
        while True:
            for css in css_candidates:
                if self.driver.find_elements("css selector", css):
                    return True
            if time.monotonic() >= deadline:
                return False
            self._sleep(0.3)

    def wait_until(self, predicate: Callable[[], bool], timeout: float | None = None) -> bool:
        timeout = timeout if timeout is not None else self.settings.scraper_page_load_timeout_sec
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                return False
            self._sleep(0.3)
        return True

    def click_first(self, css_candidates: list[str]) -> bool:
        """조작도 대기 규칙을 따른다. 클릭은 페이지 로드 수에 넣지 않고 actions로 센다."""
        for css in css_candidates:
            elements = self.driver.find_elements("css selector", css)
            if elements:
                self.human_delay()
                el = elements[0]
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                el.click()
                self.actions += 1
                return True
        return False

    def scroll_into_view(self, css_candidates: list[str]) -> bool:
        for css in css_candidates:
            elements = self.driver.find_elements("css selector", css)
            if elements:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", elements[0])
                return True
        return False

    @property
    def page_source(self) -> str:
        return self.driver.page_source

    @property
    def current_url(self) -> str:
        return self.driver.current_url
