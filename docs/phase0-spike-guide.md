# Phase 0 수집 가능성 점검(spike) 가이드 — 오너 PC에서 수동 실행

이번 작업에서는 **실제 쿠팡 사이트에 접속하지 않았다.** 이유:
- 쿠팡 robots.txt가 자동 접근을 막고 있어 접속 여부는 오너가 정할 일이다(README 11, TBD-1).
- spike 대상 상품은 오너가 정해야 한다(Q5).
- 클라우드 서버 IP에서의 접속은 실제 사용 환경과 달라 결과가 대표성이 없다.

그래서 파서·셀렉터는 **합성 HTML 스냅샷**으로 개발·테스트했다(`service/tests/fixtures/html/`). 실제 화면 구조는 아래 절차로 확인해야 한다.

## 절차

```bash
cd service
python -m venv .venv && . .venv/bin/activate
pip install -e ".[api,worker,dev]"
cp .env.example .env            # REVIEW_PROVIDER=coupang, SCRAPER_HEADLESS=false 유지
# Chrome 설치 필요(Selenium Manager가 드라이버를 맞춰 받는다)

python -m realstar spike --per-star 100 \
  --url "<상품 링크 1>" --url "<상품 링크 2>" --url "<상품 링크 3>"
```

- 브라우저 창이 뜨고 3~7초 간격으로 천천히 움직인다. 로그인 창 등이 뜨면 손대지 말고 중단한다.
- 결과: `var/spike_report_*.json`(성공 여부, 페이지 수, 소요 시간, 별점별 수집 수, 차단 시점), `var/scrape_html/`(리뷰 영역 HTML 최근 200건).
- **차단되면 우회하지 않고 즉시 멈춘다**(60분 쿨다운). 반복되면 README 11장의 대안(브라우저 확장 방식)을 검토한다.

## spike 후 할 일

1. `var/scrape_html/`과 브라우저 개발자 도구로 실제 DOM을 확인하고 `packages/core/realstar/collectors/coupang/selectors.yaml`을 고친다. `version`을 올린다.
   - 리뷰가 별도 HTML 조각 URL로 로드되면 `review_mode: fragment`와 `urls.review_fragment`를 쓴다(같은 브라우저 세션, 같은 속도 규칙).
2. 실제 HTML을 `tests/fixtures/html/`에 저장하고(작성자 닉네임 등은 지운다) `tests/unit/test_parsers.py` 기대값을 실제 값으로 바꾼다.
3. 리포트 요약을 오너에게 공유한다: 상품별 성공 여부 / 페이지 수 / 소요 시간 / 차단 여부와 시점.
4. 일일 스모크 테스트(Phase 8): `python -m realstar smoke --url "<고정 상품 링크>"` → 실패 시 종료 코드 1(cron에서 알림 연결).

## 안전장치 요약 (구현됨)

| 규칙 | 구현 |
|---|---|
| 브라우저 1개, 전역 동시 수집 1개 | Celery `scrape` 큐 동시성 1 + Redis 분산 락 |
| 무작위 대기 3~7초 | `BrowserSession.human_delay` (페이지 이동·클릭 모두) |
| 분석당·일일 페이지 상한 | `SCRAPER_MAX_PAGES_PER_ANALYSIS`(80), `SCRAPER_MAX_PAGES_PER_DAY`(1500) |
| 차단 감지 → 즉시 중단·쿨다운 | 제목·본문 문구, CAPTCHA/챌린지 요소, 연속 빈 리뷰 영역 → `BlockedError` → 60분 쿨다운 |
| 공개 영역만 | 허용 URL 패턴 외 열지 않음, 로그인·장바구니·주문으로 이동되면 중단 |
| 작성자 정보 미저장 | 닉네임은 솔트 해시만, 학습용 내보내기에는 해시도 없음 |
| 우회 기능 없음 | stealth·프록시·UA 위조·CAPTCHA 풀이·재시도 강화 없음 |
| 셀렉터 깨짐 감지 | 필수 필드 누락률 > 20% → `ParserBrokenError`, `scrape_log`에 실패 셀렉터 기록 |
