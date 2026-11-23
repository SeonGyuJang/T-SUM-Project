# 지금 할 일 (순서대로)

현재 상태: 네이버 ✅ 준비됨 · LGC ⬜ 다운로드 전 · 쿠팡 ⏳ 수집 중 · AI 리뷰 ⬜ 시작 전

```
[A] 설치 ─► [B] LGC 받기 ─► [C] 1단계 학습(댓글)   ← AI 리뷰 없이 바로 시작 가능
                │
[D] AI 리뷰 수집(팀 작업) ─► [E] 2단계 데이터 ─► [F] 2단계 학습(리뷰) ─► [G] 평가 ─► [H] 웹·홈페이지 확인
```

모든 명령은 `model/kor-ai-detector` 폴더에서 실행합니다.

---

## [A] 설치 (한 번)

```bash
cd model/kor-ai-detector
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tests/smoke_test.py                            # "모든 점검 통과"가 나오면 OK
python convert_sources.py                             # 네이버(+쿠팡) → data/raw/*_human.jsonl
```

## [B] LGC 데이터 받기 — **당신이 할 일**

1. https://huggingface.co/keepsteady/XDAC_obs 에 로그인 → 접근 조건 동의(자동 승인)
2. 토큰 만들기: Hugging Face → Settings → Access Tokens → **Read** 토큰
3. 터미널:
   ```bash
   huggingface-cli login          # (또는 hf auth login) 토큰 붙여 넣기
   python download_lgc.py         # ./XDAC_obs 에 받고 LGC 필드·라벨 값을 출력 (약 1GB)
   ```
4. 출력된 **필드 이름과 라벨 값**을 보고 [C]의 옵션을 정합니다. 예를 들어 출력이
   `필드: ['text', 'label', 'model', ...]`, `label: {'human': 1300000, 'llm': 1000000}` 이면
   `--lgc-text-field text --lgc-label-field label --lgc-ai-values llm --lgc-generator-field model` 입니다.
   (출력 내용을 보내 주시면 옵션을 맞춰 드릴게요.)

> LGC는 라이선스가 명시돼 있지 않습니다. 발표·연구용으로 쓰고, 상업적으로 쓰기 전에는 저자에게 확인하세요.

## [C] 1단계 학습 (LGC 댓글) — AI 리뷰를 기다리지 않고 시작

```bash
python prepare_data.py --lgc XDAC_obs/LGC_data/LGC_data_v1.0.json \
  --lgc-text-field <본문필드> --lgc-label-field <라벨필드> --lgc-ai-values <AI값> \
  [--lgc-generator-field <모델필드>] [--lgc-group-field <기사ID필드>] --out data/processed
```
출력의 `lgc_raw_label_values`에서 사람/AI가 둘 다 잡혔는지 꼭 확인하세요(AI 값이 틀리면 전부 사람이 됩니다).

**짧은 시험 학습** (5~20분, 파이프라인 점검):
```bash
python train.py --model beomi/KcELECTRA-base-v2022 \
  --train data/processed/stage1_train.jsonl --val data/processed/stage1_val.jsonl \
  --out models/debug --epochs 1 --max-train-samples 5000 --max-val-samples 1000 --max-len 128
```
**본 학습**: GPU에서 (맥북 CPU·MPS로는 200만 건이 너무 오래 걸립니다 → Google Colab GPU나 클라우드 권장)
```bash
python train.py --model beomi/KcELECTRA-base-v2022 \
  --train data/processed/stage1_train.jsonl --val data/processed/stage1_val.jsonl \
  --out models/stage1 --epochs 1 --lr 3e-5 --batch-size 64 --max-len 128 --eval-steps 5000 --fp16
```
처음엔 `--max-train-samples 300000`으로 줄여 돌려 보고, 검증 AUROC가 계속 오르면 전체로 늘리세요.

## [D] AI 리뷰 수집 — **팀이 할 일** (가장 오래 걸림)

```bash
python make_ai_tasks.py make --n 1000 --generators chatgpt claude gemini
# → data/ai_tasks/tasks_chatgpt.csv · tasks_claude.csv · tasks_gemini.csv
```
1. CSV를 엑셀·구글 시트로 엽니다. 행마다 `prompt` 칸을 해당 서비스(ChatGPT·Claude·Gemini)의 **새 대화**에 붙여 넣습니다.
2. 답을 그대로 `text` 칸에, 실제로 쓴 모델명(예: `gpt-4o`, `claude-sonnet-5-5`, `gemini-2.5-flash`)을 `model_version` 칸에 적습니다.
   - "물론입니다! 다음은 리뷰입니다:" 같은 안내 문구는 지우지 않아도 됩니다(자동 정리). 그 밖의 내용은 손대지 마세요.
   - **한 대화에 하나씩.** 한 번에 여러 개를 받으면 비슷한 글이 나옵니다. ChatGPT의 '메모리' 기능은 꺼 두세요.
   - 가벼운 모델과 상위 모델을 섞어 쓰면 좋습니다(같은 서비스 안에서 모델 바꾸기).
