"""리뷰 수집기.

- CrawlerProvider(기본): 요청이 들어오면 저장소 루트의 coupang_reviews.py를 실행해 수집한다.
- FixtureProvider: 저장된 JSON으로 동작한다(개발·테스트·발표 모드용).
"""

from __future__ import annotations

from realstar.collectors.base import ProductMeta, RawReview, ReviewProvider, SearchCandidate
from realstar.config import Settings
from realstar.state.store import StateStore


def make_provider(settings: Settings, state: StateStore, *, training: bool = False) -> ReviewProvider:
    if settings.review_provider == "crawler":
        from realstar.collectors.crawler_provider import CrawlerProvider

        return CrawlerProvider(settings)
    if settings.review_provider == "fixture":
        from realstar.collectors.fixture_provider import FixtureProvider

        return FixtureProvider(settings.fixture_dir)
    raise RuntimeError(f"review_provider={settings.review_provider!r}는 지원하지 않습니다 (crawler | fixture).")


__all__ = ["ProductMeta", "RawReview", "ReviewProvider", "SearchCandidate", "make_provider"]
