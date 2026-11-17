"""수집 인터페이스와 데이터 스키마 (README 5.2)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

SortOrder = Literal["latest", "best"]
STARS = (5, 4, 3, 2, 1)


class ProductMeta(BaseModel):
    product_id: str
    item_id: str | None = None
    vendor_item_id: str | None = None
    name: str
    image_url: str | None = None
    url: str | None = None
    category: str | None = None
    displayed_avg: float | None = None
    total_reviews: int
    star_counts: dict[int, int] | None = None
    star_ratio: dict[int, float] | None = None

    def resolved_star_counts(self) -> dict[int, int]:
        """별점별 전체 개수 N_s. 비율만 있으면 round(total × ratio)로 계산한다(README 5.2)."""
        if self.star_counts:
            return {s: int(self.star_counts.get(s, 0)) for s in STARS}
        if self.star_ratio:
            return {s: int(round(self.total_reviews * float(self.star_ratio.get(s, 0.0)))) for s in STARS}
        raise ValueError("star_counts와 star_ratio가 모두 없습니다")


class RawReview(BaseModel):
    review_id: str
    product_id: str
    star: int = Field(ge=1, le=5)
    title: str | None = None
    content: str
    created_at: str | None = None  # YYYY-MM-DD
    has_photo: bool = False
    helpful_count: int = 0
    option_name: str | None = None
    author_hash: str | None = None
    raw_html_ref: str | None = None


class SearchCandidate(BaseModel):
    product_id: str
    item_id: str | None = None
    vendor_item_id: str | None = None
    name: str | None = None
    price: int | None = None
    image_url: str | None = None
    url: str | None = None
    is_ad: bool = False
    rating: float | None = None
    review_count: int | None = None
    match_score: float | None = None


class CollectProgress(BaseModel):
    star: int
    collected: int
    target: int
    pages_loaded: int


ProgressCallback = Callable[[CollectProgress], None]


@runtime_checkable
class ReviewProvider(Protocol):
    """리뷰 수집 구현체 인터페이스. 저장된 JSON으로 동작하는 FixtureProvider."""

    def get_product_meta(self, product_id: str) -> ProductMeta: ...

    def get_reviews(
        self,
        product_id: str,
        star: int,
        limit: int,
        sort: SortOrder = "latest",
        on_progress: ProgressCallback | None = None,
    ) -> list[RawReview]: ...

    def search(self, query: str) -> list[SearchCandidate]: ...

    def resolve_short_url(self, url: str) -> str: ...

    @property
    def pages_loaded(self) -> int: ...

    def close(self) -> None: ...
