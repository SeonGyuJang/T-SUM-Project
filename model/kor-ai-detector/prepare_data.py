"""LGC 댓글 + 리뷰(사람/AI) 데이터를 통합 JSONL로 정리하고 학습/검증/테스트로 나눕니다.

출력 레코드 형식 (한 줄에 하나):
  {"id", "text", "label"(0=사람, 1=AI), "domain"("comment"|"review"),
   "platform", "generator", "group", + 원본의 rating/category/prompt_type/date (있으면)}

사용 예:
  python prepare_data.py \
    --lgc ./XDAC_obs/LGC_data/LGC_data_v1.0.json \
    --lgc-text-field text --lgc-label-field label --lgc-ai-values 1 \
    --human-reviews data/raw/naver_human.csv \
    --ai-reviews data/raw/ai_chatgpt.jsonl data/raw/ai_claude.jsonl data/raw/ai_gemini.jsonl \
    --human-before 2022-12-01 \
    --holdout-generators gemini \
    --out data/processed
"""
import argparse
import csv
import json
import os
import random
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import auroc  # noqa: E402

ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")

# AI 출력에만 붙는 메타 문구(모델이 덧붙인 안내문). 실제 조작자는 지우고 올리므로 학습 데이터에서도 지웁니다.
AI_PREAMBLE = re.compile(
    r"^\s*(물론(이죠|입니다)?|네[,!.]|좋아요[,!.]|다음은|아래는|요청하신|Here is|Here's|Sure)[^\n]*(:|입니다\.?|드릴게요\.?)\s*\n+",
    re.IGNORECASE,
)
AI_LABEL_PREFIX = re.compile(r"^\s*(\*\*)?(리뷰|후기|상품\s*리뷰|Review)\s*(\d+)?\s*[:：](\*\*)?\s*", re.IGNORECASE)
AI_REFUSAL = re.compile(r"(AI 언어 ?모델|인공지능 ?모델로서|죄송하지만[, ]+.*(작성|도와)|as an AI)", re.IGNORECASE)


def read_any(path):
    if path.endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in ("data", "items", "records"):
                if isinstance(data.get(k), list):
                    return data[k]
            raise ValueError(f"{path}: JSON 최상위가 dict인데 data/items/records 리스트가 없습니다.")
        return data
    if path.endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    raise ValueError(f"지원하지 않는 형식: {path} (.json/.jsonl/.csv)")


def normalize(text):
    """사람/AI 공통 정규화. 줄바꿈·연속 공백은 유의미한 신호라서 보존합니다."""
    text = unicodedata.normalize("NFC", str(text))
    text = ZERO_WIDTH.sub("", text)
    return text.strip()


def clean_ai(text):
    """AI 생성물 전용 후처리. (정리된 텍스트, 버려야 하면 None)"""
    if AI_REFUSAL.search(text):
        return None
    text = AI_PREAMBLE.sub("", text)
    text = AI_LABEL_PREFIX.sub("", text)
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'“”":
        text = text[1:-1].strip()
    if text.startswith("“") and text.endswith("”"):
        text = text[1:-1].strip()
    return text


EXTRA_FIELDS = ("rating", "category", "prompt_type", "date", "model_version")


def build_review_rows(paths, label, args, stats):
    rows = []
    for path in paths:
        src = os.path.splitext(os.path.basename(path))[0]
        for i, r in enumerate(read_any(path)):
            text = r.get(args.review_text_field)
            if text is None:
                raise KeyError(f"{path}: '{args.review_text_field}' 컬럼이 없습니다. 가진 컬럼: {list(r.keys())}")
            text = normalize(text)
            if label == 1:
                cleaned = clean_ai(text)
                if cleaned is None:
                    stats["ai_refusal_dropped"] += 1
                    continue
                if cleaned != text:
                    stats["ai_meta_cleaned"] += 1
                text = cleaned
            else:
                date = str(r.get("date") or "")
                if args.human_before and date and date[:10] >= args.human_before:
                    stats["human_after_cutoff_dropped"] += 1
                    continue
                if args.human_before and not date:
                    stats["human_no_date"] += 1
            platform = (r.get("platform") or "").strip().lower() or ("unknown" if label == 0 else "generated")
            generator = (r.get(args.ai_generator_field) or "").strip().lower() if label == 1 else "human"
            if label == 1 and not generator:
                raise KeyError(f"{path}: AI 리뷰에 '{args.ai_generator_field}' 값이 비어 있습니다 (행 {i}).")
            row = {
                "id": f"{src}-{i}",
                "text": text,
                "label": label,
                "domain": "review",
                "platform": platform,
                "generator": generator,
                "group": str(r.get(args.review_group_field) or f"{src}-{i}"),
            }
            for k in EXTRA_FIELDS:
                if r.get(k) not in (None, ""):
                    row[k] = r[k]
            rows.append(row)
    return rows


