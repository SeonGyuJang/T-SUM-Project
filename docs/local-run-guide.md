# 내 PC에서 실행하기 — API + 홈페이지 + 수집기

홈페이지에 **링크·상품명·캡처 이미지**를 넣으면, API가 저장소 루트의 수집기 `coupang_reviews.py`를
그대로 실행해 리뷰를 모으고, 진행 상황(브라우저 실행 → 상품 페이지 → 별점별 개수 → 별점별 리뷰 수집)을
홈페이지에 실시간으로 보여 줍니다. 수집이 끝나면 별점 분포와 수집한 리뷰 원문이 결과 화면에 나옵니다.

- **AI 판별(가짜 리뷰 탐지)만 빠져 있습니다.** 모델이 없으면(`DETECTOR_MODE=none`) 판별 단계는 건너뛰고
  "AI 판별 준비 중"으로 표시합니다. 모델이 연결되면 같은 리뷰로 사람 리뷰 기준 별점을 계산합니다.
- 수집 결과는 수집기 형식 그대로 `output/products/<상품ID>.json`에 저장됩니다. 수집기를 터미널에서
  직접 실행해 모은 상품도 홈페이지의 "수집한 상품" 목록에 바로 나옵니다.
- 이미 수집을 마친 상품은 다시 수집하지 않고(`CRAWLER_REUSE_HOURS`, 기본 24시간) 결과 화면의
  "최신 리뷰로 다시 수집" 버튼으로만 새로 모읍니다.
- Redis·PostgreSQL·Celery 없이 프로세스 하나로 돌아갑니다.

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
pip install "scrapling[fetchers]" && scrapling install   # 수집기(coupang_reviews.py)용
cp .env.local.example .env
```

Windows (PowerShell):
```powershell
cd service
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[api,dev]"
pip install "scrapling[fetchers]"; scrapling install
copy .env.local.example .env
```

> 수집기를 이미 다른 가상환경에서 쓰고 있다면 scrapling을 다시 설치하지 않고 `.env`의
> `CRAWLER_PYTHON`에 그 파이썬 경로(예: `/Users/me/crawler-venv/bin/python`)를 적어도 됩니다.

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
확인: http://localhost:8000/api/health → `"status": "ok"`, `"review_provider": "crawler"`,
`"crawler": {"script_found": true, "scrapling_installed": true, ...}`.

**터미널 2 — 홈페이지** (service/apps/web 폴더):
```bash
npm run dev
```
→ http://localhost:3000 접속. 끌 때는 각 터미널에서 `Ctrl + C`.

### 서버를 켰을 때 꼭 볼 것

uvicorn 터미널에 아래처럼 나와야 합니다. 다르면 `.env`나 브랜치를 확인하세요.
```
  리얼별점 API  ·  REVIEW_PROVIDER=crawler  ·  DETECTOR_MODE=none
  수집기 파일   : …/coupang_reviews.py  (있음)
  수집기 파이썬 : …/python
  scrapling     : 설치됨
```
- `REVIEW_PROVIDER=fixture` → 예시 데이터 모드(수집기 실행 안 함). `cp .env.local.example .env` 후 재시작.
- `scrapling : 없음` → 그 파이썬에 scrapling 설치, 또는 `.env`의 `CRAWLER_PYTHON`에 크롤러를 돌리던 파이썬 경로.
- 코드를 받은(`git pull`) 뒤에는 uvicorn을 **반드시 재시작**하세요(자동 재시작 안 됨).

## ③ 확인할 것

| # | 해 볼 것 | 정상이면 |
|---|---|---|
| 1 | 링크 탭에 쿠팡 상품 링크(`https://www.coupang.com/vp/products/…`) 입력 → 분석하기 | 수집용 Chrome 창이 뜨고, 홈페이지 진행 화면에 단계·별점별 막대·전체 진행률·경과 시간·수집 기록이 실시간으로 바뀜 |
| 2 | 수집이 끝날 때까지 기다림 (상품 하나에 보통 3~10분) | 결과 화면: 전체 평균, 별점 분포, "AI 판별 준비 중" 안내, 수집한 리뷰(별점별·페이지) |
| 3 | `/analyze` 또는 홈 화면 | "수집한 상품" 목록에 방금 상품(과 `output/products`에 있던 상품)이 보임 → 누르면 바로 결과 |
| 4 | 결과 화면 "최신 리뷰로 다시 수집" | 저장 파일을 무시하고 수집기를 다시 실행 |
| 5 | 상품명 탭에 상품명 입력 | 이미 수집한 상품 + 쿠팡 검색 결과 후보 → 고르면 수집 시작 |
| 6 | 공유 링크(`https://link.coupang.com/a/…`) | 브라우저로 열어 상품 번호를 찾은 뒤 수집 |
| 7 | 이미지 탭 (OCR 설치 시) | 이미지에서 읽은 상품명으로 검색 → 후보 선택 → 수집 |

쿠팡이 차단(HTTP 403 등)하면 "지금은 리뷰를 가져올 수 없어요" 화면이 나오고 `BLOCK_COOLDOWN_MIN` 동안 새 수집을 쉽니다.
수집기 실패 기록은 수집기와 같은 `output/failed.txt`에 남습니다.

### 쿠팡에 접속하지 않고 확인하기 (예시 JSON)

`.env`에서 `REVIEW_PROVIDER=fixture`로 바꾸면 저장된 예시 상품으로 동작합니다:
`1000000001`(별점 재계산 고정 예제), `1000000002`(표본 부족), `1000000003`(차단 모의), `1000000004`(리뷰 없음), 검색어 `텀블러`.

### 수집 없이 화면만 보기

```bash
cd service/apps/web
npm run dev:mock      # 가짜 API(목업)로 전체 화면·상태(차단·오류 포함) 확인
npm run dev:demo      # 발표 모드: 저장된 예시 결과만, 네트워크 없음
```

## 참고

- 수집기 연결 구조: API → `collectors/crawler_provider.py` → (subprocess) `collectors/crawler_runner.py` → `coupang_reviews.py`.
  runner는 수집기 함수를 감싸서 진행 상황만 관찰하고, 수집 로직 자체는 건드리지 않습니다.
  수집기 파일의 함수 이름(`collect_product`, `collect_summary`, `collect_rating`, `fetch_review_page`, `open_session`)을
  바꾸면 runner도 함께 맞춰 주세요.
- 수집 데이터는 `service/var/realstar.db`(SQLite)에 쌓입니다. 처음부터 다시 하려면 API를 끄고 `service/var`를 지우세요.
- 운영(Heroku) 구성은 `docs/deploy-heroku.md`.
