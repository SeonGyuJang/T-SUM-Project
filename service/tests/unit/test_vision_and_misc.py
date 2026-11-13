from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from realstar.collectors.base import RawReview, SearchCandidate
from realstar.collectors.export_training import export_training_batch, filter_before, read_targets
from realstar.collectors.fixture_provider import FixtureProvider
from realstar.config import Settings
from realstar.detection import preprocess
from realstar.errors import InvalidInputError, ScraperBusyError
from realstar.resolver.image import load_image, resolve_by_image
from realstar.resolver.models import MemorySearchCache, ResolveResult
from realstar.resolver.name_search import resolve_by_name
from realstar.state.store import Cooldown, LocalStateStore
from realstar.vision.ocr import OcrLine
from realstar.vision.product_text_heuristics import guess_product_text, is_ui_line
from realstar.vision.vlm import DisabledVlm, parse_vlm_json
from tests.conftest import JSON_DIR


def png_bytes(size: tuple[int, int] = (400, 300), exif: bool = False) -> bytes:
    img = Image.new("RGB", size, "white")
    buf = io.BytesIO()
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "SecretCam"  # Make
        img.save(buf, "JPEG", exif=ex)
    else:
        img.save(buf, "PNG")
    return buf.getvalue()


def test_load_image_strips_exif_and_limits_size() -> None:
    img = load_image(png_bytes((4000, 1000), exif=True), 10_000_000, 2000)
    assert max(img.size) == 2000
    assert not img.info.get("exif") and len(img.getexif()) == 0


def test_load_image_rejects() -> None:
    with pytest.raises(InvalidInputError):
        load_image(b"", 100, 100)
    with pytest.raises(InvalidInputError):
        load_image(b"not an image", 100_000, 100)
    with pytest.raises(InvalidInputError):
        load_image(png_bytes(), 10, 100)


def L(text: str, y: float, h: float, x: float = 10, conf: float = 0.95) -> OcrLine:
    return OcrLine(text, (x, y, x + 300, y + h), conf)


COUPANG_CAPTURE = [
    L("쿠팡", 5, 20),
    L("로켓배송", 40, 14),
    L("소니 WH-1000XM5 무선 노이즈캔슬링 헤드폰", 80, 30),
    L("블랙", 115, 30),
    L("15%", 160, 16),
    L("389,000원", 180, 24),
    L("장바구니", 400, 18),
    L("바로구매", 400, 18, x=320),
]


def test_heuristics_pick_product_line() -> None:
    g = guess_product_text(COUPANG_CAPTURE, 600)
    assert g.product_name and g.product_name.startswith("소니 WH-1000XM5")
    assert g.product_name.endswith("블랙")  # 두 줄로 나뉜 상품명 합치기
    assert g.model_number == "wh1000xm5"
    assert g.is_coupang_screenshot and g.has_text
    assert g.confidence > 0.45


def test_ui_lines() -> None:
    assert is_ui_line("로켓배송")
    assert is_ui_line("389,000원")
    assert is_ui_line("15%")
    assert not is_ui_line("제주 삼다수 2L 6개")


def test_no_text() -> None:
    g = guess_product_text([], 600)
    assert g.query is None and not g.has_text


class FakeOcr:
    name = "fake"
    available = True

    def __init__(self, lines: list[OcrLine]) -> None:
        self.lines = lines

    def read(self, image: Image.Image) -> list[OcrLine]:
        return self.lines


class FakeVlm:
    available = True

    def extract(self, image: Image.Image) -> dict:  # type: ignore[type-arg]
        return {"has_text": False, "search_queries": ["무선 청소기 A100", "핸디 청소기"], "confidence": 0.4, "category_guess": "청소기"}


def _search_fn(settings: Settings):  # type: ignore[no-untyped-def]
    provider = FixtureProvider(JSON_DIR)
    cache = MemorySearchCache()

    def search(q: str, brand: str | None, force: bool) -> ResolveResult:
        return resolve_by_name(q, provider, cache, settings, brand=brand, force_selection=force, input_type="image")

    return search


def test_image_resolve_with_ocr(settings: Settings) -> None:
    lines = [L("[예시] 무선 청소기 A100 화이트", 80, 30), L("189,000원", 130, 20)]
    res = resolve_by_image(png_bytes(), _search_fn(settings), settings, FakeOcr(lines), DisabledVlm())
    assert res.input_type == "image"
    assert res.candidates and res.candidates[0].product_id == "1000000001"
    assert res.extracted and res.extracted["product_name"].startswith("[예시] 무선 청소기")


def test_image_without_text_uses_vlm_and_forces_selection(settings: Settings) -> None:
    res = resolve_by_image(png_bytes(), _search_fn(settings), settings, FakeOcr([]), FakeVlm())
    assert res.status == "needs_selection"
    assert res.extracted and res.extracted["vlm_used"]


