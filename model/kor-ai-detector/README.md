# 한국어 AI 생성 리뷰 탐지 모델 개발 가이드

상품 리뷰가 **사람이 쓴 것인지, AI(LLM)가 쓴 것인지** 판별하는 분류 모델을 만드는 절차를 정리한 문서입니다.
데이터 준비부터 2단계 파인튜닝, 평가, XDAC 기준선 비교, 실서비스 적용까지 순서대로 다룹니다.

---

## 1. 개요

### 1.1 목표
- 입력: 한국어 상품 리뷰 텍스트 1건
- 출력: `P(AI)` (0~1, AI가 썼을 확률)와 판정(사람 / AI / 판단 보류)
- 운영 기준: **사람 리뷰를 AI로 오판하는 비율(FPR)을 1% 이하로 묶은 상태에서** AI 리뷰를 최대한 많이 잡는 것

### 1.2 접근 방식 한눈에 보기

```
[한국어 인코더 모델]  beomi/KcELECTRA-base-v2022 (기본값)
        │
        ▼  1단계 파인튜닝: LGC 뉴스 댓글 (사람 130만 + AI 100만, 14개 LLM)
[댓글 탐지 모델]  → 짧은 구어체 한국어에서 "AI 말투"를 학습
        │
        ▼  2단계 파인튜닝: 리뷰 데이터 (네이버/쿠팡 사람 리뷰 + 팀 생성 AI 리뷰)
        │                  + LGC 댓글 15% 섞기(이전 학습 내용 망각 방지)
[리뷰 탐지 모델]  → 최종 모델
        │
        ▼  평가: 검증셋에서 임계값 결정 → 여러 테스트셋에서 성능 확인
        │        XDAC-D(공개 모델)를 같은 기준으로 돌려 비교
```

### 1.3 왜 이 구조인가
| 결정 | 이유 |
|---|---|
| 생성형 LLM이 아닌 **인코더 분류 모델** | 리뷰는 짧고 대량이라 빠르고 저렴한 모델이 유리. 인코더가 문장을 벡터로 만들고, 그 위의 분류층이 `P(AI)`를 냅니다. |
| **KcELECTRA** 기본 사용 | 네이버 뉴스 댓글 같은 구어체·이모지·신조어 위주로 사전학습되어 댓글·리뷰 문체와 잘 맞습니다. 성능이 부족하면 `klue/roberta-large`로 바꿔 비교하세요. |
| XDAC 모델을 **직접 파인튜닝하지 않음** | XDAC는 가중치가 암호화된 모듈(`xdac_encrypted.py`)로 배포되어 추론만 됩니다. 대신 XDAC가 공개한 **LGC 데이터**로 우리 모델을 학습하고, XDAC-D는 비교용 기준선으로만 씁니다. |
| **2단계** 학습 | LGC(댓글)는 양이 많아 "AI 말투" 기본기를 잡기 좋고, 리뷰 데이터는 실제 목표 도메인에 맞추는 역할을 합니다. |
| 사람 데이터만이 아니라 **AI 리뷰도 함께** 2단계에 투입 | 이진 분류는 두 클래스가 모두 있어야 학습됩니다. 같은 도메인의 AI 리뷰가 없으면 모델이 "댓글 vs 리뷰"를 구분하는 쪽으로 잘못 학습됩니다. |

---

## 2. 파일 구성

```
kor-ai-detector/
├── README.md            ← 이 문서
├── requirements.txt
├── prepare_data.py      데이터 통합·정제·분할 (1단계/2단계 데이터 생성)
├── train.py             파인튜닝 (1단계·2단계 공용)
├── evaluate.py          임계값 결정 + 테스트셋 평가 리포트
├── xdac_baseline.py     XDAC-D 기준선 점수 생성
├── metrics.py           AUROC, FPR 기준 임계값 등 지표 함수
└── tests/smoke_test.py  GPU 없이 도는 점검 스크립트
```

---

