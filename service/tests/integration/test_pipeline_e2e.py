"""FixtureProvider + 더미 detector E2E (README 10). 실제 쿠팡에 접속하지 않는다."""

from __future__ import annotations

import pytest

from realstar.config import Settings
from realstar.detection.backends import DummyDetectorBackend
from realstar.pipeline.analysis import AnalysisPipeline
from realstar.pipeline.result_schema import AnalysisResult
from realstar.pipeline.service import InlineDispatcher, RealstarService
from realstar.state.store import Cooldown, get_state_store


def make_service(settings: Settings, detector: DummyDetectorBackend | None = None) -> tuple[RealstarService, InlineDispatcher]:
    pipe = AnalysisPipeline(settings, detector=detector or DummyDetectorBackend())
    disp = InlineDispatcher(settings, pipe)
    return RealstarService(settings, disp), disp


def run(svc: RealstarService, disp: InlineDispatcher, product_id: str, force: bool = False) -> dict:  # type: ignore[type-arg]
    started = svc.start_analysis(product_id, force_refresh=force)
    disp.wait_all(60)
    view = svc.get_analysis(started["analysis_id"])
    assert view is not None
    return view


def test_fixed_example_end_to_end(settings: Settings, fixed_example_detector: DummyDetectorBackend) -> None:
    svc, disp = make_service(settings, fixed_example_detector)
    res = svc.resolve_link("https://www.coupang.com/vp/products/1000000001?itemId=111&vendorItemId=222")
    assert res.status == "resolved" and res.candidates[0].product_id == "1000000001"
    view = run(svc, disp, "1000000001")
    assert view["status"] == "done", view["error"]
    result = AnalysisResult.model_validate(view["result"])  # 5.7 스키마 검증
    r = result.ratings
    assert round(r.avg_all or 0, 2) == 4.21
    assert round(r.avg_human or 0, 2) == 4.08
    assert round(r.diff or 0, 2) == -0.13
    assert round(r.ai_share or 0, 3) == 0.499
    assert r.avg_human_ci95 and r.avg_human_ci95[0] < (r.avg_human or 0) < r.avg_human_ci95[1]
    assert result.per_star["5"].model_dump() == {"total": 1200, "collected": 100, "human": 50, "ai": 50, "uncertain": 0, "human_ratio": 0.5, "ratio_substituted": False}
    assert result.platform_stats.star_counts == {"5": 1200, "4": 400, "3": 160, "2": 100, "1": 140}
    assert result.sampling.per_star_limit == 100 and result.sampling.sort == "latest"
    for s in "54321":
        tops = result.top_human_reviews[s]
        assert 1 <= len(tops) <= 5
        assert all(t.len_chars >= 40 for t in tops)
    assert result.model.version == "dummy-dev-0" and result.model.is_dummy
    assert result.warnings[0].code == "dummy_detector"
    assert view["progress"]["stars"]["5"]["collected"] == 100


def test_cache_reuse_and_force_refresh(settings: Settings) -> None:
    svc, disp = make_service(settings)
    v1 = run(svc, disp, "1000000002")
    assert v1["status"] == "done"
    again = svc.start_analysis("1000000002")
    assert again["cached"] and again["analysis_id"] == v1["analysis_id"]  # TTL 안이면 캐시 결과
    v2 = run(svc, disp, "1000000002", force=True)
    assert v2["analysis_id"] != v1["analysis_id"] and v2["status"] == "done"


def test_review_sample_cache_skips_scraping(settings: Settings) -> None:
    svc, disp = make_service(settings)
    run(svc, disp, "1000000002")
    # 결과 캐시를 무시하고(force 아님) 새 분석을 만들려면 결과만 지우고 표본은 남긴다
    from realstar.db.models import Analysis
    from realstar.db.session import session_scope

    with session_scope(settings.database_url) as s:
        for a in s.query(Analysis).all():
            s.delete(a)
    v = run(svc, disp, "1000000002")
    assert v["status"] == "done" and v["result"]["sampling"]["from_cache"]


