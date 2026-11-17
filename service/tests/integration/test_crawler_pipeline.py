"""수집기(coupang_reviews.py) 연동 E2E.

실제 쿠팡에 접속하지 않는다: tests/fakes/scrapling 이 StealthySession을 흉내 내고,
저장소 루트의 coupang_reviews.py는 고치지 않은 그대로 실행된다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realstar.config import REPO_ROOT, Settings
from realstar.detection.backends import DummyDetectorBackend, NoDetectorBackend
from realstar.pipeline.analysis import AnalysisPipeline
from realstar.pipeline.result_schema import AnalysisResult
from realstar.pipeline.service import InlineDispatcher, RealstarService

FAKES = Path(__file__).resolve().parents[1] / "fakes"
PID = "7777777777"
URL = f"https://www.coupang.com/vp/products/{PID}?itemId=1"


@pytest.fixture()
def crawler_settings(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("PYTHONPATH", str(FAKES))
    monkeypatch.delenv("FAKE_COUPANG_BLOCK", raising=False)
    return settings.model_copy(update={
        "review_provider": "crawler",
        "crawler_script": REPO_ROOT / "coupang_reviews.py",
        "crawler_output_dir": tmp_path / "output",
        "sample_per_star": 30,
        "detector_mode": "none",
    })


def make(settings: Settings, detector: object) -> tuple[RealstarService, InlineDispatcher, list[dict]]:  # type: ignore[type-arg]
    pipe = AnalysisPipeline(settings, detector=detector)  # type: ignore[arg-type]
    snapshots: list[dict] = []  # type: ignore[type-arg]
    orig = pipe._progress

    def spy(analysis_id: str, **progress: object) -> None:
        orig(analysis_id, **progress)
        snapshots.append(dict(progress))

    pipe._progress = spy  # type: ignore[method-assign]
    disp = InlineDispatcher(settings, pipe)
    return RealstarService(settings, disp), disp, snapshots


def run(svc: RealstarService, disp: InlineDispatcher, force: bool = False) -> dict:  # type: ignore[type-arg]
    started = svc.start_analysis(PID, force_refresh=force, input_={"type": "url", "query": URL})
    disp.wait_all(120)
    view = svc.get_analysis(started["analysis_id"])
    assert view is not None
    return view


def test_link_runs_crawler_and_shows_result_without_model(crawler_settings: Settings) -> None:
    svc, disp, snaps = make(crawler_settings, NoDetectorBackend())
    res = svc.resolve_link(URL)
    assert res.status == "resolved" and res.candidates[0].product_id == PID

    view = run(svc, disp)
    assert view["status"] == "done", view["error"]
    result = AnalysisResult.model_validate(view["result"])
    assert result.detection.available is False
    assert result.product.name == "가짜 비타민C 1000 120정"
    assert result.product.image_url == "https://thumbnail.coupangcdn.com/fake.jpg"
    assert result.platform_stats.star_counts == {"5": 42, "4": 13, "3": 5, "2": 0, "1": 3}
    assert {k: v.collected for k, v in result.per_star.items()} == {"5": 30, "4": 13, "3": 5, "2": 0, "1": 3}
    assert round(result.ratings.avg_all or 0, 2) == 4.44 and result.ratings.avg_human is None
    assert result.warnings[0].code == "detection_unavailable"

    # 진행 화면에 쓰이는 이벤트가 단계별로 들어왔다
    stages = [s.get("crawl_stage") for s in snaps if s.get("crawl_stage")]
    assert {"browser", "open_page", "summary"} <= set(stages)
    star5 = [s["stars"]["5"]["collected"] for s in snaps if "5" in (s.get("stars") or {}) and "collected" in s["stars"]["5"]]
    assert star5[-1] == 30 and max(star5) == 30
    assert any(s.get("logs") for s in snaps)

    # 수집기 형식 그대로 output/products 에 저장되고, 홈페이지 목록·리뷰 API로 이어진다
    saved = json.loads((crawler_settings.crawler_output_dir / "products" / f"{PID}.json").read_text(encoding="utf-8"))
    assert saved["상품정보"]["수집_완료"] is True and len(saved["리뷰"]) == 51
    products = svc.list_products()
    assert products[0]["product_id"] == PID and products[0]["analysis_id"] == view["analysis_id"]
    page = svc.list_reviews(PID, star=5, offset=0, limit=10)
    assert page["total"] == 30 and len(page["items"]) == 10 and page["items"][0]["content"]


def test_saved_file_is_reused_and_force_recollects(crawler_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    svc, disp, _ = make(crawler_settings, NoDetectorBackend())
    assert run(svc, disp)["status"] == "done"
    # 저장 파일 재사용: 차단 상태여도 브라우저를 열지 않으므로 성공한다
    monkeypatch.setenv("FAKE_COUPANG_BLOCK", "1")
    svc2, disp2, snaps2 = make(crawler_settings.model_copy(update={"cache_ttl_hours": 0}), NoDetectorBackend())
    v = run(svc2, disp2, force=False)
    assert v["status"] == "done" and any(s.get("crawl_stage") == "reuse" for s in snaps2)
    # 강제 새로고침은 수집기를 다시 실행 → 403 → 차단 상태
    v2 = run(svc2, disp2, force=True)
    assert v2["status"] == "blocked"


def test_with_detector_full_result(crawler_settings: Settings) -> None:
    svc, disp, _ = make(crawler_settings, DummyDetectorBackend())
    v = run(svc, disp)
    assert v["status"] == "done", v["error"]
    r = AnalysisResult.model_validate(v["result"])
    assert r.detection.available is True and r.ratings.avg_human is not None


def test_crawler_missing_dependency(crawler_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "")  # 가짜 scrapling 없음 → 수집기 import 실패
    svc, disp, _ = make(crawler_settings, NoDetectorBackend())
    v = run(svc, disp)
    assert v["status"] == "failed" and v["error"]["code"] == "crawler_unavailable"


def test_short_link_and_search(crawler_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    html = tmp_path / "search.html"
    html.write_text(
        '<ul><li class="search-product"><a class="search-product-link" href="/vp/products/7777777777?itemId=1&vendorItemId=2">'
        '<img src="//thumbnail.coupangcdn.com/a.jpg" alt="가짜 비타민C 1000 120정"><div class="name">가짜 비타민C 1000 120정</div>'
        '<strong class="price-value">12,900</strong><span class="rating">4.5</span><span class="rating-total-count">(63)</span></a></li>'
        '<li class="search-product search-product__ad-badge"><a href="/vp/products/8888888888?itemId=3&sourceType=srp_product_ads">'
        '<div class="name">다른 비타민 세트</div></a></li></ul>',
        encoding="utf-8",
    )
    monkeypatch.setenv("FAKE_COUPANG_SEARCH", str(html))
    svc, _, _ = make(crawler_settings, NoDetectorBackend())
    r = svc.resolve_link("[쿠팡] 비타민 https://link.coupang.com/a/fake")
    assert r.status == "resolved" and r.candidates[0].product_id == PID
    s = svc.search("가짜 비타민C 1000")
    ids = [c.product_id for c in s.candidates]
    assert PID in ids
    top = next(c for c in s.candidates if c.product_id == PID)
    assert top.price == 12900 and top.review_count == 63 and top.rating == 4.5


def test_cooldown_still_serves_saved_files_and_local_search(crawler_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from realstar.state.store import Cooldown, get_state_store

    svc, disp, _ = make(crawler_settings, NoDetectorBackend())
    assert run(svc, disp)["status"] == "done"
    Cooldown(get_state_store(crawler_settings), crawler_settings.block_cooldown_min).start("test")
    monkeypatch.setenv("FAKE_COUPANG_BLOCK", "1")
    svc2, disp2, _ = make(crawler_settings.model_copy(update={"cache_ttl_hours": 0}), NoDetectorBackend())
    assert run(svc2, disp2)["status"] == "done"  # 저장 파일은 쿨다운과 무관
    s = svc2.search("가짜 비타민")  # 브라우저 없이 수집한 상품에서 찾는다
    assert s.status == "needs_selection" and s.candidates[0].product_id == PID
    s2 = svc2.search("없는 상품 이름")
    assert s2.status == "blocked" and s2.message


def test_search_blocked_has_message(crawler_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_COUPANG_BLOCK", "1")
    svc, _, _ = make(crawler_settings, NoDetectorBackend())
    r = svc.search("아무 상품")
    assert r.status == "blocked" and "링크" in (r.message or "")


def test_crawler_crash_shows_reason(crawler_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_COUPANG_CRASH", "Target page, context or browser has been closed")
    svc, disp, _ = make(crawler_settings, NoDetectorBackend())
    v = run(svc, disp)
    assert v["status"] == "failed" and v["error"]["code"] == "crawler_failed"
    assert v["error"]["message"].startswith("리뷰를 수집하지 못했어요: 요약 정보를 가져오지 못함")
    log_file = crawler_settings.crawler_output_dir / "raw" / "debug" / "crawler_last.log"
    assert "browser has been closed" in log_file.read_text(encoding="utf-8")


def test_missing_browser_gives_install_command(crawler_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_COUPANG_LAUNCH_ERROR", "BrowserType.launch_persistent_context: Executable doesn't exist at /x/chromium-1248/chrome")
    svc, disp, _ = make(crawler_settings, NoDetectorBackend())
    v = run(svc, disp)
    assert v["status"] == "failed" and v["error"]["code"] == "crawler_unavailable"
    assert "patchright install chromium" in v["error"]["message"]