## 3. 환경 설정

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python tests/smoke_test.py      # 데이터 처리·평가 로직 점검 (GPU·모델 불필요)
```

- 학습은 GPU 1장(예: 24GB 이상) 기준으로 설계했습니다. `--fp16`(또는 A100/H100이면 `--bf16`)을 켜세요.
- XDAC 기준선을 돌리려면 Hugging Face에 로그인하고 `keepsteady/XDAC_obs` 접근 승인을 받아야 합니다.

---

## 4. 데이터 준비

### 4.1 데이터 현황과 역할

| 데이터 | 상태 | 라벨 | 쓰임 |
|---|---|---|---|
| LGC 뉴스 댓글 | 준비됨 | 사람 + AI | 1단계 학습, 2단계 replay |
| 네이버 쇼핑 리뷰 | 준비됨 | 사람 | 2단계 학습·검증·테스트 |
| 쿠팡 리뷰 | 수집 중 | 사람 | 처음엔 **플랫폼 교차 테스트 전용**, 이후 학습에 합류 |
| 팀 생성 AI 리뷰 | 생성 예정 | AI | 2단계 학습·검증·테스트 (ChatGPT, Claude, Gemini) |

### 4.2 LGC 데이터 필드 확인
XDAC 안내 코드로 내려받은 뒤 필드 구조를 먼저 확인하세요.

```python
from pprint import pprint
pprint(dataset_LGC[0]); pprint(dataset_LGC[-1])
```

확인한 필드명을 `prepare_data.py`에 넘깁니다.

| 옵션 | 의미 | 예 |
|---|---|---|
| `--lgc-text-field` | 댓글 본문 필드 | `text` |
| `--lgc-label-field` | 사람/AI 라벨 필드 | `label` |
| `--lgc-ai-values` | 라벨 값 중 **AI를 뜻하는 값들** (쉼표 구분) | `1` 또는 `llm,ai` |
| `--lgc-generator-field` | (있으면) 생성 모델명 필드 | `model` |
| `--lgc-group-field` | (있으면) 기사 ID 필드. 같은 기사 댓글이 학습/테스트에 흩어지지 않게 함 | `article_id` |

실행 후 출력되는 `lgc_raw_label_values`에서 라벨 값 분포를 꼭 확인하세요. AI 값 지정이 틀리면 전부 사람으로 처리됩니다.

### 4.3 리뷰 데이터 공통 형식
사람 리뷰와 AI 리뷰 모두 아래 컬럼을 갖춘 `.csv` / `.jsonl` / `.json`으로 맞춥니다.

| 컬럼 | 사람 리뷰 | AI 리뷰 | 설명 |
|---|---|---|---|
| `text` | 필수 | 필수 | 리뷰 본문 |
| `product_id` | 필수 | 필수 | 상품 ID. **분할 기준**이므로 AI 리뷰도 원본 상품 ID를 그대로 기록 |
| `platform` | 필수 | 권장 | `naver`, `coupang`. AI 리뷰는 "어느 플랫폼 상품을 보고 만들었는지" |
| `generator` | – | 필수 | `chatgpt`, `claude`, `gemini` (모델군 단위) |
| `model_version` | – | 권장 | 실제 모델명·버전 |
| `prompt_type` | – | 권장 | `scratch` / `rewrite` / `style` (4.5절) |
| `date` | 권장 | – | `YYYY-MM-DD`. `--human-before` 필터에 사용 |
| `rating`, `category` | 권장 | 권장 | 분포 비교·세부 분석용 |

### 4.4 사람 데이터 정제 원칙
1. **2022년 12월 이전 리뷰 위주로 사용** (`--human-before 2022-12-01`). ChatGPT 공개 이후 리뷰에는 이미 AI가 쓴 글이 섞여 있을 수 있어 "사람" 라벨이 오염됩니다. 날짜가 없는 리뷰 수는 `human_no_date`로 보고됩니다.
2. **개인정보 제거**: 이름, 전화번호, 주소, 주문번호 등은 수집 단계에서 마스킹하세요.
3. **줄바꿈·연속 공백·반복 문자(ㅋㅋ, ㅎㅎ)는 지우지 않습니다.** XDAC 연구에서 사람과 AI를 가르는 핵심 신호였습니다. 스크립트도 유니코드 정규화와 보이지 않는 문자 제거만 합니다.
4. 플랫폼이 자동으로 붙이는 문구(옵션명, "한 달 사용 후기" 태그, 추천 수 등)는 **본문에서 떼어내세요.** 남겨 두면 모델이 "네이버 서식 = 사람"이라는 지름길을 배웁니다.
5. 데이터 수집 방식은 각 플랫폼 이용약관과 법적 검토를 거치세요.

### 4.5 AI 리뷰 생성 가이드 (팀 작업)
가장 중요한 원칙은 **사람 리뷰와 AI 리뷰가 "AI다움" 외에는 최대한 같은 분포를 갖게 하는 것**입니다. 그렇지 않으면 모델이 길이·별점·상품 같은 엉뚱한 차이로 분류합니다.

**(1) 분포 맞추기**
- 사람 리뷰가 있는 **같은 상품(`product_id`)** 에 대해 생성합니다.
- 별점은 해당 상품의 사람 리뷰 별점 분포에서 뽑아 조건으로 줍니다.
- **목표 길이도 사람 리뷰 길이 분포에서 뽑아** 프롬프트에 넣습니다 ("2문장 이내", "40자 내외" 등). LLM은 기본적으로 사람보다 길게 씁니다.
- 생성량은 2단계 전체에서 **AI 리뷰 수 ≈ 사람 리뷰 수**, 모델군별로 비슷하게 맞춥니다.

**(2) 생성 유형 세 가지를 섞기** (`prompt_type`에 기록)

| 유형 | 방법 | 비중(권장) |
|---|---|---|
| `scratch` | 상품명·카테고리·별점·페르소나(연령대, 구매 목적, 말투)만 주고 처음부터 작성 | 40% |
| `style` | 같은 상품의 실제 사람 리뷰 3~5개를 예시로 주고 "이런 말투로 새 리뷰 작성" | 30% |
| `rewrite` | 실제 사람 리뷰 1개를 주고 다듬기·바꿔쓰기 (**가장 어려운 사례**, 실제 악용과 가장 비슷) | 30% |

`rewrite`에 쓴 원본 사람 리뷰는 반드시 같은 `product_id`로 기록하세요. 그래야 원본과 재작성본이 같은 split에 묶여 누출이 생기지 않습니다.

**(3) 다양성 확보**
- 각 모델군 안에서도 가벼운 모델과 상위 모델을 섞고, temperature를 0.7~1.1 범위에서 바꿔 가며 생성합니다.
- 페르소나와 말투 지시(반말/존댓말, 이모지 사용 여부, 오타 허용 등)를 무작위로 조합합니다.

**(4) 후처리**
- 모델이 붙인 안내 문구("물론입니다! 다음은 리뷰입니다:", "리뷰:" 접두어, 감싼 따옴표)와 거절 응답은 `prepare_data.py`가 자동으로 정리·제거합니다. 정리 건수는 `ai_meta_cleaned`, `ai_refusal_dropped`로 보고됩니다.
- 그 밖의 내용은 손대지 않습니다. 실제 조작자도 메타 문구만 지우고 올리기 때문입니다.

**(5) 처음 보는 모델 평가용 데이터 남기기**
- 모델군이 3개뿐이므로, **하나를 학습에서 빼고 테스트하는 실험을 3번 돌려**(leave-one-generator-out) 일반화 성능을 추정합니다. 최종 모델은 3개 모두로 학습합니다.
- 가능하면 학습에 전혀 쓰지 않을 **네 번째 출처**(국내 모델이나 오픈소스 모델 등)로 소량을 만들어 최종 테스트 전용으로 보관하세요. 실제 악용에는 저렴한 오픈소스 모델이 많이 쓰입니다.
- holdout 모델의 리뷰는 기본적으로 **테스트 split 상품의 것만** 평가에 쓰입니다(누출 차단). 그만큼 표본이 줄어드니 holdout 모델 리뷰는 넉넉히 만들거나, `--holdout-all-groups`로 모두 쓰되 결과를 조금 낙관적으로 해석하세요.

### 4.6 `prepare_data.py` 실행

```bash
python prepare_data.py \
  --lgc ./XDAC_obs/LGC_data/LGC_data_v1.0.json \
  --lgc-text-field <본문필드> --lgc-label-field <라벨필드> --lgc-ai-values <AI값> \
  --human-reviews data/raw/naver_human.csv \
  --ai-reviews data/raw/ai_chatgpt.jsonl data/raw/ai_claude.jsonl data/raw/ai_gemini.jsonl \
  --human-before 2022-12-01 \
  --holdout-generators gemini \
  --out data/processed
