"""저장소 루트 collect_training_data.py(학습 데이터 수집기) 테스트. 가짜 scrapling으로 실제 쿠팡에 접속하지 않는다."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from realstar.config import REPO_ROOT

FAKES = Path(__file__).resolve().parents[1] / "fakes"
SCRIPT = REPO_ROOT / "collect_training_data.py"


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    e = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_COUPANG_")}
    e.update({"PYTHONPATH": str(FAKES), "FAKE_COUPANG_COUNTS": '{"5": 2000, "4": 300, "3": 1600, "2": 0, "1": 1500}'})
    e.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=e, timeout=300)


def test_collect_pre_and_post_split_and_resume(tmp_path: Path) -> None:
    products = tmp_path / "p.txt"
    products.write_text("## 식품\nhttps://www.coupang.com/vp/products/1111111111\n## 생활\nhttps://www.coupang.com/vp/products/2222222222\n",
                        encoding="utf-8")
    out = tmp_path / "out"
    r = run("collect", str(products), "--out", str(out), "--max-products", "1")
    assert r.returncode == 0, r.stdout + r.stderr
    rows = [json.loads(line) for f in out.glob("*.jsonl") for line in f.read_text(encoding="utf-8").splitlines()]
    pre = [x for x in rows if x["period"] == "pre_chatgpt"]
    post = [x for x in rows if x["period"] == "post_chatgpt"]
    assert len(pre) == 90 and len(post) == 40  # 5·3·1점 30개씩(4점은 최근 리뷰뿐, 2점은 없음) / 이후 4개 별점 × 10
    assert all(x["created_at"] < "2022-11-30" for x in pre) and all(x["created_at"] >= "2023-01-01" for x in post)
    assert len({x["review_id"] for x in rows}) == len(rows)
    assert {x["category"] for x in rows} == {"식품"} and "writer" not in rows[0]
    years = {x["created_at"][:4] for x in pre}
    assert {"2021", "2022"} <= years  # 오래된 구간까지 고르게 담는다

    r2 = run("collect", str(products), "--out", str(out))  # 이어서: 끝난 상품은 건너뛴다
    assert "완료 1개 / 이번에 1개" in r2.stdout
    state = json.loads((out / "_state.json").read_text(encoding="utf-8"))
    assert set(state["products"]) == {"1111111111", "2222222222"}
    s = run("stats", "--out", str(out))
    assert "H1 쿠팡 이전 리뷰 180 / 15,000" in s.stdout


def test_collect_stops_on_block(tmp_path: Path) -> None:
    products = tmp_path / "p.txt"
    products.write_text("https://www.coupang.com/vp/products/1111111111\n", encoding="utf-8")
    r = run("collect", str(products), "--out", str(tmp_path / "out"), env={"FAKE_COUPANG_BLOCK": "1"})
    assert r.returncode == 2 and "막았어요" in r.stdout
    assert not (tmp_path / "out" / "_state.json").exists()
