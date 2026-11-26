"""서비스 공통 예외. API·UI는 `code`로 상태와 안내 문구를 고른다."""

from __future__ import annotations


class RealstarError(Exception):
    code = "error"
    user_message = "문제가 생겨 요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요."

    def __init__(self, detail: str = "", **extra: object) -> None:
        super().__init__(detail or self.code)
        self.detail = detail
        self.extra = extra


class BlockedError(RealstarError):
    """사이트가 자동 접근을 거부했다(403, Access Denied, CAPTCHA, 연속 빈 결과).

    감지 즉시 수집을 중단하고 쿨다운에 들어간다. 우회를 시도하지 않는다(README 0-3).
    """

    code = "blocked"
    user_message = "지금은 쿠팡에서 정보를 가져올 수 없어요. 잠시 후 다시 시도하거나 저장된 결과를 확인해 주세요."

    def __init__(self, signal: str, detail: str = "", **extra: object) -> None:
        super().__init__(detail or signal, **extra)
        self.signal = signal


class CooldownActiveError(RealstarError):
    code = "blocked"
    user_message = BlockedError.user_message

    def __init__(self, until_iso: str) -> None:
        super().__init__(f"cooldown until {until_iso}")
        self.until_iso = until_iso


class ParserBrokenError(RealstarError):
    """셀렉터가 깨져 필수 필드 누락률이 임계값을 넘었다(README 5.2)."""

    code = "parser_broken"
    user_message = "쿠팡 화면 구조가 바뀌어 리뷰를 읽지 못했어요. 운영팀이 확인 중이에요."

    def __init__(self, page: str, failed_selectors: dict[str, float], detail: str = "") -> None:
        super().__init__(detail or f"{page}: {failed_selectors}")
        self.page = page
        self.failed_selectors = failed_selectors


class PageBudgetExceededError(RealstarError):
    code = "page_budget_exceeded"
    user_message = "오늘 수집할 수 있는 양을 모두 썼어요. 내일 다시 시도하거나 저장된 결과를 확인해 주세요."

    def __init__(self, scope: str, limit: int) -> None:
        super().__init__(f"{scope} page budget {limit} exceeded")
        self.scope = scope
        self.limit = limit


class ForbiddenAreaError(RealstarError):
    """로그인·장바구니·주문·개인 정보 페이지 접근 시도(README 0-3에서 금지)."""

    code = "forbidden_area"
    user_message = "공개 상품 페이지만 분석할 수 있어요."


class InvalidInputError(RealstarError):
    code = "invalid_input"
    user_message = "입력을 확인해 주세요."

    def __init__(self, detail: str, user_message: str | None = None) -> None:
        super().__init__(detail)
        if user_message:
            self.user_message = user_message


class ScraperBusyError(RealstarError):
    code = "scraper_busy"
    user_message = "지금 다른 분석의 리뷰를 수집하고 있어요. 잠시 후 다시 시도해 주세요."


class DetectorUnavailableError(RealstarError):
    code = "detector_unavailable"
    user_message = "AI 판별 모델을 사용할 수 없어요. 잠시 후 다시 시도해 주세요."

    def __init__(self, detail: str = "", user_message: str | None = None, **extra: object) -> None:
        super().__init__(detail, **extra)
        if user_message:
            self.user_message = user_message


class VisionUnavailableError(RealstarError):
    code = "vision_unavailable"
    user_message = "지금은 이미지 인식을 사용할 수 없어요. 링크나 상품명으로 검색해 주세요."


class CrawlerUnavailableError(RealstarError):
    """수집기(coupang_reviews.py)를 실행할 수 없다: 파일 없음, scrapling 미설치 등."""

    code = "crawler_unavailable"
    user_message = "리뷰 수집기를 실행할 수 없어요. 서버의 수집기 설치 상태를 확인해 주세요."

    def __init__(self, detail: str = "", user_message: str | None = None) -> None:
        super().__init__(detail)
        if user_message:
            self.user_message = user_message


class CrawlerFailedError(RealstarError):
    """수집기가 실행됐지만 도중에 실패했다. 원인 문구를 그대로 화면에 보여 준다."""

    code = "crawler_failed"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.user_message = f"리뷰를 수집하지 못했어요: {detail[:200]}"