```

쿠팡 데이터가 준비되면 `--human-reviews`에 추가하고 `--test-only-platforms coupang`을 붙여 플랫폼 교차 테스트부터 합니다.

**처리 내용**
1. 형식 통일 (`id, text, label, domain, platform, generator, group` + 부가 필드)
2. 정제: 길이 필터(기본 5~2000자), 완전 중복 제거, 같은 문장이 사람·AI 양쪽에 있으면 제거, AI 메타 문구 정리
3. **그룹 단위 분할**: 1단계는 기사 단위, 2단계는 상품 단위. 같은 상품 리뷰가 학습과 테스트에 동시에 들어가지 않습니다.
4. holdout 모델과 테스트 전용 플랫폼은 학습/검증에서 완전히 격리

**생성 파일**

| 파일 | 내용 |
|---|---|
| `stage1_{train,val,test}.jsonl` | LGC 댓글 (90/5/5) |
| `stage2_{train,val,test}.jsonl` | 리뷰 (상품 단위 80/10/10, holdout 모델·테스트 전용 플랫폼 제외) |
| `stage2_test_unseen_gen.jsonl` | 테스트 상품의 사람 리뷰 + holdout 모델 AI 리뷰 |
| `stage2_test_xplatform.jsonl` | 테스트 전용 플랫폼(예: 쿠팡)의 전체 리뷰 |
| `data_summary.json` | split별 건수, 생성 모델·플랫폼 분포, 길이 중앙값, 정제 통계 |

**지름길 점검**: 실행 마지막에 "글자 수만으로 사람/AI를 가른 AUROC"를 출력합니다. 0.7 이상(또는 0.3 이하)이면 경고가 뜹니다. 이 경우 모델 학습 전에 AI 리뷰의 길이 조건부터 다시 맞추세요.

---

## 5. 학습

### 5.1 1단계: LGC 댓글

```bash
python train.py \
  --model beomi/KcELECTRA-base-v2022 \
  --train data/processed/stage1_train.jsonl \
  --val   data/processed/stage1_val.jsonl \
  --out   models/stage1 \
  --epochs 1 --lr 3e-5 --batch-size 64 --max-len 128 \
  --eval-steps 5000 --fp16
