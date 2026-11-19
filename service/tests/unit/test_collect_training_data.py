"""저장소 루트 collect_training_data.py(학습 데이터 수집기) 테스트. 가짜 scrapling으로 실제 쿠팡에 접속하지 않는다."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from realstar.config import REPO_ROOT

FAKES = Path(__file__).resolve().parents[1] / "fakes"
SCRIPT = REPO_ROOT / "collect_training_data.py"
OLD = {"5": 2000, "4": 600, "3": 1600, "2": 300, "1": 1500}
NEW = {"5": 200, "4": 30, "3": 10, "2": 3, "1": 5}


def run(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    e = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_COUPANG_")}
    e.update({"PYTHONPATH": str(FAKES), "FAKE_COUPANG_COUNTS": '{"5": 2000, "4": 300, "3": 1600, "2": 0, "1": 1500}',
              "COLLECT_DELAY_SCALE": "0.01"})
    e.update(env or {})
    # cwd를 임시 폴더로: 수집기의 상대 경로 브라우저 프로필(.browser_profile)이 실제 프로필을 건드리지 않게
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=e, timeout=600, cwd=cwd)


def store(out: Path) -> dict:  # type: ignore[type-arg]
    return json.loads((out / "coupang_training.json").read_text(encoding="utf-8"))


def reviews(d: dict) -> list[dict]:  # type: ignore[type-arg]
    return [r for p in d["products"].values() for r in p["reviews"]]


def test_collect_pre_and_post_split_and_resume(tmp_path: Path) -> None:
    products = tmp_path / "p.txt"
    products.write_text("## 식품\nhttps://www.coupang.com/vp/products/1111111111\n## 생활\nhttps://www.coupang.com/vp/products/2222222222\n",
                        encoding="utf-8")
    out = tmp_path / "out"
    r = run(tmp_path, "collect", str(products), "--out", str(out), "--max-products", "1")
    assert r.returncode == 0, r.stdout + r.stderr
    d = store(out)
    rows = reviews(d)
    pre = [x for x in rows if x["period"] == "pre_chatgpt"]
    post = [x for x in rows if x["period"] == "post_chatgpt"]
    assert len(pre) == 90 and len(post) == 40  # 5·3·1점 30개씩(4점은 최근 리뷰뿐, 2점은 없음) / 이후 4개 별점 × 10
    assert all(x["created_at"] < "2022-11-30" for x in pre) and all(x["created_at"] >= "2023-01-01" for x in post)
    assert len({x["review_id"] for x in rows}) == len(rows)
    assert {x["category"] for x in rows} == {"식품"} and "writer" not in rows[0]
    assert {"2021", "2022"} <= {x["created_at"][:4] for x in pre}  # 오래된 구간까지 고르게 담는다
    assert d["summary"]["reviews_pre_chatgpt"] == 90 and d["products"]["1111111111"]["status"] == "collected"

    r2 = run(tmp_path, "collect", str(products), "--out", str(out))  # 이어서: 끝난 상품은 건너뛴다
    assert "완료 1개 / 남은 1개" in r2.stdout
    assert set(store(out)["products"]) == {"1111111111", "2222222222"}
    s = run(tmp_path, "stats", "--out", str(out))
    assert "H1 쿠팡 이전 리뷰 180 / 15,000" in s.stdout


def test_collect_stops_on_block(tmp_path: Path) -> None:
    products = tmp_path / "p.txt"
    products.write_text("https://www.coupang.com/vp/products/1111111111\n", encoding="utf-8")
    r = run(tmp_path, "collect", str(products), "--out", str(tmp_path / "out"), env={"FAKE_COUPANG_BLOCK": "1"})
    assert r.returncode == 2 and "막았어요" in r.stdout
    saved = tmp_path / "out" / "coupang_training.json"
    assert not saved.exists() or not store(tmp_path / "out")["products"]


def _category_setup(tmp_path: Path, n: int) -> tuple[Path, dict[str, str]]:
    html = tmp_path / "list.html"
    html.write_text("".join(f'<li><a href="/vp/products/40000000{i:02d}?itemId={i}"><img alt="상품 {i}"></a></li>' for i in range(1, n + 1))
                    + '<a href="/np/categories/9">다른 카테고리</a>', encoding="utf-8")
    cats = tmp_path / "cats.txt"
    cats.write_text("## 주방\nhttps://www.coupang.com/np/categories/111111\n", encoding="utf-8")
    counts = {f"40000000{i:02d}": (OLD if i % 2 else NEW) for i in range(1, n + 1)}
    return cats, {"FAKE_COUPANG_SEARCH": str(html), "FAKE_COUPANG_COUNTS_BY_PID": json.dumps(counts)}


def test_category_mode_skips_products_without_old_reviews(tmp_path: Path) -> None:
    cats, env = _category_setup(tmp_path, 2)
    out = tmp_path / "out"
    r = run(tmp_path, "category", str(cats), "--out", str(out), "--per-product", "25", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    d = store(out)
    rows = reviews(d)
    assert {x["product_id"] for x in rows} == {"4000000001"} and len(rows) == 25  # 상품당 최대 25개
    assert all(x["period"] == "pre_chatgpt" and x["category"] == "주방" for x in rows)
    assert {x["star"] for x in rows} >= {1, 3, 5}  # 적은 별점부터 몫을 나눠 담는다
    assert d["products"]["4000000002"]["status"] == "no_old"
    assert len(d["categories"]["https://www.coupang.com/np/categories/111111"]["products"]) == 2
    r2 = run(tmp_path, "category", str(cats), "--out", str(out), env=env)  # 이어서: 목록·확인 결과 재사용
    assert "남은 0개" in r2.stdout and "새로 확인할 상품이 없어요" in r2.stdout


def test_parallel_workers_share_one_file_and_stop_together_on_block(tmp_path: Path) -> None:
    cats, env = _category_setup(tmp_path, 6)
    out = tmp_path / "out"
    r = run(tmp_path, "category", str(cats), "--out", str(out), "--per-product", "10", "--workers", "2", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    d = store(out)
    assert len(d["products"]) == 6 and {p["worker"] for p in d["products"].values()} == {1, 2}
    ids = [x["review_id"] for x in reviews(d)]
    assert len(ids) == len(set(ids)) == 30  # 과거 리뷰가 있는 상품 3개 × 10, 중복 없음
    assert "[W1]" in r.stdout and "[W2]" in r.stdout

    # 차단: 한 작업자가 막히면 모두 멈추고, 끝난 상품만 저장된다 → 다시 실행하면 이어서
    (tmp_path / "b").mkdir()
    cats2, env2 = _category_setup(tmp_path / "b", 6)
    out2 = tmp_path / "b" / "out"
    r2 = run(tmp_path / "b", "category", str(cats2), "--out", str(out2), "--per-product", "10", "--workers", "2",
             env={**env2, "FAKE_COUPANG_BLOCK_PIDS": "4000000004"})
    assert r2.returncode == 2 and "모든 작업자를 멈춥니다" in r2.stdout
    saved = store(out2)["products"]
    assert "4000000004" not in saved and len(saved) < 6
    r3 = run(tmp_path / "b", "category", str(cats2), "--out", str(out2), "--per-product", "10", "--workers", "2", env=env2)
    assert r3.returncode == 0 and len(store(out2)["products"]) == 6


def test_legacy_jsonl_is_imported_once(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    row = {"review_id": "cp-1-1", "product_id": "1", "category": "식품", "product_name": "옛 상품", "star": 5, "title": None,
           "content": "예전에 모은 리뷰", "created_at": "2021-01-01", "period": "pre_chatgpt", "length_bucket": "S"}
    (out / "20261117_000000.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "_state.json").write_text(json.dumps({"products": {"1": {"done": True, "status": "collected"},
                                                              "2": {"done": True, "status": "no_old"}}}), encoding="utf-8")
    r = run(tmp_path, "stats", "--out", str(out))
    assert "옮겨 왔어요" in r.stdout and "H1 쿠팡 이전 리뷰 1 / 15,000" in r.stdout
    # stats는 저장하지 않으므로, 수집 명령이 처음 저장할 때 파일이 생긴다 → 여기서는 저장 경로만 확인
    products = tmp_path / "p.txt"
    products.write_text("https://www.coupang.com/vp/products/1\nhttps://www.coupang.com/vp/products/2\n", encoding="utf-8")
    r2 = run(tmp_path, "collect", str(products), "--out", str(out))
    assert "완료 2개 / 남은 0개" in r2.stdout


def test_throttle_spacing_across_processes(tmp_path: Path) -> None:
    code = (
        "import multiprocessing as mp, sys, time\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import collect_training_data as c\n"
        "def w(lock, last, q):\n"
        "    c._THROTTLE = (lock, last, 0.3)\n"
        "    for _ in range(4):\n"
        "        c.throttle_wait(); q.put(time.time())\n"
        "if __name__ == '__main__':\n"
        "    ctx = mp.get_context('spawn'); lock, last, q = ctx.Lock(), ctx.Value('d', 0.0), ctx.Queue()\n"
        "    ps = [ctx.Process(target=w, args=(lock, last, q)) for _ in range(3)]\n"
        "    [p.start() for p in ps]; ts = sorted(q.get() for _ in range(12)); [p.join() for p in ps]\n"
        "    print(min(b - a for a, b in zip(ts, ts[1:])))\n"
    )
    script = tmp_path / "t.py"
    script.write_text(code, encoding="utf-8")
    t0 = time.time()
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert float(r.stdout.strip()) >= 0.29 and time.time() - t0 >= 3.0  # 12회 × 0.3초 간격
