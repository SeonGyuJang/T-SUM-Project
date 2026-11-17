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
    # crawler: 요청이 들어오면 저장소 루트의 수집기(coupang_reviews.py)를 실행한다(기본).
    # fixture: 저장된 JSON(tests/fixtures/json)만 쓴다(개발·테스트).
    review_provider: Literal["crawler", "fixture"] = "crawler"
    fixture_dir: Path = SERVICE_ROOT / "tests" / "fixtures" / "json"
    sample_per_star: int = 100  # 별점당 분석에 쓰는 최대 리뷰 수 (수집기 --per-rating)

    # ── 수집기 실행 (review_provider=crawler) ───────────────────
    crawler_script: Path = REPO_ROOT / "coupang_reviews.py"
    # 수집기를 실행할 파이썬. 비우면 서비스와 같은 파이썬(scrapling이 설치돼 있어야 함).
    crawler_python: str = ""
    # 수집 결과 폴더. 수집기를 직접 실행할 때와 같은 output/ 을 쓰므로, CLI로 모은 상품도 홈페이지에 나온다.
    crawler_output_dir: Path = REPO_ROOT / "output"
    crawler_headless: bool = False  # 수집기 안내: 창을 숨기면 차단이 늘 수 있음
    crawler_timeout_min: int = 40  # 상품 하나 수집 최대 시간
    crawler_search_timeout_sec: int = 80  # 상품명 검색·단축 링크 해석 최대 시간
    crawler_search_limit: int = 20
    # 이미 수집을 마친 파일이 이 시간 안이면 다시 수집하지 않는다(0이면 항상 재사용). '다시 수집'은 무시하고 새로 모은다.
    crawler_reuse_hours: int = 24
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
    resolve_timeout_sec: int = 120

    # ── 탐지 / 집계 ───────────────────────────────────────
    # detector_mode: http(detector_server 호출) | inprocess(realstar_model 직접 로드) | dummy(개발 전용)
    #                | none(AI 모델 미연결: 판별을 건너뛰고 수집·별점 분포·리뷰만 보여 준다)
    detector_mode: Literal["http", "inprocess", "dummy", "none"] = "none"
    # 모델이 준비되지 않았을 때 분석을 실패로 끝내지 않고 'AI 판별 제외' 결과를 만든다.
    detection_fallback: bool = True
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
