"""사람 리뷰 + 생성 AI 리뷰 → 학습 데이터셋 (MODEL_DEV.md M3).

  python -m realstar_model build-dataset                 # model/data/generated/*.jsonl 전부 사용
  python -m realstar_model build-dataset --holdout-generator claude-haiku-5-5   # 이 생성 모델은 테스트(t_gen)에만

- 사람 리뷰는 AI 리뷰와 '같은 분할·별점·길이 구간'에서 1:1로 뽑는다 → 길이·별점만으로 구분하는 지름길 차단(D-007)
- 분할은 그룹 단위(D-008). AI 샘플은 기준 리뷰(anchor)의 그룹을 따른다.
- 결과: model/data/processed/dataset.jsonl (+ dataset_manifest.json: 데이터 버전 해시, 분할별·원천별 개수)
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from realstar_model.data import SPLITS, Sample, load_human, read_jsonl
from realstar_model.paths import GENERATED, PROCESSED
from realstar_model.preprocess import clean_review


def load_ai(gen_dir: Path = GENERATED) -> list[Sample]:
    out = []
    for f in sorted(gen_dir.glob("ai_*.jsonl")):
        for r in read_jsonl(f):
            out.append(Sample(**{k: r[k] for k in ("sample_id", "label", "source", "text", "title", "star", "group", "split", "meta")}))
    return out


def build(*, human_ratio: float = 1.0, holdout_generator: str | None = None, seed: int = 42, include_coupang: bool = True,
          gen_dir: Path = GENERATED, out_dir: Path = PROCESSED, human: list[Sample] | None = None) -> dict[str, Any]:
    rng = random.Random(seed)
    ai = load_ai(gen_dir)
    if not ai:
        raise SystemExit(f"생성된 AI 리뷰가 없어요({gen_dir}/ai_*.jsonl). 먼저 `python -m realstar_model generate` 를 실행하세요.")
    human = human if human is not None else load_human(include_coupang=include_coupang)
    if holdout_generator:  # D-008: 처음 보는 생성 모델 일반화 측정용 → 이 모델 샘플은 test로만
        for s in ai:
            if s.meta.get("generator_id") == holdout_generator:
                s.split = "test"
                s.meta["t_gen"] = True

    def key(s: Sample) -> tuple[str, int, str]:
        return (s.split, int(s.star or 0), clean_review(s.title, s.text).len_bucket)

    pool: dict[tuple[str, int, str], list[Sample]] = defaultdict(list)
    by_split_star: dict[tuple[str, int], list[Sample]] = defaultdict(list)
    for s in human:
        pool[key(s)].append(s)
        by_split_star[(s.split, int(s.star or 0))].append(s)
    for lst in list(pool.values()) + list(by_split_star.values()):
        rng.shuffle(lst)
    used: set[str] = set()
    picked: list[Sample] = []
    short: Counter[str] = Counter()
    anchors = {s.meta.get("anchor_id") for s in ai}
    for s in ai:
        for _ in range(max(1, round(human_ratio))):
            cand = next((h for h in pool[key(s)] if h.sample_id not in used and h.sample_id not in anchors), None)
            if cand is None:  # 같은 길이 구간이 모자라면 같은 별점 아무 길이에서
                cand = next((h for h in by_split_star[(s.split, int(s.star or 0))] if h.sample_id not in used and h.sample_id not in anchors), None)
                short["length_relaxed"] += 1
            if cand is None:
                short["no_human"] += 1
                continue
            used.add(cand.sample_id)
            picked.append(cand)
    rows = [*picked, *ai]
    rng.shuffle(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "dataset.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for s in rows:
            f.write(json.dumps(s.to_dict(), ensure_ascii=False) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    counts = {sp: {"human": sum(1 for s in rows if s.split == sp and s.label == 0),
                   "ai": sum(1 for s in rows if s.split == sp and s.label == 1)} for sp in SPLITS}
    manifest = {
        "data_version": f"data-v0-{digest}", "path": str(path), "rows": len(rows), "splits": counts,
        "sources": dict(Counter(s.source for s in rows)), "holdout_generator": holdout_generator,
        "matching": dict(short), "human_pool": len(human),
        "len_buckets": {lab: dict(Counter(clean_review(s.title, s.text).len_bucket for s in rows if s.label == i))
                        for i, lab in ((0, "human"), (1, "ai"))},
    }
    (out_dir / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def read_dataset(path: Path = PROCESSED / "dataset.jsonl") -> list[Sample]:
    if not path.exists():
        raise SystemExit(f"데이터셋이 없어요: {path}\n  먼저 `python -m realstar_model build-dataset` 를 실행하세요.")
    return [Sample(**r) for r in read_jsonl(path)]
