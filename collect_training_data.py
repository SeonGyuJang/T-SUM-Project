"""
AI 탐지 모델 학습용 리뷰 데이터 수집기

model/MODEL_DEV.md 4.2(데이터 설계)의 원천 데이터를 모은다.
  H1  쿠팡 리뷰, 작성일 < 2022-11-30 (ChatGPT 공개 이전)  → 사람(human) 후보   [collect]
  U1  쿠팡 리뷰, 작성일 ≥ 2023-01-01                      → 라벨 없음(추세 점검) [collect --post-per-star]
  H2  네이버 쇼핑 리뷰 20만 건 (2020.06~07 수집)             → 사람(human) 후보   [naver]

쿠팡 접속은 coupang_reviews.py(서비스용 수집기)의 함수를 그대로 가져다 쓴다(같은 브라우저 프로필·같은 API 방식).
이 파일은 coupang_reviews.py를 고치지 않는다.

어떻게 2022-11-30 이전 리뷰를 찾나
  리뷰를 최신순(DATE_DESC)으로 정렬하면 페이지가 뒤로 갈수록 오래된 리뷰다. 별점별로
  "처음으로 2022-11-30 이전 리뷰가 나오는 페이지"를 이진 탐색으로 찾고(약 10번 요청),
  그 뒤 구간에서 페이지를 고르게 골라 담는다(2018~2022년이 한쪽에 몰리지 않게).
  날짜순 정렬이 안 되거나 페이지 상한 때문에 닿지 않으면, 기본 정렬 페이지를 훑어서 이전 리뷰만 고른다.

사용법 (coupang_reviews.py와 같은 파이썬·같은 폴더에서)
  python collect_training_data.py naver                              # 네이버 쇼핑 데이터 받기·변환
  python collect_training_data.py inspect "<쿠팡 상품 URL>"          # 날짜순 정렬·페이지 이동 점검 (먼저 한 번)
  python collect_training_data.py collect training_products.txt      # 상품 목록 수집 (중단 후 다시 실행하면 이어서)
  python collect_training_data.py collect training_products.txt --per-star 30 --post-per-star 10
  python collect_training_data.py stats                              # 모인 양 보기

결과 (git에 올라가지 않는 model/data/ 아래)
  model/data/raw/coupang/<날짜>_<시각>.jsonl   리뷰 1건 = 1줄 (MODEL_DEV.md 4.12.1 형식 + period 필드)
  model/data/raw/coupang/_state.json           상품별 완료 기록 (이어서 수집용)
  model/data/raw/naver/naver_shopping.jsonl    네이버 쇼핑 변환 결과

쿠팡이 차단(403·접근 거부)하면 그 자리에서 멈춘다. 우회하지 않는다. 시간이 지난 뒤 같은 명령을 다시 실행하면
끝난 상품은 건너뛰고 이어서 모은다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

# ──────────────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────────────
CUTOFF = date(2022, 11, 30)       # 이 날짜 '이전'(미만) 작성 = ChatGPT 이전 (MODEL_DEV.md D-002)
POST_FROM = date(2023, 1, 1)      # 이 날짜 이후 작성 = U1 (라벨 없음)
DATE_SORT = "DATE_DESC"           # 쿠팡 리뷰 최신순 정렬값 (inspect로 확인)
PER_STAR = 30                     # 상품·별점당 2022-11-30 이전 리뷰 최대 개수 (MODEL_DEV.md 4.2.3)
POST_PER_STAR = 10                # 상품·별점당 2023년 이후 리뷰 최대 개수 (0이면 수집 안 함)
FALLBACK_PAGES = 8                # 날짜순이 안 될 때 기본 정렬로 훑어볼 최대 페이지
PAGE_ATTEMPTS = 3
PAGE_BACKOFF = (5, 20)            # 재시도 전 대기(초)
PRODUCT_DELAY = (8.0, 15.0)       # 상품 사이 대기(초) — 서비스 수집보다 느리게
SCRAPER_VERSION = "collect_training_data/1"

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "model" / "data" / "raw" / "coupang"
NAVER_DIR = ROOT / "model" / "data" / "raw" / "naver"
NAVER_URL = "https://raw.githubusercontent.com/bab2min/corpus/master/sentiment/naver_shopping.txt"
KST = timezone(timedelta(hours=9))
STARS = (5, 4, 3, 2, 1)


class Blocked(Exception):
    """쿠팡이 자동 접근을 막았다. 즉시 중단한다."""


# ──────────────────────────────────────────────────────────────
# 공통 도우미
# ──────────────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def parse_date(v: Any) -> date | None:
    m = re.search(r"(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})", str(v or ""))
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def length_bucket(text: str) -> str:
    n = len(re.sub(r"\s+", " ", text or "").strip())
    return "S" if n < 30 else "M" if n < 100 else "L"


def period_of(d: date | None) -> str | None:
    if d is None:
        return None
    if d < CUTOFF:
        return "pre_chatgpt"
    if d >= POST_FROM:
        return "post_chatgpt"
    return None  # 2022-11-30 ~ 2022-12-31: 경계 구간이라 쓰지 않는다


def load_crawler() -> Any:
    sys.path.insert(0, str(ROOT))
    try:
        import coupang_reviews as cr  # noqa: PLC0415
    except ModuleNotFoundError as e:
        sys.exit(f"수집기 실행에 필요한 패키지가 없습니다: {e.name}\n"
                 f"  pip install \"scrapling[fetchers]\" && scrapling install  (또는 python -m patchright install chromium)")
    return cr


def read_products(path: Path) -> list[dict[str, str]]:
    """한 줄에 상품 URL 하나. '## 카테고리' 줄 아래의 URL은 그 카테고리로 기록된다. '#' 줄은 메모."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    category = ""
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("##"):
            category = line.lstrip("#").strip()
            continue
        if line.startswith("#"):
            continue
        m = re.search(r"/products/(\d+)", line)
        if not m:
            print(f"  ⚠ {line_no}번째 줄 건너뜀 (상품 페이지 주소가 아님): {line[:80]}")
            continue
        if m.group(1) in seen:
            continue
        seen.add(m.group(1))
        out.append({"product_id": m.group(1), "url": line.split()[0], "category": category})
    return out


