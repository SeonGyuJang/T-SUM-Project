"""AI 리뷰 수작업 수집용 작업표 만들기 → 채운 작업표를 prepare_data.py 입력으로 합치기 (README 4.5).

1) 작업표 만들기: 사람 리뷰에서 기준 리뷰를 골라 생성 모델별 프롬프트를 만든다. --n 은 생성 모델마다의 건수.
   python make_ai_tasks.py make --n 1000 --generators chatgpt claude gemini
   → data/ai_tasks/tasks_chatgpt.csv, tasks_claude.csv, tasks_gemini.csv
   쿠팡 카테고리를 더 모은 뒤 추가로 만들 때 (채우던 작업표는 그대로 두고 새 파일로):
   python convert_sources.py && python make_ai_tasks.py make --batch b2 --n 500
     (엑셀·구글 시트로 열어 prompt 칸을 해당 서비스 새 대화에 붙여 넣고, 답을 text 칸에, 쓴 모델명을 model_version 칸에 적는다)

2) 합치기: 채운 작업표 → data/raw/ai_<generator>.jsonl (text가 빈 행은 건너뜀)
   python make_ai_tasks.py merge data/ai_tasks/tasks_*.csv

설계 (README 4.5 분포 맞추기):
- 기준 리뷰의 product_id를 AI 리뷰에도 그대로 기록 → 원본과 생성본이 같은 split에 묶여 누출이 없다.
- 기준 리뷰는 출처별로 고르게: 카테고리 몫(--category-share, 기본 50%)을 AI Hub·쿠팡 카테고리마다 똑같이, 나머지를 네이버에서.
- 별점은 기준 리뷰의 별점, 목표 길이는 같은 출처·별점 사람 리뷰의 길이 분포에서 뽑는다(LLM은 사람보다 길게 쓴다).
- 유형: scratch 40% / style 30% / rewrite 30%. 네이버 말뭉치는 상품명이 없어 scratch·style도 기준 리뷰로 상품을 알려 준다.
- 페르소나·말투·이모지·오타 허용 여부를 무작위 조합한다. 한 대화에 하나씩 요청한다(여러 개를 한 번에 받으면 비슷해진다).
"""
import _winconsole  # noqa: F401  윈도우(cp949) 출력에서 기호 때문에 멈추지 않게
import argparse
import csv
import glob
import json
import os
import random
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
COLUMNS = ["task_id", "generator", "prompt_type", "product_id", "platform", "rating", "target_chars", "persona",
           "category", "prompt", "text", "model_version", "anchor_id"]
PERSONAS = ["20대 대학생", "20대 사회초년생", "30대 직장인", "30대 육아 중인 부모", "40대 주부", "40대 회사원",
            "50대 자영업자", "60대 은퇴자", "자취하는 1인 가구", "꼼꼼하게 비교하고 사는 사람", "물건을 자주 사는 단골"]
TONES = ["존댓말로 담백하게", "반말로 편하게", "수다스럽게", "핵심만 짧게", "불만은 솔직하게", "친근하게"]
EXTRAS = ["", "", "이모지를 한두 개 써도 돼.", "맞춤법·띄어쓰기를 가끔 틀려도 되고 ㅋㅋ, ㅠㅠ 같은 표현을 써도 돼.",
          "실제 구매자가 쓴 것처럼 자연스럽게 써."]
TYPE_MIX = {"scratch": 0.4, "style": 0.3, "rewrite": 0.3}
END = "리뷰 본문만 출력해. 인사말·설명·제목·따옴표는 쓰지 마."


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def iya(word):
    """받침이 있으면 '이야', 없으면 '야' (단골이야 / 직장인이야 / 주부야)."""
    ch = word[-1]
    if "가" <= ch <= "힣":
        return word + ("이야" if (ord(ch) - 0xAC00) % 28 else "야")
    return word + "이야"


def length_hint(n):
    if n < 15:
        return f"한 문장, {n}자 내외"
    if n < 40:
        return f"한두 문장, {n}자 내외"
    return f"약 {n}자"


