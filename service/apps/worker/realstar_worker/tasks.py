"""Celery 작업. 실제 로직은 realstar.pipeline에 있다."""

from __future__ import annotations

from typing import Any

from realstar.config import get_settings
from realstar.pipeline.analysis import AnalysisPipeline
from realstar.pipeline.service import run_browser_resolve
from realstar_worker.celery_app import app

_pipeline: AnalysisPipeline | None = None


def pipeline() -> AnalysisPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = AnalysisPipeline(get_settings())
    return _pipeline


@app.task(name="realstar.collect", acks_late=True, max_retries=0)
def collect(analysis_id: str) -> None:
    """수집(fixture) 후 탐지·집계로 넘긴다."""
    if pipeline().collect(analysis_id):
        detect_aggregate.delay(analysis_id)


@app.task(name="realstar.detect_aggregate", acks_late=True, max_retries=0)
def detect_aggregate(analysis_id: str) -> None:
    pipeline().detect_and_aggregate(analysis_id)


@app.task(name="realstar.browser_resolve", max_retries=0)
def browser_resolve(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return run_browser_resolve(get_settings(), kind, payload)
