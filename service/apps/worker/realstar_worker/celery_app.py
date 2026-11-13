"""Celery 앱 설정 (README 4장, 6장).

실행 예:
  celery -A realstar_worker.celery_app worker -Q scrape -c 1 --prefetch-multiplier 1 -n scrape@%h
  celery -A realstar_worker.celery_app worker -Q detect -c 2 -n detect@%h
"""

from __future__ import annotations

import ssl

from celery import Celery

from realstar.config import get_settings

settings = get_settings()
broker = settings.redis_url or "redis://localhost:6379/0"

app = Celery("realstar", broker=broker, backend=broker, include=["realstar_worker.tasks"])
app.conf.update(
    task_routes={
        "realstar.collect": {"queue": "scrape"},
        "realstar.browser_resolve": {"queue": "scrape"},
        "realstar.detect_aggregate": {"queue": "detect"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    timezone="Asia/Seoul",
    broker_connection_retry_on_startup=True,
    # 수집 작업은 차단 시 즉시 중단해야 하므로 Celery 자동 재시도를 쓰지 않는다
    task_default_retry_delay=0,
)
if broker.startswith("rediss://"):
    # Heroku Key-Value Store: TLS + 자체 서명 인증서
    app.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
    app.conf.redis_backend_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
