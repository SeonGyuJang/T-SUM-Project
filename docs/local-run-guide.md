# 내 PC에서 실행하기 — 수집 확인 → 웹페이지 확인

AI 모델 없이 **실제 쿠팡 수집 + 웹페이지 + 사용자 요청 처리**까지 확인하는 절차입니다.
AI 판별 자리에는 개발용 더미 판별기가 들어가며, 결과 화면에 "개발용 결과" 경고가 붙습니다(숫자는 의미 없음).

> 순서: **① 설치 → ② 수집 점검(spike) → ③ 웹페이지 실행·확인.** ②가 통과하면 AI 모델 학습으로 넘어가면 됩니다.

---

## ⓪ 준비물

| 프로그램 | 버전 | 확인 명령 |
|---|---|---|
| Git | 아무 버전 | `git --version` |
| Python | **3.11 또는 3.12** 권장(3.13도 되지만 이미지 OCR은 불가) | `python --version` (mac: `python3 --version`) |
| Node.js | **22 LTS** | `node --version` |
| Google Chrome | 최신 | 평소 쓰는 Chrome이면 됩니다 |

크롬드라이버는 따로 설치할 필요 없습니다(Selenium이 Chrome 버전에 맞춰 자동으로 받습니다).

## ① 설치 (처음 한 번)

작업 내용은 아직 `main`이 아니라 `claude/tender-faraday-0cnclz` 브랜치에 있습니다.

```bash
git clone https://github.com/SeonGyuJang/T-SUM-Project.git
cd T-SUM-Project
git checkout claude/tender-faraday-0cnclz
```

**백엔드(파이썬)**

macOS / Linux:
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
> PowerShell에서 `Activate.ps1` 실행이 막히면 한 번만: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**홈페이지(Node.js)** — 새 터미널에서:
```bash
cd T-SUM-Project/service/apps/web
npm install
```

`.env`(service 폴더)의 기본값: 실제 쿠팡 수집, Chrome 창 표시, 대기 3~7초, **별점당 20개**(빠른 확인용, 정식은 100), 더미 판별기, Redis·DB 서버 없이 단일 프로세스.

---

## ② 데이터 수집 점검 (spike)

먼저 웹 없이 수집만 따로 확인합니다. **상품 1개, 별점당 10개**로 시작하세요.

```bash
# service 폴더, 가상환경 켠 상태
python -m realstar spike --per-star 10 --url "https://www.coupang.com/vp/products/9751850127?itemId=29200410159&vendorItemId=96120828949"
```

**무슨 일이 일어나나요?** Chrome 창이 하나 뜨고 상품 페이지 → 리뷰 영역 → 최신순 → 5점 필터 → 페이지 넘김… 순서로 **3~7초 간격으로 천천히** 움직입니다. 창은 건드리지 마세요. 터미널에는 단계마다 결과가 찍힙니다.

```
[1/1] https://www.coupang.com/vp/products/9751850127?...
  ✓ 상품번호 9751850127
  ✓ 상품명: ...
  ✓ 표시 평균 ★4.8 · 리뷰 12,345개 · 별점 분포 {5: ..., 4: ..., ...} (개수)
  ✓ 5점 10/10개 (35초, 페이지 누적 3) · 작성일 2026-11-12~2026-11-08
  ✓ 4점 10/10개 ...
  ...
  → ok (210초)
요약: 성공 1/1 · 페이지 14개 · 리포트 var/spike/20261114_101500/report.json
```

### 정상 작동 판정 기준

브라우저로 같은 상품 페이지를 직접 열어 비교해 주세요.

- [ ] **상품명**이 화면과 같다
- [ ] **표시 평균·총 리뷰 수**가 화면과 같다
- [ ] **별점 분포(5~1점 개수)**가 화면의 별점 요약과 같거나 비율로 계산한 값과 맞다
- [ ] 별점마다 `수집/목표`가 같다(예: 10/10). 그 별점 리뷰가 10개보다 적으면 전부(예: 3/3)
- [ ] **작성일이 최근 날짜부터** 내려간다(최신순 정렬 적용)
- [ ] `report.json`의 `sample`(리뷰 앞부분)이 실제 그 별점 리뷰 내용과 같다
- [ ] 차단(✗ blocked) 없이 끝났다

모두 맞으면 나머지 상품도 확인합니다(상품 사이에도 같은 속도로 천천히 진행됩니다).

```bash
python -m realstar spike --per-star 10 --url "<링크1>" --url "<링크2>" --url "<링크3>" --url "<링크4>"
```
(링크 4개는 `docs/demo-products.txt`에 있습니다.)

### 실패했을 때 (처음에는 실패할 가능성이 큽니다)

현재 쿠팡 화면을 읽는 규칙(`selectors.yaml`)은 **실제 화면을 보지 않고 만든 초안**이라, 첫 실행에서 `✗ ... parser_broken`이 나오는 것이 자연스럽습니다.

1. 터미널 마지막에 나온 **결과 폴더(`service/var/spike/<시각>/`)를 통째로 압축**해서 대화에 올려 주세요.
   - `html/` 안에 Chrome이 본 페이지가 순서대로 저장돼 있습니다(리뷰 작성자 닉네임은 `***`로 가려짐).
   - 실패한 순간의 화면은 `*_FAILED_*.html`입니다.
