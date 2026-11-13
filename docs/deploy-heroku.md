# Heroku 배포 가이드

> 결정(2026-11-13): 도메인 없이 Heroku에 배포. 주소는 Heroku가 주는 `https://<앱이름>-<임의문자>.herokuapp.com`을 쓴다.
> 서비스 이름이 정해지지 않아 아래 앱 이름 `realstar-api`, `realstar-web`은 예시다(팀 결정 후 바꾸면 된다).
> 이 가이드의 명령은 아직 실제 Heroku 계정에서 실행해 보지 않았다(배포 계정·결제 정보가 필요). 처음 배포할 때 결과를 확인해 주세요.

## 1. 구성

Heroku는 앱 하나에 외부로 열린 `web` 프로세스가 하나뿐이고 다이노끼리 내부 통신이 없다. 그래서 앱 두 개로 나눈다.

| Heroku 앱 | 스택 | 프로세스 | 하는 일 |
|---|---|---|---|
| `realstar-api` | container (`heroku.yml`) | `web` | FastAPI (`/api/*`) |
| | | `detect` | 탐지·집계 Celery 워커. **AI 모델을 프로세스 안에서 로드**(`DETECTOR_MODE=inprocess`) |
| | | `scrape` | 수집 Celery 워커(Chrome + Xvfb, 동시성 1) |
| | | release | `alembic upgrade head` (배포마다 DB 마이그레이션) |
| `realstar-web` | heroku-24 (Node 빌드팩) | `web` | Next.js 홈페이지 |

애드온(`realstar-api`에 추가): Heroku Postgres → `DATABASE_URL`, Heroku Key-Value Store(Redis) → `REDIS_URL`.
코드가 Heroku 형식을 자동으로 처리한다: `postgres://` → SQLAlchemy 형식 변환, `rediss://` 자체 서명 인증서 허용(Celery 포함).

## 2. 처음 배포

```bash
heroku login

# ── 백엔드 앱 ─────────────────────────────
heroku create realstar-api --stack container
heroku addons:create heroku-postgresql:essential-0 -a realstar-api
heroku addons:create heroku-redis:mini -a realstar-api

heroku config:set -a realstar-api \
  TASK_BACKEND=celery \
  DETECTOR_MODE=inprocess \
  RESOLVE_TIMEOUT_SEC=25 \
  SCRAPER_HEADLESS=true \
  OCR_ENGINE=none \
  AUTHOR_HASH_SALT=$(python -c "import secrets;print(secrets.token_hex(16))")

git remote add heroku-api https://git.heroku.com/realstar-api.git
git push heroku-api <배포할 브랜치>:main
heroku ps:scale -a realstar-api web=1:standard-1x detect=1:standard-2x scrape=1:standard-2x

# ── 홈페이지 앱 ───────────────────────────
heroku create realstar-web
heroku buildpacks:add -a realstar-web https://github.com/lstoll/heroku-buildpack-monorepo
heroku buildpacks:add -a realstar-web heroku/nodejs
API_URL=$(heroku info -a realstar-api -s | grep web_url | cut -d= -f2 | sed 's#/$##')
heroku config:set -a realstar-web APP_BASE=service/apps/web NEXT_PUBLIC_API_BASE_URL=$API_URL NEXT_PUBLIC_API_MODE=live
WEB_URL=$(heroku info -a realstar-web -s | grep web_url | cut -d= -f2 | sed 's#/$##')
heroku config:set -a realstar-web NEXT_PUBLIC_SITE_URL=$WEB_URL
heroku config:set -a realstar-api CORS_ORIGINS=$WEB_URL

git remote add heroku-web https://git.heroku.com/realstar-web.git
git push heroku-web <배포할 브랜치>:main
```

- `NEXT_PUBLIC_*` 값은 **빌드할 때** 홈페이지에 들어간다. 값을 바꾸면 홈페이지 앱을 다시 배포해야 한다(`git commit --allow-empty` 대신 `heroku builds:create`나 새 커밋 푸시).
- 확인: `$API_URL/api/health`, `$WEB_URL`.

## 3. AI 모델 연결 (모델 개발 완료 후)

