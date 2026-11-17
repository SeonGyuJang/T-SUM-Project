"""분석 결과 스키마 (README 5.7). API 응답·웹 zod 스키마와 같은 구조를 유지한다."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

StarKey = Literal["5", "4", "3", "2", "1"]


class ProductOut(BaseModel):
    product_id: str
    name: str | None = None
    image_url: str | None = None
    url: str | None = None


class PlatformStats(BaseModel):
    displayed_avg: float | None = None
    total_reviews: int
    star_counts: dict[str, int]


class Sampling(BaseModel):
    per_star_limit: int
    sort: str
    collected_at: str | None = None
    pages_loaded: int = 0
    selectors_version: str | None = None
    from_cache: bool = False


class PerStar(BaseModel):
    total: int  # N_s
    collected: int
    human: int
    ai: int
    uncertain: int
    human_ratio: float | None
    ratio_substituted: bool = False


class Ratings(BaseModel):
    avg_all: float | None
    avg_human: float | None
    diff: float | None
    avg_human_ci95: list[float] | None = None
    diff_ci95: list[float] | None = None
    ai_share: float | None
    ai_share_ci95: list[float] | None = None
    corrected: dict[str, Any] | None = None


class TopReview(BaseModel):
    review_id: str
    title: str | None = None
    text: str
    p_human: float
    created_at: str | None = None
    has_photo: bool = False
    len_chars: int
    reason_tags: list[str] = Field(default_factory=list)


class Flags(BaseModel):
    sponsored_count: int = 0
    cash_event_count: int = 0
    near_duplicate_groups: int = 0


class WarningOut(BaseModel):
    code: str
    level: str = "warning"
    message: str
    star: int | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    version: str
    T_AI: float | None = None
    T_HUMAN: float | None = None
    thresholds: dict[str, Any] | None = None
    is_dummy: bool = False


class DetectionOut(BaseModel):
    available: bool = True
    message: str | None = None


class AnalysisResult(BaseModel):
    analysis_id: str
    product: ProductOut
    platform_stats: PlatformStats
    sampling: Sampling
    per_star: dict[str, PerStar]
    ratings: Ratings
    top_human_reviews: dict[str, list[TopReview]]
    flags: Flags
    warnings: list[WarningOut]
    model: ModelOut
    assumptions: list[str] = Field(default_factory=list)
    # AI 판별을 했는지(모델 미연결이면 available=false). 이전 결과와의 호환을 위해 기본값이 있다.
    detection: DetectionOut = Field(default_factory=DetectionOut)
    # 별점별 수집 표본 통계(평균 글자 수, 사진 리뷰 수 등)
    review_stats: dict[str, dict[str, Any]] | None = None
