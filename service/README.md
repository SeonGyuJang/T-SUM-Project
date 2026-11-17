# service/ — 리얼별점 서비스 (모델 외 전부)

홈페이지, API, 비동기 워커, 이미지 판독(OCR/VLM), 별점 재계산·Top 5, 모델 연동 어댑터.
AI 탐지 모델 자체는 `model/`(`realstar_model` 패키지) 담당이다. 연결 방법: [`docs/model-integration.md`](../docs/model-integration.md).

> **라이브 쿠팡 스크래퍼는 제거되었다.** 이 서비스는 저장된 리뷰 JSON(fixture)으로 동작한다.
> 리뷰 수집은 저장소 루트의 별도 스크립트 `coupang_reviews.py`가 독립적으로 담당하며, 그 결과를 이 서비스에
> 자동으로 연결하지는 않는다(필요하면 `tests/fixtures/json` 형식으로 넣어 쓴다).

## 구성

```
service/
├── packages/core/realstar/      # 파이썬 코어 (python -m realstar)
│   ├── collectors/              # base.py(스키마·인터페이스), fixture_provider.py(저장된 JSON)
│   ├── resolver/                # url.py, name_search.py, image.py, scoring.py
│   ├── vision/                  # ocr.py, vlm.py, product_text_heuristics.py, ui_phrases.yaml
│   ├── aggregate/               # stats.py (별점 재계산), topk.py (Top 5)
│   ├── detection/               # backends.py (realstar_model·HTTP·dummy), preprocess.py (모델 전처리 어댑터)
│   ├── pipeline/                # analysis.py (수집→탐지→집계), service.py (API·CLI 공용), result_schema.py
│   ├── db/                      # SQLAlchemy 모델, repository
│   ├── state/                   # 쿨다운·락 (Redis / 로컬 파일)
│   └── cli.py
├── apps/
│   ├── api/                     # FastAPI  (uvicorn --factory realstar_api.main:create_app)
│   ├── worker/                  # Celery: detect 큐 (수집·탐지·집계)
│   ├── detector_server/         # /predict, /health (realstar_model 래퍼)
│   └── web/                     # Next.js 홈페이지
├── migrations/                  # Alembic
├── docker-compose.yml           # Dockerfile은 저장소 루트(Dockerfile.backend, Heroku 빌드 컨텍스트 때문)
└── tests/                       # unit / integration / contract, fixtures(json)
```

## 내 PC에서 실행 (API + 홈페이지)

단계별 안내(설치 → 실행, macOS·Windows): **[`docs/local-run-guide.md`](../docs/local-run-guide.md)**

```bash
cd service
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[api,dev]"
cp .env.local.example .env                                   # fixture + 더미 판별기 + 단일 프로세스
uvicorn --factory realstar_api.main:create_app --port 8000   # API
# 새 터미널: cd apps/web && npm install && npm run dev        # 홈페이지 → http://localhost:3000
```
CLI로 바로 확인: `python -m realstar analyze --url "https://www.coupang.com/vp/products/1000000001"`
`dummy` 판별기 결과에는 "개발용 결과" 경고가 붙는다. fixture 상품: `1000000001`(별점 재계산 고정 예제),
`1000000002`(표본 부족), `1000000003`(차단 모의), `1000000004`(리뷰 없음), 단축 링크 `https://link.coupang.com/a/demo01`, 검색어 `텀블러`.

## 백엔드 없이 홈페이지만 (목업·발표 모드)

```bash
cd service/apps/web && npm ci
npm run dev:mock    # MSW 목업 API
npm run dev:demo    # 발표 모드: 저장된 예시 결과만, 네트워크 없음
```
목업 모드 상태 화면 확인용: `…/vp/products/9000000001`(차단), `…/vp/products/9000000002`(오류).

## Heroku 배포

백엔드 container 앱 + 홈페이지 Node 앱. 단계·주의점: [`docs/deploy-heroku.md`](../docs/deploy-heroku.md).
루트의 `heroku.yml`, `Dockerfile.backend`가 배포 설정이다.

## 운영 구성 (Docker Compose)

```bash
cd service
cp .env.example .env
docker compose up --build       # postgres, redis, migrate, api, worker-detect, detector, web
```
- 웹 http://localhost:3000, API http://localhost:8000/api/health, detector http://localhost:8001/health
- 모델이 아직 없으면 detector `ready=false` → 분석은 "AI 판별 모델을 사용할 수 없어요"로 끝난다. 개발 중에는 `DETECTOR_BACKEND=dummy`.

수동 실행(Docker 없이):
```bash
alembic upgrade head
uvicorn --factory realstar_detector_server.main:create_app --port 8001
celery -A realstar_worker.celery_app worker -Q detect -c 2 -n detect@%h
uvicorn --factory realstar_api.main:create_app --port 8000
```

## CLI

| 명령 | 용도 |
|---|---|
| `python -m realstar analyze --url <링크>` | 저장된 리뷰(fixture)로 상품 하나를 끝까지 분석 → 결과 JSON |
| `python -m realstar export-demo --analysis-id … --key …` | 저장된 분석 결과 → 웹 발표 모드 데이터 |
| `python -m realstar prepare-demo --products <파일>` | 상품 목록 분석 → 발표 모드 데이터 일괄 교체 |
| `python -m realstar init-db` | 개발용 SQLite 테이블 생성 |

## 테스트

```bash
cd service && pytest --cov=realstar          # 실제 외부 접속 없음
pytest -m contract                            # 모델 계약 테스트 (realstar_model 설치 시)
cd apps/web && npm run lint && npm run typecheck && npm run test:e2e   # Playwright
```
- 통계 고정 검증 예제: `tests/unit/test_stats.py` (★4.21 → ★4.080, −0.13, AI 49.9%; 표본 평균 3.00/2.79가 나오면 실패)

## 화면 확인

`docs/screenshots/{1920,1440,768,375}/` — 전 페이지 스크린샷.
재생성: 목업 빌드 서버를 띄운 뒤 `node scripts/screenshots.mjs http://localhost:3100 ../../../docs/screenshots`.
