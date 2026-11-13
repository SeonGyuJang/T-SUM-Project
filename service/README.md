# service/ — 리얼별점 서비스 (모델 외 전부)

홈페이지, API, 비동기 워커, 쿠팡 수집기(Selenium + BeautifulSoup), 이미지 판독(OCR/VLM), 별점 재계산·Top 5, 모델 연동 어댑터.
AI 탐지 모델 자체는 `model/`(`realstar_model` 패키지) 담당이다. 연결 방법: [`docs/model-integration.md`](../docs/model-integration.md).

## 구성

```
service/
├── packages/core/realstar/      # 파이썬 코어 (python -m realstar)
│   ├── collectors/              # base.py, fixture_provider.py, export_training.py
│   │   └── coupang/             # browser.py, block_detector.py, search_page.py, product_page.py,
│   │                            # review_page.py, provider.py, selectors.yaml
│   ├── resolver/                # url.py, name_search.py, image.py, scoring.py
│   ├── vision/                  # ocr.py, vlm.py, product_text_heuristics.py, ui_phrases.yaml
│   ├── aggregate/               # stats.py (README 5.4), topk.py (5.5)
│   ├── detection/               # backends.py (realstar_model·HTTP·dummy), preprocess.py (모델 전처리 어댑터)
│   ├── pipeline/                # analysis.py (수집→탐지→집계), service.py (API·CLI 공용), result_schema.py (5.7)
│   ├── db/                      # SQLAlchemy 모델 (5.9), repository
│   ├── state/                   # 쿨다운·일일 상한·분산 락 (Redis / 로컬 파일)
│   └── cli.py
├── apps/
│   ├── api/                     # FastAPI  (uvicorn --factory realstar_api.main:create_app)
│   ├── worker/                  # Celery: scrape 큐(동시성 1) / detect 큐
│   ├── detector_server/         # /predict, /health (realstar_model 래퍼)
│   └── web/                     # Next.js 홈페이지 (섹션 14)
├── migrations/                  # Alembic
├── docker-compose.yml           # Dockerfile은 저장소 루트(Dockerfile.backend/.scraper, Heroku 빌드 컨텍스트 때문)
└── tests/                       # unit / integration / contract, fixtures(html·json)
```

## 내 PC에서 실제 수집 + 웹페이지 확인

단계별 안내(설치 → 수집 점검 → 웹 실행, macOS·Windows): **[`docs/local-run-guide.md`](../docs/local-run-guide.md)**

```bash
cd service && cp .env.local.example .env                     # 실제 쿠팡 수집 + 더미 판별기 + 단일 프로세스
python -m realstar spike --per-star 10 --url "<상품 링크>"     # 수집 점검 (Chrome 창이 뜸)
uvicorn --factory realstar_api.main:create_app --port 8000    # API
cd apps/web && npm run dev                                    # 홈페이지 → http://localhost:3000
```

## 빠른 시작 1 — 백엔드 없이 홈페이지만 (목업·발표 모드)

```bash
cd service/apps/web
npm ci
npm run dev:mock    # MSW 목업 API (5.7 스키마)
npm run dev:demo    # 발표 모드: 저장된 예시 결과만, 네트워크 없음
```
목업 모드에서 상태 화면 확인용 링크: `…/vp/products/9000000001`(차단), `…/vp/products/9000000002`(화면 구조 변경 오류).

## 빠른 시작 2 — 전체 흐름 (Redis·Postgres 없이, 실제 쿠팡 접속 없이)

```bash
cd service
python -m venv .venv && . .venv/bin/activate
pip install -e ".[api,worker,dev]"
export REVIEW_PROVIDER=fixture DETECTOR_MODE=dummy TASK_BACKEND=inline \
       SCRAPER_DELAY_MIN_SEC=0 SCRAPER_DELAY_MAX_SEC=0 OCR_ENGINE=none
python -m realstar analyze --url "https://www.coupang.com/vp/products/1000000001"   # CLI로 결과 JSON
uvicorn --factory realstar_api.main:create_app --port 8000                          # API
cd apps/web && npm run dev                                                           # 웹 (live 모드)
```
`dummy` 판별기 결과에는 "개발용 결과" 경고가 붙는다. fixture 상품: `1000000001`(README 5.4 고정 예제), `1000000002`(표본 부족),
`1000000003`(차단 모의), `1000000004`(리뷰 없음), `1000000005`(셀렉터 깨짐 모의), 단축 링크 `https://link.coupang.com/a/demo01`, 검색어 `텀블러`.

