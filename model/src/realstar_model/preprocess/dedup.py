"""근접 중복 묶기 (MODEL_DEV.md 4.4-7). 삭제하지 않고 그룹 ID만 돌려준다. service가 상품 안 리뷰에 쓴다."""

from __future__ import annotations

import hashlib
import re


def _shingles(text: str, k: int = 5) -> set[str]:
    t = re.sub(r"\s+", " ", text or "").strip()
    return {t[i:i + k] for i in range(max(1, len(t) - k + 1))} if t else set()


def assign_dup_groups(texts: list[str], threshold: float = 0.9) -> list[str | None]:
    """완전 중복 + 5-gram 문자 Jaccard ≥ threshold 인 근접 중복을 같은 그룹으로. 단독이면 None.

    상품 하나(최대 수백 건) 규모를 가정한 O(n²) 구현. 데이터셋 전체에는 쓰지 않는다.
    """
    n = len(texts)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    sh = [_shingles(t) for t in texts]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = sh[i], sh[j]
            if not a or not b:
                continue
            if len(a & b) / len(a | b) >= threshold:
                parent[find(j)] = find(i)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out: list[str | None] = [None] * n
    for root, idx in groups.items():
        if len(idx) > 1:
            gid = "dup_" + hashlib.sha1(re.sub(r"\s+", " ", texts[root]).encode("utf-8")).hexdigest()[:12]
            for i in idx:
                out[i] = gid
    return out
