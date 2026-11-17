"""BrowserSession(속도 제한·상한·금지 영역)과 CoupangScraperProvider 흐름을 가짜 드라이버로 검증."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from realstar.collectors.coupang.browser import HIDE_WEBDRIVER_JS, BrowserSession, default_driver_factory
from realstar.collectors.coupang.provider import CoupangScraperProvider
from realstar.collectors.coupang.selectors import Selectors, load_selectors
from realstar.config import Settings
from realstar.errors import BlockedError, ForbiddenAreaError, PageBudgetExceededError
from realstar.state.store import LocalStateStore
from tests.fakes import FakeCoupangSite

COUNTS = {5: 12, 4: 7, 3: 0, 2: 3, 1: 1}


class FakeOptions:
    def __init__(self) -> None:
        self.arguments: list[str] = []
        self.experimental: dict[str, object] = {}
        self.binary_location: str | None = None

    def add_argument(self, argument: str) -> None:
        self.arguments.append(argument)

    def add_experimental_option(self, name: str, value: object) -> None:
        self.experimental[name] = value


class FakeDriver:
    def __init__(self, user_agent: str = "Mozilla/5.0 Chrome/131.0.0.0 Safari/537.36") -> None:
        self.commands: list[tuple[str, dict[str, object]]] = []
        self.timeout: float | None = None
        self._user_agent = user_agent

    def execute_cdp_cmd(self, command: str, parameters: dict[str, object]) -> dict[str, object]:
        self.commands.append((command, parameters))
        if command == "Browser.getVersion":
            return {"userAgent": self._user_agent}
        return {}

    def set_page_load_timeout(self, seconds: float) -> None:
        self.timeout = seconds


def patch_selenium(monkeypatch: pytest.MonkeyPatch, driver: FakeDriver) -> dict[str, object]:
    from selenium import webdriver
    from selenium.webdriver.chrome import service as chrome_service

    captured: dict[str, object] = {}

    def create_options() -> FakeOptions:
        captured["options"] = FakeOptions()
        return captured["options"]  # type: ignore[return-value]

    def create_driver(**kwargs: object) -> FakeDriver:
        captured["driver_kwargs"] = kwargs
        return driver

    def create_service(**kwargs: object) -> object:
        captured["service_kwargs"] = kwargs
        return object()

    monkeypatch.setattr(webdriver, "ChromeOptions", create_options)
    monkeypatch.setattr(webdriver, "Chrome", create_driver)
    monkeypatch.setattr(chrome_service, "Service", create_service)
    return captured


def test_default_driver_factory_applies_configured_headers(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver()
    captured = patch_selenium(monkeypatch, driver)
    configured = settings.model_copy(update={
        "scraper_user_agent": "TestBrowser/1.0",
        "scraper_custom_headers": {"X-Client": "realstar-test"},
    })

    assert default_driver_factory(configured) is driver
    options = captured["options"]
    assert isinstance(options, FakeOptions)
    assert "--user-agent=TestBrowser/1.0" in options.arguments
    assert captured["driver_kwargs"]["options"] is options  # type: ignore[index]
    assert captured["service_kwargs"] == {}
    assert driver.timeout == configured.scraper_page_load_timeout_sec
    assert driver.commands == [
        ("Page.addScriptToEvaluateOnNewDocument", {"source": HIDE_WEBDRIVER_JS}),
        ("Network.enable", {}),
        ("Network.setExtraHTTPHeaders", {"headers": {"X-Client": "realstar-test"}}),
    ]


def test_default_driver_factory_removes_automation_markers(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver()
    captured = patch_selenium(monkeypatch, driver)

    default_driver_factory(settings)
    options = captured["options"]
    assert isinstance(options, FakeOptions)
    assert options.experimental["excludeSwitches"] == ["enable-automation"]
    assert options.experimental["useAutomationExtension"] is False
    assert "--disable-blink-features=AutomationControlled" in options.arguments
    assert not any(a.startswith("--headless") for a in options.arguments)  # 기본은 화면 표시
    assert not any(a.startswith("--user-data-dir") for a in options.arguments)
    assert not any(a.startswith("--user-agent") for a in options.arguments)  # 실제 Chrome UA 사용
    assert "webdriver" in HIDE_WEBDRIVER_JS
    assert all(c != "Network.setUserAgentOverride" for c, _ in driver.commands)
    # 기본 Accept-Language는 CDP 추가 헤더가 아니라 Chrome 언어 설정으로 들어간다
    assert options.experimental["prefs"] == {"intl.accept_languages": "ko-KR,ko"}
    assert driver.commands == [("Page.addScriptToEvaluateOnNewDocument", {"source": HIDE_WEBDRIVER_JS})]


def test_accept_language_goes_to_chrome_prefs_and_other_headers_to_cdp(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = FakeDriver()
    captured = patch_selenium(monkeypatch, driver)
    configured = settings.model_copy(update={
        "scraper_custom_headers": {"accept-language": "en-US,en;q=0.8", "X-Client": "realstar-test"},
    })

    default_driver_factory(configured)
    options = captured["options"]
    assert isinstance(options, FakeOptions)
    assert options.experimental["prefs"] == {"intl.accept_languages": "en-US,en"}
    assert driver.commands[-1] == ("Network.setExtraHTTPHeaders", {"headers": {"X-Client": "realstar-test"}})


def test_headless_mode_strips_headless_marker_from_user_agent(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    driver = FakeDriver(user_agent="Mozilla/5.0 HeadlessChrome/131.0.0.0 Safari/537.36")
    captured = patch_selenium(monkeypatch, driver)
    configured = settings.model_copy(update={"scraper_headless": True, "scraper_user_data_dir": tmp_path / "profile"})

    default_driver_factory(configured)
    options = captured["options"]
    assert isinstance(options, FakeOptions)
    assert "--headless=new" in options.arguments
    assert f"--user-data-dir={tmp_path / 'profile'}" in options.arguments
    overrides = [p for c, p in driver.commands if c == "Network.setUserAgentOverride"]
    assert overrides == [{
        "userAgent": "Mozilla/5.0 Chrome/131.0.0.0 Safari/537.36",
        "acceptLanguage": "ko-KR,ko;q=0.9",
    }]


def test_headless_mode_keeps_configured_user_agent(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver(user_agent="Mozilla/5.0 HeadlessChrome/131.0.0.0 Safari/537.36")
    patch_selenium(monkeypatch, driver)
    configured = settings.model_copy(update={"scraper_headless": True, "scraper_user_agent": "TestBrowser/1.0"})

    default_driver_factory(configured)
    names = [c for c, _ in driver.commands]
    assert "Browser.getVersion" not in names and "Network.setUserAgentOverride" not in names


def test_user_data_dir_loads_from_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SCRAPER_USER_DATA_DIR", str(tmp_path / "profile"))

    assert Settings(_env_file=None).scraper_user_data_dir == tmp_path / "profile"

    monkeypatch.setenv("SCRAPER_USER_DATA_DIR", "")
    assert Settings(_env_file=None).scraper_user_data_dir is None


def test_scraper_headers_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCRAPER_USER_AGENT", "TestBrowser/1.0")
    monkeypatch.setenv("SCRAPER_CUSTOM_HEADERS", '{"X-Client":"realstar-test"}')

    settings = Settings(_env_file=None)

    assert settings.scraper_user_agent == "TestBrowser/1.0"
    assert settings.scraper_custom_headers == {"X-Client": "realstar-test"}


def test_scraper_headers_have_browser_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.scraper_user_agent is None
    assert settings.scraper_user_data_dir is None
    assert settings.scraper_custom_headers == {"Accept-Language": "ko-KR,ko;q=0.9"}


def test_scraper_custom_headers_reject_user_agent() -> None:
    with pytest.raises(ValueError, match="SCRAPER_USER_AGENT"):
        Settings(_env_file=None, scraper_custom_headers={"User-Agent": "TestBrowser/1.0"})


def make(settings: Settings, site: FakeCoupangSite, *, mode: str = "interactive", sleeps: list[float] | None = None, **kw):  # type: ignore[no-untyped-def]
    data = dict(load_selectors().data)
    data["review_mode"] = mode
    sel = Selectors(data)
    state = LocalStateStore(settings.state_dir)
    sleeps = sleeps if sleeps is not None else []
    browser = BrowserSession(
        settings, sel, state, driver_factory=lambda _s: site, sleeper=sleeps.append, rng=random.Random(0),
        delay_range=(3.0, 7.0), **kw,
    )
    return CoupangScraperProvider(settings, state, selectors=sel, browser=browser)


def test_interactive_collection(settings: Settings) -> None:
    site = FakeCoupangSite(COUNTS, page_size=5)
    sleeps: list[float] = []
    p = make(settings, site, sleeps=sleeps)
    meta = p.get_product_meta("1000000001")
    assert meta.total_reviews == 23 and meta.star_counts == COUNTS
    progress = []
    r5 = p.get_reviews("1000000001", 5, limit=10, on_progress=progress.append)
    assert [r.review_id for r in r5] == [f"5-{i}" for i in range(10)]
    assert all("최신" in r.content for r in r5)  # 최신순 정렬 적용
    assert site.sorted_latest
    assert progress[-1].collected == 10
    r4 = p.get_reviews("1000000001", 4, limit=100)  # 100개 미만이면 전부
    assert len(r4) == 7
    assert p.get_reviews("1000000001", 3, limit=100) == []  # N_s = 0
    assert len(p.get_reviews("1000000001", 1, limit=100)) == 1
    # 첫 동작 이후 모든 조작 사이에 3~7초 무작위 대기
    real_waits = [w for w in sleeps if w > 0.31]
    assert real_waits and all(3.0 - 0.5 <= w <= 7.0 for w in real_waits)
    assert len(site.visited) == 1  # 상품 페이지 1회 로드 후 화면 조작만
    p.close()


def test_fragment_collection(settings: Settings) -> None:
    site = FakeCoupangSite(COUNTS, page_size=10)
    p = make(settings, site, mode="fragment")
    p.get_product_meta("1000000001")
    r5 = p.get_reviews("1000000001", 5, limit=100)
    assert len(r5) == 12
    assert any("/vp/product/reviews?" in u and "ratings=5" in u and "sortBy=DATE_DESC" in u for u in site.visited)


def test_block_detected_on_navigation(settings: Settings) -> None:
    site = FakeCoupangSite(COUNTS, block_after_visits=0)
    p = make(settings, site)
    with pytest.raises(BlockedError):
        p.get_product_meta("1000000001")


def test_empty_review_area_streak_blocks(settings: Settings) -> None:
    site = FakeCoupangSite({5: 50, 4: 50, 3: 50, 2: 50, 1: 50}, empty_reviews=True)
    p = make(settings, site, mode="fragment")
    p.get_product_meta("1")
    with pytest.raises(BlockedError) as e:
        for star in (5, 4, 3):
            p.get_reviews("1", star, 100)
    assert e.value.signal == "empty_streak"


def test_page_budget_per_analysis(settings: Settings) -> None:
    site = FakeCoupangSite({5: 500, 4: 0, 3: 0, 2: 0, 1: 0}, page_size=10)
    p = make(settings, site, mode="fragment", max_pages=4)
    p.get_product_meta("1")
    with pytest.raises(PageBudgetExceededError) as e:
        p.get_reviews("1", 5, 100)
    assert e.value.scope == "analysis"


def test_daily_budget(settings: Settings) -> None:
    site = FakeCoupangSite(COUNTS)
    p = make(settings, site, max_pages_per_day=1)
    p.get_product_meta("1")
    with pytest.raises(PageBudgetExceededError) as e:
        p.search("청소기")
    assert e.value.scope == "daily"


def test_forbidden_urls_not_opened(settings: Settings) -> None:
    site = FakeCoupangSite(COUNTS)
    p = make(settings, site)
    for url in ("https://cart.coupang.com/cartView.pang", "https://login.coupang.com/login/login.pang", "https://www.coupang.com/np/my"):
        with pytest.raises(ForbiddenAreaError):
            p.browser.get(url)
    assert site.visited == []


def test_short_link_redirect_to_login_stops(settings: Settings) -> None:
    site = FakeCoupangSite(COUNTS, redirect={"https://link.coupang.com/a/x": "https://login.coupang.com/login"})
    p = make(settings, site)
    with pytest.raises(ForbiddenAreaError):
        p.resolve_short_url("https://link.coupang.com/a/x")


def test_short_link_resolves(settings: Settings) -> None:
    site = FakeCoupangSite(COUNTS, redirect={"https://link.coupang.com/a/x": "https://www.coupang.com/vp/products/77?itemId=1"})
    p = make(settings, site)
    assert p.resolve_short_url("https://link.coupang.com/a/x").endswith("/vp/products/77?itemId=1")


def test_search_uses_first_page_only(settings: Settings) -> None:
    site = FakeCoupangSite(COUNTS)
    p = make(settings, site)
    res = p.search("무선 청소기")
    assert res[0].product_id == "1"
    assert len(site.visited) == 1 and "q=%EB%AC%B4%EC%84%A0+%EC%B2%AD%EC%86%8C%EA%B8%B0" in site.visited[0]
