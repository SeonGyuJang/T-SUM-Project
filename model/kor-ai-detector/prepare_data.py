"""LGC 댓글 + 리뷰(사람/AI) 데이터를 통합 JSONL로 정리하고 학습/검증/테스트로 나눕니다.

출력 레코드 형식 (한 줄에 하나):
  {"id", "text", "label"(0=사람, 1=AI), "domain"("comment"|"review"),
   "platform", "generator", "group", + 원본의 rating/category/prompt_type/date (있으면)}

사용 예 (XDAC 공개 LGC는 AI 댓글 2,000건뿐 → --lgc-all-ai, 학습엔 안 쓰고 추가 테스트셋 lgc_ai_test.jsonl로):
  python prepare_data.py \
    --lgc ../data/raw/XDAC_obs/LGC_data/LGC_data_v1.0.json \
    --lgc-all-ai --lgc-text-field generated_comment --lgc-generator-field llm_model_family \
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
from metrics import auroc, length_bucket  # noqa: E402

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


def inspect_lgc(path, n=3):
    """LGC 파일 구조를 보여 줍니다: 필드 이름, 예시 레코드, 값 종류가 적은 필드(라벨 후보)의 분포."""
    rows = read_any(path)
    keys = list(dict.fromkeys(k for r in rows[:5000] for k in r))  # 레코드마다 필드가 다를 수 있어 합쳐서 본다
    print(f"레코드 {len(rows):,}건 · 필드: {keys}")
    for r in rows[:n] + rows[-1:]:
        print(json.dumps({k: (str(v)[:80] if isinstance(v, str) else v) for k, v in r.items()}, ensure_ascii=False))
    print("\n[값 종류가 20개 이하인 필드 = 라벨·생성 모델 후보]")
    for k in keys:
        vals = Counter(str(r.get(k)) for r in rows[:200000])
        if len(vals) <= 20:
            print(f"  {k}: {dict(vals.most_common(20))}")
    if looks_ai_only_xdac(rows, keys):
        print(f"\n[판단] 이 파일은 사람/AI 라벨 필드가 없고 모든 레코드에 생성 모델(llm_model_family)이 적혀 있습니다.\n"
              f"  → AI가 만든 뉴스 댓글 {len(rows):,}건만 든 공개 샘플입니다(논문의 사람 130만 + AI 100만 전체가 아님).\n"
              f"  → 사람 댓글이 없어 1단계(댓글) 학습은 할 수 없습니다. 2단계 리뷰 학습을 바로 하고, 이 파일은 'AI 댓글을 잡는지' 보는 추가 테스트로 씁니다:\n"
              f"     --lgc {path} --lgc-all-ai --lgc-text-field generated_comment --lgc-generator-field llm_model_family")
        return
    print("\n→ 본문 필드는 --lgc-text-field, 사람/AI 구분 필드는 --lgc-label-field, AI를 뜻하는 값은 --lgc-ai-values,"
          " 생성 모델 필드는 --lgc-generator-field, 기사 ID 필드는 --lgc-group-field 로 지정하세요."
          " 사람/AI 구분 필드 없이 전부 AI 글이면 --lgc-all-ai.")


def looks_ai_only_xdac(rows, keys):
    """XDAC_obs 공개 LGC_data_v1.0.json: generated_comment + llm_model_family만 있고 사람 댓글이 없다."""
    return "generated_comment" in keys and "llm_model_family" in keys and all(r.get("llm_model_family") for r in rows)


def build_lgc_rows(args, stats):
    ai_values = {v.strip().lower() for v in args.lgc_ai_values.split(",")}
    rows = []
    seen_labels = Counter()
    for i, r in enumerate(read_any(args.lgc)):
        if args.lgc_text_field not in r or (not args.lgc_all_ai and args.lgc_label_field not in r):
            hint = ""
            if "generated_comment" in r and "llm_model_family" in r:
                hint = (" (XDAC 공개 파일이면: --lgc-all-ai --lgc-text-field generated_comment"
                        " --lgc-generator-field llm_model_family)")
            raise KeyError(
                f"LGC 레코드에 '{args.lgc_text_field}' 또는 '{args.lgc_label_field}' 필드가 없습니다. "
                f"첫 레코드의 필드: {list(r.keys())} → --lgc-text-field / --lgc-label-field 로 지정하세요.{hint}"
            )
        raw_label = "ai(--lgc-all-ai)" if args.lgc_all_ai else str(r[args.lgc_label_field]).strip().lower()
        seen_labels[raw_label] += 1
        label = 1 if args.lgc_all_ai or raw_label in ai_values else 0
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


def balance_humans(rows, ratio, rng, stats):
    """사람 리뷰를 AI 리뷰 수 × ratio 로 줄인다. 별점·길이 구간 분포를 AI 쪽에 맞춰 뽑는다(README 4.5 분포 맞추기).
    네이버처럼 사람 리뷰가 훨씬 많을 때 그대로 학습하면 모델이 '전부 사람'으로 기울기 때문."""
    human = [r for r in rows if r["label"] == 0]
    ai = [r for r in rows if r["label"] == 1]
    target = int(len(ai) * ratio)
    if not ai or ratio <= 0 or len(human) <= target:
        return rows

    # 칸 = 플랫폼·카테고리·별점·길이. AI가 쿠팡 건강식품 기준으로 만들어졌으면 사람도 쿠팡 건강식품에서 뽑아야
    # 모델이 "상품 주제·플랫폼"이 아니라 AI 말투로 구분한다. 칸에 사람 리뷰가 모자라면 카테고리를 빼고, 그다음 플랫폼을 빼고 채운다.
    def keys(r):
        rating, lb = str(r.get("rating") or ""), length_bucket(r["text"])
        plat = r.get("platform")  # AI 리뷰의 platform = 기준 리뷰의 플랫폼 (make_ai_tasks가 기록)
        return [(plat, str(r.get("category") or ""), rating, lb), (plat, rating, lb), (rating, lb)]

    pools = [defaultdict(list) for _ in range(3)]
    for h in human:
        for lvl, k in enumerate(keys(h)):
            pools[lvl][k].append(h)
    for p in pools:
        for v in p.values():
            rng.shuffle(v)
    picked, used = [], set()
    for lvl in range(3):  # 가장 세밀한 칸부터, 모자란 몫만 다음 단계로
        need = Counter()
        for a in ai:
            need[keys(a)[lvl]] += ratio
        for a_k, n in need.items():
            have = sum(1 for x in picked if keys(x)[lvl] == a_k) if lvl else 0
            want_n = int(round(n)) - have
            for h in pools[lvl].get(a_k, []):
                if want_n <= 0:
                    break
                if id(h) not in used:
                    picked.append(h)
                    used.add(id(h))
                    want_n -= 1
    rest = [h for h in human if id(h) not in used]
    rng.shuffle(rest)
    picked += rest[: max(0, target - len(picked))]  # 칸이 모자라면 나머지에서 채움
    stats["human_balanced_from"] = len(human)
    stats["human_balanced_to"] = len(picked)
    print(f"[균형 맞추기] 사람 리뷰 {len(human):,}건 → {len(picked):,}건 (AI {len(ai):,}건 × {ratio:g}, 플랫폼·카테고리·별점·길이 분포를 AI에 맞춤)")
    return picked + ai


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


EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
SHORTCUT_FEATURES = {
    "글자 수": lambda t: len(t),
    "줄바꿈 수": lambda t: t.count("\n"),
    "느낌표 비율": lambda t: t.count("!") / max(1, len(t)),
    "마침표 비율": lambda t: t.count(".") / max(1, len(t)),
    "이모지 수": lambda t: len(EMOJI.findall(t)),
    "ㅋ·ㅎ·ㅠ 수": lambda t: sum(t.count(c) for c in "ㅋㅎㅠㅜ"),
}


def length_shortcut_check(rows):
    """글자 수·줄바꿈·문장부호 같은 '겉모습' 하나만으로 사람/AI가 갈리면 데이터에 지름길이 있다는 신호입니다.
    반환값: 글자 수 AUROC(이전 버전과 호환), 전체 결과는 summary['shortcut_auroc']에 저장."""
    labels = [r["label"] for r in rows]
    print("\n[지름길 점검] stage2_train에서 특징 하나만으로 낸 AUROC (0.5 = 정보 없음, 0.7↑ 또는 0.3↓면 경고)")
    result = {}
    for name, fn in SHORTCUT_FEATURES.items():
        a = auroc(labels, [fn(r["text"]) for r in rows])
        if a is None:
            continue
        result[name] = round(a, 3)
        warn = abs(a - 0.5) * 2 > 0.4
        print(f"  {'⚠' if warn else '·'} {name:<10} {a:.3f}" + ("  ← 이 특징만으로 사람/AI가 갈립니다" if warn else ""))
    if any(abs(a - 0.5) * 2 > 0.4 for a in result.values()):
        print("  → 생성 조건(길이·형식)을 사람 리뷰 분포에 맞추거나 해당 표식을 정리한 뒤 학습하세요.")
    else:
        print("  OK: 겉모습 특징 하나만으로는 잘 갈리지 않습니다.")
    length_shortcut_check.result = result
    return result.get("글자 수")


def decide_newlines(mode, human, ai, stats):
    """사람·AI 리뷰의 줄바꿈 사용률이 크게 다르면(예: 네이버 말뭉치는 줄바꿈이 전부 지워져 있음)
    모델이 '줄바꿈 = AI' 지름길을 배웁니다. auto면 그런 경우에만 양쪽 줄바꿈을 공백으로 바꿉니다."""
    def rate(rows):
        return sum("\n" in r["text"] for r in rows) / len(rows) if rows else 0.0

    hr, ar = rate(human), rate(ai)
    stats["newline_rate_human"] = round(hr, 4)
    stats["newline_rate_ai"] = round(ar, 4)
    collapse = mode == "space" or (mode == "auto" and human and ai and abs(hr - ar) > 0.05 and min(hr, ar) < 0.02)
    if mode == "auto":
        print(f"[줄바꿈] 사람 리뷰 {hr:.1%} · AI 리뷰 {ar:.1%}에 줄바꿈이 있음 → "
              + ("한쪽에만 있어 지름길이 되므로 양쪽 모두 공백으로 바꿉니다 (--newlines keep 으로 끌 수 있음)" if collapse
                 else "비슷하므로 그대로 둡니다"))
    if collapse:
        for r in human + ai:
            r["text"] = re.sub(r"[ \t]*\n+[ \t]*", " ", r["text"]).strip()
    stats["newlines_mode"] = "space" if collapse else "keep"
    return collapse


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lgc", help="LGC 댓글 데이터 (.json/.jsonl/.csv)")
    ap.add_argument("--lgc-text-field", default="text")
    ap.add_argument("--lgc-label-field", default="label")
    ap.add_argument("--lgc-ai-values", default="1,ai,llm,machine,generated",
                    help="라벨 필드에서 AI를 뜻하는 값들(쉼표 구분, 대소문자 무시). 나머지는 사람으로 처리")
    ap.add_argument("--lgc-generator-field", default=None, help="LGC에서 생성 모델명이 든 필드 (있으면)")
    ap.add_argument("--lgc-group-field", default=None, help="LGC에서 기사 ID 등 묶음 기준 필드 (있으면)")
    ap.add_argument("--lgc-all-ai", action="store_true",
                    help="라벨 필드 없이 모든 LGC 레코드를 AI로 봄 (XDAC 공개 샘플). 사람 댓글이 없으면 1단계 대신 lgc_ai_test.jsonl만 만든다")
    ap.add_argument("--inspect-lgc", action="store_true", help="LGC 파일 구조(필드·라벨 값)만 출력하고 종료")
    ap.add_argument("--newlines", choices=["auto", "keep", "space"], default="auto",
                    help="리뷰 줄바꿈 처리. auto: 사람/AI 한쪽에만 줄바꿈이 있으면 양쪽 모두 공백으로(지름길 방지)")
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
    ap.add_argument("--human-ratio", type=float, default=1.0,
                    help="2단계에서 사람 리뷰를 'AI 리뷰 수 × 이 값'으로 줄임(별점·길이 맞춤). 0이면 줄이지 않음")
    ap.add_argument("--min-chars", type=int, default=5)
    ap.add_argument("--max-chars", type=int, default=2000)
    ap.add_argument("--stage1-ratios", default="0.9,0.05,0.05")
    ap.add_argument("--stage2-ratios", default="0.8,0.1,0.1")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/processed")
    args = ap.parse_args()

    if args.inspect_lgc:
        if not args.lgc:
            ap.error("--inspect-lgc 에는 --lgc 파일이 필요합니다.")
        inspect_lgc(args.lgc)
        return
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
        if len({r["label"] for r in lgc}) < 2:
            # 사람 댓글이 없으면 분류 학습이 안 된다 → 학습에 섞지 않고 'AI 댓글을 얼마나 잡나'만 보는 테스트셋으로
            only = "AI" if lgc and lgc[0]["label"] == 1 else "사람"
            print(f"[LGC] {only} 댓글만 {len(lgc):,}건 → 1단계 학습 데이터를 만들지 않고 lgc_ai_test.jsonl(추가 테스트)만 씁니다.")
            print("      (2단계는 KcELECTRA 원본에서 바로 리뷰로 학습. 평가 때 --test 에 넣으면 생성 모델별 탐지율(TPR)이 나옵니다)")
            write_jsonl(os.path.join(args.out, "lgc_ai_test.jsonl"), lgc, rng)
            summary["lgc_ai_test"] = summarize("lgc_ai_test", lgc)
        else:
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
        decide_newlines(args.newlines, human, ai, stats)
        reviews = filter_and_dedupe(human + ai, args, stats, "review")
        holdout_gen = {g.strip().lower() for g in args.holdout_generators.split(",") if g.strip()}
        test_plat = {p.strip().lower() for p in args.test_only_platforms.split(",") if p.strip()}

        xplat = [r for r in reviews if r["platform"] in test_plat]
        rest = [r for r in reviews if r["platform"] not in test_plat]
        unseen_ai = [r for r in rest if r["label"] == 1 and r["generator"] in holdout_gen]
        main_rows = [r for r in rest if not (r["label"] == 1 and r["generator"] in holdout_gen)]
        main_rows = balance_humans(main_rows, args.human_ratio, rng, stats)

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
            summary["shortcut_auroc"] = getattr(length_shortcut_check, "result", {})

    print("\n[정제 통계]")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    summary["cleaning_stats"] = dict(stats)
    with open(os.path.join(args.out, "data_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n완료 → {args.out}/ (요약: data_summary.json)")


if __name__ == "__main__":
    main()