```

- 데이터가 200만 건 이상이라 **1 epoch**로 충분한 경우가 많습니다. 검증 AUROC가 아직 오르는 중이면 2 epoch까지 늘려 보세요.
- 댓글은 짧으므로 `--max-len 128`로 속도를 아낍니다.
- 먼저 `--max-train-samples 50000`으로 짧게 돌려 파이프라인과 손실 감소를 확인한 뒤 전체 학습을 돌리세요.

### 5.2 2단계: 리뷰

```bash
python train.py \
  --model models/stage1 \
  --train data/processed/stage2_train.jsonl \
  --val   data/processed/stage2_val.jsonl \
  --replay data/processed/stage1_train.jsonl --replay-ratio 0.15 \
  --out   models/stage2 \
  --epochs 3 --lr 2e-5 --batch-size 32 --max-len 256 --fp16
```

- `--replay`: 최종 학습셋의 15%를 LGC 댓글로 채워 1단계 지식이 지워지는 것을 막습니다. 10~20% 범위에서 조정하세요.
- 2단계는 1단계보다 학습률을 낮게 잡습니다. 검증 AUROC가 2번 연속 오르지 않으면 자동으로 멈춥니다(`--early-stopping 2`).
- 학습 결과 폴더에는 모델, 토크나이저, `train_config.json`(설정과 검증 지표)이 저장됩니다.

### 5.3 주요 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--model` | (필수) | HF 모델 ID 또는 이전 단계 결과 폴더 |
| `--epochs` / `--lr` | 3 / 2e-5 | 학습 횟수 / 학습률 |
| `--batch-size`, `--grad-accum` | 32, 1 | GPU 메모리가 부족하면 batch를 줄이고 accum을 늘림 |
| `--max-len` | 256 | 토큰 최대 길이 (긴 리뷰는 잘림) |
| `--eval-steps` | 없음(epoch마다) | 대용량 학습에서 N step마다 검증·저장 |
| `--target-fpr` | 0.01 | 검증 시 "FPR 1%에서의 탐지율"을 함께 기록 |
| `--max-train-samples` | 없음 | 빠른 점검용 샘플 제한 |

### 5.4 실험 순서 (권장)
1. **1단계 학습** → `stage1_test`로 댓글 도메인 성능 확인
2. **1단계 모델을 리뷰에 바로 평가** (2단계 전) → 도메인 차이가 얼마나 큰지 파악
3. **leave-one-generator-out 3회**: `--holdout-generators`를 `chatgpt`, `claude`, `gemini`로 바꿔 가며 prepare → 2단계 학습 → 평가
4. **최종 모델**: holdout 없이 3개 모델군 전부로 2단계 학습
5. **쿠팡 합류 전후 비교**: 쿠팡 교차 테스트 성능을 확인한 뒤 학습에 추가해 재학습

