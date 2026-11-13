"""별점 재계산 (README 5.4) — 가장 중요한 계산.

⚠️ 표본 평균으로 계산하지 않는다. 별점별 사람 비율 r_s를 표본에서 추정하고,
   실제 별점 분포 N_s에 가중한다.

  avg_all   = Σ s·N_s / Σ N_s
  avg_human = Σ s·N_s·r_s / Σ N_s·r_s
  diff      = avg_human − avg_all
  ai_share  = 1 − Σ N_s·r_s / Σ N_s
  r_s       = h_s / (h_s + a_s)   (판단 보류는 판정된 리뷰와 비율이 같다고 가정하고 제외)
  95% CI    = 별점별 표본 안에서 리뷰를 복원추출하는 부트스트랩 1,000회
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

STARS = (5, 4, 3, 2, 1)
Label = str  # "human" | "ai" | "uncertain"


@dataclass
class Warning_:
    code: str
    message: str
    star: int | None = None
    level: str = "warning"  # info | warning

    def as_dict(self) -> dict[str, object]:
        d: dict[str, object] = {"code": self.code, "level": self.level, "message": self.message}
        if self.star is not None:
            d["star"] = self.star
        return d


@dataclass
class StarSample:
    collected: int
    human: int
    ai: int
    uncertain: int

    @property
    def judged(self) -> int:
        return self.human + self.ai

    @property
    def human_ratio(self) -> float | None:
        return self.human / self.judged if self.judged else None


@dataclass
class RatingsResult:
    avg_all: float | None
    avg_human: float | None
    diff: float | None
    ai_share: float | None
    avg_human_ci95: tuple[float, float] | None
    diff_ci95: tuple[float, float] | None
    ai_share_ci95: tuple[float, float] | None
    per_star: dict[int, StarSample]
    r_used: dict[int, float | None]
    warnings: list[Warning_] = field(default_factory=list)
    corrected: dict[str, object] | None = None


def count_labels(labels_by_star: Mapping[int, list[Label]]) -> dict[int, StarSample]:
    out = {}
    for s in STARS:
        labels = labels_by_star.get(s, [])
        out[s] = StarSample(
            collected=len(labels),
            human=sum(1 for x in labels if x == "human"),
            ai=sum(1 for x in labels if x == "ai"),
            uncertain=sum(1 for x in labels if x == "uncertain"),
        )
    return out


def _point_estimate(
    N: Mapping[int, int], h: Mapping[int, float], a: Mapping[int, float]
) -> tuple[float | None, float | None, dict[int, float | None], list[int], bool]:
    """반환: (avg_human, ai_share, r_used, 대체된 별점들, 모든 별점 h=0 여부)."""
    total_h = sum(h[s] for s in STARS if N.get(s, 0) > 0)
    total_j = sum(h[s] + a[s] for s in STARS if N.get(s, 0) > 0)
    pooled = total_h / total_j if total_j else None
    r: dict[int, float | None] = {}
    substituted: list[int] = []
    for s in STARS:
        if N.get(s, 0) <= 0:
            r[s] = None
            continue
        j = h[s] + a[s]
        if j > 0:
            r[s] = h[s] / j
        else:
            r[s] = pooled  # h_s + a_s = 0 → 전체 표본 평균 비율로 대체
            substituted.append(s)
    all_h_zero = total_h == 0
    sum_N = sum(N.get(s, 0) for s in STARS)
    weights = {s: N.get(s, 0) * (r[s] or 0.0) for s in STARS if r[s] is not None}
    sum_w = sum(weights.values())
    if all_h_zero or sum_w <= 0 or pooled is None:
        return None, (1.0 - sum_w / sum_N) if (sum_N and pooled is not None) else None, r, substituted, all_h_zero
    avg_human = sum(s * w for s, w in weights.items()) / sum_w
    ai_share = 1.0 - sum_w / sum_N
    return avg_human, ai_share, r, substituted, all_h_zero


def _bootstrap(
    N: Mapping[int, int], samples: Mapping[int, StarSample], iters: int, seed: int, avg_all: float
) -> tuple[tuple[float, float] | None, tuple[float, float] | None, tuple[float, float] | None]:
    """별점별 표본(판단 보류 포함)을 복원추출한다. 다항분포 추출과 동치라 벡터화했다."""
    rng = np.random.default_rng(seed)
    active = [s for s in STARS if N.get(s, 0) > 0]
    if not active or iters <= 0:
        return None, None, None
    H = np.zeros((iters, len(active)))
    A = np.zeros((iters, len(active)))
    for k, s in enumerate(active):
        smp = samples[s]
        n = smp.collected
        if n == 0:
            continue
        draws = rng.multinomial(n, [smp.human / n, smp.ai / n, smp.uncertain / n], size=iters)
        H[:, k], A[:, k] = draws[:, 0], draws[:, 1]
    Nv = np.array([N[s] for s in active], dtype=float)
    Sv = np.array(active, dtype=float)
    J = H + A
    pooled = np.divide(H.sum(1), J.sum(1), out=np.full(iters, np.nan), where=J.sum(1) > 0)
    R = np.divide(H, J, out=np.repeat(pooled[:, None], len(active), axis=1), where=J > 0)
    W = Nv[None, :] * R
    sw = W.sum(1)
    ok = (sw > 0) & ~np.isnan(sw)
    if ok.sum() < max(10, iters // 2):
        return None, None, None
    avg_h = (W[ok] * Sv).sum(1) / sw[ok]
    ai = 1.0 - sw[ok] / Nv.sum()
    lo, hi = 2.5, 97.5
    ci = lambda x: (float(np.percentile(x, lo)), float(np.percentile(x, hi)))  # noqa: E731
    return ci(avg_h), ci(avg_h - avg_all), ci(ai)


def rogan_gladen(obs_ai: float, sens: float, spec: float) -> float:
    """(Phase 8) 오분류 보정: r_ai_corr = clip((obs_ai + spec − 1)/(sens + spec − 1), 0, 1)."""
    denom = sens + spec - 1.0
    if denom <= 0:
        raise ValueError("sens + spec must be > 1")
    return float(min(1.0, max(0.0, (obs_ai + spec - 1.0) / denom)))


def compute_ratings(
    star_counts: Mapping[int, int],
    labels_by_star: Mapping[int, list[Label]] | None = None,
    *,
    per_star: Mapping[int, StarSample] | None = None,
    displayed_avg: float | None = None,
    bootstrap_iterations: int = 1000,
    seed: int = 0,
    min_judged: int = 30,
    displayed_avg_warn_gap: float = 0.05,
    sens_spec: tuple[float, float] | None = None,
) -> RatingsResult:
    N = {s: int(star_counts.get(s, 0) or 0) for s in STARS}
    samples = dict(per_star) if per_star is not None else count_labels(labels_by_star or {})
    warnings: list[Warning_] = []
    sum_N = sum(N.values())
    if sum_N == 0:
        return RatingsResult(
            None, None, None, None, None, None, None, samples, dict.fromkeys(STARS),
            [Warning_("no_reviews", "이 상품에는 아직 리뷰가 없어요.", level="info")],
        )

    avg_all = sum(s * N[s] for s in STARS) / sum_N
    if displayed_avg is not None and abs(avg_all - displayed_avg) > displayed_avg_warn_gap:
        warnings.append(
            Warning_("displayed_avg_mismatch", f"쿠팡 표시 평균(★{displayed_avg:.2f})과 별점 분포로 계산한 평균(★{avg_all:.2f})이 달라요.")
        )

    h = {s: float(samples[s].human) for s in STARS}
    a = {s: float(samples[s].ai) for s in STARS}
    avg_human, ai_share, r_used, substituted, all_h_zero = _point_estimate(N, h, a)
    for s in substituted:
        warnings.append(Warning_("star_ratio_substituted", f"{s}점은 판정된 리뷰가 없어 전체 표본의 사람 비율로 대신 계산했어요.", star=s))
    for s in STARS:
        if N[s] > 0 and samples[s].judged < min_judged:
            warnings.append(Warning_("insufficient_sample", f"{s}점은 판정된 리뷰가 {samples[s].judged}개뿐이라 결과가 불안정할 수 있어요.", star=s))
    if all_h_zero:
        warnings.append(Warning_("no_human_reviews", "사람 리뷰로 판정된 리뷰가 없어 사람 리뷰 기준 별점을 계산하지 않았어요."))
        return RatingsResult(avg_all, None, None, ai_share, None, None, None, samples, r_used, warnings)
    if avg_human is None:
        warnings.append(Warning_("no_judged_reviews", "판정된 리뷰가 없어 사람 리뷰 기준 별점을 계산하지 않았어요."))
        return RatingsResult(avg_all, None, None, None, None, None, None, samples, r_used, warnings)

    ci_h, ci_d, ci_ai = _bootstrap(N, samples, bootstrap_iterations, seed, avg_all)
    corrected = None
    if sens_spec is not None:
        sens, spec = sens_spec
        r_corr = {}
        for s in STARS:
            if r_used[s] is None:
                continue
            r_corr[s] = 1.0 - rogan_gladen(1.0 - float(r_used[s] or 0.0), sens, spec)
        w = {s: N[s] * r for s, r in r_corr.items()}
        if sum(w.values()) > 0:
            corrected = {
                "method": "rogan_gladen",
                "sensitivity": sens,
                "specificity": spec,
                "avg_human": sum(s * x for s, x in w.items()) / sum(w.values()),
                "ai_share": 1.0 - sum(w.values()) / sum_N,
            }
    return RatingsResult(
        avg_all=avg_all,
        avg_human=avg_human,
        diff=avg_human - avg_all,
        ai_share=ai_share,
        avg_human_ci95=ci_h,
        diff_ci95=ci_d,
        ai_share_ci95=ci_ai,
        per_star=samples,
        r_used=r_used,
        warnings=warnings,
        corrected=corrected,
    )
