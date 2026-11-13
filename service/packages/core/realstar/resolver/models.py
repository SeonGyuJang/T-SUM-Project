"""상품 식별 공통 출력 (README 5.1)."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from realstar.collectors.base import SearchCandidate

ResolveStatus = Literal["resolved", "needs_selection", "not_found", "blocked"]


class ResolveResult(BaseModel):
    status: ResolveStatus
    candidates: list[SearchCandidate] = Field(default_factory=list)
    input_type: Literal["url", "query", "image"]
    query: str | None = None
    extracted: dict[str, Any] | None = None  # 이미지 판독 결과(원본 이미지는 저장하지 않는다)
    message: str | None = None
    cached: bool = False


class SearchCache(Protocol):
    def get(self, query_norm: str, ttl_hours: int) -> list[SearchCandidate] | None: ...
    def put(self, query_norm: str, candidates: list[SearchCandidate]) -> None: ...


class MemorySearchCache:
    def __init__(self) -> None:
        self._d: dict[str, list[SearchCandidate]] = {}

    def get(self, query_norm: str, ttl_hours: int) -> list[SearchCandidate] | None:
        return self._d.get(query_norm)

    def put(self, query_norm: str, candidates: list[SearchCandidate]) -> None:
        self._d[query_norm] = candidates
