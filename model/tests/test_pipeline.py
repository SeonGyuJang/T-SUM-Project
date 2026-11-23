"""생성(가짜 백엔드) → 데이터셋 → 베이스라인 → Detector 전체 흐름. 실제 API는 호출하지 않는다."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realstar_model.data import load_human, split_of
from realstar_model.data_gen.filters import check, clean_generated, overlap_ratio
from realstar_model.data_gen.generate import run
from realstar_model.datasets.build import build
from realstar_model.eval.metrics import summarize, tpr_at_fpr
from realstar_model.fusion.thresholds import decide, fit_thresholds
from realstar_model.inference import Detector, ReviewInput


def test_split_is_deterministic_and_grouped() -> None:
    assert split_of("cp:123") == split_of("cp:123")
    from collections import Counter

    c = Counter(split_of(f"g{i}") for i in range(10000))
    assert 0.77 < c["train"] / 10000 < 0.83 and 0.08 < c["val"] / 10000 < 0.12


def test_filters() -> None:
    assert clean_generated("물론입니다! 다음은 리뷰입니다: \"배송 빨라요\"") == "배송 빨라요"
    assert clean_generated("**배송** 빨라요") == "배송 빨라요"
    assert check("요청하신 리뷰를 작성해 드릴게요 좋아요 좋아요 좋아요", 20, [], "write") == "meta_phrase"
    assert check("good product very nice quality", 30, [], "write") == "low_hangul"
    anchor = "배송이 정말 빠르고 포장도 꼼꼼해서 만족스러웠습니다"
    assert overlap_ratio(anchor, [anchor]) == 1.0 and check(anchor, len(anchor), [anchor], "write") == "copied_reference"
    assert check(anchor, len(anchor), [anchor], "polish") is None  # 다듬기는 겹침 허용


def test_metrics_and_thresholds() -> None:
    y = [0] * 100 + [1] * 100
    p = [i / 200 for i in range(100)] + [0.5 + i / 200 for i in range(100)]
    assert summarize(y, p)["auroc"] == 1.0 and tpr_at_fpr(y, p, 0.01) == 1.0
    thr = fit_thresholds(p, y, ["M"] * 200, min_n=50)
    assert thr["M"]["T_AI"] >= thr["M"]["T_HUMAN"] and not thr["M"]["pooled"]
    assert decide(0.99, "M", 50, thr) == "ai" and decide(0.0, "M", 50, thr) == "human" and decide(0.99, "M", 5, thr) == "uncertain"


def test_end_to_end(tmp_path: Path, naver_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import realstar_model.models.artifact as artifact
    from realstar_model.models.baseline import train

    monkeypatch.setattr(artifact, "REPORTS", tmp_path / "reports")
    pool = load_human(include_coupang=False, naver_path=naver_file)
    gen = tmp_path / "gen"
    res = run(600, "fake-gen", backend="fake", out_dir=gen, pool=pool, concurrency=4)
    assert res["generated"] > 500
    rows = [json.loads(x) for x in (gen / "ai_fake-gen.jsonl").read_text(encoding="utf-8").splitlines()]
    by_id = {s.sample_id: s for s in pool}
    for r in rows:  # 생성 샘플은 기준 리뷰와 같은 분할·그룹
        anchor = by_id[r["meta"]["anchor_id"]]
        assert r["split"] == anchor.split and r["group"] == anchor.group and r["label"] == 1
    again = run(600, "fake-gen", backend="fake", out_dir=gen, pool=pool)  # 이어서: 목표를 채웠으면 거의 안 만든다
    assert again.get("generated", 0) <= 20

    man = build(gen_dir=gen, out_dir=tmp_path / "proc", human=pool)
    for sp, c in man["splits"].items():
        assert c["human"] == c["ai"], sp  # 1:1
    data = [json.loads(x) for x in (tmp_path / "proc" / "dataset.jsonl").read_text(encoding="utf-8").splitlines()]
    anchors = {r["meta"].get("anchor_id") for r in data if r["label"] == 1}
    assert not anchors & {r["sample_id"] for r in data if r["label"] == 0}  # 기준 리뷰는 사람 쪽에 넣지 않음

    out = train(dataset=tmp_path / "proc" / "dataset.jsonl", art_dir=tmp_path / "art" / "det-ko-review-v0.1")
    assert out["metrics"]["test"]["all"]["auroc"] > 0.9 and "b0_test" in out["metrics"]
    det = Detector.load(tmp_path / "art" / "det-ko-review-v0.1")
    preds = det.predict([ReviewInput(review_id="a", content="배송 빠르고 품질 좋아요 정말 만족해요 재구매 의사 있어요"),
                         ReviewInput(review_id="b", content="굿")])
    assert [p.review_id for p in preds] == ["a", "b"] and preds[1].label == "uncertain"
    assert 0 <= preds[0].p_ai <= 1 and preds[0].model_version == "det-ko-review-v0.1"
    m = json.loads((tmp_path / "art" / "det-ko-review-v0.1" / "manifest.json").read_text(encoding="utf-8"))
    assert {"S", "M", "L"} <= set(m["thresholds"]) and m["model_type"] == "tfidf_lr"
    assert (tmp_path / "reports" / "experiments.csv").exists()


def test_dry_run_prints_prompts_without_api(naver_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pool = load_human(include_coupang=False, naver_path=naver_file)
    res = run(50, "claude-opus-5-5", out_dir=naver_file.parent / "gen", pool=pool, dry_run=True)
    out = capsys.readouterr().out
    assert res["dry_run"] and "[system]" in out and "별점" in out
    assert not (naver_file.parent / "gen").exists()  # 아무것도 저장하지 않음
