"""PostgreSQL 스키마 (README 5.9). 개발·테스트에서는 SQLite로도 동작한다.

README 5.9 대비 추가 컬럼(docs/decisions.md D-S05):
- products.reviews_fetched_at, products.sampling: 리뷰 표본 캐시의 유효성 판단
- reviews.option_name, reviews.raw_html_ref: RawReview 필드 보존
- analyses.cached, analyses.force_refresh, analyses.input: 캐시 결과 여부, 요청 정보
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    displayed_avg: Mapped[float | None] = mapped_column(Float)
    total_reviews: Mapped[int | None] = mapped_column(Integer)
    star_counts: Mapped[dict[str, int] | None] = mapped_column(JsonType)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviews_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sampling: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class Review(Base):
    __tablename__ = "reviews"
    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), index=True)
    star: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    clean_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(String(10))
    has_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    option_name: Mapped[str | None] = mapped_column(Text)
    is_sponsored: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cash_event: Mapped[bool] = mapped_column(Boolean, default=False)
    dup_group_id: Mapped[str | None] = mapped_column(String(64))
    len_chars: Mapped[int | None] = mapped_column(Integer)
    author_hash: Mapped[str | None] = mapped_column(String(80))  # 닉네임 원문은 저장하지 않는다
    raw_html_ref: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Prediction(Base):
    __tablename__ = "predictions"
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.review_id"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    p_ai: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(16))
    features: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Analysis(Base):
    __tablename__ = "analyses"
    analysis_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    progress: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    model_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    force_refresh: Mapped[bool] = mapped_column(Boolean, default=False)
    input: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class ScrapeLog(Base):
    __tablename__ = "scrape_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    product_id: Mapped[str | None] = mapped_column(String(32), index=True)
    pages_loaded: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(16))  # ok / blocked / parser_broken / error
    detail: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class SearchCacheRow(Base):
    __tablename__ = "search_cache"
    query_norm: Mapped[str] = mapped_column(Text, primary_key=True)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JsonType)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