def load_state(out_dir: Path) -> dict[str, Any]:
    p = out_dir / "_state.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except ValueError:
            pass
    return {"products": {}}


def save_state(out_dir: Path, state: dict[str, Any]) -> None:
    p = out_dir / "_state.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


# ──────────────────────────────────────────────────────────────
# 쿠팡: 페이지 단위 요청
# ──────────────────────────────────────────────────────────────
class ReviewPager:
    """한 상품·한 별점의 리뷰 페이지를 요청한다. 같은 페이지는 다시 요청하지 않는다."""

    def __init__(self, cr: Any, page: Any, pid: str, star: int, sort: str, log: Any) -> None:
        self.cr, self.page, self.pid, self.star, self.sort, self.log = cr, page, pid, star, sort, log
        self.cache: dict[int, list[dict[str, Any]]] = {}
        self.raw_first: Any = None
        self.requests = 0

    def url(self, page_no: int) -> str:
        return self.cr.API_BASE + "?" + urlencode({
            "productId": self.pid, "page": page_no, "size": self.cr.PAGE_SIZE, "sortBy": self.sort,
            "ratingSummary": "true", "ratings": str(self.star), "market": "",
        })

    def get(self, page_no: int) -> list[dict[str, Any]]:
        """파싱된 리뷰 목록. 빈 페이지면 []. 차단이면 Blocked."""
        if page_no in self.cache:
            return self.cache[page_no]
        last_err = ""
        for attempt in range(1, PAGE_ATTEMPTS + 1):
            self.cr.pause(self.page, self.cr.API_DELAY_RANGE)
            self.requests += 1
            try:
                data = self.cr.api_get(self.page, self.url(page_no))
            except Exception as e:  # HTTP 오류·JSON 아님(차단 페이지)
                last_err = str(e)
                if ("403" in last_err or "JSON이 아닌" in last_err) and attempt == PAGE_ATTEMPTS:
                    raise Blocked(last_err) from e
                wait = PAGE_BACKOFF[min(attempt - 1, len(PAGE_BACKOFF) - 1)]
                self.log(f"      ↻ {self.star}점 {page_no}페이지 {last_err[:60]} → {wait}초 후 재시도")
                self.page.wait_for_timeout(wait * 1000)
                continue
            items = self.cr.find_review_list(data)
            if page_no == 1:
                self.raw_first = data
            parsed = [self.cr.parse_review(x) for x in items]
            for r in parsed:
                r["_date"] = parse_date(r.get("date"))
            self.cache[page_no] = parsed
            return parsed
        self.cache[page_no] = []
        return []

    def total(self) -> int | None:
        if self.raw_first is None:
            return None
        items = self.cr.find_review_list(self.raw_first)
        t = self.cr.find_number(self.raw_first, self.cr.TOTAL_KEYS, skip_lists=items)
        return int(t) if t is not None else None

    def oldest(self, page_no: int) -> date | None:
        ds = [r["_date"] for r in self.get(page_no) if r["_date"]]
        return min(ds) if ds else None


