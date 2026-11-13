"""리뷰 수집기. `make_provider`로 설정에 맞는 구현체를 만든다."""

from __future__ import annotations

from realstar.collectors.base import ProductMeta, RawReview, ReviewProvider, SearchCandidate
from realstar.config import Settings
from realstar.state.store import StateStore


def make_provider(settings: Settings, state: StateStore, *, training: bool = False) -> ReviewProvider:
    if settings.review_provider == "fixture":
        from realstar.collectors.fixture_provider import FixtureProvider

        return FixtureProvider(settings.fixture_dir)
    from realstar.collectors.coupang.provider import CoupangScraperProvider

    return CoupangScraperProvider(settings, state, training=training)  # type: ignore[return-value]


__all__ = ["ProductMeta", "RawReview", "ReviewProvider", "SearchCandidate", "make_provider"]
