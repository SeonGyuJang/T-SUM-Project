"""API 프로세스에서 Celery로 작업을 보내는 디스패처."""

from __future__ import annotations

from typing import Any

from celery.exceptions import TimeoutError as CeleryTimeout

from realstar.config import Settings
from realstar.errors import ScraperBusyError


class CeleryDispatcher:
    def __init__(self, settings: Settings) -> None:
        from realstar_worker import tasks

        self.tasks = tasks
        self.settings = settings

    def enqueue_analysis(self, analysis_id: str) -> None:
        self.tasks.collect.delay(analysis_id)

    def browser_resolve(self, kind: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        res = self.tasks.browser_resolve.delay(kind, payload)
        try:
            return dict(res.get(timeout=timeout))
        except CeleryTimeout as e:
            res.revoke()
            raise ScraperBusyError("scrape queue busy") from e
