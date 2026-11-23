"""model/ 폴더 기준 경로. 데이터·아티팩트는 git에 올리지 않는다(.gitignore: model/data/, model/artifacts/)."""

from __future__ import annotations

from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parents[2]  # .../model
REPO_ROOT = MODEL_ROOT.parent
DATA = MODEL_ROOT / "data"
RAW_NAVER = DATA / "raw" / "naver" / "naver_shopping.jsonl"
RAW_COUPANG = DATA / "raw" / "coupang" / "coupang_training.json"
GENERATED = DATA / "generated"
PROCESSED = DATA / "processed"
ARTIFACTS = MODEL_ROOT / "artifacts"
REPORTS = MODEL_ROOT / "reports"
