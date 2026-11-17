"""가짜 StealthySession: 쿠팡 /next-api/review 응답 모양을 흉내 낸다.

환경 변수
  FAKE_COUPANG_COUNTS  별점별 전체 리뷰 수 JSON (기본 {"5": 42, "4": 13, "3": 5, "2": 0, "1": 3})
  FAKE_COUPANG_BLOCK   "1"이면 상품 페이지가 HTTP 403
  FAKE_COUPANG_SEARCH  검색 결과 HTML 파일 경로
  FAKE_COUPANG_DELAY   API 응답마다 기다릴 초 (진행 화면 확인용, 기본 0)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

NAME = "가짜 비타민C 1000 120정"


def _counts() -> dict[int, int]:
    raw = json.loads(os.environ.get("FAKE_COUPANG_COUNTS") or '{"5": 42, "4": 13, "3": 5, "2": 0, "1": 3}')
    return {int(k): int(v) for k, v in raw.items()}


def _review(pid: str, star: int, i: int) -> dict[str, Any]:
    return {
        "reviewId": int(f"{star}{i:05d}"),
        "rating": star,
        "headline": f"{star}점 후기 {i}",
        "content": f"{star}점을 준 이유는 이렇습니다. 실제로 써 보니 {'좋았' if star >= 4 else '아쉬웠'}어요. 리뷰 번호 {i}.",
        "reviewAt": 1793000000000 - i * 86400000,
        "itemName": "120정, 1개",
        "displayName": "홍길동",
        "attachments": [{"imgSrcThumbnail": "image2/PRODUCTREVIEW/x.jpg"}] if i % 4 == 0 else [],
    }


class _Mouse:
    def wheel(self, *_: Any) -> None:
        return None


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.mouse = _Mouse()
        self.pid = (urlparse(url).path.rstrip("/").split("/") or [""])[-1]

    def wait_for_timeout(self, _ms: int) -> None:
        return None

    def reload(self, **_: Any) -> None:
        return None

    def goto(self, url: str, **_: Any) -> FakeResponse:
        self.url = url
        return FakeResponse(url, 200)

    def wait_for_selector(self, *_: Any, **__: Any) -> None:
        return None

    def content(self) -> str:
        path = os.environ.get("FAKE_COUPANG_SEARCH")
        return open(path, encoding="utf-8").read() if path else "<html></html>"

    def evaluate(self, js: str, arg: Any = None) -> Any:
        if arg is None:  # og:title / og:image
            return {"title": f"{NAME} | 쿠팡", "image": "//thumbnail.coupangcdn.com/fake.jpg"}
        time.sleep(float(os.environ.get("FAKE_COUPANG_DELAY") or 0))
        q = {k: v[0] for k, v in parse_qs(urlparse(arg).query).items()}
        counts = _counts()
        star = int(q["ratings"]) if q.get("ratings") else None
        page, size = int(q.get("page", 1)), int(q.get("size", 10))
        total = counts.get(star, 0) if star else sum(counts.values())
        if star:
            pool = [_review(self.pid, star, i) for i in range(counts.get(star, 0))]
        else:
            pool = [_review(self.pid, s, i) for s in (5, 4, 3, 2, 1) for i in range(counts.get(s, 0))]
        items = pool[(page - 1) * size: page * size]
        body = {
            "rCode": "RET0000",
            "rData": {
                "paging": {"totalCount": total, "currentPage": page},
                "ratingSummaryTotal": {
                    "ratingAverage": round(sum(s * n for s, n in counts.items()) / max(1, sum(counts.values())), 1),
                    "ratingSummaries": [{"rating": s, "count": counts.get(s, 0)} for s in (5, 4, 3, 2, 1)],
                },
                "paging_contents": items,
            },
        }
        return {"status": 200, "text": json.dumps(body, ensure_ascii=False)}


class _Sel:
    def __init__(self, v: str | None) -> None:
        self.v = v

    def get(self) -> str | None:
        return self.v


class FakeResponse:
    def __init__(self, url: str, status: int) -> None:
        self.url = url
        self.status = status

    def css(self, selector: str) -> _Sel:
        return _Sel(f"{NAME} | 쿠팡" if "og:title" in selector else None)


class StealthySession:
    def __init__(self, **kw: Any) -> None:
        self.kw = kw

    def __enter__(self) -> StealthySession:
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def fetch(self, url: str, page_action: Any = None, **_: Any) -> FakeResponse:
        if os.environ.get("FAKE_COUPANG_BLOCK") == "1":
            return FakeResponse(url, 403)
        final = url.replace("https://link.coupang.com/a/fake", "https://www.coupang.com/vp/products/7777777777?itemId=1")
        page = FakePage(final)
        if page_action:
            page_action(page)
        return FakeResponse(final, 200)
