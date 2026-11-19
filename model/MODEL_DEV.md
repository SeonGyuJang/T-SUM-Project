# MODEL_DEV.md — AI 작성 리뷰 탐지 모델 개발 마스터 문서

> **이 문서는 `model/` 폴더 작업의 단일 기준 문서(Single Source of Truth)입니다.**
> `model/` 폴더에서 일하는 에이전트는 **작업을 시작할 때마다 이 문서 전체를 먼저 읽고**, **작업이 끝날 때마다 이 문서를 갱신**합니다.
> 루트 `README.md`의 5.6절은 요약입니다. 모델에 관해 두 문서가 충돌하면 **이 문서가 우선**합니다.

---

## 0. 문서 사용 규칙 (반드시 지킬 것)

### 0.1 세션 시작 시
1. 이 문서 전체를 읽는다. 특히 **1장(현재 상태)**, **7장(열린 질문)**, **6장(작업 로그)의 최근 5개 항목**을 먼저 본다.
2. 1장의 "다음 할 일"을 기준으로 이번 세션의 작업을 정한다. 사용자의 새 요청이 있으면 먼저 2장(사용자 요청 기록)에 기록한다.

### 0.2 작업 중
- 설계를 바꾸는 결정을 하면 **3장(결정 기록)**에 새 항목을 추가한다. 기존 결정을 바꾸는 경우 기존 항목을 지우지 말고 상태를 `대체됨(D-xxx)`으로 바꾼다.
- 실험을 돌리면 **5장(실험 기록)**에 결과를 남긴다. 실패한 실험도 남긴다.
- 4장(기술 명세)과 다르게 구현해야 하면, 먼저 3장에 결정을 기록하고 4장을 수정한 뒤 구현한다. **문서와 코드가 다른 상태로 두지 않는다.**

### 0.3 세션 종료 시 (매번)
1. **6장(작업 로그)**에 항목을 추가한다. 날짜, 한 일, 바꾼 파일, 결과, 남은 문제, 다음 할 일을 적는다.
2. **1장(현재 상태)**을 최신으로 고친다.
3. 사용자에게 물어볼 것이 생겼으면 **7장**에 추가하고, 사용자에게 직접 질문한다.

### 0.4 기록 원칙
- **추가만 한다(append-only).** 1장(현재 상태)과 4장(기술 명세)만 덮어써서 수정할 수 있다. 4장을 수정할 때는 해당 절 끝에 `(수정: 날짜, D-xxx)` 표시를 남긴다.
- 날짜는 `YYYY-MM-DD`(Asia/Seoul) 형식으로 쓴다.
- ID 규칙:
  - 사용자 요청 `R-001`
  - 결정 `D-001`
  - 실험 `EXP-YYYYMMDD-NN`
  - 열린 질문 `Q-M01`
  - 모델 버전 `det-ko-review-vMAJOR.MINOR`
- 사용자 요청은 **사용자 표현을 최대한 그대로** 요약해 적는다. 에이전트의 해석은 따로 적는다.

### 0.5 폴더 경계 규칙
- 이 폴더(`model/`)의 에이전트는 `service/` 폴더의 코드를 **수정하지 않는다.** 서비스 쪽 변경이 필요하면 7장에 적고 사용자에게 알린다.
- `model/`과 `service/`는 **4.12절의 계약(데이터 계약, 추론 API 계약)**으로만 연결된다. 계약을 바꾸려면 결정 기록(D-xxx)을 남기고, 루트 README에도 반영하도록 사용자에게 알린다.
- 모델과 관계없는 코드(웹, API 서버, 스크래퍼, OCR/VLM 이미지 판독)는 이 폴더에 만들지 않는다.

---

## 1. 현재 상태 (항상 최신으로 유지)

| 항목 | 내용 |
|---|---|
| 현재 단계 | **M1 (사람 데이터) 수집 시작** — 수집기 준비 완료, 실제 수집 대기 |
| 최신 모델 버전 | 없음 |
| 최신 데이터 버전 | 없음 |
| 막힌 것(Blocker) | Q-M08(2022-11-30 이후 리뷰 라벨 방침) 답변 대기, Q-M01·Q-M02 대기 |
| 다음 할 일 | ① `collect_training_data.py naver` ② 상품 목록(`training_products.txt`) 작성 → `inspect`로 날짜순 정렬 확인 → `collect` ③ `stats`로 별점×길이 칸 부족분 확인 ④ Q-M08 결정 후 AI 데이터(M2) 방침 확정 |
| 마지막 갱신 | 2026-11-17 (학습 데이터 수집기 추가) |

---

## 2. 사용자 요청 기록 (Request Log)

| ID | 날짜 | 사용자 요청(요약) | 에이전트 해석 / 반영 위치 | 상태 |
|---|---|---|---|---|
| R-001 | 2026-11-13 | 최신 논문들의 여러 기술을 융합해서 AI가 생성한 텍스트를 탐지하고 싶다. | 서로 다른 원리의 신호 4종을 메타 분류기로 융합하는 구조(4.3) | 설계 반영 |
| R-002 | 2026-11-13 | 한국어 특화 모델을 써야 할 것 같다. 쿠팡 리뷰가 AI로 작성됐는지 판단하려 한다. | 한국어 인코더, 한국어 LLM, Kiwi 언어 특징. 도메인은 쿠팡 리뷰(짧은 구어체) | 설계 반영 |
| R-003 | 2026-11-13 | 별점별 100개 리뷰의 사람 작성 수를 파악하고, 전체 평균과 사람 리뷰 평균의 차이를 보여준다. 별점별로 사람이 썼을 확률이 높은 Top 5를 보여준다. | 모델은 **보정된 확률(p_ai, p_human)**과 3단계 라벨을 출력해야 한다. 별점별 사람 비율 추정의 정확도도 평가해야 한다(4.10.5) | 설계 반영 |
| R-004 | 2026-11-13 | 쿠팡 수집은 Selenium/BeautifulSoup 등 비 API 방식으로 한다. | 사람 리뷰 학습 데이터 중 쿠팡 과거 리뷰는 `service/` 스크래퍼가 내보낸 파일로 받는다(4.12.1). 데이터 생성에 상용 LLM API를 쓸지는 Q-M02로 확인 | 일부 확인 필요 |
| R-005 | 2026-11-13 | 모델 개발 코드는 별도 폴더로 관리한다. 모든 작업·수정·사용자 요청을 별도 md 파일에 기록해 길을 잃지 않게 한다. 이 md에는 AI 개발 방법이 매우 자세하고 기술적으로 적혀 있어야 한다. | `model/` 폴더 분리, 이 문서(MODEL_DEV.md) 운영 규칙(0장) | 반영 |
| R-006 | 2026-11-17 | 새 코드를 만들어 AI 모델 개발용 데이터 수집을 시작한다. 데이터는 네이버 쇼핑 데이터와 직접 수집한 리뷰를 쓴다. ChatGPT가 나오기 전 기간은 AI를 사용하지 않은 데이터, 그 이후 데이터는 AI를 사용한 데이터로 규정한다. 적절한 양이 모이면 모델 개발을 시작한다. | 수집기 `collect_training_data.py`(저장소 루트) 추가: H2 네이버, H1 쿠팡 2022-11-30 이전, U1 쿠팡 2023년 이후. "이후 = AI" 라벨은 D-002·4.2.1(이후 리뷰는 라벨 없는 U1)과 충돌하므로 Q-M08로 확인 요청. 수집 방법은 라벨 방침과 무관하므로 먼저 진행 | 수집기 반영, 라벨 방침 확인 필요 |
| R-007 | 2026-11-17 | 쿠팡 과거 데이터 수집 코드: training_products.txt 링크만이 아니라, 카테고리를 지정하면 그 안의 상품을 전부 돌며 과거(2022-11-20 이전) 리뷰가 있는지 확인하고 없으면 넘어가고 있으면 수집. 상품당 최대 10~50개(과적합 방지, 에이전트 판단). 리뷰 페이지네이션(data-page)으로 맨 뒤로 가서 리뷰 시작 시점을 확인하는 방식 제안. | `category` 명령 추가(D-011). 페이지 이동은 리뷰 API의 page 파라미터로 마지막 페이지를 바로 요청. 기준일은 D-002의 2022-11-30을 기본으로 두고 `--cutoff 2022-11-20`으로 바꿀 수 있게 함(사용자가 쓴 날짜가 오타인지 확인 필요) | 반영 |
| R-008 | 2026-11-19 | 크롤링이 너무 느리다. ① 여러 개를 띄워 동시에 충돌 없이 병렬 수집하고, 병렬로 띄운 크롤링 웹페이지는 서로 다른 IP를 가져야 한다(과부하가 덜 걸리게). ② 수집되는 모든 데이터는 하나의 json 파일에 구조화되어 저장. ③ 중간에 끊기는 경우를 고려해 실시간 저장(상품 단위 저장은 괜찮음). | ① 같은 IP에서 작업자(브라우저) N개 병렬, 전체 요청 간격 제한, 하나가 차단되면 모두 중단(D-012). **서로 다른 IP(프록시 등)는 쿠팡의 자동 접근 차단을 우회하는 방식이라 구현하지 않음**(README 0-3, D-012). ② `coupang_training.json` 하나(상품별 중첩 구조). ③ 상품 하나가 끝날 때마다 임시 파일 → 바꿔치기 저장 | 반영(서로 다른 IP 제외) |

