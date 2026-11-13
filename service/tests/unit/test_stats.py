"""README 5.4 고정 검증 예제 — 반드시 통과해야 한다."""

from __future__ import annotations

import math

import pytest

from realstar.aggregate.stats import StarSample, compute_ratings, rogan_gladen

N = {5: 1200, 4: 400, 3: 160, 2: 100, 1: 140}
H = {5: 50, 4: 30, 3: 80, 2: 70, 1: 60}


def fixed_labels() -> dict[int, list[str]]:
    return {s: ["human"] * H[s] + ["ai"] * (100 - H[s]) for s in N}


def test_fixed_example_point_estimates() -> None:
    r = compute_ratings(N, fixed_labels(), displayed_avg=4.2, bootstrap_iterations=1000, seed=1)
    assert r.avg_all == pytest.approx(8420 / 2000)
    assert round(r.avg_all, 2) == 4.21
    assert r.avg_human == pytest.approx(4088 / 1002)
    assert round(r.avg_human, 3) == 4.080
    assert round(r.diff, 2) == -0.13  # type: ignore[arg-type]
    assert round(r.ai_share, 3) == 0.499  # type: ignore[arg-type]
    # 사람 추정 개수 {5:600, 4:120, 3:128, 2:70, 1:84} → 1,002
    assert sum(N[s] * r.r_used[s] for s in N) == pytest.approx(1002)  # type: ignore[operator]


def test_fixed_example_is_not_naive_sample_mean() -> None:
    """잘못된 표본 평균 방식(전체 3.00, 사람 2.79)이 나오면 실패."""
    r = compute_ratings(N, fixed_labels(), bootstrap_iterations=0)
    assert not math.isclose(r.avg_all, 3.00, abs_tol=0.005)  # type: ignore[arg-type]
    assert not math.isclose(r.avg_human, 2.79, abs_tol=0.005)  # type: ignore[arg-type]
    naive_all = sum(s * 100 for s in N) / 500
    naive_human = sum(s * H[s] for s in N) / sum(H.values())
    assert naive_all == 3.0 and round(naive_human, 2) == 2.79  # 비교 기준이 맞는지 확인


def test_bootstrap_ci_contains_point_and_is_reproducible() -> None:
    a = compute_ratings(N, fixed_labels(), bootstrap_iterations=1000, seed=7)
    b = compute_ratings(N, fixed_labels(), bootstrap_iterations=1000, seed=7)
    assert a.avg_human_ci95 == b.avg_human_ci95
    lo, hi = a.avg_human_ci95  # type: ignore[misc]
    assert lo < a.avg_human < hi  # type: ignore[operator]
    assert 0.05 < hi - lo < 0.6
    dlo, dhi = a.diff_ci95  # type: ignore[misc]
    assert dlo < a.diff < dhi  # type: ignore[operator]


def test_uncertain_excluded_from_ratio() -> None:
    labels = fixed_labels()
    labels[5] = ["human"] * 25 + ["ai"] * 25 + ["uncertain"] * 50
    r = compute_ratings(N, labels, bootstrap_iterations=0)
    assert r.r_used[5] == pytest.approx(0.5)
    assert r.per_star[5].uncertain == 50


def test_star_with_no_judged_reviews_uses_pooled_ratio() -> None:
    labels = fixed_labels()
    labels[3] = ["uncertain"] * 10
    r = compute_ratings(N, labels, bootstrap_iterations=200)
    pooled = (50 + 30 + 70 + 60) / 400
    assert r.r_used[3] == pytest.approx(pooled)
    assert any(w.code == "star_ratio_substituted" and w.star == 3 for w in r.warnings)


def test_all_human_zero_no_avg_human() -> None:
    labels = {s: ["ai"] * 50 for s in N}
    r = compute_ratings(N, labels, bootstrap_iterations=100)
    assert r.avg_human is None and r.diff is None
    assert any(w.code == "no_human_reviews" for w in r.warnings)
    assert r.avg_all == pytest.approx(4.21)


def test_insufficient_sample_warning() -> None:
    labels = fixed_labels()
    labels[1] = ["human"] * 10 + ["ai"] * 5
    r = compute_ratings(N, labels, bootstrap_iterations=0, min_judged=30)
    assert [w.star for w in r.warnings if w.code == "insufficient_sample"] == [1]


def test_displayed_avg_mismatch_warning() -> None:
    r = compute_ratings(N, fixed_labels(), displayed_avg=4.0, bootstrap_iterations=0)
    assert any(w.code == "displayed_avg_mismatch" for w in r.warnings)
    r2 = compute_ratings(N, fixed_labels(), displayed_avg=4.2, bootstrap_iterations=0)
    assert not any(w.code == "displayed_avg_mismatch" for w in r2.warnings)


def test_zero_reviews() -> None:
    r = compute_ratings(dict.fromkeys(N, 0), {}, bootstrap_iterations=0)
    assert r.avg_all is None
    assert r.warnings[0].code == "no_reviews"


def test_star_without_reviews_is_ignored() -> None:
    n = {5: 100, 4: 0, 3: 0, 2: 0, 1: 50}
    labels = {5: ["human"] * 40 + ["ai"] * 60, 1: ["human"] * 45 + ["ai"] * 5}
    r = compute_ratings(n, labels, bootstrap_iterations=100)
    # 사람 추정: 5점 40, 1점 45 → (5·40 + 1·45) / 85
    assert r.avg_human == pytest.approx((5 * 40 + 45) / 85)
    assert r.r_used[4] is None


def test_per_star_counts_input() -> None:
    per = {s: StarSample(collected=100, human=H[s], ai=100 - H[s], uncertain=0) for s in N}
    r = compute_ratings(N, per_star=per, bootstrap_iterations=0)
    assert round(r.avg_human, 3) == 4.080  # type: ignore[arg-type]


def test_rogan_gladen() -> None:
    assert rogan_gladen(0.5, 0.9, 0.95) == pytest.approx((0.5 + 0.95 - 1) / (0.9 + 0.95 - 1))
    assert rogan_gladen(0.01, 0.9, 0.95) == 0.0
    assert rogan_gladen(0.99, 0.9, 0.95) == 1.0
    with pytest.raises(ValueError):
        rogan_gladen(0.5, 0.4, 0.5)
    r = compute_ratings(N, fixed_labels(), bootstrap_iterations=0, sens_spec=(0.9, 0.95))
    assert r.corrected is not None and r.corrected["method"] == "rogan_gladen"
