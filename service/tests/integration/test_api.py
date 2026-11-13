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
