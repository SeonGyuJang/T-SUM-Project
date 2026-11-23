"""저장소에서 이미 모은 사람 리뷰를 README 4.3 공통 형식(.jsonl)으로 바꿉니다.

  네이버 쇼핑  model/data/raw/naver/naver_shopping.jsonl      (python collect_training_data.py naver)
  쿠팡         model/data/raw/coupang/coupang_training.json   (python collect_training_data.py category ...)

  python convert_sources.py              # → data/raw/naver_human.jsonl, data/raw/coupang_human.jsonl

공통 형식 필드: text, product_id, platform, date, rating, category, (쿠팡) product_name, source_id
- 네이버 말뭉치에는 상품 정보가 없어 리뷰마다 product_id = "nv-<리뷰ID>"(리뷰 1건 = 그룹 1개)로 둡니다.
  날짜도 없어서 수집 시점(2020년 6~7월)의 상한인 2020-07-31을 넣습니다(--human-before 필터 통과용, date_estimated=true).
- 쿠팡은 2022-11-30 이전(period=pre_chatgpt) 리뷰만 내보냅니다. 플랫폼이 붙이는 '쿠팡캐시 리뷰 이벤트' 고지 문구는 본문에서 뗍니다(README 4.4-4).
"""
import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_DATA = os.path.join(os.path.dirname(ROOT), "data", "raw")
CASH_EVENT = re.compile(r"본\s*(?:리뷰|후기)[^.\n]{0,80}?쿠팡\s*캐시[^.\n]{0,80}?(?:작성|참여)[^.\n]{0,30}?(?:것입니다|합니다|했습니다)\.?\s*")


def write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  → {path}: {len(rows):,}건")


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--naver", default=os.path.join(MODEL_DATA, "naver", "naver_shopping.jsonl"))
    ap.add_argument("--coupang", default=os.path.join(MODEL_DATA, "coupang", "coupang_training.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "raw"))
    args = ap.parse_args()
    if os.path.exists(args.naver):
        write(os.path.join(args.out, "naver_human.jsonl"), naver(args.naver))
    else:
        print(f"  ⚠ 네이버 파일 없음: {args.naver}  (저장소 루트에서 python collect_training_data.py naver)")
    if os.path.exists(args.coupang):
        write(os.path.join(args.out, "coupang_human.jsonl"), coupang(args.coupang))
    else:
        print(f"  · 쿠팡 파일 없음(수집 중이면 정상): {args.coupang}")


if __name__ == "__main__":
    main()