---

## 6. 평가

### 6.1 실행

```bash
# 우리 모델
python evaluate.py --model models/stage2 \
  --val  data/processed/stage2_val.jsonl \
  --test data/processed/stage2_test.jsonl \
         data/processed/stage2_test_unseen_gen.jsonl \
         data/processed/stage2_test_xplatform.jsonl \
  --out reports/stage2
```

결과물: `report.md`(사람이 읽는 표), `report.json`(전체 수치), `pred_<테스트셋>.csv`(건별 점수·판정·본문, 오답 분석용)

### 6.2 임계값을 정하는 방식
- 임계값은 **검증셋의 사람 리뷰**로 정합니다. 사람 리뷰 중 1%만 AI로 오판되는 점수를 기준선으로 삼고, `P(AI)`가 그보다 크면 AI로 판정합니다.
- 테스트셋을 보고 임계값을 고르지 않으므로, 테스트 결과를 실서비스 기대치로 볼 수 있습니다.
- 기준을 바꾸려면 `--target-fpr 0.005`처럼 지정합니다.

### 6.3 지표 읽는 법

| 지표 | 의미 | 볼 때 주의할 점 |
|---|---|---|
| **AUROC** | 임계값과 무관한 전반적 분리 능력 (0.5 = 무작위, 1.0 = 완벽) | 모델 간 비교용 |
| **TPR @ FPR 1%** | 사람 오탐을 1%로 묶었을 때 잡아내는 AI 리뷰 비율 | **핵심 지표** |
| 실제 FPR | 테스트셋에서 실제로 나온 사람 오탐률 | 1%보다 크게 높으면 검증셋과 테스트셋 분포가 다르다는 신호 |
| 판단 보류 비율 | `P(AI)`가 0.4~0.7인 비율 | 사람 검수로 넘길 물량 추정 |

세부 표는 세 가지로 나뉩니다.
- **생성 모델별**: AI 행은 `tpr`(탐지율), `human` 행은 `fpr`(오탐률)을 봅니다. 특정 모델만 낮으면 그 모델의 생성 다양성을 늘리세요.
- **플랫폼별**: 네이버만 높고 쿠팡이 낮으면 플랫폼 서식이 지름길로 쓰였을 가능성이 큽니다.
- **길이 구간별**: 20자 미만은 원래 어렵습니다. 짧은 리뷰는 판단 보류로 돌리는 정책도 고려하세요.

### 6.4 테스트셋별로 확인할 질문

| 테스트셋 | 확인할 질문 |
|---|---|
| `stage2_test` | 학습한 생성 모델·플랫폼 안에서 처음 보는 상품을 잘 판정하는가 |
| `stage2_test_unseen_gen` | **학습에 안 쓴 LLM**이 쓴 리뷰도 잡는가 (`stage2_test`와의 차이가 일반화 손실) |
| `stage2_test_xplatform` | 다른 플랫폼 리뷰에서도 오탐률이 유지되는가 |

### 6.5 XDAC-D 기준선 비교

```bash
# 1) 출력 구조 확인 (XDAC 출력 형식이 공개 문서에 없어서 먼저 확인)
python xdac_baseline.py --inspect --data data/processed/stage2_val.jsonl

# 2) AI 확률이 든 필드 경로를 지정해 점수 저장
python xdac_baseline.py --score-key <필드.경로> \
  --data data/processed/stage2_val.jsonl data/processed/stage2_test.jsonl \
  --out reports/xdac_scores.csv          # 값이 '사람일 확률'이면 --invert

# 3) 같은 기준으로 평가
python evaluate.py --scores-csv reports/xdac_scores.csv \
  --val data/processed/stage2_val.jsonl --test data/processed/stage2_test.jsonl \
  --out reports/xdac
```

`reports/xdac/report.md`와 `reports/stage2/report.md`의 TPR@FPR1%를 비교하면 "XDAC 대비 개선 폭"이 나옵니다.

