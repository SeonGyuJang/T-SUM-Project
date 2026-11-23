"""realstar_model 명령 (model/ 폴더에서 `python -m realstar_model <명령>`).

  data-stats       사람 데이터(네이버·쿠팡) 양과 분할 확인
  generate         Claude로 AI 리뷰 생성 → model/data/generated/ai_<모델>.jsonl
  build-dataset    사람+AI → model/data/processed/dataset.jsonl (1:1, 같은 분할·별점·길이)
  train-baseline   B0(지름길 점검) + B1(TF-IDF LR) 학습 → artifacts/det-ko-review-v0.1
  train-encoder    한국어 인코더 학습(GPU 권장) → artifacts/det-ko-review-v0.2
  predict          아티팩트로 문장 하나 판별해 보기
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from realstar_model.paths import ARTIFACTS, GENERATED, PROCESSED


def _print_metrics(res: dict) -> None:  # type: ignore[type-arg]
    m = res["metrics"]
    print(f"\n아티팩트: {res['artifact']}  (실험 기록 {res['experiment']} → model/reports/)")
    print("        구간     n      AUROC   TPR@1%FPR  TPR@2%FPR  ECE")
    for split in ("val", "test", "test_t_gen"):
        if split not in m:
            continue
        for b in ("all", "S", "M", "L"):
            x = m[split].get(b)
            if x and "auroc" in x:
                print(f"  {split:<10} {b:<4} {x['n']:>6,}  {x['auroc']:.4f}  {x['tpr@1%fpr']:.4f}     {x['tpr@2%fpr']:.4f}     {x['ece']:.4f}")
    if "b0_test" in m and "auroc" in m["b0_test"]["all"]:
        a = m["b0_test"]["all"]["auroc"]
        print(f"\n  B0(길이·문장부호만) test AUROC {a:.4f}" + ("  ⚠ 높아요: 생성 데이터의 길이·형식이 사람 데이터와 달라 모델이 지름길을 배울 수 있어요" if a >= 0.8 else "  (낮을수록 좋음)"))
    t = res["thresholds"]["M"]
    print(f"  임계값(M 구간): AI ≥ {t['T_AI']} · 사람 ≤ {t['T_HUMAN']}  (그 사이는 판단 보류)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="realstar_model", description="리얼별점 AI 작성 리뷰 탐지 모델")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("data-stats", help="사람 데이터 확인")
    d.add_argument("--no-coupang", action="store_true")

    g = sub.add_parser("generate", help="Claude로 AI 리뷰 생성")
    g.add_argument("--n", type=int, default=1000, help="목표 생성 개수(분할 8:1:1, 이미 만든 만큼은 건너뜀)")
    g.add_argument("--model", default="claude-opus-5-5", help="생성 모델 (기본 claude-opus-5-5)")
    g.add_argument("--effort", default="low", choices=["low", "medium", "high"], help="생성 노력 수준 (짧은 리뷰라 low 권장)")
    g.add_argument("--concurrency", type=int, default=4, help="동시 요청 수")
    g.add_argument("--polish-ratio", type=float, default=0.2, help="사람 리뷰를 AI가 다듬는 샘플 비율(MODEL_DEV A3)")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--no-coupang", action="store_true", help="기준 리뷰로 네이버만 사용")
    g.add_argument("--dry-run", action="store_true", help="API 호출 없이 프롬프트 예시만 보기")
    g.add_argument("--backend", default="claude", choices=["claude", "fake"], help=argparse.SUPPRESS)
    g.add_argument("--out", default=str(GENERATED), help=argparse.SUPPRESS)

    b = sub.add_parser("build-dataset", help="사람+AI 학습 데이터셋 만들기")
    b.add_argument("--human-ratio", type=float, default=1.0, help="AI 1건당 사람 리뷰 수 (기본 1)")
    b.add_argument("--holdout-generator", default=None, help="이 생성 모델 샘플은 테스트(t_gen)에만 사용")
    b.add_argument("--no-coupang", action="store_true")
    b.add_argument("--gen-dir", default=str(GENERATED), help=argparse.SUPPRESS)
    b.add_argument("--out", default=str(PROCESSED), help=argparse.SUPPRESS)

    t = sub.add_parser("train-baseline", help="B0·B1 베이스라인 학습 (CPU, 수 분)")
    t.add_argument("--version", default="det-ko-review-v0.1")
    t.add_argument("--C", type=float, default=4.0)
    t.add_argument("--dataset", default=str(PROCESSED / "dataset.jsonl"), help=argparse.SUPPRESS)
    t.add_argument("--art-dir", default="", help=argparse.SUPPRESS)

    e = sub.add_parser("train-encoder", help="한국어 인코더 학습 (pip install -e '.[encoder]', GPU 권장)")
    e.add_argument("--version", default="det-ko-review-v0.2")
    e.add_argument("--encoder", default="beomi/KcELECTRA-base-v2022")
    e.add_argument("--epochs", type=int, default=3)
    e.add_argument("--batch-size", type=int, default=32)
    e.add_argument("--lr", type=float, default=3e-5)
    e.add_argument("--max-length", type=int, default=256)
    e.add_argument("--limit", type=int, default=0, help="빠른 시험: train 샘플 수 제한")
    e.add_argument("--dataset", default=str(PROCESSED / "dataset.jsonl"), help=argparse.SUPPRESS)
    e.add_argument("--art-dir", default="", help=argparse.SUPPRESS)

    p = sub.add_parser("predict", help="아티팩트로 리뷰 판별해 보기")
    p.add_argument("text", nargs="+")
    p.add_argument("--artifact", default=str(ARTIFACTS / "det-ko-review-v0.1"))

    args = ap.parse_args(argv)
    if args.cmd == "data-stats":
        from realstar_model.data import load_human
        from realstar_model.preprocess import clean_review

        rows = load_human(include_coupang=not args.no_coupang)
        print(f"사람 리뷰 {len(rows):,}건 · 원천 {dict(Counter(r.source for r in rows))}")
        print(f"분할 {dict(Counter(r.split for r in rows))} · 별점 {dict(sorted(Counter(r.star for r in rows).items()))}")
        print(f"길이 구간 {dict(Counter(clean_review(r.title, r.text).len_bucket for r in rows))}")
        n_ai = sum(1 for f in Path(GENERATED).glob("ai_*.jsonl") for _ in f.open(encoding="utf-8"))
        print(f"생성된 AI 리뷰 {n_ai:,}건 ({GENERATED})")
        return 0
    if args.cmd == "generate":
        from realstar_model.data_gen.generate import run

        res = run(args.n, args.model, backend=args.backend, effort=args.effort, concurrency=args.concurrency,
                  polish_ratio=args.polish_ratio, seed=args.seed, out_dir=Path(args.out), dry_run=args.dry_run,
                  include_coupang=not args.no_coupang)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "build-dataset":
        from realstar_model.datasets.build import build

        man = build(human_ratio=args.human_ratio, holdout_generator=args.holdout_generator, include_coupang=not args.no_coupang,
                    gen_dir=Path(args.gen_dir), out_dir=Path(args.out))
        print(json.dumps(man, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "train-baseline":
        from realstar_model.models.baseline import train

        _print_metrics(train(version=args.version, dataset=Path(args.dataset), C=args.C, art_dir=Path(args.art_dir) if args.art_dir else None))
        return 0
    if args.cmd == "train-encoder":
        try:
            from realstar_model.models.encoder import train as train_enc
        except ImportError as ex:
            raise SystemExit(f"인코더 학습에는 torch·transformers가 필요해요: pip install -e '.[encoder]'  ({ex})") from ex
        _print_metrics(train_enc(version=args.version, encoder_id=args.encoder, epochs=args.epochs, batch_size=args.batch_size,
                                 lr=args.lr, max_length=args.max_length, limit=args.limit, dataset=Path(args.dataset),
                                 art_dir=Path(args.art_dir) if args.art_dir else None))
        return 0
    if args.cmd == "predict":
        from realstar_model.inference import Detector, ReviewInput

        det = Detector.load(args.artifact)
        for i, pr in enumerate(det.predict([ReviewInput(review_id=str(i), content=t) for i, t in enumerate(args.text)])):
            print(f"[{pr.label}] p_ai={pr.p_ai:.3f} ({pr.len_bucket}) · {args.text[i][:60]}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