def build_prompt(kind, anchor, examples, rating, target, persona, tone, extra):
    product = anchor.get("product_name")
    lines = []
    if kind == "rewrite":
        lines.append(f"다음은 별점 {rating}점짜리 상품 리뷰야.\n\n{anchor['text']}\n")
        lines.append(f"이 리뷰를 더 자연스럽고 읽기 좋게 다듬어서 다시 써 줘. 내용과 별점의 느낌은 유지하고, 분량은 {length_hint(target)}로.")
    else:
        if product:
            lines.append(f"상품: {product}" + (f" (카테고리: {anchor['category']})" if anchor.get("category") else ""))
        else:
            lines.append(f"다음은 어떤 상품을 산 사람이 남긴 리뷰야. 어떤 상품인지만 파악하고 내용은 따라 하지 마.\n\n{anchor['text']}\n")
        if kind == "style" and examples:
            lines.append("다음은 실제 구매자들이 쓴 리뷰들이야. 이런 말투로 써 줘(내용·표현은 베끼지 마):")
            lines += [f"- {e['text']}" for e in examples]
            lines.append("")
        lines.append(f"너는 이 상품을 산 {iya(persona)}. 별점 {rating}점을 주는 리뷰를 {tone} 써 줘. 분량: {length_hint(target)}.")
    if extra:
        lines.append(extra)
    lines.append(END)
    return "\n".join(lines)


def source_of(r):
    """기준 리뷰의 출처 칸: 카테고리가 있는 출처(AI Hub·쿠팡)는 카테고리별, 네이버는 하나(카테고리 정보 없음)."""
    plat = r.get("platform") or "?"
    return f"{plat}:{r['category']}" if r.get("category") else plat


def read_existing(out_dir):
    """이미 만든 작업표들: 쓴 기준 리뷰 id(다음 묶음에서 다시 안 쓰도록)와 파일별 채운 행 수."""
    used, filled = set(), {}
    for path in glob.glob(os.path.join(out_dir, "tasks_*.csv")):
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        used.update(r.get("anchor_id") for r in rows if r.get("anchor_id"))
        filled[os.path.abspath(path)] = sum(1 for r in rows if (r.get("text") or "").strip())
    return used, filled


def plan_sources(pool, coupang_share, total, cap=0.5):
    """출처별 뽑을 비율. 카테고리 몫(coupang_share)을 카테고리(AI Hub·쿠팡)들에 똑같이 나누고 나머지는 네이버 등에.
    풀 크기 비례로 뽑으면 큰 출처가 거의 전부를 차지하고, 그 안에서도 많이 모인 카테고리만 나온다.
    단, 한 출처의 AI 수가 그 출처 사람 리뷰의 cap(50%)을 넘지 않게 한다: 넘으면 prepare 단계에서 같은 출처 사람 리뷰로
    짝을 못 맞춰 "그 카테고리 = AI"라는 지름길이 생긴다. 넘친 몫은 여유 있는 다른 카테고리 → 네이버 순으로 넘긴다."""
    by_src = defaultdict(list)
    for r in pool:
        by_src[source_of(r)].append(r)
    cp = [k for k in by_src if ":" in k]          # 카테고리 칸
    other = [k for k in by_src if ":" not in k]   # 카테고리 없는 출처(네이버)
    if not cp or not other:
        share = {k: 1 / len(by_src) for k in by_src}
    else:
        share = {k: coupang_share / len(cp) for k in cp}
        share.update({k: (1 - coupang_share) / len(other) for k in other})
    limit = {k: cap * len(v) / max(1, total) for k, v in by_src.items()}
    capped = set()
    for _ in range(len(share) + 1):
        over = sum(max(0.0, share[k] - limit[k]) for k in share)
        if over <= 1e-12:
            break
        for k in share:
            if share[k] > limit[k]:
                share[k] = limit[k]
                capped.add(k)
        room = [k for k in cp if k not in capped] or [k for k in other if k not in capped]
        if not room:  # 전부 꽉 참: 사람 리뷰가 모자라다 → 비율만 정규화하고 경고
            break
        for k in room:
            share[k] += over / len(room)
    tot = sum(share.values())
    share = {k: v / tot for k, v in share.items()}
    return by_src, share, capped


