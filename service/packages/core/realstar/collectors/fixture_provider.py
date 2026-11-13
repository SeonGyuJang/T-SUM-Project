"""FixtureProvider: 저장된 JSON으로 동작하는 ReviewProvider (개발·테스트 필수, README 5.2).

디렉터리 구조 (`FIXTURE_DIR`):
  products/{product_id}.json   {"meta": ProductMeta, "reviews": [RawReview...], "simulate": {...}}
  search/{query_norm}.json     {"candidates": [SearchCandidate...]}
  short_links.json             {"https://link.coupang.com/a/xxx": "https://www.coupang.com/vp/products/..."}

simulate (선택):
  {"blocked_at_star": 3}       해당 별점 수집 중 BlockedError
  {"parser_broken": true}      ParserBrokenError
  {"page_size": 10}            진행률 콜백 단위
"""

from __future__ import annotations

import json
from pathlib import Path

from realstar.collectors.base import (
    CollectProgress,
    ProductMeta,
    ProgressCallback,
    RawReview,
    SearchCandidate,
    SortOrder,
)
from realstar.errors import BlockedError, InvalidInputError, ParserBrokenError

FIXTURE_SELECTORS_VERSION = "fixture"


class FixtureProvider:
    selectors_version = FIXTURE_SELECTORS_VERSION

    def __init__(self, fixture_dir: Path) -> None:
        self.dir = Path(fixture_dir)
        self._pages = 0

    @property
    def pages_loaded(self) -> int:
        return self._pages

    def _load_product(self, product_id: str) -> dict:  # type: ignore[type-arg]
        path = self.dir / "products" / f"{product_id}.json"
        if not path.exists():
            raise InvalidInputError(f"fixture product {product_id} not found", "상품을 찾지 못했어요. 링크를 확인해 주세요.")
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def get_product_meta(self, product_id: str) -> ProductMeta:
        data = self._load_product(product_id)
        self._pages += 1
        if data.get("simulate", {}).get("parser_broken"):
            raise ParserBrokenError("product", {"product.name": 1.0})
        return ProductMeta.model_validate(data["meta"])

    def get_reviews(
        self,
        product_id: str,
        star: int,
        limit: int,
        sort: SortOrder = "latest",
        on_progress: ProgressCallback | None = None,
    ) -> list[RawReview]:
        data = self._load_product(product_id)
        sim = data.get("simulate", {})
        page_size = int(sim.get("page_size", 10))
        reviews = [RawReview.model_validate(r) for r in data.get("reviews", []) if int(r["star"]) == star]
        if sort == "latest":
            reviews.sort(key=lambda r: r.created_at or "", reverse=True)
        out: list[RawReview] = []
        for i in range(0, min(limit, len(reviews)), page_size):
            self._pages += 1
            out.extend(reviews[i : min(i + page_size, limit)])
            if sim.get("blocked_at_star") == star and len(out) >= page_size:
                raise BlockedError("fixture_simulated", f"simulated block at star {star}")
            if on_progress:
                on_progress(CollectProgress(star=star, collected=len(out), target=min(limit, len(reviews)), pages_loaded=self._pages))
        return out

    def search(self, query: str) -> list[SearchCandidate]:
        from realstar.resolver.scoring import normalize_query

        self._pages += 1
        path = self.dir / "search" / f"{normalize_query(query)}.json"
        if not path.exists():
            # 등록된 모든 검색 fixture에서 상품명 부분 일치로 후보를 모은다
            out: list[SearchCandidate] = []
            for p in sorted((self.dir / "search").glob("*.json")):
                for c in json.loads(p.read_text(encoding="utf-8")).get("candidates", []):
                    cand = SearchCandidate.model_validate(c)
                    hit = any(tok in normalize_query(cand.name or "") for tok in normalize_query(query).split())
                    if hit and all(x.product_id != cand.product_id for x in out):
                        out.append(cand)
            return out
        return [SearchCandidate.model_validate(c) for c in json.loads(path.read_text(encoding="utf-8"))["candidates"]]

    def resolve_short_url(self, url: str) -> str:
        self._pages += 1
        mapping_path = self.dir / "short_links.json"
        mapping = json.loads(mapping_path.read_text(encoding="utf-8")) if mapping_path.exists() else {}
        if url not in mapping:
            raise InvalidInputError(f"unknown short link {url}", "링크를 열지 못했어요. 상품 페이지 주소를 직접 붙여 넣어 주세요.")
        return str(mapping[url])

    def close(self) -> None:
        return None