def build_lgc_rows(args, stats):
    ai_values = {v.strip().lower() for v in args.lgc_ai_values.split(",")}
    rows = []
    seen_labels = Counter()
    for i, r in enumerate(read_any(args.lgc)):
        if args.lgc_text_field not in r or args.lgc_label_field not in r:
            raise KeyError(
                f"LGC 레코드에 '{args.lgc_text_field}' 또는 '{args.lgc_label_field}' 필드가 없습니다. "
                f"첫 레코드의 필드: {list(r.keys())} → --lgc-text-field / --lgc-label-field 로 지정하세요."
            )
        raw_label = str(r[args.lgc_label_field]).strip().lower()
        seen_labels[raw_label] += 1
        label = 1 if raw_label in ai_values else 0
        gen = "human"
        if label == 1:
            gen = str(r.get(args.lgc_generator_field) or "lgc-llm").strip().lower() if args.lgc_generator_field else "lgc-llm"
        rows.append({
            "id": f"lgc-{i}",
            "text": normalize(r[args.lgc_text_field]),
            "label": label,
            "domain": "comment",
            "platform": "naver-news",
            "generator": gen,
            "group": str(r.get(args.lgc_group_field) or f"lgc-{i}") if args.lgc_group_field else f"lgc-{i}",
        })
    stats["lgc_raw_label_values"] = dict(seen_labels.most_common(20))
    return rows


def filter_and_dedupe(rows, args, stats, tag):
    out, by_text = [], defaultdict(set)
    for r in rows:
        by_text[r["text"]].add(r["label"])
    seen = set()
    for r in rows:
        t = r["text"]
        if not (args.min_chars <= len(t) <= args.max_chars):
            stats[f"{tag}_length_filtered"] += 1
            continue
        if len(by_text[t]) > 1:
            stats[f"{tag}_conflicting_label_dropped"] += 1
            continue
        if t in seen:
            stats[f"{tag}_duplicate_dropped"] += 1
            continue
        seen.add(t)
        out.append(r)
    return out


def group_split(rows, ratios, rng):
    """같은 group(상품/기사)이 여러 split에 걸치지 않게 나눕니다."""
    groups = sorted({r["group"] for r in rows})
    rng.shuffle(groups)
    n = len(groups)
    cut1 = int(n * ratios[0])
    cut2 = cut1 + int(n * ratios[1])
    assign = {g: ("train" if i < cut1 else "val" if i < cut2 else "test") for i, g in enumerate(groups)}
    splits = {"train": [], "val": [], "test": []}
    for r in rows:
        splits[assign[r["group"]]].append(r)
    return splits


def write_jsonl(path, rows, rng=None):
    if rng:
        rows = rows[:]
        rng.shuffle(rows)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def summarize(name, rows):
    c = Counter(r["label"] for r in rows)
    gens = Counter(r["generator"] for r in rows if r["label"] == 1)
    plats = Counter(r["platform"] for r in rows)
    lens = {lab: [len(r["text"]) for r in rows if r["label"] == lab] for lab in (0, 1)}
    med = {lab: (statistics.median(v) if v else None) for lab, v in lens.items()}
    print(f"  {name:<28} 총 {len(rows):>8,} | 사람 {c[0]:>8,} | AI {c[1]:>8,} | "
          f"길이 중앙값 사람 {med[0]} / AI {med[1]}")
    if gens:
        print(f"  {'':<28} 생성 모델: {dict(gens)}")
    if len(plats) > 1 or name.startswith("stage2"):
        print(f"  {'':<28} 플랫폼: {dict(plats)}")
    return {"n": len(rows), "human": c[0], "ai": c[1], "generators": dict(gens),
            "platforms": dict(plats), "median_len": med}