---

## 3. 결정 기록 (Decision Log)

| ID | 날짜 | 결정 | 이유 | 상태 |
|---|---|---|---|---|
| D-001 | 2026-11-13 | 탐지 모델은 ① 한국어 인코더 분류기 ② LLM hidden state probe ③ LLM 로그확률 통계 ④ 한국어 언어 특징 → ⑤ 메타 분류기 → 확률 보정 구조로 만든다. | 신호들의 약점이 서로 다르다(분포 이동, 짧은 글, 새 생성 모델). 이질적 신호를 합치면 성능이 오른다는 선행연구(TOCSIN, DivEye 결합 실험)가 있다. | 유효 |
| D-002 | 2026-11-13 | 사람 라벨은 **작성일 2022-11-30 이전** 리뷰로 정한다. 사람이 직접 라벨링하지 않는다. | ChatGPT 공개 이전 리뷰는 사실상 사람이 작성했다. 사람은 AI 리뷰를 구분하지 못한다(약 50%). | 유효 |
| D-003 | 2026-11-13 | 주 평가지표는 TPR@FPR=1%, 2%로 한다. AUROC는 보조 지표다. | 실제 구매자를 AI로 오판하는 비용이 크다. AUROC는 분포 밖에서 과신하는 오판을 숨긴다(Rethinking…, 2026). | 유효 |
| D-004 | 2026-11-13 | 3단계 라벨 `ai / human / uncertain`. 임계값은 검증셋에서 정하고 **길이 구간별로 따로** 정한다. | 짧은 리뷰는 정보가 부족하다. 길이 구간마다 점수 분포가 달라, 하나의 임계값으로는 구간별 FPR을 지킬 수 없다. | 유효 |
| D-005 | 2026-11-13 | 메타 분류기는 **out-of-fold(OOF) 예측**으로 학습한다(상품 단위 GroupKFold). | 같은 데이터로 학습한 기반 모델 점수를 쓰면 누수가 생기고, 메타 분류기가 ①만 과신하게 된다. | 유효 |
| D-006 | 2026-11-13 | 모델 입력에서는 **줄바꿈을 공백으로 합친다.** 줄바꿈 수는 별도 특징으로만 두고, ablation으로 지름길 여부를 검증한다. | 수집 경로(스크래핑 vs 생성)에 따라 줄바꿈 형태가 달라지는 아티팩트 위험이 있다(Measuring Artifact Reliance, 2026). | 유효 |
| D-007 | 2026-11-13 | AI 리뷰의 길이 분포를 같은 별점·카테고리의 사람 리뷰 길이 분포에 맞춰 생성한다. | 길이 자체가 지름길이 되는 것을 막는다. | 유효 |
| D-008 | 2026-11-13 | 데이터 분할은 상품 단위 그룹으로 나누고, 생성 모델 제외·카테고리 제외 테스트셋을 따로 둔다. | 같은 상품의 리뷰가 학습과 테스트에 동시에 들어가는 누수를 막는다. 처음 보는 생성 모델에 대한 일반화를 측정한다. | 유효 |
| D-009 | 2026-11-13 | `model/`과 `service/`의 폴더를 분리하고, 4.12 계약으로만 연결한다. 전처리 모듈은 `model/`에 두고 서비스가 import한다. | 학습과 추론의 전처리를 반드시 같게 하기 위함(R-005). | 유효 |
| D-010 | 2026-11-17 | H1·U1 쿠팡 리뷰 수집은 저장소 루트 `collect_training_data.py`가 담당한다(서비스 스크래퍼는 제거됨). `coupang_reviews.py`의 접속 함수를 재사용하고, 출력은 4.12.1 형식에 `period`(pre_chatgpt/post_chatgpt)·`length_bucket`·`option_name` 필드를 더한다. 2022-11-30 이전 리뷰는 최신순 정렬 + 이진 탐색으로 경계 페이지를 찾고, 그 뒤 구간에서 페이지를 고르게 골라 담는다. 2022-11-30~2022-12-31은 경계 구간으로 수집하지 않는다. | 서비스 수집 경로가 바뀌었다(R-006). 기본 정렬 앞쪽은 최근 리뷰가 대부분이라 이전 리뷰에 닿으려면 깊은 페이지가 필요하다. 이진 탐색은 별점당 약 10회 요청으로 경계를 찾는다. | 유효 |
| D-011 | 2026-11-17 | H1 수집에 카테고리 모드를 둔다(사용자 요청 R-007). 상품당 최대 40개, 별점은 적은 쪽(1점)부터 남은 몫을 균등 배분한다. 과거 리뷰 유무는 리뷰 API에 마지막 페이지 번호를 바로 넣어 확인한다(화면 페이지 버튼 클릭 대신). | 상품 목록을 사람이 고르는 부담을 줄이고 카테고리 안에서 고르게 모은다. 한 상품에서 많이 담으면 그 상품 고유 표현에 과적합된다(10~50개 범위에서 40). | 유효 |
| D-012 | 2026-11-19 | 학습 데이터 수집 결과는 JSON 파일 하나(`model/data/raw/coupang/coupang_training.json`, 상품별로 리뷰 중첩)에 저장하고, 상품마다 원자적으로(임시 파일 → os.replace) 갱신한다. 병렬 수집은 같은 IP에서 작업자 프로세스 N개(최대 4)로 하며, 메인 프로세스만 파일을 쓴다. 작업자마다 Chrome 프로필 사본을 쓰고, 모든 작업자를 합쳐 요청 간격을 `--min-interval`(기본 1초) 이상으로 묶는다. 한 작업자가 차단되면 모두 멈춘다. 서로 다른 IP로 요청을 분산하는 방식은 쓰지 않는다. | 사용자 요청 R-008. JSON 하나로 관리·이어서 수집이 쉽다. 같은 프로필은 동시에 열 수 없다. IP 분산은 사이트의 차단을 우회하는 것이며 총 부하도 줄지 않는다(README 0-3 원칙). 이전 JSONL·_state.json은 첫 실행 때 한 번 옮겨 온다. | 유효 |

---

## 4. 기술 명세 (How We Build the Detector)