def is_desc(reviews: list[dict[str, Any]]) -> bool:
    ds = [r["_date"] for r in reviews if r["_date"]]
    return len(ds) >= 2 and all(a >= b for a, b in zip(ds, ds[1:]))


def spread_pages(first: int, last: int, n: int) -> list[int]:
    """[first, last] 구간에서 n개 페이지를 고르게 고른다."""
    if last <= first or n <= 1:
        return [first]
    n = min(n, last - first + 1)
    return sorted({first + round(i * (last - first) / (n - 1)) for i in range(n)})


def collect_star(cr: Any, page: Any, pid: str, star: int, per_star: int, post_per_star: int, log: Any) -> dict[str, Any]:
    """한 별점: 2022-11-30 이전 리뷰 per_star개 + 2023년 이후 리뷰 post_per_star개."""
    pager = ReviewPager(cr, page, pid, star, DATE_SORT, log)
    first = pager.get(1)
    out: dict[str, Any] = {"pre": [], "post": [], "method": "date_sort", "requests": 0}
    if not first:
        out["requests"] = pager.requests
        return out

    if post_per_star:
        out["post"] = [r for r in first if r["_date"] and r["_date"] >= POST_FROM][:post_per_star]

    total = pager.total() or len(first)
    last = max(1, math.ceil(total / cr.PAGE_SIZE))
    pre: list[dict[str, Any]] = []
    seen: set[Any] = set()

    def take(reviews: list[dict[str, Any]], limit: int | None = None) -> None:
        added = 0
        for r in reviews:
            if len(pre) >= per_star or (limit is not None and added >= limit):
                return
            key = r["review_id"] or (r["date"], r["content"][:80])
            if key in seen or not r["_date"] or r["_date"] >= CUTOFF:
                continue
            seen.add(key)
            pre.append(r)
            added += 1

    capped = False
    if is_desc(first):
        # 페이지 상한이 있을 수 있으니, 실제로 닿는 마지막 페이지를 찾는다
        reach = last
        while reach > 1 and not pager.get(reach):
            reach //= 2
        if reach < last:
            lo, hi = reach, min(last, reach * 2)  # 닿는 마지막 페이지를 좁힌다
            while lo + 1 < hi:
                mid = (lo + hi) // 2
                if pager.get(mid):
                    lo = mid
                else:
                    hi = mid
            reach = lo
            capped = True
            log(f"      · {star}점: 전체 {last}페이지 중 {reach}페이지까지만 열림")
        oldest_reach = pager.oldest(reach)
        if oldest_reach is not None and oldest_reach < CUTOFF:
            lo, hi = 1, reach  # 처음으로 2022-11-30 이전 리뷰가 나오는 페이지
            while lo < hi:
                mid = (lo + hi) // 2
                od = pager.oldest(mid)
                if od is not None and od < CUTOFF:
                    hi = mid
                else:
                    lo = mid + 1
            need = math.ceil(per_star / cr.PAGE_SIZE) + 1
            chosen = spread_pages(lo, reach, need)
            quota = math.ceil(per_star / len(chosen))  # 페이지마다 고르게 담아 오래된 연도도 섞이게 한다
            for p in chosen:
                take(pager.get(p), quota)
            for p in chosen:  # 할당을 못 채운 만큼 다시 채운다
                take(pager.get(p))
            p = lo
            while len(pre) < per_star and p <= reach:  # 부족하면 경계부터 차례로 채운다
                take(pager.get(p))
                p += 1
        elif oldest_reach is not None:
            log(f"      · {star}점: 닿는 페이지 안에 2022-11-30 이전 리뷰가 없음 (가장 오래된 {oldest_reach})")
    else:
        out["method"] = "fallback_scan"

    if len(pre) < per_star and (out["method"] == "fallback_scan" or (capped and not pre)):
        # 날짜순이 안 되거나 페이지 상한 때문에 닿지 않을 때: 기본 정렬(베스트순)에는 오래된 리뷰가 섞여 있다
        if out["method"] == "date_sort":
            out["method"] = "date_sort+fallback"
        scan = ReviewPager(cr, page, pid, star, cr.SORT_BY, log)
        for p in range(1, FALLBACK_PAGES + 1):
            got = scan.get(p)
            if not got:
                break
            take(got)
            if post_per_star and len(out["post"]) < post_per_star:
                extra = [r for r in got if r["_date"] and r["_date"] >= POST_FROM and r not in out["post"]]
                out["post"] += extra[: post_per_star - len(out["post"])]
            if len(pre) >= per_star:
                break
        pager.requests += scan.requests

    out["pre"] = pre
    out["requests"] = pager.requests
    return out