def length_shortcut_check(rows):
    """글자 수 하나만으로 사람/AI가 갈리면 데이터에 지름길이 있다는 신호입니다."""
    labels = [r["label"] for r in rows]
    a = auroc(labels, [len(r["text"]) for r in rows])
    if a is None:
        return None
    strength = abs(a - 0.5) * 2  # 0 = 정보 없음, 1 = 길이만으로 완벽 분리
    print(f"\n[지름길 점검] stage2_train에서 '글자 수'만으로 낸 AUROC = {a:.3f}")
    if strength > 0.4:
        print("  ⚠ 길이 분포 차이가 큽니다. AI 리뷰 생성 시 길이 조건을 사람 리뷰 분포에 맞추세요.")
    else:
        print("  OK: 길이만으로는 잘 갈리지 않습니다.")
    return a


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lgc", help="LGC 댓글 데이터 (.json/.jsonl/.csv)")
    ap.add_argument("--lgc-text-field", default="text")
    ap.add_argument("--lgc-label-field", default="label")
    ap.add_argument("--lgc-ai-values", default="1,ai,llm,machine,generated",
                    help="라벨 필드에서 AI를 뜻하는 값들(쉼표 구분, 대소문자 무시). 나머지는 사람으로 처리")
    ap.add_argument("--lgc-generator-field", default=None, help="LGC에서 생성 모델명이 든 필드 (있으면)")
    ap.add_argument("--lgc-group-field", default=None, help="LGC에서 기사 ID 등 묶음 기준 필드 (있으면)")
    ap.add_argument("--human-reviews", nargs="*", default=[], help="사람 리뷰 파일들 (공통 형식)")
    ap.add_argument("--ai-reviews", nargs="*", default=[], help="AI 생성 리뷰 파일들 (공통 형식 + generator)")
    ap.add_argument("--review-text-field", default="text")
    ap.add_argument("--review-group-field", default="product_id")
    ap.add_argument("--ai-generator-field", default="generator")
    ap.add_argument("--human-before", default=None,
                    help="YYYY-MM-DD. 이 날짜 이전에 작성된 사람 리뷰만 사용 (date 컬럼 필요)")
    ap.add_argument("--holdout-generators", default="",
                    help="쉼표 구분. 이 모델이 만든 AI 리뷰는 학습에서 빼고 '처음 보는 모델' 테스트에만 사용")
    ap.add_argument("--holdout-all-groups", action="store_true",
                    help="holdout 모델 리뷰를 학습 상품 것까지 모두 테스트에 사용 (기본: 테스트 상품 것만 사용해 누출 차단)")
    ap.add_argument("--test-only-platforms", default="",
                    help="쉼표 구분. 이 플랫폼 데이터는 학습에서 빼고 '플랫폼 교차' 테스트에만 사용 (예: coupang)")
    ap.add_argument("--min-chars", type=int, default=5)
    ap.add_argument("--max-chars", type=int, default=2000)
    ap.add_argument("--stage1-ratios", default="0.9,0.05,0.05")
    ap.add_argument("--stage2-ratios", default="0.8,0.1,0.1")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/processed")
    args = ap.parse_args()

    if not args.lgc and not (args.human_reviews or args.ai_reviews):
        ap.error("--lgc 또는 --human-reviews/--ai-reviews 중 하나는 필요합니다.")
    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(args.seed)
    stats = Counter()
    summary = {}
    print("=" * 100)

    # ---------- Stage 1: LGC 댓글 ----------
    if args.lgc:
        lgc = filter_and_dedupe(build_lgc_rows(args, stats), args, stats, "lgc")
        ratios = [float(x) for x in args.stage1_ratios.split(",")]
        sp = group_split(lgc, ratios, rng)
        print("[Stage 1] LGC 댓글")
        for k in ("train", "val", "test"):
            write_jsonl(os.path.join(args.out, f"stage1_{k}.jsonl"), sp[k], rng)
            summary[f"stage1_{k}"] = summarize(f"stage1_{k}", sp[k])

    # ---------- Stage 2: 리뷰 ----------
    if args.human_reviews or args.ai_reviews:
        human = build_review_rows(args.human_reviews, 0, args, stats)
        ai = build_review_rows(args.ai_reviews, 1, args, stats)
        reviews = filter_and_dedupe(human + ai, args, stats, "review")
        holdout_gen = {g.strip().lower() for g in args.holdout_generators.split(",") if g.strip()}
        test_plat = {p.strip().lower() for p in args.test_only_platforms.split(",") if p.strip()}

        xplat = [r for r in reviews if r["platform"] in test_plat]
        rest = [r for r in reviews if r["platform"] not in test_plat]
        unseen_ai = [r for r in rest if r["label"] == 1 and r["generator"] in holdout_gen]
        main_rows = [r for r in rest if not (r["label"] == 1 and r["generator"] in holdout_gen)]

        ratios = [float(x) for x in args.stage2_ratios.split(",")]
        sp = group_split(main_rows, ratios, rng)
        # 학습/검증 split에 속한 상품의 holdout AI 리뷰는 내용 누출을 막기 위해 제외
        trainval_groups = {x["group"] for x in sp["train"] + sp["val"]}
        if args.holdout_all_groups:
            unseen_ai_test = unseen_ai
        else:
            unseen_ai_test = [r for r in unseen_ai if r["group"] not in trainval_groups]
        stats["holdout_ai_dropped_overlap_with_train_groups"] = len(unseen_ai) - len(unseen_ai_test)

        print("\n[Stage 2] 리뷰")
        outputs = {
            "stage2_train": sp["train"],
            "stage2_val": sp["val"],
            "stage2_test": sp["test"],
        }
        if holdout_gen:
            outputs["stage2_test_unseen_gen"] = [r for r in sp["test"] if r["label"] == 0] + unseen_ai_test
        if test_plat:
            outputs["stage2_test_xplatform"] = xplat
        for name, rows in outputs.items():
            write_jsonl(os.path.join(args.out, f"{name}.jsonl"), rows, rng)
            summary[name] = summarize(name, rows)
        for name in ("stage2_train", "stage2_val"):
            if outputs[name] and len({r["label"] for r in outputs[name]}) < 2:
                print(f"  ⚠ {name}에 한쪽 라벨만 있습니다. 사람/AI 리뷰가 모두 있어야 2단계 학습이 됩니다.")
        if outputs["stage2_train"]:
            summary["length_only_auroc"] = length_shortcut_check(outputs["stage2_train"])

    print("\n[정제 통계]")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    summary["cleaning_stats"] = dict(stats)
    with open(os.path.join(args.out, "data_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n완료 → {args.out}/ (요약: data_summary.json)")


if __name__ == "__main__":
    main()
