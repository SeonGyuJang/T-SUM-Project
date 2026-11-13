# 결정 기록 (service · 홈페이지)

> README 0-9, 14.2에 따라 서비스·홈페이지 쪽 결정을 날짜와 함께 남긴다. 모델 쪽 결정은 `model/MODEL_DEV.md` 3장.
> 날짜는 Asia/Seoul 기준.

## 1. 오너 질문 (README 14.2) — ⏳ 답변 대기

2026-11-13 작업은 "AI 모델 개발을 제외한 나머지 모든 기능을 개발해 달라"는 요청(R-S001)에 따라 **질문 답변 없이 추천 기본값으로 진행**했다.
기본값을 쓴 곳은 코드·화면에 `TODO(owner)`로 표시했다. 답을 받으면 아래 표의 "답변" 칸을 채우고 해당 위치를 고친다.

| # | 질문 | 사용한 기본값 | 바꿀 위치 | 답변 |
|---|---|---|---|---|
| Q1 | 서비스 이름과 한 줄 소개 | "리얼별점" / "AI가 쓴 리뷰를 걸러낸 진짜 별점" | `service/apps/web/src/lib/site.ts`, `scripts/make-og.mjs`(OG 이미지 재생성) | |
| Q2 | 로고 유무, 브랜드 색상 | 텍스트 로고 + 별 아이콘(자체 SVG), 남색 `#1E3A8A` 단일 강조색 | `src/app/globals.css`의 `--primary*`, `src/components/layout/logo.tsx`, `src/app/icon.svg` | |
| Q3 | 발표 일시·시간·화면 해상도 | 1920×1080, 시연 3분 | `docs/demo-checklist.md` | |
| Q4 | 발표장 인터넷·기기 | 인터넷 불안정 가정 → 발표 모드(오프라인) 구현 | `docs/demo-checklist.md` | |
| Q5 | 시연용 예시 상품 3~5개 | **가상 예시 3개(샘플 데이터 배지 표시)**. 실제 상품 미선정 | `src/demo/data/*.json` ← `python -m realstar export-demo` | |
| Q6 | 배포 위치 | 로컬 시연 (+ 선택적 Vercel) | `NEXT_PUBLIC_SITE_URL`, `CORS_ORIGINS` | |
| Q7 | 팀/제작자 소개, 연락처 | 노출 안 함. 소개 페이지는 프로젝트 배경만 | `site.contactEmail`, `src/app/about/page.tsx` | |
| Q8 | 모델 성능 공개 여부 | 공개. 평가 전이라 "평가 후 공개" 문구 | `site.modelMetrics` | |
| Q9 | 다크 모드 | 라이트 모드만 | — | |
| Q10 | 약관·개인정보처리방침 | 에이전트 초안 + "검토 중인 초안(법률 자문 아님)" 안내 | `src/app/terms`, `src/app/privacy`, `legal-draft-note.tsx` | |
| Q11 | 방문자 분석 도구 | 사용 안 함(외부 스크립트 0개) | `src/app/privacy/page.tsx` 4항 | |
| Q12 | 디자인 참고·회피 스타일 | 없음. **W1 시안 2종 대신 1종으로 바로 구현**(D-S08) | — | |

## 2. TBD (README 13장) 기본값 사용 현황

| ID | 기본값 | 코드 표시 |
|---|---|---|
| TBD-1 | 개인·연구용 (공개 전 법률 검토 필요) | 약관 초안 |
| TBD-3 | 임계값은 모델 manifest에서 읽음(서비스 하드코딩 없음) | `realstar.detection.backends` |
| TBD-4 | 자동 선택 0.85 / 간격 0.15 | `config.py`, `resolver/scoring.py` `# TBD-4: 기본값 사용` |
| TBD-5 | VLM 미사용(OCR만) | `config.py`, `.env.example` |
| TBD-6 | 제목 포함 — 탐지 입력 구성은 model 패키지 담당. service는 title·content를 따로 넘긴다 | `DetectInput` |
| TBD-10 | 브라우저 headless=false (Docker에서는 Xvfb) | `config.py`, `docker/scraper.Dockerfile` |
| TBD-2, 7, 8, 9 | 모델 쪽 결정(MODEL_DEV.md) | — |

## 3. 서비스 쪽 결정