### 4.0 목표와 성공 기준
- **입력:** 쿠팡 리뷰 1건(제목, 본문, 별점, 카테고리 선택값)
- **출력:** `p_ai ∈ [0,1]`(보정된 확률), `p_human = 1 − p_ai`, `label ∈ {ai, human, uncertain}`, 특징 요약, `model_version`
- **서비스에서의 용도:** 별점별 사람 비율 `r_s`를 추정하고, `p_human` 순으로 Top 5를 고른다. 따라서 **확률 보정**과 **비율 추정 정확도**가 개별 분류 정확도만큼 중요하다.
- **v1 출시 기준(Go 조건, 사용자 승인으로 조정 가능):**
  | 지표 | 기준 |
  |---|---|
  | T_iid AUROC | ≥ 0.95 |
  | T_gen(생성 모델 제외), L 구간(≥100자) TPR@1%FPR | ≥ 0.60 |
  | T_time(쿠팡 2022-11 이전 사람 리뷰, 학습 미사용) 실제 FPR | ≤ 3% (목표 2%) |
  | 보정 오차 ECE (T_iid) | ≤ 0.05 |
  | 집계 시뮬레이션 별점별 사람 비율 MAE (4.10.5) | ≤ 0.08 |
  | 리뷰 500개 배치 추론 시간(목표 GPU 기준) | ≤ 60초 |

### 4.1 개발 환경
- Python 3.11, PyTorch(CUDA), transformers, accelerate, datasets, scikit-learn, lightgbm, kiwipiepy, datasketch(MinHash), pandas/pyarrow, pyyaml, joblib, tqdm, pytest, ruff, mypy
- 데이터 생성(선택): vLLM(로컬 오픈 모델 서빙), 상용 LLM SDK(Q-M02 결정에 따름)
- 실험 추적: `reports/experiments.csv` + 실험별 `reports/EXP-*/` 폴더(설정 사본, 지표 JSON, 그림). MLflow는 선택 사항이다.
- 재현성:
  - 모든 스크립트는 `--config configs/*.yaml`로만 동작한다.
  - 시드는 `seed: 42` 기본, 주요 실험은 시드 3개(42, 43, 44)로 평균±표준편차를 낸다.
  - 데이터 버전은 분할 파일들의 SHA256 앞 8자리로 표시한다(예: `data-v1-3fa9c2d1`).

### 4.2 데이터 설계

#### 4.2.1 원천 데이터
| 코드 | 원천 | 라벨 | 용도 | 비고 |
|---|---|---|---|---|
| H1 | 쿠팡 리뷰, **작성일 < 2022-11-30** | human(0) | 학습·검증·테스트 주력 | `service/` 스크래퍼가 내보낸 JSONL(4.12.1). 3점 리뷰는 이 원천에서만 확보된다. |
| H2 | 네이버 쇼핑 리뷰 20만 건(bab2min/corpus `sentiment/naver_shopping.txt`) | human(0) | 보조 학습 | 평점은 1·2·4·5만 있고 3점이 없다. 플랫폼이 달라 지름길 위험이 있으므로 비중을 제한한다(전체 사람 데이터의 40% 이하). |
| A1 | 상용 LLM으로 생성 | ai(1) | 학습·테스트 | Q-M02 |
| A2 | 로컬 오픈 LLM으로 생성 | ai(1) | 학습·테스트 | GPU 사양에 따름(Q-M01) |
| A3 | 사람 리뷰(H1)를 LLM이 다듬기·늘리기·요약 | ai(1), `subtype=polished` | 선택(Q-M05) | v1에서는 ai로 합치고 하위 유형만 기록한다. |
| U1 | 쿠팡 리뷰, 작성일 ≥ 2023-01-01 (라벨 없음) | – | 시간 추세 점검(4.10.4) | 학습에 쓰지 않는다. |

#### 4.2.2 규모 목표 (Q-M04로 확정)
- 사람: 25,000건(H1 ≥ 15,000, H2 ≤ 10,000)
- AI: 25,000건(A1·A2 합계, 생성 모델당 최소 2,500)
- 별점(1~5) × 길이 구간(S/M/L) 각 칸에 최소 300건을 확보한다. 부족한 칸은 5장에 기록하고 추가로 생성·수집한다.
- 길이 구간 정의(공백 포함 문자 수, 전처리 후 기준): **S < 30자, 30자 ≤ M < 100자, L ≥ 100자**

#### 4.2.3 H1 수집 요구사항 (`service/` 스크래퍼에 전달할 사양)
- 카테고리 8종 이상(가전, 식품, 뷰티, 생활용품, 패션, 유아동, 스포츠, 반려동물 등)에 걸쳐, 2021년 이전에 출시되어 리뷰가 많은 상품 200~500개
- 상품당 2022-11-30 이전 리뷰를 별점별 최대 30건씩 수집한다(한 상품이 데이터를 독점하지 않게).
- 필드는 4.12.1 스키마를 따른다. 작성일이 없는 리뷰는 제외한다.
- 테스트(T_time)용으로 **상품 50개는 학습에서 완전히 제외**한다(상품 ID 목록을 `data/splits/t_time_products.txt`로 고정).
- 수집 도구: 저장소 루트 `collect_training_data.py` (`naver` / `inspect` / `category` / `collect` / `stats`), 카테고리 목록 `training_categories.txt`, 상품 목록 `training_products.txt`.
- 카테고리 모드(`category`): 카테고리 목록 페이지를 넘기며 상품을 모으고, 상품마다 전체 별점·최신순 첫/마지막 페이지만 보고 2022-11-30 이전 리뷰 유무를 판단한다. 있으면 **상품당 최대 40개**(1점부터 별점마다 남은 몫을 균등 배분)를 담는다. 상품당 상한은 한 상품의 문체·어휘에 과적합되는 것을 막기 위함이다. (수정: 2026-11-17, D-011) 결과는 `model/data/raw/coupang/coupang_training.json`(JSON 하나, D-012), `model/data/raw/naver/naver_shopping.jsonl`. (수정: 2026-11-19, D-012)

### 4.3 전체 아키텍처

```
리뷰 → [전처리 4.4] → clean_text, 길이, 플래그
          │
          ├─▶ ① 인코더 분류기 (4.6) ─────────────▶ f1 = logit_enc
          │
          ├─▶ 한국어 causal LM (고정, 4.7)
          │     ├─ 원문 forward 1회 ─▶ ② probe 특징 (4.7.2)
          │     │                     ③ 통계 특징 (4.8.1~4.8.4)
          │     └─ 어절 셔플 forward K회 ─▶ ③ 셔플 특징 (4.8.5)
          │
          ├─▶ ④ Kiwi 언어 특징 (4.9) ───────────▶ 해석 가능한 수치 약 30개
          │
          └─▶ 길이·메타 특징 (문자 수, 어절 수, 토큰 수)
                         │
                         ▼
          ⑤ 메타 분류기 LightGBM (OOF 학습, 4.10.1)
                         ▼
          확률 보정 Isotonic/Platt (4.10.2) → p_ai
                         ▼
          길이 구간별 임계값 (4.10.3) → label
```

### 4.4 전처리 (`src/realstar_model/preprocess/`) — 학습과 추론 공용
`service/`는 이 모듈을 그대로 import한다(D-009). 순서는 다음과 같다.
1. **유니코드 정규화:** NFC. 제로폭 문자(U+200B~U+200D, U+FEFF)를 제거하되, 제거 개수는 특징 `zw_count`로 남긴다.
2. **상투 문구 제거:** `preprocess/boilerplate_patterns.yaml`의 정규식으로 제거하고 플래그를 기록한다.
   - 예: `본 리뷰는 .*?쿠팡캐시.*?작성한 것입니다\.?` → `is_cash_event=1`
   - 체험단·협찬·제공 고지 → `is_sponsored=1`
   - 패턴 파일은 버전을 올리며 관리하고, 바꾸면 6장에 기록한다.
