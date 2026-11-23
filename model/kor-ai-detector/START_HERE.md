# 지금 할 일 (순서대로)

현재 상태: 네이버 ✅ 준비됨 · LGC ✅ 받음(**AI 댓글 2,000건뿐 → 1단계 학습 생략**) · 쿠팡 ⏳ 수집 중 · AI 리뷰 ⬜ 시작 전

```
[A] 설치 ─► [B] LGC 받기(끝) ─► XDAC-D 기준선(선택)
                │
[D] AI 리뷰 수집(팀 작업, 지금 가장 중요) ─► [E] 데이터 만들기 ─► [F] 학습(리뷰) ─► [G] 평가 ─► [H] 웹·홈페이지 확인
```

모든 명령은 `model/kor-ai-detector` 폴더에서 실행합니다 (`cd model/kor-ai-detector`).
저장소 루트에 있다면 `python model/kor-ai-detector/<스크립트>.py` 처럼 경로를 붙여도 됩니다.

> **왜 1단계(LGC 댓글 학습)를 빼나요?** XDAC_obs가 공개한 `LGC_data_v1.0.json`은 논문의 사람 130만 + AI 100만 전체가 아니라
> **AI가 쓴 뉴스 댓글 2,000건 샘플**입니다. 사람/AI 라벨 필드도, 사람 댓글도 없어서 이것만으로는 "사람 vs AI" 학습이 안 됩니다.
> 그래서 KcELECTRA 원본에서 **바로 리뷰로 학습**하고(KcELECTRA는 이미 뉴스 댓글로 사전학습돼 있음),
> 2,000건은 "리뷰가 아닌 AI 글도 잡는지" 보는 **추가 테스트셋**(`lgc_ai_test.jsonl`)으로만 씁니다.
> 학습에 섞지 않는 이유: AI 쪽에만 뉴스 댓글이 들어가면 모델이 "AI 말투"가 아니라 "뉴스 주제"로 구분하게 됩니다.

---

## [A] 설치 (한 번)

```bash
cd model/kor-ai-detector
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tests/smoke_test.py                            # "모든 점검 통과"가 나오면 OK
python convert_sources.py                             # 네이버(+쿠팡) → data/raw/*_human.jsonl
```

## [B] LGC 받기 — ✅ 끝남

`python download_lgc.py --inspect-only`가 `model/data/raw/XDAC_obs/LGC_data/LGC_data_v1.0.json`(2,000건)을 찾아 복사해 두었습니다.
- `get_xdac_path()`는 암호화된 데이터·모델을 임시 폴더(`/var/folders/…/xdac_…`)에 풀어 줍니다. 처음엔 몇 분 멈춘 듯 보이는 게 정상입니다.
- 임시 폴더는 재부팅하면 지워질 수 있어 표준 위치로 복사해 둔 것입니다. XDAC-D 기준선을 돌릴 땐 `xdac_baseline.py`가 다시 `get_xdac_path()`를 부릅니다.

> LGC는 라이선스가 명시돼 있지 않습니다. 발표·연구용으로 쓰고, 상업적으로 쓰기 전에는 저자에게 확인하세요.
> 전체 LGC(사람 댓글 포함)가 꼭 필요하면 저자(모델 카드의 Contact)에게 문의할 수 있습니다. 받게 되면 1단계를 다시 켤 수 있게 코드는 남겨 두었습니다(README 5.1).

## [D] AI 리뷰 수집 — **팀이 할 일, 지금 가장 중요** (이게 있어야 학습 가능)

```bash
python make_ai_tasks.py make --n 1000 --generators chatgpt claude gemini
# → data/ai_tasks/tasks_chatgpt.csv · tasks_claude.csv · tasks_gemini.csv
```
1. CSV를 엑셀·구글 시트로 엽니다. 행마다 `prompt` 칸을 해당 서비스(ChatGPT·Claude·Gemini)의 **새 대화**에 붙여 넣습니다.
2. 답을 그대로 `text` 칸에, 실제로 쓴 모델명(예: `gpt-4o`, `claude-sonnet-5-5`, `gemini-2.5-flash`)을 `model_version` 칸에 적습니다.
   - "물론입니다! 다음은 리뷰입니다:" 같은 안내 문구는 지우지 않아도 됩니다(자동 정리). 그 밖의 내용은 손대지 마세요.
   - **한 대화에 하나씩.** 한 번에 여러 개를 받으면 비슷한 글이 나옵니다. ChatGPT의 '메모리' 기능은 꺼 두세요.
   - 가벼운 모델과 상위 모델을 섞어 쓰면 좋습니다(같은 서비스 안에서 모델 바꾸기).
3. 다 채운 만큼 합칩니다(중간에 몇 번이고 다시 실행해도 됩니다):
   ```bash
   python make_ai_tasks.py merge data/ai_tasks/tasks_*.csv     # → data/raw/ai_chatgpt.jsonl …
   ```

