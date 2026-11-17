"""분석 파이프라인: 수집 → 전처리 → AI 작성 탐지 → 집계 (README 2장, 4장).

수집 단계(`collect`)와 탐지·집계 단계(`detect_and_aggregate`)를 분리한다.
Celery에서는 각각 `scrape` 큐(동시성 1)와 `detect` 큐에서 돈다. 수집은 전역 락으로 한 번에 1개만 실행한다.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any

from realstar.aggregate.stats import STARS, StarSample, compute_ratings
from realstar.aggregate.topk import TopCandidate, select_top_k
from realstar.collectors import make_provider
from realstar.collectors.base import CollectProgress, ProductMeta, RawReview, ReviewProvider
from realstar.config import Settings
from realstar.db import repository as repo
from realstar.db.models import Analysis, Product
from realstar.db.session import session_scope
from realstar.detection import preprocess
from realstar.detection.backends import DetectorBackend, make_backend
from realstar.detection.schemas import DetectInput, ModelInfo
from realstar.errors import (
    BlockedError,
    DetectorUnavailableError,
    ForbiddenAreaError,
    PageBudgetExceededError,
    ParserBrokenError,
    RealstarError,
)
from realstar.pipeline.result_schema import AnalysisResult
from realstar.state.store import SCRAPE_LOCK_KEY, Cooldown, StateStore, get_state_store

log = logging.getLogger(__name__)

STAGES = ["resolve", "collect", "detect", "aggregate"]
FIXED_ASSUMPTIONS = [
    "판단 보류 리뷰는 판정된 리뷰와 사람 비율이 같다고 가정하고 계산에서 제외했어요.",
    "사람 리뷰 기준 별점은 별점별 표본에서 추정한 사람 비율을 상품 전체 별점 분포에 반영해 계산했어요.",
]


def _thresholds_flat(info: ModelInfo) -> tuple[float | None, float | None]:
    t = info.thresholds or {}
    if "T_AI" in t:
        return t.get("T_AI"), t.get("T_HUMAN")
    mid = t.get("M") or (next(iter(t.values())) if t else None)
    if isinstance(mid, dict):
        return mid.get("T_AI"), mid.get("T_HUMAN")
    return None, None


class AnalysisPipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        state: StateStore | None = None,
        provider_factory: Callable[[], ReviewProvider] | None = None,
        detector: DetectorBackend | None = None,
        lock_timeout_sec: float = 6 * 3600,
    ) -> None:
        self.settings = settings
        self.db = settings.database_url
        self.state = state or get_state_store(settings)
        self.cooldown = Cooldown(self.state, settings.block_cooldown_min)
        self.provider_factory = provider_factory or (lambda: make_provider(settings, self.state))
        self._detector = detector
        self.lock_timeout_sec = lock_timeout_sec

    @property
    def detector(self) -> DetectorBackend:
        if self._detector is None:
            s = self.settings
            self._detector = make_backend(
                s.detector_mode, detector_url=s.detector_url, artifact_path=s.model_artifact_path,
                min_chars=s.min_chars, timeout=s.detector_timeout_sec, artifact_url=s.model_artifact_url,
            )
        return self._detector

    # ── 상태 갱신 ──────────────────────────────────────────
    def _set(self, analysis_id: str, **fields: Any) -> None:
        repo.update_analysis(self.db, analysis_id, **fields)

    def _progress(self, analysis_id: str, **progress: Any) -> None:
        repo.merge_progress(self.db, analysis_id, **progress)

    def _fail(self, analysis_id: str, status: str, err: RealstarError, extra: dict[str, Any] | None = None) -> None:
        error = {"code": err.code, "message": err.user_message, "detail": err.detail}
        error.update(extra or {})
        print(f"[분석 {analysis_id}] {status}: {err.code} · {err.detail or err.user_message}", flush=True)
        with session_scope(self.db) as s:
            a = s.get(Analysis, analysis_id)
            if a is None:
                return
            cached = repo.latest_done_analysis(s, a.product_id)
            if cached is not None and cached.analysis_id != analysis_id:
                error["cached_analysis_id"] = cached.analysis_id
                error["cached_collected_at"] = (cached.result or {}).get("sampling", {}).get("collected_at")
            a.status = status
            a.error = error
            a.finished_at = repo.now_utc()
            prog = dict(a.progress or {})
            prog["stage"] = status
            a.progress = prog

    def _eta(self, remaining_pages: int) -> int:
        if self.settings.review_provider == "crawler":
            return int(remaining_pages * 3.5) + 15  # 수집기: API 호출 사이 1.5~3.5초 대기 + 응답 시간
        return int(remaining_pages * 2.0) + 10

    def _sample_sort(self) -> str:
        if self.settings.review_provider == "crawler":
            from realstar.collectors.crawler_provider import CRAWLER_SORT

            return CRAWLER_SORT
        return self.settings.review_sort

    # ── 1단계: 수집 ──────────────────────────────────────
    def collect(self, analysis_id: str) -> bool:
        """True면 탐지·집계로 넘어간다."""
        with session_scope(self.db) as s:
            a = s.get(Analysis, analysis_id)
            if a is None:
                return False
            product_id, force = a.product_id, a.force_refresh
            if not force and repo.cached_product(s, product_id, self.settings.cache_ttl_hours, self.settings.sample_per_star, self._sample_sort()):
                a.progress = {**(a.progress or {}), "stage": "collect", "from_cache": True, "message": "저장된 리뷰 표본을 사용해요"}
                return True

        if not force and self._saved_file_reusable(product_id):
            # 이미 수집해 둔 파일: 브라우저를 열지 않으므로 차단 쿨다운·수집 락과 무관하게 바로 처리한다
            return self._collect_locked(analysis_id, product_id)

        st = self.cooldown.status()
        if st:
            self._fail(analysis_id, "blocked", BlockedError("cooldown"), {"cooldown_until": st["until"]})
            return False

        with self.state.lock(SCRAPE_LOCK_KEY, timeout_sec=self.lock_timeout_sec, lease_sec=3 * 3600):
            # 락을 기다리는 동안 다른 작업이 차단됐을 수 있다
            st = self.cooldown.status()
            if st:
                self._fail(analysis_id, "blocked", BlockedError("cooldown"), {"cooldown_until": st["until"]})
                return False
            return self._collect_locked(analysis_id, product_id)

    def _collect_locked(self, analysis_id: str, product_id: str) -> bool:
        started = repo.now_utc()
        self._set(analysis_id, status="collecting")
        self._progress(analysis_id, stage="collect", message="상품 정보를 확인하고 있어요")
        provider = self.provider_factory()
        collected: dict[int, list[RawReview]] = {}
        meta: ProductMeta | None = None
        outcome: str = "ok"
        detail: dict[str, Any] = {}
        try:
            if hasattr(provider, "collect_all"):
                return self._collect_with_crawler(analysis_id, product_id, provider)
            meta = provider.get_product_meta(product_id)
            counts = meta.resolved_star_counts() if meta.total_reviews else dict.fromkeys(STARS, 0)
            with session_scope(self.db) as s:
                repo.upsert_product(s, meta, counts)
            targets = {s_: min(self.settings.sample_per_star, counts.get(s_, 0)) for s_ in STARS}
            page_size = 10
            stars_prog = {str(s_): {"collected": 0, "target": targets[s_], "total": counts.get(s_, 0), "status": "pending"} for s_ in STARS}
            self._progress(
                analysis_id,
                product={"product_id": product_id, "name": meta.name, "image_url": meta.image_url},
                stars=stars_prog,
                eta_seconds=self._eta(sum(math.ceil(t / page_size) for t in targets.values())),
                message="리뷰를 모으고 있어요",
            )
            for star in STARS:
                if targets[star] == 0:
                    self._progress(analysis_id, stars={str(star): {"status": "skipped"}})
                    collected[star] = []
                    continue
                self._progress(analysis_id, current_star=star, stars={str(star): {"status": "collecting"}})

                def on_progress(p: CollectProgress, _star: int = star) -> None:
                    remaining = sum(math.ceil((targets[x] - (p.collected if x == _star else 0)) / page_size) for x in STARS if x <= _star)
                    self._progress(
                        analysis_id,
                        pages_loaded=p.pages_loaded,
                        stars={str(_star): {"collected": p.collected}},
                        eta_seconds=self._eta(remaining),
                        message=f"{_star}점 리뷰 수집 중 {p.collected}/{targets[_star]}",
                    )

                reviews = provider.get_reviews(product_id, star, targets[star], sort=self.settings.review_sort, on_progress=on_progress)
                collected[star] = reviews
                self._progress(analysis_id, stars={str(star): {"collected": len(reviews), "status": "done"}}, pages_loaded=provider.pages_loaded)
            all_reviews = [r for s_ in STARS for r in collected[s_]]
            sampling = {
                "per_star_limit": self.settings.sample_per_star,
                "sort": self.settings.review_sort,
                "collected_at": repo.now_utc().isoformat(),
                "pages_loaded": provider.pages_loaded,
                "selectors_version": getattr(provider, "selectors_version", None),
            }
            with session_scope(self.db) as s:
                repo.replace_reviews(s, product_id, all_reviews)
                repo.mark_reviews_fetched(s, product_id, sampling)
            return True
        except BlockedError as e:
            outcome, detail = "blocked", {"signal": e.signal, "detail": e.detail}
            until = self.cooldown.start(e.signal)
            partial = {str(k): len(v) for k, v in collected.items()}
            # 부분 결과는 디버깅용으로만 남기고 결과를 만들지 않는다(README 5.4 예외 처리)
            self._fail(analysis_id, "blocked", e, {"cooldown_until": until.isoformat(), "partial_counts": partial})
            return False
        except ParserBrokenError as e:
            outcome, detail = "parser_broken", {"page": e.page, "failed_selectors": e.failed_selectors}
            log.error("parser broken: %s %s", e.page, e.failed_selectors)
            self._fail(analysis_id, "failed", e, {"failed_selectors": e.failed_selectors})
            return False
        except (PageBudgetExceededError, ForbiddenAreaError) as e:
            outcome, detail = "error", {"code": e.code, "detail": e.detail}
            self._fail(analysis_id, "failed", e)
            return False
        except RealstarError as e:
            outcome, detail = "error", {"code": e.code, "detail": e.detail}
            self._fail(analysis_id, "failed", e)
            return False
        except Exception as e:
            log.exception("collect failed")
            outcome, detail = "error", {"exception": type(e).__name__, "detail": str(e)[:500]}
            self._fail(analysis_id, "failed", RealstarError(f"{type(e).__name__}: {e}"[:400]))
            return False
        finally:
            with session_scope(self.db) as s:
                repo.add_scrape_log(s, product_id, started, provider.pages_loaded, outcome, detail)
            provider.close()

    def _saved_file_reusable(self, product_id: str) -> bool:
        if self.settings.review_provider != "crawler":
            return False
        from realstar.collectors.crawler_provider import CrawlerProvider

        prov = CrawlerProvider(self.settings)
        return prov.reusable(prov.load_saved(product_id))

    @staticmethod
    def _source_url(inp: Any, product_id: str) -> str | None:
        """요청에 실린 원래 상품 링크(옵션 itemId 포함)가 같은 상품이면 그 링크로 수집한다."""
        from realstar.resolver.url import parse_product_url

        if not isinstance(inp, dict):
            return None
        for key in ("url", "query"):
            v = inp.get(key)
            if isinstance(v, str) and v.startswith("http"):
                parsed = parse_product_url(v)
                if parsed is not None and parsed.product_id == product_id:
                    return v
        return None

    # ── 1단계(수집기): coupang_reviews.py 실행 + 진행 이벤트 반영 ──────────
    def _collect_with_crawler(self, analysis_id: str, product_id: str, provider: Any) -> bool:
        from realstar.collectors.crawler_provider import meta_from_file, reviews_from_file

        page_size = 10
        per_star = self.settings.sample_per_star
        st: dict[str, Any] = {"targets": {}, "collected": {}, "logs": [], "last_write": 0.0}
        with session_scope(self.db) as s:
            a = s.get(Analysis, analysis_id)
            assert a is not None
            force = a.force_refresh
            url = self._source_url(a.input, product_id)
        try:
            detection_ready = bool(self.detector.info().ready)
        except Exception:
            detection_ready = False
        self._progress(analysis_id, started_at=repo.now_utc().isoformat(), crawl_stage="start",
                       message="리뷰 수집을 준비하고 있어요", logs=[],
                       detection_available=detection_ready or not self.settings.detection_fallback)

        def remaining_pages() -> int:
            n = 0
            for s_ in STARS:
                t = st["targets"].get(s_)
                if t is None:
                    t = per_star
                n += math.ceil(max(0, t - st["collected"].get(s_, 0)) / page_size)
            return n

        def on_event(evt: dict[str, Any]) -> None:
            import time as _time

            kind = evt.get("type")
            if kind == "reuse":
                self._progress(analysis_id, crawl_stage="reuse", from_saved_file=True,
                               message="이미 수집해 둔 리뷰 파일을 불러오고 있어요")
            elif kind == "stage":
                self._progress(analysis_id, crawl_stage=evt.get("stage"), message=evt.get("message"))
            elif kind == "product":
                prod = {"product_id": product_id}
                if evt.get("name"):
                    prod["name"] = evt["name"]
                if evt.get("image_url"):
                    prod["image_url"] = evt["image_url"]
                self._progress(analysis_id, product=prod)
            elif kind == "summary":
                counts = {int(k): int(v or 0) for k, v in (evt.get("rating_counts") or {}).items()}
                stars: dict[str, Any] = {}
                for s_ in STARS:
                    if s_ in counts:
                        st["targets"][s_] = min(per_star, counts[s_])
                    stars[str(s_)] = {
                        "collected": 0, "target": st["targets"].get(s_, per_star), "total": counts.get(s_, 0),
                        "status": "skipped" if counts.get(s_) == 0 else "pending",
                    }
                self._progress(analysis_id, stars=stars, total_reviews=evt.get("total"),
                               eta_seconds=self._eta(remaining_pages()), message="별점별 리뷰를 모으고 있어요")
            elif kind == "star_start":
                s_ = int(evt["star"])
                st["targets"][s_] = int(evt.get("target") or 0)
                self._progress(analysis_id, current_star=s_,
                               stars={str(s_): {"status": "collecting", "target": st["targets"][s_]}},
                               message=f"{s_}점 리뷰를 모으고 있어요")
            elif kind == "page":
                s_ = int(evt["star"])
                st["collected"][s_] = int(evt.get("collected") or 0)
                if evt.get("target"):
                    st["targets"][s_] = int(evt["target"])
                now = _time.monotonic()
                if now - st["last_write"] < 0.8:  # DB 쓰기를 너무 자주 하지 않는다
                    return
                st["last_write"] = now
                self._progress(
                    analysis_id, pages_loaded=evt.get("pages_loaded"),
                    stars={str(s_): {"collected": st["collected"][s_], "target": st["targets"].get(s_, 0)}},
                    eta_seconds=self._eta(remaining_pages()),
                    message=f"{s_}점 리뷰 수집 중 {st['collected'][s_]}/{st['targets'].get(s_, 0)}",
                )
            elif kind == "star_done":
                s_ = int(evt["star"])
                got, tgt = int(evt.get("collected") or 0), int(evt.get("target") or 0)
                st["collected"][s_], st["targets"][s_] = got, tgt
                self._progress(analysis_id, stars={str(s_): {"collected": got, "target": tgt,
                                                             "status": "done" if got >= tgt else "partial"}},
                               eta_seconds=self._eta(remaining_pages()))
            elif kind == "log":
                msg = str(evt.get("message") or "").strip()
                if not msg:
                    return
                st["logs"] = (st["logs"] + [{"at": repo.now_utc().isoformat(), "message": msg[:200]}])[-8:]
                self._progress(analysis_id, logs=st["logs"])

        data = provider.collect_all(product_id, url, force=force, on_event=on_event)
        meta = meta_from_file(data)
        meta.product_id = meta.product_id or product_id
        reviews = reviews_from_file(data)
        counts = meta.resolved_star_counts() if meta.total_reviews else dict.fromkeys(STARS, 0)
        info = data.get("상품정보") or {}
        with session_scope(self.db) as s:
            repo.upsert_product(s, meta, counts)
        by_star = {s_: [r for r in reviews if r.star == s_][:per_star] for s_ in STARS}
        self._progress(
            analysis_id,
            product={"product_id": product_id, "name": meta.name, "image_url": meta.image_url},
            stars={str(s_): {"collected": len(by_star[s_]), "target": min(per_star, counts.get(s_, 0)) or len(by_star[s_]),
                             "total": counts.get(s_, 0), "status": "done" if counts.get(s_, 0) else "skipped"} for s_ in STARS},
            eta_seconds=0, crawl_stage="saved", message="수집한 리뷰를 저장하고 있어요",
        )
        from realstar.collectors.crawler_provider import parse_collected_at

        collected_at = parse_collected_at(info.get("수집_시각"))
        sampling = {
            "per_star_limit": per_star,
            "sort": self._sample_sort(),
            "collected_at": (collected_at or repo.now_utc()).isoformat(),
            "pages_loaded": provider.pages_loaded,
            "selectors_version": getattr(provider, "selectors_version", None),
            "complete": bool(info.get("수집_완료", True)),
            "shortfalls": info.get("목표_미달") or {},
        }
        with session_scope(self.db) as s:
            repo.replace_reviews(s, product_id, [r for s_ in STARS for r in by_star[s_]])
            repo.mark_reviews_fetched(s, product_id, sampling)
        return True

    # ── 2단계: 탐지 + 집계 ──────────────────────────────────
    def detect_and_aggregate(self, analysis_id: str) -> None:
        try:
            self._detect_and_aggregate(analysis_id)
        except DetectorUnavailableError as e:
            self._fail(analysis_id, "failed", e)
        except RealstarError as e:
            self._fail(analysis_id, "failed", e)
        except Exception as e:
            log.exception("detect/aggregate failed")
            self._fail(analysis_id, "failed", RealstarError(f"{type(e).__name__}: {e}"[:400]))

    def _detect_and_aggregate(self, analysis_id: str) -> None:
        self._set(analysis_id, status="detecting")
        self._progress(analysis_id, stage="detect", message="AI 작성 여부를 판별하고 있어요")
        info = self.detector.info()
        if not info.ready:
            if not self.settings.detection_fallback:
                raise DetectorUnavailableError(info.error or "detector not ready")
            self._finish_without_detection(analysis_id, info)
            return
        version = info.model_version or "unknown"
        min_chars = max(self.settings.min_chars, info.min_chars or 0)

        with session_scope(self.db) as s:
            a = s.get(Analysis, analysis_id)
            assert a is not None
            product = s.get(Product, a.product_id)
            assert product is not None
            rows = repo.get_reviews(s, a.product_id)
            # 전처리(model 패키지의 clean_review) + 중복 그룹
            pre_source = "passthrough"
            for r in rows:
                c = preprocess.clean(r.title, r.content)
                r.clean_text, r.len_chars = c.clean_text, c.len_chars
                r.is_sponsored, r.is_cash_event = c.is_sponsored, c.is_cash_event
                pre_source = c.source
            groups, dedup_source = preprocess.assign_dup_groups([r.clean_text or r.content for r in rows])
            for r, g in zip(rows, groups, strict=True):
                r.dup_group_id = g
            review_data: list[dict[str, Any]] = [
                {
                    "review_id": r.review_id, "star": r.star, "title": r.title, "content": r.content,
                    "created_at": r.created_at, "has_photo": r.has_photo, "len_chars": r.len_chars or 0,
                    "dup_group_id": r.dup_group_id, "is_sponsored": r.is_sponsored, "is_cash_event": r.is_cash_event,
                }
                for r in rows
            ]
            cached_preds = repo.get_predictions(s, [r.review_id for r in rows], version)
            preds: dict[str, dict[str, Any]] = {
                rid: {"p_ai": p.p_ai, "label": p.label, "reason_tags": (p.features or {}).get("_reason_tags", [])}
                for rid, p in cached_preds.items()
            }
            product_info: dict[str, Any] = {
                "product_id": product.product_id, "name": product.name, "image_url": product.image_url, "url": product.url,
                "displayed_avg": product.displayed_avg, "total_reviews": product.total_reviews or 0,
                "star_counts": {int(k): int(v) for k, v in (product.star_counts or {}).items()},
                "sampling": dict(product.sampling or {}), "category": product.category,
            }
            from_cache = bool((a.progress or {}).get("from_cache"))

        todo = [d for d in review_data if d["review_id"] not in preds]
        total = len(review_data)
        self._progress(analysis_id, detected=total - len(todo), detect_total=total)
        bs = self.settings.detector_batch_size
        for i in range(0, len(todo), bs):
            batch = todo[i : i + bs]
            outs = self.detector.predict(
                [DetectInput(review_id=d["review_id"], title=d["title"], content=d["content"], star=d["star"], category=product_info["category"]) for d in batch],
                batch_size=bs,
            )
            by_id = {o.review_id: o for o in outs}
            with session_scope(self.db) as s:
                for d in batch:
                    o = by_id.get(d["review_id"])
                    if o is None:
                        raise DetectorUnavailableError(f"missing prediction for {d['review_id']}")
                    feats = dict(o.features)
                    feats["_reason_tags"] = o.reason_tags
                    repo.save_prediction(s, o.review_id, o.model_version or version, o.p_ai, o.label, feats)
                    preds[o.review_id] = {"p_ai": o.p_ai, "label": o.label, "reason_tags": o.reason_tags}
            self._progress(analysis_id, detected=total - len(todo) + i + len(batch))

        self._set(analysis_id, status="aggregating")
        self._progress(analysis_id, stage="aggregate", message="별점을 다시 계산하고 있어요")
        result = self._build_result(analysis_id, product_info, review_data, preds, info, version, min_chars, pre_source, dedup_source, from_cache)
        with session_scope(self.db) as s:
            a = s.get(Analysis, analysis_id)
            assert a is not None
            a.result = result
            a.status = "done"
            a.model_version = version
            a.finished_at = repo.now_utc()
            a.cached = from_cache
            a.progress = {**(a.progress or {}), "stage": "done", "message": "분석이 끝났어요"}

    # ── 2단계(모델 없음): AI 판별을 건너뛰고 수집 결과만 정리 ───────────────
    def _finish_without_detection(self, analysis_id: str, info: ModelInfo) -> None:
        self._progress(analysis_id, stage="aggregate", detection_available=False,
                       message="AI 판별 모델이 아직 없어 수집 결과만 정리하고 있어요")
        with session_scope(self.db) as s:
            a = s.get(Analysis, analysis_id)
            assert a is not None
            product = s.get(Product, a.product_id)
            assert product is not None
            rows = repo.get_reviews(s, a.product_id)
            pre = [preprocess.clean(r.title, r.content) for r in rows]
            for r, c in zip(rows, pre, strict=True):
                r.clean_text, r.len_chars = c.clean_text, c.len_chars
                r.is_sponsored, r.is_cash_event = c.is_sponsored, c.is_cash_event
            N = {s_: int((product.star_counts or {}).get(str(s_), 0)) for s_ in STARS}
            by_star: dict[int, list[Any]] = {s_: [r for r in rows if r.star == s_] for s_ in STARS}
            sampling = dict(product.sampling or {})
            from_cache = bool((a.progress or {}).get("from_cache"))
            prod = {"product_id": product.product_id, "name": product.name, "image_url": product.image_url, "url": product.url}
            displayed_avg, total_reviews = product.displayed_avg, product.total_reviews or 0
            flags = {
                "sponsored_count": sum(1 for r in rows if r.is_sponsored),
                "cash_event_count": sum(1 for r in rows if r.is_cash_event),
                "near_duplicate_groups": 0,
            }
            per_star_out: dict[str, Any] = {}
            review_stats: dict[str, Any] = {}
            for s_ in STARS:
                lst = by_star[s_]
                per_star_out[str(s_)] = {"total": N[s_], "collected": len(lst), "human": 0, "ai": 0, "uncertain": 0,
                                         "human_ratio": None, "ratio_substituted": False}
                lens = [r.len_chars or len(r.content or "") for r in lst]
                review_stats[str(s_)] = {
                    "collected": len(lst),
                    "avg_chars": round(sum(lens) / len(lens), 1) if lens else None,
                    "photo_count": sum(1 for r in lst if r.has_photo),
                    "sponsored_count": sum(1 for r in lst if r.is_sponsored or r.is_cash_event),
                }

        n_all = sum(N.values())
        avg_all = sum(s_ * n for s_, n in N.items()) / n_all if n_all else None
        warnings: list[dict[str, Any]] = [{
            "code": "detection_unavailable", "level": "info",
            "message": "AI 판별 모델이 아직 연결되지 않아 사람 리뷰 기준 별점과 AI 리뷰 비중은 계산하지 않았어요. "
                       "수집한 리뷰와 별점 분포는 그대로 볼 수 있어요.",
        }]
        if n_all == 0:
            warnings.append({"code": "no_reviews", "level": "info", "message": "아직 리뷰가 없는 상품이에요."})
        if displayed_avg is not None and avg_all is not None and abs(displayed_avg - avg_all) > self.settings.displayed_avg_warn_gap:
            warnings.append({"code": "displayed_avg_mismatch", "level": "info",
                             "message": f"쿠팡 표시 평균(★{displayed_avg:.1f})과 별점 분포로 계산한 평균(★{avg_all:.2f})이 달라요."})
        if sampling.get("complete") is False:
            short = ", ".join(f"{k} {v}" for k, v in (sampling.get("shortfalls") or {}).items())
            warnings.append({"code": "collect_partial", "level": "warning",
                             "message": f"일부 별점은 목표만큼 모으지 못했어요({short}). '다시 수집'으로 채울 수 있어요."})
        result = {
            "analysis_id": analysis_id,
            "product": prod,
            "platform_stats": {"displayed_avg": displayed_avg, "total_reviews": total_reviews,
                               "star_counts": {str(s_): N[s_] for s_ in STARS}},
            "sampling": {
                "per_star_limit": sampling.get("per_star_limit", self.settings.sample_per_star),
                "sort": sampling.get("sort", self._sample_sort()),
                "collected_at": sampling.get("collected_at"),
                "pages_loaded": sampling.get("pages_loaded", 0),
                "selectors_version": sampling.get("selectors_version"),
                "from_cache": from_cache,
            },
            "per_star": per_star_out,
            "ratings": {"avg_all": None if avg_all is None else round(avg_all, 4), "avg_human": None, "diff": None,
                        "avg_human_ci95": None, "diff_ci95": None, "ai_share": None, "ai_share_ci95": None, "corrected": None},
            "top_human_reviews": {str(s_): [] for s_ in STARS},
            "flags": flags,
            "warnings": warnings,
            "model": {"version": "none", "T_AI": None, "T_HUMAN": None, "thresholds": None, "is_dummy": False},
            "assumptions": ["전체 평균은 쿠팡이 알려 준 별점별 리뷰 개수로 계산했어요."],
            "detection": {"available": False, "message": info.error or "AI 판별 모델이 아직 연결되지 않았어요."},
            "review_stats": review_stats,
        }
        validated = AnalysisResult.model_validate(result).model_dump()
        with session_scope(self.db) as s:
            a = s.get(Analysis, analysis_id)
            assert a is not None
            a.result = validated
            a.status = "done"
            a.model_version = None
            a.finished_at = repo.now_utc()
            a.cached = from_cache
            a.progress = {**(a.progress or {}), "stage": "done", "message": "수집 결과를 정리했어요"}

    def _build_result(
        self,
        analysis_id: str,
        product: dict[str, Any],
        reviews: list[dict[str, Any]],
        preds: dict[str, dict[str, Any]],
        info: ModelInfo,
        version: str,
        min_chars: int,
        pre_source: str,
        dedup_source: str,
        from_cache: bool,
    ) -> dict[str, Any]:
        labels_by_star: dict[int, list[str]] = {s: [] for s in STARS}
        top_cands: dict[int, list[TopCandidate]] = {s: [] for s in STARS}
        for d in reviews:
            p = preds[d["review_id"]]
            label = p["label"]
            if d["len_chars"] < min_chars:
                label = "uncertain"  # README 5.3-5: 짧은 리뷰는 판단 보류로 강제
            labels_by_star[d["star"]].append(label)
            top_cands[d["star"]].append(
                TopCandidate(
                    review_id=d["review_id"], star=d["star"], p_human=1.0 - float(p["p_ai"]), label=label,
                    len_chars=d["len_chars"], has_photo=d["has_photo"], dup_group_id=d["dup_group_id"],
                    text=d["content"], title=d["title"], created_at=d["created_at"], reason_tags=list(p.get("reason_tags") or []),
                )
            )

        N = {s: int(product["star_counts"].get(s, 0)) for s in STARS}
        sens_spec = (info.sensitivity, info.specificity) if info.sensitivity and info.specificity else None
        rr = compute_ratings(
            N,
            labels_by_star,
            displayed_avg=product["displayed_avg"],
            bootstrap_iterations=self.settings.bootstrap_iterations,
            seed=self.settings.bootstrap_seed,
            min_judged=self.settings.min_judged_per_star,
            displayed_avg_warn_gap=self.settings.displayed_avg_warn_gap,
            sens_spec=sens_spec,  # type: ignore[arg-type]
        )
        warnings = [w.as_dict() for w in rr.warnings]
        substituted = {w["star"] for w in warnings if w["code"] == "star_ratio_substituted"}

        top: dict[str, list[dict[str, Any]]] = {}
        for s in STARS:
            picked = select_top_k(top_cands[s], k=self.settings.top_k, min_chars=self.settings.top_min_chars)
            top[str(s)] = [
                {
                    "review_id": c.review_id, "title": c.title, "text": c.text, "p_human": round(c.p_human, 4),
                    "created_at": c.created_at, "has_photo": c.has_photo, "len_chars": c.len_chars, "reason_tags": c.reason_tags,
                }
                for c in picked
            ]
            if N[s] > 0 and len(picked) < self.settings.top_k:
                warnings.append({"code": "top_insufficient", "level": "info", "star": s,
                                 "message": f"{s}점에서 조건에 맞는 사람 리뷰가 {len(picked)}개뿐이에요."})

        if info.is_dummy:
            warnings.insert(0, {"code": "dummy_detector", "level": "warning",
                                "message": "개발용 더미 판별기로 계산한 결과예요. 실제 AI 작성 여부와 관계없어요."})
        if pre_source != "realstar_model":
            warnings.append({"code": "preprocess_unavailable", "level": "info",
                             "message": "전처리 모듈이 아직 연결되지 않아 상투 문구·체험단 표시를 확인하지 않았어요."})

        per_star_out = {}
        for s in STARS:
            smp: StarSample = rr.per_star[s]
            per_star_out[str(s)] = {
                "total": N[s], "collected": smp.collected, "human": smp.human, "ai": smp.ai, "uncertain": smp.uncertain,
                "human_ratio": None if smp.human_ratio is None else round(smp.human_ratio, 4),
                "ratio_substituted": s in substituted,
            }
        t_ai, t_human = _thresholds_flat(info)
        sampling = product["sampling"]

        def r4(x: float | None) -> float | None:
            return None if x is None else round(x, 4)

        def ci(x: tuple[float, float] | None) -> list[float] | None:
            return None if x is None else [round(x[0], 4), round(x[1], 4)]

        result = {
            "analysis_id": analysis_id,
            "product": {k: product[k] for k in ("product_id", "name", "image_url", "url")},
            "platform_stats": {
                "displayed_avg": product["displayed_avg"], "total_reviews": product["total_reviews"],
                "star_counts": {str(s): N[s] for s in STARS},
            },
            "sampling": {
                "per_star_limit": sampling.get("per_star_limit", self.settings.sample_per_star),
                "sort": sampling.get("sort", self.settings.review_sort),
                "collected_at": sampling.get("collected_at"),
                "pages_loaded": sampling.get("pages_loaded", 0),
                "selectors_version": sampling.get("selectors_version"),
                "from_cache": from_cache,
            },
            "per_star": per_star_out,
            "ratings": {
                "avg_all": r4(rr.avg_all), "avg_human": r4(rr.avg_human), "diff": r4(rr.diff),
                "avg_human_ci95": ci(rr.avg_human_ci95), "diff_ci95": ci(rr.diff_ci95),
                "ai_share": r4(rr.ai_share), "ai_share_ci95": ci(rr.ai_share_ci95), "corrected": rr.corrected,
            },
            "top_human_reviews": top,
            "flags": {
                "sponsored_count": sum(1 for d in reviews if d["is_sponsored"]),
                "cash_event_count": sum(1 for d in reviews if d["is_cash_event"]),
                "near_duplicate_groups": len({d["dup_group_id"] for d in reviews if d["dup_group_id"]}),
            },
            "warnings": warnings,
            "model": {"version": version, "T_AI": t_ai, "T_HUMAN": t_human, "thresholds": info.thresholds, "is_dummy": info.is_dummy},
            "assumptions": FIXED_ASSUMPTIONS + ([] if dedup_source == "realstar_model" else ["근접 중복은 완전히 같은 문장만 묶었어요."]),
        }
        return AnalysisResult.model_validate(result).model_dump()

    def run(self, analysis_id: str) -> None:
        if self.collect(analysis_id):
            self.detect_and_aggregate(analysis_id)
