"""학습 결과 → 아티팩트 폴더 (MODEL_DEV.md 4.12.3). service는 manifest.json을 읽어 Detector로 연다."""

from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from realstar_model import __version__
from realstar_model.paths import ARTIFACTS, REPORTS
from realstar_model.preprocess import MIN_CHARS, patterns_version

KST = timezone(timedelta(hours=9))


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def write_manifest(art_dir: Path, *, model_version: str, model_type: str, data_version: str, thresholds: dict[str, Any],
                   calibration: dict[str, float], metrics: dict[str, Any], extra: dict[str, Any] | None = None) -> Path:
    art_dir.mkdir(parents=True, exist_ok=True)
    m = {
        "model_version": model_version, "model_type": model_type, "package_version": __version__,
        "created_at": datetime.now(KST).isoformat(timespec="seconds"), "git_commit": git_commit(),
        "data_version": data_version, "preprocess_patterns_version": patterns_version(),
        # service의 _thresholds_flat은 'M' 구간 값을 대표값으로 읽는다
        "thresholds": thresholds, "min_chars": MIN_CHARS, "calibration": calibration,
        "metrics_summary": metrics, **(extra or {}),
    }
    path = art_dir / "manifest.json"
    path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def new_experiment_dir() -> tuple[str, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    day = datetime.now(KST).strftime("%Y%m%d")
    n = 1 + sum(1 for p in REPORTS.glob(f"EXP-{day}-*") if p.is_dir())
    exp = f"EXP-{day}-{n:02d}"
    d = REPORTS / exp
    d.mkdir(parents=True, exist_ok=True)
    return exp, d


def log_experiment(exp: str, row: dict[str, Any]) -> None:
    """reports/experiments.csv에 한 줄 추가 (MODEL_DEV.md 4.1 실험 추적)."""
    path = REPORTS / "experiments.csv"
    cols = ["exp", "date", "model_type", "model_version", "data_version", "test_auroc", "test_tpr@1%fpr", "test_tpr@2%fpr",
            "test_ece", "b0_test_auroc", "notes"]
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({"exp": exp, "date": datetime.now(KST).strftime("%Y-%m-%d"), **row})


def default_art_dir(version: str) -> Path:
    return ARTIFACTS / version
