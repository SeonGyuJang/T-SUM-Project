"""리뷰 영역 파싱과 조작 (README 5.2 수집 절차 3~6).

- 파서(`parse_reviews`)는 순수 함수라 HTML 스냅샷으로 테스트한다.
- 수집기(`ReviewCollector`)는 BrowserSession으로 정렬=최신순, 별점 필터, 페이지 넘김을 한다.
  review_mode=fragment이면 같은 브라우저 세션에서 리뷰 조각 URL을 연다(속도·차단 규칙 동일).
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from realstar.collectors.base import CollectProgress, ProgressCallback, RawReview, SortOrder
from realstar.collectors.coupang.browser import BrowserSession
from realstar.collectors.coupang.selectors import (
    Selectors,
    make_soup,
    multiline_text_of,
    parse_int,
    select_all,
    select_first,
    text_of,
)
from realstar.errors import ParserBrokenError

log = logging.getLogger(__name__)


@dataclass
class ParseStats:
    items: int = 0
    missing: dict[str, int] = field(default_factory=dict)

    def miss(self, f: str) -> None:
        self.missing[f] = self.missing.get(f, 0) + 1

    def missing_rates(self) -> dict[str, float]:
        return {k: v / self.items for k, v in self.missing.items()} if self.items else {}


def author_hash(name: str | None, salt: str) -> str | None:
    if not name:
        return None
    return "sha256:" + hashlib.sha256((salt + "|" + name.strip()).encode()).hexdigest()


def content_hash_id(product_id: str, star: int, content: str, date: str | None) -> str:
    h = hashlib.sha256(f"{product_id}|{star}|{date}|{content}".encode()).hexdigest()[:24]
    return f"h_{h}"


def parse_reviews(
    html: str,
    selectors: Selectors,
    product_id: str,
    *,
    expected_star: int | None = None,
    salt: str = "",
) -> tuple[list[RawReview], ParseStats]:
    sel = selectors.section("reviews")
    soup = make_soup(html)
    stats = ParseStats()
    out: list[RawReview] = []
    date_re = re.compile(sel.get("date_pattern", r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"))
    for art in select_all(soup, sel.get("item", [])):
        stats.items += 1
        # 별점
        star = None
        star_node = select_first(art, sel.get("star", []))
        if star_node is not None:
            star = parse_int(str(star_node.get(sel.get("star_attr", "data-rating"), "")) or None)
            if star is None:
                star = parse_int(text_of(star_node))
        if star is None or not 1 <= star <= 5:
            stats.miss("star")
            star = expected_star
        # 본문
        content = multiline_text_of(select_first(art, sel.get("content", [])))
        if not content:
            stats.miss("content")
        title = text_of(select_first(art, sel.get("title", [])))
        # 작성일
        created_at = None
        dm = date_re.search(text_of(select_first(art, sel.get("date", []))) or "")
        if dm:
            y, mth, d = (int(x) for x in dm.groups())
            created_at = f"{y:04d}-{mth:02d}-{d:02d}"
        else:
            stats.miss("date")
        # 식별자
        review_id = None
        for attr in sel.get("review_id_attrs", []):
            if art.get(attr):
                review_id = str(art.get(attr))
                break
        if review_id is None:
            for css in sel.get("review_id_child", []):
                node = art.select_one(css)
                if node is not None:
                    for attr in sel.get("review_id_attrs", []):
                        if node.get(attr):
                            review_id = str(node.get(attr))
                            break
                if review_id:
                    break
        if not content or star is None:
            continue
        if review_id is None:
            review_id = content_hash_id(product_id, star, content, created_at)
        helpful = 0
        help_node = select_first(art, sel.get("helpful", []))
        if help_node is not None:
            helpful = parse_int(str(help_node.get(sel.get("helpful_attr", "data-count"), "")) or None) or parse_int(text_of(help_node)) or 0
        author_name = text_of(select_first(art, sel.get("author", [])))
        out.append(
            RawReview(
                review_id=review_id,
                product_id=product_id,
                star=star,
                title=title,
                content=content,
                created_at=created_at,
                has_photo=select_first(art, sel.get("photo", [])) is not None,
                helpful_count=helpful,
                option_name=text_of(select_first(art, sel.get("option", []))),
                author_hash=author_hash(author_name, salt),  # 닉네임 원문은 저장하지 않는다
            )
        )
    return out, stats


def check_parse_health(stats: ParseStats, selectors: Selectors, threshold: float) -> None:
    required = selectors.get("reviews", "required_fields", ["star", "content", "date"])
    rates = {k: v for k, v in stats.missing_rates().items() if k in required and v > threshold}
    if rates:
        failed = {f"reviews.{k}": round(v, 3) for k, v in rates.items()}
        raise ParserBrokenError("reviews", failed, f"missing rate over {threshold}: {failed}")


def has_no_review_marker(html: str, selectors: Selectors) -> bool:
    soup = make_soup(html)
    return select_first(soup, selectors.css_list("reviews", "no_review")) is not None


class DebugHtmlStore:
    """원본 HTML(리뷰 영역) 최근 N건만 저장한다(파서 회귀 fixture 용도)."""

    def __init__(self, directory: Path, keep: int) -> None:
        self.dir = Path(directory)
        self.keep = keep
        self._recent: deque[Path] = deque()

    def save(self, name: str, html: str, selectors: Selectors) -> str | None:
        if self.keep <= 0:
            return None
        self.dir.mkdir(parents=True, exist_ok=True)
        soup = make_soup(html)
        section = select_first(soup, selectors.css_list("reviews", "section"))
        path = self.dir / f"{name}.html"
        path.write_text(str(section) if section is not None else html, encoding="utf-8")
        self._recent.append(path)
        files = sorted(self.dir.glob("*.html"), key=lambda p: p.stat().st_mtime)
        for old in files[: max(0, len(files) - self.keep)]:
            old.unlink(missing_ok=True)
        return path.name


class ReviewCollector:
    def __init__(
        self,
        browser: BrowserSession,
        selectors: Selectors,
        *,
        salt: str,
        fail_threshold: float,
        debug_store: DebugHtmlStore | None = None,
    ) -> None:
        self.b = browser
        self.sel = selectors
        self.salt = salt
        self.fail_threshold = fail_threshold
        self.debug = debug_store
        self._sorted_latest = False

    @property
    def mode(self) -> str:
        return str(self.sel.data.get("review_mode", "interactive"))

    # ── 공통 ──────────────────────────────────────────────
    def _ingest(
        self, html: str, product_id: str, star: int, seen: set[str], out: list[RawReview], limit: int, page_no: int
    ) -> int:
        """페이지 하나를 파싱해 out에 더한다. 페이지에서 읽은 리뷰 수(중복 포함)를 돌려준다."""
        reviews, stats = parse_reviews(html, self.sel, product_id, expected_star=star, salt=self.salt)
        if stats.items:
            check_parse_health(stats, self.sel, self.fail_threshold)
        ref = self.debug.save(f"{product_id}_s{star}_p{page_no}", html, self.sel) if self.debug else None
        for r in reviews:
            if len(out) >= limit:
                break
            if r.star != star or r.review_id in seen:
                continue
            seen.add(r.review_id)
            r.raw_html_ref = ref
            out.append(r)
        return len(reviews)

    def _after_page(self, n_items: int, collected_in_star: int, html: str) -> bool:
        """빈 페이지 처리. 계속 진행하면 True.

        - 이 별점에서 아직 하나도 못 읽었는데(N_s > 0) 비어 있으면 차단 신호로 센다.
          연속 SCRAPER_EMPTY_STREAK_LIMIT회면 BlockedError(README 0-3 '리뷰 영역이 연속으로 비어 있음').
        - 이미 읽은 뒤 비어 있으면 목록 끝으로 본다.
        """
        if n_items > 0:
            self.b.block_detector.record_review_page(n_items, expected_more=True)
            return True
        if has_no_review_marker(html, self.sel):
            return False
        if collected_in_star == 0:
            self.b.block_detector.record_review_page(0, expected_more=True)
            return False
        return False

    def collect(
        self,
        product_id: str,
        star: int,
        limit: int,
        sort: SortOrder = "latest",
        expected_total: int | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[RawReview]:
        target = min(limit, expected_total) if expected_total is not None else limit
        if target <= 0:
            return []
        if self.mode == "fragment":
            return self._collect_fragment(product_id, star, target, sort, on_progress)
        return self._collect_interactive(product_id, star, target, sort, on_progress)

    # ── fragment 모드 ──────────────────────────────────────
    def _collect_fragment(
        self, product_id: str, star: int, target: int, sort: SortOrder, on_progress: ProgressCallback | None
    ) -> list[RawReview]:
        tmpl = str(self.sel.get("urls", "review_fragment"))
        size = int(self.sel.get("urls", "review_fragment_page_size", 10))
        sort_by = self.sel.get("reviews", "sort_by_param", {}).get(sort, "DATE_DESC")
        out: list[RawReview] = []
        seen: set[str] = set()
        page = 1
        while len(out) < target:
            html = self.b.get(tmpl.format(product_id=product_id, page=page, size=size, sort_by=sort_by, star=star))
            before = len(out)
            n_items = self._ingest(html, product_id, star, seen, out, target, page)
            if on_progress:
                on_progress(CollectProgress(star=star, collected=len(out), target=target, pages_loaded=self.b.pages_loaded))
            if not self._after_page(n_items, before, html):
                break
            if len(out) == before:  # 새 리뷰 없이 중복만 → 목록 끝
                break
            page += 1
        return out

    # ── interactive 모드 ───────────────────────────────────
    def prepare_review_area(self) -> None:
        """리뷰 영역으로 스크롤하고 렌더링을 기다린 뒤 정렬을 최신순으로 바꾼다."""
        self.b.scroll_into_view(self.sel.css_list("reviews", "section"))
        self.b.wait_for_any(self.sel.css_list("reviews", "list_ready"))

    def _ensure_sort(self, sort: SortOrder) -> None:
        if sort != "latest" or self._sorted_latest:
            return
        before = self._list_signature()
        if self.b.click_first(self.sel.css_list("reviews", "sort_latest")):
            self._wait_list_settled(before)
            self.b.after_navigation()
        self._sorted_latest = True

    def _list_signature(self) -> str:
        soup = make_soup(self.b.page_source)
        items = select_all(soup, self.sel.css_list("reviews", "item"))
        if not items and has_no_review_marker(str(soup), self.sel):
            return "<no-review>"
        return "|".join((text_of(i) or "")[:60] for i in items[:3])

    def _list_stars(self) -> tuple[list[int | None], bool]:
        html = self.b.page_source
        reviews, stats = parse_reviews(html, self.sel, "_", salt="")
        del stats
        return [r.star for r in reviews], has_no_review_marker(html, self.sel)

    def _wait_list_settled(self, before: str, star: int | None = None) -> None:
        """클릭 후 목록이 실제로 바뀌고(이전 목록 재사용 방지), 잠시 그대로 유지될 때까지 기다린다.

        사이트가 목록을 비동기로 다시 그리므로, 바뀐 직후의 중간 상태(예: 이전 클릭의 늦은 결과)를 읽지 않게 한다.
        star가 주어지면 보이는 리뷰가 모두 그 별점일 때까지 기다린다.
        """
        self.b.wait_for_any(self.sel.css_list("reviews", "list_ready"))
        self.b.wait_until(lambda: self._list_signature() != before)
        last: list[str] = []
        repeats = [0]

        def settled() -> bool:
            sig = self._list_signature()
            repeats[0] = repeats[0] + 1 if last and sig == last[-1] else 0
            last.append(sig)
            if repeats[0] < 2:
                return False
            if star is None:
                return True
            stars, empty = self._list_stars()
            return empty or (bool(stars) and all(x == star for x in stars))

        self.b.wait_until(settled)

    def _select_star(self, star: int) -> None:
        before = self._list_signature()
        self.b.click_first(self.sel.css_list("reviews", "star_filter_open"))
        option_css = str(self.sel.get("reviews", "star_filter_option")).format(star=star)
        if not self.b.click_first([option_css]):
            raise ParserBrokenError("reviews", {"reviews.star_filter_option": 1.0}, f"star filter {star} not found")
        self._wait_list_settled(before, star=star)

    def _go_next_page(self, next_page: int) -> bool:
        before = self._list_signature()
        page_css = str(self.sel.get("reviews", "page_button")).format(page=next_page)
        if self.b.click_first([page_css]) or self.b.click_first(self.sel.css_list("reviews", "next_page_group")):
            self._wait_list_settled(before)
            return True
        return False

    def _expand_more(self) -> None:
        more = self.sel.css_list("reviews", "more_button")
        if not more:
            return
        for _ in range(50):
            if not self.b.click_first(more):
                break

    def _collect_interactive(
        self, product_id: str, star: int, target: int, sort: SortOrder, on_progress: ProgressCallback | None
    ) -> list[RawReview]:
        self.prepare_review_area()
        self._ensure_sort(sort)
        self._select_star(star)
        out: list[RawReview] = []
        seen: set[str] = set()
        page = 1
        while True:
            self._expand_more()
            html = self.b.after_navigation()
            before = len(out)
            n_items = self._ingest(html, product_id, star, seen, out, target, page)
            if on_progress:
                on_progress(CollectProgress(star=star, collected=len(out), target=target, pages_loaded=self.b.pages_loaded))
            if not self._after_page(n_items, before, html) or len(out) >= target or len(out) == before:
                break
            # 리뷰 페이지 넘김은 화면 안 조작이지만 상한 관리를 위해 페이지 로드로 센다
            self.b.consume_page_budget()
            if not self._go_next_page(page + 1):
                break
            page += 1
        return out
