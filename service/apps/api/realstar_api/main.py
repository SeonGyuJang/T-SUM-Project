"""FastAPI 앱 (README 5.7).

  POST /api/resolve              multipart: url | query | image 중 하나 → 5.1 출력
  POST /api/analyses             {"product_id", "force_refresh"} → {"analysis_id", "status", "queue_position"}
  GET  /api/analyses/{id}        상태·진행률·결과
  GET  /api/analyses/{id}/events SSE 진행 이벤트
  GET  /api/products             수집한 상품 목록 (수집기 output/ + DB)
  GET  /api/products/{id}/reviews  수집한 리뷰 (별점 필터·페이지)
  GET  /api/health               detector, 수집기, 차단 쿨다운 상태
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from realstar import __version__
from realstar.config import Settings, get_settings
from realstar.db.session import init_db
from realstar.detection import preprocess
from realstar.detection.backends import light_info
from realstar.errors import InvalidInputError, RealstarError
from realstar.pipeline.service import Dispatcher, RealstarService, make_dispatcher
from realstar.state.store import Cooldown, get_state_store

log = logging.getLogger(__name__)

STATUS_FOR_CODE = {
    "invalid_input": 422,
    "forbidden_area": 422,
    "scraper_busy": 503,
    "vision_unavailable": 503,
    "detector_unavailable": 503,
    "blocked": 503,
    "crawler_unavailable": 503,
    "page_budget_exceeded": 429,
}


class CreateAnalysis(BaseModel):
    product_id: str = Field(min_length=1, max_length=20)
    force_refresh: bool = False
    source: dict[str, Any] | None = None


def _crawler_health(settings: Settings) -> dict[str, Any]:
    if settings.review_provider != "crawler":
        return {"enabled": False}
    import importlib.util

    script = settings.crawler_script
    return {
        "enabled": True,
        "script": str(script),
        "script_found": script.exists(),
        "python": settings.crawler_python or "(서비스와 같은 파이썬)",
        # 다른 파이썬을 지정했으면 그쪽 설치 여부는 여기서 알 수 없다
        "scrapling_installed": None if settings.crawler_python else importlib.util.find_spec("scrapling") is not None,
        "headless": settings.crawler_headless,
        "output_dir": str(settings.crawler_output_dir),
    }


def create_app(settings: Settings | None = None, dispatcher: Dispatcher | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.database_url.startswith("sqlite"):
            init_db(settings.database_url)  # 운영(PostgreSQL)은 alembic upgrade head
        yield

    app = FastAPI(title="리얼별점 API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["GET", "POST"], allow_headers=["*"],
    )
    disp = dispatcher or make_dispatcher(settings)
    svc = RealstarService(settings, disp)
    app.state.service = svc
    app.state.settings = settings

    @app.exception_handler(RealstarError)
    async def _realstar_error(_: Request, exc: RealstarError) -> JSONResponse:
        return JSONResponse(
            status_code=STATUS_FOR_CODE.get(exc.code, 500),
            content={"error": {"code": exc.code, "message": exc.user_message}},
        )

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_input", "message": "입력을 확인해 주세요.", "detail": [{"loc": list(e.get("loc", [])), "msg": str(e.get("msg"))} for e in exc.errors()[:3]]}})

    @app.post("/api/resolve")
    async def resolve(
        url: str | None = Form(default=None),
        query: str | None = Form(default=None),
        image: UploadFile | None = File(default=None),
    ) -> dict[str, Any]:
        given = [x for x in (url, query, image) if x not in (None, "")]
        if len(given) != 1:
            raise InvalidInputError("exactly one of url/query/image", "링크, 상품명, 이미지 중 하나만 입력해 주세요.")
        if url:
            res = await asyncio.to_thread(svc.resolve_link, url)
        elif query:
            res = await asyncio.to_thread(svc.search, query)
        else:
            assert image is not None
            data = await image.read(settings.image_max_bytes + 1)  # 메모리에서만 처리, 저장하지 않음
            res = await asyncio.to_thread(svc.resolve_image, data)
            del data
        return res.model_dump()

    @app.post("/api/analyses", status_code=202)
    async def create_analysis(body: CreateAnalysis) -> dict[str, Any]:
        return await asyncio.to_thread(svc.start_analysis, body.product_id, force_refresh=body.force_refresh, input_=body.source)

    @app.get("/api/analyses/{analysis_id}")
    async def get_analysis(analysis_id: str) -> dict[str, Any]:
        view = await asyncio.to_thread(svc.get_analysis, analysis_id)
        if view is None:
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "분석 결과를 찾지 못했어요. 주소를 확인하거나 다시 분석해 주세요."}})  # type: ignore[return-value]
        return view

    @app.get("/api/products")
    async def list_products() -> dict[str, Any]:
        return {"items": await asyncio.to_thread(svc.list_products)}

    @app.get("/api/products/{product_id}/reviews")
    async def list_reviews(
        product_id: str,
        star: int | None = Query(default=None, ge=1, le=5),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=10, ge=1, le=50),
        model_version: str | None = Query(default=None, max_length=64),
    ) -> dict[str, Any]:
        if not product_id.isdigit():
            raise InvalidInputError("bad product_id", "상품 번호가 올바르지 않아요.")
        return await asyncio.to_thread(svc.list_reviews, product_id, star=star, offset=offset, limit=limit, model_version=model_version)

    @app.get("/api/analyses/{analysis_id}/events")
    async def analysis_events(analysis_id: str, request: Request) -> StreamingResponse:
        async def gen() -> AsyncIterator[str]:
            last = None
            idle = 0
            for _ in range(3600):
                if await request.is_disconnected():
                    return
                view = await asyncio.to_thread(svc.get_analysis, analysis_id)
                if view is None:
                    yield "event: error\ndata: {\"code\": \"not_found\"}\n\n"
                    return
                payload = json.dumps({k: view[k] for k in ("analysis_id", "status", "progress", "error")}, ensure_ascii=False)
                if payload != last:
                    yield f"event: progress\ndata: {payload}\n\n"
                    last = payload
                    idle = 0
                else:
                    idle += 1
                    if idle >= 15:  # 프록시 유휴 연결 종료 방지(Heroku: 55초 동안 데이터가 없으면 끊김)
                        yield ": keep-alive\n\n"
                        idle = 0
                if view["status"] in ("done", "failed", "blocked"):
                    yield f"event: end\ndata: {json.dumps({'status': view['status']})}\n\n"
                    return
                await asyncio.sleep(1.0)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        def _collect() -> dict[str, Any]:
            cd = Cooldown(get_state_store(settings), settings.block_cooldown_min).status()
            det = light_info(
                settings.detector_mode, detector_url=settings.detector_url, artifact_path=settings.model_artifact_path,
                min_chars=settings.min_chars,
            )
            from realstar.vision.ocr import get_ocr_engine

            ocr = get_ocr_engine(settings.ocr_engine) if settings.ocr_engine != "none" else None
            return {
                "status": "ok",
                "version": __version__,
                "detector": det.model_dump(),
                "preprocess": {"realstar_model": preprocess.model_preprocess_available()},
                "review_provider": settings.review_provider,
                "crawler": _crawler_health(settings),
                "cooldown": {"active": cd is not None, **(cd or {})},
                "ocr": {"engine": settings.ocr_engine, "available": bool(ocr and ocr.available), "vlm_enabled": settings.vlm_enabled},
                "task_backend": settings.task_backend,
            }

        return await asyncio.to_thread(_collect)

    return app

