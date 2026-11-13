from __future__ import annotations

from realstar.aggregate.topk import TopCandidate, select_top_k


def c(rid: str, p: float, *, label: str = "human", n: int = 60, photo: bool = False, dup: str | None = None) -> TopCandidate:
    return TopCandidate(review_id=rid, star=5, p_human=p, label=label, len_chars=n, has_photo=photo, dup_group_id=dup, text="x" * n)


def test_filters_label_and_length() -> None:
    got = select_top_k([c("a", 0.99, label="ai"), c("b", 0.98, n=39), c("c", 0.90), c("d", 0.80, label="uncertain")], k=5, min_chars=40)
    assert [x.review_id for x in got] == ["c"]


def test_sorted_by_p_human() -> None:
    got = select_top_k([c("a", 0.7), c("b", 0.9), c("c", 0.8), c("d", 0.95), c("e", 0.6), c("f", 0.5)])
    assert [x.review_id for x in got] == ["d", "b", "c", "a", "e"]


def test_one_per_dup_group() -> None:
    got = select_top_k([c("a", 0.99, dup="g1"), c("b", 0.98, dup="g1"), c("c", 0.90)])
    assert [x.review_id for x in got] == ["a", "c"]


def test_tie_prefers_photo_then_length() -> None:
    got = select_top_k([c("a", 0.950, n=50), c("b", 0.945, n=200), c("c", 0.942, n=60, photo=True), c("d", 0.90)], k=3)
    assert [x.review_id for x in got] == ["c", "b", "a"]


def test_not_tied_beyond_eps() -> None:
    got = select_top_k([c("a", 0.95, n=50), c("b", 0.93, n=300, photo=True)], k=2)
    assert [x.review_id for x in got] == ["a", "b"]


def test_fewer_than_k() -> None:
    assert len(select_top_k([c("a", 0.9), c("b", 0.8)], k=5)) == 2
    assert select_top_k([], k=5) == []
