"""DB 접근 함수 모음 (캐시 TTL 판단 포함)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from realstar.collectors.base import ProductMeta, RawReview, SearchCandidate
from realstar.db.models import Analysis, Prediction, Product, Review, ScrapeLog, SearchCacheRow
from realstar.db.session import session_scope

ACTIVE_STATUSES = ("queued", "collecting", "detecting", "aggregating")
TERMINAL_STATUSES = ("done", "failed", "blocked")


def now_utc() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def is_fresh(dt: datetime | None, ttl_hours: int) -> bool:
    dt = _aware(dt)
    return dt is not None and now_utc() - dt < timedelta(hours=ttl_hours)


def new_analysis_id() -> str:
    return "an_" + secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:16]


# ── products / reviews ───────────────────────────────────
def upsert_product(s: Session, meta: ProductMeta, star_counts: dict[int, int]) -> Product:
    p = s.get(Product, meta.product_id) or Product(product_id=meta.product_id)
    p.name = meta.name
    p.image_url = meta.image_url
    p.url = meta.url
    p.category = meta.category
    p.displayed_avg = meta.displayed_avg
    p.total_reviews = meta.total_reviews
    p.star_counts = {str(k): int(v) for k, v in star_counts.items()}
    p.fetched_at = now_utc()
    s.add(p)
    return p


def mark_reviews_fetched(s: Session, product_id: str, sampling: dict[str, Any]) -> None:
    p = s.get(Product, product_id)
    if p is not None:
        p.reviews_fetched_at = now_utc()
        p.sampling = sampling


def replace_reviews(s: Session, product_id: str, reviews: list[RawReview]) -> None:
    """새 표본으로 교체한다(이전 표본의 예측은 review_id가 같으면 재사용)."""
    keep_ids = {r.review_id for r in reviews}
    old = s.scalars(select(Review).where(Review.product_id == product_id)).all()
    for row in old:
        if row.review_id not in keep_ids:
            for pred in s.scalars(select(Prediction).where(Prediction.review_id == row.review_id)).all():
                s.delete(pred)
            s.delete(row)
    s.flush()
    ts = now_utc()
    for r in reviews:
        row = s.get(Review, r.review_id) or Review(review_id=r.review_id)
        row.product_id = product_id
        row.star = r.star
        row.title = r.title
        row.content = r.content
        row.created_at = r.created_at
        row.has_photo = r.has_photo
        row.helpful_count = r.helpful_count
        row.option_name = r.option_name
        row.author_hash = r.author_hash
        row.raw_html_ref = r.raw_html_ref
        row.fetched_at = ts
        s.add(row)


def get_reviews(s: Session, product_id: str) -> list[Review]:
    return list(s.scalars(select(Review).where(Review.product_id == product_id).order_by(Review.star.desc(), Review.created_at.desc())).all())


def cached_product(s: Session, product_id: str, ttl_hours: int, per_star_limit: int, sort: str) -> Product | None:
    """상품 메타와 리뷰 표본이 TTL 안에 같은 조건으로 수집돼 있으면 돌려준다(F8)."""
    p = s.get(Product, product_id)
    if p is None or not is_fresh(p.reviews_fetched_at, ttl_hours):
        return None
    sampling = p.sampling or {}
    if sampling.get("per_star_limit") != per_star_limit or sampling.get("sort") != sort:
        return None
    return p


# ── predictions ──────────────────────────────────────────
def get_predictions(s: Session, review_ids: list[str], model_version: str) -> dict[str, Prediction]:
    if not review_ids:
        return {}
    rows = s.scalars(select(Prediction).where(Prediction.model_version == model_version, Prediction.review_id.in_(review_ids))).all()
    return {r.review_id: r for r in rows}


def save_prediction(s: Session, review_id: str, model_version: str, p_ai: float, label: str, features: dict[str, Any]) -> None:
    row = s.get(Prediction, (review_id, model_version)) or Prediction(review_id=review_id, model_version=model_version)
    row.p_ai = p_ai
    row.label = label
    row.features = features
    row.created_at = now_utc()
    s.add(row)


# ── analyses ─────────────────────────────────────────────
def create_analysis(s: Session, product_id: str, *, force_refresh: bool, input_: dict[str, Any] | None = None, status: str = "queued") -> Analysis:
    a = Analysis(
        analysis_id=new_analysis_id(),
        product_id=product_id,
        status=status,
        progress={"stage": status},
        created_at=now_utc(),
        force_refresh=force_refresh,
        input=input_ or {},
    )
    s.add(a)
    s.flush()
    return a


def latest_done_analysis(s: Session, product_id: str, ttl_hours: int | None = None) -> Analysis | None:
    q = select(Analysis).where(Analysis.product_id == product_id, Analysis.status == "done").order_by(Analysis.finished_at.desc()).limit(1)
    a = s.scalars(q).first()
    if a is None:
        return None
    if ttl_hours is not None and not is_fresh(a.finished_at, ttl_hours):
        return None
    return a


def active_analysis(s: Session, product_id: str) -> Analysis | None:
    q = select(Analysis).where(Analysis.product_id == product_id, Analysis.status.in_(ACTIVE_STATUSES)).order_by(Analysis.created_at.desc()).limit(1)
    return s.scalars(q).first()


def queue_position(s: Session, a: Analysis) -> int:
    """수집 대기열 순번(1 = 다음 차례). 수집 중인 작업이 있으면 그 뒤로 센다."""
    ahead = s.scalar(
        select(func.count()).select_from(Analysis).where(Analysis.status == "queued", Analysis.created_at < a.created_at)
    )
    collecting = s.scalar(select(func.count()).select_from(Analysis).where(Analysis.status == "collecting"))
    return int(ahead or 0) + int(collecting or 0) + 1


def update_analysis(database_url: str, analysis_id: str, **fields: Any) -> None:
    with session_scope(database_url) as s:
        a = s.get(Analysis, analysis_id)
        if a is None:
            return
        for k, v in fields.items():
            setattr(a, k, v)


def merge_progress(database_url: str, analysis_id: str, **progress: Any) -> None:
    with session_scope(database_url) as s:
        a = s.get(Analysis, analysis_id)
        if a is None:
            return
        cur = dict(a.progress or {})
        for k, v in progress.items():
            if isinstance(v, dict) and isinstance(cur.get(k), dict):
                merged = dict(cur[k])
                merged.update(v)
                cur[k] = merged
            else:
                cur[k] = v
        cur["updated_at"] = now_utc().isoformat()
        a.progress = cur


# ── scrape_log / search_cache ────────────────────────────
def add_scrape_log(s: Session, product_id: str | None, started_at: datetime, pages: int, outcome: str, detail: dict[str, Any] | None) -> None:
    s.add(ScrapeLog(started_at=started_at, finished_at=now_utc(), product_id=product_id, pages_loaded=pages, outcome=outcome, detail=detail or {}))


class DbSearchCache:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get(self, query_norm: str, ttl_hours: int) -> list[SearchCandidate] | None:
        with session_scope(self.database_url) as s:
            row = s.get(SearchCacheRow, query_norm)
            if row is None or not is_fresh(row.fetched_at, ttl_hours):
                return None
            return [SearchCandidate.model_validate(c) for c in row.candidates]

    def put(self, query_norm: str, candidates: list[SearchCandidate]) -> None:
        with session_scope(self.database_url) as s:
            row = s.get(SearchCacheRow, query_norm) or SearchCacheRow(query_norm=query_norm)
            row.candidates = [c.model_dump() for c in candidates]
            row.fetched_at = now_utc()
            s.add(row)