## Heroku 배포

도메인 없이 Heroku에 배포한다(백엔드 container 앱 + 홈페이지 Node 앱). 단계별 명령·주의점: [`docs/deploy-heroku.md`](../docs/deploy-heroku.md).
루트의 `heroku.yml`, `Dockerfile.backend`, `Dockerfile.scraper`가 배포 설정이다.

## 운영 구성 (Docker Compose)

```bash
cd service
cp .env.example .env            # AUTHOR_HASH_SALT 등 채우기
docker compose up --build       # postgres, redis, migrate, api, worker-scrape(Chrome+Xvfb), worker-detect, detector, web
```
- 웹 http://localhost:3000, API http://localhost:8000/api/health, detector http://localhost:8001/health
- 모델이 아직 없으면 detector `ready=false` → 분석은 "AI 판별 모델을 사용할 수 없어요"로 끝난다. 개발 중에는 `.env`에 `DETECTOR_BACKEND=dummy`.

수동 실행(Docker 없이):
```bash
alembic upgrade head
uvicorn --factory realstar_detector_server.main:create_app --port 8001
celery -A realstar_worker.celery_app worker -Q scrape -c 1 --prefetch-multiplier 1 -n scrape@%h
celery -A realstar_worker.celery_app worker -Q detect -c 2 -n detect@%h
uvicorn --factory realstar_api.main:create_app --port 8000
```

## CLI

| 명령 | 용도 |
|---|---|
| `python -m realstar analyze --url <링크>` | 링크 하나로 끝까지 분석 → 결과 JSON (Phase 4) |
| `python -m realstar spike --url … --url …` | Phase 0 수집 가능성 점검 리포트 (실사이트, 수동) — [가이드](../docs/phase0-spike-guide.md) |
| `python -m realstar smoke --url <링크>` | 일일 셀렉터 스모크 테스트 (실패 시 종료 코드 1) |
| `python -m realstar export-training --targets f.txt` | 학습용 과거 리뷰 → `model/data/raw/coupang/` (MODEL_DEV 4.12.1) |
| `python -m realstar export-demo --analysis-id … --key …` | 실제 분석 결과 → 웹 발표 모드 데이터 |
| `python -m realstar prepare-demo --products ../docs/demo-products.txt` | 시연 상품 4개 실제 분석 → 발표 모드 데이터 일괄 교체 |
| `python -m realstar cooldown [--clear]` | 차단 쿨다운 확인/해제 |

## 테스트

```bash
cd service && pytest --cov=realstar          # 128개, 실제 쿠팡 접속 없음 (커버리지 88%)
pytest -m contract                            # 모델 계약 테스트 (realstar_model 설치 시)
pytest -m browser -o addopts=""               # 실제 Chrome으로 수집기 흐름 검증(로컬 모의 사이트, 쿠팡 접속 없음)
cd apps/web && npm run lint && npm run typecheck && npm run test:e2e   # Playwright 15개
```
- 통계 고정 검증 예제: `tests/unit/test_stats.py` (★4.21 → ★4.080, −0.13, AI 49.9%; 표본 평균 3.00/2.79가 나오면 실패)
- 파서: `tests/fixtures/html/` 스냅샷 — ⚠️ 현재 합성 스냅샷. Phase 0 spike 후 실제 HTML로 교체 필요
- 스크래퍼 흐름(대기·상한·차단·금지 영역): 가짜 드라이버(`tests/fakes.py`)

## 화면 확인

`docs/screenshots/{1920,1440,768,375}/` — 전 페이지(홈, 분석, 후보 선택, 진행, 결과, 표본 부족, 차단, 오류, 작동 원리, FAQ, 소개, 약관, 개인정보, 404).
재생성: 목업 빌드 서버를 띄운 뒤 `node scripts/screenshots.mjs http://localhost:3100 ../../../docs/screenshots`.
