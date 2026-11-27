from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from realstar.config import Settings
from realstar.detection.backends import DummyDetectorBackend
from realstar.pipeline.analysis import AnalysisPipeline
from realstar.pipeline.service import InlineDispatcher
from realstar_api.main import create_app


def client(settings: Settings, detector: DummyDetectorBackend | None = None) -> tuple[TestClient, InlineDispatcher]:
    disp = InlineDispatcher(settings, AnalysisPipeline(settings, detector=detector or DummyDetectorBackend()))
    return TestClient(create_app(settings, disp)), disp


def test_resolve_url(settings: Settings) -> None:
    c, _ = client(settings)
    r = c.post("/api/resolve", data={"url": "https://m.coupang.com/vm/products/1000000001?itemId=1"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "resolved" and body["candidates"][0]["product_id"] == "1000000001"


def test_resolve_requires_exactly_one(settings: Settings) -> None:
    c, _ = client(settings)
    r = c.post("/api/resolve", data={"url": "https://www.coupang.com/vp/products/1", "query": "청소기"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_input"
    r = c.post("/api/resolve", data={})
    assert r.status_code == 422


def test_resolve_bad_url_message(settings: Settings) -> None:
    c, _ = client(settings)
    r = c.post("/api/resolve", data={"url": "https://www.11st.co.kr/products/1"})
    assert r.status_code == 422 and "쿠팡" in r.json()["error"]["message"]


def test_resolve_query(settings: Settings) -> None:
    c, _ = client(settings)
    r = c.post("/api/resolve", data={"query": "텀블러"})
    assert r.status_code == 200 and r.json()["status"] == "needs_selection"


def test_resolve_image_without_ocr(settings: Settings) -> None:
    c, _ = client(settings)
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, "PNG")
    r = c.post("/api/resolve", files={"image": ("a.png", buf.getvalue(), "image/png")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "vision_unavailable"


def test_analysis_flow(settings: Settings, fixed_example_detector: DummyDetectorBackend) -> None:
    c, disp = client(settings, fixed_example_detector)
    r = c.post("/api/analyses", json={"product_id": "1000000001", "force_refresh": False})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and body["queue_position"] >= 1
    disp.wait_all(60)
    g = c.get(f"/api/analyses/{body['analysis_id']}")
    assert g.status_code == 200
    v = g.json()
    assert v["status"] == "done"
    assert v["result"]["ratings"]["avg_all"] == 4.21
    assert round(v["result"]["ratings"]["avg_human"], 2) == 4.08
    # SSE: 완료된 분석은 progress 후 end 이벤트
    with c.stream("GET", f"/api/analyses/{body['analysis_id']}/events") as s:
        text = "".join(s.iter_text())
    assert "event: progress" in text and "event: end" in text


def test_analysis_not_found(settings: Settings) -> None:
    c, _ = client(settings)
    r = c.get("/api/analyses/an_nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_analysis_bad_body(settings: Settings) -> None:
    c, _ = client(settings)
    assert c.post("/api/analyses", json={}).status_code == 422
    assert c.post("/api/analyses", json={"product_id": "abc"}).status_code == 422


def test_health(settings: Settings) -> None:
    c, _ = client(settings)
    h = c.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["detector"]["backend"] == "dummy" and h["detector"]["is_dummy"]
    assert h["cooldown"]["active"] is False
    assert h["ocr"]["available"] is False


# ── 리뷰 직접 판별 (/api/detect) ─────────────────────────────


def test_detect_reviews_uses_pipeline_detector(settings: Settings) -> None:
    det = DummyDetectorBackend(min_chars=20)
    c, disp = client(settings, det)
    r = c.post("/api/detect", json={"reviews": [
        {"text": "배송 빠르고 포장도 꼼꼼해서 만족스러운 구매였어요 재구매 의사 있어요"},
        {"text": "좋아요"},
    ]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"]["version"] == DummyDetectorBackend.VERSION and body["model"]["is_dummy"] is True
    first, short = body["results"]
    assert first["index"] == 0 and first["label"] in ("ai", "human", "uncertain") and 0 <= first["p_ai"] <= 1
    assert first["thresholds"] == {"T_AI": 0.8, "T_HUMAN": 0.3} and first["too_short"] is False
    assert short["too_short"] is True and short["label"] == "uncertain"   # 20자 미만은 판단 보류
    assert disp.pipeline.detector is det                                   # 분석과 같은 판별기(모델을 두 번 올리지 않음)


def test_detect_validation(settings: Settings) -> None:
    c, _ = client(settings)
    assert c.post("/api/detect", json={"reviews": []}).status_code == 422
    assert c.post("/api/detect", json={"reviews": [{"text": "   "}]}).status_code == 422
    assert c.post("/api/detect", json={"reviews": [{"text": "가" * 3001}]}).status_code == 422
    assert c.post("/api/detect", json={"reviews": [{"text": "리뷰"}] * 21}).status_code == 422


def test_detect_without_model(settings: Settings) -> None:
    from realstar.detection.backends import NoDetectorBackend

    s = settings.model_copy(update={"detector_mode": "none"})
    disp = InlineDispatcher(s, AnalysisPipeline(s, detector=NoDetectorBackend()))
    c = TestClient(create_app(s, disp))
    r = c.post("/api/detect", json={"reviews": [{"text": "배송 빠르고 좋아요 정말 만족합니다 추천해요"}]})
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "detector_unavailable" and "DETECTOR_MODE" in err["message"]


def test_detect_thresholds_by_length_bucket() -> None:
    from realstar.pipeline.service import _bucket_thresholds

    th = {"S": {"T_AI": 0.9, "T_HUMAN": 0.2}, "M": {"T_AI": 0.8, "T_HUMAN": 0.3}, "ALL": {"T_AI": 0.85, "T_HUMAN": 0.25}}
    assert _bucket_thresholds(th, "S") == {"T_AI": 0.9, "T_HUMAN": 0.2}
    assert _bucket_thresholds(th, "L") == {"T_AI": 0.85, "T_HUMAN": 0.25}      # 구간 없으면 ALL
    assert _bucket_thresholds({"T_AI": 0.7, "T_HUMAN": 0.4}, "M") == {"T_AI": 0.7, "T_HUMAN": 0.4}
    assert _bucket_thresholds(None, "M") is None


# ── 판정 기준(서비스 설정) ─────────────────────────────


def test_service_thresholds_relabel_and_version() -> None:
    from realstar.detection.backends import ServiceThresholdBackend
    from realstar.detection.schemas import DetectInput, DetectOutput, ModelInfo

    class Fixed:
        def info(self) -> ModelInfo:
            return ModelInfo(ready=True, backend="t", model_version="det-ko-review-v0.9", thresholds={"T_AI": 0.98, "T_HUMAN": 0.54}, min_chars=20)

        def predict(self, items: list[DetectInput], batch_size: int = 64) -> list[DetectOutput]:
            ps = {"a": 0.95, "b": 0.90, "c": 0.8999, "d": 0.20, "e": 0.1999, "f": 0.99}
            return [DetectOutput(review_id=i.review_id, p_ai=ps[i.review_id], p_human=1 - ps[i.review_id], label="uncertain",
                                 model_version="det-ko-review-v0.9", features={"len_chars": 5 if i.review_id == "f" else 50}) for i in items]

    b = ServiceThresholdBackend(Fixed(), 0.90, 0.20, min_chars=20)
    info = b.info()
    assert info.thresholds == {"T_AI": 0.90, "T_HUMAN": 0.20} and info.model_version == "det-ko-review-v0.9+th90-20"
    outs = b.predict([DetectInput(review_id=k, content="x" * 50) for k in "abcdef"])
    got = {o.review_id: o.label for o in outs}
    # 90% 이상 AI(경계 포함) · 20% 미만 사람(20%는 보류) · 그 사이 보류 · 20자 미만은 무조건 보류
    assert got == {"a": "ai", "b": "ai", "c": "uncertain", "d": "uncertain", "e": "human", "f": "uncertain"}
    assert all(o.model_version == "det-ko-review-v0.9+th90-20" for o in outs)  # 기준이 바뀌면 저장된 판정을 다시 쓰지 않음
    assert {o.review_id: o.p_ai for o in outs}["a"] == 0.95                     # 확률은 그대로


def test_make_backend_applies_thresholds_only_to_real_models(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from realstar.detection.backends import (
        DummyDetectorBackend,
        ServiceThresholdBackend,
        light_info,
        make_backend,
    )

    kw = {"detector_url": "http://x", "artifact_path": tmp_path, "min_chars": 20, "thresholds": (0.9, 0.2)}
    assert isinstance(make_backend("inprocess", **kw), ServiceThresholdBackend)
    assert isinstance(make_backend("dummy", **kw), DummyDetectorBackend)
    assert not isinstance(make_backend("inprocess", **{**kw, "thresholds": None}), ServiceThresholdBackend)
    (tmp_path / "manifest.json").write_text('{"model_version": "det-ko-review-v0.9", "thresholds": {"ALL": {"T_AI": 0.97, "T_HUMAN": 0.5}}}')
    info = light_info("inprocess", detector_url="", artifact_path=tmp_path, min_chars=20, thresholds=(0.9, 0.2))
    assert info.thresholds == {"T_AI": 0.9, "T_HUMAN": 0.2} and info.model_version == "det-ko-review-v0.9+th90-20"


def test_threshold_settings_validation() -> None:
    import pytest

    s = Settings(detect_t_ai=0.85, detect_t_human=0.1)
    assert s.detect_thresholds == (0.85, 0.1)
    assert Settings(detect_threshold_source="model").detect_thresholds is None
    with pytest.raises(ValueError):
        Settings(detect_t_ai=0.3, detect_t_human=0.5)
