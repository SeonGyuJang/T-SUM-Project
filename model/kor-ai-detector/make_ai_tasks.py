"""AI 리뷰 수작업 수집용 작업표 만들기 → 채운 작업표를 prepare_data.py 입력으로 합치기 (README 4.5).

1) 작업표 만들기: 사람 리뷰에서 기준 리뷰를 골라 생성 모델별 프롬프트를 만든다.
   python make_ai_tasks.py make --n 300 --generators chatgpt claude gemini
   → data/ai_tasks/tasks_chatgpt.csv, tasks_claude.csv, tasks_gemini.csv
     (엑셀·구글 시트로 열어 prompt 칸을 해당 서비스 새 대화에 붙여 넣고, 답을 text 칸에, 쓴 모델명을 model_version 칸에 적는다)

2) 합치기: 채운 작업표 → data/raw/ai_<generator>.jsonl (text가 빈 행은 건너뜀)
   python make_ai_tasks.py merge data/ai_tasks/tasks_*.csv

설계 (README 4.5 분포 맞추기):
- 기준 리뷰의 product_id를 AI 리뷰에도 그대로 기록 → 원본과 생성본이 같은 split에 묶여 누출이 없다.
- 별점은 기준 리뷰의 별점, 목표 길이는 같은 별점 사람 리뷰의 길이 분포에서 뽑는다(LLM은 사람보다 길게 쓴다).
- 유형: scratch 40% / style 30% / rewrite 30%. 네이버 말뭉치는 상품명이 없어 scratch·style도 기준 리뷰로 상품을 알려 준다.
- 페르소나·말투·이모지·오타 허용 여부를 무작위 조합한다. 한 대화에 하나씩 요청한다(여러 개를 한 번에 받으면 비슷해진다).
"""
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


def cmd_make(args):
    rng = random.Random(args.seed)
    pool = [r for p in args.human for r in load_jsonl(p) if r.get("text") and r.get("rating")]
    if not pool:
        sys.exit("사람 리뷰가 없습니다. 먼저 python convert_sources.py 를 실행하세요.")
    by_rating = defaultdict(list)
    by_product = defaultdict(list)
    for r in pool:
        by_rating[int(r["rating"])].append(r)
        by_product[r["product_id"]].append(r)
    ratings = sorted(by_rating)
    os.makedirs(args.out, exist_ok=True)
    used = set()
    for gen in args.generators:
        rows = []
        for i in range(args.n):
            kind = rng.choices(list(TYPE_MIX), weights=list(TYPE_MIX.values()))[0]
            rating = rng.choice(ratings)  # 별점을 고르게(사람 쪽 별점 분포는 prepare 단계에서 맞춰 비교)
            anchor = rng.choice(by_rating[rating])
            for _ in range(20):  # 같은 기준 리뷰를 되도록 다시 쓰지 않되, 후보가 적으면 그대로 쓴다
                if anchor.get("source_id") not in used:
                    break
                anchor = rng.choice(by_rating[rating])
            used.add(anchor.get("source_id"))
            same = [x for x in by_product[anchor["product_id"]] if x is not anchor]
            if len(same) >= 3:  # 같은 상품 리뷰가 있으면 그것을 말투 예시로(README 4.5)
                examples = rng.sample(same, k=min(len(same), rng.randint(3, 5)))
            else:  # 없으면(네이버 등) 같은 별점의 다른 리뷰
                others = [x for x in by_rating[rating] if x is not anchor]
                examples = rng.sample(others, k=min(3, len(others)))
            target = len(rng.choice(by_rating[rating])["text"]) if kind != "rewrite" else round(len(anchor["text"]) * rng.uniform(0.9, 1.3))
            target = max(8, min(400, target))
            persona, tone, extra = rng.choice(PERSONAS), rng.choice(TONES), rng.choice(EXTRAS)
            rows.append({
                "task_id": f"{gen}-{i:05d}", "generator": gen, "prompt_type": kind, "product_id": anchor["product_id"],
                "platform": anchor.get("platform", ""), "rating": rating, "target_chars": target, "persona": persona,
                "category": anchor.get("category") or "",
                "prompt": build_prompt(kind, anchor, examples, rating, target, persona, tone, extra),
                "text": "", "model_version": "", "anchor_id": anchor.get("source_id", ""),
            })
        path = os.path.join(args.out, f"tasks_{gen}.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:  # 엑셀에서 한글이 깨지지 않게 BOM
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
        print(f"  → {path}: {len(rows)}건 · 유형 {dict(Counter(r['prompt_type'] for r in rows))} · 플랫폼 {dict(Counter(r['platform'] for r in rows))}")


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
    m.add_argument("--human", nargs="+", default=sorted(glob.glob(os.path.join(ROOT, "data", "raw", "*_human.jsonl"))))
    m.add_argument("--generators", nargs="+", default=["chatgpt", "claude", "gemini"])
    m.add_argument("--n", type=int, default=300, help="생성 모델마다 만들 작업 수")
    m.add_argument("--seed", type=int, default=42)
    m.add_argument("--out", default=os.path.join(ROOT, "data", "ai_tasks"))
    g = sub.add_parser("merge", help="채운 작업표 → data/raw/ai_<generator>.jsonl")
    g.add_argument("files", nargs="+")
    g.add_argument("--out", default=os.path.join(ROOT, "data", "raw"))
    args = ap.parse_args()
    (cmd_make if args.cmd == "make" else cmd_merge)(args)


if __name__ == "__main__":
    main()