def to_record(r: dict[str, Any], pid: str, product_name: str, category: str, collected_at: str) -> dict[str, Any]:
    d: date | None = r["_date"]
    rid = r.get("review_id") or hashlib.sha1(f"{pid}|{r.get('date')}|{r.get('content', '')[:200]}".encode()).hexdigest()[:20]
    content = r.get("content") or ""
    return {
        "review_id": f"cp-{pid}-{rid}",
        "product_id": pid,
        "category": category or None,
        "product_name": product_name,
        "star": r.get("rating"),
        "title": r.get("title") or None,
        "content": content,
        "created_at": d.isoformat() if d else None,
        "has_photo": bool(r.get("photos")),
        "helpful_count": 0,
        "option_name": r.get("purchased_item") or None,
        "period": period_of(d),
        "length_bucket": length_bucket(content),
        "collected_at": collected_at,
        "source": "coupang_reviews",
        "scraper_version": SCRAPER_VERSION,
    }


def collect_one(cr: Any, session: Any, item: dict[str, str], per_star: int, post_per_star: int) -> dict[str, Any]:
    pid = item["product_id"]
    box: dict[str, Any] = {"stars": {}, "name": ""}

    def log(msg: str) -> None:
        print(msg, flush=True)

    def action(page: Any) -> Any:
        try:
            try:
                title = page.evaluate("() => document.querySelector('meta[property=\"og:title\"]')?.content || document.title || ''")
            except Exception:
                title = ""
            if isinstance(title, dict):
                title = title.get("title") or ""
            box["name"] = cr.clean_product_name(title if isinstance(title, str) else "")
            cr.warm_up(page)
            for star in STARS:
                res = collect_star(cr, page, pid, star, per_star, post_per_star, log)
                box["stars"][star] = res
                log(f"    {star}점: 2022-11-30 이전 {len(res['pre'])}/{per_star}"
                    + (f" · 2023년 이후 {len(res['post'])}/{post_per_star}" if post_per_star else "")
                    + f"  (요청 {res['requests']}회, {res['method']})")
        except Exception as e:  # Scrapling은 page_action 예외를 삼키므로 직접 보관
            box["error"] = e
        return page

    resp = session.fetch(item["url"], page_action=action)
    if getattr(resp, "status", 200) != 200:
        raise Blocked(f"상품 페이지 HTTP {resp.status}")
    if "error" in box:
        raise box["error"]
    return box