| ID | 날짜 | 결정 | 이유 | 상태 |
|---|---|---|---|---|
| D-S01 | 2026-11-13 | Python 코어 패키지명은 `realstar`(경로 `service/packages/core/realstar/`). README 7장의 `packages/core/{resolver,collectors,...}`를 이 패키지 아래에 그대로 둔다. CLI는 `python -m realstar`. | README Phase 4의 `python -m realstar analyze` 명령과 맞추기 위함 | 유효 |
| D-S02 | 2026-11-13 | 탐지는 `DetectorBackend` 인터페이스 하나로 감싼다: `http`(detector_server, 운영 기본), `inprocess`(`realstar_model` 직접), `dummy`(개발 전용). 더미 결과에는 항상 `dummy_detector` 경고가 붙고 발표 데이터로 내보낼 수 없다. | 모델 완성 전에도 전체 흐름을 개발·테스트하고, 완성 후에는 설정만 바꿔 바로 연결하기 위함 | 유효 |
| D-S03 | 2026-11-13 | 전처리는 `realstar_model.preprocess.clean_review`를 import한다. 패키지가 없을 때는 텍스트를 바꾸지 않는 통과 모드로 동작하고 결과에 `preprocess_unavailable` 안내를 남긴다. 상투 문구 규칙은 service에 복제하지 않는다. 근접 중복도 model의 `preprocess.dedup.assign_dup_groups`가 있으면 그것을 쓰고, 없으면 완전 중복만 묶는다. | README 7.1 "전처리 재구현 금지" 준수 | 유효 |
| D-S04 | 2026-11-13 | `len_chars < MIN_CHARS`이면 모델 라벨과 무관하게 서비스 집계에서도 `uncertain`으로 강제한다(이중 안전장치). | README 5.3-5 | 유효 |
| D-S05 | 2026-11-13 | DB 스키마에 README 5.9 외 컬럼 추가: `products.category/reviews_fetched_at/sampling`, `reviews.option_name/raw_html_ref`, `analyses.cached/force_refresh/input`. | 리뷰 표본 캐시 유효성(같은 표본 조건인지) 판단, RawReview 필드 보존 | 유효 |
| D-S06 | 2026-11-13 | 상품명·단축 링크 해석도 브라우저를 쓰므로 수집 큐(동시성 1)와 같은 전역 락을 쓴다. 수집 중이면 `RESOLVE_TIMEOUT_SEC`(90초) 대기 후 "다른 분석 수집 중" 안내. 검색 캐시가 있으면 브라우저 없이 답한다. | 브라우저 1개·전역 동시 1개 규칙(README 0-3, 4장) | 유효 |
| D-S07 | 2026-11-13 | 이미지 OCR은 API 프로세스 메모리에서만 처리하고, 추출한 검색어만 수집 워커로 보낸다(이미지를 큐·DB·디스크에 두지 않음). EXIF는 픽셀만 새 이미지로 복사해 제거. | README 5.1 (c) "원본 저장 안 함" | 유효 |
| D-S08 | 2026-11-13 | W1 디자인 시안 2종 승인 절차를 생략하고 1종(남색 단일 강조색, Pretendard, 테두리 위주 카드)으로 W2까지 구현했다. 토큰이 CSS 변수로 분리돼 있어 오너 의견에 따라 바꾸기 쉽다. | 오너 부재 중 전체 구현 요청(R-S001). 승인 대기 항목으로 남김 | **오너 확인 필요** |
| D-S09 | 2026-11-13 | 발표 모드는 MSW가 아닌 브라우저 내 로컬 구현으로 동작한다(서비스 워커 등록 실패 위험 제거). 개발용 목업 모드는 MSW. 두 모드 모두 같은 로컬 로직(`lib/api/local-backend.ts`)을 쓴다. | 발표 안정성(README 14.1-4) | 유효 |
| D-S10 | 2026-11-13 | 발표 모드 예시 3개는 **가상 데이터**이며 화면에 "샘플 데이터" 배지와 경고가 표시된다. 숫자는 서비스와 같은 계산 함수로 만들었고 예시 A는 README 5.4 고정 검증 예제와 같다. 실제 발표 전 Q5 상품을 실제로 분석해 교체해야 한다. | 저장 데이터를 실제 결과로 꾸미지 않기(README 14.7) | 유효 |
| D-S11 | 2026-11-13 | 수집 중 '리뷰 영역이 연속으로 비어 있음' 판정: 해당 별점에서 하나도 못 읽었는데(N_s>0) 빈 페이지가 나오면 1회로 세고, 연속 `SCRAPER_EMPTY_STREAK_LIMIT`(3)회면 차단 처리. 이미 읽은 뒤의 빈 페이지는 목록 끝으로 본다. | 차단 오탐(목록 끝)과 미탐을 함께 줄이기 위함 | 유효 |
| D-S12 | 2026-11-13 | 결과 페이지(`/analyses/*`)는 `noindex`, robots.txt에서도 제외. | 개별 분석 결과는 검색 노출 대상이 아님. Lighthouse SEO 점수가 이 페이지만 낮은 이유 | 유효 |

## 4. 사용자 요청 기록

| ID | 날짜 | 요청(요약) | 반영 |
|---|---|---|---|
| R-S001 | 2026-11-13 | "AI 모델 개발은 시간이 걸리니 AI 모델 개발을 제외한 나머지 모든 기능을 개발해 달라. 나중에 저장된 모델만 불러와 실행하면 되도록, AI 개발 완료 후 바로 돌아갈 수 있게 구성해 달라." | `service/` 전체 구현. 모델 연결 방법은 `docs/model-integration.md`. `model/` 폴더는 수정하지 않음. |
