"""상품명 입력 → 쿠팡 검색 결과 후보 (README 5.1 (b), F2)."""

from __future__ import annotations

from realstar.collectors.base import ReviewProvider, SearchCandidate
from realstar.config import Settings
from realstar.errors import BlockedError, InvalidInputError
from realstar.resolver.models import ResolveResult, SearchCache
from realstar.resolver.scoring import decide_auto, normalize_query, rank_candidates


def search_candidates(
    query: str, provider: ReviewProvider, cache: SearchCache, settings: Settings
) -> tuple[list[SearchCandidate], bool]:
    """검색 결과는 질의 기준으로 캐시한다(TTL). 반환: (후보, 캐시 사용 여부)."""
    qn = normalize_query(query)
    cached = cache.get(qn, settings.cache_ttl_hours)
    if cached is not None:
        return cached, True
    results = provider.search(query)
    if results:  # 빈 결과(일시 오류·화면 변경)는 캐시하지 않는다
        cache.put(qn, results)
    return results, False


def resolve_by_name(
    query: str,
    provider: ReviewProvider,
    cache: SearchCache,
    settings: Settings,
    *,
    brand: str | None = None,
    force_selection: bool = False,
    input_type: str = "query",
) -> ResolveResult:
    query = (query or "").strip()
    if len(normalize_query(query)) < 2:
        raise InvalidInputError("query too short", "상품명을 두 글자 이상 입력해 주세요.")
    try:
        raw, cached = search_candidates(query, provider, cache, settings)
    except BlockedError:
        return ResolveResult(
            status="blocked", input_type=input_type, query=query,  # type: ignore[arg-type]
            message="쿠팡 검색 페이지가 자동 접근을 막았어요. 상품 링크를 붙여 넣으면 바로 분석할 수 있어요.",
        )
    ranked = rank_candidates(query, raw, brand=brand)
    top = ranked[: settings.resolve_max_candidates]
    if not top:
        return ResolveResult(
            status="not_found", input_type=input_type, query=query, cached=cached,  # type: ignore[arg-type]
            message="검색 결과가 없어요. 상품명을 조금 더 간단히 입력해 보세요."
            + (" (지금 서버는 예시 데이터 모드예요: service/.env 의 REVIEW_PROVIDER=crawler)" if settings.review_provider == "fixture" else ""),
        )
    auto = not force_selection and decide_auto(ranked, settings.resolve_auto_top1, settings.resolve_auto_gap)
    return ResolveResult(
        status="resolved" if auto else "needs_selection",
        candidates=top[:1] if auto else top,
        input_type=input_type,  # type: ignore[arg-type]
        query=query,
        cached=cached,
    )
