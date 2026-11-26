"""한국어 인코더 모델을 사람/AI 이진 분류기로 파인튜닝합니다 (1단계·2단계 공용).

1단계 (LGC 댓글):
  python train.py --model beomi/KcELECTRA-base-v2022 \
    --train data/processed/stage1_train.jsonl --val data/processed/stage1_val.jsonl \
    --out models/stage1 --epochs 1 --lr 3e-5

2단계 (리뷰, 1단계 결과에서 이어서 학습 + LGC 일부를 섞어 망각 방지):
  python train.py --model models/stage1 \
    --train data/processed/stage2_train.jsonl --val data/processed/stage2_val.jsonl \
    --replay data/processed/stage1_train.jsonl --replay-ratio 0.15 \
    --out models/stage2 --epochs 3 --lr 2e-5
"""
import _winconsole  # noqa: F401  윈도우(cp949) 출력에서 기호 때문에 멈추지 않게
import argparse
import json
import math
import os
import random
import sys
from collections import Counter

import numpy as np
import torch
from datasets import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
    set_seed,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import auroc, binary_report, threshold_at_fpr  # noqa: E402

ID2LABEL = {0: "human", 1: "ai"}
LABEL2ID = {"human": 0, "ai": 1}


def load_jsonl(path, limit=None, rng=None):
    """limit이 있으면 파일을 한 번 읽으면서 무작위 limit개만 남깁니다(저수지 표집).
    LGC 학습셋(약 200만 건)을 replay용으로 일부만 쓸 때 전체를 메모리에 올리지 않기 위함."""
    rng = rng or random.Random()
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(x for x in f if x.strip()):
            if not limit or len(rows) < limit:
                rows.append(line)
            else:
                j = rng.randint(0, n)
                if j < limit:
                    rows[j] = line
    out = []
    for line in rows:
        r = json.loads(line)
        out.append({"text": r["text"], "label": int(r["label"])})
    return out


def data_preprocess_info(train_path):
    """prepare_data.py가 남긴 전처리 설정(줄바꿈 처리 등). 추론 때 똑같이 적용해야 합니다."""
    p = os.path.join(os.path.dirname(os.path.abspath(train_path)), "data_summary.json")
    if not os.path.exists(p):
        return {"newlines": "keep"}
    with open(p, encoding="utf-8") as f:
        stats = json.load(f).get("cleaning_stats", {})
    return {"newlines": stats.get("newlines_mode", "keep")}


def softmax_p1(logits):
    logits = logits - logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    return (e[:, 1] / e.sum(axis=1)).tolist()