**얼마나?**
- **파일럿: 생성 모델마다 100~200건.** 이만큼 모이면 바로 [E]~[G]를 한 번 돌려 지름길 점검과 파이프라인을 확인하세요(학습 몇 분).
- **첫 버전: 생성 모델마다 1,000건(총 3,000건).** 사람 리뷰는 [E]에서 AI 수에 맞춰 자동으로 뽑습니다.
- 수작업이면 1건에 30초~1분 → 3,000건은 25~50시간입니다. 팀원이 나눠 하거나, API를 쓸 수 있으면 훨씬 빠릅니다
  (Claude는 `model/` 패키지의 `python -m realstar_model generate`로 자동 생성 가능).

## [E] 데이터 만들기

```bash
python prepare_data.py \
  --lgc ../data/raw/XDAC_obs/LGC_data/LGC_data_v1.0.json \
  --lgc-all-ai --lgc-text-field generated_comment --lgc-generator-field llm_model_family \
  --human-reviews data/raw/naver_human.jsonl \
  --ai-reviews data/raw/ai_chatgpt.jsonl data/raw/ai_claude.jsonl data/raw/ai_gemini.jsonl \
  --human-before 2022-12-01 --holdout-generators gemini --out data/processed
```
- LGC는 `lgc_ai_test.jsonl`(테스트 전용)로만 나옵니다. `stage1_*` 파일은 만들어지지 않는 게 정상입니다.
- 사람 리뷰(20만)는 AI 수 × 1(`--human-ratio`)로 **별점·길이를 맞춰** 자동으로 줄입니다.
- 네이버엔 줄바꿈이 없어서, AI 쪽에만 줄바꿈이 있으면 양쪽 줄바꿈을 공백으로 바꿉니다(`--newlines auto`, 이유가 출력됨).
- **마지막 [지름길 점검]을 꼭 보세요.** ⚠가 뜬 특징(길이·마침표 등)이 있으면 모델이 AI다움이 아니라 그 차이로 구분합니다 → [D]의 생성 방식을 고친 뒤 다시.
- 쿠팡이 모이면 `--human-reviews`에 `data/raw/coupang_human.jsonl`을 더하고 `--test-only-platforms coupang`으로 플랫폼 교차 테스트부터 하세요(`python convert_sources.py`를 다시 실행해 최신화).

## [F] 학습 (리뷰)

```bash
python train.py --model beomi/KcELECTRA-base-v2022 \
  --train data/processed/stage2_train.jsonl --val data/processed/stage2_val.jsonl \
  --out models/stage2 --epochs 3 --lr 2e-5 --batch-size 32 --max-len 256 --fp16
```
- 3,000 + 3,000건 기준 **RTX 3060에서 몇 분**, 맥북(MPS)에서도 수십 분 안팎입니다. 100만 건 같은 대규모 학습은 이제 필요 없습니다.
- `--fp16`은 CUDA GPU에서만 켜지고 맥에서는 자동으로 무시됩니다.
- 일반화 확인(README 5.4): `--holdout-generators`를 chatgpt / claude / gemini로 바꿔 [E]→[F]→[G]를 3번. 최종 모델은 holdout 없이.

## [G] 평가

```bash
python evaluate.py --model models/stage2 --val data/processed/stage2_val.jsonl \
  --test data/processed/stage2_test.jsonl data/processed/stage2_test_unseen_gen.jsonl data/processed/lgc_ai_test.jsonl \
  --out reports/stage2
```
`reports/stage2/report.md`에서 **TPR@FPR1%**(핵심), 실제 FPR, 생성 모델별·길이별 표를 봅니다. 오답은 `pred_*.csv`.
- `lgc_ai_test`는 AI 글만 있어 AUROC·FPR은 `-`로 나오고 **탐지율(TPR)만** 의미가 있습니다. 생성 모델군(GPT·Claude·Gemma·Qwen·Gemini·HCX·Llama·EXAONE)별로 나옵니다.
- 댓글은 짧아서 20자 미만이 많고, 그런 글은 판정이 "판단 보류"로 나옵니다(정보 부족). TPR은 점수 기준이라 그대로 봐도 됩니다.

**XDAC-D 기준선 (선택)**: 같은 테스트셋을 XDAC-D로 채점해 우리 모델과 비교합니다. 사용법은 `python xdac_baseline.py --help`.
지금 당장은 출력 구조 확인만 미리 해 둘 수 있습니다(임계값을 정할 검증셋은 AI 리뷰가 모여야 생깁니다):
```bash
python prepare_data.py --lgc ../data/raw/XDAC_obs/LGC_data/LGC_data_v1.0.json --lgc-all-ai --lgc-text-field generated_comment --lgc-generator-field llm_model_family --out data/processed
python xdac_baseline.py --inspect --data data/processed/lgc_ai_test.jsonl
```

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
`model/data/`(네이버·쿠팡·LGC·XDAC 원천 데이터), `data/`, `models/`, `reports/`는 `.gitignore`에 들어 있습니다(리뷰 원문·대용량 가중치).
