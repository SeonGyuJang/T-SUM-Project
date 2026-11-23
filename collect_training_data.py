"""
AI 탐지 모델 학습용 리뷰 데이터 수집기

model/MODEL_DEV.md 4.2(데이터 설계)의 원천 데이터를 모은다.
  H1  쿠팡 리뷰, 작성일 < 2022-11-30 (ChatGPT 공개 이전)  → 사람(human) 후보   [collect]
  U1  쿠팡 리뷰, 작성일 ≥ 2023-01-01                      → 라벨 없음(추세 점검) [collect --post-per-star]
  H2  네이버 쇼핑 리뷰 20만 건 (2020.06~07 수집)             → 사람(human) 후보   [naver]

쿠팡 접속은 coupang_reviews.py(서비스용 수집기)의 함수를 그대로 가져다 쓴다(같은 브라우저 프로필·같은 API 방식).
이 파일은 coupang_reviews.py를 고치지 않는다.

어떻게 2022-11-30 이전 리뷰를 찾나
  쿠팡은 리뷰 목록 하나(정렬 × 별점)마다 최신 1,500개까지만 보여 준다(그 뒤 페이지는 빈 응답).
  그래서 목록마다 1,500번째 리뷰(리뷰가 더 적으면 마지막 리뷰)까지 가서 그 날짜를 본다.
    · 그 날짜가 2022-11-30 이후 → 그 목록에는 가져올 과거 리뷰가 없다.
    · 이전 → "처음으로 2022-11-30 이전 리뷰가 나오는 페이지"를 이진 탐색으로 찾고, 거기서부터 1,500번째까지
      페이지를 고르게 골라 담는다(2018~2022년이 한쪽에 몰리지 않게).
  상품 확인(category 모드): 상품 전체 목록(최신순)으로 먼저 본다.
    · 리뷰 1,500개 이하 → 마지막 리뷰가 2022-11-30 이후면 그 상품은 수집할 리뷰가 없다(요청 2회로 끝).
    · 1,500개 초과 → 1,500번째 리뷰가 이후여도 별점별 목록은 각자 최신 1,500개씩 보여 주므로(1~4점은 리뷰가 적어
      더 옛날까지 닿는다) 별점마다 같은 방법으로 확인한다. --quick-skip 을 주면 이 경우도 바로 건너뛴다.
  쿠팡 4·1점처럼 최신순을 요청해도 날짜가 섞여 나오는 목록은 1,500개 안 어디에나 과거 리뷰가 있을 수 있어서
  앞에서부터 훑는다(최대 --scan-pages 페이지).

사용법 (coupang_reviews.py와 같은 파이썬·같은 폴더에서)
  python collect_training_data.py naver                              # 네이버 쇼핑 데이터 받기·변환
  python collect_training_data.py inspect "<쿠팡 상품 URL>"          # 날짜순 정렬·페이지 이동 점검 (먼저 한 번)
  python collect_training_data.py category training_categories.txt   # 카테고리 안 상품을 전부 돌며 과거 리뷰가 있으면 수집
  python collect_training_data.py category training_categories.txt --workers 3   # 브라우저 3개로 나눠서
  python collect_training_data.py category "https://www.coupang.com/np/categories/194276" --name 식품
  python collect_training_data.py collect training_products.txt      # 상품 목록 수집 (중단 후 다시 실행하면 이어서)
  python collect_training_data.py collect training_products.txt --per-star 30 --post-per-star 10
  python collect_training_data.py stats                              # 모인 양 보기
  python collect_training_data.py chrome                             # 원격 연결용 Chrome 띄우기 (Mac)
  python collect_training_data.py collect training_products.txt --cdp-url http://localhost:9222   # 그 Chrome에 붙어서 수집

탐지 회피 (기본으로 항상 켬)
  1. 자동화 흔적 제거  설치된 실제 Chrome으로 실행(없으면 내장 Chromium), navigator.webdriver·CDP 노출 숨김(Scrapling),
                      요청 사이사이 마우스 이동·스크롤·잠깐 멈춤 같은 사람 동작
  2. 지문 위장        WebRTC로 로컬 IP가 새지 않게 차단, 고정 1920×1080 대신 실제 창·화면 크기, 한국어·서울 시간대,
                      캔버스 노이즈(내장 Chromium에서만 효과. 실제 Chrome에서는 효과 없음을 확인함)
  3. 원격 브라우저    python collect_training_data.py chrome  으로 Mac의 Chrome을 전용 프로필로 띄운 뒤
                      --cdp-url http://localhost:9222  를 붙여 실행하면 그 Chrome에 붙어서 수집한다.
                      (Chrome 136부터 평소 쓰는 기본 프로필로는 원격 연결 포트가 열리지 않아 전용 프로필을 쓴다)
  끄려면 --no-real-chrome(내장 Chromium 사용). 프록시 로테이션은 넣지 않았다.

병렬 수집
  --workers N : 브라우저 N개를 띄워 상품을 나눠 맡는다(같은 PC·같은 IP). 브라우저마다 Chrome 프로필을 따로 쓴다
                (.browser_profile, .browser_profile_w1, …; 처음 한 번 원본 프로필을 복사해 쿠키를 이어받음).
                전체 요청 간격은 --min-interval 초 이상으로 묶는다. 하나라도 차단되면 모두 멈춘다.
                같은 IP에서 동시에 요청하므로 N을 늘릴수록 차단 위험이 커진다(권장 2~3).

결과 (git에 올라가지 않는 model/data/ 아래)
  model/data/raw/coupang/coupang_training.json   수집한 모든 쿠팡 데이터 (JSON 파일 하나)
      {"meta": {...}, "summary": {...},
       "categories": {"<카테고리 URL>": {"name", "listed_at", "products": [{product_id, url, name}, ...]}},
       "products": {"<상품ID>": {"name", "url", "category", "status": "collected"|"no_old", "checked_at",
                                 "check": {...}, "counts": {...}, "reviews": [리뷰, ...]}}}
      리뷰 = MODEL_DEV.md 4.12.1 형식 + period(pre_chatgpt/post_chatgpt) · length_bucket
      상품 하나가 끝날 때마다 바로 저장한다(임시 파일에 쓴 뒤 바꿔치기 → 중간에 끊겨도 파일이 깨지지 않음).
  model/data/raw/naver/naver_shopping.jsonl      네이버 쇼핑 변환 결과 (별도 파일)

쿠팡이 차단(403·접근 거부)하면 모든 브라우저를 닫고 5분 → 15분 → 30분 쉬었다가, 끝난 상품은 건너뛰고 이어서 모은다.
두 번째 차단부터는 이 스크립트가 만든 브라우저 프로필을 지우고 새 쿠키로 시작한다(원격 Chrome 모드에서는 건드리지 않음).
세 번 쉬어도 막히면 멈춘다. 시간이 지난 뒤 같은 명령을 다시 실행하면 이어서 모은다.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import random
import re
import shutil
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
CAP_REVIEWS = 1500                # 쿠팡이 리뷰 목록 하나(정렬×별점)에서 보여 주는 최대 개수. 그 뒤 페이지는 비어 있다
FALLBACK_PAGES = 30               # 날짜가 섞여 나오는 목록에서 1,500개 안을 훑어볼 최대 페이지 (--scan-pages)
QUICK_SKIP = False                # --quick-skip: 리뷰 1,500개 초과 상품도 전체 목록 1,500번째가 이후면 바로 건너뜀
PAGE_ATTEMPTS = 3
PAGE_BACKOFF = (5.0, 20.0)        # 재시도 전 대기(초)
PRODUCT_DELAY = (8.0, 15.0)       # 상품 사이 대기(초) — 서비스 수집보다 느리게
SKIP_DELAY = (3.0, 6.0)           # 과거 리뷰가 없어 건너뛴 상품 뒤 대기(초)
PER_PRODUCT = 40                  # 카테고리 모드: 상품당 최대 리뷰 수 (한 상품 과대표집·과적합 방지)
LIST_PAGES = 10                   # 카테고리 모드: 상품 목록을 넘겨 볼 최대 페이지 수
LIST_SIZE = 60                    # 카테고리 목록 한 페이지 상품 수 (쿠팡 listSize)
MAX_WORKERS = 4                   # 같은 IP에서 동시에 띄울 최대 브라우저 수
MIN_INTERVAL = 1.0                # 모든 작업자를 합친 요청 사이 최소 간격(초)
SCRAPER_VERSION = "collect_training_data/4"

# 탐지 회피 설정 (기본으로 항상 켬)
STEALTH_OPTIONS = {"hide_canvas": True, "block_webrtc": True, "allow_webgl": True}
# Scrapling은 창 크기와 상관없이 화면을 1920×1080으로 고정한다 → 노트북 화면과 어긋나 티가 난다. 실제 창 크기를 쓴다.
REAL_WINDOW = {"no_viewport": True, "viewport": None, "screen": None, "device_scale_factor": None}
CHROME_PATHS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
CHROME_PROFILE_NAME = ".browser_profile_chrome"   # 실제 Chrome용 프로필 (내장 Chromium 프로필과 섞이면 Chrome이 못 여는 경우가 있음)
CDP_PORT = 9222
CDP_PROFILE = Path.home() / ".realstar_cdp_chrome"  # 원격 연결용 Chrome 전용 프로필
CDP_FLAGS = (
    "--no-first-run", "--no-default-browser-check", "--lang=ko-KR", "--accept-lang=ko-KR,ko,en-US,en",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp", "--force-webrtc-ip-handling-policy",
)
HUMAN_EVERY = (3, 6)              # API 요청 3~6번마다 사람 동작(마우스·스크롤·멈춤)
SOFT_BLOCK_WAIT = 30.0            # 차단 응답을 처음 받으면 잠깐 쉬고 한 번 더 해 본다(초)
BLOCK_COOLDOWNS = (300, 900, 1800)  # 차단되면 모두 멈추고 쉬는 시간(초): 5분 → 15분 → 30분

# 테스트 전용: 대기 시간 배율(예: 0.01). 실제 수집에서는 쓰지 않는다.
_DELAY_SCALE = float(os.environ.get("COLLECT_DELAY_SCALE") or 1.0)
if _DELAY_SCALE != 1.0:
    PRODUCT_DELAY = (PRODUCT_DELAY[0] * _DELAY_SCALE, PRODUCT_DELAY[1] * _DELAY_SCALE)
    SKIP_DELAY = (SKIP_DELAY[0] * _DELAY_SCALE, SKIP_DELAY[1] * _DELAY_SCALE)
    PAGE_BACKOFF = (PAGE_BACKOFF[0] * _DELAY_SCALE, PAGE_BACKOFF[1] * _DELAY_SCALE)
    MIN_INTERVAL = MIN_INTERVAL * _DELAY_SCALE
    SOFT_BLOCK_WAIT = SOFT_BLOCK_WAIT * _DELAY_SCALE
    BLOCK_COOLDOWNS = tuple(int(x * _DELAY_SCALE) for x in BLOCK_COOLDOWNS)

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
    if _DELAY_SCALE != 1.0:
        lo, hi = cr.API_DELAY_RANGE
        cr.API_DELAY_RANGE = (lo * _DELAY_SCALE, hi * _DELAY_SCALE)
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
            if "/np/categories/" in line or "/np/search" in line:
                print(f"  ⚠ {line_no}번째 줄은 카테고리·검색 주소예요 → training_categories.txt 에 넣고 "
                      f"`python collect_training_data.py category training_categories.txt` 로 실행하세요: {line[:80]}")
            else:
                print(f"  ⚠ {line_no}번째 줄 건너뜀 (상품 페이지 주소가 아님): {line[:80]}")
            continue
        if m.group(1) in seen:
            continue
        seen.add(m.group(1))
        out.append({"product_id": m.group(1), "url": line.split()[0], "category": category})
    return out


STORE_NAME = "coupang_training.json"
STORE_SCHEMA = "realstar-training/1"


class Store:
    """수집 데이터 JSON 파일 하나. 메인 프로세스만 쓴다(병렬 수집 때도 작업자는 결과만 넘긴다)."""

    def __init__(self, out_dir: Path) -> None:
        self.dir = out_dir
        self.path = out_dir / STORE_NAME
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                d.setdefault("categories", {})
                d.setdefault("products", {})
                return d  # type: ignore[no-any-return]
            except ValueError as e:
                bak = self.path.with_suffix(f".broken-{datetime.now(KST):%Y%m%d%H%M%S}.json")
                self.path.replace(bak)
                print(f"  ⚠ {self.path.name}을 읽지 못해 {bak.name}(으)로 옮기고 새로 시작해요: {e}")
        d = {"schema": STORE_SCHEMA, "meta": {"created_at": now_iso()}, "summary": {}, "categories": {}, "products": {}}
        self._import_legacy(d)
        return d

    def _import_legacy(self, d: dict[str, Any]) -> None:
        """이전 형식(*.jsonl + _state.json)으로 모은 데이터가 있으면 한 번만 옮겨 온다."""
        files = sorted(self.dir.glob("*.jsonl"))
        state_p = self.dir / "_state.json"
        if not files and not state_p.exists():
            return
        state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
        for f in files:
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                prod = d["products"].setdefault(r["product_id"], {
                    "product_id": r["product_id"], "name": r.get("product_name"), "url": None,
                    "category": r.get("category"), "status": "collected", "checked_at": r.get("collected_at"), "reviews": []})
                if all(x["review_id"] != r["review_id"] for x in prod["reviews"]):
                    prod["reviews"].append(r)
        for pid, info in (state.get("products") or {}).items():
            prod = d["products"].setdefault(pid, {"product_id": pid, "reviews": []})
            prod.setdefault("name", info.get("name"))
            prod.setdefault("category", info.get("category"))
            prod["status"] = info.get("status") or ("collected" if prod["reviews"] else "no_old")
            prod.setdefault("checked_at", info.get("at"))
            if info.get("check"):
                prod["check"] = info["check"]
        for url, c in (state.get("categories") or {}).items():
            d["categories"][url] = {"name": c.get("name"), "listed_at": c.get("listed_at"), "products": c.get("products", [])}
        for prod in d["products"].values():
            prod["counts"] = review_counts(prod.get("reviews", []))
        d["meta"]["imported_from"] = [f.name for f in files] + (["_state.json"] if state_p.exists() else [])
        print(f"  이전 형식 데이터를 {STORE_NAME}로 옮겨 왔어요: 상품 {len(d['products'])}개 (원본 파일은 그대로 둠)")

    # ── 조회 ──
    recheck_since: str | None = None  # --recheck-no-old: 이 시각 전에 '과거 리뷰 없음'으로 끝난 상품은 다시 확인

    def is_done(self, pid: str) -> bool:
        prod = self.data["products"].get(pid, {})
        status = prod.get("status")
        if status == "no_old" and self.recheck_since and (prod.get("checked_at") or "") < self.recheck_since:
            return False
        return status in ("collected", "no_old")

    def listing(self, url: str) -> list[dict[str, str]] | None:
        c = self.data["categories"].get(url)
        return c.get("products") if c and c.get("products") else None

    # ── 기록 ──
    def set_listing(self, url: str, name: str, products: list[dict[str, str]]) -> None:
        self.data["categories"][url] = {"name": name, "listed_at": now_iso(), "products": products}
        self.save()

    def put_product(self, item: dict[str, str], result: dict[str, Any]) -> dict[str, Any]:
        rows = result["rows"]
        prod = {
            "product_id": item["product_id"], "name": result.get("name") or item.get("name"), "url": item.get("url"),
            "category": item.get("category") or None,
            "status": "collected" if any(r["period"] == "pre_chatgpt" for r in rows) else "no_old",
            "checked_at": now_iso(), "check": result.get("check") or {}, "worker": result.get("worker"),
            "counts": review_counts(rows), "reviews": rows,
        }
        self.data["products"][item["product_id"]] = prod
        self.save()
        return prod

    def save(self) -> None:
        d = self.data
        d["schema"] = STORE_SCHEMA
        d.setdefault("meta", {}).update({"updated_at": now_iso(), "cutoff": CUTOFF.isoformat(),
                                         "post_from": POST_FROM.isoformat(), "scraper_version": SCRAPER_VERSION})
        prods = d["products"].values()
        d["summary"] = {
            "products_checked": len(d["products"]),
            "products_collected": sum(1 for p in prods if p.get("status") == "collected"),
            "products_no_old": sum(1 for p in prods if p.get("status") == "no_old"),
            "reviews_pre_chatgpt": sum(p.get("counts", {}).get("pre_chatgpt", 0) for p in prods),
            "reviews_post_chatgpt": sum(p.get("counts", {}).get("post_chatgpt", 0) for p in prods),
        }
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)  # 바꿔치기: 저장 도중 끊겨도 이전 파일이 남는다

    def reviews(self) -> list[dict[str, Any]]:
        return [r for p in self.data["products"].values() for r in p.get("reviews", [])]


def review_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pre = [r for r in rows if r.get("period") == "pre_chatgpt"]
    return {
        "pre_chatgpt": len(pre),
        "post_chatgpt": sum(1 for r in rows if r.get("period") == "post_chatgpt"),
        "pre_by_star": {str(s): sum(1 for r in pre if r.get("star") == s) for s in STARS},
    }


# ──────────────────────────────────────────────────────────────
# 브라우저 열기 (탐지 회피 설정 포함)
# ──────────────────────────────────────────────────────────────
def find_chrome() -> str | None:
    """설치된 Google Chrome 실행 파일."""
    for p in CHROME_PATHS:
        if Path(p).exists():
            return p
    for name in ("google-chrome", "google-chrome-stable", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def cdp_alive(cdp_url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(cdp_url.rstrip("/") + "/json/version", timeout=timeout) as r:  # noqa: S310 (로컬 주소)
            return r.status == 200
    except Exception:
        return False


def open_browser(cr: Any, cfg: dict[str, Any]) -> Any:
    """설정에 맞는 브라우저 세션.
    cdp_url 있음 → 이미 떠 있는 Chrome에 연결(그 Chrome의 쿠키·창을 그대로 씀).
    없음        → 새로 띄움: 실제 Chrome(있으면) + WebRTC 차단 + 캔버스 노이즈 + 실제 창 크기."""
    cdp_url = cfg.get("cdp_url")
    if cdp_url:
        from scrapling.fetchers import RemoteSession  # noqa: PLC0415
        if not cdp_alive(cdp_url):
            raise RuntimeError(f"원격 Chrome({cdp_url})에 연결할 수 없어요. 먼저 `python collect_training_data.py chrome` 을 실행하세요.")
        # new_context=False: 그 Chrome의 기본 창·쿠키를 그대로 쓴다(이때 언어·UA 같은 설정은 Chrome 자체 값을 따름)
        return RemoteSession(cdp_url=cdp_url, new_context=False, timeout=60000, retries=1)
    extra: dict[str, Any] = {**STEALTH_OPTIONS}
    if not cfg.get("headless"):
        extra["additional_args"] = dict(REAL_WINDOW)  # 창 없는 모드에서는 가상 화면이 800×600이라 쓰지 않는다
    try:
        return cr.open_session(headless=cfg.get("headless", False), real_chrome=bool(cfg.get("real_chrome")), **extra)
    except TypeError:  # 옛 coupang_reviews.py(open_session(headless)만 받음)
        return cr.open_session(headless=cfg.get("headless", False))


def apply_page_size(cr: Any, cfg: dict[str, Any]) -> None:
    """--page-size: 한 번에 받는 리뷰 수(기본 10 = 쿠팡 화면과 같음). 상한은 개수(1,500개)라서
    크게 받으면 같은 범위를 더 적은 요청으로 본다."""
    cr.PAGE_SIZE = int(cfg.get("page_size") or cr.PAGE_SIZE)


def use_profile(cr: Any, cfg: dict[str, Any], wid: int) -> None:
    """작업자가 쓸 브라우저 프로필 폴더를 정한다(실제 Chrome이면 Chrome 전용 폴더)."""
    base = Path(cr.PROFILE_DIR)
    if cfg.get("real_chrome"):
        base = base.with_name(CHROME_PROFILE_NAME)
    cr.PROFILE_DIR = profile_path(base, wid)


_HUMAN_LEFT = random.randint(*HUMAN_EVERY)


def human_touch(page: Any) -> None:
    """요청 몇 번마다 사람처럼 마우스를 움직이고, 조금 스크롤하고, 잠깐 멈춘다."""
    global _HUMAN_LEFT
    _HUMAN_LEFT -= 1
    if _HUMAN_LEFT > 0:
        return
    _HUMAN_LEFT = random.randint(*HUMAN_EVERY)
    try:
        size = page.evaluate("() => [innerWidth, innerHeight]")
        w, h = (int(size[0]), int(size[1])) if isinstance(size, list) and len(size) == 2 else (1200, 800)
        for _ in range(random.randint(2, 4)):
            page.mouse.move(random.randint(40, max(60, w - 40)), random.randint(80, max(100, h - 40)),
                            steps=random.randint(8, 25))  # 한 번에 순간이동하지 않고 여러 단계로 이동
            page.wait_for_timeout(random.randint(120, 450))
        page.mouse.wheel(0, random.choice((-1, 1)) * random.randint(150, 600))
        page.wait_for_timeout(int(random.uniform(0.8, 3.5) * 1000 * _DELAY_SCALE))  # 읽는 척 잠깐 멈춤
    except Exception:
        pass  # 사람 동작은 보조 수단. 실패해도 수집은 계속한다


def is_closed(e: BaseException) -> bool:
    msg = str(e).lower()
    return "has been closed" in msg or "target closed" in msg or "connection closed" in msg


# ──────────────────────────────────────────────────────────────
# 병렬 작업자 공용: 전체 요청 간격 제한, 중단 신호, 로그 머리말
# ──────────────────────────────────────────────────────────────
_THROTTLE: Any = None   # (lock, 공유 시각 Value, 최소 간격 초) — 작업자 프로세스에서 설정
_STOP: Any = None       # multiprocessing.Event — 한 작업자가 차단되면 모두 멈춘다
_PREFIX = ""
_SLOT: tuple[int, int] | None = None   # (작업자 번호, 작업자 수) — 창을 화면에 나란히 놓기 위함
_PLACED = False


class Stopped(Exception):
    """다른 작업자가 차단돼 이번 상품을 멈췄다(저장하지 않고 다음 실행 때 다시 한다)."""


def say(msg: str) -> None:
    print(f"{_PREFIX}{msg}", flush=True)


def throttle_wait() -> None:
    """모든 작업자를 합쳐 요청 사이 간격을 지킨다."""
    if _STOP is not None and _STOP.is_set():
        raise Stopped()
    if _THROTTLE is None:
        return
    lock, last, interval = _THROTTLE
    with lock:
        wait = last.value + interval - time.time()
        if wait > 0:
            time.sleep(wait)
        last.value = time.time()


# ──────────────────────────────────────────────────────────────
# 쿠팡: 페이지 단위 요청
# ──────────────────────────────────────────────────────────────
class ReviewPager:
    """한 상품·한 별점의 리뷰 페이지를 요청한다. 같은 페이지는 다시 요청하지 않는다."""

    def __init__(self, cr: Any, page: Any, pid: str, star: int | None, sort: str, log: Any) -> None:
        self.cr, self.page, self.pid, self.star, self.sort, self.log = cr, page, pid, star, sort, log
        self.cache: dict[int, list[dict[str, Any]]] = {}
        self.raw_first: Any = None
        self.requests = 0

    def url(self, page_no: int) -> str:
        return self.cr.API_BASE + "?" + urlencode({
            "productId": self.pid, "page": page_no, "size": self.cr.PAGE_SIZE, "sortBy": self.sort,
            "ratingSummary": "true", "ratings": "" if self.star is None else str(self.star), "market": "",
        })

    def get(self, page_no: int) -> list[dict[str, Any]]:
        """파싱된 리뷰 목록. 빈 페이지면 []. 차단이면 Blocked."""
        if page_no in self.cache:
            return self.cache[page_no]
        last_err = ""
        soft_waited = False
        cr_blocked = getattr(self.cr, "Blocked", ())
        for attempt in range(1, PAGE_ATTEMPTS + 1):
            self.cr.pause(self.page, self.cr.API_DELAY_RANGE)
            human_touch(self.page)
            throttle_wait()
            self.requests += 1
            try:
                data = self.cr.api_get(self.page, self.url(page_no))
            except Exception as e:  # HTTP 오류·JSON 아님(차단 페이지)
                last_err = str(e)
                if is_closed(e):
                    raise
                blocked = (cr_blocked and isinstance(e, cr_blocked)) or any(
                    k in last_err for k in ("403", "429", "JSON이 아닌", "차단 페이지"))
                if blocked and not soft_waited:  # 처음 막히면 잠깐 쉬고 한 번 더
                    soft_waited = True
                    self.log(f"      ⏸ {self.star or '전체'}{'점' if self.star else ''} {page_no}페이지 {last_err[:60]} → {SOFT_BLOCK_WAIT:.0f}초 쉬고 다시")
                    self.page.wait_for_timeout(int(SOFT_BLOCK_WAIT * 1000))
                    continue
                if blocked:
                    raise Blocked(last_err) from e
                wait = PAGE_BACKOFF[min(attempt - 1, len(PAGE_BACKOFF) - 1)]
                self.log(f"      ↻ {self.star or '전체'}{'점' if self.star else ''} {page_no}페이지 {last_err[:60]} → {wait}초 후 재시도")
                self.page.wait_for_timeout(int(wait * 1000))
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
        """이 목록의 리뷰 수. 별점 필터를 걸어도 응답의 전체 개수는 상품 전체 수라서,
        별점이 있으면 요약 정보의 별점별 개수를 쓴다."""
        if self.raw_first is None:
            return None
        if self.star is not None:
            counts = self.cr.find_rating_counts(self.raw_first) or {}
            n = counts.get(self.star, counts.get(str(self.star)))
            if n is not None:
                return int(n)
        items = self.cr.find_review_list(self.raw_first)
        t = self.cr.find_number(self.raw_first, self.cr.TOTAL_KEYS, skip_lists=items)
        return int(t) if t is not None else None

    def oldest(self, page_no: int) -> date | None:
        ds = [r["_date"] for r in self.get(page_no) if r["_date"]]
        return min(ds) if ds else None


def is_desc(reviews: list[dict[str, Any]]) -> bool:
    """최신순으로 나왔는지. 한 군데 정도 어긋나는 건 허용한다(쿠팡 4·1점 최신순은 4~6군데씩 뒤섞여 나옴)."""
    ds = [r["_date"] for r in reviews if r["_date"]]
    if len(ds) < 2:
        return False
    flips = sum(1 for a, b in zip(ds, ds[1:]) if a < b)
    return flips <= (1 if len(ds) >= 6 else 0)


def window_pages(n: int, size: int) -> int:
    """리뷰 n개 목록에서 쿠팡이 보여 주는 마지막 페이지 (최신 1,500개까지)."""
    return max(1, math.ceil(min(n, CAP_REVIEWS) / size))


def find_reach(pager: ReviewPager, last: int) -> int:
    """실제로 열리는 마지막 페이지. 보통 last 그대로다(요청 1회).
    빈 페이지면(삭제·숨김 리뷰로 개수가 어긋난 경우 등) 이진 탐색으로 실제 끝을 찾는다."""
    if last <= 1 or pager.get(last):
        return last
    lo, hi = 1, last                        # lo는 열리고 hi는 안 열림
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if pager.get(mid):
            lo = mid
        else:
            hi = mid
    return lo


def star_counts(cr: Any, raw: Any) -> dict[int, int]:
    """응답의 요약 정보에서 별점별 리뷰 수 {5: n, …, 1: n}."""
    counts = cr.find_rating_counts(raw) if raw is not None else None
    out: dict[int, int] = {}
    for k, v in (counts or {}).items():
        with contextlib.suppress(TypeError, ValueError):
            out[int(k)] = int(v)
    return out


def spread_pages(first: int, last: int, n: int) -> list[int]:
    """[first, last] 구간에서 n개 페이지를 고르게 고른다."""
    if last <= first or n <= 1:
        return [first]
    n = min(n, last - first + 1)
    return sorted({first + round(i * (last - first) / (n - 1)) for i in range(n)})


def collect_star(cr: Any, page: Any, pid: str, star: int, per_star: int, post_per_star: int, log: Any,
                 known_count: int | None = None) -> dict[str, Any]:
    """한 별점: 2022-11-30 이전 리뷰 per_star개 + 2023년 이후 리뷰 post_per_star개.

    쿠팡은 별점 목록마다 최신 1,500개까지만 보여 준다.
      최신순으로 나오는 목록 → 1,500번째(더 적으면 마지막) 리뷰 날짜가 2022-11-30 이후면 이 별점은 과거 리뷰 없음.
                               이전이면 경계 페이지를 이진 탐색으로 찾아 1,500번째까지 고르게 담는다.
      날짜가 섞여 나오는 목록 → 1,500개 안 어디에나 있을 수 있어 앞에서부터 훑는다(최대 FALLBACK_PAGES 페이지).
    known_count: 상품 확인 단계에서 이미 알아낸 이 별점의 리뷰 수(0이면 요청 없이 끝)."""
    out: dict[str, Any] = {"pre": [], "post": [], "method": "date_sort", "requests": 0,
                           "count": known_count, "window": 0, "window_oldest": None}
    if known_count == 0:
        out["method"] = "none"
        return out
    pager = ReviewPager(cr, page, pid, star, DATE_SORT, log)
    first = pager.get(1)
    if not first:
        out["requests"] = pager.requests
        return out

    if post_per_star:
        out["post"] = [r for r in first if r["_date"] and r["_date"] >= POST_FROM][:post_per_star]

    count = known_count if known_count is not None else (pager.total() or len(first))
    window = min(count, CAP_REVIEWS)
    last = window_pages(count, cr.PAGE_SIZE)
    out["count"], out["window"] = count, window
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

    if is_desc(first):
        # 1,500번째(또는 마지막) 리뷰가 있는 페이지까지 가서 그 날짜를 본다
        reach = find_reach(pager, last)
        oldest_reach = pager.oldest(reach)
        out["window_oldest"] = oldest_reach.isoformat() if oldest_reach else None
        where = f"{window:,}번째(쿠팡이 보여 주는 끝)" if count > CAP_REVIEWS else f"마지막({count:,}번째)"
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
            log(f"      · {star}점: {where} 리뷰가 {oldest_reach} → 2022-11-30 이전 리뷰 없음")
    else:
        out["method"] = "scan"
        scan_to = min(last, FALLBACK_PAGES)
        for p in range(1, scan_to + 1):
            got = pager.get(p)
            if not got:
                break
            take(got)
            if post_per_star and len(out["post"]) < post_per_star:
                extra = [r for r in got if r["_date"] and r["_date"] >= POST_FROM and r not in out["post"]]
                out["post"] += extra[: post_per_star - len(out["post"])]
            if len(pre) >= per_star:
                break
        if len(pre) < per_star and scan_to < last:
            log(f"      · {star}점: 날짜가 섞여 나오는 목록 · {window:,}개 중 앞 {scan_to * cr.PAGE_SIZE:,}개만 훑음"
                " (--scan-pages로 늘릴 수 있음)")

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


# ──────────────────────────────────────────────────────────────
# 카테고리 모드: 카테고리 목록 → 상품마다 과거 리뷰 확인 → 있으면 수집
# ──────────────────────────────────────────────────────────────
_PID_RE = re.compile(r"/vp/products/(\d+)")


def parse_listing(html: str) -> list[dict[str, str]]:
    """카테고리·검색 목록 HTML에서 상품 링크를 모은다(화면 클래스 이름에 기대지 않는다)."""
    from html.parser import HTMLParser

    found: dict[str, dict[str, str]] = {}

    class P(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.cur: dict[str, Any] | None = None
            self.depth = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            a = {k: (v or "") for k, v in attrs}
            if self.cur is None:
                if tag == "a" and _PID_RE.search(a.get("href", "")):
                    self.cur, self.depth = {"href": a["href"], "texts": [], "alt": ""}, 0
                return
            if tag == "img" and not self.cur["alt"]:
                self.cur["alt"] = a.get("alt", "")
            if tag not in ("img", "br", "input", "source", "meta", "link", "hr", "wbr"):
                self.depth += 1

        def handle_endtag(self, tag: str) -> None:
            if self.cur is None:
                return
            if tag == "a" and self.depth == 0:
                href = self.cur["href"]
                pid = _PID_RE.search(href).group(1)  # type: ignore[union-attr]
                texts = [t for t in self.cur["texts"] if not re.fullmatch(r"[\d,.()원%\s]+", t)]
                name = self.cur["alt"] or (max(texts, key=len) if texts else "")
                if pid not in found:
                    url = href if href.startswith("http") else "https://www.coupang.com" + href
                    found[pid] = {"product_id": pid, "url": url, "name": name.strip()}
                self.cur = None
            elif tag not in ("img", "br", "input", "source", "meta", "link", "hr", "wbr"):
                self.depth = max(0, self.depth - 1)

        def handle_data(self, data: str) -> None:
            if self.cur is not None and data.strip():
                self.cur["texts"].append(data.strip())

    P().feed(html)
    return list(found.values())


def listing_url(base: str, page_no: int) -> str:
    from urllib.parse import parse_qsl, urlparse, urlunparse

    u = urlparse(base)
    q = dict(parse_qsl(u.query))
    q["page"] = str(page_no)
    if "/np/categories/" in u.path:
        q.setdefault("listSize", str(LIST_SIZE))
    return urlunparse(u._replace(query=urlencode(q)))


def list_category(cr: Any, session: Any, url: str, max_pages: int) -> list[dict[str, str]]:
    """카테고리(또는 검색 결과) 목록을 넘기며 상품 링크를 모은다. 새 상품이 안 나오면 멈춘다."""
    products: dict[str, dict[str, str]] = {}
    for page_no in range(1, max_pages + 1):
        box: dict[str, Any] = {}

        def action(page: Any, _box: dict[str, Any] = box) -> Any:
            try:
                # 상품 목록이 늦게 그려지는 화면: 상품 링크가 나타날 때까지 잠시 기다린다
                with contextlib.suppress(Exception):
                    page.wait_for_selector('a[href*="/vp/products/"]', timeout=12000)
                cr.warm_up(page)
                _box["html"] = page.content()
            except Exception as e:
                _box["error"] = e
            return page

        resp = session.fetch(listing_url(url, page_no), page_action=action)
        if getattr(resp, "status", 200) != 200:
            raise Blocked(f"카테고리 목록 HTTP {resp.status}")
        html = box.get("html") or ""
        if "Access Denied" in html[:30000] or "사용권한이 없습니다" in html[:30000]:
            raise Blocked("카테고리 목록 접근 거부")
        new = [p for p in parse_listing(html) if p["product_id"] not in products]
        print(f"  목록 {page_no}페이지: 새 상품 {len(new)}개", flush=True)
        if not new and page_no == 1:
            explain_empty_listing(url, html)
        if not new:
            break
        for p in new:
            products[p["product_id"]] = p
        time.sleep(random.uniform(*SKIP_DELAY))
    return list(products.values())


def subcategory_links(html: str, url: str) -> list[tuple[str, str]]:
    """페이지 안의 다른 카테고리 링크(번호, 이름). 이름이 있는 것만, 중복 없이."""
    self_id = (re.search(r"/np/categories/(\d+)", url) or [None, ""])[1]
    out: dict[str, str] = {}
    for m in re.finditer(r'<a[^>]+href="[^"]*/np/categories/(\d+)[^"]*"[^>]*>(.*?)</a>', html, re.S | re.I):
        cid, inner = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        name = re.sub(r"\s+", " ", inner).strip()
        if cid != self_id and name and len(name) <= 30 and cid not in out:
            out[cid] = name
    return list(out.items())


def explain_empty_listing(url: str, html: str) -> None:
    """목록에서 상품을 못 찾았을 때: 화면을 저장하고, 들어갈 수 있는 하위 카테고리를 보여 준다."""
    d = OUT_DIR.parent.parent / "debug"
    try:
        d.mkdir(parents=True, exist_ok=True)
        cid = (re.search(r"/np/categories/(\d+)", url) or [None, "list"])[1]
        path = d / f"category_{cid}_page1.html"
        path.write_text(html, encoding="utf-8")
        print(f"    · 받은 화면을 저장했어요: {path}  (화면 구조 확인용)")
    except OSError:
        pass
    if len(html) < 2000:
        print("    · 화면 내용이 거의 비어 있어요. 차단 화면이거나 로딩이 덜 된 것 같아요.")
    subs = subcategory_links(html, url)
    if subs:
        print("    · 이 페이지는 상품 목록이 아니라 카테고리 홈인 것 같아요. 아래처럼 세부 카테고리 주소를 넣어 주세요:")
        for cid, name in subs[:25]:
            print(f"        {name}: https://www.coupang.com/np/categories/{cid}")
        if len(subs) > 25:
            print(f"        … 외 {len(subs) - 25}개")


def old_review_check(cr: Any, page: Any, pid: str, log: Any) -> dict[str, Any]:
    """상품 전체 목록(최신순)으로 수집할 과거 리뷰가 있는지 본다.
    리뷰 1,500개 이하: 마지막 리뷰가 2022-11-30 이후면 없음(요청 2회로 끝).
    1,500개 초과: 1,500번째 리뷰가 이전이면 있음. 이후면 별점별로 확인(별점 목록은 각자 최신 1,500개를 보여 줌).
                  --quick-skip이면 이 경우도 없음으로 보고 건너뛴다."""
    pager = ReviewPager(cr, page, pid, None, DATE_SORT, log)
    first = pager.get(1)
    if not first:
        return {"has_old": False, "reason": "리뷰 없음", "requests": pager.requests}
    counts = star_counts(cr, pager.raw_first)
    total = pager.total() or sum(counts.values()) or len(first)
    info: dict[str, Any] = {"total": total, "star_counts": {str(k): v for k, v in sorted(counts.items(), reverse=True)}}
    if not is_desc(first):
        return {"has_old": True, "reason": "전체 목록이 최신순으로 안 나옴 → 별점별로 확인", **info,
                "requests": pager.requests}
    reach = find_reach(pager, window_pages(total, cr.PAGE_SIZE))
    oldest = pager.oldest(reach)
    window = min(total, CAP_REVIEWS)
    info.update({"window": window, "window_oldest": oldest.isoformat() if oldest else None,
                 "capped": total > CAP_REVIEWS, "requests": pager.requests})
    if oldest is not None and oldest < CUTOFF:
        return {"has_old": True, "reason": f"최신 {window:,}개 안에 {oldest} 리뷰가 있음", **info}
    if total <= CAP_REVIEWS:
        return {"has_old": False, "reason": f"리뷰 {total:,}개 전부 2022-11-30 이후 (가장 오래된 {oldest})", **info}
    if QUICK_SKIP:
        return {"has_old": False, "reason": f"전체 {total:,}개 중 1,500번째 리뷰가 {oldest} (--quick-skip)", **info}
    return {"has_old": True, "reason": f"전체 {total:,}개 중 1,500번째 리뷰가 {oldest} → 별점별 목록(각 1,500개)으로 확인", **info}


def read_categories(args_targets: list[str], name: str) -> list[dict[str, str]]:
    """인자로 받은 카테고리 URL들, 또는 '## 이름' + URL 형식의 txt 파일."""
    out: list[dict[str, str]] = []
    for t in args_targets:
        path = Path(t)
        if path.exists() and not t.startswith("http"):
            current = ""
            for raw in path.read_text(encoding="utf-8-sig").splitlines():
                line = raw.strip()
                if line.startswith("##"):
                    current = line.lstrip("#").strip()
                elif line.startswith("http"):
                    if "/vp/products/" in line:
                        print(f"  ⚠ 상품 주소는 training_products.txt 에 넣고 collect 명령으로 수집하세요: {line[:80]}")
                        continue
                    out.append({"name": current or name, "url": line.split()[0]})
        elif t.startswith("http"):
            out.append({"name": name, "url": t})
        else:
            print(f"  ⚠ 카테고리 주소나 파일이 아님: {t}")
    return out


# ──────────────────────────────────────────────────────────────
# 상품 하나 처리 (작업자 안에서 실행) → 결과는 피클 가능한 dict
# ──────────────────────────────────────────────────────────────
def product_title(cr: Any, page: Any) -> str:
    try:
        t = page.evaluate("() => document.querySelector('meta[property=\"og:title\"]')?.content || document.title || ''")
    except Exception:
        return ""
    if isinstance(t, dict):
        t = t.get("title") or ""
    return cr.clean_product_name(t) if isinstance(t, str) and t else ""


def process_item(cr: Any, session: Any, item: dict[str, str], cfg: dict[str, Any]) -> dict[str, Any]:
    """상품 페이지를 열고 수집한다.
    mode=category: 과거 리뷰 유무 확인 → 있으면 상품당 최대 per_product개(1점부터 남은 몫 배분)
    mode=list:     별점마다 per_star개(+ 이후 리뷰 post_per_star개)"""
    pid = item["product_id"]
    box: dict[str, Any] = {"stars": {}, "check": {}}

    def action(page: Any) -> Any:
        try:
            place_window(page)
            box["name"] = product_title(cr, page) or item.get("name") or ""
            if cfg["mode"] == "category":
                chk = old_review_check(cr, page, pid, say)
                box["check"] = chk
                if not chk["has_old"]:
                    return page
                cr.warm_up(page)
                known = chk.get("star_counts") or {}
                remaining = cfg["per_product"]
                for idx, star in enumerate((1, 2, 3, 4, 5)):  # 적은 별점부터: 남는 몫을 다음 별점이 가져간다
                    if remaining <= 0:
                        break
                    quota = math.ceil(remaining / (5 - idx))
                    res = collect_star(cr, page, pid, star, quota, cfg["post_per_star"], say, known_count=known.get(str(star)))
                    box["stars"][star] = res
                    remaining -= len(res["pre"])
                    say(f"    {star}점: 이전 {len(res['pre'])}/{quota}"
                        + (f" · 이후 {len(res['post'])}" if cfg["post_per_star"] else "")
                        + (f"  (리뷰 {res['count']:,}개, 요청 {res['requests']}회, {res['method']})" if res["count"] is not None
                           else f"  (요청 {res['requests']}회)"))
            else:
                cr.warm_up(page)
                for star in STARS:
                    res = collect_star(cr, page, pid, star, cfg["per_star"], cfg["post_per_star"], say)
                    box["stars"][star] = res
                    say(f"    {star}점: 이전 {len(res['pre'])}/{cfg['per_star']}"
                        + (f" · 이후 {len(res['post'])}/{cfg['post_per_star']}" if cfg["post_per_star"] else "")
                        + (f"  (리뷰 {res['count']:,}개, " if res["count"] is not None else "  (")
                        + f"요청 {res['requests']}회, {res['method']})")
        except BaseException as e:  # Scrapling은 page_action 예외를 삼키므로 직접 보관
            box["error"] = e
        return page

    throttle_wait()
    resp = session.fetch(item["url"], page_action=action)
    if "error" in box:
        raise box["error"]
    status = getattr(resp, "status", 200)
    if status != 200:
        if not box["check"] and not box["stars"]:  # 리뷰를 하나도 못 받았으면 차단
            raise Blocked(f"상품 페이지 HTTP {status}")
        # 상품 페이지 응답만 403이고 리뷰 API는 정상이었던 경우: 받은 결과를 버리지 않는다
        say(f"    (참고) 상품 페이지 응답은 {status}였지만 리뷰는 받아서 저장해요")
    collected_at = now_iso()
    rows = [to_record(r, pid, box["name"], item.get("category", ""), collected_at)
            for star in STARS for r in (box["stars"].get(star) or {}).get("pre", []) + (box["stars"].get(star) or {}).get("post", [])]
    check = {k: v for k, v in box["check"].items() if k != "has_old"}
    return {"name": box["name"], "check": check, "rows": rows}


# ──────────────────────────────────────────────────────────────
# 병렬 실행: 작업자(브라우저) N개 + 메인(저장 담당) 1개
# ──────────────────────────────────────────────────────────────
PROFILE_SKIP = shutil.ignore_patterns("Singleton*", "Cache", "Code Cache", "GPUCache", "*ShaderCache", "DawnGraphiteCache",
                                      "DawnWebGPUCache", "GraphiteDawnCache", "GPUPersistentCache", "component_crx_cache",
                                      "Crashpad", "BrowserMetrics*")


def place_window(page: Any) -> None:
    """작업자 창을 화면에 나란히 배치한다(Scrapling은 모든 창을 같은 위치 0,0에 띄워서 겹쳐 보인다)."""
    global _PLACED
    if _PLACED or _SLOT is None or _SLOT[1] <= 1:
        return
    _PLACED = True
    wid, n = _SLOT
    try:
        scr = page.evaluate("() => [screen.availWidth, screen.availHeight, screen.availLeft || 0, screen.availTop || 0]")
        if not (isinstance(scr, list) and len(scr) == 4):
            return
        sw, sh, sl, st = (int(v) for v in scr)
        cols = min(n, 2) if sw < 2200 else min(n, 3)
        rows = math.ceil(n / cols)
        w, h = max(600, sw // cols), max(500, sh // rows)
        left, top = sl + (wid % cols) * (sw // cols), st + (wid // cols) * (sh // rows)
        cdp = page.context.new_cdp_session(page)
        win = cdp.send("Browser.getWindowForTarget")
        cdp.send("Browser.setWindowBounds", {"windowId": win["windowId"], "bounds": {"windowState": "normal"}})
        cdp.send("Browser.setWindowBounds", {"windowId": win["windowId"],
                                             "bounds": {"left": left, "top": top, "width": w, "height": h}})
    except Exception:
        pass  # 창 배치는 보기 편하게 하려는 것일 뿐, 실패해도 수집은 계속한다


def profile_path(base: Path, wid: int) -> Path:
    return base if wid == 0 else base.with_name(f"{base.name}_w{wid}")


def base_profile(real_chrome: bool) -> Path:
    base = Path(".browser_profile")
    with contextlib.suppress(Exception):
        base = Path(load_crawler().PROFILE_DIR)
    return base.with_name(CHROME_PROFILE_NAME) if real_chrome else base


def reset_profiles(workers: int, real_chrome: bool) -> None:
    """차단 표시가 남은 쿠키를 버리려고, 이 스크립트가 쓰는 브라우저 프로필 폴더를 지운다."""
    base = base_profile(real_chrome)
    for wid in range(max(1, workers)):
        p = profile_path(base, wid)
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
            print(f"  브라우저 프로필 초기화: {p}", flush=True)


def prepare_profiles(workers: int, real_chrome: bool = False) -> None:
    """작업자별 Chrome 프로필 사본을 작업자를 띄우기 전에 만든다(같은 프로필은 동시에 못 연다).
    원본을 복사해 쿠키를 이어받는다. 캐시는 빼고 복사한다. 이미 있으면 그대로 쓴다."""
    if workers <= 1:
        return
    base = base_profile(real_chrome)
    for wid in range(1, workers):
        dst = profile_path(base, wid)
        if dst.exists() or not base.exists():
            continue
        print(f"  작업자 {wid + 1}용 브라우저 프로필 복사 중: {base} → {dst} (처음 한 번만)", flush=True)
        try:
            shutil.copytree(base, dst, ignore=PROFILE_SKIP)
        except (OSError, shutil.Error) as e:
            print(f"  ⚠ 일부 파일을 복사하지 못했어요({str(e)[:120]}). 그대로 진행해요.", flush=True)


def nap(rng: tuple[float, float]) -> None:
    end = time.time() + random.uniform(*rng)
    while time.time() < end:
        if _STOP is not None and _STOP.is_set():
            return
        time.sleep(0.2)


def worker_main(wid: int, cfg: dict[str, Any], task_q: Any, result_q: Any, stop: Any, lock: Any, last: Any) -> None:
    global _THROTTLE, _STOP, _PREFIX, _SLOT, CUTOFF, FALLBACK_PAGES, QUICK_SKIP
    CUTOFF = date.fromisoformat(cfg["cutoff"])
    FALLBACK_PAGES = cfg.get("scan_pages", FALLBACK_PAGES)
    QUICK_SKIP = bool(cfg.get("quick_skip", QUICK_SKIP))
    _THROTTLE, _STOP, _PREFIX = (lock, last, cfg["min_interval"]), stop, (f"[W{wid + 1}] " if cfg["workers"] > 1 else "")
    _SLOT = None if cfg.get("cdp_url") else (wid, cfg["workers"])  # 원격 Chrome 창은 옮기지 않는다
    session = None
    try:
        cr = load_crawler()
        apply_page_size(cr, cfg)
        if not cfg.get("cdp_url"):
            use_profile(cr, cfg, wid)  # 사본은 메인이 미리 만들어 둔다
        session = open_browser(cr, cfg).__enter__()
        where = cfg["cdp_url"] if cfg.get("cdp_url") else f"{cr.PROFILE_DIR} · {'실제 Chrome' if cfg.get('real_chrome') else '내장 Chromium'}"
        result_q.put(("ready", wid, None, where))
        while not stop.is_set():
            item = task_q.get()
            if item is None:
                break
            result_q.put(("start", wid, item, None))
            try:
                res = process_item(cr, session, item, cfg)
            except Stopped:
                break
            except Blocked as e:
                stop.set()
                result_q.put(("blocked", wid, item, str(e)))
                break
            except Exception as e:
                result_q.put(("error", wid, item, f"{type(e).__name__}: {e}"[:300]))
                if is_closed(e):  # 브라우저·탭이 닫혔으면 새로 띄운다(이 상품은 다음 실행 때 다시)
                    with contextlib.suppress(Exception):
                        session.__exit__(None, None, None)
                    session = open_browser(cr, cfg).__enter__()
                continue
            result_q.put(("done", wid, item, res))
            nap(PRODUCT_DELAY if any(r["period"] == "pre_chatgpt" for r in res["rows"]) else SKIP_DELAY)
    except KeyboardInterrupt:
        pass
    except BaseException as e:  # 브라우저 실행 실패, 패키지 없음 등
        result_q.put(("fatal", wid, None, f"{type(e).__name__}: {e}"[:500]))
    finally:
        if session is not None:
            with contextlib.suppress(Exception):  # 이미 닫힌 브라우저를 닫다 나는 오류는 무시
                session.__exit__(None, None, None)
        result_q.put(("exit", wid, None, None))


def run_items(items: list[dict[str, str]], cfg: dict[str, Any], store: Store) -> int:
    """작업자들에게 상품을 나눠 주고, 끝난 상품을 받는 즉시 JSON 파일에 저장한다."""
    import multiprocessing as mp

    if not items:
        print("새로 확인할 상품이 없어요.")
        return 0
    workers = max(1, min(cfg["workers"], MAX_WORKERS, len(items)))
    cfg = {**cfg, "workers": workers, "cutoff": CUTOFF.isoformat()}
    ctx = mp.get_context("spawn")
    task_q, result_q, stop = ctx.Queue(), ctx.Queue(), ctx.Event()
    lock, last = ctx.Lock(), ctx.Value("d", 0.0)
    for it in items:
        task_q.put(it)
    for _ in range(workers):
        task_q.put(None)
    mode = f"원격 Chrome {cfg['cdp_url']}" if cfg.get("cdp_url") else ("실제 Chrome" if cfg.get("real_chrome") else "내장 Chromium")
    print(f"상품 {len(items)}개를 작업자 {workers}개로 수집해요 ({mode} · 요청 간격 최소 {cfg['min_interval']}초 · 저장: {store.path})")
    if not cfg.get("cdp_url"):
        prepare_profiles(workers, bool(cfg.get("real_chrome")))
    procs = [ctx.Process(target=worker_main, args=(w, cfg, task_q, result_q, stop, lock, last), daemon=True) for w in range(workers)]
    for pr in procs:
        pr.start()
    alive, started, finished, ready = workers, 0, 0, 0
    totals: Counter[str] = Counter()
    blocked = interrupted = False
    try:
        while alive:
            kind, wid, item, payload = result_q.get()
            tag = f"[W{wid + 1}] " if workers > 1 else ""
            if kind == "exit":
                alive -= 1
            elif kind == "start":
                started += 1
                print(f"{tag}▶ [{started}/{len(items)}] {item['product_id']} {item.get('category') or ''} {item.get('name', '')[:30]}", flush=True)
            elif kind == "done":
                prod = store.put_product(item, {**payload, "worker": wid + 1})  # 상품 하나 끝날 때마다 바로 저장
                finished += 1
                n_pre = prod["counts"]["pre_chatgpt"]
                totals[prod["status"]] += 1
                totals["reviews"] += n_pre
                totals["post"] += prod["counts"]["post_chatgpt"]
                why = prod["check"].get("reason", "")
                if n_pre:
                    print(f"{tag}  ✓ {item['product_id']} 이전 리뷰 {n_pre}건 저장" + (f" ({why})" if why else ""), flush=True)
                else:
                    print(f"{tag}  – {item['product_id']} 건너뜀: {why or '과거 리뷰 없음'}", flush=True)
            elif kind == "blocked":
                blocked = True
                print(f"{tag}⛔ 쿠팡이 자동 접근을 막았어요: {payload} → 모든 작업자를 멈추고 쉬었다가 이어서 해요.", flush=True)
            elif kind == "error":
                totals["error"] += 1
                print(f"{tag}  ⚠ {item['product_id']} 실패(다음 실행 때 다시 시도): {payload}", flush=True)
            elif kind == "ready":
                ready += 1
                print(f"{tag}브라우저 준비됨 ({ready}/{workers}) · {payload}", flush=True)
            elif kind == "fatal":
                print(f"{tag}⚠ 작업자를 시작하지 못했어요: {payload}", flush=True)
    except KeyboardInterrupt:
        interrupted = True
        stop.set()
        print("\n중단 요청: 작업자를 멈춰요. 끝난 상품까지는 이미 저장돼 있어요.", flush=True)
    finally:
        for pr in procs:
            pr.join(timeout=20)
            if pr.is_alive():
                pr.terminate()
    print(f"\n{'중단' if (blocked or interrupted) else '완료'}: 수집 {totals['collected']}개 상품·이전 리뷰 {totals['reviews']}건"
          + (f"·이후 {totals['post']}건" if totals["post"] else "")
          + f", 과거 리뷰 없어 건너뜀 {totals['no_old']}개" + (f", 실패 {totals['error']}개" if totals["error"] else "")
          + f" → {store.path}")
    if interrupted:
        return 130
    return 2 if blocked else 0


def cooldown(seconds: int, reason: str) -> None:
    end = time.time() + seconds
    print(f"\n⏸ {reason} → {seconds // 60}분 {seconds % 60}초 쉬었다가 이어서 해요 (Ctrl+C로 중단 가능)", flush=True)
    while (left := int(end - time.time())) > 0:
        print(f"\r   남은 시간 {left // 60:02d}:{left % 60:02d} ", end="", flush=True)
        time.sleep(min(5, left))
    print("\r   다시 시작해요.            ", flush=True)


def run_with_recovery(items: list[dict[str, str]], cfg: dict[str, Any], store: Store) -> int:
    """run_items를 돌리고, 차단되면 쉬었다가 남은 상품으로 다시 돌린다."""
    rounds = cfg.get("block_rounds", len(BLOCK_COOLDOWNS))
    blocks = 0
    while True:
        todo = [it for it in items if not store.is_done(it["product_id"])]
        code = run_items(todo, cfg, store)
        if code != 2:
            return code
        blocks += 1
        if blocks > rounds:
            print(f"   {rounds}번 쉬어도 계속 막혀서 멈춰요. 몇 시간 뒤 같은 명령을 다시 실행하면 이어서 해요.")
            return 2
        try:
            cooldown(BLOCK_COOLDOWNS[min(blocks - 1, len(BLOCK_COOLDOWNS) - 1)], f"차단 {blocks}번째")
        except KeyboardInterrupt:
            print("\n중단했어요. 끝난 상품까지는 저장돼 있어요.")
            return 130
        if blocks >= 2 and not cfg.get("cdp_url"):
            reset_profiles(cfg.get("workers", 1), bool(cfg.get("real_chrome")))


def cmd_collect(args: argparse.Namespace) -> int:
    out_dir = Path(args.out) if args.out else OUT_DIR
    store = Store(out_dir)
    if args.recheck_no_old:
        store.recheck_since = now_iso()
        print("  ※ 이전에 '과거 리뷰 없음'으로 끝난 상품도 다시 확인해요 (--recheck-no-old)")
    products = read_products(Path(args.products))
    todo = [p for p in products if not store.is_done(p["product_id"])]
    print(f"상품 {len(products)}개 / 완료 {len(products) - len(todo)}개 / 남은 {len(todo)}개 · 별점당 이전 {args.per_star}개, "
          f"이후 {args.post_per_star}개 · 기준일 {CUTOFF}")
    if args.max_products:
        todo = todo[: args.max_products]
    cfg = {"mode": "list", "per_star": args.per_star, "post_per_star": args.post_per_star, "per_product": 0,
           "headless": args.headless, "workers": args.workers, "min_interval": args.min_interval, **browser_cfg(args),
           **scan_cfg(args)}
    return run_with_recovery(todo, cfg, store)


def cmd_category(args: argparse.Namespace) -> int:
    cats = read_categories(args.targets, args.name)
    if not cats:
        print("수집할 카테고리가 없습니다. 파일의 '## 이름' 줄 아래에 카테고리 주소"
              "(https://www.coupang.com/np/categories/숫자)를 한 줄에 하나씩 넣어 주세요.")
        other = ROOT / "training_products.txt"
        if other.exists() and "/np/categories/" in other.read_text(encoding="utf-8-sig"):
            print("  → training_products.txt 에 카테고리 주소가 들어 있어요. training_categories.txt 로 옮겨 주세요.")
        return 1
    out_dir = Path(args.out) if args.out else OUT_DIR
    store = Store(out_dir)
    if args.recheck_no_old:
        store.recheck_since = now_iso()
        print("  ※ 이전에 '과거 리뷰 없음'으로 끝난 상품도 다시 확인해요 (--recheck-no-old)")
    print(f"카테고리 {len(cats)}개 · 상품당 최대 {args.per_product}개 · 기준일 {CUTOFF} 이전 · 목록 최대 {args.max_list_pages}페이지")
    # 1) 목록 읽기: 브라우저 하나로 차례대로 (저장된 목록이 있으면 재사용)
    need = [c for c in cats if args.relist or store.listing(c["url"]) is None]
    if need:
        if args.workers > 1:
            print(f"  ※ 카테고리 목록 {len(need)}개는 브라우저 1개로 차례대로 읽어요. 다 읽으면 작업자 {args.workers}개가 동시에 상품을 확인해요.")
        cr = load_crawler()
        bcfg = {"headless": args.headless, **browser_cfg(args)}
        if not bcfg.get("cdp_url"):
            use_profile(cr, bcfg, 0)
        for blocks in range(len(BLOCK_COOLDOWNS) + 1):
            try:
                with open_browser(cr, bcfg) as session:
                    for cat in need:
                        if store.listing(cat["url"]) is not None and not args.relist:
                            continue  # 차단 전에 이미 읽은 목록
                        print(f"\n▶ 카테고리 목록 [{cat['name'] or '이름 없음'}] {cat['url']}")
                        store.set_listing(cat["url"], cat["name"], list_category(cr, session, cat["url"], args.max_list_pages))
                break
            except Blocked as e:
                if blocks >= len(BLOCK_COOLDOWNS):
                    print(f"\n⛔ 쿠팡이 계속 막아서 멈춰요: {e}\n   나중에 같은 명령을 다시 실행하면 이어서 해요.")
                    return 2
                cooldown(BLOCK_COOLDOWNS[blocks], f"카테고리 목록 차단: {e}")
    # 2) 상품 나눠 수집
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for cat in cats:
        products = store.listing(cat["url"]) or []
        todo = [p for p in products if not store.is_done(p["product_id"]) and p["product_id"] not in seen]
        print(f"  [{cat['name'] or cat['url']}] 상품 {len(products)}개 / 확인 끝 {len(products) - len(todo)}개 / 남은 {len(todo)}개")
        if args.max_products:
            todo = todo[: args.max_products]
        for p in todo:
            seen.add(p["product_id"])
            items.append({**p, "category": cat["name"]})
    cfg = {"mode": "category", "per_product": args.per_product, "post_per_star": args.post_per_star, "per_star": 0,
           "headless": args.headless, "workers": args.workers, "min_interval": args.min_interval, **browser_cfg(args),
           **scan_cfg(args)}
    return run_with_recovery(items, cfg, store)


def scan_cfg(args: argparse.Namespace) -> dict[str, Any]:
    return {"page_size": getattr(args, "page_size", 10), "scan_pages": getattr(args, "scan_pages", FALLBACK_PAGES),
            "quick_skip": getattr(args, "quick_skip", False)}


def browser_cfg(args: argparse.Namespace) -> dict[str, Any]:
    """명령줄 옵션 → 브라우저 설정. 실제 Chrome은 설치돼 있으면 기본으로 쓴다."""
    cdp_url = getattr(args, "cdp_url", "") or ""
    real = (not getattr(args, "no_real_chrome", False)) and not cdp_url and find_chrome() is not None
    if not cdp_url and not getattr(args, "no_real_chrome", False) and not real:
        print("  ※ Google Chrome을 찾지 못해 내장 Chromium으로 실행해요 (Chrome을 설치하면 자동으로 씀)")
    return {"cdp_url": cdp_url, "real_chrome": real}


def cmd_chrome(args: argparse.Namespace) -> int:
    """원격 연결용으로 Mac의 Chrome을 전용 프로필 + 디버깅 포트로 띄운다."""
    import subprocess  # noqa: PLC0415

    url = f"http://localhost:{args.port}"
    if cdp_alive(url):
        print(f"이미 원격 연결용 Chrome이 떠 있어요: {url}")
    else:
        exe = find_chrome()
        if not exe:
            print("Google Chrome을 찾지 못했어요. https://www.google.com/chrome/ 에서 설치한 뒤 다시 실행하세요.")
            return 1
        profile = Path(args.profile).expanduser()
        profile.mkdir(parents=True, exist_ok=True)
        cmd = [exe, f"--remote-debugging-port={args.port}", f"--user-data-dir={profile}", *CDP_FLAGS,
               "https://www.coupang.com/"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)  # noqa: S603
        for _ in range(40):
            if cdp_alive(url):
                break
            time.sleep(0.5)
        else:
            print(f"Chrome은 띄웠지만 {url} 에 연결되지 않아요. 다른 Chrome이 같은 프로필을 쓰고 있는지 확인하세요: {profile}")
            return 1
        print(f"원격 연결용 Chrome을 띄웠어요 · 프로필 {profile} · 주소 {url}")
    print("\n  1) 뜬 Chrome 창에서 쿠팡이 정상으로 보이는지 확인하세요. 상품 몇 개를 직접 둘러보면 쿠키가 자연스럽게 쌓여요.")
    print("  2) 이 창은 켜 둔 채로, 다른 터미널에서 수집 명령에 --cdp-url 을 붙여 실행하세요:")
    print(f"       python collect_training_data.py collect training_products.txt --cdp-url {url}")
    print("  ※ 평소 쓰는 Chrome과 별개의 프로필이라 평소 Chrome의 로그인·기록은 건드리지 않아요.")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """상품 하나로 1,500개 상한·최신순 정렬·이진 탐색이 되는지 확인한다(저장하지 않음)."""
    cr = load_crawler()
    apply_page_size(cr, {"page_size": args.page_size})
    pid = cr.product_id_from_url(args.url)
    box: dict[str, Any] = {}

    def action(page: Any) -> Any:
        try:
            cr.warm_up(page)
            box["check"] = old_review_check(cr, page, pid, print)
            known = (box["check"].get("star_counts") or {}).get(str(args.star))
            pager = ReviewPager(cr, page, pid, args.star, DATE_SORT, print)
            first = pager.get(1)
            ds = [r["_date"] for r in first if r["_date"]]
            box["first"] = {"n": len(first), "dates": ds, "desc": is_desc(first),
                            "flips": sum(1 for a, b in zip(ds, ds[1:]) if a < b)}
            box["trial"] = collect_star(cr, page, pid, args.star, 10, 3, print, known_count=known)
        except Exception as e:
            box["error"] = e
        return page

    bcfg = {"headless": args.headless, **browser_cfg(args)}
    if not bcfg.get("cdp_url"):
        use_profile(cr, bcfg, 0)
    with open_browser(cr, bcfg) as session:
        resp = session.fetch(args.url, page_action=action)
    if "error" in box:
        if isinstance(box["error"], Blocked) or getattr(resp, "status", 200) != 200:
            print(f"⛔ 쿠팡이 막았어요: {box['error']}")
            return 2
        raise box["error"]
    c = box["check"]
    sc = c.get("star_counts") or {}
    print(f"[상품 전체] 리뷰 {c.get('total') or 0:,}개 (" + ", ".join(f"{k}점 {v:,}" for k, v in sc.items()) + ")")
    if c.get("window"):
        print(f"   최신순 {c['window']:,}번째 리뷰 날짜: {c.get('window_oldest')}"
              + ("  ← 쿠팡이 보여 주는 끝(1,500번째)" if c.get("capped") else "  ← 마지막 리뷰"))
    print(f"   판정: {'수집할 과거 리뷰 있음(또는 별점별 확인)' if c['has_old'] else '수집할 과거 리뷰 없음'} · {c['reason']}")
    f = box["first"]
    print(f"[{args.star}점 최신순 첫 페이지] {f['n']}개 · 날짜 {', '.join(d.isoformat() for d in f['dates'][:5])}"
          f" · 날짜순? {'예' if f['desc'] else '아니오'} (어긋난 곳 {f['flips']})")
    t = box["trial"]
    pre_dates = sorted(r["_date"] for r in t["pre"])
    print(f"[시험 수집 {args.star}점] 리뷰 {t['count'] or 0:,}개 · 보이는 범위 {t['window']:,}개"
          + (f" · 그 끝 날짜 {t['window_oldest']}" if t["window_oldest"] else "")
          + f" · 방식 {t['method']} · 요청 {t['requests']}회 · 이전 {len(t['pre'])}개"
          + (f" ({pre_dates[0]} ~ {pre_dates[-1]})" if pre_dates else "") + f" · 이후 {len(t['post'])}개")
    if not f["desc"]:
        print(f"※ {args.star}점 목록은 최신순을 요청해도 날짜가 섞여 나와서, 1,500개 안을 앞에서부터 훑는 방식으로 모아요.")
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
    store = Store(out_dir)
    by_period: dict[str, Counter[tuple[int, str]]] = defaultdict(Counter)
    products: dict[str, set[str]] = defaultdict(set)
    categories: Counter[str] = Counter()
    years: Counter[int] = Counter()
    for r in store.reviews():
        per = r.get("period") or "boundary"
        by_period[per][(int(r["star"]), r.get("length_bucket") or length_bucket(r["content"]))] += 1
        products[per].add(r["product_id"])
        if per == "pre_chatgpt":
            categories[r.get("category") or "(미지정)"] += 1
            if r.get("created_at"):
                years[int(r["created_at"][:4])] += 1
    print(f"파일: {store.path}")
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
    if store.data["products"]:
        per_cat: dict[str, Counter[str]] = defaultdict(Counter)
        for info in store.data["products"].values():
            per_cat[info.get("category") or "(미지정)"][info.get("status") or "?"] += 1
        print("\n[확인한 상품] 카테고리: 수집 / 과거 리뷰 없어 건너뜀")
        for cat, c in sorted(per_cat.items()):
            print(f"  {cat}: {c['collected']} / {c['no_old']}")
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
    g = sub.add_parser("category", help="카테고리 안 상품을 돌며 과거 리뷰가 있으면 수집")
    g.add_argument("targets", nargs="+", help="카테고리 URL(여러 개 가능) 또는 '## 이름' + URL 형식 txt 파일")
    g.add_argument("--name", default="", help="URL로 줄 때 카테고리 이름")
    g.add_argument("--per-product", type=int, default=PER_PRODUCT, help=f"상품당 최대 리뷰 수 (기본 {PER_PRODUCT})")
    g.add_argument("--post-per-star", type=int, default=0, help="상품·별점당 2023년 이후 리뷰 수 (기본 0=안 함)")
    g.add_argument("--max-list-pages", type=int, default=LIST_PAGES, help=f"목록을 넘겨 볼 최대 페이지 (기본 {LIST_PAGES})")
    g.add_argument("--max-products", type=int, default=0, help="카테고리마다 이번에 확인할 최대 상품 수")
    g.add_argument("--relist", action="store_true", help="저장된 상품 목록을 무시하고 목록을 다시 읽기")
    g.add_argument("--headless", action="store_true", help="브라우저 창 숨기기 (차단이 늘 수 있음)")
    i = sub.add_parser("inspect", help="상품 하나로 날짜순 정렬·이진 탐색 점검")
    i.add_argument("url")
    i.add_argument("--star", type=int, default=5)
    i.add_argument("--headless", action="store_true")
    n = sub.add_parser("naver", help="네이버 쇼핑 리뷰 20만 건 내려받기·변환")
    n.add_argument("--force", action="store_true", help="이미 받은 파일이 있어도 다시 받기")
    sub.add_parser("stats", help="모인 데이터 양 보기")
    ch = sub.add_parser("chrome", help="원격 연결용으로 Mac의 Chrome을 전용 프로필로 띄우기")
    ch.add_argument("--port", type=int, default=CDP_PORT, help=f"원격 디버깅 포트 (기본 {CDP_PORT})")
    ch.add_argument("--profile", default=str(CDP_PROFILE), help=f"전용 Chrome 프로필 폴더 (기본 {CDP_PROFILE})")
    for p in (c, g, i):
        p.add_argument("--page-size", type=int, default=10,
                       help="한 번에 받는 리뷰 수 (기본 10 = 쿠팡 화면과 같음. 50을 받아 주면 같은 1,500개를 더 적은 요청으로 봄)")
    for p in (c, g):
        p.add_argument("--scan-pages", type=int, default=FALLBACK_PAGES,
                       help=f"날짜가 섞여 나오는 별점 목록에서 1,500개 안을 훑어볼 최대 페이지 (기본 {FALLBACK_PAGES})")
        p.add_argument("--recheck-no-old", action="store_true", help="이전에 '과거 리뷰 없음'으로 끝난 상품도 다시 확인")
    g.add_argument("--quick-skip", action="store_true",
                   help="리뷰 1,500개 초과 상품도 전체 목록 1,500번째 리뷰가 2022-11-30 이후면 바로 건너뜀 "
                        "(빠르지만 1~4점 목록에만 남은 과거 리뷰를 놓침)")
    for p in (c, g, i):
        p.add_argument("--cdp-url", default="", help="이미 띄운 Chrome에 연결 (예: http://localhost:9222, `chrome` 명령으로 띄움)")
        p.add_argument("--no-real-chrome", action="store_true", help="설치된 Chrome 대신 내장 Chromium 사용")
    for p in (c, g):
        p.add_argument("--workers", type=int, default=1, help=f"동시에 띄울 브라우저 수 (기본 1, 최대 {MAX_WORKERS}, 권장 2~3)")
        p.add_argument("--min-interval", type=float, default=MIN_INTERVAL,
                       help=f"모든 브라우저를 합친 요청 사이 최소 간격(초, 기본 {MIN_INTERVAL})")
    for p in (c, g, n, sub.choices["stats"]):
        p.add_argument("--out", default="", help="결과 폴더 (기본 model/data/raw/…)")
    for p in sub.choices.values():  # --cutoff는 명령 앞·뒤 어디에 써도 된다
        p.add_argument("--cutoff", dest="cutoff_sub", default=None, help="사람 리뷰 기준일 (기본 2022-11-30)")
    ap.add_argument("--cutoff", default=CUTOFF.isoformat(), help="사람 리뷰 기준일 (기본 2022-11-30)")
    cmds = {"collect": cmd_collect, "category": cmd_category, "inspect": cmd_inspect, "naver": cmd_naver, "stats": cmd_stats,
            "chrome": cmd_chrome}
    # 명령 앞에 --를 붙여 쓴 경우(--category)도 받아 준다
    raw = list(sys.argv[1:] if argv is None else argv)
    raw = [a[2:] if a.startswith("--") and a[2:] in cmds and a[2:] not in raw else a for a in raw]
    args = ap.parse_args(raw)
    try:
        CUTOFF = date.fromisoformat(args.cutoff_sub or args.cutoff)
    except ValueError:
        ap.error(f"--cutoff 날짜 형식이 올바르지 않아요(예: 2022-11-30): {args.cutoff_sub or args.cutoff}")
    return cmds[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())