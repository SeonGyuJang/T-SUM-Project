# model/ — AI 작성 리뷰 탐지 모델 (`realstar_model`)

설계·결정·기록은 [`MODEL_DEV.md`](MODEL_DEV.md). 이 문서는 **실행 순서**만 정리한다.

```
사람 리뷰(네이버 쇼핑 20만 + 쿠팡 2022-11-30 이전)
      │  기준 리뷰로 사용
      ▼
Claude로 AI 리뷰 생성 ──► 데이터셋(사람:AI = 1:1, 같은 분할·별점·길이) ──► 학습 ──► artifacts/det-ko-review-v0.x/
                                                                                       │
                                                                       service가 Detector.load()로 사용
```

## 0. 설치 (처음 한 번)

```bash
cd model
pip install -e ".[gen,dev]"          # 생성(Claude API) + 베이스라인
pip install -e ".[encoder]"          # 인코더 학습까지 (torch·transformers, GPU 권장)
```

## 1. 사람 데이터 준비

```bash
cd ..                                 # 저장소 루트
python collect_training_data.py naver # → model/data/raw/naver/naver_shopping.jsonl (20만 건)
cd model
python -m realstar_model data-stats   # 양·분할·별점·길이 확인
```
쿠팡 수집기(`collect_training_data.py category`)로 모은 2022-11-30 이전 리뷰가 있으면 자동으로 함께 쓴다.

## 2. AI 리뷰 생성 (Claude API)

네이버 데이터는 **전부 사람 리뷰**라서, 탐지 모델을 학습하려면 AI가 쓴 리뷰를 만들어야 한다.
사람 리뷰 하나를 '기준 리뷰'로 주고 "같은 상품을 산 다른 구매자로서 새 리뷰를 써라"라고 시킨다(주제가 같아져 모델이 주제로 구분하지 못하게).

```bash
export ANTHROPIC_API_KEY=sk-ant-...                       # 또는 `ant auth login`
python -m realstar_model generate --n 5 --dry-run          # API 호출 없이 프롬프트만 확인 (먼저!)
python -m realstar_model generate --n 200                  # 소량으로 결과 확인 → model/data/generated/ai_claude-opus-5-5.jsonl
python -m realstar_model generate --n 5000                 # 본 생성 (끊겨도 다시 실행하면 이어서)
```
- 기본 모델 `claude-opus-5-5`, 노력 수준 `low`. 생성 모델을 여러 개 쓰면 특정 모델 말투만 외우는 것을 막는다(MODEL_DEV D-008):
  `--model claude-sonnet-5-5`, `--model claude-haiku-5-5` 로 각각 돌리고, 하나는 `build-dataset --holdout-generator`로 테스트 전용으로 둔다.
- 20%는 사람 리뷰를 AI가 다듬은 샘플(`--polish-ratio`)이다. 실제로 흔한 "초안을 AI로 다듬기" 유형.
- 거절(refusal) 시 서버 측 대체 모델로 자동 재시도한다(Opus·Sonnet). 진행 중 토큰 사용량이 출력된다.
- 탈락 필터: 메타 문구("작성해 드릴게요"), 마크다운, 한글 비율 < 0.7, 목표 길이 0.5~1.8배 밖, 기준 리뷰 베끼기(8글자 겹침 ≥ 30%), 중복.

## 3. 데이터셋 만들기

```bash
python -m realstar_model build-dataset
python -m realstar_model build-dataset --holdout-generator claude-haiku-5-5   # 처음 보는 생성 모델 평가(t_gen)
```
AI 1건마다 같은 분할·별점·길이 구간의 사람 리뷰 1건을 뽑는다 → `model/data/processed/dataset.jsonl`.

## 4. 학습

```bash
python -m realstar_model train-baseline     # CPU 몇 분 → artifacts/det-ko-review-v0.1  (B0 지름길 점검 + B1 TF-IDF)
python -m realstar_model train-encoder      # GPU 권장 → artifacts/det-ko-review-v0.2  (beomi/KcELECTRA-base-v2022)
python -m realstar_model train-encoder --limit 2000 --epochs 1   # 빠른 시험
```
결과표: AUROC, **TPR@1%FPR**(사람을 1%만 AI로 오판할 때 AI를 잡는 비율, 주 지표), ECE(확률 보정 오차) — 전체·길이 구간별.
**B0(길이·문장부호만)의 AUROC가 0.8 이상이면** 생성 데이터의 형식이 사람 데이터와 달라 모델이 지름길을 배우는 중이다 → 생성 프롬프트·필터를 고친다.
실험 기록은 `model/reports/`(git에 올림).

GPU가 없으면 Google Colab에서 `train-encoder`만 돌리고 `artifacts/` 폴더를 받아 와도 된다.

## 5. 홈페이지(service)에 연결

```bash
cd ../service
pip install -e ../model                               # service 가상환경에
# service/.env
DETECTOR_MODE=inprocess
MODEL_ARTIFACT_PATH=../model/artifacts/det-ko-review-v0.1
```
API를 다시 시작하면 결과 화면에 사람 리뷰 기준 별점·AI 비중·Top 5가 나온다.
확인: `MODEL_ARTIFACT_PATH=../model/artifacts/det-ko-review-v0.1 pytest -m contract`

## 테스트

```bash
cd model && pytest -q        # 실제 API 호출 없음(가짜 생성기 사용)
```