Heroku에는 볼륨이 없고 `model/artifacts/`는 git에 올라가지 않는다. 그래서:
1. 모델 아티팩트 폴더(`det-ko-review-v1.0/`, `manifest.json` 포함)를 tar.gz로 묶어 비공개 저장소(S3 미리 서명 URL, Hugging Face 비공개 저장소 등)에 올린다.
2. `heroku config:set -a realstar-api MODEL_ARTIFACT_URL=<주소> MODEL_ARTIFACT_PATH=/tmp/models/det-ko-review-v1.0`
3. `model/pyproject.toml`이 커밋돼 있으면 다음 배포 때 이미지에 `realstar_model`이 자동 설치된다. `detect` 다이노가 시작할 때 아티팩트를 받아 둔다(다이노 재시작마다 다시 받음).
4. LM 가중치(MODEL_DEV 4.7)는 Hugging Face에서 받는다(`HF_HOME=/tmp/hf`). 비공개 모델이면 `HF_TOKEN`을 config var로 넣는다.

**메모리:** Heroku에는 GPU가 없다. 인코더 + 1.5~3B LM을 CPU로 올리면 수 GB가 필요해 `detect`는 Performance-L(14GB) 수준이 필요할 수 있다.
비용을 줄이려면 MODEL_DEV 4.13의 **CPU 경량 모드(`-lite`, ①+④)** 아티팩트를 쓰거나, GPU 서버에 `detector_server`를 따로 띄우고
`DETECTOR_MODE=http`, `DETECTOR_URL=<그 서버 주소>`로 바꾼다. 모델 크기가 정해지면 다시 정하면 된다.

## 4. 이미지 입력(OCR)

기본 Heroku 빌드는 OCR을 넣지 않아 이미지 탭이 "지금은 이미지 인식을 사용할 수 없어요"로 안내한다. 켜려면:
- `heroku.yml`의 `PIP_EXTRAS`를 `api,worker,postgres,ocr`로 바꾸고 배포
- `heroku config:set -a realstar-api OCR_ENGINE=paddleocr`, `web` 다이노를 `standard-2x`(1GB) 이상으로
- 첫 요청 때 PaddleOCR 한국어 모델을 내려받는다(다이노 재시작마다 다시 받음).

## 5. ⚠️ 꼭 알아야 할 점

1. **쿠팡이 Heroku에서의 접속을 막을 가능성이 높다.** Heroku 다이노는 미국 데이터센터(AWS) IP를 쓰고, 쿠팡은 비브라우저·데이터센터 접근을 막는 엣지 보안을 운영한다(README 11).
   차단되면 서비스는 규칙대로 즉시 멈추고 60분 쉬며 "지금은 리뷰를 가져올 수 없어요"를 보여준다. 우회(프록시 등)는 하지 않는다.
   먼저 `docs/phase0-spike-guide.md`로 오너 PC에서 수집이 되는지 확인하고, Heroku에서도 한 번 시험해 보길 권한다.
   구조상 `scrape` 워커는 Heroku 밖(예: 팀원 PC)에서 Heroku의 `REDIS_URL`·`DATABASE_URL`에 연결해 돌릴 수도 있다(이 경우 `heroku ps:scale scrape=0`).
   어디서 수집할지는 사이트 정책·법적 검토(TBD-1)와 함께 팀이 정할 일이다.
2. **요청 30초 제한:** 상품명·단축 링크 해석은 최대 25초만 기다린다(`RESOLVE_TIMEOUT_SEC=25`). 다른 분석이 수집 중이면 "잠시 후 다시 시도" 안내가 나온다. 분석 자체는 비동기라 영향 없다.
3. **파일 시스템은 임시:** 다이노가 재시작되면 `/tmp`가 비워진다. 상태(쿨다운·일일 상한·락)는 Redis, 데이터는 Postgres에 있으므로 문제없다. 디버그용 리뷰 HTML(`/tmp/realstar/scrape_html`)만 사라진다.
4. **비용(2026-07 기준 표):** Standard-1X $25/월, Standard-2X $50/월, Performance-L $500/월 + Postgres·Redis 애드온 요금. 발표 기간에만 다이노를 켜고(`heroku ps:scale ...=1`) 끝나면 0으로 줄이면 아낄 수 있다.
5. **Eco·Basic 다이노는 메모리 0.5GB**라 Chrome 수집 워커에는 부족하다.

## 6. 다시 배포·운영

```bash
git push heroku-api <브랜치>:main      # 백엔드(배포마다 마이그레이션 자동)
git push heroku-web <브랜치>:main      # 홈페이지
heroku logs -t -a realstar-api --dyno scrape
heroku run -a realstar-api "python -m realstar cooldown"          # 차단 쿨다운 확인
```