3. 다 채우면 합칩니다:
   ```bash
   python make_ai_tasks.py merge data/ai_tasks/tasks_*.csv     # → data/raw/ai_chatgpt.jsonl …
   ```

**얼마나?** 첫 버전은 **생성 모델마다 1,000건(총 3,000건)** 을 목표로 하세요. 사람 리뷰는 [E]에서 AI 수에 맞춰 자동으로 뽑습니다.
수작업이면 1건에 30초~1분 → 3,000건은 25~50시간입니다. 팀원이 나눠 하거나, API를 쓸 수 있으면 훨씬 빠릅니다
(Claude는 `model/` 패키지의 `python -m realstar_model generate`로 자동 생성 가능).

## [E] 2단계 데이터 만들기

```bash
python prepare_data.py \
  --lgc XDAC_obs/LGC_data/LGC_data_v1.0.json --lgc-text-field … --lgc-label-field … --lgc-ai-values … \
  --human-reviews data/raw/naver_human.jsonl \
  --ai-reviews data/raw/ai_chatgpt.jsonl data/raw/ai_claude.jsonl data/raw/ai_gemini.jsonl \
  --human-before 2022-12-01 --holdout-generators gemini --out data/processed
```
- 사람 리뷰(20만)는 AI 수 × 1(`--human-ratio`)로 **별점·길이를 맞춰** 자동으로 줄입니다.
- 네이버엔 줄바꿈이 없어서, AI 쪽에만 줄바꿈이 있으면 양쪽 줄바꿈을 공백으로 바꿉니다(`--newlines auto`, 이유가 출력됨).
- **마지막 [지름길 점검]을 꼭 보세요.** ⚠가 뜬 특징(길이·마침표 등)이 있으면 모델이 AI다움이 아니라 그 차이로 구분합니다 → [D]의 생성 방식을 고친 뒤 다시.
- 쿠팡이 모이면 `--human-reviews`에 `data/raw/coupang_human.jsonl`을 더하고 `--test-only-platforms coupang`으로 플랫폼 교차 테스트부터 하세요(`python convert_sources.py`를 다시 실행해 최신화).

## [F] 2단계 학습 (리뷰)

```bash
python train.py --model models/stage1 \
  --train data/processed/stage2_train.jsonl --val data/processed/stage2_val.jsonl \
  --replay data/processed/stage1_train.jsonl --replay-ratio 0.15 \
  --out models/stage2 --epochs 3 --lr 2e-5 --batch-size 32 --max-len 256 --fp16
```
일반화 확인(README 5.4): `--holdout-generators`를 chatgpt / claude / gemini로 바꿔 [E]→[F]→[G]를 3번. 최종 모델은 holdout 없이.

## [G] 평가

```bash
python evaluate.py --model models/stage2 --val data/processed/stage2_val.jsonl \
  --test data/processed/stage2_test.jsonl data/processed/stage2_test_unseen_gen.jsonl --out reports/stage2
```
`reports/stage2/report.md`에서 **TPR@FPR1%**(핵심), 실제 FPR, 생성 모델별·길이별 표를 봅니다. 오답은 `pred_*.csv`.

## [H] 웹페이지·홈페이지로 확인

```bash
python app.py --model models/stage2 --report reports/stage2/report.json     # → http://127.0.0.1:7860
```
리뷰를 넣어 판정을 보거나, 테스트셋에서 무작위로 뽑아 정답과 비교합니다.

홈페이지(리얼별점)에 붙이기:
```bash
python export_for_service.py --model models/stage2 --report reports/stage2/report.json --version det-ko-review-v1.0
# service/.env:  DETECTOR_MODE=inprocess   MODEL_ARTIFACT_PATH=../model/artifacts/det-ko-review-v1.0
# service 가상환경: pip install -e ../model torch transformers
```

---

### 결과물은 git에 올라가지 않습니다
`data/`, `models/`, `reports/`, `XDAC_obs/`는 `.gitignore`에 들어 있습니다(리뷰 원문·대용량 가중치).
