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
  python coupang_reviews.py collect urls.txt --real-chrome        # 설치된 Chrome 사용 (권장)

차단 대응
  - 요청 간격을 넉넉히 두고, 상품 3개마다 2~4분 쉽니다.
  - 쿠팡이 막으면(403/429) 브라우저를 닫고 5분 → 15분 → 30분 쉬었다가 이어서 수집합니다.
    세 번 쉬어도 막히면 그날은 멈춥니다. 몇 시간 뒤 다시 실행하세요.
  - 별점 하나를 끝낼 때마다 output/products/<상품ID>.partial.json 에 저장하므로,
    차단이나 Ctrl+C로 멈춰도 다시 실행하면 끝난 별점은 건너뛰고 이어서 합니다.

결과
  output/products/<상품ID>.json   상품별 결과 (이미 있으면 다음 실행 때 건너뜀)
                                  {"상품정보": {전체/별점별 리뷰 개수 ...}, "리뷰": [ {...}, ... ]}
  output/all_products.json        전체 상품 결과를 하나로 합친 파일
  output/failed.txt               실패한 URL과 이유
"""

import argparse
import json
import random
import re
import shutil
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
EXTRA_PAGES = 5                # 목표 페이지 수 외에 더 넘겨 볼 여유 페이지
PAGE_RETRIES = 4               # 한 페이지가 빈 응답/오류일 때 시도 횟수
RETRY_BACKOFF = (5, 15, 30)    # 재시도 전 대기(초): 점점 길게

# 속도 설정: 차단은 대부분 "짧은 시간에 너무 많은 요청" 때문입니다. 줄이지 마세요.
API_DELAY_RANGE = (2.5, 5.0)       # API 호출 사이 대기(초)
PRODUCT_DELAY_RANGE = (20.0, 40.0)  # 상품 사이 대기(초)
LONG_BREAK_EVERY = 3                # 상품 N개마다
LONG_BREAK_RANGE = (120, 240)       # 길게 쉬기(초)

# 차단 대응
BLOCK_STATUSES = {401, 403, 407, 429, 444, 503}
SOFT_BLOCK_WAIT = 30                # 차단 응답을 처음 받았을 때 잠깐 쉬는 시간(초)
BLOCK_COOLDOWNS = (300, 900, 1800)  # 차단이 계속되면 브라우저를 닫고 쉬는 시간(초): 5분 → 15분 → 30분

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
WRITER_KEYS = ("displayName", "displayWriter", "name", "nickname", "memberName")
PHOTO_LIST_KEYS = ("attachments", "imageAttachments", "photos", "images")
PHOTO_URL_KEYS = ("imgSrcThumbnail", "thumbnailPath", "thumbnail", "thumbnailUrl",
                  "imgSrcOrigin", "imagePath", "imageUrl", "imgSrc", "url", "path")
PHOTO_URL_PREFIX = "https://thumbnail.coupangcdn.com/thumbnails/local/320/"  # 상대 경로일 때 붙임

# 리뷰 작성자 이름을 가릴지 여부 (True: 한송희 → 한*희)
MASK_CUSTOMER_NAME = True

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


def normalize_date(v, fmt="%Y년%m월%d일"):
    """epoch(ms/s) 숫자나 날짜 문자열을 '2026년09월09일' 형태로."""
    if v is None:
        return ""
    n = to_int(v) if not isinstance(v, str) or v.isdigit() else None
    if n is not None:
        if n > 1e11:
            n /= 1000
        if n > 1e9:
            return datetime.fromtimestamp(n, KST).strftime(fmt)
    s = str(v).strip()
    m = re.match(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", s)
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3])).strftime(fmt)
    return s


def mask_name(name: str) -> str:
    name = (name or "").strip()
    if not MASK_CUSTOMER_NAME or len(name) < 2 or "*" in name:
        return name
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def writer_name(item) -> str:
    v = get_field(item, WRITER_KEYS, depth=0)
    if v is None and isinstance(item.get("member"), dict):
        v = get_field(item["member"], WRITER_KEYS, depth=1)
    return mask_name(v if isinstance(v, str) else "")


def photo_urls(item) -> list:
    """리뷰 첨부 이미지 URL 목록."""
    atts = get_field(item, PHOTO_LIST_KEYS, depth=0) or []
    if isinstance(atts, dict):
        atts = [atts]
    urls = []
    for a in atts if isinstance(atts, list) else []:
        cand = None
        if isinstance(a, str):
            cand = a
        elif isinstance(a, dict):
            cand = get_field(a, PHOTO_URL_KEYS, depth=1)
            if not isinstance(cand, str):  # 키 이름을 모를 때: 이미지처럼 생긴 문자열 아무거나
                cand = next((v for v in a.values() if isinstance(v, str)
                             and re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", v, re.I)), None)
        if not isinstance(cand, str) or not cand.strip():
            continue
        cand = cand.strip()
        if cand.startswith("//"):
            cand = "https:" + cand
        elif not cand.startswith("http"):
            cand = PHOTO_URL_PREFIX + cand.lstrip("/")
        if cand not in urls:
            urls.append(cand)
    return urls


def format_rating(v) -> str:
    if v is None:
        return ""
    f = round(float(v), 1)
    return str(int(f)) if f == int(f) else str(f)


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
        # 별점 + (리뷰 ID 또는 본문)이 있으면 리뷰로 인정. 본문 없이 별점만 남긴 리뷰도 포함.
        hits = sum(1 for x in dicts
                   if get_field(x, RATING_KEYS, depth=1) is not None
                   and (get_field(x, ID_KEYS, depth=0) is not None
                        or get_field(x, CONTENT_KEYS) is not None))
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
        "writer": writer_name(item),
        "photos": photo_urls(item),
    }


def to_output_review(r, product_name, url, total, avg):
    """첨부해 주신 JSON 형식으로 변환 (모든 값은 문자열)."""
    return {
        "고객_아이디": r["writer"],
        "고객_평점": str(r["rating"]) if r["rating"] is not None else "",
        "구매상품": r["purchased_item"],
        "단가_와우": "",
        "단가_쿠팡": "",
        "리뷰_작성_시간": r["date"],
        "리뷰_제목": r["title"],
        "상세리뷰": r["content"],
        "상품": product_name,
        "상품_URL": url,
        "상품평_개수": str(total) if total is not None else "",
        "와우할인가": "",
        "전체_평점": format_rating(avg),
        "쿠팡판매가": "",
        "포토리뷰": json.dumps(r["photos"], ensure_ascii=False),
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
class Blocked(Exception):
    """쿠팡이 요청을 막았을 때 (403/429 같은 상태코드, 또는 차단 페이지)."""


class BrowserClosed(Exception):
    """브라우저 탭/창이 닫혀 더 진행할 수 없을 때."""


def is_closed_error(e) -> bool:
    msg = str(e).lower()
    return "has been closed" in msg or "target closed" in msg or "connection closed" in msg


def api_get(page, url):
    res = page.evaluate(FETCH_JS, url)
    status = res["status"]
    if status in BLOCK_STATUSES:
        raise Blocked(f"API HTTP {status}")
    if status != 200:
        raise RuntimeError(f"API HTTP {status}")
    try:
        return json.loads(res["text"])
    except json.JSONDecodeError:
        text = res["text"][:300]
        if re.search(r"(?i)access denied|<html|captcha", text):
            raise Blocked("차단 페이지(HTML) 응답")
        raise RuntimeError(f"JSON이 아닌 응답: {text[:120]!r}")


def pause(page, rng):
    page.wait_for_timeout(int(random.uniform(*rng) * 1000))


def warm_up(page):
    """사람처럼 조금 스크롤 (페이지가 리뷰 영역을 준비하도록)."""
    for _ in range(4):
        page.mouse.wheel(0, random.randint(500, 1000))
        page.wait_for_timeout(random.randint(400, 900))


def save_debug(pid, rating, page_no, attempt, data):
    """이상한 응답을 output/raw/debug/ 에 저장 (원인 확인용)."""
    d = RAW_DIR / "debug"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}_r{rating}_p{page_no}_try{attempt}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) if not isinstance(data, str) else data,
        encoding="utf-8")


def call_with_retry(page, label, fn, log=print, debug_key=None):
    """fn()을 호출하고, 빈 응답이면 간격을 늘려 재시도한다.
    차단(Blocked)이면 한 번만 잠깐 쉬었다 다시 해 보고, 그래도 막히면 Blocked를 위로 올린다.
    끝까지 빈 응답이면 None."""
    blocked_once = False
    for attempt in range(1, PAGE_RETRIES + 1):
        try:
            result = fn()
            if result is not None:
                return result
            reason = "빈 응답"
        except Blocked as e:
            if debug_key:
                save_debug(*debug_key, attempt, str(e))
            if blocked_once:
                raise
            blocked_once = True
            log(f"      ⏸ {label} {e} → {SOFT_BLOCK_WAIT}초 쉬고 한 번 더 시도")
            page.wait_for_timeout(SOFT_BLOCK_WAIT * 1000)
            continue
        except Exception as e:
            if is_closed_error(e):
                raise BrowserClosed(str(e)[:120]) from e
            reason = str(e)[:80]
        if debug_key:
            save_debug(*debug_key, attempt, reason)
        if attempt == PAGE_RETRIES:
            break
        wait = RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)]
        log(f"      ↻ {label} {reason} → {wait}초 후 재시도 ({attempt}/{PAGE_RETRIES - 1})")
        page.wait_for_timeout(wait * 1000)
    return None


def collect_summary(page, pid, log=print):
    """전체 리뷰 수 / 별점별 개수 / 평균 별점."""
    holder = {}

    def once():
        data = api_get(page, review_api_url(pid, 1))
        reviews = find_review_list(data)
        counts = find_rating_counts(data)
        total = find_number(data, TOTAL_KEYS, skip_lists=reviews)
        avg = find_number(data, AVERAGE_KEYS, skip_lists=reviews)
        holder["data"] = data
        holder["info"] = {"total_reviews": int(total) if total is not None else None,
                          "average_rating": avg, "rating_counts": counts}
        return holder["info"] if counts and sum(counts.values()) > 0 else None

    info = call_with_retry(page, "요약 정보", once, log, debug_key=(pid, "summary", 1))
    if info is None and "info" not in holder:
        raise RuntimeError("요약 정보를 가져오지 못함 (output/raw/debug/ 확인)")
    # 별점별 개수를 못 찾았어도 나머지로 진행 (별점 필터 응답 개수로 보완)
    return holder.get("data"), info or holder["info"]


def fetch_review_page(page, pid, rating, page_no, log=print):
    """리뷰 한 페이지. 빈 응답이면 재시도, 끝까지 실패하면 (None, None). 차단이면 Blocked."""
    def once():
        data = api_get(page, review_api_url(pid, page_no, rating=str(rating)))
        items = find_review_list(data)
        return (data, items) if items else None

    result = call_with_retry(page, f"{rating}점 {page_no}페이지", once, log,
                             debug_key=(pid, rating, page_no))
    return result if result else (None, None)


def collect_rating(page, pid, rating, target, log=print):
    """특정 별점의 리뷰를 target 개까지 수집. (첫 페이지 응답의 전체 개수도 함께 반환)

    target 개를 채우거나, 쿠팡이 실제로 더 줄 리뷰가 없을 때만 멈춘다.
    """
    got, seen, filtered_total, mismatched = [], set(), None, 0
    no_new_streak = failed_pages = 0
    max_pages = -(-target // PAGE_SIZE) + EXTRA_PAGES  # 올림 + 여유
    page_no = 0

    def absorb(batch):
        nonlocal mismatched
        added = 0
        for raw in batch:
            if len(got) >= target:
                break
            r = parse_review(raw)
            key = r["review_id"] or (r["date"], r["content"][:80])
            if key in seen:
                continue
            seen.add(key)
            if r["rating"] is not None and r["rating"] != rating:
                mismatched += 1
            got.append(r)
            added += 1
        return added

    while len(got) < target and page_no < max_pages:
        page_no += 1
        data, items = fetch_review_page(page, pid, rating, page_no, log)
        if items is None:
            failed_pages += 1
            log(f"      ✗ {rating}점 {page_no}페이지를 끝내 못 가져옴 (output/raw/debug/ 확인)")
            if failed_pages >= 2:
                break
            continue  # 한 페이지는 건너뛰고 다음 페이지에서 채워 봄
        if filtered_total is None:
            t = find_number(data, TOTAL_KEYS, skip_lists=items)
            filtered_total = int(t) if t is not None else None
            if filtered_total is not None:  # 필터 응답이 알려 준 실제 개수로 목표 보정
                target = min(target, filtered_total)
                max_pages = -(-target // PAGE_SIZE) + EXTRA_PAGES

        new = absorb(items)
        # 10개보다 적게 왔는데 아직 목표에 못 미치면, 같은 페이지를 다시 요청해 빠진 리뷰 보충
        refill = 0
        while len(items) < PAGE_SIZE and len(got) < target and refill < 2:
            refill += 1
            pause(page, API_DELAY_RANGE)
            _, again = fetch_review_page(page, pid, rating, page_no, log)
            if not again:
                break
            new += absorb(again)
            items = again if len(again) > len(items) else items
        # 같은 리뷰만 계속 오면(마지막 페이지를 넘김) 3번 연속일 때 멈춤
        no_new_streak = 0 if new else no_new_streak + 1
        if no_new_streak >= 3:
            break
        if len(got) < target:
            pause(page, API_DELAY_RANGE)

    if mismatched > len(got) * 0.5:
        log(f"    ⚠ {rating}점 필터가 적용되지 않은 것 같습니다 "
            f"({len(got)}개 중 {mismatched}개가 다른 별점). 'ratings' 파라미터 형식을 확인하세요.")
    return got, filtered_total, target


# ── 진행 상황 저장 (차단·중단 후 이어서 수집) ─────────────────────
def partial_path(pid):
    return PRODUCT_DIR / f"{pid}.partial.json"


def load_partial(pid):
    p = partial_path(pid)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        summ = d.get("summary")
        if summ and summ.get("rating_counts"):
            summ["rating_counts"] = {int(k): v for k, v in summ["rating_counts"].items()}
        return {
            "summary": summ,
            "og": d.get("og", ""),
            "reviews": {int(k): v for k, v in d.get("reviews", {}).items()},
            "filtered_totals": {int(k): v for k, v in d.get("filtered_totals", {}).items()},
            "shortfalls": {int(k): tuple(v) for k, v in d.get("shortfalls", {}).items()},
        }
    except Exception:
        return None


def save_partial(pid, state):
    PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
    summ = dict(state["summary"]) if state.get("summary") else None
    if summ and summ.get("rating_counts"):
        summ["rating_counts"] = {str(k): v for k, v in summ["rating_counts"].items()}
    data = {
        "summary": summ,
        "og": state.get("og", ""),
        "reviews": {str(k): v for k, v in state["reviews"].items()},
        "filtered_totals": {str(k): v for k, v in state["filtered_totals"].items()},
        "shortfalls": {str(k): list(v) for k, v in state["shortfalls"].items()},
    }
    tmp = partial_path(pid).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(partial_path(pid))  # 쓰는 도중 중단돼도 파일이 깨지지 않게


def fallback_name(state):
    """상품 페이지가 막혀 og:title을 못 읽었을 때: 리뷰의 구매 옵션 중 가장 흔한 값."""
    names = [r["purchased_item"] for rs in state["reviews"].values() for r in rs if r["purchased_item"]]
    return max(set(names), key=names.count) if names else ""


def collect_product(session, url, per_rating, log=print):
    pid = product_id_from_url(url)
    saved = load_partial(pid) or {}
    state = {
        "error": None,
        "summary": saved.get("summary"),
        "og": saved.get("og", ""),
        "reviews": saved.get("reviews", {}),
        "filtered_totals": saved.get("filtered_totals", {}),
        "shortfalls": saved.get("shortfalls", {}),
    }
    done = [r for r in state["reviews"] if r not in state["shortfalls"]]
    if done:
        log(f"    ↪ 이전에 끝낸 별점 이어서 건너뜀: {', '.join(f'{r}점' for r in sorted(done, reverse=True))}")

    def action(page):
        # page_action 안의 예외는 Scrapling이 로그만 남기고 삼키므로 직접 보관
        try:
            if not state["og"]:
                try:
                    state["og"] = page.locator('meta[property="og:title"]').first.get_attribute(
                        "content", timeout=3000) or ""
                except Exception:
                    pass
            warm_up(page)
            if not state["summary"]:
                _, state["summary"] = collect_summary(page, pid, log)
                save_partial(pid, state)
            counts = state["summary"]["rating_counts"] or {}
            for rating in (5, 4, 3, 2, 1):
                if rating in state["reviews"] and rating not in state["shortfalls"]:
                    continue  # 이미 끝난 별점
                state["shortfalls"].pop(rating, None)
                known = counts.get(rating)
                if known == 0:
                    state["reviews"][rating], state["filtered_totals"][rating] = [], 0
                    save_partial(pid, state)
                    continue
                pause(page, API_DELAY_RANGE)
                target = min(per_rating, known) if known is not None else per_rating
                reviews, ftotal, final_target = collect_rating(page, pid, rating, target, log)
                state["reviews"][rating] = reviews
                state["filtered_totals"][rating] = ftotal
                if len(reviews) < final_target:
                    state["shortfalls"][rating] = (len(reviews), final_target)
                save_partial(pid, state)  # 별점 하나 끝날 때마다 저장
                total_txt = known if known is not None else ftotal
                mark = "✓" if len(reviews) >= final_target else "⚠ 목표 미달"
                log(f"    {rating}점: {len(reviews)}/{final_target}개 수집 {mark}"
                    + (f" (전체 {total_txt}개)" if total_txt is not None else ""))
        except Exception as e:
            state["error"] = e
        return page

    try:
        resp = session.fetch(url, page_action=action)
    except Exception as e:
        if is_closed_error(e):
            raise BrowserClosed(str(e)[:120]) from e
        raise
    if state["error"]:
        raise state["error"]
    if not state["summary"]:
        if resp.status in BLOCK_STATUSES:
            raise Blocked(f"상품 페이지 HTTP {resp.status}")
        raise RuntimeError(f"리뷰 정보를 못 가져옴 (상품 페이지 HTTP {resp.status})")
    if resp.status != 200:
        # 리뷰 API는 정상이었으므로 결과를 버리지 않는다 (이전 버전에서 이것 때문에 실패 처리됨)
        log(f"    (참고) 상품 페이지 응답은 {resp.status}였지만 리뷰는 정상 수집되어 저장합니다")

    summary = state["summary"]
    if not summary["rating_counts"]:  # 요약 응답에 별점별 개수가 없으면 필터 응답 개수로 채움
        ft = state["filtered_totals"]
        if all(ft.get(r) is not None for r in range(1, 6)):
            summary["rating_counts"] = {r: ft[r] for r in range(5, 0, -1)}
    if summary["total_reviews"] is None and summary["rating_counts"]:
        summary["total_reviews"] = sum(summary["rating_counts"].values())

    og = state["og"] or resp.css('meta[property="og:title"]::attr(content)').get() or ""
    name = clean_product_name(og) or fallback_name(state)
    total, avg = summary["total_reviews"], summary["average_rating"]
    counts = summary["rating_counts"] or {}
    reviews = [to_output_review(r, name, url, total, avg)
               for rating in (5, 4, 3, 2, 1) for r in state["reviews"].get(rating, [])]
    return {
        "상품정보": {
            "상품ID": pid,
            "상품명": name,
            "상품_URL": url,
            "전체_평점": format_rating(avg),
            "전체_리뷰_개수": total,
            "별점별_리뷰_개수": {f"{r}점": counts.get(r) for r in (5, 4, 3, 2, 1)},
            "수집된_리뷰_개수": {f"{r}점": len(state["reviews"].get(r, [])) for r in (5, 4, 3, 2, 1)},
            "수집_완료": not state["shortfalls"],
            "목표_미달": {f"{r}점": f"{g}/{t}" for r, (g, t) in state["shortfalls"].items()},
            "수집_시각": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        },
        "리뷰": reviews,
    }


def open_session(headless=False, real_chrome=False, **extra):
    return StealthySession(
        headless=headless,
        real_chrome=real_chrome,   # 설치된 실제 Chrome 사용 (지문이 더 자연스러움)
        user_data_dir=str(PROFILE_DIR),
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        timeout=60000,
        retries=1,                 # 재시도는 이 스크립트가 직접 관리 (Scrapling 자동 재시도는
                                   # 수집 전체를 처음부터 다시 돌려서 꺼 둠)
        **extra,
    )


class BrowserRunner:
    """브라우저 세션을 열고, 차단되면 닫았다가 다시 여는 관리자."""

    def __init__(self, headless=False, real_chrome=False):
        self.headless, self.real_chrome = headless, real_chrome
        self.session = None

    def start(self, fresh_profile=False):
        self.close()
        if fresh_profile and PROFILE_DIR.exists():
            # 이 스크립트가 만든 브라우저 프로필 폴더만 지움 (차단 표시가 남은 쿠키 제거)
            shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        self.session = open_session(headless=self.headless, real_chrome=self.real_chrome)
        self.session.start()
        return self.session

    def close(self):
        if self.session is not None:
            try:
                self.session.close()
            except Exception:
                pass  # 이미 닫힌 브라우저를 닫다가 나는 오류는 무시
            self.session = None


def cooldown(seconds, reason):
    end = time.time() + seconds
    print(f"  ⏸ {reason} → {seconds // 60}분 {seconds % 60}초 쉬었다가 이어서 합니다 (Ctrl+C로 중단 가능)")
    while (left := int(end - time.time())) > 0:
        print(f"\r    남은 시간 {left // 60:02d}:{left % 60:02d} ", end="", flush=True)
        time.sleep(min(5, left))
    print("\r    다시 시작합니다.          ")


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
        s = out["summary"]
        sample_out = to_output_review(parse_review(reviews[0]), "(상품명)", url,
                                      s["total_reviews"], s["average_rating"])
        sample_out["상세리뷰"] = sample_out["상세리뷰"][:60] + "…"
        print(f"[출력 형식 예시] {json.dumps(sample_out, ensure_ascii=False, indent=2)}")
        # 작성자 / 사진 필드 확인용 원본 일부
        r0 = reviews[0]
        print(f"[원본 작성자 필드] displayName={r0.get('displayName')!r}, "
              f"displayWriter={str(r0.get('displayWriter'))[:80]!r}, member={str(r0.get('member'))[:80]!r}")
        with_photo = next((x for x in reviews if get_field(x, PHOTO_LIST_KEYS, depth=0)), None)
        if with_photo:
            att = get_field(with_photo, PHOTO_LIST_KEYS, depth=0)
            print(f"[원본 사진 첨부 예시] {json.dumps(att[:1] if isinstance(att, list) else att, ensure_ascii=False)[:400]}")
            print(f"[사진 URL 인식] {photo_urls(with_photo)[:3]}")
        else:
            print("[사진 첨부] 이 페이지의 리뷰 10개에는 사진이 없습니다.")
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


def collect(url_file, per_rating, headless, real_chrome=False):
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

    def is_done(u):
        path = PRODUCT_DIR / f"{product_id_from_url(u)}.json"
        if not path.exists():
            return False
        try:  # 목표에 못 미친 상품은 다시 수집
            return json.loads(path.read_text(encoding="utf-8"))["상품정보"].get("수집_완료", True)
        except Exception:
            return False

    todo = [u for u in urls if not is_done(u)]
    print(f"전체 {len(urls)}개 / 완료 {len(urls) - len(todo)}개 / 남은 {len(todo)}개")

    runner = BrowserRunner(headless=headless, real_chrome=real_chrome)
    blocks_in_a_row = closed_retries = 0
    finished_since_break = 0
    try:
        runner.start()
        n = 0
        while n < len(todo):
            url = todo[n]
            print(f"[{n + 1}/{len(todo)}] {url}")
            try:
                result = collect_product(runner.session, url, per_rating)
            except Blocked as e:
                blocks_in_a_row += 1
                if blocks_in_a_row > len(BLOCK_COOLDOWNS):
                    print(f"  ✗ {blocks_in_a_row - 1}번 쉬어도 계속 막힙니다 ({e}). 오늘은 여기서 멈춥니다.")
                    print("    진행 상황은 저장되어 있으니, 몇 시간 뒤 같은 명령을 다시 실행하면 이어서 수집합니다.")
                    break
                runner.close()
                cooldown(BLOCK_COOLDOWNS[blocks_in_a_row - 1], f"쿠팡이 요청을 막았습니다 ({e})")
                # 두 번째 차단부터는 쿠키를 새로 받기 위해 브라우저 프로필을 초기화
                runner.start(fresh_profile=blocks_in_a_row >= 2)
                continue  # 같은 상품을 저장된 지점부터 다시
            except BrowserClosed as e:
                closed_retries += 1
                if closed_retries <= 2:
                    print(f"  ↻ 브라우저가 닫혔습니다. 새로 띄워서 저장된 지점부터 다시 합니다 ({closed_retries}/2)")
                    runner.start()
                    continue
                e = f"브라우저가 계속 닫힘: {e}"
                print(f"  ✗ 실패: {e}")
                with (OUTPUT_DIR / "failed.txt").open("a", encoding="utf-8") as f:
                    f.write(f"{url}\t{e}\n")
                runner.start()
                closed_retries = 0
                n += 1
                continue
            except Exception as e:
                print(f"  ✗ 실패: {e}")
                with (OUTPUT_DIR / "failed.txt").open("a", encoding="utf-8") as f:
                    f.write(f"{url}\t{e}\n")
                n += 1
                continue

            blocks_in_a_row = closed_retries = 0
            info = result["상품정보"]
            path = PRODUCT_DIR / f"{info['상품ID']}.json"
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            if info["수집_완료"]:
                partial_path(info["상품ID"]).unlink(missing_ok=True)
                status = "✓"
            else:
                status = f"⚠ 일부 미달 {info['목표_미달']} (다음 실행 때 그 별점만 다시 수집)"
            print(f"  {status} {info['상품명'][:40]} | 전체 {info['전체_리뷰_개수']}개 "
                  f"| 별점별 {info['별점별_리뷰_개수']} | 수집 {len(result['리뷰'])}개")

            n += 1
            finished_since_break += 1
            if n < len(todo):
                if finished_since_break >= LONG_BREAK_EVERY:
                    finished_since_break = 0
                    cooldown(random.randint(*LONG_BREAK_RANGE), f"상품 {LONG_BREAK_EVERY}개마다 쉬는 시간")
                else:
                    wait = random.uniform(*PRODUCT_DELAY_RANGE)
                    print(f"  … 다음 상품까지 {wait:.0f}초 대기")
                    time.sleep(wait)
    except KeyboardInterrupt:
        print("\n중단했습니다. 지금까지 진행한 내용은 저장되어 있고, 다시 실행하면 이어서 수집합니다.")
    finally:
        runner.close()
        merged = [json.loads(p.read_text(encoding="utf-8"))
                  for p in sorted(PRODUCT_DIR.glob("*.json")) if not p.name.endswith(".partial.json")]
        (OUTPUT_DIR / "all_products.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장 위치 → {PRODUCT_DIR}/, {OUTPUT_DIR/'all_products.json'} (상품 {len(merged)}개)")


def main():
    ap = argparse.ArgumentParser(description="쿠팡 상품 리뷰 수집기 (JSON)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover", help="리뷰 관련 요청 목록 보기").add_argument("url")
    sub.add_parser("inspect", help="API 응답 구조 점검").add_argument("url")
    c = sub.add_parser("collect", help="URL 목록 수집")
    c.add_argument("url_file")
    c.add_argument("--per-rating", type=int, default=PER_RATING_TARGET, help="별점당 최대 개수 (기본 100)")
    c.add_argument("--headless", action="store_true", help="브라우저 창 숨기기 (차단이 늘 수 있음)")
    c.add_argument("--real-chrome", action="store_true",
                   help="설치된 실제 Chrome으로 실행 (차단이 줄어드는 경우가 많음, Chrome 설치 필요)")
    args = ap.parse_args()

    if args.cmd == "discover":
        discover(args.url)
    elif args.cmd == "inspect":
        inspect(args.url)
    else:
        collect(args.url_file, args.per_rating, args.headless, args.real_chrome)


if __name__ == "__main__":
    sys.exit(main())