3. **공백 정규화:** 연속 공백은 1개로 줄인다. 줄바꿈 수를 `newline_count`에 저장한 뒤 줄바꿈을 공백으로 바꾼다(D-006). 앞뒤 공백을 제거한다.
4. **보존 규칙:** 이모지, ㅋㅋ·ㅎㅎ·ㅠㅠ, 자모 단독, 특수문자, 맞춤법 오류는 **그대로 둔다.**
5. **모델 입력 구성:** `text_for_model = title + " / " + body`(제목이 없으면 body만). 제목 포함 여부는 ablation 대상이다(TBD-6).
6. **길이 계산:** `len_chars`(전처리 후 문자 수), `len_eojeol`(공백 기준 어절 수), `len_bucket ∈ {S, M, L}`
7. **중복 처리(데이터셋 구축 시):** 정확 중복은 제거하고, MinHash(5-gram 문자 shingle, 128 perm) Jaccard ≥ 0.9인 근접 중복은 한 그룹으로 묶어 **같은 분할에만** 들어가게 한다.
8. **필터(데이터셋 구축 시):** 한글 문자 비율 < 0.5인 리뷰와 `len_chars < 5`는 제외한다.

### 4.5 AI 리뷰 생성 (`src/realstar_model/data_gen/`)

#### 4.5.1 생성 모델 풀
- 구체적인 모델 ID와 버전은 생성 시점에 확정해 `configs/generators.yaml`과 6장에 기록한다. 라이선스도 함께 기록한다.
- 상용(Q-M02 승인 시): 서로 다른 회사의 소형·중형 모델 2~3종(GPT 계열, Claude 계열, Gemini 계열)
- 오픈(GPU에 따라): 예) `Qwen/Qwen2.5-7B-Instruct`, `naver-hyperclovax/HyperCLOVAX-SEED-Text-Instruct-1.5B`, `kakaocorp/kanana-nano-2.1b-instruct`, `LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct`(비상업 라이선스이므로 연구용으로만 사용)
- 테스트 전용 생성 모델(T_gen): **상용 1종 + 오픈 1종을 학습에서 완전히 제외**한다.

#### 4.5.2 프롬프트 매트릭스
각 샘플마다 아래 변수를 무작위로 뽑는다(`configs/gen_matrix.yaml`).
| 변수 | 값 |
|---|---|
| 카테고리 / 상품 | H1 상품 목록에서 뽑는다. 상품명과 간단한 설명을 넣는다. **학습 분할 상품만 사용한다.** |
| 별점 | 1~5 (H1의 별점 분포가 아니라 균등하게) |
| 목표 길이 | 같은 별점·카테고리 사람 리뷰의 길이 분포에서 샘플링한다(D-007). 프롬프트에는 "약 N자"로 지시한다. |
| 페르소나 | 20대 대학생, 30대 직장인, 40대 주부, 50대 자영업자, 60대 등 10종 이상 + 말투(담백함/수다스러움/불만 많음/꼼꼼함) |
| 참고 리뷰 | 0개(40%) / 실제 사람 리뷰 1~3개(60%). **반드시 학습 분할 H1에서만** 고른다. |
| 휴머나이즈 지시 | 없음(50%) / "실제 구매자처럼 자연스럽게"(25%) / "맞춤법·띄어쓰기를 가끔 틀리고 ㅋㅋ, ㅠㅠ 같은 표현 사용"(25%) |
| 디코딩 | temperature ∈ [0.7, 1.1], top_p ∈ [0.9, 1.0] 균등 샘플링 |

**기본 프롬프트 골격** (모델별 chat template 적용):
```
[system] 너는 쿠팡에서 실제로 상품을 구매한 소비자다. 요청한 리뷰 본문만 출력한다. 인사말, 설명, 따옴표, 제목 표시는 쓰지 않는다.
[user] 상품: {product_name}
설명: {product_desc}
별점: {star}점
작성자: {persona}
분량: 약 {target_chars}자
{reference_block}   # "다음은 다른 구매자들의 리뷰야. 참고만 하고 베끼지 마:\n- ...\n- ..."
{humanize_block}
이 상품에 대한 리뷰를 작성해.
```
- 리뷰 제목도 쓰는 경우는 별도 프롬프트로 생성한다(10~25자).

#### 4.5.3 생성 후 필터링
1. 메타 문구 제거·거부: "다음은", "리뷰입니다", "물론입니다", "작성해 드릴게요", 마크다운 기호(`**`, `#`), 따옴표로 감싼 전체 텍스트 → 정리하고, 정리할 수 없으면 폐기
2. 길이가 목표의 0.5~1.8배 범위를 벗어나면 폐기
3. 한글 비율 < 0.7이면 폐기
4. 참고 리뷰와의 8-gram(문자) 중복 비율 ≥ 0.3이면 폐기(베끼기 방지, 라벨 오염 방지)
5. 4.4의 중복 처리를 적용
6. 각 생성 배치에서 무작위 100건을 `reports/gen_qc/`에 내보내 **사용자 검수**를 요청한다(Q-M06). 검수 결과는 5장에 기록한다.

#### 4.5.4 생성 메타데이터 (모든 AI 샘플에 저장)
`generator_id, generator_version, prompt_template_id, persona_id, humanize_level, n_refs, ref_review_ids, temperature, top_p, target_chars, created_at`

### 4.6 ① 한국어 인코더 분류기 (`models/encoder_clf.py`)
- **후보 모델**(구현 시 Hugging Face에서 존재와 라이선스를 확인한 뒤 기록): `beomi/KcELECTRA-base-v2022`(구어체·댓글 학습), `klue/roberta-large`, `beomi/kcbert-base`. M4에서 셋을 비교해 하나를 고른다.
- **입력:** `text_for_model`, `max_length = 256`(리뷰 95백분위 길이를 확인해 조정), truncation `longest_first`
- **구조:** `AutoModelForSequenceClassification`(num_labels=2)
- **학습 설정(기본값):**
  | 항목 | 값 |
  |---|---|
  | optimizer | AdamW, weight_decay 0.01 |
  | lr | base 모델 3e-5 / large 모델 1e-5, linear decay, warmup 10% |
  | batch size | 32 (gradient accumulation으로 맞춤) |
  | epochs | 최대 5, early stopping(patience 1) |
  | early stopping 기준 | 검증셋 TPR@1%FPR |
  | 정밀도 | fp16/bf16 |
  | 손실 | CrossEntropy. 클래스 비율이 1:1에서 ±10% 이상 벗어나면 class weight 적용 |
  | 시드 | 42, 43, 44 |
- **OOF 학습:** 학습 분할에서 상품 단위 `GroupKFold(n_splits=5)`로 폴드마다 학습해 OOF logit을 만든다. 추론용 최종 모델은 학습 분할 전체로 다시 학습한다(같은 epoch 수 사용).
- **출력 특징:** `f_enc_logit`(log-odds)

### 4.7 한국어 causal LM과 ② Hidden-state Probe

#### 4.7.1 LM 선택 (GPU에 따라, Q-M01)
| VRAM | 후보 (bf16 기준) | 비고 |
|---|---|---|
| 8GB | `Qwen/Qwen2.5-1.5B`, `naver-hyperclovax/HyperCLOVAX-SEED-Text-Instruct-1.5B` | 최소 구성 |
| 16GB | `Bllossom/llama-3.2-Korean-Bllossom-3B`, `Qwen/Qwen2.5-3B` | 권장 |
| 24GB 이상 | `Qwen/Qwen2.5-7B` 또는 동급 한국어 강화 7~8B | 성능 우선 |
- ③ 통계에는 가능하면 **base(사전학습) 모델**을 쓴다. 지시 미세조정 모델은 확률이 왜곡될 수 있다. 후보 2개를 M5에서 비교한다.
- 라이선스를 7장·6장에 기록한다. 상업 이용이 불가한 모델은 연구용으로만 쓴다.
- LM은 학습하지 않는다(가중치 고정, `eval()`, `torch.inference_mode()`).

