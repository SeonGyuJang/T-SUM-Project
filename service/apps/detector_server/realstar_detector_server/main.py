"""AI Detector HTTP 서버 (README 4장, Phase 2 'detector_server /predict 배치 API').

`realstar_model` 패키지(model/)를 import해 `/predict`를 제공한다. 모델 코드는 model/ 담당이고
이 서버는 HTTP 래퍼다(MODEL_DEV.md 4.12.2).

환경 변수
  DETECTOR_BACKEND      realstar_model(기본) | dummy(개발 전용)
  MODEL_ARTIFACT_PATH   예: ../model/artifacts/det-ko-review-v1.0  (manifest.json이 있는 폴더)

모델이 아직 없으면 /health에 ready=false와 이유를 보여 주고 /predict는 503을 돌려준다.
모델이 완성되면 `pip install -e ../model` 후 MODEL_ARTIFACT_PATH만 지정해 재시작하면 된다.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from realstar.config import get_settings
from realstar.detection.backends import DetectorBackend, DummyDetectorBackend, RealstarModelBackend
from realstar.detection.schemas import ModelInfo, PredictRequest, PredictResponse
from realstar.errors import DetectorUnavailableError

log = logging.getLogger(__name__)
MAX_BATCH = 2000


def make_server_backend() -> DetectorBackend:
    settings = get_settings()
    kind = os.environ.get("DETECTOR_BACKEND", "realstar_model")
    if kind == "dummy":
        log.warning("DETECTOR_BACKEND=dummy — 개발용 더미 판별기로 동작합니다")
        return DummyDetectorBackend(min_chars=settings.min_chars)
    return RealstarModelBackend(
        Path(os.environ.get("MODEL_ARTIFACT_PATH", str(settings.model_artifact_path))), settings.model_artifact_url
    )


def create_app(backend: DetectorBackend | None = None) -> FastAPI:
    app = FastAPI(title="리얼별점 Detector", version="0.1.0")
    state: dict[str, DetectorBackend] = {}

    def get_backend() -> DetectorBackend:
        if "b" not in state:
            state["b"] = backend or make_server_backend()
        return state["b"]

    @app.get("/health", response_model=ModelInfo)
    def health() -> ModelInfo:
        return get_backend().info()

    @app.post("/predict", response_model=PredictResponse)
    def predict(req: PredictRequest) -> PredictResponse | JSONResponse:
        b = get_backend()
        info = b.info()
        if not info.ready:
            return JSONResponse(status_code=503, content={"error": {"code": "detector_unavailable", "message": info.error or "model not loaded"}})
        if len(req.reviews) > MAX_BATCH:
            return JSONResponse(status_code=413, content={"error": {"code": "batch_too_large", "message": f"최대 {MAX_BATCH}건"}})
        t0 = time.perf_counter()
        try:
            preds = b.predict(req.reviews, batch_size=req.batch_size)
        except DetectorUnavailableError as e:
            return JSONResponse(status_code=503, content={"error": {"code": "detector_unavailable", "message": e.detail}})
        log.info("predict %d reviews in %.2fs", len(req.reviews), time.perf_counter() - t0)
        return PredictResponse(predictions=preds, model=info)

    return app