def test_insufficient_sample_warnings(settings: Settings) -> None:
    svc, disp = make_service(settings)
    v = run(svc, disp, "1000000002")
    codes = {w["code"] for w in v["result"]["warnings"]}
    assert "insufficient_sample" in codes
    assert v["result"]["per_star"]["1"]["collected"] == 1


def test_blocked_stops_and_starts_cooldown(settings: Settings) -> None:
    svc, disp = make_service(settings)
    v = run(svc, disp, "1000000003")
    assert v["status"] == "blocked" and v["result"] is None  # 부분 결과로 결과를 만들지 않는다
    assert v["error"]["code"] == "blocked" and "cooldown_until" in v["error"]
    assert v["error"]["partial_counts"] == {"5": 100, "4": 100}
    cd = Cooldown(get_state_store(settings), settings.block_cooldown_min)
    assert cd.status() is not None
    # 쿨다운 동안 새 수집은 즉시 blocked
    v2 = run(svc, disp, "1000000001")
    assert v2["status"] == "blocked" and v2["error"]["code"] == "blocked"


def test_blocked_shows_cached_result(settings: Settings) -> None:
    svc, disp = make_service(settings)
    ok = run(svc, disp, "1000000002")
    Cooldown(get_state_store(settings), 60).start("test")
    v = run(svc, disp, "1000000002", force=True)
    assert v["status"] == "blocked"
    assert v["error"]["cached_analysis_id"] == ok["analysis_id"]


def test_parser_broken_fails(settings: Settings) -> None:
    svc, disp = make_service(settings)
    v = run(svc, disp, "1000000005")
    assert v["status"] == "failed" and v["error"]["code"] == "parser_broken"
    from realstar.db.models import ScrapeLog
    from realstar.db.session import session_scope

    with session_scope(settings.database_url) as s:
        logs = s.query(ScrapeLog).all()
        assert logs[-1].outcome == "parser_broken"


def test_zero_reviews(settings: Settings) -> None:
    svc, disp = make_service(settings)
    v = run(svc, disp, "1000000004")
    assert v["status"] == "done"
    assert v["result"]["ratings"]["avg_all"] is None
    assert v["result"]["warnings"][1]["code"] == "no_reviews"


def test_detector_unavailable(settings: Settings) -> None:
    class Down(DummyDetectorBackend):
        def info(self):  # type: ignore[no-untyped-def]
            i = super().info()
            i.ready = False
            i.error = "model not loaded"
            return i

    svc, disp = make_service(settings, Down())
    v = run(svc, disp, "1000000002")
    assert v["status"] == "failed" and v["error"]["code"] == "detector_unavailable"


def test_short_link_and_name_search(settings: Settings) -> None:
    svc, disp = make_service(settings)
    r = svc.resolve_link("[쿠팡] 예시 청소기 https://link.coupang.com/a/demo01")
    assert r.status == "resolved" and r.candidates[0].product_id == "1000000001" and r.candidates[0].item_id == "111"
    s = svc.search("텀블러")
    assert s.status == "needs_selection"
    s2 = svc.search("텀블러")  # 캐시 경로(브라우저 미사용)
    assert s2.cached


def test_min_chars_forced_uncertain(settings: Settings) -> None:
    detector = DummyDetectorBackend(min_chars=0)  # 모델이 라벨을 줘도 서비스가 MIN_CHARS 규칙을 강제
    svc, disp = make_service(settings.model_copy(update={"min_chars": 10_000}), detector)
    v = run(svc, disp, "1000000002")
    ps = v["result"]["per_star"]["5"]
    assert ps["uncertain"] == ps["collected"] and ps["human"] == 0


@pytest.mark.parametrize("bad", ["abc", "12a"])
def test_bad_product_id(settings: Settings, bad: str) -> None:
    from realstar.errors import InvalidInputError

    svc, _ = make_service(settings)
    with pytest.raises(InvalidInputError):
        svc.start_analysis(bad)
