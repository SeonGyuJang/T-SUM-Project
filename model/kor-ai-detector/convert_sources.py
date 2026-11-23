"""모은 사람 리뷰들을 README 4.3 공통 형식으로 바꿔 **파일 하나**(data/raw/human_reviews.jsonl)로 합칩니다.

  AI Hub 속성기반 감정분석  model/data/raw/AI_hub/pre/<구분 폴더>/*.json   (직접 압축을 풀어 넣은 것, 약 25만 건)
  네이버 쇼핑              model/data/raw/naver/naver_shopping.jsonl      (python collect_training_data.py naver, 20만 건)
  쿠팡 (있으면)            model/data/raw/coupang/coupang_training.json

  python convert_sources.py              # → data/raw/human_reviews.jsonl  (+ 출처·카테고리·별점·날짜 요약 출력)
  python convert_sources.py --no-coupang # 쿠팡 수집분은 빼기

JSONL = 한 줄에 리뷰 하나인 JSON. 45만 건을 JSON 배열 하나로 두면 매번 통째로 읽어야 해서 느려 이 형식을 씁니다.
공통 형식 필드: text, product_id, platform, date, rating(1~5), category, product_name, source_id
- AI Hub: ReviewScore(0~100)를 1~5점으로(20점 단위, 반올림), RDate → date, 카테고리 = "Domain > MainCategory",
  product_id = 같은 카테고리·상품명이면 같은 값(같은 상품 리뷰가 학습과 테스트에 갈라지지 않게).
  상품명의 비식별 표시(OO, 스** 같은 가림)는 product_name에서 지웁니다(AI 생성 프롬프트에 그대로 들어가지 않게). 본문은 그대로 둡니다.
  2022-12-01 이후 날짜 리뷰는 사람 라벨로 쓰지 않아 뺍니다(--cutoff).
- 네이버 말뭉치에는 상품 정보가 없어 리뷰마다 product_id = "nv-<리뷰ID>"(리뷰 1건 = 그룹 1개)로 둡니다.
  날짜도 없어서 수집 시점(2020년 6~7월)의 상한인 2020-07-31을 넣습니다(--human-before 필터 통과용, date_estimated=true).
- 쿠팡은 2022-11-30 이전(period=pre_chatgpt) 리뷰만 내보냅니다. '쿠팡캐시 리뷰 이벤트' 고지 문구는 본문에서 뗍니다(README 4.4-4).
"""
import argparse
import glob
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DATA = os.path.join(os.path.dirname(ROOT), "data", "raw")
CASH_EVENT = re.compile(r"본\s*(?:리뷰|후기)[^.\n]{0,80}?쿠팡\s*캐시[^.\n]{0,80}?(?:작성|참여)[^.\n]{0,30}?(?:것입니다|합니다|했습니다)\.?\s*")


def write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  → {path}: {len(rows):,}건")


MASK_TOKEN = re.compile(r"^(?:O{2,}|0{2,}|X{2,})$|\*")


def nfc(x):
    return unicodedata.normalize("NFC", str(x)).strip() if x not in (None, "") else ""


def clean_product_name(name):
    """'OO 스** 티셔츠 4종세트' → '티셔츠 4종세트' (가림 표시가 든 낱말을 뺀다)."""
    words = [w for w in nfc(name).split() if not MASK_TOKEN.search(w)]
    return " ".join(words)


def aihub_rating(score):
    try:
        v = float(score)
    except (TypeError, ValueError):
        return None
    return max(1, min(5, int(v / 20 + 0.5))) if v > 5 else max(1, min(5, int(round(v))))


def aihub(src_dir, cutoff, stats):
    files = sorted(glob.glob(os.path.join(src_dir, "**", "*.json"), recursive=True))
    if not files:
        print(f"  ⚠ AI Hub JSON 파일이 없습니다: {src_dir}")
        return []
    rows = []
    for path in files:
        rel = nfc(os.path.relpath(path, src_dir))  # macOS 한글 파일명은 NFD라 NFC로
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            stats["aihub_bad_file"] += 1
            print(f"  ⚠ 읽지 못한 파일: {rel} ({type(e).__name__})")
            continue
        if isinstance(data, dict):
            data = data.get("data") or data.get("documents") or [data]
        fid = hashlib.sha1(rel.encode()).hexdigest()[:8]
        for i, r in enumerate(data):
            text = nfc(r.get("RawText"))
            if not text:
                stats["aihub_no_text"] += 1
                continue
            d = re.sub(r"\D", "", str(r.get("RDate") or ""))
            date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) >= 8 else None
            if date and cutoff and date >= cutoff:
                stats["aihub_after_cutoff"] += 1
                continue
            domain, main, product = nfc(r.get("Domain")), nfc(r.get("MainCategory")), nfc(r.get("ProductName"))
            category = " > ".join(x for x in (domain, main) if x) or None
            pid = "ah-" + hashlib.sha1(f"{category}|{product or rel + '#' + str(i)}".encode()).hexdigest()[:12]
            rows.append({"text": text, "product_id": pid, "platform": "aihub", "date": date,
                         "rating": aihub_rating(r.get("ReviewScore")), "category": category,
                         "product_name": clean_product_name(product) or None, "source": nfc(r.get("Source")) or None,
                         "source_id": f"ah-{fid}-{r.get('Index', i)}", "file": rel})
            stats["aihub_ok"] += 1
    print(f"  · AI Hub: 파일 {len(files):,}개 → 리뷰 {len(rows):,}건"
          + (f" (기준일 {cutoff} 이후 {stats['aihub_after_cutoff']:,}건 제외)" if stats["aihub_after_cutoff"] else ""))
    return rows


