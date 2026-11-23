"""AI 리뷰 생성 실행 (MODEL_DEV.md 4.5).

  python -m realstar_model generate --n 2000                          # 기본: claude-opus-5-5
  python -m realstar_model generate --n 2000 --model claude-sonnet-5-5 # 생성 모델마다 따로 돌려 다양성 확보(D-008)
  python -m realstar_model generate --n 5 --dry-run                   # API 호출 없이 프롬프트만 확인

- Claude API 키: ANTHROPIC_API_KEY 환경 변수(또는 `ant auth login`)
- 결과: model/data/generated/ai_<모델>.jsonl  (한 줄 = 샘플 1건, 생성되는 즉시 저장 → 끊겨도 이어서 실행)
- 기준 리뷰(anchor)와 참고 리뷰는 항상 같은 분할(train/val/test)에서 고르고, 생성 샘플도 그 분할에 넣는다(누수 방지).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from realstar_model.data import SPLIT_RATIO, SPLITS, Sample, load_human, read_jsonl
from realstar_model.data_gen.filters import check, clean_generated
from realstar_model.data_gen.prompts import (
    HUMANIZE_WEIGHTS,
    PERSONAS,
    PROMPT_VERSION,
    SYSTEM,
    TONES,
    GenSpec,
    build_prompt,
    pick,
)
from realstar_model.paths import GENERATED
from realstar_model.preprocess import clean_review

KST = timezone(timedelta(hours=9))
DEFAULT_MODEL = "claude-opus-5-5"
# 서버 측 거절 대체(fallbacks="default")를 지원하는 모델. Haiku 5.5는 서버 측 대체가 없다.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-fable-5-1"}
# output_config.effort를 받지 않는 예전 모델
NO_EFFORT_MODELS = {"claude-haiku-4-5", "claude-sonnet-4-5"}

Backend = Callable[[str, str], dict[str, Any]]  # (system, user) -> {"text", "stop_reason", "served_model", "usage", "fell_back"}


def claude_backend(model: str, effort: str) -> Backend:
    import anthropic

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY · ANTHROPIC_AUTH_TOKEN · `ant auth login` 프로필 순으로 찾는다

    def call(system: str, user: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model, "max_tokens": 16000, "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if model not in NO_EFFORT_MODELS:
            kwargs["output_config"] = {"effort": effort}  # 짧은 리뷰 작성이라 low면 충분하다
        if model in FALLBACK_MODELS:
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            resp = client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if b.type == "text") if resp.stop_reason != "refusal" else ""
        fell_back = any(getattr(b, "type", "") == "fallback" for b in resp.content)
        usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
        return {"text": text, "stop_reason": resp.stop_reason, "served_model": resp.model, "usage": usage, "fell_back": fell_back}

    return call


def fake_backend(model: str, effort: str) -> Backend:
    """테스트 전용: API 없이 규칙으로 문장을 만든다. 실제 학습 데이터로 쓰면 안 된다."""
    words = ["배송", "포장", "가격", "품질", "디자인", "사용감", "마감", "냄새", "크기", "색상", "성능", "재구매"]

    def call(system: str, user: str) -> dict[str, Any]:
        rng = random.Random(hashlib.sha256(user.encode()).hexdigest())
        m = re.search(r"분량(?:은|:)?\s*약\s*(\d+)자", user)
        target = int(m.group(1)) if m else 60
        out = ""
        while len(out) < target:
            out += f"{rng.choice(words)}{rng.choice(['이', '도', '은'])} {rng.choice(['괜찮아요', '만족스러워요', '아쉬워요', '좋네요', '그저 그래요'])}. "
        return {"text": out.strip(), "stop_reason": "end_turn", "served_model": f"fake:{model}", "usage": {}, "fell_back": False}

    return call


def make_specs(pool: list[Sample], n_by_split: dict[str, int], seed: int, polish_ratio: float) -> list[tuple[str, GenSpec]]:
    """분할별로 생성 명세를 만든다. 별점은 그 분할의 사람 리뷰에 있는 별점 중 균등하게(4.5.2)."""
    rng = random.Random(seed)
    by_split_star: dict[tuple[str, int], list[Sample]] = defaultdict(list)
    for s in pool:
        if s.star:
            by_split_star[(s.split, int(s.star))].append(s)
    specs: list[tuple[str, GenSpec]] = []
    for split, n in n_by_split.items():
        stars = sorted({st for (sp, st) in by_split_star if sp == split})
        if not stars:
            continue
        for _ in range(n):
            star = rng.choice(stars)
            cands = by_split_star[(split, star)]
            anchor = rng.choice(cands)
            refs = rng.sample(cands, k=min(len(cands), rng.choice([0, 0, 1, 2])))
            refs = [r for r in refs if r.sample_id != anchor.sample_id]
            mode = "polish" if rng.random() < polish_ratio else "write"
            if mode == "polish":  # 다듬기는 원래 리뷰 길이 근처로
                base = clean_review(anchor.title, anchor.text).len_chars
                target = round(base * rng.uniform(0.9, 1.4))
            else:  # D-007: 같은 별점 사람 리뷰의 길이 분포에서
                length_from = rng.choice(cands)
                target = clean_review(length_from.title, length_from.text).len_chars
            target = max(10, min(600, target))
            specs.append((split, GenSpec(
                mode=mode,
                star=star, target_chars=target, persona=rng.choice(PERSONAS), tone=rng.choice(TONES),
                humanize=pick(rng, HUMANIZE_WEIGHTS), anchor_id=anchor.sample_id, anchor_text=anchor.text,
                anchor_group=anchor.group, ref_ids=[r.sample_id for r in refs], ref_texts=[r.text for r in refs],
            )))
    return specs


def output_path(model: str, out_dir: Path = GENERATED) -> Path:
    return out_dir / f"ai_{model.replace('/', '_')}.jsonl"


def run(n: int, model: str = DEFAULT_MODEL, *, backend: str = "claude", effort: str = "low", concurrency: int = 4,
        polish_ratio: float = 0.2, seed: int = 42, out_dir: Path = GENERATED, dry_run: bool = False,
        include_coupang: bool = True, pool: list[Sample] | None = None) -> dict[str, Any]:
    pool = pool if pool is not None else load_human(include_coupang=include_coupang)
    out = output_path(model, out_dir)
    have = Counter(r["split"] for r in read_jsonl(out))
    want = {sp: round(n * r) for sp, r in zip(SPLITS, SPLIT_RATIO, strict=True)}
    todo = {sp: max(0, want[sp] - have.get(sp, 0)) for sp in SPLITS}
    print(f"목표 {n}건 {want} / 이미 생성 {dict(have)} / 이번에 {todo} · 모델 {model} · 사람 리뷰 풀 {len(pool):,}건")
    # 이미 생성한 만큼 시드를 옮겨 같은 명세가 반복되지 않게 한다
    specs = make_specs(pool, todo, seed + sum(have.values()), polish_ratio)
    if dry_run:
        for split, spec in specs[: min(5, len(specs))]:
            print(f"\n── [{split}] mode={spec.mode} star={spec.star} target≈{spec.target_chars}자 persona={spec.persona} humanize={spec.humanize}")
            print(f"[system] {SYSTEM}\n[user]\n{build_prompt(spec)}")
        return {"dry_run": True, "planned": len(specs)}
    if not specs:
        return {"generated": 0, "path": str(out)}
    call = (fake_backend if backend == "fake" else claude_backend)(model, effort)
    seen = {clean_review(None, r["text"]).clean_text for r in read_jsonl(out)}
    out.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    stats: Counter[str] = Counter()
    tokens: Counter[str] = Counter()
    t0 = time.time()

    def one(split: str, spec: GenSpec) -> tuple[str, dict[str, Any] | None]:
        user = build_prompt(spec)
        try:
            res = call(SYSTEM, user)
        except Exception as e:  # SDK가 429·5xx·연결 오류는 자동 재시도한 뒤 남은 오류
            return f"api_error:{type(e).__name__}", None
        if res["stop_reason"] == "refusal":
            return "refusal", None
        if res["stop_reason"] == "max_tokens":
            return "max_tokens", None
        text = clean_generated(res["text"])
        why = check(text, spec.target_chars, [spec.anchor_text, *spec.ref_texts], spec.mode)
        if why:
            return why, None
        sid = "ai-" + hashlib.sha1(f"{model}|{text}".encode()).hexdigest()[:16]
        rec = Sample(
            sample_id=sid, label=1, source=f"ai:{model}", text=text, star=spec.star,
            group=spec.anchor_group, split=split,
            meta={"generator_id": model, "served_model": res["served_model"], "fell_back": res["fell_back"],
                  "mode": spec.mode, "subtype": "polished" if spec.mode == "polish" else "generated",
                  "persona": spec.persona, "tone": spec.tone, "humanize_level": spec.humanize,
                  "n_refs": len(spec.ref_ids), "anchor_id": spec.anchor_id, "ref_review_ids": spec.ref_ids,
                  "target_chars": spec.target_chars, "effort": effort, "prompt_template_id": PROMPT_VERSION,
                  "usage": res["usage"], "created_at": datetime.now(KST).isoformat(timespec="seconds")},
        ).to_dict()
        return "ok", rec

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futs = [ex.submit(one, sp, spec) for sp, spec in specs]
        for i, f in enumerate(as_completed(futs), 1):
            status, rec = f.result()
            with lock:
                if rec is not None:
                    key = clean_review(None, rec["text"]).clean_text
                    if key in seen:
                        status, rec = "duplicate", None
                    else:
                        seen.add(key)
                        with out.open("a", encoding="utf-8") as fh:  # 생성되는 즉시 저장
                            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        for k, v in (rec["meta"].get("usage") or {}).items():
                            tokens[k] += v
                stats[status] += 1
                if i % 25 == 0 or i == len(futs):
                    print(f"  {i}/{len(futs)} · 저장 {stats['ok']} · 탈락 {dict((k, v) for k, v in stats.items() if k != 'ok')} · "
                          f"토큰 입력 {tokens['input_tokens']:,} / 출력 {tokens['output_tokens']:,} · {time.time() - t0:.0f}초", flush=True)
    return {"generated": stats["ok"], "rejected": {k: v for k, v in stats.items() if k != "ok"}, "tokens": dict(tokens), "path": str(out)}
