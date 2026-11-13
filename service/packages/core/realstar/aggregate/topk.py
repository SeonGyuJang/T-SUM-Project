"""별점별 사람 리뷰 Top 5 선정 (README 5.5).

1. 후보: label == human 이고 len_chars ≥ TOP_MIN_CHARS(40)
2. p_human 내림차순
3. 같은 dup_group_id에서는 1개만
4. 동률(차이 0.01 이내)이면 사진이 있거나 길이가 긴 리뷰 우선
5. 후보가 5개 미만이면 있는 만큼만 (부족 안내는 호출자가 표시)
"""

from __future__ import annotations

from dataclasses import dataclass, field

TIE_EPS = 0.01


@dataclass
class TopCandidate:
    review_id: str
    star: int
    p_human: float
    label: str
    len_chars: int
    has_photo: bool
    dup_group_id: str | None
    text: str
    title: str | None = None
    created_at: str | None = None
    reason_tags: list[str] = field(default_factory=list)


def select_top_k(cands: list[TopCandidate], k: int = 5, min_chars: int = 40) -> list[TopCandidate]:
    pool = [c for c in cands if c.label == "human" and c.len_chars >= min_chars]
    picked: list[TopCandidate] = []
    used_groups: set[str] = set()
    while pool and len(picked) < k:
        pool = [c for c in pool if c.dup_group_id is None or c.dup_group_id not in used_groups]
        if not pool:
            break
        best_p = max(c.p_human for c in pool)
        tied = [c for c in pool if best_p - c.p_human <= TIE_EPS + 1e-12]
        chosen = max(tied, key=lambda c: (c.has_photo, c.len_chars, c.p_human, c.review_id))
        picked.append(chosen)
        if chosen.dup_group_id is not None:
            used_groups.add(chosen.dup_group_id)
        pool = [c for c in pool if c is not chosen]
    return picked
