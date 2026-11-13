from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from realstar.detection.backends import DummyDetectorBackend, HttpDetectorBackend, RealstarModelBackend
from realstar_detector_server.main import create_app


def test_dummy_predict() -> None:
    c = TestClient(create_app(DummyDetectorBackend()))
    assert c.get("/health").json()["ready"] is True
    r = c.post("/predict", json={"reviews": [{"review_id": "r1", "title": None, "content": "배송 빠르고 좋아요 ㅋㅋ 잘 쓰고 있어요", "star": 5}]})
    assert r.status_code == 200
    p = r.json()["predictions"][0]
    assert p["review_id"] == "r1" and abs(p["p_ai"] + p["p_human"] - 1) < 1e-6
    assert p["label"] in ("human", "ai", "uncertain") and p["model_version"] == "dummy-dev-0"


def test_missing_model_returns_503(tmp_path: Path) -> None:
    c = TestClient(create_app(RealstarModelBackend(tmp_path / "no-artifact")))
    h = c.get("/health").json()
    assert h["ready"] is False and h["error"]
    r = c.post("/predict", json={"reviews": [{"review_id": "r1", "content": "x"}]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "detector_unavailable"


def test_http_backend_unreachable() -> None:
    info = HttpDetectorBackend("http://127.0.0.1:9").info()
    assert info.ready is False and info.error
