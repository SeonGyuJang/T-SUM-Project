"""
쿠팡 상품 리뷰 수집기 (Scrapling 0.5.x 기준) - JSON API 방식

무엇을 수집하나
  - 상품명, 전체 리뷰 수, 별점별 리뷰 수(5~1점), 평균 별점(찾을 수 있으면)
  - 별점별로 최대 100개씩 리뷰: 구매한 상품(옵션), 별점, 리뷰 내용, 작성 날짜
    (해당 별점 리뷰가 100개보다 적으면 있는 만큼 전부)

어떻게 동작하나
  상품 페이지를 실제 브라우저로 연 뒤, 그 페이지 안에서 쿠팡이 리뷰를 불러올 때 쓰는
  /next-api/review API를 같은 쿠키로 호출합니다. 화면 HTML 구조가 바뀌어도 영향이 적습니다.

사용법
  pip install "scrapling[fetchers]"
  scrapling install

  # (1) 응답 구조 점검: 원본 JSON을 output/raw/ 에 저장하고, 필드를 제대로 찾았는지 보여줍니다.
  python coupang_reviews.py inspect "https://www.coupang.com/vp/products/9751850127"

  # (2) 수집: urls.txt 에 상품 URL을 한 줄에 하나씩
  python coupang_reviews.py collect urls.txt
  python coupang_reviews.py collect urls.txt --per-rating 50      # 별점당 50개

결과
  output/products/<상품ID>.json   상품별 결과 (이미 있으면 다음 실행 때 건너뜀)
  output/all_products.json        전체 상품 결과를 하나로 합친 파일
  output/failed.txt               실패한 URL과 이유
"""

import argparse
import json
import random
import re
import sys
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from scrapling.fetchers import StealthySession

# ──────────────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────────────
API_BASE = "https://www.coupang.com/next-api/review"
PAGE_SIZE = 10                 # 쿠팡 페이지가 쓰는 값 그대로
SORT_BY = "ORDER_SCORE_ASC"    # discover에서 확인된 기본 정렬값
PER_RATING_TARGET = 100        # 별점당 최대 수집 개수
MAX_PAGES_PER_RATING = 30      # 안전장치: 별점당 최대 페이지 수

API_DELAY_RANGE = (1.5, 3.5)   # API 호출 사이 대기(초)
PRODUCT_DELAY_RANGE = (5.0, 10.0)  # 상품 사이 대기(초)

OUTPUT_DIR = Path("output")
PRODUCT_DIR = OUTPUT_DIR / "products"
RAW_DIR = OUTPUT_DIR / "raw"
PROFILE_DIR = Path(".browser_profile")
KST = timezone(timedelta(hours=9))

# JSON 필드 이름 후보 (앞에 있을수록 우선). inspect 결과를 보고 필요하면 앞쪽에 추가하세요.
RATING_KEYS = ("rating", "ratingScore", "starRating", "score", "star")
CONTENT_KEYS = ("content", "reviewContent", "reviewText", "contents", "text", "body", "comment")
TITLE_KEYS = ("headline", "title", "reviewTitle")
DATE_KEYS = ("reviewAt", "reviewedAt", "createdAt", "registeredAt", "reviewDate",
             "createdDate", "regDate", "writtenAt", "createAt", "date")
OPTION_KEYS = ("itemName", "vendorItemName", "optionName", "productOption", "purchaseOption",
               "itemOption", "optionValue", "productName", "option")
ID_KEYS = ("reviewId", "id")
TOTAL_KEYS = ("totalCount", "totalReviewCount", "reviewCount", "ratingCount", "totalElements", "total")
AVERAGE_KEYS = ("ratingAverage", "averageRating", "avgRating", "ratingAvg", "averageScore", "average")
COUNT_KEYS = ("count", "ratingCount", "reviewCount", "totalCount", "cnt")

# 페이지 안에서 실행할 fetch (브라우저의 쿠키/헤더를 그대로 사용)
FETCH_JS = """async (url) => {
  const r = await fetch(url, {credentials: 'include',
                              headers: {'accept': 'application/json, text/plain, */*'}});
  return {status: r.status, text: await r.text()};
}"""


