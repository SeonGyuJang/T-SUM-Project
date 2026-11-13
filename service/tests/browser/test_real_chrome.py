"""실제 Chrome + Selenium으로 수집기 전체 흐름을 로컬 모의 사이트에서 검증한다(쿠팡 접속 없음).

Chrome이 없으면 건너뛴다. 실행: pytest -m browser
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from realstar.collectors.coupang.provider import CoupangScraperProvider
from realstar.collectors.coupang.selectors import Selectors, load_selectors
from realstar.config import Settings
from realstar.errors import BlockedError
from realstar.state.store import LocalStateStore
from tests.browser import mock_site

pytestmark = pytest.mark.browser
CHROME = os.environ.get("SCRAPER_CHROME_BINARY") or shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
if not CHROME:
    pytest.skip("Chrome 없음", allow_module_level=True)


@pytest.fixture(scope="module")
def site():  # type: ignore[no-untyped-def]
    srv, base = mock_site.start()
    yield base
    srv.shutdown()


def provider_for(base: str, settings: Settings, tmp_path: Path) -> CoupangScraperProvider:
    data = dict(load_selectors().data)
    urls = dict(data["urls"])
    urls.update(base=base, product=base + "/vp/products/{product_id}", search=base + "/np/search?q={query}",
                allowed_patterns=[r"^http://127\.0\.0\.1:\d+/"])
    data["urls"] = urls
    s = settings.model_copy(update={"scraper_headless": True, "scraper_chrome_binary": CHROME, "scraper_chrome_container": True,
                                    "scraper_delay_min_sec": 0.2, "scraper_delay_max_sec": 0.4, "scraper_page_load_timeout_sec": 15})
    return CoupangScraperProvider(s, LocalStateStore(tmp_path / "st"), selectors=Selectors(data), snapshot_dir=tmp_path / "snap")


def test_collect_with_real_chrome(site: str, settings: Settings, tmp_path: Path) -> None:
    p = provider_for(site, settings, tmp_path)
    try:
        meta = p.get_product_meta("77")
        assert meta.name == "[모의] 테스트 상품" and meta.total_reviews == 45
        assert meta.star_counts == mock_site.COUNTS and meta.displayed_avg == 4.3
        r5 = p.get_reviews("77", 5, limit=12)  # 페이지 3장을 넘겨야 한다
        assert len(r5) == 12 and len({r.review_id for r in r5}) == 12
        assert all(r.star == 5 and "최신순" in r.content for r in r5)  # 최신순 정렬 클릭 반영
        assert r5[0].review_id == "5000"
        r1 = p.get_reviews("77", 1, limit=100)  # 6개뿐 → 전부
        assert len(r1) == 6 and all(r.star == 1 for r in r1)
        assert p.get_reviews("77", 3, limit=100) == []
        assert all(r.author_hash and "구매자" not in r.author_hash for r in r5)
        snaps = list((tmp_path / "snap").glob("*.html"))
        assert snaps and all("구매자" not in f.read_text(encoding="utf-8") for f in snaps)  # 닉네임 가림
        cands = p.search("텀블러")
        assert cands[0].product_id == "77" and cands[0].price == 12900
    finally:
        p.close()


def test_block_page_with_real_chrome(site: str, settings: Settings, tmp_path: Path) -> None:
    p = provider_for(site, settings, tmp_path)
    try:
        with pytest.raises(BlockedError):
            p.browser.get(site + "/blocked")
    finally:
        p.close()
