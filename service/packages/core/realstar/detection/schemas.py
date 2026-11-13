"""탐지 입력·출력 스키마 (README 5.6 출력 스키마, MODEL_DEV.md 4.12.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DetectLabel = Literal["human", "ai", "uncertain"]


class DetectInput(BaseModel):
    review_id: str
    title: str | None = None
    content: str
    star: int | None = None
    category: str | None = None


class DetectOutput(BaseModel):
    review_id: str
    p_ai: float = Field(ge=0.0, le=1.0)
    p_human: float = Field(ge=0.0, le=1.0)
    label: DetectLabel
    len_bucket: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    reason_tags: list[str] = Field(default_factory=list)
    model_version: str


class ModelInfo(BaseModel):
    ready: bool
    backend: str
    model_version: str | None = None
    thresholds: dict[str, Any] | None = None  # 길이 구간별 {S: {T_AI, T_HUMAN}, ...} 또는 단일 값
    min_chars: int | None = None
    sensitivity: float | None = None  # (Phase 8) Rogan–Gladen 보정용, manifest에 있으면 사용
    specificity: float | None = None
    is_dummy: bool = False
    error: str | None = None


class PredictRequest(BaseModel):
    reviews: list[DetectInput]
    batch_size: int = 64


class PredictResponse(BaseModel):
    predictions: list[DetectOutput]
    model: ModelInfo
