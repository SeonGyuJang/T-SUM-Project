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
    from realstar.collectors.crawler_provider import check_crawler

    return {"enabled": True, **check_crawler(settings), "headless": settings.crawler_headless,
            "output_dir": str(settings.crawler_output_dir)}


def _startup_banner(settings: Settings) -> None:
    """uvicorn 터미널에 실행 모드를 크게 보여 준다(잘못된 .env를 바로 알아차리도록)."""
    lines = ["", "=" * 72, f"  리얼별점 API  ·  REVIEW_PROVIDER={settings.review_provider}  ·  DETECTOR_MODE={settings.detector_mode}"]
    if settings.review_provider == "crawler":
        c = _crawler_health(settings)
        lines.append(f"  수집기 파일   : {c['script']}  ({'있음' if c['script_found'] else '없음!'})")
        lines.append(f"  수집기 파이썬 : {c['python']}")
        fix = '없음! → 이 파이썬에 pip install "scrapling[fetchers]" 또는 .env의 CRAWLER_PYTHON 지정'
        lines.append("  scrapling     : " + ("설치됨" if c["scrapling_installed"] else fix))
        lines.append(f"  수집 결과 폴더: {settings.crawler_output_dir}")
        if c.get("problem"):
            lines.append(f"  ⚠ {c['problem']}")
    else:
        lines.append("  ⚠ 예시 데이터(fixture) 모드: 쿠팡 수집기를 실행하지 않아요.")
        lines.append("    실제 수집을 하려면 service/.env 에 REVIEW_PROVIDER=crawler 로 두고 다시 시작하세요.")
    lines.append(f"  홈페이지: service/apps/web 에서 `npm run dev` → {(settings.cors_origin_list or ['http://localhost:3000'])[0]}")
    lines.append("=" * 72)
    print("\n".join(lines), flush=True)


def create_app(settings: Settings | None = None, dispatcher: Dispatcher | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.database_url.startswith("sqlite"):
            init_db(settings.database_url)  # 운영(PostgreSQL)은 alembic upgrade head
        try:
            await asyncio.to_thread(_startup_banner, settings)
        except Exception:  # 안내 출력 실패로 서버가 멈추면 안 된다
            log.exception("startup banner failed")
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

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        # 이 서버는 API다. 홈페이지는 Next.js(service/apps/web, `npm run dev`)가 따로 띄운다.
        web = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:3000"
        return {
            "service": "리얼별점 API",
            "message": f"여기는 API 서버예요. 홈페이지는 service/apps/web 에서 `npm run dev`를 실행한 뒤 {web} 으로 접속하세요.",
            "homepage": web,
            "health": "/api/health",
            "docs": "/docs",
        }

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

