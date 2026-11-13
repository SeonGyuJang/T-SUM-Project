from __future__ import annotations

from realstar.collectors.base import SearchCandidate
from realstar.resolver.scoring import (
    decide_auto,
    model_numbers,
    normalize_query,
    rank_candidates,
    specs,
)


def test_normalize_units_and_symbols() -> None:
    assert normalize_query("제주 삼다수  500 mL × 20개 [무료배송]") == "제주 삼다수 500ml x20개 무료배송"
    assert normalize_query("코카콜라 1.5 L") == "코카콜라 1.5l"
    assert normalize_query("Ｓｏｎｙ WH-1000XM5") == "sony wh-1000xm5"


def test_model_numbers() -> None:
    assert model_numbers("소니 WH-1000XM5 노이즈캔슬링") == {"wh1000xm5"}
    assert model_numbers("갤럭시S24 울트라 256GB") == {"s24"}
    assert model_numbers("삼다수 500ml 20개") == set()


def test_specs() -> None:
    assert specs("삼다수 500 mL x 20개") == {"500ml", "x20", "20개"}


def cand(pid: str, name: str, ad: bool = False) -> SearchCandidate:
    return SearchCandidate(product_id=pid, name=name, is_ad=ad)


def test_rank_model_number_dominates() -> None:
    cands = [
        cand("1", "소니 WH-1000XM4 무선 헤드폰"),
        cand("2", "소니 WH-1000XM5 무선 노이즈캔슬링 헤드폰 블랙"),
        cand("3", "무선 헤드폰 블루투스"),
    ]
    ranked = rank_candidates("소니 WH-1000XM5", cands)
    assert ranked[0].product_id == "2"
    assert (ranked[0].match_score or 0) > (ranked[1].match_score or 0) + 0.15


def test_ad_penalty() -> None:
    cands = [cand("1", "삼다수 500ml 20개", ad=True), cand("2", "삼다수 500ml 20개")]
    ranked = rank_candidates("삼다수 500ml 20개", cands)
    assert ranked[0].product_id == "2"


def test_decide_auto() -> None:
    def sc(*scores: float) -> list[SearchCandidate]:
        return [SearchCandidate(product_id=str(i), match_score=s) for i, s in enumerate(scores)]

    assert decide_auto(sc(0.9, 0.7), 0.85, 0.15)
    assert not decide_auto(sc(0.9, 0.8), 0.85, 0.15)
    assert not decide_auto(sc(0.8), 0.85, 0.15)
    assert decide_auto(sc(0.86), 0.85, 0.15)
    assert not decide_auto([], 0.85, 0.15)
