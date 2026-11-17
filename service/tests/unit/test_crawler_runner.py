"""crawler_runner 단위 테스트 (같은 프로세스에서 실행해 이벤트 형식을 확인한다)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from realstar.collectors import crawler_runner as runner
from realstar.config import REPO_ROOT

FAKES = Path(__file__).resolve().parents[1] / "fakes"


def events(out: str) -> list[dict]:  # type: ignore[type-arg]
    return [json.loads(line[len(runner.PREFIX):]) for line in out.splitlines() if line.startswith(runner.PREFIX)]


@pytest.fixture(autouse=True)
def _fake_scrapling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(FAKES))
    monkeypatch.delenv("FAKE_COUPANG_BLOCK", raising=False)
    sys.modules.pop("coupang_reviews", None)


def test_collect_events(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = runner.main(["collect", "--script", str(REPO_ROOT / "coupang_reviews.py"), "--url",
                        "https://www.coupang.com/vp/products/7777777777", "--per-rating", "20", "--out", str(tmp_path)])
    evts = events(capsys.readouterr().out)
    assert code == 0
    kinds = [e["type"] for e in evts]
    assert kinds[0] == "stage" and kinds[-1] == "result"
    assert {"product", "summary", "star_start", "page", "star_done", "log"} <= set(kinds)
    done = {e["star"]: e["collected"] for e in evts if e["type"] == "star_done"}
    assert done == {5: 20, 4: 13, 3: 5, 1: 3}  # 2점은 0개라 수집기가 건너뛴다
    saved = json.loads((tmp_path / "products" / "7777777777.json").read_text(encoding="utf-8"))
    assert saved["상품정보"]["대표이미지"] == "https://thumbnail.coupangcdn.com/fake.jpg"
    assert (tmp_path / "all_products.json").exists()


def test_collect_blocked(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_COUPANG_BLOCK", "1")
    code = runner.main(["collect", "--script", str(REPO_ROOT / "coupang_reviews.py"), "--url",
                        "https://www.coupang.com/vp/products/7777777777", "--out", str(tmp_path)])
    last = events(capsys.readouterr().out)[-1]
    assert code == 1 and last["type"] == "error" and last["kind"] == "blocked"
    assert "403" in (tmp_path / "failed.txt").read_text(encoding="utf-8")


def test_missing_script(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert runner.main(["resolve", "--script", str(tmp_path / "nope.py"), "--url", "https://link.coupang.com/a/x"]) == 2
    assert events(capsys.readouterr().out)[-1]["kind"] == "setup"


def test_resolve(capsys: pytest.CaptureFixture[str]) -> None:
    assert runner.main(["resolve", "--script", str(REPO_ROOT / "coupang_reviews.py"), "--url", "https://link.coupang.com/a/fake"]) == 0
    assert events(capsys.readouterr().out)[-1]["url"].startswith("https://www.coupang.com/vp/products/7777777777")


def test_parse_search_html() -> None:
    html = (
        '<a href="/vp/products/1?itemId=9&vendorItemId=8"><img data-src="//img.coupangcdn.com/a.jpg" alt="알트 이름">'
        '<div class="ProductUnit_productName__x">삼다수 2L 12개</div><span class="Price_value">7,900원</span>'
        '<span class="ProductRating_rating__x">4.5</span><span>(12,345)</span></a>'
        '<a href="/vp/products/2?sourceType=srp_product_ads"><img src="data:x" alt="광고 상품"></a>'
        '<a href="/np/categories/1">카테고리</a>'
    )
    out = runner.parse_search_html(html, 10)
    assert [o["product_id"] for o in out] == ["1", "2"]
    a, b = out
    assert a["name"] == "삼다수 2L 12개" and a["price"] == 7900 and a["rating"] == 4.5 and a["review_count"] == 12345
    assert a["image_url"] == "https://img.coupangcdn.com/a.jpg" and a["item_id"] == "9" and not a["is_ad"]
    assert b["name"] == "광고 상품" and b["is_ad"] and b["image_url"] is None
