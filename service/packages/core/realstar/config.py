"""환경 변수 설정 (README 8장). 비밀값은 코드에 두지 않고 .env로 받는다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[3]  # .../service
REPO_ROOT = SERVICE_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── 스크래퍼 (README 0-3, 8장) ─────────────────────────────
    scraper_headless: bool = False  # TBD-10: 기본값 사용 (화면 표시)
    scraper_delay_min_sec: float = 3.0
    scraper_delay_max_sec: float = 7.0
    scraper_page_load_timeout_sec: int = 20
    scraper_max_pages_per_analysis: int = 80
    scraper_max_pages_per_day: int = 1500
    scraper_block_cooldown_min: int = 60
    scraper_parser_fail_threshold: float = 0.2
    scraper_empty_streak_limit: int = 3
    scraper_debug_html_dir: Path = SERVICE_ROOT / "var" / "scrape_html"
    scraper_debug_html_keep: int = 20
    scraper_chrome_binary: str | None = None  # 비워 두면 Selenium Manager가 찾는다
    scraper_chromedriver_path: str | None = None
    sample_per_star: int = 100
    review_sort: Literal["latest", "best"] = "latest"

    # 학습용 배치 수집 (README 5.6: 서비스 수집보다 더 느리게, 일일 상한 별도)
    training_delay_min_sec: float = 8.0
    training_delay_max_sec: float = 15.0
    training_max_pages_per_day: int = 300
    training_export_dir: Path = REPO_ROOT / "model" / "data" / "raw" / "coupang"
    training_cutoff_date: str = "2022-11-30"
    training_per_star_limit: int = 30

    # 수집 구현체: coupang(운영) | fixture(개발·테스트)
    review_provider: Literal["coupang", "fixture"] = "coupang"
    fixture_dir: Path = SERVICE_ROOT / "tests" / "fixtures" / "json"

    # 작성자 식별 정보는 해시만 저장한다. 솔트는 비밀값.
    author_hash_salt: str = Field(default="", repr=False)

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
    resolve_timeout_sec: int = 90

    # ── 탐지 / 집계 ───────────────────────────────────────
    # detector_mode: http(detector_server 호출) | inprocess(realstar_model 직접 로드) | dummy(개발 전용)
    detector_mode: Literal["http", "inprocess", "dummy"] = "http"
    model_artifact_path: Path = REPO_ROOT / "model" / "artifacts" / "det-ko-review-v1.0"
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
