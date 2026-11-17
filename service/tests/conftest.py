from __future__ import annotations

import json
from pathlib import Path

import pytest

from realstar.config import Settings
from realstar.db.session import init_db
from realstar.detection.backends import DummyDetectorBackend

FIXTURES = Path(__file__).parent / "fixtures"
HTML = FIXTURES / "html"
JSON_DIR = FIXTURES / "json"


def read_html(name: str) -> str:
    return (HTML / name).read_text(encoding="utf-8")


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        state_dir=tmp_path / "state",
        review_provider="fixture",
        fixture_dir=JSON_DIR,
        detector_mode="dummy",
        task_backend="inline",
        redis_url="",
        bootstrap_iterations=1000,
        ocr_engine="none",
    )
    init_db(s.database_url)
    return s


@pytest.fixture()
def fixed_example_detector() -> DummyDetectorBackend:
    """README 5.4 고정 예제 라벨(h = {5:50, 4:30, 3:80, 2:70, 1:60})을 그대로 돌려주는 판별기."""
    labels = json.loads((JSON_DIR / "labels_1000000001.json").read_text())
    return DummyDetectorBackend(overrides=labels)
