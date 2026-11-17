# 내 PC에서 실행하기 — API + 홈페이지

라이브 쿠팡 스크래퍼는 제거되었습니다. 이 서비스는 **저장된 리뷰 JSON(fixture)**으로 동작하며,
AI 판별 자리에는 개발용 더미 판별기가 들어갑니다(결과 화면에 "개발용 결과" 표시, 숫자는 의미 없음).
Redis·PostgreSQL·Celery 없이 프로세스 하나로 돌아갑니다.

리뷰 수집은 이 저장소 루트의 별도 스크립트 `coupang_reviews.py`가 담당합니다(이 서비스와 분리되어 독립 실행).
그 스크립트의 결과 JSON을 서비스에 넣는 연결은 아직 하지 않았습니다.

## ⓪ 준비물

| 프로그램 | 버전 | 확인 |
|---|---|---|
| Python | 3.11 / 3.12 권장 (3.13도 됨, 이미지 OCR만 3.11·3.12) | `python --version` |
| Node.js | 22 LTS | `node --version` |

## ① 설치 (처음 한 번)

```bash
git clone https://github.com/SeonGyuJang/T-SUM-Project.git
cd T-SUM-Project
git checkout claude/tender-faraday-0cnclz
```

백엔드(파이썬) — macOS / Linux:
```bash
cd service
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[api,dev]"
cp .env.local.example .env
```

Windows (PowerShell):
```powershell
cd service
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[api,dev]"
copy .env.local.example .env
```

홈페이지(Node.js) — 새 터미널:
```bash
cd T-SUM-Project/service/apps/web
npm install
```

## ② 실행

터미널 두 개를 씁니다.

**터미널 1 — API 서버** (service 폴더, 가상환경 켠 상태):
```bash
uvicorn --factory realstar_api.main:create_app --port 8000
```
확인: http://localhost:8000/api/health → `"status": "ok"`, `"review_provider": "fixture"`.

**터미널 2 — 홈페이지** (service/apps/web 폴더):
```bash
npm run dev
```
→ http://localhost:3000 접속. 끌 때는 각 터미널에서 `Ctrl + C`.

## ③ 확인할 것 (사용자 요청 처리)

입력 화면에서 아래 **예시 상품 번호**를 링크 형태로 넣으면 저장된 리뷰로 분석이 돌아갑니다.

| # | 해 볼 것 | 정상이면 |
|---|---|---|
| 1 | 홈·작동 원리·FAQ 이동 | 모든 페이지가 열리고 깨진 링크 없음 |
| 2 | 링크 탭에 `https://www.coupang.com/vp/products/1000000001` 입력 → 분석하기 | 진행 화면 → 결과 화면. 전체 평균 vs 사람 리뷰 기준 별점, 별점별 차트, Top 5, "개발용 결과" 표시 |
| 3 | 같은 링크 다시 분석 | 저장된 결과가 바로 열림(24시간 캐시) |
| 4 | 상품명 탭에 `텀블러` 입력 | 후보 카드가 나오고, 고르면 분석 시작 |
| 5 | 쿠팡이 아닌 주소 입력 | "지금은 쿠팡 상품 링크만 분석할 수 있어요." |

예시 상품(fixture, `service/tests/fixtures/json`): `1000000001`(별점 재계산 고정 예제), `1000000002`(표본 부족),
`1000000003`(차단 모의), `1000000004`(리뷰 없음), 검색어 `텀블러`.

### 수집 없이 화면만 보기

```bash
cd service/apps/web
npm run dev:mock      # 가짜 API(목업)로 전체 화면·상태(차단·오류 포함) 확인
npm run dev:demo      # 발표 모드: 저장된 예시 결과만, 네트워크 없음
```

## 참고

- 실제 리뷰로 분석하려면 `coupang_reviews.py`로 수집한 JSON을 `service/tests/fixtures/json` 형식(상품 메타 + 별점별 리뷰)으로 넣으면 됩니다. 자동 변환·연결은 아직 없습니다.
- 수집 데이터는 `service/var/realstar.db`(SQLite)에 쌓입니다. 처음부터 다시 하려면 API를 끄고 `service/var`를 지우세요.
- 운영(Heroku) 구성은 `docs/deploy-heroku.md`.
