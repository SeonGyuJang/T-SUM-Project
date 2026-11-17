"""CrawlerProvider: 요청이 들어오면 저장소 루트의 수집기(coupang_reviews.py)를 실행해 리뷰를 모은다.

- 수집 로직은 수집기 파일이 전부 담당한다. 서비스는 `crawler_runner.py`를 subprocess로 실행하고,
  runner가 내보내는 진행 이벤트(JSON 줄)를 받아 홈페이지 진행 화면에 반영한다.
- 수집 결과는 수집기 형식 그대로 `output/products/<상품ID>.json`에 저장되고, 서비스는 그 파일을 읽어
  ProductMeta / RawReview로 바꿔 쓴다. 따라서 수집기를 직접(CLI로) 실행해 모은 상품도 홈페이지에 바로 나온다.
- 이미 수집이 끝난 파일이 있고 `crawler_reuse_hours` 안이면 다시 수집하지 않는다(강제 새로고침 제외).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from realstar.collectors.base import (
    STARS,
    CollectProgress,
    ProductMeta,
    ProgressCallback,
    RawReview,
    SearchCandidate,
    SortOrder,
)
from realstar.config import Settings
from realstar.errors import BlockedError, CrawlerUnavailableError, InvalidInputError, RealstarError

log = logging.getLogger(__name__)

RUNNER = Path(__file__).with_name("crawler_runner.py")
PREFIX = "@@RS@@"
KST = timezone(timedelta(hours=9))
CRAWLER_SORT: SortOrder = "best"  # 수집기 SORT_BY=ORDER_SCORE_ASC (쿠팡 기본 정렬)
SELECTORS_VERSION = "coupang_reviews.py"

EventCallback = Callable[[dict[str, Any]], None]


# ── 수집기 출력 파일 → 서비스 데이터 ─────────────────────────────
def _to_int(v: Any) -> int | None:
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_korean_date(v: str | None) -> str | None:
    """'2026년09월09일' / '2026-09-09' / '2026.09.09' → '2026-09-09'."""
    if not v:
        return None
    m = re.search(r"(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})", str(v))
    if not m:
        return None
    return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"


def parse_collected_at(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.strptime(str(v), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    except ValueError:
        return None


def star_counts_of(info: dict[str, Any], reviews: list[dict[str, Any]] | None = None) -> dict[int, int]:
    raw = info.get("별점별_리뷰_개수") or {}
    got = info.get("수집된_리뷰_개수") or {}
    out: dict[int, int] = {}
    for s in STARS:
        n = _to_int(raw.get(f"{s}점"))
        if n is None:  # 별점별 개수를 못 찾은 경우 수집한 개수로 대신한다
            n = _to_int(got.get(f"{s}점"))
        if n is None and reviews is not None:
            n = sum(1 for r in reviews if _to_int(r.get("고객_평점")) == s)
        out[s] = n or 0
    return out


def meta_from_file(data: dict[str, Any]) -> ProductMeta:
    info = data.get("상품정보") or {}
    reviews = data.get("리뷰") or []
    counts = star_counts_of(info, reviews)
    total = _to_int(info.get("전체_리뷰_개수"))
    if total is None or total <= 0:
        total = sum(counts.values())
    computed = (sum(s * n for s, n in counts.items()) / sum(counts.values())) if sum(counts.values()) else None
    shown = _to_float(info.get("전체_평점"))
    # 수집기는 평균 별점 필드를 이름 추측으로 찾는다. 별점 분포와 크게 다르면(다른 필드를 잡은 것) 쓰지 않는다.
    displayed = shown if (shown is not None and computed is not None and abs(shown - computed) <= 0.1) else None
    return ProductMeta(
        product_id=str(info.get("상품ID") or ""),
        name=str(info.get("상품명") or "") or f"상품 {info.get('상품ID')}",
        image_url=info.get("대표이미지") or None,
        url=info.get("상품_URL") or None,
        displayed_avg=round(displayed, 2) if displayed is not None else None,
        total_reviews=total,
        star_counts=counts,
    )


def review_id_for(product_id: str, r: dict[str, Any]) -> str:
    key = "|".join(str(r.get(k) or "") for k in ("고객_아이디", "고객_평점", "리뷰_작성_시간", "리뷰_제목"))
    key += "|" + str(r.get("상세리뷰") or "")[:300]
    return f"c{product_id}-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


def reviews_from_file(data: dict[str, Any]) -> list[RawReview]:
    info = data.get("상품정보") or {}
    pid = str(info.get("상품ID") or "")
    out: list[RawReview] = []
    used: set[str] = set()
    for r in data.get("리뷰") or []:
        star = _to_int(r.get("고객_평점"))
        if star not in STARS:
            continue
        rid = review_id_for(pid, r)
        n = 1
        while rid in used:  # 완전히 같은 리뷰가 두 번 들어온 경우
            n += 1
            rid = f"{review_id_for(pid, r)}-{n}"
        used.add(rid)
        try:
            photos = json.loads(r.get("포토리뷰") or "[]")
        except (TypeError, ValueError):
            photos = []
        writer = str(r.get("고객_아이디") or "")
        out.append(
            RawReview(
                review_id=rid,
                product_id=pid,
                star=star,
                title=(r.get("리뷰_제목") or None),
                content=str(r.get("상세리뷰") or ""),
                created_at=parse_korean_date(r.get("리뷰_작성_시간")),
                has_photo=bool(photos),
                option_name=(r.get("구매상품") or None),
                author_hash=hashlib.sha256(writer.encode("utf-8")).hexdigest()[:16] if writer else None,
            )
        )
    return out


def summary_of_file(path: Path) -> dict[str, Any] | None:
    """홈페이지 '수집한 상품' 목록용 요약."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = meta_from_file(data)
    except Exception:
        return None
    info = data.get("상품정보") or {}
    got = info.get("수집된_리뷰_개수") or {}
    collected_at = parse_collected_at(info.get("수집_시각"))
    return {
        "product_id": meta.product_id,
        "name": meta.name,
        "image_url": meta.image_url,
        "url": meta.url,
        "total_reviews": meta.total_reviews,
        "collected_reviews": sum(_to_int(v) or 0 for v in got.values()) or len(data.get("리뷰") or []),
        "collected_at": collected_at.isoformat() if collected_at else None,
        "complete": bool(info.get("수집_완료", True)),
        "avg_all": round(sum(s * n for s, n in (meta.star_counts or {}).items()) / meta.total_reviews, 2) if meta.total_reviews else None,
    }