#### 4.7.2 Probe 특징 추출
1. 입력: `text_for_model`을 LM 토크나이저로 토큰화(max 256 토큰). BOS 토큰만 추가하고 chat template은 쓰지 않는다.
2. `output_hidden_states=True`로 모든 레이어의 hidden state를 얻는다. 패딩과 BOS를 제외하고 **토큰 평균 풀링**을 해 레이어별 벡터 `h_l ∈ R^d`를 만든다.
3. 사용 레이어: 전체 L개 중 **짝수 번째 레이어**(연산량 절감). 결과는 `float16`으로 `data/features/probe/*.npy`에 캐시한다.
4. 레이어별로 두 종류의 점수를 만든다(학습은 OOF 폴드별로):
   - **(a) 로지스틱 회귀 probe:** StandardScaler → `LogisticRegression(C ∈ {0.01, 0.1, 1}, L2)`. C는 내부 CV로 고른다. 출력은 `f_probe_lr_l{l}`(logit).
   - **(b) 평균 차이 방향(steering vector):** `v_l = mean(h_l | ai) − mean(h_l | human)`를 정규화한 뒤 `f_sv_l{l} = cos(h_l − μ_l, v_l)`로 계산한다(μ_l은 학습 폴드 전체 평균). 학습할 파라미터가 거의 없어 분포 이동에 강하다.
5. 메타 분류기에는 레이어별 점수를 모두 넣는다(최대 약 L개 특징). 과적합되면 성능 상위 6개 레이어만 남긴다(M7 ablation으로 결정).

### 4.8 ③ 로그확률 통계 특징 (`features/stats.py`)
같은 LM의 원문 forward 결과(logits)로 계산한다. 토큰 위치 `t = 2..T`(첫 토큰 제외), `p_t(v) = softmax(logits_{t-1})[v]`, 실제 토큰 `x_t`.

