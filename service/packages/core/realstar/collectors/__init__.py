"""리뷰 수집기.

라이브 쿠팡 스크래퍼는 제거됨. 현재는 저장된 JSON으로 동작하는 FixtureProvider만 제공한다
(개발·테스트·발표 모드용). 다른 경로로 수집한 리뷰는 FixtureProvider 형식의 JSON으로 넣어 쓴다.
"""

from __future__ import annotations

from realstar.collectors.base import ProductMeta, RawReview, ReviewProvider, SearchCandidate
from realstar.config import Settings
from realstar.state.store import StateStore


def make_provider(settings: Settings, state: StateStore, *, training: bool = False) -> ReviewProvider:
    if settings.review_provider == "fixture":
        from realstar.collectors.fixture_provider import FixtureProvider

        return FixtureProvider(settings.fixture_dir)
    raise RuntimeError(
        f"review_provider={settings.review_provider!r}는 더 이상 지원하지 않습니다. "
        "라이브 쿠팡 스크래퍼는 제거되었어요. REVIEW_PROVIDER=fixture 를 쓰거나 "
        "저장된 리뷰 JSON을 FixtureProvider 형식으로 넣어 주세요."
    )


__all__ = ["ProductMeta", "RawReview", "ReviewProvider", "SearchCandidate", "make_provider"]
