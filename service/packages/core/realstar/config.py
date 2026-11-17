"""환경 변수 설정 (README 8장). 비밀값은 코드에 두지 않고 .env로 받는다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[3]  # .../service
REPO_ROOT = SERVICE_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── 수집 ───────────────────────────────────────────────
    # 라이브 쿠팡 스크래퍼는 제거됨. 현재는 저장된 JSON으로 동작하는 fixture만 지원한다.
    review_provider: Literal["fixture"] = "fixture"
    fixture_dir: Path = SERVICE_ROOT / "tests" / "fixtures" / "json"
    sample_per_star: int = 100  # 별점당 분석에 쓰는 최대 리뷰 수
    review_sort: Literal["latest", "best"] = "latest"
    # 수집이 불가(blocked) 상태가 되면 이 시간(분) 동안 새 수집을 쉬게 한다.
    block_cooldown_min: int = 60

    # ── 비전 ──────────────────────────────────────────────
    ocr_engine: Literal["paddleocr", "easyocr", "none"] = "paddleocr"
    vlm_enabled: bool = False  # TBD-5: 기본값 사용 (OCR만)
    vlm_model_path: str = ""
    image_max_bytes: int = 10 * 1024 * 1024
    image_max_side: int = 2000

    # ── 인프라 ────────────────────────────────────────────
    database_url: str = f"sqlite:///{SERVICE_ROOT / 'var' / 'realstar.db'}"
    redis_url: str = ""  # 비우면 로컬 상태 저장소(파일)와 inline 작업 실행을 쓴다
    detector_url: str = "http://localhost:8001"
    task_backend: Literal["celery", "inline"] = "inline"
    state_dir: Path = SERVICE_ROOT / "var" / "state"
    cors_origins: str = "http://localhost:3000"
    # 상품명·단축 링크 해석이 수집 큐를 기다리는 최대 시간. Heroku는 요청 30초 제한이 있어 25로 둔다.
    resolve_timeout_sec: int = 90

    # ── 탐지 / 집계 ───────────────────────────────────────
    # detector_mode: http(detector_server 호출) | inprocess(realstar_model 직접 로드) | dummy(개발 전용)
    detector_mode: Literal["http", "inprocess", "dummy"] = "http"
    model_artifact_path: Path = REPO_ROOT / "model" / "artifacts" / "det-ko-review-v1.0"
    # 아티팩트 폴더가 없을 때 받아 올 tar.gz 주소(Heroku처럼 볼륨이 없는 배포용). 비우면 받지 않는다.
    model_artifact_url: str = ""
    detector_batch_size: int = 64
    detector_timeout_sec: int = 120
    min_chars: int = 20
    top_min_chars: int = 40
    top_k: int = 5
    min_judged_per_star: int = 30
    displayed_avg_warn_gap: float = 0.05
    bootstrap_iterations: int = 1000
    bootstrap_seed: int = 20261113
    cache_ttl_hours: int = 24

    # ── 상품 식별 (TBD-4: 기본값 사용) ─────────────────────
    resolve_auto_top1: float = 0.85
    resolve_auto_gap: float = 0.15
    resolve_max_candidates: int = 5

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        """Heroku Postgres는 postgres:// 형식을 준다 → SQLAlchemy + psycopg3 형식으로 바꾼다."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def redis_ssl_kwargs(self) -> dict[str, object]:
        """Heroku Key-Value Store는 rediss:// + 자체 서명 인증서를 쓴다(문서 권장: ssl_cert_reqs=None)."""
        return {"ssl_cert_reqs": None} if self.redis_url.startswith("rediss://") else {}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
