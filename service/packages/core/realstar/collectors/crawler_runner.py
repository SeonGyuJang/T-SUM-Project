"""사용자 수집기(저장소 루트 coupang_reviews.py)를 그대로 실행하면서 진행 이벤트를 내보내는 실행기.

서비스(API·워커)가 subprocess로 실행한다. 수집 로직은 고치지 않고, 수집기 모듈의 함수를
감싸서(wrap) 진행 상황만 관찰한다. realstar 패키지를 import하지 않으므로 수집기 전용
가상환경의 파이썬(CRAWLER_PYTHON)으로도 실행할 수 있다.

  python crawler_runner.py collect --script ../coupang_reviews.py --url URL [--per-rating 100] [--headless] [--out DIR]
  python crawler_runner.py search  --script ../coupang_reviews.py --query "상품명" [--limit 20] [--headless]
  python crawler_runner.py resolve --script ../coupang_reviews.py --url https://link.coupang.com/a/xxx [--headless]

stdout 한 줄 = 이벤트 하나: "@@RS@@" + JSON. 그 밖의 출력은 수집기 로그로 취급된다.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import traceback
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

PREFIX = "@@RS@@"
SEARCH_URL = "https://www.coupang.com/np/search"
BLOCK_HINTS = ("403", "차단", "JSON이 아닌 응답", "Access Denied", "사용권한")


def emit(type_: str, **kw: Any) -> None:
    print(PREFIX + json.dumps({"type": type_, **kw}, ensure_ascii=False, default=str), flush=True)


def load_crawler(script: Path) -> Any:
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("coupang_reviews", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"수집기 파일을 불러올 수 없음: {script}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def error_kind(msg: str) -> str:
    return "blocked" if any(h in msg for h in BLOCK_HINTS) else "error"


# ──────────────────────────────────────────────────────────────
# collect: 상품 하나 수집 → output/products/<상품ID>.json
# ──────────────────────────────────────────────────────────────
def cmd_collect(cr: Any, args: argparse.Namespace) -> int:
    if args.out:
        out = Path(args.out)
        cr.OUTPUT_DIR, cr.PRODUCT_DIR, cr.RAW_DIR = out, out / "products", out / "raw"
    cr.PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
    pid = cr.product_id_from_url(args.url)

    orig_summary, orig_rating, orig_page, orig_warm = cr.collect_summary, cr.collect_rating, cr.fetch_review_page, cr.warm_up
    st: dict[str, Any] = {"pages": 0, "warmed": False, "seen": {}, "target": {}, "image": None}

    def warm_up(page: Any) -> Any:
        if not st["warmed"]:
            st["warmed"] = True
            meta: dict[str, Any] = {}
            try:
                meta = page.evaluate(
                    "() => ({title: document.querySelector('meta[property=\"og:title\"]')?.content || document.title || null,"
                    " image: document.querySelector('meta[property=\"og:image\"]')?.content || null})"
                ) or {}
            except Exception:
                meta = {}
            img = meta.get("image")
            if isinstance(img, str) and img.startswith("//"):
                img = "https:" + img
            st["image"] = img
            name = cr.clean_product_name(meta.get("title") or "") if meta.get("title") else None
            emit("product", product_id=pid, name=name, image_url=img)
            emit("stage", stage="page_loaded", message="상품 페이지를 열었어요. 리뷰 정보를 요청하고 있어요")
        return orig_warm(page)

    def collect_summary(page: Any, pid_: str, log: Any = print) -> Any:
        emit("stage", stage="summary", message="별점별 리뷰 개수를 확인하고 있어요")
        data, info = orig_summary(page, pid_, log)
        counts = info.get("rating_counts") or {}
        emit("summary", total=info.get("total_reviews"), average=info.get("average_rating"),
             rating_counts={str(k): v for k, v in counts.items()})
        return data, info

    def collect_rating(page: Any, pid_: str, rating: int, target: int, log: Any = print) -> Any:
        st["seen"][rating] = set()
        st["target"][rating] = target
        emit("star_start", star=rating, target=target)
        got, ftotal, final_target = orig_rating(page, pid_, rating, target, log)
        emit("star_done", star=rating, collected=len(got), target=final_target, filtered_total=ftotal)
        return got, ftotal, final_target

    def fetch_review_page(page: Any, pid_: str, rating: int, page_no: int, log: Any = print) -> Any:
        data, items = orig_page(page, pid_, rating, page_no, log)
        st["pages"] += 1
        seen = st["seen"].setdefault(rating, set())
        target = st["target"].get(rating, 0)
        if items:
            if page_no == 1:  # 필터 응답이 알려 준 실제 개수로 목표 보정 (수집기와 같은 규칙)
                t = cr.find_number(data, cr.TOTAL_KEYS, skip_lists=items)
                if t is not None:
                    target = min(target, int(t))
                    st["target"][rating] = target
            for raw in items:
                r = cr.parse_review(raw)
                seen.add(r["review_id"] or (r["date"], r["content"][:80]))
        emit("page", star=rating, page=page_no, items=len(items or []), pages_loaded=st["pages"],
             collected=min(len(seen), target) if target else len(seen), target=target)
        return data, items

    cr.warm_up, cr.collect_summary, cr.collect_rating, cr.fetch_review_page = warm_up, collect_summary, collect_rating, fetch_review_page

    def log(msg: Any) -> None:
        emit("log", message=str(msg).strip())

    emit("stage", stage="browser", message="수집용 브라우저를 실행하고 있어요")
    try:
        with cr.open_session(headless=args.headless) as session:
            emit("stage", stage="open_page", message="쿠팡 상품 페이지를 열고 있어요")
            result = cr.collect_product(session, args.url, args.per_rating, log)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}" if not str(e) else str(e)
        try:
            with (cr.OUTPUT_DIR / "failed.txt").open("a", encoding="utf-8") as f:
                f.write(f"{args.url}\t{msg}\n")
        except Exception:
            pass
        emit("error", kind=error_kind(msg), message=msg[:500], pages_loaded=st["pages"])
        return 1

    info = result["상품정보"]
    if st["image"] and not info.get("대표이미지"):
        info["대표이미지"] = st["image"]
    path = cr.PRODUCT_DIR / f"{info['상품ID']}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    try:  # 수집기 collect 명령과 같은 합본 파일도 갱신
        merged = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(cr.PRODUCT_DIR.glob("*.json"))]
        (cr.OUTPUT_DIR / "all_products.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    emit("result", path=str(path.resolve()), complete=bool(info.get("수집_완료")), reviews=len(result["리뷰"]), pages_loaded=st["pages"])
    return 0


# ──────────────────────────────────────────────────────────────
# search: 쿠팡 검색 결과 첫 페이지 → 상품 후보
# ──────────────────────────────────────────────────────────────
_PID = re.compile(r"/vp/products/(\d+)")
_PRICE = re.compile(r"^\s*([\d,]{3,})\s*원?\s*$")
_RATING = re.compile(r"^\s*([1-5](?:\.\d)?)\s*$")
_COUNT = re.compile(r"^\s*\(\s*([\d,]+)\s*\)\s*$")
_VOID = {"img", "br", "hr", "input", "meta", "link", "source", "wbr", "area", "col", "embed", "param", "track"}


class _SearchParser(HTMLParser):
    """검색 결과에서 /vp/products/ 링크 단위로 이름·이미지·가격·별점·리뷰 수를 모은다.

    쿠팡 화면 클래스 이름은 자주 바뀌므로 특정 클래스에 기대지 않고 링크 안의 텍스트 모양으로 판단한다.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, Any]] = []
        self.cur: dict[str, Any] | None = None
        self.depth = 0
        self.classes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if self.cur is None:
            if tag == "a" and _PID.search(a.get("href", "")):
                self.cur = {"href": a["href"], "texts": [], "img": None, "alt": None, "ad": "ad" in a.get("class", "").lower()}
                self.depth, self.classes = 0, []
            return
        if tag == "img" and self.cur["img"] is None:
            for attr in ("data-img-src", "data-src", "src"):
                v = a.get(attr)
                if v and not v.startswith("data:"):
                    self.cur["img"] = v
                    break
            self.cur["alt"] = a.get("alt") or None
        if tag in _VOID:
            return
        self.depth += 1
        self.classes.append(a.get("class", ""))
        if "ad-badge" in a.get("class", "").lower() or "adbadge" in a.get("class", "").lower():
            self.cur["ad"] = True

    def handle_endtag(self, tag: str) -> None:
        if self.cur is None or tag in _VOID:
            return
        if tag == "a" and self.depth == 0:
            self.items.append(self.cur)
            self.cur = None
            return
        self.depth = max(0, self.depth - 1)
        if self.classes:
            self.classes.pop()

    def handle_data(self, data: str) -> None:
        if self.cur is not None and data.strip():
            self.cur["texts"].append((data.strip(), " ".join(self.classes[-3:]).lower()))