# ── provider ─────────────────────────────────────────────────
class CrawlerProvider:
    selectors_version = SELECTORS_VERSION
    sort: SortOrder = CRAWLER_SORT

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.script = Path(settings.crawler_script).resolve()
        self.output_dir = Path(settings.crawler_output_dir).resolve()
        self._pages = 0
        self._data: dict[str, dict[str, Any]] = {}

    @property
    def pages_loaded(self) -> int:
        return self._pages

    # ── 파일 ──
    def product_path(self, product_id: str) -> Path:
        return self.output_dir / "products" / f"{product_id}.json"

    def load_saved(self, product_id: str) -> dict[str, Any] | None:
        path = self.product_path(product_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except (OSError, ValueError):
            log.warning("could not read crawler output %s", path)
            return None

    def reusable(self, data: dict[str, Any] | None) -> bool:
        if not data:
            return False
        info = data.get("상품정보") or {}
        if not info.get("수집_완료", True) or not data.get("리뷰"):
            return False
        hours = self.settings.crawler_reuse_hours
        if hours <= 0:
            return True
        at = parse_collected_at(info.get("수집_시각"))
        return at is None or datetime.now(KST) - at <= timedelta(hours=hours)

    # ── 실행 ──
    def _python(self) -> str:
        return self.settings.crawler_python or sys.executable

    def _run(self, cmd: str, extra: list[str], on_event: EventCallback | None, timeout_sec: float) -> dict[str, Any]:
        """runner를 실행하고 마지막 결과/오류 이벤트를 돌려준다."""
        if not self.script.exists():
            raise CrawlerUnavailableError(f"crawler script not found: {self.script}")
        args = [self._python(), str(RUNNER), cmd, "--script", str(self.script), *extra]
        if self.settings.crawler_headless:
            args.append("--headless")
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        log.info("crawler %s: %s", cmd, " ".join(extra))
        try:
            proc = subprocess.Popen(
                args, cwd=str(self.script.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
            )
        except OSError as e:
            raise CrawlerUnavailableError(f"cannot start crawler python {self._python()}: {e}") from e
        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout_sec, _kill)
        timer.daemon = True
        timer.start()
        final: dict[str, Any] | None = None
        tail: deque[str] = deque(maxlen=20)
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip("\n")
                if line.startswith(PREFIX):
                    try:
                        evt = json.loads(line[len(PREFIX):])
                    except ValueError:
                        continue
                    if "pages_loaded" in evt:
                        self._pages = max(self._pages, int(evt["pages_loaded"] or 0))
                    if evt.get("type") in ("result", "error", "search_result", "resolved"):
                        final = evt
                    elif on_event:
                        on_event(evt)
                elif line.strip():
                    tail.append(line.strip())
                    if on_event:  # 수집기·Scrapling이 직접 찍은 출력도 진행 기록으로 보여 준다
                        on_event({"type": "log", "message": line.strip()[:300]})
            proc.wait()
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
        if timed_out.is_set():
            raise RealstarError(f"crawler timed out after {timeout_sec:.0f}s")
        if final is None:
            raise RealstarError(f"crawler exited ({proc.returncode}) without result: {' / '.join(tail)[-500:]}")
        if final.get("type") == "error":
            msg = str(final.get("message") or "")
            if final.get("kind") == "blocked":
                raise BlockedError("crawler", msg)
            if final.get("kind") == "setup":
                raise CrawlerUnavailableError(msg)
            raise RealstarError(msg[:300])
        return final

    def collect_all(self, product_id: str, url: str | None, *, force: bool = False, on_event: EventCallback | None = None) -> dict[str, Any]:
        """상품 하나를 수집(또는 저장된 파일 재사용)하고 수집기 형식 데이터를 돌려준다."""
        saved = self.load_saved(product_id)
        if not force and self.reusable(saved):
            assert saved is not None
            if on_event:
                on_event({"type": "reuse", "collected_at": (saved.get("상품정보") or {}).get("수집_시각")})
            self._data[product_id] = saved
            return saved
        target_url = url or f"https://www.coupang.com/vp/products/{product_id}"
        timeout = self.settings.crawler_timeout_min * 60
        final = self._run(
            "collect",
            ["--url", target_url, "--per-rating", str(self.settings.sample_per_star), "--out", str(self.output_dir)],
            on_event, timeout,
        )
        data = self.load_saved(product_id)
        if data is None:
            raise RealstarError(f"crawler finished but output missing: {final.get('path')}")
        if not data.get("리뷰") and (_to_int((data.get("상품정보") or {}).get("전체_리뷰_개수")) or 0) > 0:
            raise BlockedError("crawler_empty", "리뷰가 있는 상품인데 하나도 받지 못함")
        self._data[product_id] = data
        return data

    # ── ReviewProvider 인터페이스 (저장된 파일 기준) ──
    def _file(self, product_id: str) -> dict[str, Any]:
        data = self._data.get(product_id) or self.load_saved(product_id)
        if data is None:
            raise InvalidInputError(f"not collected: {product_id}", "아직 수집하지 않은 상품이에요.")
        self._data[product_id] = data
        return data

    def get_product_meta(self, product_id: str) -> ProductMeta:
        return meta_from_file(self._file(product_id))

    def get_reviews(
        self, product_id: str, star: int, limit: int, sort: SortOrder = "latest", on_progress: ProgressCallback | None = None,
    ) -> list[RawReview]:
        out = [r for r in reviews_from_file(self._file(product_id)) if r.star == star][:limit]
        if on_progress:
            on_progress(CollectProgress(star=star, collected=len(out), target=len(out), pages_loaded=self._pages))
        return out

    def local_search(self, query: str) -> list[SearchCandidate]:
        """이미 수집한 상품 중 이름이 맞는 것 (브라우저를 열지 않는다)."""
        from realstar.resolver.scoring import normalize_query

        toks = [t for t in normalize_query(query).split() if len(t) >= 2]
        if not toks:
            return []
        out: list[SearchCandidate] = []
        for path in sorted((self.output_dir / "products").glob("*.json")):
            s = summary_of_file(path)
            if not s:
                continue
            name = normalize_query(s["name"] or "")
            hits = sum(1 for t in toks if t in name)
            if hits and hits / len(toks) >= 0.5:
                out.append(SearchCandidate(product_id=s["product_id"], name=s["name"], image_url=s["image_url"], url=s["url"],
                                           review_count=s["total_reviews"], rating=s["avg_all"]))
        return out

    def search(self, query: str) -> list[SearchCandidate]:
        local = self.local_search(query)
        try:
            final = self._run("search", ["--query", query, "--limit", str(self.settings.crawler_search_limit)], None,
                              self.settings.crawler_search_timeout_sec)
            live = [SearchCandidate.model_validate(c) for c in final.get("candidates") or []]
        except (BlockedError, RealstarError) as e:
            if not local:
                raise
            log.warning("live search failed, using collected products only: %s", e)
            live = []
        seen = {c.product_id for c in local}
        return local + [c for c in live if c.product_id not in seen]

    def resolve_short_url(self, url: str) -> str:
        final = self._run("resolve", ["--url", url], None, self.settings.crawler_search_timeout_sec)
        return str(final.get("url") or "")

    def close(self) -> None:
        return None


def list_collected(settings: Settings) -> list[dict[str, Any]]:
    out_dir = Path(settings.crawler_output_dir) / "products"
    items = [s for p in out_dir.glob("*.json") if (s := summary_of_file(p))]
    items.sort(key=lambda s: s.get("collected_at") or "", reverse=True)
    return items


__all__ = ["CrawlerProvider", "list_collected", "meta_from_file", "reviews_from_file"]
