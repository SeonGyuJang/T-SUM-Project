"""베이스라인 학습 (MODEL_DEV.md 4.11.3).

  B0  표면 특징(길이·문장부호) + 로지스틱 회귀   → 지름길 점검용(높으면 데이터 아티팩트를 의심)
  B1  문자 n-gram(2~5) TF-IDF + 로지스틱 회귀    → 첫 배포 가능 모델(det-ko-review-v0.1)

  python -m realstar_model train-baseline
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from realstar_model.data import Sample
from realstar_model.datasets.build import read_dataset
from realstar_model.eval.metrics import report
from realstar_model.fusion.thresholds import apply_platt, fit_platt, fit_thresholds
from realstar_model.models.artifact import default_art_dir, log_experiment, new_experiment_dir, write_manifest
from realstar_model.models.features import FEATURES, surface_matrix
from realstar_model.paths import PROCESSED
from realstar_model.preprocess import clean_review


def _split(rows: list[Sample], name: str) -> list[Sample]:
    return [r for r in rows if r.split == name]


def train(*, version: str = "det-ko-review-v0.1", dataset: Path = PROCESSED / "dataset.jsonl", art_dir: Path | None = None,
          C: float = 4.0, max_features: int = 300_000, seed: int = 42) -> dict[str, Any]:
    rows = read_dataset(dataset)
    manifest = json.loads((dataset.parent / "dataset_manifest.json").read_text(encoding="utf-8")) \
        if (dataset.parent / "dataset_manifest.json").exists() else {}
    tr, va, te = (_split(rows, s) for s in ("train", "val", "test"))
    if not tr or not va or not te:
        raise SystemExit(f"분할이 비어 있어요(train {len(tr)}, val {len(va)}, test {len(te)}). 생성 샘플을 더 늘려 주세요.")
    cl = {id(r): clean_review(r.title, r.text) for r in rows}
    X = {n: [cl[id(r)].text_for_model for r in s] for n, s in (("train", tr), ("val", va), ("test", te))}
    Y = {n: np.asarray([r.label for r in s]) for n, s in (("train", tr), ("val", va), ("test", te))}
    B = {n: [cl[id(r)].len_bucket for r in s] for n, s in (("train", tr), ("val", va), ("test", te))}
    print(f"데이터 {manifest.get('data_version', '?')}: train {len(tr):,} / val {len(va):,} / test {len(te):,}")

    # B0: 지름길 점검
    b0 = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, random_state=seed))
    b0.fit(surface_matrix([cl[id(r)] for r in tr]), Y["train"])
    b0_test = report(Y["test"], b0.predict_proba(surface_matrix([cl[id(r)] for r in te]))[:, 1], B["test"])
    print(f"  B0(표면 특징) test AUROC {b0_test['all'].get('auroc')}  ← 0.8 이상이면 길이·문장부호 지름길을 의심하세요")

    # B1: 문자 n-gram TF-IDF + LR
    b1 = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, max_features=max_features, sublinear_tf=True),
        LogisticRegression(C=C, max_iter=3000, random_state=seed),
    )
    b1.fit(X["train"], Y["train"])
    s_val, s_test = b1.decision_function(X["val"]), b1.decision_function(X["test"])
    cal = fit_platt(s_val, Y["val"])
    p_val, p_test = apply_platt(s_val, cal), apply_platt(s_test, cal)
    thr = fit_thresholds(p_val, Y["val"], B["val"])
    metrics: dict[str, Any] = {"val": report(Y["val"], p_val, B["val"]), "test": report(Y["test"], p_test, B["test"]), "b0_test": b0_test}
    tgen = [i for i, r in enumerate(te) if r.meta.get("t_gen") or r.label == 0]
    if any(te[i].meta.get("t_gen") for i in tgen):  # 처음 보는 생성 모델(t_gen)
        metrics["test_t_gen"] = report(Y["test"][tgen], p_test[tgen], [B["test"][i] for i in tgen])

    art = art_dir or default_art_dir(version)
    art.mkdir(parents=True, exist_ok=True)
    joblib.dump(b1, art / "tfidf_lr.joblib")
    write_manifest(art, model_version=version, model_type="tfidf_lr", data_version=manifest.get("data_version", "unknown"),
                   thresholds=thr, calibration=cal, metrics=metrics,
                   extra={"features": {"b0": FEATURES}, "params": {"C": C, "max_features": max_features, "ngram": [2, 5]},
                          "notes": "베이스라인(B1). 사람 데이터: 네이버 쇼핑(+쿠팡 H1), AI 데이터: 생성 리뷰. 실험용."})
    exp, exp_dir = new_experiment_dir()
    (exp_dir / "metrics.json").write_text(json.dumps({"artifact": str(art), **metrics}, ensure_ascii=False, indent=2), encoding="utf-8")
    t = metrics["test"]["all"]
    log_experiment(exp, {"model_type": "tfidf_lr", "model_version": version, "data_version": manifest.get("data_version"),
                         "test_auroc": t.get("auroc"), "test_tpr@1%fpr": t.get("tpr@1%fpr"), "test_tpr@2%fpr": t.get("tpr@2%fpr"),
                         "test_ece": t.get("ece"), "b0_test_auroc": b0_test["all"].get("auroc"), "notes": "B1 baseline"})
    return {"artifact": str(art), "experiment": exp, "metrics": metrics, "thresholds": thr}