def parse_search_html(html: str, limit: int) -> list[dict[str, Any]]:
    p = _SearchParser()
    p.feed(html)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in p.items:
        href = it["href"]
        m = _PID.search(href)
        if not m:
            continue
        pid = m.group(1)
        texts: list[tuple[str, str]] = it["texts"]
        name = next((t for t, c in texts if "name" in c and len(t) >= 4), None) or it["alt"]
        if not name:
            cands = [t for t, _ in texts if not _PRICE.match(t) and not _RATING.match(t) and not _COUNT.match(t)]
            name = max(cands, key=len) if cands else None
        if not name:
            continue
        price = next((int(mm.group(1).replace(",", "")) for t, c in texts if (mm := _PRICE.match(t)) and ("price" in c or t.endswith("원"))), None)
        rating = next((float(mm.group(1)) for t, c in texts if "rating" in c and (mm := _RATING.match(t))), None)
        count = next((int(mm.group(1).replace(",", "")) for t, _ in texts if (mm := _COUNT.match(t))), None)
        qs = parse_qs(urlparse(href).query)
        item_id = (qs.get("itemId") or [""])[0] or None
        key = f"{pid}:{item_id or ''}"
        if key in seen or any(o["product_id"] == pid for o in out):
            continue
        seen.add(key)
        img = it["img"]
        if img and img.startswith("//"):
            img = "https:" + img
        out.append({
            "product_id": pid,
            "item_id": item_id,
            "vendor_item_id": (qs.get("vendorItemId") or [""])[0] or None,
            "name": name.strip(),
            "price": price,
            "image_url": urljoin("https://www.coupang.com", img) if img else None,
            "url": urljoin("https://www.coupang.com", href),
            "is_ad": bool(it["ad"]) or "ads" in (qs.get("sourceType") or [""])[0].lower(),
            "rating": rating,
            "review_count": count,
        })
        if len(out) >= limit:
            break
    return out