| 특징 | 정의 | 설명 |
|---|---|---|
| `mean_logp` | (1/T') Σ_t log p_t(x_t) | AI 글은 높은 경향 |
| `std_logp` | 위 값들의 표준편차 | AI 글은 고르게 높은 경향 |
| `mean_logrank` | (1/T') Σ_t log rank_t(x_t) (rank는 1부터) | GLTR/DetectLLM 계열 |
| `lrr` | −mean_logp / mean_logrank | DetectLLM의 LRR |
| `mean_entropy` | (1/T') Σ_t H_t, H_t = −Σ_v p_t(v) log p_t(v) | 예측 불확실성 |
| `fdgpt_curv` | [Σ_t (log p_t(x_t) − μ_t)] / sqrt(Σ_t σ_t²), μ_t = Σ_v p_t(v) log p_t(v), σ_t² = Σ_v p_t(v)(log p_t(v))² − μ_t² | Fast-DetectGPT의 analytic 조건부 확률 곡률(샘플링 모델 = 점수 모델) |
| `late_mean_logp`, `late_fdgpt_curv` | 위 두 값을 **토큰 후반 50%**에서만 계산 | 후반부 안정성 신호(When AI Settles Down, 2026) |
| `n_tokens` | T' | 짧은 글의 신뢰도를 메타 분류기가 판단하게 함 |

#### 4.8.5 셔플 perplexity 특징 (Luminol 방식)
- 어절(공백 단위) 순서를 고정 시드로 무작위로 섞은 텍스트 K=3개를 만들고, 각각 forward해서 `ppl_shuf_k`를 얻는다. **원문 forward와 별개로 K회 추가 연산이 필요하다.**
- 특징: `shuf_logratio = log(mean_k ppl_shuf_k) − log(ppl_orig)`, `shuf_ratio_std`
- 어절이 3개 미만이면 값을 결측(NaN)으로 둔다. LightGBM이 결측을 처리한다.
- 연산 비용 때문에 ablation에서 기여가 작으면(TPR@1%FPR 개선 < 0.01) 제거한다.

#### 4.8.6 구현 메모
- 배치는 길이 기준으로 정렬해 패딩을 줄인다. `torch.inference_mode`, bf16을 쓴다.
- 엔트로피와 μ_t, σ_t²는 vocab 전체 소프트맥스에서 계산하므로, 배치 크기는 메모리에 맞춰 자동 조절한다.
- 결과는 `data/features/stats/*.parquet`에 캐시한다(키: `sample_id`, `lm_id`).

### 4.9 ④ 한국어 언어 특징 (`features/linguistic_ko.py`)
Kiwi(kiwipiepy)를 쓴다. 한 번 초기화한 인스턴스를 재사용한다. 모든 비율은 분모가 0이면 0으로 둔다.

| 그룹 | 특징 | 정의 |
|---|---|---|
| 띄어쓰기 | `spacing_err_rate` | Kiwi 띄어쓰기 교정 결과와 원문의 공백 위치 차이 수 / 어절 수 |
| 품사 다양성 | `pos_bigram_ttr`, `pos_trigram_ttr` | 고유 품사 n-gram 수 / 전체 품사 n-gram 수 |
| 형태소 | `unk_morph_ratio` | 미등록·분석 불가 형태소 비율(정확한 태그는 구현 시 Kiwi 문서로 확인해 기록) |
| 종결 | `ending_diversity` | 고유 종결어미 수 / 문장 수 |
| | `polite_ratio` | 해요체·합쇼체 종결 비율 |
| | `nominal_ending_ratio` | 명사형 종결(~음, ~함, ~임) 비율 |
| 문장 | `sent_len_mean`, `sent_len_std`, `sent_len_cv` | 문장 길이(어절) 평균, 표준편차, 변동계수 |
| 구두점 | `comma_per_sent`, `exclaim_count`, `question_count`, `tilde_count`, `ellipsis_count`, `period_per_sent` | 각 기호 사용량 |
| 구어 표현 | `laugh_count`(ㅋ·ㅎ 반복), `cry_count`(ㅠ·ㅜ 반복), `jamo_only_ratio`, `emoji_count`, `emoticon_count`(^^, ;; 등) | 정규식 |
| 문자 구성 | `digit_ratio`, `latin_ratio`, `hanja_ratio`, `repeat_char_max`(같은 글자 최대 연속 수) | 문자 단위 |
| AI 상투구 | `ai_phrase_hits`(정규화), `ai_phrase_types` | `lexicons/ai_phrases_ko.txt` 사전 매칭. 사전은 학습 데이터에서 AI 쪽 log-odds 상위 n-gram 후보를 뽑아 사람이 검토해 만든다. **테스트 분할로는 만들지 않는다.** |
| 구조 | `list_marker_count`(`-`, `•`, `1.`, `장점:`, `단점:` 등), `has_summary_phrase`("총평", "결론적으로") | 구조화 서식 |
| 기타 | `newline_count`, `zw_count`, `is_cash_event`, `is_sponsored` | 전처리 단계에서 얻은 값 |
| 길이 | `len_chars`, `len_eojeol` | 4.4 |

- **해석 태그 매핑:** 각 특징을 "구어체 표현", "불규칙한 띄어쓰기", "정형화된 문장 구조", "AI 상투 표현" 같은 사람이 읽을 수 있는 태그에 연결하는 표를 `features/reason_tags.yaml`에 둔다(서비스의 근거 태그용).

### 4.10 ⑤ 메타 분류기, 보정, 임계값

#### 4.10.1 메타 분류기 (`fusion/meta.py`)
- **입력 특징:** `f_enc_logit` + probe 점수들 + 4.8 통계 + 4.9 언어 특징 + 길이. 모두 OOF이거나 비지도 특징이다(D-005).
- **모델:** LightGBM(binary)
  | 파라미터 | 기본값 |
  |---|---|
  | learning_rate | 0.05 |
  | num_leaves | 31 |
  | min_data_in_leaf | 50 |
  | feature_fraction | 0.8 |
  | bagging_fraction / freq | 0.8 / 1 |
  | lambda_l2 | 1.0 |
  | n_estimators | 최대 3000, early stopping 100 (검증셋 logloss) |
- **비교 대상:** 표준화 + 로지스틱 회귀(L2). 검증셋 TPR@1%FPR이 더 좋은 쪽을 쓰고, 차이가 0.01 이내면 단순한 로지스틱 회귀를 쓴다.
- 특징 중요도(gain)와 SHAP 요약을 `reports/`에 저장한다.

#### 4.10.2 확률 보정 (`fusion/calibrate.py`)
- 보정용 데이터는 **보정·검증 분할(val)**만 쓴다(학습 분할 사용 금지).
- val의 샘플이 2,000건 이상이면 Isotonic Regression, 미만이면 Platt scaling을 쓴다.
- 보정 전후 ECE(15 bins)와 reliability diagram을 저장한다.

#### 4.10.3 임계값 (`fusion/thresholds.py`, D-004)
길이 구간 b ∈ {S, M, L}마다 val 보정 확률로 정한다.
- `T_AI[b]` = val의 사람 샘플 `p_ai` 분포에서 **98백분위수**. 사람 오판율 ≤ 2%를 뜻한다(TBD-3에 따라 조정).
- `T_HUMAN[b]` = val의 AI 샘플 `p_ai` 분포에서 **5백분위수**. AI 통과율 ≤ 5%를 뜻한다.
- 판정: `p_ai ≥ T_AI[b]` → ai, `p_ai ≤ T_HUMAN[b]` → human, 그 외 → uncertain
- `T_HUMAN[b] ≥ T_AI[b]`(보류 구간이 없음)이면 두 값을 그 중간값으로 같게 두고 5장에 기록한다.
- `len_chars < MIN_CHARS(20)`이면 무조건 uncertain이다.
- 구간별 표본이 300건 미만이면 인접 구간과 합쳐서 정하고 기록한다.

#### 4.10.4 시간 추세 점검 (T_time, U1)
- T_time(학습 제외 상품 50개의 2022-11 이전 사람 리뷰)에서 **실제 FPR**을 측정한다. 이 값이 실전 오판율의 가장 현실적인 추정치다.
- U1(2023년 이후 리뷰, 라벨 없음)에 대해 월별 `ai` 비율을 그래프로 만든다. 2022-11 이전 구간은 거의 0이고 이후 증가하는 형태가 기대된다. 그래프와 해석을 리포트에 넣는다.

#### 4.10.5 집계 시뮬레이션 (서비스 관점 평가)
- 테스트 분할에서 가상 상품 200개를 만든다. 별점마다 사람 비율 `r_s`를 0~1에서 무작위로 정하고, 별점당 100개를 뽑는다.
- 모델 라벨로 `r̂_s = h_s / (h_s + a_s)`를 계산해 다음을 보고한다.
  - MAE(r̂_s, r_s)
  - 사람 리뷰 기준 평균 오차(루트 README 5.4 공식 사용)
  - 판단 보류 비율
- Rogan–Gladen 보정 전후를 비교한다. 민감도와 특이도는 val에서 추정한다.

### 4.11 평가 프로토콜 (`eval/`)

#### 4.11.1 분할
| 분할 | 구성 | 용도 |
|---|---|---|
| `train` | 학습 상품, 학습 생성 모델 | ①② 학습(OOF 5-fold 포함), ⑤ 학습 |
| `val` | 학습 상품과 겹치지 않는 상품, 학습 생성 모델 | 보정, 임계값, early stopping |
| `t_iid` | val과 같은 조건의 별도 상품 | 같은 분포 성능 |
| `t_gen` | 테스트 전용 생성 모델 2종의 AI 샘플 + t_iid 사람 샘플 | 새 생성 모델 일반화 |
| `t_cat` | 학습에서 뺀 카테고리 1~2개 | 새 카테고리 일반화 |
| `t_time` | 학습 제외 상품 50개의 쿠팡 사람 리뷰 | 실전 FPR |
| `t_attack` | t_iid AI 샘플에 공격을 적용한 것 | 강건성 |
| `u1` | 2023년 이후 쿠팡 리뷰(라벨 없음) | 추세 점검 |
- 대략적인 비율: train 70% / val 10% / t_iid 10% / 나머지 테스트용 상품·생성 모델은 별도 확보. 모든 분할은 **상품 단위**로 나누고, 근접 중복 그룹은 한 분할에만 넣는다(D-008).
- 분할 파일은 `data/splits/*.parquet`(sample_id 목록)로 고정하고, 해시를 데이터 버전으로 쓴다.

#### 4.11.2 지표
- 주 지표: TPR@FPR=1%, 2%
- 보조 지표: AUROC, AUPRC, ECE, 판단 보류 비율, 확정 판정(ai/human) 정확도
- 모든 지표를 길이 구간(S/M/L)별, 별점별, 생성 모델별로도 보고한다.
- 1,000회 부트스트랩 95% 신뢰구간과 시드 3개의 평균±표준편차를 함께 낸다.

#### 4.11.3 베이스라인 (반드시 함께 보고)
| ID | 베이스라인 | 목적 |
|---|---|---|
| B0 | 길이·줄바꿈·문장부호 수만 쓴 로지스틱 회귀 | 지름길 점검. 이 값이 높으면 데이터 아티팩트를 의심하고 원인을 찾는다. |
| B1 | 문자 n-gram(2~5) TF-IDF + 로지스틱 회귀 | 고전적인 강한 기준선 |
| B2 | Fast-DetectGPT 단독(`fdgpt_curv` 임계값) | zero-shot 기준선 |
| B3 | ① 인코더 단독 | 메인 모델 단독 성능 |

#### 4.11.4 Ablation (M7)
"전체 모델 − 구성 요소 하나"를 ②, ③(셔플 제외), ③셔플, ④, 제목 포함, `newline_count` 포함 각각에 대해 실험한다. 각 결과를 T_iid, T_gen, T_time의 TPR@1%FPR로 표에 정리한다.

#### 4.11.5 강건성 공격 세트 (`t_attack`)
1. 다른 LLM으로 다시 쓰기(paraphrase)
2. 무작위 오타 주입(자모 치환, 3%)
3. 띄어쓰기 무작위 제거·추가(10%)
4. ㅋㅋ·이모지 삽입
5. 문장 순서 섞기
6. 제로폭 문자 삽입

공격별 TPR 하락폭을 보고한다.

### 4.12 폴더 간 계약 (model ↔ service)

#### 4.12.1 데이터 계약: service → model (학습용 쿠팡 리뷰)
- `service/`의 스크래퍼가 `model/data/raw/coupang/{YYYYMMDD}_{batch}.jsonl`로 내보낸다. 한 줄은 리뷰 1건이다.
```json
{"review_id": "str", "product_id": "str", "category": "str|null", "product_name": "str",
 "star": 1, "title": "str|null", "content": "str", "created_at": "YYYY-MM-DD",
 "has_photo": true, "helpful_count": 0, "collected_at": "YYYY-MM-DDTHH:MM:SS+09:00",
 "source": "coupang_scraper", "scraper_version": "str"}
```
- 작성자 식별 정보는 포함하지 않는다. `model/`은 이 파일을 읽기만 한다.

#### 4.12.2 추론 API 계약: model → service
- `model/`은 설치 가능한 패키지 `realstar_model`을 제공한다(`pip install -e ../model`).
```python
from realstar_model.inference import Detector, ReviewInput

det = Detector.load("artifacts/det-ko-review-v1.0")   # manifest.json 기준으로 로드
preds = det.predict([ReviewInput(review_id="r1", title="...", content="...", star=5)],
                    batch_size=64)
# -> list[Prediction(review_id, p_ai, p_human, label, len_bucket, features: dict,
#                    reason_tags: list[str], model_version)]
from realstar_model.preprocess import clean_review   # 서비스 전처리도 이 함수를 그대로 사용
```
- `service/apps/detector_server`가 이 패키지를 import해 HTTP `/predict`로 제공한다. 서버 코드는 service 쪽 담당이다.
- `predict`는 내부에서 반드시 4.4 전처리를 적용한다. 서비스가 전처리를 다시 구현하지 않는다.

#### 4.12.3 모델 아티팩트 구조
```
artifacts/det-ko-review-v1.0/
├── manifest.json          # model_version, created_at, git_commit, data_version, lm_id, encoder_id,
│                          # feature_list, thresholds{S,M,L}, min_chars, metrics_summary, licenses
├── encoder/               # HF save_pretrained 결과
├── probe/                 # 레이어별 scaler·LR·sv 벡터 (joblib)
├── meta_lgbm.txt          # LightGBM 모델
├── calibrator.joblib
├── lexicons/              # ai_phrases_ko.txt, boilerplate_patterns.yaml 사본
└── reason_tags.yaml
```
- LM 가중치는 아티팩트에 넣지 않고 `lm_id`(Hugging Face ID와 revision 해시)로 참조한다.
- 버전 규칙: 특징 구성이나 데이터가 크게 바뀌면 MAJOR, 재학습이나 임계값 조정은 MINOR.

### 4.13 추론 성능 목표와 최적화
- 리뷰 500개 기준, 16GB GPU 목표 60초 이내
- 최적화:
  - 인코더와 LM을 한 프로세스에 상주시킨다.
  - 길이로 정렬한 배치를 쓰고, bf16을 쓴다.
  - 셔플 K는 ablation 결과로 줄이거나 없앤다.
  - Kiwi는 멀티프로세스로 병렬 처리한다.
- CPU 전용 저하 모드: ①과 ④만으로 동작하는 경량 메타 모델을 별도로 학습해 둔다(`det-ko-review-v1.0-lite`).

### 4.14 위험 요소와 점검 목록
| 위험 | 점검 방법 |
|---|---|
| 플랫폼 차이 지름길(H2 네이버 vs 쿠팡) | 사람 데이터를 H1만 썼을 때와 H1+H2를 썼을 때의 T_time 성능 비교 |
| 수집 경로 아티팩트(줄바꿈, 공백, 특수문자) | B0 성능, `newline_count` ablation, 전처리 후 문자 분포 비교표 |
| 참고 리뷰 베끼기로 인한 라벨 오염 | 4.5.3의 8-gram 필터, 생성 샘플과 사람 샘플 간 최근접 유사도 분포 확인 |
| 테스트 누수 | 상품·근접 중복 그룹 단위 분할, AI 상투구 사전을 train에서만 구축 |
| 생성 AI 리뷰가 실제보다 쉬움 | 사용자 검수(Q-M06), t_gen·t_attack 성능, U1 추세 확인 |
| 짧은 리뷰 과신 | 길이 구간별 임계값, S 구간 판단 보류 비율 보고 |

---

## 5. 실험 기록 (Experiment Log)

> 형식: `### EXP-YYYYMMDD-NN — 제목` → 목적 / 설정 파일 / 데이터 버전 / 결과 표 / 해석 / 다음 조치. 실패한 실험도 기록한다.

(아직 없음)

---

## 6. 작업 로그 (Work Log)

> 형식: `### YYYY-MM-DD — 작업 제목` → 한 일 / 변경 파일 / 결과 / 남은 문제 / 다음 할 일. 최신 항목을 아래에 추가한다.

### 2026-11-13 — 문서 최초 작성
- 한 일: 기획 대화에서 확정된 탐지 모델 설계를 이 문서로 정리했다. 폴더 분리 원칙(D-009)과 문서 운영 규칙(0장)을 수립했다.
- 변경 파일: `model/MODEL_DEV.md`(신규)
- 결과: 4장 기술 명세 v1, 결정 D-001~D-009, 요청 R-001~R-005
- 남은 문제: Q-M01~Q-M06 답변 대기
- 다음 할 일: 8장 M0부터 시작

---

### 2026-11-17 — 학습 데이터 수집기 추가 (R-006)
- 한 일: `collect_training_data.py`(루트) 작성. `naver`(bab2min/corpus 네이버 쇼핑 20만 건 → JSONL, 중복 92건 제거, 199,908건), `collect`(쿠팡 H1·U1, 상품 단위 이어서 수집, 차단 시 즉시 중단), `inspect`(정렬·이진 탐색 점검), `stats`(별점×길이×기간 분포, 4.2.2 목표 대비). 상품 목록 템플릿 `training_products.txt`.
- 바꾼 파일: `collect_training_data.py`, `training_products.txt`, `service/tests/unit/test_collect_training_data.py`, `service/tests/fakes/scrapling/fetchers.py`(페이지 상한 흉내), 이 문서.
- 결과: 가짜 쿠팡 응답으로 검증(이전 리뷰 날짜 < 2022-11-30, 이후 ≥ 2023-01-01, 중복 0, 이어서 수집, 차단 시 중단). 실제 쿠팡에서 `sortBy=DATE_DESC`가 최신순으로 동작하는지는 미확인 → 사용자 PC에서 `inspect`로 확인 필요.
- 네이버 H2 분포: 5점 81,170 / 4점 18,783 / 2점 63,948 / 1점 36,007 (3점 없음), 길이 S 101,072 / M 87,971 / L 10,865. L 구간과 3점은 H1에서 채워야 한다.
- 남은 문제: Q-M08(이후 리뷰 라벨 방침), 상품 목록 작성(Q-M07).
- 다음 할 일: 1장 참고.

---

### 2026-11-17 — 카테고리 모드 추가 (R-007)
- 한 일: `collect_training_data.py category` — 카테고리 목록 페이지 순회(새 상품이 없으면 중단, 목록은 _state.json에 저장해 재사용), 상품별 과거 리뷰 확인(2~4회 요청), 상품당 최대 40개 수집, 확인 결과(수집/건너뜀) 기록. `stats`에 카테고리별 수집/건너뜀 수. 템플릿 `training_categories.txt`.
- 결과: 가짜 쿠팡 응답으로 검증(과거 리뷰 없는 상품 건너뜀, 상품당 상한, 별점 배분, 이어서 실행). 실제 쿠팡 카테고리 목록 페이지가 열리는지(403 여부)와 목록 HTML에서 상품 링크가 잡히는지는 사용자 PC에서 확인 필요.
- 다음 할 일: 카테고리 2~3개로 시험 실행 → 결과 확인 후 확대.

---

### 2026-11-19 — 병렬 수집·JSON 하나·상품 단위 실시간 저장 (R-008)
- 한 일: `--workers N` 병렬 수집(작업자 프로세스·프로필 사본·전체 요청 간격 제한·차단 시 전체 중단·Ctrl+C 시 정리), 저장을 `coupang_training.json` 하나로 변경(상품마다 원자적 저장, summary 자동 갱신), 이전 JSONL·_state.json 자동 이관, `stats`가 JSON을 읽도록 변경. 테스트용 대기 배율(COLLECT_DELAY_SCALE).
- 결과: 가짜 쿠팡 응답으로 검증 — 작업자 2개가 상품을 나눠 처리, 리뷰 중복 0, 한 작업자 차단 시 모두 중단·끝난 상품만 저장·재실행 시 이어서, 프로세스 3개 사이 요청 간격 0.3초 유지, Ctrl+C 후 JSON 유효. 실제 쿠팡에서 작업자 수에 따른 차단 빈도는 미확인.
- 하지 않은 것: 작업자마다 다른 IP(R-008 ①의 일부) — D-012 참고.
- 다음 할 일: 사용자 PC에서 `--workers 2`로 시험 → 차단 여부를 보고 수·간격 조정.

---

## 7. 열린 질문 (사용자에게 확인 필요)

| ID | 질문 | 왜 필요한가 | 임시 기본값 | 상태 |
|---|---|---|---|---|
| Q-M01 | 학습·추론에 쓸 GPU와 VRAM 용량은? (로컬, Colab, 클라우드) | LM 크기(4.7.1), 로컬 생성 가능 여부 | 16GB 가정, 3B LM | 대기 |
| Q-M02 | AI 리뷰 생성에 상용 LLM API(GPT/Claude/Gemini)를 써도 되나? 쓴다면 월 예산은? (서비스 수집은 비 API 방식으로 정했지만, 학습 데이터 생성은 별개) | 실제 AI 리뷰 대부분이 상용 모델로 작성되므로 데이터 대표성에 큰 영향 | 오픈 모델만 사용 | 대기 |
| Q-M03 | 상업적으로 이용할 계획이 있나? | 모델 라이선스 선택(EXAONE 등 비상업 라이선스) | 연구·발표용 | 대기 |
| Q-M04 | 데이터 규모 목표(사람 2.5만 / AI 2.5만)로 진행해도 되나? | 수집 기간·생성 비용 | 2.5만 / 2.5만 | 대기 |
| Q-M05 | AI가 다듬은 사람 리뷰(혼합)를 별도 클래스로 둘까, AI로 합칠까? | 라벨 체계 | v1은 AI로 통합, 하위 유형만 기록 | 대기 |
| Q-M06 | 생성된 AI 리뷰 샘플 100건 검수를 직접 해줄 수 있나? | 생성 데이터가 실제 AI 리뷰처럼 보이는지 확인 | 검수 요청 예정 | 대기 |
| Q-M07 | H1 수집용 상품 목록(200~500개)을 사용자가 정할까, 에이전트가 후보를 만들어 승인받을까? | 카테고리 균형, 수집 일정 | 에이전트가 후보를 만들고 사용자가 승인 | 대기 |
| Q-M08 | 2022-11-30 이후 작성된 쿠팡 리뷰를 전부 AI 라벨로 쓸까, 아니면 기존 설계대로 라벨 없음(U1)으로 두고 AI 라벨은 LLM으로 생성한 리뷰(A1·A2)로 만들까? | 이후 리뷰 대부분은 여전히 사람이 쓴 것이라, 전부 AI로 두면 라벨 오류가 크고 모델이 AI 문체 대신 시기 차이(신상품·이벤트 문구·최근 말투)를 배운다. 평가(T_time FPR)도 의미가 없어진다. | 기존 설계 유지: 이후 리뷰는 U1(추세 점검), AI 라벨은 생성 데이터 | 대기 |

---

## 8. 모델 개발 단계 (Milestones)

> 루트 README의 Phase 1(데이터셋·베이스라인)과 Phase 2(융합·보정)를 세분화한 것이다.

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| **M0** 환경 | `model/` 패키지 골격(9장), pyproject, configs, pytest·ruff CI, GPU 확인 스크립트 | `pytest` 통과, GPU·패키지 버전 리포트를 6장에 기록 |
| **M1** 사람 데이터 | H2 다운로드·정제. H1 수집 사양(4.2.3)을 사용자에게 전달하고, 받은 JSONL을 적재·검증. 전처리(4.4) 구현과 테스트 | 원천별 건수, 별점×길이 분포표, 전처리 단위 테스트 |
| **M2** AI 데이터 | 생성 파이프라인(4.5), 필터, 메타데이터, 사용자 검수 | 생성 모델별 건수, 필터 탈락률, 검수 결과 |
| **M3** 데이터셋 | 중복 그룹, 분할(4.11.1), 데이터 버전 고정 | 분할별 건수·분포표, 누수 점검 결과(상품·근접 중복 교차 0건) |
| **M4** 베이스라인 | B0, B1, B2, ① 인코더 후보 3종 비교(OOF 포함) | 평가 리포트(4.11.2 형식). **사용자에게 중간 보고** |
| **M5** 특징 | ② probe, ③ 통계·셔플, ④ 언어 특징 구현과 캐시 | 특징별 단독 성능표, 단위 테스트 |
| **M6** 융합 | ⑤ 메타 분류기, 보정, 길이 구간별 임계값 | val·t_iid 성능, ECE, 임계값 표 |
| **M7** 평가 | 전체 테스트 분할, ablation, 공격, 시간 추세, 집계 시뮬레이션 | 최종 평가 리포트 `reports/final_v1.md`, 4.0 Go 조건 판정 |
| **M8** 패키징 | 추론 API(4.12.2), 아티팩트(4.12.3), lite 모델, 추론 속도 측정 | `Detector.load().predict()` 예제 동작, 속도 리포트 |
| **M9** 인계 | service 측에 사용법 문서 전달, 계약 테스트 | `model/docs/inference_usage.md`, 계약 테스트 통과 |

---

## 9. `model/` 폴더 구조

```
model/
├── MODEL_DEV.md                  # ← 이 문서 (항상 최신)
├── pyproject.toml                # 패키지명 realstar_model
├── configs/
│   ├── data.yaml                 # 원천 경로, 규모, 분할 비율
│   ├── generators.yaml           # 생성 모델 목록, 버전, 라이선스
│   ├── gen_matrix.yaml           # 프롬프트 변수 분포
│   ├── encoder.yaml
│   ├── lm_features.yaml          # LM ID, 레이어, 셔플 K
│   ├── meta.yaml
│   └── eval.yaml
├── src/realstar_model/
│   ├── preprocess/               # clean.py, boilerplate_patterns.yaml, dedup.py
│   ├── data_gen/                 # prompts.py, generate.py, filters.py, clients/
│   ├── datasets/                 # build.py, split.py, versioning.py
│   ├── features/                 # stats.py, probe.py, linguistic_ko.py, reason_tags.yaml
│   ├── models/                   # encoder_clf.py
│   ├── fusion/                   # meta.py, calibrate.py, thresholds.py
│   ├── eval/                     # metrics.py, report.py, attacks.py, aggregate_sim.py, temporal.py
│   └── inference/                # detector.py (공개 API), schemas.py
├── scripts/                      # 단계별 실행 진입점: m1_build_human.py, m2_generate.py, ...
├── lexicons/                     # ai_phrases_ko.txt
├── tests/
├── docs/                         # inference_usage.md
├── reports/                      # experiments.csv, EXP-*/, gen_qc/, final_v1.md   (git 추적)
├── data/                         # (gitignore) raw/, interim/, processed/, features/, splits/
└── artifacts/                    # (gitignore) det-ko-review-v*/
```

---

## 10. 참고 연구 (설계 근거)
| 기법 | 이 프로젝트에서의 사용처 |
|---|---|
| Fast-DetectGPT (ICLR 2024): 조건부 확률 곡률 | 4.8 `fdgpt_curv` |
| DetectLLM / GLTR: log-rank, LRR | 4.8 |
| Luminol-AIDetect (2026): 셔플 전후 perplexity | 4.8.5 |
| When AI Settles Down (EMNLP 2026 Findings): 후반부 안정성 | 4.8 `late_*` |
| RepreGuard (TACL 2025), SV-Detect (2026), Linear Probing (2026): 내부 표현 방향 | 4.7.2 |
| Rethinking AI-Generated Text Detection (2026): 미세조정 베이스라인의 강함, 저FPR 평가, 분포 밖 과신 | 4.6, D-003 |
| KatFishNet (ACL 2025): 한국어 띄어쓰기·품사·쉼표 특징 | 4.9 |
| TOCSIN (EMNLP 2024), DivEye (TMLR 2026): 이질적 신호 결합의 효과 | D-001 |
| Measuring Artifact Reliance (2026): 데이터 추출 아티팩트 지름길 | D-006, B0 |
| EditLens (ICLR 2026), DetectRL-X (ACL 2026): AI 편집·혼합 텍스트 | A3, Q-M05 |