def cmd_collect(args: argparse.Namespace) -> int:
    cr = load_crawler()
    out_dir = Path(args.out) if args.out else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    products = read_products(Path(args.products))
    state = load_state(out_dir)
    done = {pid for pid, s in state["products"].items() if s.get("done")}
    todo = [p for p in products if p["product_id"] not in done]
    if args.max_products:
        todo = todo[: args.max_products]
    print(f"상품 {len(products)}개 / 완료 {len(products) - len([p for p in products if p['product_id'] not in done])}개 / "
          f"이번에 {len(todo)}개 · 별점당 이전 {args.per_star}개, 이후 {args.post_per_star}개 · 기준일 {CUTOFF}")
    if not todo:
        return 0
    out_file = out_dir / f"{datetime.now(KST):%Y%m%d_%H%M%S}.jsonl"
    total_pre = total_post = 0
    try:
        with cr.open_session(headless=args.headless) as session:
            for n, item in enumerate(todo, 1):
                print(f"[{n}/{len(todo)}] {item['product_id']} {item['category'] or ''}", flush=True)
                box = collect_one(cr, session, item, args.per_star, args.post_per_star)
                collected_at = now_iso()
                rows = []
                for star in STARS:
                    res = box["stars"].get(star) or {"pre": [], "post": []}
                    rows += [to_record(r, item["product_id"], box["name"], item["category"], collected_at)
                             for r in res["pre"] + res["post"]]
                with out_file.open("a", encoding="utf-8") as f:  # 상품 단위로 한 번에 쓴다(중간 차단 시 반쪽 기록 없음)
                    for row in rows:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                pre = sum(1 for r in rows if r["period"] == "pre_chatgpt")
                post = sum(1 for r in rows if r["period"] == "post_chatgpt")
                total_pre, total_post = total_pre + pre, total_post + post
                state["products"][item["product_id"]] = {
                    "done": True, "name": box["name"], "category": item["category"], "pre": pre, "post": post,
                    "per_star": {str(s): len((box["stars"].get(s) or {}).get("pre", [])) for s in STARS},
                    "file": out_file.name, "at": collected_at,
                }
                save_state(out_dir, state)
                print(f"  ✓ {box['name'][:40]} · 이전 {pre}건 · 이후 {post}건", flush=True)
                if n < len(todo):
                    time.sleep(random.uniform(*PRODUCT_DELAY))
    except Blocked as e:
        print(f"\n⛔ 쿠팡이 자동 접근을 막았어요: {e}\n   여기서 멈춥니다(우회하지 않음). 시간이 지난 뒤 같은 명령을 다시 실행하면 이어서 모아요.")
        print(f"   이번 실행: 이전 {total_pre}건, 이후 {total_post}건 → {out_file}")
        return 2
    print(f"\n완료: 이전 {total_pre}건, 이후 {total_post}건 → {out_file}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """상품 하나로 날짜순 정렬·페이지 이동·이진 탐색이 되는지 확인한다(저장하지 않음)."""
    cr = load_crawler()
    pid = cr.product_id_from_url(args.url)
    box: dict[str, Any] = {}

    def action(page: Any) -> Any:
        try:
            cr.warm_up(page)
            for sort in (DATE_SORT, cr.SORT_BY):
                pager = ReviewPager(cr, page, pid, args.star, sort, print)
                first = pager.get(1)
                total = pager.total()
                ds = [r["_date"] for r in first if r["_date"]]
                box[sort] = {"n": len(first), "total": total, "dates": ds, "desc": is_desc(first)}
            res = collect_star(cr, page, pid, args.star, 10, 3, print)
            box["trial"] = res
        except Exception as e:
            box["error"] = e
        return page

    with cr.open_session(headless=args.headless) as session:
        resp = session.fetch(args.url, page_action=action)
    if getattr(resp, "status", 200) != 200:
        print(f"⛔ 상품 페이지 HTTP {resp.status} (차단되었을 수 있음)")
        return 2
    if "error" in box:
        raise box["error"]
    for sort in (DATE_SORT, cr.SORT_BY):
        b = box[sort]
        dates = ", ".join(d.isoformat() for d in b["dates"][:5])
        print(f"[정렬 {sort}] 리뷰 {b['n']}개 · {args.star}점 전체 {b['total']}개 · 첫 페이지 날짜 {dates} · 최신순? {'예' if b['desc'] else '아니오'}")
    t = box["trial"]
    pre_dates = sorted(r["_date"] for r in t["pre"])
    print(f"[시험 수집 {args.star}점] 방식 {t['method']} · 요청 {t['requests']}회 · 이전 {len(t['pre'])}개"
          + (f" ({pre_dates[0]} ~ {pre_dates[-1]})" if pre_dates else "") + f" · 이후 {len(t['post'])}개")
    if not box[DATE_SORT]["desc"]:
        print(f"⚠ sortBy={DATE_SORT}가 최신순으로 동작하지 않는 것 같아요. 기본 정렬을 훑는 방식으로 모읍니다(효율이 낮음).")
    return 0


# ──────────────────────────────────────────────────────────────
# 네이버 쇼핑 (H2)
# ──────────────────────────────────────────────────────────────
def cmd_naver(args: argparse.Namespace) -> int:
    out_dir = Path(args.out) if args.out else NAVER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "naver_shopping.txt"
    if not raw.exists() or args.force:
        print(f"내려받는 중: {NAVER_URL}")
        with urllib.request.urlopen(NAVER_URL, timeout=120) as r:  # noqa: S310 (고정 주소)
            raw.write_bytes(r.read())
    seen: set[str] = set()
    counts: Counter[tuple[int, str]] = Counter()
    dup = bad = 0
    out = out_dir / "naver_shopping.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for line in raw.read_text(encoding="utf-8").splitlines():
            star_s, _, text = line.partition("\t")
            text = text.strip()
            if not star_s.strip().isdigit() or not text:
                bad += 1
                continue
            key = re.sub(r"\s+", " ", text)
            if key in seen:
                dup += 1
                continue
            seen.add(key)
            star = int(star_s)
            lb = length_bucket(text)
            counts[(star, lb)] += 1
            f.write(json.dumps({
                "review_id": "nv-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16],
                "product_id": None, "category": None, "product_name": None,
                "star": star, "title": None, "content": text,
                "created_at": None,  # 원본에 날짜 없음. 수집 기간 2020.06~07 (bab2min/corpus README)
                "period": "pre_chatgpt", "length_bucket": lb,
                "source": "naver_shopping", "source_note": "bab2min/corpus sentiment/naver_shopping.txt (2020.06~07)",
            }, ensure_ascii=False) + "\n")
    print(f"완료 → {out}  (중복 {dup}건·형식 오류 {bad}건 제외)")
    print_table("네이버 쇼핑 (H2)", counts)
    return 0


# ──────────────────────────────────────────────────────────────
# 통계
# ──────────────────────────────────────────────────────────────
def print_table(title: str, counts: Counter[tuple[int, str]]) -> None:
    print(f"\n[{title}] 별점 × 길이(S<30자, M<100자, L≥100자)")
    print("  별점      S       M       L     합계")
    for s in STARS:
        row = [counts.get((s, b), 0) for b in "SML"]
        print(f"  {s}점 " + "".join(f"{v:>8,}" for v in row) + f"{sum(row):>9,}")
    tot = [sum(counts.get((s, b), 0) for s in STARS) for b in "SML"]
    print("  합계 " + "".join(f"{v:>8,}" for v in tot) + f"{sum(tot):>9,}")


def cmd_stats(args: argparse.Namespace) -> int:
    out_dir = Path(args.out) if args.out else OUT_DIR
    by_period: dict[str, Counter[tuple[int, str]]] = defaultdict(Counter)
    products: dict[str, set[str]] = defaultdict(set)
    categories: Counter[str] = Counter()
    seen: set[str] = set()
    years: Counter[int] = Counter()
    for f in sorted(out_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r["review_id"] in seen:
                continue
            seen.add(r["review_id"])
            per = r.get("period") or "boundary"
            by_period[per][(int(r["star"]), r.get("length_bucket") or length_bucket(r["content"]))] += 1
            products[per].add(r["product_id"])
            if per == "pre_chatgpt":
                categories[r.get("category") or "(미지정)"] += 1
                if r.get("created_at"):
                    years[int(r["created_at"][:4])] += 1
    pre = by_period.get("pre_chatgpt", Counter())
    print_table(f"쿠팡 2022-11-30 이전 (H1 · 사람 후보) · 상품 {len(products.get('pre_chatgpt', set()))}개", pre)
    if years:
        print("  작성 연도: " + ", ".join(f"{y}년 {n:,}" for y, n in sorted(years.items())))
    if categories:
        print("  카테고리: " + ", ".join(f"{c} {n:,}" for c, n in categories.most_common()))
    if by_period.get("post_chatgpt"):
        print_table(f"쿠팡 2023년 이후 (U1 · 라벨 없음) · 상품 {len(products['post_chatgpt'])}개", by_period["post_chatgpt"])
    naver = NAVER_DIR / "naver_shopping.jsonl"
    nv: Counter[tuple[int, str]] = Counter()
    if naver.exists():
        for line in naver.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            nv[(int(r["star"]), r["length_bucket"])] += 1
        print_table("네이버 쇼핑 (H2 · 사람 후보)", nv)
    h1 = sum(pre.values())
    print(f"\n목표(MODEL_DEV.md 4.2.2): H1 쿠팡 이전 리뷰 {h1:,} / 15,000 ({h1 / 150:.0f}%)"
          f" · H2 네이버는 사람 데이터의 40% 이하로만 사용 (보유 {sum(nv.values()):,})")
    thin = [f"{s}점-{b}" for s in STARS for b in "SML" if pre.get((s, b), 0) + (nv.get((s, b), 0) if s != 3 else 0) < 300]
    if thin:
        print("  칸당 300건 미만(사람 데이터): " + ", ".join(thin))
    return 0


def main(argv: list[str] | None = None) -> int:
    global CUTOFF
    ap = argparse.ArgumentParser(description="AI 탐지 모델 학습용 리뷰 데이터 수집기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="상품 목록에서 쿠팡 리뷰 수집 (이어서 수집 지원)")
    c.add_argument("products")
    c.add_argument("--per-star", type=int, default=PER_STAR, help=f"상품·별점당 2022-11-30 이전 리뷰 수 (기본 {PER_STAR})")
    c.add_argument("--post-per-star", type=int, default=POST_PER_STAR, help=f"상품·별점당 2023년 이후 리뷰 수 (기본 {POST_PER_STAR}, 0=안 함)")
    c.add_argument("--max-products", type=int, default=0, help="이번 실행에서 수집할 최대 상품 수")
    c.add_argument("--headless", action="store_true", help="브라우저 창 숨기기 (차단이 늘 수 있음)")
    i = sub.add_parser("inspect", help="상품 하나로 날짜순 정렬·이진 탐색 점검")
    i.add_argument("url")
    i.add_argument("--star", type=int, default=5)
    i.add_argument("--headless", action="store_true")
    n = sub.add_parser("naver", help="네이버 쇼핑 리뷰 20만 건 내려받기·변환")
    n.add_argument("--force", action="store_true", help="이미 받은 파일이 있어도 다시 받기")
    sub.add_parser("stats", help="모인 데이터 양 보기")
    for p in (c, n, sub.choices["stats"]):
        p.add_argument("--out", default="", help="결과 폴더 (기본 model/data/raw/…)")
    ap.add_argument("--cutoff", default=CUTOFF.isoformat(), help="사람 리뷰 기준일 (기본 2022-11-30)")
    args = ap.parse_args(argv)
    CUTOFF = date.fromisoformat(args.cutoff)
    return {"collect": cmd_collect, "inspect": cmd_inspect, "naver": cmd_naver, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
