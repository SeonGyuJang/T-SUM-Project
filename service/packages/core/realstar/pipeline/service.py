"""API·CLI가 함께 쓰는 애플리케이션 서비스: 분석 생성/조회, 상품 식별, 작업 디스패치."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Protocol

from realstar.collectors import make_provider
from realstar.config import Settings
from realstar.db import repository as repo
from realstar.db.models import Analysis, Product
from realstar.db.session import session_scope
from realstar.detection.backends import DetectorBackend, make_backend
from realstar.detection.schemas import DetectInput
from realstar.errors import (
    BlockedError,
    DetectorUnavailableError,
    InvalidInputError,
    RealstarError,
    ScraperBusyError,
)
from realstar.pipeline.analysis import AnalysisPipeline
from realstar.resolver import resolve_url
from realstar.resolver.models import ResolveResult
from realstar.resolver.name_search import resolve_by_name
from realstar.resolver.scoring import normalize_query
from realstar.resolver.url import classify
from realstar.state.store import SCRAPE_LOCK_KEY, Cooldown, get_state_store

log = logging.getLogger(__name__)


# ── 스크래퍼 컨텍스트에서 실행되는 식별 작업 (브라우저 필요) ──────────────
def run_browser_resolve(settings: Settings, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """단축 링크 해석·상품명 검색. 수집 워커(또는 inline 스크래퍼 스레드)에서 실행된다."""
    state = get_state_store(settings)
    cooldown = Cooldown(state, settings.block_cooldown_min)
    cache = repo.DbSearchCache(settings.database_url)
    if cooldown.status():
        if kind == "query" and settings.review_provider == "crawler":
            # 차단 쉬는 중: 브라우저는 열지 않고 이미 수집한 상품에서만 찾는다
            from realstar.collectors.crawler_provider import CrawlerProvider

            local = CrawlerProvider(settings)
            res = resolve_by_name(payload["query"], _LocalOnly(local), _NoCache(),  # type: ignore[arg-type]
                                  settings, brand=payload.get("brand"), force_selection=True,
                                  input_type=payload.get("input_type", "query"))
            if res.status == "not_found":
                res.status = "blocked"
                res.message = COOLDOWN_SEARCH_MESSAGE
            return res.model_dump()
        return ResolveResult(status="blocked", input_type=payload.get("input_type", kind)).model_dump()  # type: ignore[arg-type]
    with state.lock(SCRAPE_LOCK_KEY, timeout_sec=settings.resolve_timeout_sec, lease_sec=600):
        provider = make_provider(settings, state)
        try:
            if kind == "short_url":
                return resolve_url(payload["url"], provider).model_dump()
            res = resolve_by_name(
                payload["query"], provider, cache, settings,
                brand=payload.get("brand"), force_selection=bool(payload.get("force_selection")),
                input_type=payload.get("input_type", "query"),
            )
            return res.model_dump()
        except BlockedError as e:
            cooldown.start(e.signal)
            return ResolveResult(status="blocked", input_type=payload.get("input_type", "query")).model_dump()  # type: ignore[arg-type]
        except RealstarError as e:
            # 워커 경계(Celery)를 넘을 수 있게 직렬화 가능한 형태로 돌려준다
            return {"_error": {"code": e.code, "message": e.user_message, "detail": e.detail}}
        finally:
            provider.close()


COOLDOWN_SEARCH_MESSAGE = "쿠팡이 잠시 자동 접근을 막아 검색을 쉬고 있어요. 이미 수집한 상품 중에는 없어요. 잠시 후 다시 시도해 주세요."


class _LocalOnly:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    def search(self, query: str) -> list[Any]:
        return self.provider.local_search(query)  # type: ignore[no-any-return]


class _NoCache:
    def get(self, query_norm: str, ttl_hours: int) -> None:
        return None

    def put(self, query_norm: str, candidates: list[Any]) -> None:
        return None


def _raise_if_error(d: dict[str, Any]) -> dict[str, Any]:
    if "_error" in d:
        err = RealstarError(d["_error"].get("detail", ""))
        err.code = d["_error"]["code"]
        err.user_message = d["_error"]["message"]
        raise err
    return d


class _NoBrowserProvider:
    def search(self, query: str) -> list[Any]:
        raise ScraperBusyError("search cache expired")


class Dispatcher(Protocol):
    def enqueue_analysis(self, analysis_id: str) -> None: ...
    def browser_resolve(self, kind: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]: ...


class InlineDispatcher:
    """Redis·Celery 없이 같은 프로세스에서 실행(개발·발표 로컬·테스트).

    수집 스레드는 1개(브라우저 1개), 탐지·집계 스레드는 별도다(README 4장: 수집 대기 중에도 탐지는 진행).
    """

    def __init__(self, settings: Settings, pipeline: AnalysisPipeline | None = None) -> None:
        self.settings = settings
        self.pipeline = pipeline or AnalysisPipeline(settings)
        self.scrape_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scrape")
        self.detect_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="detect")
        self.futures: list[Future[Any]] = []
        self._lock = threading.Lock()

    def enqueue_analysis(self, analysis_id: str) -> None:
        def _collect() -> None:
            if self.pipeline.collect(analysis_id):
                with self._lock:
                    self.futures.append(self.detect_pool.submit(self.pipeline.detect_and_aggregate, analysis_id))

        with self._lock:
            self.futures.append(self.scrape_pool.submit(_collect))

    def browser_resolve(self, kind: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        fut = self.scrape_pool.submit(run_browser_resolve, self.settings, kind, payload)
        try:
            return fut.result(timeout=timeout)
        except FutureTimeout as e:
            raise ScraperBusyError("resolve timed out waiting for scraper") from e

    def wait_all(self, timeout: float = 60) -> None:
        """테스트용: 대기 중인 작업이 끝날 때까지 기다린다."""
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                pending = [f for f in self.futures if not f.done()]
            if not pending:
                return
            for f in pending:
                f.result(timeout=max(0.1, deadline - time.time()))


def make_dispatcher(settings: Settings) -> Dispatcher:
    if settings.task_backend == "celery":
        from realstar_worker.dispatch import CeleryDispatcher  # apps/worker

        return CeleryDispatcher(settings)
    return InlineDispatcher(settings)


def _bucket_thresholds(th: dict[str, Any] | None, bucket: str | None) -> dict[str, float] | None:
    """manifest 임계값은 길이 구간별({S, M, L, ALL} → {T_AI, T_HUMAN}) 또는 하나({T_AI, T_HUMAN})다."""
    if not th:
        return None
    t = th.get(bucket or "") or th.get("ALL") or th
    try:
        return {"T_AI": float(t["T_AI"]), "T_HUMAN": float(t["T_HUMAN"])}
    except (KeyError, TypeError, ValueError):
        return None


class RealstarService:
    def __init__(self, settings: Settings, dispatcher: Dispatcher) -> None:
        self.settings = settings
        self.dispatcher = dispatcher
        self.cache = repo.DbSearchCache(settings.database_url)
        self._detector: DetectorBackend | None = None

    # ── 리뷰 직접 판별 (/api/detect) ──────────────────────
    def detector(self) -> DetectorBackend:
        """분석 파이프라인과 같은 판별기. 같은 프로세스에 파이프라인이 있으면(inline) 이미 올린 모델을 같이 쓴다."""
        pipe = getattr(self.dispatcher, "pipeline", None)
        if pipe is not None:
            return pipe.detector  # type: ignore[no-any-return]
        if self._detector is None:
            s = self.settings
            self._detector = make_backend(
                s.detector_mode, detector_url=s.detector_url, artifact_path=s.model_artifact_path,
                min_chars=s.min_chars, timeout=s.detector_timeout_sec, artifact_url=s.model_artifact_url,
            )
        return self._detector

    def check_reviews(self, reviews: list[dict[str, Any]]) -> dict[str, Any]:
        """사용자가 입력한 리뷰 글을 그대로 판별한다. 글은 저장하지 않는다(DB·로그 모두)."""
        det = self.detector()
        info = det.info()
        if not info.ready:
            hint = {"none": "서버 설정(DETECTOR_MODE)에서 판별 모델이 꺼져 있어요."}.get(self.settings.detector_mode, "")
            raise DetectorUnavailableError(
                info.error or "detector not ready",
                user_message=("AI 판별 모델이 아직 연결되지 않아 리뷰를 판별할 수 없어요. " + hint).strip(),
            )
        items = [
            DetectInput(review_id=f"input-{i}", title=(r.get("title") or None), content=r["text"], star=r.get("star"))
            for i, r in enumerate(reviews)
        ]
        outs = det.predict(items, batch_size=32)
        min_chars = info.min_chars or self.settings.min_chars
        results = []
        for i, (r, o) in enumerate(zip(reviews, outs, strict=True)):
            n = int((o.features or {}).get("len_chars") or len(r["text"].strip()))
            results.append({
                "index": i, "label": o.label, "p_ai": o.p_ai, "len_chars": n, "too_short": n < min_chars,
                "thresholds": _bucket_thresholds(info.thresholds, o.len_bucket), "reason_tags": o.reason_tags,
            })
        return {
            "model": {"version": info.model_version, "is_dummy": info.is_dummy, "min_chars": min_chars},
            "results": results,
        }

    # ── 상품 식별 (/api/resolve) ──────────────────────────
    def resolve_link(self, text: str) -> ResolveResult:
        url, parsed = classify(text)
        if parsed is not None:
            res = resolve_url(url, None)  # 정규식만으로 추출: 브라우저를 열지 않는다
        else:
            res = ResolveResult.model_validate(_raise_if_error(self.dispatcher.browser_resolve("short_url", {"url": url}, self.settings.resolve_timeout_sec)))
        return self._enrich_from_db(res)

    def search(self, query: str, *, brand: str | None = None, force_selection: bool = False, input_type: str = "query") -> ResolveResult:
        if len(normalize_query(query)) < 2:
            raise InvalidInputError("query too short", "상품명을 두 글자 이상 입력해 주세요.")
        # 검색 캐시가 있으면 브라우저 없이 바로 답한다(resolve_by_name이 캐시를 먼저 본다)
        if self.cache.get(normalize_query(query), self.settings.cache_ttl_hours) is not None:
            return resolve_by_name(query, _NoBrowserProvider(), self.cache, self.settings, brand=brand,  # type: ignore[arg-type]
                                   force_selection=force_selection, input_type=input_type)
        payload = {"query": query, "brand": brand, "force_selection": force_selection, "input_type": input_type}
        return ResolveResult.model_validate(_raise_if_error(self.dispatcher.browser_resolve("query", payload, self.settings.resolve_timeout_sec)))

    def resolve_image(self, data: bytes) -> ResolveResult:
        from realstar.resolver.image import resolve_by_image
        from realstar.vision.ocr import get_ocr_engine
        from realstar.vision.vlm import get_vlm

        ocr = get_ocr_engine(self.settings.ocr_engine)
        vlm = get_vlm(self.settings.vlm_enabled, self.settings.vlm_model_path)
        if not ocr.available and not vlm.available:
            from realstar.errors import VisionUnavailableError

            raise VisionUnavailableError(getattr(ocr, "reason", "OCR unavailable"))

        def search(q: str, brand: str | None, force: bool) -> ResolveResult:
            return self.search(q, brand=brand, force_selection=force, input_type="image")

        return resolve_by_image(data, search, self.settings, ocr, vlm)

    def _enrich_from_db(self, res: ResolveResult) -> ResolveResult:
        """이미 수집한 상품이면 이름·썸네일을 채운다(추가 페이지 로드 없음)."""
        if not res.candidates:
            return res
        with session_scope(self.settings.database_url) as s:
            for c in res.candidates:
                p = s.get(Product, c.product_id)
                if p is not None:
                    c.name = c.name or p.name
                    c.image_url = c.image_url or p.image_url
        return res

    # ── 분석 (/api/analyses) ──────────────────────────────
    def start_analysis(self, product_id: str, *, force_refresh: bool = False, input_: dict[str, Any] | None = None) -> dict[str, Any]:
        if not product_id.isdigit():
            raise InvalidInputError("bad product_id", "상품 번호가 올바르지 않아요.")
        with session_scope(self.settings.database_url) as s:
            if not force_refresh:
                done = repo.latest_done_analysis(s, product_id, self.settings.cache_ttl_hours)
                if done is not None:
                    return {"analysis_id": done.analysis_id, "status": "done", "queue_position": 0, "cached": True}
            active = repo.active_analysis(s, product_id)
            if active is not None:
                return {"analysis_id": active.analysis_id, "status": active.status, "queue_position": repo.queue_position(s, active), "cached": False}
            a = repo.create_analysis(s, product_id, force_refresh=force_refresh, input_=input_)
            analysis_id = a.analysis_id
            pos = repo.queue_position(s, a)
        self.dispatcher.enqueue_analysis(analysis_id)
        return {"analysis_id": analysis_id, "status": "queued", "queue_position": pos, "cached": False}

    # ── 수집한 상품·리뷰 (/api/products) ──────────────────────
    def list_products(self, limit: int = 60) -> list[dict[str, Any]]:
        """수집을 마친 상품 목록: 수집기 output/ 파일 + DB(이 서비스로 분석한 상품)."""
        from sqlalchemy import select

        items: dict[str, dict[str, Any]] = {}
        if self.settings.review_provider == "crawler":
            from realstar.collectors.crawler_provider import list_collected

            for it in list_collected(self.settings):
                items[it["product_id"]] = {**it, "source": "crawler_file"}
        with session_scope(self.settings.database_url) as s:
            for p in s.scalars(select(Product).where(Product.reviews_fetched_at.is_not(None))).all():
                cur = items.get(p.product_id)
                counts = {int(k): int(v) for k, v in (p.star_counts or {}).items()}
                n = sum(counts.values())
                base = cur or {
                    "product_id": p.product_id, "name": p.name, "image_url": p.image_url, "url": p.url,
                    "total_reviews": p.total_reviews or 0,
                    "collected_reviews": len(repo.get_reviews(s, p.product_id)),
                    "collected_at": (p.sampling or {}).get("collected_at"),
                    "complete": (p.sampling or {}).get("complete", True),
                    "avg_all": round(sum(k * v for k, v in counts.items()) / n, 2) if n else None,
                    "source": "db",
                }
                base["image_url"] = base.get("image_url") or p.image_url
                done = repo.latest_done_analysis(s, p.product_id, self.settings.cache_ttl_hours)
                base["analysis_id"] = done.analysis_id if done is not None else None
                items[p.product_id] = base
        out = sorted(items.values(), key=lambda x: x.get("collected_at") or "", reverse=True)
        return out[:limit]

    def list_reviews(self, product_id: str, *, star: int | None, offset: int, limit: int, model_version: str | None = None) -> dict[str, Any]:
        from sqlalchemy import func, select

        from realstar.db.models import Prediction, Review

        with session_scope(self.settings.database_url) as s:
            q = select(Review).where(Review.product_id == product_id)
            cq = select(func.count()).select_from(Review).where(Review.product_id == product_id)
            if star is not None:
                q, cq = q.where(Review.star == star), cq.where(Review.star == star)
            total = int(s.scalar(cq) or 0)
            rows = s.scalars(q.order_by(Review.star.desc(), Review.created_at.desc(), Review.review_id).offset(offset).limit(limit)).all()
            preds: dict[str, Prediction] = {}
            if model_version and rows:
                preds = {p.review_id: p for p in s.scalars(select(Prediction).where(
                    Prediction.review_id.in_([r.review_id for r in rows]), Prediction.model_version == model_version)).all()}
            items = [
                {
                    "review_id": r.review_id, "star": r.star, "title": r.title, "content": r.content,
                    "created_at": r.created_at, "has_photo": r.has_photo, "option_name": r.option_name,
                    "len_chars": r.len_chars or len(r.content or ""),
                    "is_sponsored": bool(r.is_sponsored or r.is_cash_event),
                    "label": preds[r.review_id].label if r.review_id in preds else None,
                    "p_ai": preds[r.review_id].p_ai if r.review_id in preds else None,
                }
                for r in rows
            ]
        return {"product_id": product_id, "star": star, "total": total, "offset": offset, "limit": limit, "items": items}

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with session_scope(self.settings.database_url) as s:
            a = s.get(Analysis, analysis_id)
            if a is None:
                return None
            return self.view(s, a)

    @staticmethod
    def view(s: Any, a: Analysis) -> dict[str, Any]:
        progress = dict(a.progress or {})
        if a.status == "queued":
            progress["queue_position"] = repo.queue_position(s, a)
        return {
            "analysis_id": a.analysis_id,
            "product_id": a.product_id,
            "status": a.status,
            "progress": progress,
            "result": a.result if a.status == "done" else None,
            "error": a.error,
            "cached": a.cached,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "finished_at": a.finished_at.isoformat() if a.finished_at else None,
        }