def make_compute_metrics(target_fpr):
    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        p = softmax_p1(np.asarray(logits))
        labels = np.asarray(labels).tolist()
        out = {"auroc": auroc(labels, p) or 0.0}
        human = [s for s, y in zip(p, labels) if y == 0]
        if human and any(y == 1 for y in labels):
            thr = threshold_at_fpr(human, target_fpr)
            rep = binary_report(labels, p, thr)
            out[f"tpr_at_fpr{target_fpr:g}"] = rep["tpr"] or 0.0
        out["acc@0.5"] = float(np.mean([(s > 0.5) == (y == 1) for s, y in zip(p, labels)]))
        return out
    return compute_metrics


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="HF 모델 ID 또는 1단계 결과 폴더")
    ap.add_argument("--train", required=True)
    ap.add_argument("--val", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--replay", default=None, help="섞어 넣을 이전 단계 학습 데이터 (예: stage1_train.jsonl)")
    ap.add_argument("--replay-ratio", type=float, default=0.15, help="최종 학습셋 중 replay 데이터 비율")
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--grad-accum", type=int, default=1)
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--warmup-ratio", type=float, default=0.06)
    ap.add_argument("--weight-decay", type=float, default=0.01)
    ap.add_argument("--eval-steps", type=int, default=None, help="지정하면 N step마다 검증 (대용량 1단계용)")
    ap.add_argument("--max-train-samples", type=int, default=None, help="빠른 점검용 샘플 수 제한")
    ap.add_argument("--max-val-samples", type=int, default=20000)
    ap.add_argument("--target-fpr", type=float, default=0.01)
    ap.add_argument("--early-stopping", type=int, default=2, help="검증 AUROC가 N번 연속 안 오르면 중단 (0=끔)")
    ap.add_argument("--fp16", action="store_true")
    ap.add_argument("--bf16", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    set_seed(args.seed)
    rng = random.Random(args.seed)

    train_rows = load_jsonl(args.train, args.max_train_samples, rng)
    if args.replay:
        if not 0 < args.replay_ratio < 1:
            ap.error("--replay-ratio 는 0과 1 사이여야 합니다.")
        n_replay = int(len(train_rows) * args.replay_ratio / (1 - args.replay_ratio))
        replay_rows = load_jsonl(args.replay, n_replay, rng)
        print(f"[replay] {args.replay} 에서 {len(replay_rows):,}개를 섞습니다.")
        train_rows += replay_rows
    rng.shuffle(train_rows)
    val_rows = load_jsonl(args.val, args.max_val_samples, rng)

    for name, rows in (("train", train_rows), ("val", val_rows)):
        c = Counter(r["label"] for r in rows)
        print(f"[{name}] 총 {len(rows):,} | 사람 {c[0]:,} | AI {c[1]:,}")
        if len(c) < 2:
            sys.exit(f"{name} 데이터에 한쪽 라벨만 있습니다. 사람/AI가 모두 필요합니다.")

    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=2, id2label=ID2LABEL, label2id=LABEL2ID
    )

    def tokenize(batch):
        return tok(batch["text"], truncation=True, max_length=args.max_len)

    train_ds = Dataset.from_list(train_rows).map(tokenize, batched=True, remove_columns=["text"])
    val_ds = Dataset.from_list(val_rows).map(tokenize, batched=True, remove_columns=["text"])

    # transformers 5.x에는 warmup_ratio가 없다 → 정수 warmup_steps로 계산해 넘긴다(4.x·5.x 모두 동작)
    steps_per_epoch = math.ceil(len(train_rows) / (args.batch_size * args.grad_accum))
    warmup_steps = int(math.ceil(steps_per_epoch * args.epochs * args.warmup_ratio))
    strategy = "steps" if args.eval_steps else "epoch"
    step_kwargs = {"eval_steps": args.eval_steps, "save_steps": args.eval_steps} if args.eval_steps else {}
    targs = TrainingArguments(
        **step_kwargs,
        output_dir=os.path.join(args.out, "checkpoints"),
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        gradient_accumulation_steps=args.grad_accum,
        warmup_steps=warmup_steps,
        weight_decay=args.weight_decay,
        eval_strategy=strategy,
        save_strategy=strategy,
        logging_steps=50,
        load_best_model_at_end=True,
        metric_for_best_model="auroc",
        greater_is_better=True,
        save_total_limit=2,
        fp16=args.fp16 and torch.cuda.is_available(),
        bf16=args.bf16 and torch.cuda.is_available(),  # bf16 학습은 CUDA GPU에서만
        report_to="none",
        seed=args.seed,
    )
    callbacks = [EarlyStoppingCallback(args.early_stopping)] if args.early_stopping > 0 else []
    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=DataCollatorWithPadding(tok),
        compute_metrics=make_compute_metrics(args.target_fpr),
        callbacks=callbacks,
    )
    trainer.train()
    metrics = trainer.evaluate()
    print("[best val]", json.dumps(metrics, ensure_ascii=False, indent=2))

    trainer.save_model(args.out)
    tok.save_pretrained(args.out)
    with open(os.path.join(args.out, "train_config.json"), "w", encoding="utf-8") as f:
        json.dump({"args": vars(args), "val_metrics": metrics, "preprocess": data_preprocess_info(args.train),
                   "max_len": args.max_len, "n_train": len(train_rows), "n_val": len(val_rows)},
                  f, ensure_ascii=False, indent=2)
    print(f"저장 완료 → {args.out}")


if __name__ == "__main__":
    main()
