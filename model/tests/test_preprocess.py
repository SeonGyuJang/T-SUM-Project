from realstar_model.preprocess import clean_review, length_bucket
from realstar_model.preprocess.dedup import assign_dup_groups


def test_contract_fields_and_cash_event_removed() -> None:
    r = clean_review(title="좋아요", content="본 리뷰는 쿠팡캐시를 지급받기 위해 작성한 것입니다. 배송 빨라요 ㅋㅋ")
    assert r.is_cash_event and "쿠팡캐시" not in r.clean_text and "ㅋㅋ" in r.clean_text  # 보존 규칙(4.4-4)
    assert r.text_for_model == f"좋아요 / {r.clean_text}" and r["len_chars"] == len(r.clean_text)


def test_newline_zero_width_and_nfc() -> None:
    r = clean_review(None, "첫 줄\n둘째​ 줄\r\n\n셋째   줄 😀")
    assert r.newline_count == 3 and r.zw_count == 1 and "\n" not in r.clean_text and "  " not in r.clean_text
    assert "😀" in r.clean_text


def test_sponsored_flag() -> None:
    r = clean_review(None, "업체로부터 제품을 제공받아 솔직하게 작성한 후기입니다. 향이 좋아요")
    assert r.is_sponsored and r.clean_text.startswith("향이 좋아요")


def test_length_bucket_edges() -> None:
    assert (length_bucket(29), length_bucket(30), length_bucket(99), length_bucket(100)) == ("S", "M", "M", "L")


def test_dedup_groups() -> None:
    g = assign_dup_groups(["배송 빠르고 좋아요 재구매합니다", "배송 빠르고 좋아요 재구매합니다!", "완전히 다른 리뷰예요 별로"])
    assert g[0] == g[1] is not None and g[2] is None