def test_image_without_text_no_vlm(settings: Settings) -> None:
    res = resolve_by_image(png_bytes(), _search_fn(settings), settings, FakeOcr([]), DisabledVlm())
    assert res.status == "not_found" and res.message


def test_parse_vlm_json() -> None:
    d = parse_vlm_json('설명입니다 {"has_text": true, "product_name": "삼다수", "confidence": "0.7", "search_queries": ["a","b","c","d"]} 끝')
    assert d and d["confidence"] == 0.7 and d["search_queries"] == ["a", "b", "c"]
    assert parse_vlm_json("no json") is None


def test_name_search_auto_and_selection(settings: Settings) -> None:
    provider = FixtureProvider(JSON_DIR)
    cache = MemorySearchCache()
    r = resolve_by_name("무선 청소기 A100", provider, cache, settings)
    assert r.status == "resolved" and r.candidates[0].product_id == "1000000001"
    r2 = resolve_by_name("텀블러", provider, cache, settings)
    assert r2.status == "needs_selection" and 2 <= len(r2.candidates) <= 5
    pages = provider.pages_loaded
    r3 = resolve_by_name("텀블러", provider, cache, settings)
    assert r3.cached and provider.pages_loaded == pages  # 검색 캐시
    r4 = resolve_by_name("존재하지않는상품명", provider, cache, settings)
    assert r4.status == "not_found"
    with pytest.raises(InvalidInputError):
        resolve_by_name("a", provider, cache, settings)


def test_local_state_store(tmp_path: Path) -> None:
    st = LocalStateStore(tmp_path)
    st.set("k", "v", ttl_sec=100)
    assert st.get("k") == "v"
    assert st.incr("c") == 1 and st.incr("c", 2) == 3
    with st.lock("L", timeout_sec=0.1), pytest.raises(ScraperBusyError), st.lock("L", timeout_sec=0.3):
        pass
    with st.lock("L", timeout_sec=0.1):
        pass  # 해제 후 다시 획득 가능
    st.set("e", "x", ttl_sec=1)
    assert st.ttl("e") in (0, 1)


def test_cooldown(tmp_path: Path) -> None:
    cd = Cooldown(LocalStateStore(tmp_path), 60)
    assert cd.status() is None
    cd.start("empty_streak")
    st = cd.status()
    assert st and st["reason"] == "empty_streak"
    cd.clear()
    assert cd.status() is None


def test_preprocess_passthrough_when_model_missing() -> None:
    if preprocess.model_preprocess_available():
        pytest.skip("realstar_model 설치됨")
    c = preprocess.clean("제목", "본문 ㅋㅋ")
    assert c.source == "passthrough" and c.clean_text == "제목\n본문 ㅋㅋ" and c.len_chars == len("제목\n본문 ㅋㅋ")
    groups, src = preprocess.assign_dup_groups(["같은 글", "같은  글", "다른 글"])
    assert src == "exact_only" and groups[0] == groups[1] and groups[0] is not None and groups[2] is None


def test_export_training(tmp_path: Path) -> None:
    targets_file = tmp_path / "targets.txt"
    targets_file.write_text("# 주석\n1000000002,주방용품\n")
    out_path, n, outcome = export_training_batch(
        FixtureProvider(JSON_DIR), read_targets(targets_file), tmp_path / "out", batch="t1", cutoff="2026-03-01", per_star_limit=3
    )
    rows = [json.loads(x) for x in out_path.read_text().splitlines()]
    assert outcome == "ok" and n == len(rows) > 0
    assert all(r["created_at"] < "2026-03-01" for r in rows)
    assert set(rows[0]) == {"review_id", "product_id", "category", "product_name", "star", "title", "content", "created_at",
                            "has_photo", "helpful_count", "collected_at", "source", "scraper_version"}
    assert "author_hash" not in rows[0] and rows[0]["category"] == "주방용품"
    per_star: dict[int, int] = {}
    for r in rows:
        per_star[r["star"]] = per_star.get(r["star"], 0) + 1
    assert max(per_star.values()) <= 3


def test_filter_before() -> None:
    rs = [RawReview(review_id=str(i), product_id="p", star=5, content="x", created_at=d) for i, d in enumerate(["2022-11-29", "2022-11-30", None, "2021-01-01"])]
    assert [r.review_id for r in filter_before(rs, "2022-11-30", 10)] == ["0", "3"]


def test_search_candidate_roundtrip() -> None:
    c = SearchCandidate(product_id="1", name="a", price=100)
    assert SearchCandidate.model_validate(c.model_dump()) == c
