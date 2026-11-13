"""DB 엔진·세션."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from realstar.db.models import Base


@lru_cache(maxsize=8)
def get_engine(database_url: str) -> Engine:
    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        path = database_url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        kwargs = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    engine = create_engine(database_url, **kwargs)  # type: ignore[arg-type]
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(conn, _):  # type: ignore[no-untyped-def]
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def init_db(database_url: str) -> None:
    """개발·테스트용 테이블 생성. 운영(PostgreSQL)은 Alembic 마이그레이션을 쓴다."""
    Base.metadata.create_all(get_engine(database_url))


@lru_cache(maxsize=8)
def get_sessionmaker(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False)


@contextmanager
def session_scope(database_url: str) -> Iterator[Session]:
    s = get_sessionmaker(database_url)()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