def naver(src):
    rows = []
    with open(src, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rid = str(r["review_id"])
            rows.append({"text": r["content"], "product_id": rid if rid.startswith("nv-") else f"nv-{rid}", "platform": "naver",
                         "date": "2020-07-31", "date_estimated": True, "rating": r.get("star"), "source_id": r["review_id"]})
    return rows


def coupang(src):
    d = json.load(open(src, encoding="utf-8"))
    rows, dropped = [], 0
    for pid, prod in d.get("products", {}).items():
        for r in prod.get("reviews", []):
            if r.get("period") != "pre_chatgpt":
                dropped += 1
                continue
            text = CASH_EVENT.sub("", r.get("content") or "").strip()
            if not text:
                continue
            rows.append({"text": text, "product_id": f"cp-{pid}", "platform": "coupang", "date": r.get("created_at"),
                         "rating": r.get("star"), "category": r.get("category") or prod.get("category"),
                         "product_name": r.get("product_name") or prod.get("name"), "source_id": r["review_id"]})
    if dropped:
        print(f"  (쿠팡 2022-11-30 이후 리뷰 {dropped:,}건은 사람 라벨로 쓰지 않아 제외)")
    return rows


def summarize(rows):
    print(f"\n[합친 사람 리뷰] 총 {len(rows):,}건")
    for label, key in (("출처", "platform"), ("별점", "rating")):
        print(f"  {label}: {dict(Counter(r.get(key) for r in rows).most_common())}")
    cats = Counter(r.get("category") for r in rows if r.get("category"))
    if cats:
        print(f"  카테고리 {len(cats)}개: {dict(cats.most_common(15))}" + (" …" if len(cats) > 15 else ""))
    years = Counter((r.get("date") or "?")[:4] for r in rows if not r.get("date_estimated"))
    if years:
        print(f"  연도(추정 날짜 제외): {dict(sorted(years.items()))}")
    srcs = Counter(r.get("source") for r in rows if r.get("source"))
    if len(srcs) > 1:
        print(f"  AI Hub Source: {dict(srcs)}  ← 리뷰가 아닌 출처가 섞였다면 알려 주세요")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aihub", default=os.path.join(MODEL_DATA, "AI_hub", "pre"), help="AI Hub 압축 푼 폴더")
    ap.add_argument("--naver", default=os.path.join(MODEL_DATA, "naver", "naver_shopping.jsonl"))
    ap.add_argument("--coupang", default=os.path.join(MODEL_DATA, "coupang", "coupang_training.json"))
    ap.add_argument("--no-coupang", action="store_true", help="쿠팡 수집분은 넣지 않음")
    ap.add_argument("--cutoff", default="2022-12-01", help="이 날짜 이후 리뷰는 사람 라벨로 쓰지 않음 (ChatGPT 공개 2022-11-30)")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "raw", "human_reviews.jsonl"))
    args = ap.parse_args()
    stats = Counter()
    rows = []
    if os.path.isdir(args.aihub):
        rows += aihub(args.aihub, args.cutoff, stats)
    else:
        print(f"  · AI Hub 폴더 없음: {args.aihub}")
    if os.path.exists(args.naver):
        nv = naver(args.naver)
        print(f"  · 네이버: {len(nv):,}건")
        rows += nv
    else:
        print(f"  ⚠ 네이버 파일 없음: {args.naver}  (저장소 루트에서 python collect_training_data.py naver)")
    if not args.no_coupang and os.path.exists(args.coupang):
        cp = coupang(args.coupang)
        print(f"  · 쿠팡: {len(cp):,}건")
        rows += cp
    if not rows:
        raise SystemExit("사람 리뷰를 하나도 찾지 못했습니다. 위 경로를 확인하세요.")
    write(args.out, rows)
    summarize(rows)


if __name__ == "__main__":
    main()
