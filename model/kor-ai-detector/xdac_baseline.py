"""XDAC-D를 리뷰 테스트셋에 그대로 돌려 기준선 점수(id,score)를 만듭니다.

XDAC 엔진의 출력 구조는 공개 문서에 나와 있지 않으므로 2단계로 씁니다.

1) 출력 구조 확인:
   python xdac_baseline.py --inspect --data data/processed/stage2_val.jsonl

2) AI 확률이 든 필드 경로를 지정해 점수 저장 (예: 결과가 {"detection": {"ai_prob": 0.9}} 라면):
   python xdac_baseline.py --score-key detection.ai_prob \
     --data data/processed/stage2_val.jsonl data/processed/stage2_test.jsonl \
     --out reports/xdac_scores.csv
   # 값이 '사람일 확률'이면 --invert 를 붙이세요.

그다음 evaluate.py --scores-csv reports/xdac_scores.csv ... 로 같은 기준에서 비교합니다.
"""
import argparse
import csv
import json
import os
import sys


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def get_path(obj, dotted):
    for key in dotted.split("."):
        if isinstance(obj, (list, tuple)):
            obj = obj[int(key)]
        elif isinstance(obj, dict):
            obj = obj[key]
        else:
            obj = getattr(obj, key)
    return float(obj)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xdac-root", default="./XDAC_obs")
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--inspect", action="store_true", help="처음 3개 결과의 구조만 출력하고 종료")
    ap.add_argument("--score-key", help="결과 1건에서 P(AI) 값까지의 점(.) 경로")
    ap.add_argument("--invert", action="store_true", help="값이 사람일 확률이면 1-값으로 뒤집기")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--out", default="reports/xdac_scores.csv")
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(args.xdac_root)))
    from XDAC_obs.xdac_encrypted import AIUnifiedEngine, get_xdac_path  # noqa: E402

    root = get_xdac_path()
    engine = AIUnifiedEngine(
        detection_model_path=os.path.join(root, "XDAC-D"),
        attribution_model_path=os.path.join(root, "XDAC-A"),
        device=args.device,
        xai_enabled=False,  # 점수만 필요하므로 설명 기능은 끔 (속도)
    )

    if args.inspect:
        recs = load_jsonl(args.data[0])[:3]
        results = engine.predict([r["text"] for r in recs], batch_size=3)
        print("type(results) =", type(results))
        items = results if isinstance(results, (list, tuple)) else [results]
        for r, res in zip(recs, items):
            print("\n텍스트:", r["text"][:60])
            try:
                print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
            except TypeError:
                print(repr(res))
        print("\n위 구조에서 'AI일 확률' 값의 경로를 --score-key 로 넘기세요.")
        return

    if not args.score_key:
        ap.error("--score-key 가 필요합니다. 먼저 --inspect 로 구조를 확인하세요.")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    seen = set()
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "score"])
        for path in args.data:
            recs = [r for r in load_jsonl(path) if r["id"] not in seen]
            for i in range(0, len(recs), args.batch_size):
                chunk = recs[i:i + args.batch_size]
                results = engine.predict([r["text"] for r in chunk], batch_size=len(chunk))
                for r, res in zip(chunk, results):
                    s = get_path(res, args.score_key)
                    w.writerow([r["id"], f"{(1 - s) if args.invert else s:.6f}"])
                    seen.add(r["id"])
            print(f"{path}: {len(recs):,}건 완료")
    print(f"저장 → {args.out}")


if __name__ == "__main__":
    main()
