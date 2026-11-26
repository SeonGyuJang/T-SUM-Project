"""학습된 모델(또는 외부 점수 파일)을 테스트셋들에서 평가합니다.

임계값은 검증셋(--val)의 사람 리뷰로 정합니다: 사람 글 중 --target-fpr(기본 1%)만 AI로 오판되는 지점.
테스트셋 점수를 보고 임계값을 고르지 않으므로 결과를 그대로 실서비스 기대치로 볼 수 있습니다.

우리 모델 평가:
  python evaluate.py --model models/stage2 \
    --val data/processed/stage2_val.jsonl \
    --test data/processed/stage2_test.jsonl data/processed/stage2_test_unseen_gen.jsonl \
    --out reports/stage2

외부 점수(예: XDAC 기준선) 평가 — id,score 컬럼 CSV:
  python evaluate.py --scores-csv reports/xdac_scores.csv \
    --val data/processed/stage2_val.jsonl --test data/processed/stage2_test.jsonl --out reports/xdac
"""
import _winconsole  # noqa: F401  윈도우(cp949) 출력에서 기호 때문에 멈추지 않게
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import binary_report, breakdown, length_bucket  # noqa: E402
from predictor import MIN_CHARS, thresholds_from_val, verdict  # noqa: E402


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class ModelScorer:
    """학습된 모델 점수. 전처리·장치 선택(CUDA/MPS/CPU)은 predictor.Predictor와 같다."""

    def __init__(self, model_dir, max_len, batch_size, device=None):
        from predictor import Predictor
        self.p = Predictor(model_dir, max_len=max_len, batch_size=batch_size, device=device)

    def __call__(self, records):
        return self.p.score([r["text"] for r in records])


class CsvScorer:
    def __init__(self, path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            self.scores = {row["id"]: float(row["score"]) for row in csv.DictReader(f)}

    def __call__(self, records):
        missing = [r["id"] for r in records if r["id"] not in self.scores]
        if missing:
            sys.exit(f"점수 CSV에 없는 id가 {len(missing)}개 있습니다 (예: {missing[:3]}).")
        return [self.scores[r["id"]] for r in records]


def fmt(x):
    return "-" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))


def table(title, rows_by_group, cols):
    lines = [f"\n#### {title}", "", "| 그룹 | " + " | ".join(cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for g, rep in rows_by_group.items():
        lines.append(f"| {g} | " + " | ".join(fmt(rep[c]) for c in cols) + " |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--model", help="학습된 모델 폴더")
    src.add_argument("--scores-csv", help="외부 점수 CSV (id,score; score = P(AI))")
    ap.add_argument("--val", required=True, help="임계값을 정할 검증셋")
    ap.add_argument("--test", nargs="+", required=True)
    ap.add_argument("--target-fpr", type=float, default=0.01)
    ap.add_argument("--ai-miss", type=float, default=0.05,
                    help="검증셋 AI 리뷰 중 '사람'으로 내보내도 되는 비율. T_HUMAN을 정한다 (그 사이는 판단 보류)")
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--out", default="reports/eval")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    scorer = ModelScorer(args.model, args.max_len, args.batch_size) if args.model else CsvScorer(args.scores_csv)

    val = load_jsonl(args.val)
    val_scores = scorer(val)
    if not any(r["label"] == 0 for r in val):
        sys.exit("검증셋에 사람(label=0) 리뷰가 없어 임계값을 정할 수 없습니다.")
    thr, t_human = thresholds_from_val([r["label"] for r in val], val_scores, args.target_fpr, args.ai_miss)
    val_rep = binary_report([r["label"] for r in val], val_scores, thr)

    def verdicts(recs, scores):
        return [verdict(s, thr, t_human, len(r["text"])) for r, s in zip(recs, scores)]

    md = [f"# 평가 결과", "",
          f"- 점수 출처: `{args.model or args.scores_csv}`",
          f"- 임계값 T_AI (검증셋 사람 FPR {args.target_fpr:.0%} 기준): **{thr:.4f}**  → P(AI) > T_AI 이면 AI",
          f"- 임계값 T_HUMAN (검증셋 AI 중 {args.ai_miss:.0%}만 아래): **{t_human:.4f}**  → P(AI) ≤ T_HUMAN 이면 사람, 그 사이는 판단 보류"
          f" (글자 수 {MIN_CHARS}자 미만도 판단 보류)",
          f"- 검증셋: AUROC {fmt(val_rep['auroc'])}, TPR {fmt(val_rep['tpr'])}, FPR {fmt(val_rep['fpr'])}"]
    report = {"threshold": thr, "thresholds": {"T_AI": thr, "T_HUMAN": t_human}, "target_fpr": args.target_fpr,
              "ai_miss": args.ai_miss, "min_chars": MIN_CHARS, "val": val_rep, "tests": {}}
    main_cols = ["n", "n_human", "n_ai", "auroc", "tpr", "fpr", "precision", "f1"]

    for path in args.test:
        name = os.path.splitext(os.path.basename(path))[0]
        recs = load_jsonl(path)
        if not recs:
            print(f"  ⚠ {path}가 비어 있어 건너뜁니다.")
            continue
        scores = scorer(recs)
        overall = binary_report([r["label"] for r in recs], scores, thr)
        vs = verdicts(recs, scores)
        uncertain = vs.count("판단 보류") / len(vs)
        by_gen = breakdown(recs, scores, thr, lambda r: r.get("generator", "?"))
        by_plat = breakdown(recs, scores, thr, lambda r: r.get("platform", "?"))
        by_len = breakdown(recs, scores, thr, lambda r: length_bucket(r["text"]))
        report["tests"][name] = {"overall": overall, "uncertain_ratio": uncertain,
                                 "by_generator": by_gen, "by_platform": by_plat, "by_length": by_len}

        md.append(f"\n## {name}")
        md.append(f"\nAUROC **{fmt(overall['auroc'])}** · TPR@FPR{args.target_fpr:g} **{fmt(overall['tpr'])}** · "
                  f"실제 FPR {fmt(overall['fpr'])} · 판단 보류 비율 {uncertain:.1%}")
        md.append(table("생성 모델별 (human 행 = 사람 리뷰 오탐률은 fpr 열)", by_gen, main_cols))
        md.append(table("플랫폼별", by_plat, main_cols))
        md.append(table("길이 구간별", by_len, main_cols))

        with open(os.path.join(args.out, f"pred_{name}.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "label", "score", "pred", "verdict", "generator", "platform", "prompt_type", "text"])
            for r, s, v in zip(recs, scores, vs):
                w.writerow([r["id"], r["label"], f"{s:.6f}", int(s > thr), v,
                            r.get("generator", ""), r.get("platform", ""), r.get("prompt_type", ""), r["text"]])

    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\n저장 → {args.out}/report.md, report.json, pred_*.csv")


if __name__ == "__main__":
    main()