def cmd_make(args):
    rng = random.Random(args.seed if not args.batch else f"{args.seed}-{args.batch}")
    pool = [r for p in args.human for r in load_jsonl(p) if r.get("text") and r.get("rating")]
    if not pool:
        sys.exit("사람 리뷰가 없습니다. 먼저 python convert_sources.py 를 실행하세요.")
    os.makedirs(args.out, exist_ok=True)
    used, filled = read_existing(args.out)
    suffix = f"_{args.batch}" if args.batch else ""
    for gen in args.generators:  # 채우던 작업표를 덮어쓰지 않도록 먼저 전부 확인
        path = os.path.abspath(os.path.join(args.out, f"tasks_{gen}{suffix}.csv"))
        if filled.get(path) and not args.force:
            sys.exit(f"{path} 에 이미 답을 채운 행이 {filled[path]}건 있어 덮어쓰지 않습니다.\n"
                     f"  → 새 묶음으로 만드세요:  python make_ai_tasks.py make --batch b2 --n …  (이전 묶음에서 쓴 기준 리뷰는 자동으로 피함)")
    by_rating, by_product = defaultdict(list), defaultdict(list)
    for r in pool:
        by_rating[int(r["rating"])].append(r)
        by_product[r["product_id"]].append(r)
    by_src, share, capped = plan_sources(pool, args.coupang_share, args.n * len(args.generators))
    src_rating = {k: defaultdict(list) for k in by_src}
    for k, rows in by_src.items():
        for r in rows:
            src_rating[k][int(r["rating"])].append(r)
    print(f"  기준 리뷰 출처 비율: " + ", ".join(f"{k} {v:.0%}({len(by_src[k]):,}건 중)" for k, v in sorted(share.items())))
    if used:
        print(f"  이전 작업표에서 쓴 기준 리뷰 {len(used):,}건은 피합니다.")
    if capped:
        print(f"  · 사람 리뷰가 적어 몫을 줄인 출처: {sorted(capped)} (AI가 그 출처 사람 리뷰의 절반을 넘지 않게). 더 모으면 늘어납니다.")
    keys, weights = list(share), list(share.values())
    for gen in args.generators:
        rows = []
        for i in range(args.n):
            kind = rng.choices(list(TYPE_MIX), weights=list(TYPE_MIX.values()))[0]
            src = rng.choices(keys, weights=weights)[0]
            ratings = sorted(src_rating[src])
            rating = rng.choice(ratings)  # 별점을 고르게(사람 쪽 별점·길이·출처 분포는 prepare 단계에서 AI에 맞춰 뽑음)
            cands = src_rating[src][rating]
            anchor = rng.choice(cands)
            for _ in range(20):  # 같은 기준 리뷰를 되도록 다시 쓰지 않되, 후보가 적으면 그대로 쓴다
                if anchor.get("source_id") not in used:
                    break
                anchor = rng.choice(cands)
            used.add(anchor.get("source_id"))
            same = [x for x in by_product[anchor["product_id"]] if x is not anchor]
            if len(same) >= 3:  # 같은 상품 리뷰가 있으면 그것을 말투 예시로(README 4.5)
                examples = rng.sample(same, k=min(len(same), rng.randint(3, 5)))
            else:  # 없으면(네이버 등) 같은 출처·별점의 다른 리뷰
                others = [x for x in cands if x is not anchor] or [x for x in by_rating[rating] if x is not anchor]
                examples = rng.sample(others, k=min(3, len(others)))
            length_ref = src_rating[src][rating] if len(src_rating[src][rating]) >= 20 else by_rating[rating]
            target = len(rng.choice(length_ref)["text"]) if kind != "rewrite" else round(len(anchor["text"]) * rng.uniform(0.9, 1.3))
            target = max(8, min(400, target))
            persona, tone, extra = rng.choice(PERSONAS), rng.choice(TONES), rng.choice(EXTRAS)
            rows.append({
                "task_id": f"{gen}{'-' + args.batch if args.batch else ''}-{i:05d}", "generator": gen, "prompt_type": kind,
                "product_id": anchor["product_id"],
                "platform": anchor.get("platform", ""), "rating": rating, "target_chars": target, "persona": persona,
                "category": anchor.get("category") or "",
                "prompt": build_prompt(kind, anchor, examples, rating, target, persona, tone, extra),
                "text": "", "model_version": "", "anchor_id": anchor.get("source_id", ""),
            })
        path = os.path.join(args.out, f"tasks_{gen}{suffix}.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:  # 엑셀에서 한글이 깨지지 않게 BOM
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
        cats = Counter(r["category"] for r in rows if r["category"])
        print(f"  → {path}: {len(rows)}건 · 유형 {dict(Counter(r['prompt_type'] for r in rows))} · 플랫폼 {dict(Counter(r['platform'] for r in rows))}"
              + (f"\n     카테고리 {len(cats)}개: {dict(cats.most_common(12))}" if cats else ""))


def cmd_merge(args):
    out_rows = defaultdict(list)
    skipped = Counter()
    for pattern in args.files:
        for path in glob.glob(pattern) or [pattern]:
            with open(path, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    text = (r.get("text") or "").strip()
                    if not text:
                        skipped["빈 text"] += 1
                        continue
                    gen = (r.get("generator") or "").strip().lower()
                    if not gen:
                        skipped["generator 없음"] += 1
                        continue
                    out_rows[gen].append({
                        "text": text, "product_id": r["product_id"], "platform": r.get("platform") or "generated",
                        "generator": gen, "model_version": (r.get("model_version") or "").strip(),
                        "prompt_type": r.get("prompt_type"), "rating": r.get("rating"), "category": r.get("category") or None,
                        "task_id": r.get("task_id"), "anchor_id": r.get("anchor_id"),
                    })
    os.makedirs(args.out, exist_ok=True)
    for gen, rows in out_rows.items():
        path = os.path.join(args.out, f"ai_{gen}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        no_ver = sum(1 for r in rows if not r["model_version"])
        print(f"  → {path}: {len(rows)}건 · 유형 {dict(Counter(r['prompt_type'] for r in rows))}"
              + (f" · ⚠ model_version 빈 행 {no_ver}건" if no_ver else ""))
    if skipped:
        print(f"  건너뜀: {dict(skipped)}")
    if not out_rows:
        sys.exit("text가 채워진 행이 없습니다.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="작업표 만들기")
    merged = os.path.join(ROOT, "data", "raw", "human_reviews.jsonl")  # convert_sources.py가 만든 합본
    m.add_argument("--human", nargs="+",
                   default=[merged] if os.path.exists(merged) else sorted(glob.glob(os.path.join(ROOT, "data", "raw", "*_human.jsonl"))))
    m.add_argument("--generators", nargs="+", default=["chatgpt", "claude", "gemini"])
    m.add_argument("--n", type=int, default=300, help="생성 모델마다 만들 작업 수")
    m.add_argument("--category-share", "--coupang-share", dest="coupang_share", type=float, default=0.5,
                   help="기준 리뷰 중 카테고리 있는 출처(AI Hub·쿠팡)의 몫, 카테고리마다 똑같이 나눔. 나머지는 네이버")
    m.add_argument("--batch", default="", help="추가 묶음 이름(예: b2) → tasks_<모델>_b2.csv. 이전 묶음의 기준 리뷰는 피함")
    m.add_argument("--force", action="store_true", help="답을 채운 작업표도 덮어씀(주의)")
    m.add_argument("--seed", type=int, default=42)
    m.add_argument("--out", default=os.path.join(ROOT, "data", "ai_tasks"))
    g = sub.add_parser("merge", help="채운 작업표 → data/raw/ai_<generator>.jsonl")
    g.add_argument("files", nargs="+")
    g.add_argument("--out", default=os.path.join(ROOT, "data", "raw"))
    args = ap.parse_args()
    (cmd_make if args.cmd == "make" else cmd_merge)(args)


if __name__ == "__main__":
    main()
