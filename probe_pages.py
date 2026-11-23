"""
쿠팡 리뷰 API 점검: 페이지 상한과 최신순 정렬이 실제로 어떻게 동작하는지 상품 하나로 확인한다. (저장하지 않음)

  python probe_pages.py "<쿠팡 상품 URL>" --cdp-url http://localhost:9222
  python probe_pages.py "<쿠팡 상품 URL>" --cdp-url http://localhost:9222 --stars 5 1

확인하는 것
  1) 별점별 실제 리뷰 수 (요약 정보의 별점별 개수)
  2) 최신순(DATE_DESC)과 기본 정렬(베스트순)의 첫 페이지가 같은 리뷰인지 → 같으면 최신순이 무시된 것
  3) 한 페이지 크기(size)를 키울 수 있는지, 그때 상한이 '150페이지'인지 '1,500개'인지
  --sort 로 다른 정렬값을 시험할 수 있다 (개발자 도구에서 찾은 값)
요청은 별점당 6~7번, 요청 사이 2.5~5초 쉰다.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_training_data as ctd  # noqa: E402

KST = timezone(timedelta(hours=9))
DATE_FIELDS = ("reviewAt", "createdAt", "modifiedAt", "updatedAt")


def to_day(v):
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        n = float(v)
        n = n / 1000 if n > 1e11 else n
        return datetime.fromtimestamp(n, KST).date() if n > 1e9 else None
    return ctd.parse_date(v)


def outline(obj, path="", depth=0, out=None):
    """JSON 구조를 한 줄씩: 키 이름, 리스트 길이, 짧은 값."""
    out = [] if out is None else out
    if depth > 3 or len(out) > 60:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if isinstance(v, (dict, list)):
                out.append(f"{p}: {'{…}' if isinstance(v, dict) else f'[{len(v)}개]'}")
                outline(v if isinstance(v, dict) else (v[0] if v else {}), p + ("" if isinstance(v, dict) else "[0]"), depth + 1, out)
            else:
                out.append(f"{p} = {str(v)[:40]!r}")
    return out


def inversions(days):
    ds = [d for d in days if d]
    return sum(1 for a, b in zip(ds, ds[1:]) if a < b), max(0, len(ds) - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--cdp-url", default="")
    ap.add_argument("--stars", type=int, nargs="+", default=[5, 4, 1])
    ap.add_argument("--sort", default=ctd.DATE_SORT, help="시험할 최신순 정렬값 (기본 DATE_DESC)")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--no-real-chrome", action="store_true")
    args = ap.parse_args()

    cr = ctd.load_crawler()
    pid = cr.product_id_from_url(args.url)
    cfg = {"headless": args.headless, **ctd.browser_cfg(args)}
    if not cfg.get("cdp_url"):
        ctd.use_profile(cr, cfg, 0)
    lines = []

    def get(page, sort, star, page_no):
        cr.pause(page, cr.API_DELAY_RANGE)
        url = cr.API_BASE + "?" + urlencode({
            "productId": pid, "page": page_no, "size": cr.PAGE_SIZE, "sortBy": sort,
            "ratingSummary": "true", "ratings": "" if star is None else str(star), "market": ""})
        try:
            data = cr.api_get(page, url)
        except Exception as e:
            return None, str(e)[:60]
        items = cr.find_review_list(data)
        total = cr.find_number(data, cr.TOTAL_KEYS, skip_lists=items)
        return items, (int(total) if total is not None else None)

    def action(page):
        try:
            cr.warm_up(page)
            data = cr.api_get(page, cr.API_BASE + "?" + urlencode({
                "productId": pid, "page": 1, "size": cr.PAGE_SIZE, "sortBy": cr.SORT_BY,
                "ratingSummary": "true", "ratings": "", "market": ""}))
            counts = cr.find_rating_counts(data) or {}
            lines.append(f"[요약] 별점별 실제 리뷰 수: " + ", ".join(f"{k}점 {v:,}" for k, v in counts.items()))
            # review/batch: 쿠팡 화면이 리뷰 영역을 그릴 때 함께 부르는 요청. 안에 뭐가 있는지 구조만 본다.
            try:
                cr.pause(page, cr.API_DELAY_RANGE)
                batch = cr.api_get(page, cr.API_BASE + "/batch?" + urlencode({"productId": pid, "viRoleCode": 3}))
                Path("probe_batch.json").write_text(__import__("json").dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
                lines.append("[batch] 구조 (전체는 probe_batch.json):")
                lines.extend(f"   {ln}" for ln in outline(batch)[:40])
                bc = cr.find_rating_counts(batch)
                if bc:
                    lines.append(f"   → 별점별 개수 있음: {bc}")
            except Exception as e:
                lines.append(f"[batch] 실패: {str(e)[:80]}")
            for star in args.stars:
                n = counts.get(star)
                lines.append(f"\n[{star}점] 실제 {n if n is not None else '?':,}개 = {-(-(n or 0) // cr.PAGE_SIZE)}페이지" if n is not None else f"\n[{star}점]")
                a, _ = get(page, args.sort, star, 1)
                b, _ = get(page, cr.SORT_BY, star, 1)
                if not a or not b:
                    lines.append("   첫 페이지 실패")
                    continue
                ida, idb = [x.get("reviewId") for x in a], [x.get("reviewId") for x in b]
                same = sum(1 for x in ida if x in idb)
                inv, pairs = inversions([to_day(x.get("reviewAt")) for x in a])
                lines.append(f"   {args.sort} 첫 페이지: 뒤집힘 {inv}/{pairs} · 베스트순 첫 페이지와 겹치는 리뷰 {same}/{len(ida)}"
                             + ("  ← 최신순이 무시되고 베스트순으로 나옴" if same == len(ida) else ""))
                for size in (20, 50):
                    url_items, _ = get_size(page, args.sort, star, 1, size)
                    if url_items is None:
                        lines.append(f"   size={size}: 실패")
                        continue
                    msg = f"   size={size}: 1페이지 {len(url_items)}개"
                    if len(url_items) == size and n and n > 1500:
                        p_after = 1500 // size + 1          # 1,500개 상한이면 여기서 비어야 함
                        far, _ = get_size(page, args.sort, star, p_after, size)
                        msg += (f" · {p_after}페이지({(p_after - 1) * size + 1}번째~) {len(far) if far is not None else '실패'}개"
                                + ("  → 상한은 '150페이지' (크게 받으면 더 깊이 닿음 ✓)" if far else "  → 상한은 '약 1,500개'"))
                    lines.append(msg)
                    if len(url_items) < size:
                        break  # 이 크기를 안 받아 주면 더 큰 크기도 안 됨
        except Exception as e:
            lines.append(f"오류: {type(e).__name__}: {e}")
        return page

    def get_size(page, sort, star, page_no, size):
        cr.pause(page, cr.API_DELAY_RANGE)
        url = cr.API_BASE + "?" + urlencode({
            "productId": pid, "page": page_no, "size": size, "sortBy": sort,
            "ratingSummary": "true", "ratings": str(star), "market": ""})
        try:
            return cr.find_review_list(cr.api_get(page, url)), None
        except Exception as e:
            return None, str(e)[:60]

    with ctd.open_browser(cr, cfg) as session:
        resp = session.fetch(args.url, page_action=action)
    print(f"상품 {pid} · 상품 페이지 HTTP {resp.status}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()