def cmd_search(cr: Any, args: argparse.Namespace) -> int:
    url = SEARCH_URL + "?" + urlencode({"q": args.query, "channel": "user"})
    box: dict[str, Any] = {}

    def action(page: Any) -> Any:
        try:
            cr.warm_up(page)
            box["html"] = page.content()
        except Exception as e:
            box["error"] = e
        return page

    emit("stage", stage="browser", message="쿠팡에서 상품을 검색하고 있어요")
    try:
        with cr.open_session(headless=args.headless) as session:
            resp = session.fetch(url, page_action=action)
        if getattr(resp, "status", 200) != 200:
            raise RuntimeError(f"검색 페이지 HTTP {resp.status} (차단되었을 수 있음)")
        if "error" in box:
            raise box["error"]
        html = box.get("html") or ""
        if any(h in html[:20000] for h in ("Access Denied", "사용권한이 없습니다")):
            raise RuntimeError("검색 페이지 접근 거부 (차단되었을 수 있음)")
    except Exception as e:
        msg = str(e) or type(e).__name__
        emit("error", kind=error_kind(msg), message=msg[:500])
        return 1
    emit("search_result", candidates=parse_search_html(html, args.limit))
    return 0


# ──────────────────────────────────────────────────────────────
# resolve: 공유·단축 링크 → 최종 상품 URL
# ──────────────────────────────────────────────────────────────
def cmd_resolve(cr: Any, args: argparse.Namespace) -> int:
    box: dict[str, Any] = {}

    def action(page: Any) -> Any:
        box["url"] = page.url
        return page

    try:
        with cr.open_session(headless=args.headless) as session:
            resp = session.fetch(args.url, page_action=action)
        final = box.get("url") or getattr(resp, "url", None) or ""
    except Exception as e:
        msg = str(e) or type(e).__name__
        emit("error", kind=error_kind(msg), message=msg[:500])
        return 1
    emit("resolved", url=final)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="coupang_reviews.py 실행기 (진행 이벤트 출력)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "search", "resolve"):
        p = sub.add_parser(name)
        p.add_argument("--script", required=True)
        p.add_argument("--headless", action="store_true")
        if name in ("collect", "resolve"):
            p.add_argument("--url", required=True)
        if name == "collect":
            p.add_argument("--per-rating", type=int, default=100)
            p.add_argument("--out", default="")
        if name == "search":
            p.add_argument("--query", required=True)
            p.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)

    script = Path(args.script).resolve()
    if not script.exists():
        emit("error", kind="setup", message=f"수집기 파일이 없습니다: {script}")
        return 2
    try:
        cr = load_crawler(script)
    except ModuleNotFoundError as e:
        emit("error", kind="setup", message=f"수집기 실행에 필요한 패키지가 없습니다: {e.name} "
             "(pip install \"scrapling[fetchers]\" && scrapling install)")
        return 2
    except Exception as e:
        emit("error", kind="setup", message=f"수집기를 불러오지 못했습니다: {type(e).__name__}: {e}",
             trace=traceback.format_exc()[-1500:])
        return 2
    return {"collect": cmd_collect, "search": cmd_search, "resolve": cmd_resolve}[args.cmd](cr, args)


if __name__ == "__main__":
    sys.exit(main())