### 6.6 오답 분석
`pred_*.csv`에서 다음 두 묶음을 정기적으로 읽어 보세요.
- `label=0, pred=1` (사람인데 AI로 판정): 체험단·정형화된 리뷰, 맞춤법이 완벽한 긴 리뷰가 많으면 학습 데이터에 그런 사람 리뷰를 보강합니다.
- `label=1, pred=0` (AI인데 놓침): 대부분 `rewrite` 유형이나 짧은 리뷰일 것입니다. 해당 유형의 생성 비중을 늘립니다.

---

## 7. 실서비스 적용

### 7.1 추론 예시

```python
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_DIR = "models/stage2"
THRESHOLD = 0.0   # reports/stage2/report.md 의 임계값으로 교체
UNCERTAIN = (0.4, 0.7)

tok = AutoTokenizer.from_pretrained(MODEL_DIR)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR).eval()

def judge(text: str):
    enc = tok(text, truncation=True, max_length=256, return_tensors="pt")
    with torch.no_grad():
        p_ai = torch.softmax(model(**enc).logits, dim=-1)[0, 1].item()
    if UNCERTAIN[0] <= p_ai <= UNCERTAIN[1]:
        verdict = "판단 보류"
    else:
        verdict = "AI" if p_ai > THRESHOLD else "사람"
    return {"p_ai": round(p_ai, 4), "verdict": verdict}

print(judge("배송 빠르고 포장도 꼼꼼해요 ㅎㅎ 재구매 의사 있습니다!"))
```

### 7.2 운영 원칙
- 판정 결과는 **검수 우선순위를 정하는 신호**로 쓰고, 단독으로 제재 근거로 쓰지 않습니다.
- 계정 단위 신호(짧은 시간에 여러 리뷰, 비슷한 문체 반복 등)와 함께 보면 정확도가 크게 오릅니다.
- 새 LLM이 나오면 성능이 떨어집니다. 분기마다 최신 모델로 AI 리뷰를 소량 생성해 `stage2_test_unseen_gen`처럼 평가하고, 떨어지면 재학습하세요.
- 사람이 돈을 받고 쓴 조작 리뷰는 이 모델로 잡히지 않습니다. 목적이 "가짜 리뷰 전반"이라면 별도 신호가 필요합니다.

---

## 8. 한계와 주의사항
- **LGC 데이터 라이선스**: 접근이 게이트로 막혀 있고 라이선스가 명시되어 있지 않습니다. 상업적 사용 전에 저자에게 이용 조건을 확인하세요.
- **사람 라벨 오염**: 날짜 필터를 써도 일부 오염은 남습니다. 실제 FPR이 검증셋보다 약간 높게 나올 수 있습니다.
- **생성 모델 편향**: 학습에 쓴 3개 모델군에 맞춰진 모델입니다. 다른 LLM에 대한 성능은 `unseen_gen` 결과로만 추정할 수 있습니다.
- **짧은 리뷰**: 20자 미만은 정보가 적어 신뢰도가 낮습니다.

---

## 9. 점검 현황

`tests/smoke_test.py`는 GPU나 모델 없이 합성 데이터로 다음을 확인합니다.

| 항목 | 상태 |
|---|---|
| 지표 함수 (AUROC, FPR 기준 임계값) | ✅ 통과 |
| LGC 필드 매핑, 라벨 값 매핑, 중복 제거 | ✅ 통과 |
| 기사·상품 단위 분할 (split 간 그룹 겹침 없음) | ✅ 통과 |
| holdout 생성 모델·테스트 전용 플랫폼 격리 | ✅ 통과 |
| 날짜 필터, AI 메타 문구 정리, 거절 응답 제거 | ✅ 통과 |
| 지름길(길이) 경고 | ✅ 통과 |
| `evaluate.py --scores-csv` 리포트 생성 | ✅ 통과 |
| `train.py`, `evaluate.py --model`, `xdac_baseline.py` | ⚠ 문법 검사만 통과. 실제 학습·추론은 아직 실행하지 않음 |

GPU 환경에서 처음 돌릴 때는 아래 순서로 짧게 확인하세요.

```bash
python tests/smoke_test.py
python train.py --model beomi/KcELECTRA-base-v2022 \
  --train data/processed/stage1_train.jsonl --val data/processed/stage1_val.jsonl \
  --out models/debug --epochs 1 --max-train-samples 2000 --max-val-samples 500
python evaluate.py --model models/debug --val data/processed/stage2_val.jsonl \
  --test data/processed/stage2_test.jsonl --out reports/debug
```
