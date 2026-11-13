"""프로세스 간 공유 상태: 차단 쿨다운, 일일 페이지 카운터, 전역 스크래핑 락.

- 운영: Redis(분산 락, README 4장)
- 개발·CLI: 로컬 파일 + fcntl 락 (Redis 없이 동작)
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from realstar.config import Settings
from realstar.errors import CooldownActiveError, ScraperBusyError

KST = ZoneInfo("Asia/Seoul")
COOLDOWN_KEY = "realstar:scrape:cooldown"
SCRAPE_LOCK_KEY = "realstar:scrape:lock"


def daily_pages_key(prefix: str = "service") -> str:
    return f"realstar:scrape:pages:{prefix}:{datetime.now(KST):%Y%m%d}"


class StateStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_sec: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def incr(self, key: str, amount: int = 1, ttl_sec: int | None = None) -> int: ...
    def ttl(self, key: str) -> int | None: ...
    def lock(self, key: str, timeout_sec: float, lease_sec: int = 3600) -> contextlib.AbstractContextManager[None]: ...


class LocalStateStore:
    """JSON 파일 하나에 키·값·만료 시각을 저장한다. 같은 머신의 프로세스 간 공유된다."""

    def __init__(self, state_dir: Path) -> None:
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "state.json"
        self._guard = self.dir / "state.lock"
        self._thread_lock = threading.RLock()

    @contextlib.contextmanager
    def _locked(self) -> Iterator[dict[str, dict[str, float | str | None]]]:
        with self._thread_lock, self._guard.open("a+") as g:
            fcntl.flock(g, fcntl.LOCK_EX)
            try:
                data = json.loads(self.path.read_text()) if self.path.exists() else {}
            except json.JSONDecodeError:
                data = {}
            now = time.time()
            data = {k: v for k, v in data.items() if v.get("exp") is None or float(v["exp"]) > now}  # type: ignore[arg-type]
            yield data
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(self.path)
            fcntl.flock(g, fcntl.LOCK_UN)

    def get(self, key: str) -> str | None:
        with self._locked() as data:
            item = data.get(key)
            return None if item is None else str(item["v"])

    def set(self, key: str, value: str, ttl_sec: int | None = None) -> None:
        with self._locked() as data:
            data[key] = {"v": value, "exp": time.time() + ttl_sec if ttl_sec else None}

    def delete(self, key: str) -> None:
        with self._locked() as data:
            data.pop(key, None)

    def incr(self, key: str, amount: int = 1, ttl_sec: int | None = None) -> int:
        with self._locked() as data:
            item = data.get(key)
            value = int(item["v"]) + amount if item else amount  # type: ignore[arg-type]
            exp = item.get("exp") if item else (time.time() + ttl_sec if ttl_sec else None)
            data[key] = {"v": str(value), "exp": exp}
            return value

    def ttl(self, key: str) -> int | None:
        with self._locked() as data:
            item = data.get(key)
            if not item or item.get("exp") is None:
                return None
            return max(0, int(float(item["exp"]) - time.time()))  # type: ignore[arg-type]

    @contextlib.contextmanager
    def lock(self, key: str, timeout_sec: float, lease_sec: int = 3600) -> Iterator[None]:
        token = uuid.uuid4().hex
        deadline = time.time() + timeout_sec
        while True:
            with self._locked() as data:
                if key not in data:
                    data[key] = {"v": token, "exp": time.time() + lease_sec}
                    break
            if time.time() >= deadline:
                raise ScraperBusyError(f"lock {key} busy")
            time.sleep(0.2)
        try:
            yield
        finally:
            with self._locked() as data:
                if data.get(key, {}).get("v") == token:
                    data.pop(key, None)


class RedisStateStore:
    def __init__(self, redis_url: str) -> None:
        import redis

        self.r = redis.Redis.from_url(redis_url, decode_responses=True)

    def get(self, key: str) -> str | None:
        v = self.r.get(key)
        return None if v is None else str(v)

    def set(self, key: str, value: str, ttl_sec: int | None = None) -> None:
        self.r.set(key, value, ex=ttl_sec)

    def delete(self, key: str) -> None:
        self.r.delete(key)

    def incr(self, key: str, amount: int = 1, ttl_sec: int | None = None) -> int:
        pipe = self.r.pipeline()
        pipe.incrby(key, amount)
        if ttl_sec:
            pipe.expire(key, ttl_sec, nx=True)
        return int(pipe.execute()[0])

    def ttl(self, key: str) -> int | None:
        t = int(self.r.ttl(key))
        return t if t >= 0 else None

    @contextlib.contextmanager
    def lock(self, key: str, timeout_sec: float, lease_sec: int = 3600) -> Iterator[None]:
        lk = self.r.lock(key, timeout=lease_sec, blocking_timeout=timeout_sec)
        if not lk.acquire():
            raise ScraperBusyError(f"lock {key} busy")
        try:
            yield
        finally:
            with contextlib.suppress(Exception):
                lk.release()


_stores: dict[str, StateStore] = {}


def get_state_store(settings: Settings) -> StateStore:
    key = settings.redis_url or str(settings.state_dir)
    if key not in _stores:
        _stores[key] = RedisStateStore(settings.redis_url) if settings.redis_url else LocalStateStore(settings.state_dir)
    return _stores[key]


class Cooldown:
    """차단 감지 후 쿨다운(기본 60분) 동안 새 수집을 하지 않는다."""

    def __init__(self, store: StateStore, minutes: int) -> None:
        self.store = store
        self.minutes = minutes

    def start(self, reason: str) -> datetime:
        until = datetime.now(UTC) + timedelta(minutes=self.minutes)
        self.store.set(COOLDOWN_KEY, json.dumps({"until": until.isoformat(), "reason": reason}), self.minutes * 60)
        return until

    def status(self) -> dict[str, str] | None:
        raw = self.store.get(COOLDOWN_KEY)
        return json.loads(raw) if raw else None

    def ensure_inactive(self) -> None:
        st = self.status()
        if st:
            raise CooldownActiveError(st["until"])

    def clear(self) -> None:
        self.store.delete(COOLDOWN_KEY)
