"""실제 Chrome으로 수집기를 시험하기 위한 로컬 모의 사이트(쿠팡 아님).

selectors.yaml 초안 구조를 따르는 상품 페이지에 JavaScript로 최신순 정렬·별점 필터·페이지 넘김을 구현했다.
실제 쿠팡 화면을 흉내 낸 것이 아니라, 수집기의 화면 조작·대기·파싱 로직이 실제 브라우저에서 도는지 확인하는 용도다.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

COUNTS = {5: 23, 4: 12, 3: 0, 2: 4, 1: 6}
PAGE_SIZE = 5


def reviews(star: int) -> list[dict]:
    return [{"id": f"{star}{i:03d}", "star": star, "date": f"2026.{10 - i // 10:02d}.{28 - i % 28:02d}",
             "text": f"{star}점 리뷰 {i}번째 본문이에요. 배송 빠르고 포장도 괜찮았어요 ㅎㅎ", "author": f"구매자{i}"}
            for i in range(COUNTS[star])]


PRODUCT = """<!doctype html><html><head><meta charset="utf-8"><title>[모의] 테스트 상품 - 로컬</title></head><body>
<div class="prod-buy-header"><h2 class="prod-buy-header__title">[모의] 테스트 상품</h2>
<span class="rating-star-num" style="width: 86%"></span><span class="count">{total}개 상품평</span></div>
<div style="height:1500px">상세 설명</div>
<div id="sdpReview" class="sdp-review">
  <button class="sdp-review__article__order__sort__best-btn">랭킹순</button>
  <button class="sdp-review__article__order__sort__newest-btn">최신순</button>
  <div class="sdp-review__article__order__star__all">전체 별점</div>
  <div class="sdp-review__article__order__star__list">{rows}</div>
  <section class="js_reviewArticleListContainer"></section>
  <div class="sdp-review__article__page"></div>
</div>
<script>
const DATA = {data};
let state = {{star: null, page: 1, latest: false}};
function render() {{
  setTimeout(() => {{   // 실제 사이트처럼 비동기로 늦게 그린다
    let list = state.star ? DATA[state.star] : [].concat(...Object.values(DATA));
    if (!state.latest) list = list.slice().reverse();
    const pages = Math.ceil(list.length / {ps});
    const items = list.slice((state.page - 1) * {ps}, state.page * {ps});
    document.querySelector('.js_reviewArticleListContainer').innerHTML = items.length ? items.map(r =>
      `<article class="sdp-review__article__list" data-review-id="${{r.id}}">
        <span class="sdp-review__article__list__info__user__name">${{r.author}}</span>
        <div class="sdp-review__article__list__info__product-info__star-orange" data-rating="${{r.star}}"></div>
        <div class="sdp-review__article__list__info__product-info__reg-date">${{r.date}}</div>
        <div class="sdp-review__article__list__review__content">${{r.text}}<br>${{state.latest ? '최신순' : '랭킹순'}}</div>
      </article>`).join('') : '<div class="sdp-review__article__no-review">등록된 상품평이 없습니다.</div>';
    document.querySelector('.sdp-review__article__page').innerHTML =
      Array.from({{length: pages}}, (_, i) => `<button class="sdp-review__article__page__num" data-page="${{i + 1}}">${{i + 1}}</button>`).join('');
    document.querySelectorAll('.sdp-review__article__page__num').forEach(b => b.onclick = () => {{ state.page = +b.dataset.page; render(); }});
  }}, 300);
}}
document.querySelector('.sdp-review__article__order__sort__newest-btn').onclick = () => {{ state.latest = true; state.page = 1; render(); }};
document.querySelectorAll('.sdp-review__article__order__star__list__item').forEach(el => el.onclick = () => {{
  state.star = +el.dataset.rating; state.page = 1; render(); }});
render();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a: object) -> None: ...

    def _send(self, html: str, code: int = 200) -> None:
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        if u.path.startswith("/vp/products/"):
            rows = "".join(
                f'<div class="sdp-review__article__order__star__list__item" data-rating="{s}">'
                f'<span class="sdp-review__article__order__star__list__item__count">{c}</span></div>' for s, c in COUNTS.items())
            data = json.dumps({s: reviews(s) for s in COUNTS})
            self._send(PRODUCT.format(total=sum(COUNTS.values()), rows=rows, data=data, ps=PAGE_SIZE))
        elif u.path.startswith("/np/search"):
            q = parse_qs(u.query).get("q", [""])[0]
            self._send(f'<html><body><ul id="productList"><li class="search-product"><a href="/vp/products/77?itemId=1">'
                       f'<div class="name">[모의] {q} 상품</div><strong class="price-value">12,900</strong></a></li></ul></body></html>')
        elif u.path == "/blocked":
            self._send("<html><head><title>Access Denied</title></head><body>Access Denied</body></html>", 403)
        else:
            self._send("<html><body>not found</body></html>", 404)


def start() -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"
