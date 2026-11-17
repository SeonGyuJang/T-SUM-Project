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


def test_category_mode_skips_products_without_old_reviews(tmp_path: Path) -> None:
    html = tmp_path / "list.html"
    html.write_text(
        '<li><a href="/vp/products/3000000001?itemId=1"><img alt="오래된 상품"></a></li>'
        '<li><a href="/vp/products/3000000002"><div class="name">신상품</div></a></li>'
        '<a href="/np/categories/9">다른 카테고리</a>', encoding="utf-8")
    cats = tmp_path / "cats.txt"
    cats.write_text("## 주방\nhttps://www.coupang.com/np/categories/111111\n", encoding="utf-8")
    env = {
        "FAKE_COUPANG_SEARCH": str(html),
        "FAKE_COUPANG_COUNTS_BY_PID": json.dumps({
            "3000000001": {"5": 2000, "4": 600, "3": 1600, "2": 300, "1": 1500},
            "3000000002": {"5": 200, "4": 30, "3": 10, "2": 3, "1": 5},
        }),
    }
    out = tmp_path / "out"
    r = run("category", str(cats), "--out", str(out), "--per-product", "25", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    rows = [json.loads(line) for f in out.glob("*.jsonl") for line in f.read_text(encoding="utf-8").splitlines()]
    assert {x["product_id"] for x in rows} == {"3000000001"} and len(rows) == 25  # 상품당 최대 25개
    assert all(x["period"] == "pre_chatgpt" and x["category"] == "주방" for x in rows)
    assert {x["star"] for x in rows} >= {1, 3, 5}  # 적은 별점부터 몫을 나눠 담는다
    state = json.loads((out / "_state.json").read_text(encoding="utf-8"))
    assert state["products"]["3000000002"]["status"] == "no_old"
    r2 = run("category", str(cats), "--out", str(out), env=env)  # 이어서: 목록·확인 결과 재사용
    assert "이번에 0개" in r2.stdout