# ──────────────────────────────────────────────────────────────
# JSON 탐색 도우미 (필드 이름을 정확히 몰라도 찾아가도록)
# ──────────────────────────────────────────────────────────────
def walk(obj):
    """모든 dict / list 를 너비 우선으로 순회 (얕은 것부터)."""
    queue = deque([obj])
    while queue:
        cur = queue.popleft()
        yield cur
        if isinstance(cur, dict):
            queue.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            queue.extend(v for v in cur if isinstance(v, (dict, list)))


def get_field(d, keys, depth=2):
    """dict 에서 후보 키 값을 찾되, 없으면 하위 dict 까지 depth 만큼 내려가 찾는다."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    if depth > 0:
        for v in d.values():
            if isinstance(v, dict):
                found = get_field(v, keys, depth - 1)
                if found not in (None, "", [], {}):
                    return found
    return None


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize_date(v):
    """epoch(ms/s) 숫자나 문자열을 'YYYY-MM-DD HH:MM' 형태로."""
    if v is None:
        return ""
    n = to_int(v) if not isinstance(v, str) or v.isdigit() else None
    if n is not None:
        if n > 1e11:
            n /= 1000
        if n > 1e9:
            return datetime.fromtimestamp(n, KST).strftime("%Y-%m-%d %H:%M")
    return str(v).strip()


def option_text(v):
    if isinstance(v, list):
        return ", ".join(option_text(x) for x in v if x)
    if isinstance(v, dict):
        return ", ".join(str(x) for x in v.values() if isinstance(x, (str, int, float)) and x != "")
    return str(v).strip() if v is not None else ""


def find_review_list(data):
    """응답 안에서 '리뷰 목록'으로 보이는 가장 긴 리스트를 찾는다."""
    best = []
    for node in walk(data):
        if not isinstance(node, list) or not node:
            continue
        dicts = [x for x in node if isinstance(x, dict)]
        if len(dicts) < len(node) * 0.8:
            continue
        hits = sum(1 for x in dicts
                   if get_field(x, RATING_KEYS) is not None and get_field(x, CONTENT_KEYS) is not None)
        if hits >= max(1, len(dicts) * 0.5) and len(dicts) > len(best):
            best = dicts
    return best


def parse_review(item):
    rating = to_int(get_field(item, RATING_KEYS))
    content = get_field(item, CONTENT_KEYS)
    title = get_field(item, TITLE_KEYS)
    return {
        "review_id": str(get_field(item, ID_KEYS, depth=0) or ""),
        "rating": rating,
        "purchased_item": option_text(get_field(item, OPTION_KEYS)),
        "title": str(title).strip() if isinstance(title, str) else "",
        "content": str(content).strip() if content is not None else "",
        "date": normalize_date(get_field(item, DATE_KEYS)),
    }


def find_rating_counts(data):
    """별점별 리뷰 수 {5: n, 4: n, ...} 를 찾는다. 못 찾으면 None."""
    for node in walk(data):
        # 형태 1: {"5": 120, "4": 30, ...} 또는 {5: 120, ...}
        if isinstance(node, dict):
            keys = {str(k) for k in node.keys()}
            if {"1", "2", "3", "4", "5"} <= keys:
                counts = {r: to_int(node.get(str(r), node.get(r))) for r in range(5, 0, -1)}
                if all(c is not None for c in counts.values()):
                    return counts
        # 형태 2: [{"rating": 5, "count": 120}, ...]
        if isinstance(node, list) and 2 <= len(node) <= 6 and all(isinstance(x, dict) for x in node):
            counts = {}
            for x in node:
                r = to_int(get_field(x, RATING_KEYS, depth=0))
                c = to_int(get_field(x, COUNT_KEYS, depth=0))
                if r in (1, 2, 3, 4, 5) and c is not None:
                    counts[r] = c
            if len(counts) >= 2:
                return {r: counts.get(r, 0) for r in range(5, 0, -1)}
    return None


def find_number(data, keys, skip_lists=None):
    """리뷰 목록 바깥의 얕은 위치에서 숫자 필드를 찾는다."""
    skip = {id(x) for x in (skip_lists or [])}
    for node in walk(data):
        if isinstance(node, dict) and id(node) not in skip:
            for k in keys:
                if k in node and isinstance(node[k], (int, float, str)):
                    n = to_float(node[k])
                    if n is not None:
                        return n
    return None


def clean_product_name(og_title: str) -> str:
    name = og_title.replace(" | 쿠팡", "").strip()
    if " - " in name:
        name = name.rsplit(" - ", 1)[0]  # 뒤에 붙는 카테고리 제거
    return name.strip()


def product_id_from_url(url: str) -> str:
    m = re.search(r"/products/(\d+)", url)
    if not m:
        raise ValueError(f"상품 ID를 찾을 수 없는 URL: {url}")
    return m.group(1)


def review_api_url(pid: str, page: int, rating="") -> str:
    return API_BASE + "?" + urlencode({
        "productId": pid, "page": page, "size": PAGE_SIZE, "sortBy": SORT_BY,
        "ratingSummary": "true", "ratings": rating, "market": "",
    })


# ──────────────────────────────────────────────────────────────
# 브라우저 페이지 안에서 API 호출
# ──────────────────────────────────────────────────────────────
def api_get(page, url):
    res = page.evaluate(FETCH_JS, url)
    if res["status"] != 200:
        raise RuntimeError(f"API HTTP {res['status']} ({url})")
    try:
        return json.loads(res["text"])
    except json.JSONDecodeError:
        raise RuntimeError(f"JSON이 아닌 응답(차단 페이지일 수 있음): {res['text'][:120]!r}")


def pause(page, rng):
    page.wait_for_timeout(int(random.uniform(*rng) * 1000))


def warm_up(page):
    """사람처럼 조금 스크롤 (페이지가 리뷰 영역을 준비하도록)."""
    for _ in range(4):
        page.mouse.wheel(0, random.randint(500, 1000))
        page.wait_for_timeout(random.randint(400, 900))


def collect_summary(page, pid):
    data = api_get(page, review_api_url(pid, 1))
    reviews = find_review_list(data)
    counts = find_rating_counts(data)
    total = find_number(data, TOTAL_KEYS, skip_lists=reviews)
    avg = find_number(data, AVERAGE_KEYS, skip_lists=reviews)
    return data, {
        "total_reviews": int(total) if total is not None else None,
        "average_rating": avg,
        "rating_counts": counts,
    }


def collect_rating(page, pid, rating, target, log=print):
    """특정 별점의 리뷰를 target 개까지 수집. (첫 페이지 응답의 전체 개수도 함께 반환)"""
    got, seen, filtered_total, mismatched = [], set(), None, 0
    for page_no in range(1, MAX_PAGES_PER_RATING + 1):
        data = api_get(page, review_api_url(pid, page_no, rating=str(rating)))
        items = find_review_list(data)
        if page_no == 1:
            t = find_number(data, TOTAL_KEYS, skip_lists=items)
            filtered_total = int(t) if t is not None else None
        if not items:
            break
        new = 0
        for raw in items:
            r = parse_review(raw)
            key = r["review_id"] or (r["date"], r["content"][:80])
            if key in seen:
                continue
            seen.add(key)
            if r["rating"] is not None and r["rating"] != rating:
                mismatched += 1
            got.append(r)
            new += 1
            if len(got) >= target:
                break
        if len(got) >= target or new == 0 or len(items) < PAGE_SIZE:
            break
        pause(page, API_DELAY_RANGE)
    if mismatched > len(got) * 0.5:
        log(f"    ⚠ {rating}점 필터가 적용되지 않은 것 같습니다 "
            f"({len(got)}개 중 {mismatched}개가 다른 별점). 'ratings' 파라미터 형식을 확인하세요.")
    return got, filtered_total


def collect_product(session, url, per_rating, log=print):
    pid = product_id_from_url(url)
    state = {"error": None}

    def action(page):
        # page_action 안의 예외는 Scrapling이 로그만 남기고 삼키므로 직접 보관
        try:
            warm_up(page)
            _, summary = collect_summary(page, pid)
            state["summary"] = summary
            counts = summary["rating_counts"] or {}
            state["reviews"], state["filtered_totals"] = {}, {}
            for rating in (5, 4, 3, 2, 1):
                pause(page, API_DELAY_RANGE)
                known = counts.get(rating)
                if known == 0:
                    state["reviews"][rating], state["filtered_totals"][rating] = [], 0
                    continue
                target = min(per_rating, known) if known is not None else per_rating
                reviews, ftotal = collect_rating(page, pid, rating, target, log)
                state["reviews"][rating] = reviews
                state["filtered_totals"][rating] = ftotal
                log(f"    {rating}점: {len(reviews)}개 수집"
                    + (f" (전체 {known if known is not None else ftotal}개)"
                       if (known is not None or ftotal is not None) else ""))
        except Exception as e:
            state["error"] = e
        return page

    resp = session.fetch(url, page_action=action)
    if resp.status != 200:
        raise RuntimeError(f"상품 페이지 HTTP {resp.status} (차단되었을 수 있음)")
    if state["error"]:
        raise state["error"]

    og = resp.css('meta[property="og:title"]::attr(content)').get() or ""
    summary = state["summary"]

    # 요약 응답에서 별점별 개수를 못 찾았으면, 별점 필터 응답의 전체 개수로 채움
    if not summary["rating_counts"]:
        ft = state["filtered_totals"]
        if all(ft.get(r) is not None for r in range(1, 6)):
            summary["rating_counts"] = {r: ft[r] for r in range(5, 0, -1)}
            summary["rating_counts_source"] = "별점 필터 응답의 전체 개수"
    if summary["total_reviews"] is None and summary["rating_counts"]:
        summary["total_reviews"] = sum(summary["rating_counts"].values())
        summary["total_reviews_source"] = "별점별 개수 합계"

    reviews = [r for rating in (5, 4, 3, 2, 1) for r in state["reviews"].get(rating, [])]
    return {
        "product_id": pid,
        "product_name": clean_product_name(og),
        "url": url,
        "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_reviews": summary["total_reviews"],
            "average_rating": summary["average_rating"],
            "rating_counts": {str(k): v for k, v in (summary["rating_counts"] or {}).items()} or None,
            **{k: v for k, v in summary.items() if k.endswith("_source")},
        },
        "collected_counts": {str(r): len(state["reviews"].get(r, [])) for r in (5, 4, 3, 2, 1)},
        "reviews": reviews,
    }


def open_session(headless=False, **extra):
    return StealthySession(
        headless=headless,
        user_data_dir=str(PROFILE_DIR),
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        timeout=60000,
        retries=2,
        **extra,
    )


# ──────────────────────────────────────────────────────────────
# 명령: discover / inspect / collect
# ──────────────────────────────────────────────────────────────
def discover(url):
    """페이지가 보내는 리뷰 관련 요청 목록 확인 (API 주소가 바뀌었을 때용)."""
    def action(page):
        warm_up(page)
        page.wait_for_timeout(3000)
        return page

    with open_session(record_requests=True) as session:
        page = session.fetch(url, page_action=action, network_idle=True)
        print(f"[상태코드] {page.status}")
        for r in session.network.search(url_pattern=r"(?i)review", include_static=False, limit=None):
            print(f"  {r.status} {r.method} {r.url[:180]}")


def inspect(url):
    """원본 JSON 저장 + 필드 인식 결과 출력. 수집 결과가 비어 있으면 이걸로 확인하세요."""
    pid = product_id_from_url(url)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = {}

    def action(page):
        try:
            warm_up(page)
            out["summary_raw"], out["summary"] = collect_summary(page, pid)
            pause(page, API_DELAY_RANGE)
            out["r1_raw"] = api_get(page, review_api_url(pid, 1, rating="1"))
        except Exception as e:
            out["error"] = e
        return page

    with open_session() as session:
        session.fetch(url, page_action=action)
    if "error" in out:
        raise out["error"]

    (RAW_DIR / f"{pid}_summary.json").write_text(
        json.dumps(out["summary_raw"], ensure_ascii=False, indent=2), encoding="utf-8")
    (RAW_DIR / f"{pid}_rating1.json").write_text(
        json.dumps(out["r1_raw"], ensure_ascii=False, indent=2), encoding="utf-8")

    reviews = find_review_list(out["summary_raw"])
    print(f"[원본 저장] {RAW_DIR}/{pid}_summary.json, {pid}_rating1.json")
    print(f"[요약 인식] {json.dumps(out['summary'], ensure_ascii=False)}")
    print(f"[리뷰 목록] {len(reviews)}개 인식")
    if reviews:
        print(f"[원본 리뷰 키] {list(reviews[0].keys())}")
        print(f"[파싱 예시] {json.dumps(parse_review(reviews[0]), ensure_ascii=False)}")
    r1 = [parse_review(x)["rating"] for x in find_review_list(out["r1_raw"])]
    print(f"[ratings=1 필터 결과 별점] {r1}  ← 전부 1이면 필터 정상")

    missing = []
    if not out["summary"]["rating_counts"]:
        missing.append("별점별 개수")
    if out["summary"]["total_reviews"] is None:
        missing.append("전체 리뷰 수")
    if reviews:
        sample = parse_review(reviews[0])
        missing += [k for k in ("rating", "purchased_item", "content", "date") if not sample[k]]
    if missing:
        print(f"⚠ 못 찾은 항목: {missing} → 원본 JSON에서 해당 키 이름을 찾아 "
              f"파일 위쪽 *_KEYS 목록 맨 앞에 추가하세요.")


def collect(url_file, per_rating, headless):
    PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
    urls, seen_ids = [], set()
    for line_no, line in enumerate(Path(url_file).read_text(encoding="utf-8-sig").splitlines(), 1):
        u = line.strip()
        if not u or u.startswith("#"):
            continue
        m = re.search(r"/products/(\d+)", u)
        if not m:
            print(f"  ⚠ {line_no}번째 줄 건너뜀 (상품 페이지 주소가 아님): {u[:80]}")
            continue
        if m.group(1) in seen_ids:
            continue  # 같은 상품의 다른 옵션 링크는 한 번만
        seen_ids.add(m.group(1))
        urls.append(u)
    todo = [u for u in urls if not (PRODUCT_DIR / f"{product_id_from_url(u)}.json").exists()]
    print(f"전체 {len(urls)}개 / 완료 {len(urls) - len(todo)}개 / 남은 {len(todo)}개")

    with open_session(headless=headless) as session:
        for n, url in enumerate(todo, start=1):
            print(f"[{n}/{len(todo)}] {url}")
            try:
                result = collect_product(session, url, per_rating)
                path = PRODUCT_DIR / f"{result['product_id']}.json"
                path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                s = result["summary"]
                print(f"  ✓ {result['product_name'][:40]} | 전체 {s['total_reviews']}개 "
                      f"| 별점별 {s['rating_counts']} | 수집 {len(result['reviews'])}개")
            except Exception as e:
                print(f"  ✗ 실패: {e}")
                with (OUTPUT_DIR / "failed.txt").open("a", encoding="utf-8") as f:
                    f.write(f"{url}\t{e}\n")
            if n < len(todo):
                time.sleep(random.uniform(*PRODUCT_DELAY_RANGE))

    merged = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PRODUCT_DIR.glob("*.json"))]
    (OUTPUT_DIR / "all_products.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료 → {PRODUCT_DIR}/, {OUTPUT_DIR/'all_products.json'}")


def main():
    ap = argparse.ArgumentParser(description="쿠팡 상품 리뷰 수집기 (JSON)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover", help="리뷰 관련 요청 목록 보기").add_argument("url")
    sub.add_parser("inspect", help="API 응답 구조 점검").add_argument("url")
    c = sub.add_parser("collect", help="URL 목록 수집")
    c.add_argument("url_file")
    c.add_argument("--per-rating", type=int, default=PER_RATING_TARGET, help="별점당 최대 개수 (기본 100)")
    c.add_argument("--headless", action="store_true", help="브라우저 창 숨기기 (차단이 늘 수 있음)")
    args = ap.parse_args()

    if args.cmd == "discover":
        discover(args.url)
    elif args.cmd == "inspect":
        inspect(args.url)
    else:
        collect(args.url_file, args.per_rating, args.headless)


if __name__ == "__main__":
    sys.exit(main())