2. 그 HTML로 셀렉터를 실제 화면에 맞게 고치고, 실제 HTML을 테스트 스냅샷으로 넣겠습니다.
3. 직접 보고 싶다면: `python -m realstar diagnose-html var/spike/<시각>/html` — 어떤 셀렉터가 몇 개 맞는지와 파서 결과를 보여줍니다.

| 메시지 | 뜻 | 할 일 |
|---|---|---|
| `parser_broken` | 화면 구조가 셀렉터 초안과 다름 | 결과 폴더 공유 → 셀렉터 수정 |
| `blocked` | 쿠팡이 자동 접근을 막음(Access Denied·보안 확인 화면 등) | **다시 시도하지 말고** 결과 폴더 공유. 60분 쿨다운이 걸립니다 |
| `forbidden_area` | 로그인 등 금지 페이지로 이동됨 | 결과 폴더 공유 |
| `page_budget_exceeded` | 분석당·일일 페이지 상한 도달 | 다음 날 다시, 또는 `--per-star` 줄이기 |
| 처음부터 Chrome이 안 뜸 | Chrome 미설치·버전 문제 | Chrome 업데이트 후 재시도. 회사·학교망이면 드라이버 다운로드가 막혔을 수 있음 |

> 차단 쿨다운 확인/해제: `python -m realstar cooldown` / `python -m realstar cooldown --clear`
> (해제는 원인을 확인한 뒤에만. 막힌 직후 반복 시도는 하지 않습니다.)

---

## ③ 웹페이지 실행

터미널 두 개를 씁니다.

**터미널 1 — API 서버** (service 폴더, 가상환경 켠 상태)
```bash
uvicorn --factory realstar_api.main:create_app --port 8000
```
확인: 브라우저에서 http://localhost:8000/api/health → `"status": "ok"`, `detector.backend`가 `"dummy"`.

**터미널 2 — 홈페이지** (service/apps/web 폴더)
```bash
npm run dev
```
→ **http://localhost:3000** 접속. 끌 때는 각 터미널에서 `Ctrl + C`.

### 확인할 것 (사용자 요청 처리)

| # | 해 볼 것 | 정상이면 |
|---|---|---|
| 1 | 홈·작동 원리·FAQ 페이지 이동 | 모든 페이지가 열리고 깨진 링크 없음 |
| 2 | 분석하기 → **링크** 탭에 시연 상품 링크 붙여넣기 → 분석하기 | 진행 화면으로 이동. **API를 켠 PC에서 Chrome 창이 떠서 수집 시작.** 진행 화면에 "5점 리뷰 수집 중 8/20"처럼 별점별 진행률이 바뀜 |
| 3 | 수집이 끝날 때까지 대기(별점당 20개 기준 수 분) | 결과 화면: 전체 평균 vs 사람 리뷰 기준 별점, 별점별 구성 차트, Top 5, "개발용 결과" 경고. **전체 평균·리뷰 수·별점 분포는 실제 쿠팡 값**이어야 함(사람/AI 구분은 더미라 의미 없음) |
| 4 | 같은 링크로 다시 분석 | 수집 없이 저장된 결과가 바로 열림(24시간 캐시) |
| 5 | **상품명** 탭에 "비타민" 입력 → 상품 찾기 | Chrome이 쿠팡 검색 결과 1페이지를 열고, 후보 카드(이름·가격·일치도·광고 표시)가 나옴 → 하나 고르면 분석 시작 |
| 6 | 링크 칸에 쿠팡이 아닌 주소 입력 | "지금은 쿠팡 상품 링크만 분석할 수 있어요." |
| 7 | 수집 중에 같은 상품을 다른 탭에서 또 요청 | 새 수집 없이 진행 중인 분석 화면으로 연결 |

**이미지 탭**은 OCR을 설치해야 동작합니다(선택). 설치하지 않으면 "지금은 이미지 인식을 사용할 수 없어요"가 정상입니다.
```bash
pip install -e ".[ocr]"         # Python 3.11·3.12만
# .env 에서 OCR_ENGINE=paddleocr 로 바꾸고 API 재시작 (첫 사용 때 한국어 OCR 모델을 받느라 1~2분 걸림)
```

### 수집 없이 화면만 보고 싶을 때

```bash
cd service/apps/web
npm run dev:mock      # 가짜 API(목업)로 전체 화면·상태(차단·오류 포함) 확인
```

---

## 참고

- **정식 값(별점당 100개)으로 돌릴 때:** `.env`의 `SAMPLE_PER_STAR=100`. 쿠팡이 리뷰를 한 페이지에 5개씩 보여 준다면 상품 하나에 페이지 넘김이 100번 넘게 필요해, 분석당 상한(`SCRAPER_MAX_PAGES_PER_ANALYSIS=80`)에 걸릴 수 있습니다. spike 결과(페이지 수)를 보고 함께 조정하겠습니다.
- 수집 데이터는 `service/var/realstar.db`(SQLite)에 쌓입니다. 처음부터 다시 하려면 API를 끄고 `service/var` 폴더를 지우면 됩니다.
- 이 실행 방식은 Redis·PostgreSQL 없이 프로세스 하나로 도는 개발용입니다. 운영(Heroku) 구성은 `docs/deploy-heroku.md`.
