# AI 모델 연결 가이드 (모델 개발 완료 후)

서비스는 모델 없이도 전부 만들어져 있고, **모델이 계약(MODEL_DEV.md 4.12)대로 나오면 코드 수정 없이 설정만으로 연결**된다.
연결 경로는 가짜 모델 패키지로 미리 검증해 두었다(`service/tests/integration/test_model_adapter_simulated.py`).

## 1. 서비스가 모델에 기대하는 것 (계약)

```python
# pip install -e model  → 패키지명 realstar_model
from realstar_model.inference import Detector, ReviewInput
det = Detector.load("<아티팩트 폴더>")            # manifest.json이 있는 폴더
preds = det.predict([ReviewInput(review_id=..., title=..., content=..., star=...)], batch_size=64)
# 각 Prediction에 필요한 필드: review_id, p_ai, label("human"|"ai"|"uncertain")
# 있으면 쓰는 필드: p_human(없으면 1-p_ai), len_bucket, features(dict), reason_tags(list[str]), model_version
# dataclass · pydantic 모델 · dict 모두 받는다.

from realstar_model.preprocess import clean_review
r = clean_review(title=..., content=...)          # ← 키워드 인자로 호출한다
# 쓰는 필드: clean_text, text_for_model(없으면 clean_text), len_chars, is_sponsored, is_cash_event
# dict 또는 속성 객체 모두 가능

# (선택) 상품 안 근접 중복 그룹
from realstar_model.preprocess.dedup import assign_dup_groups   # list[str] -> list[str | None]
```

`manifest.json`에서 서비스가 읽는 키: `model_version`, `thresholds`(단일 `{T_AI, T_HUMAN}` 또는 길이 구간별 `{S:{...}, M:{...}, L:{...}}`), `min_chars`,
`metrics_summary.sensitivity` / `metrics_summary.specificity`(있으면 Rogan–Gladen 보정값을 결과에 함께 낸다, Phase 8).

> ⚠️ 모델 쪽 확인 필요: MODEL_DEV.md 4.12.2에는 `clean_review`의 인자·반환 필드가 정해져 있지 않다.
> 위 형태(키워드 인자 `title`, `content`)로 만들거나, 다르게 만들 경우 `service/packages/core/realstar/detection/preprocess.py`의 어댑터 한 곳만 고치면 된다.
> 이 내용을 모델 작업 때 MODEL_DEV.md 7장 열린 질문으로 올려 주세요(service 작업에서는 model/ 문서를 수정하지 않았습니다).

## 2. 연결 순서

```bash
# 1) 모델 패키지 설치 (service 가상환경에서)
cd service
pip install -e ../model

# 2) 계약 테스트 — 패키지·아티팩트가 있으면 자동 실행, 없으면 skip
MODEL_ARTIFACT_PATH=../model/artifacts/det-ko-review-v1.0 pytest -m contract -v
```

**운영 구성(Docker / Celery):** `.env`에서
```
DETECTOR_MODE=http
DETECTOR_BACKEND=realstar_model
MODEL_VERSION=det-ko-review-v1.0
```
그리고 이미지를 다시 빌드한다(`docker compose up --build`). `model/pyproject.toml`이 있으면 detector 이미지에 자동 설치되고,
`model/artifacts/`가 `/models`로 마운트된다. GPU를 쓰려면 `docker-compose.yml`의 detector `deploy` 주석을 푼다.

**로컬 단일 프로세스:** `.env`에서 `DETECTOR_MODE=inprocess`, `MODEL_ARTIFACT_PATH=../model/artifacts/det-ko-review-v1.0`.

## 3. 연결 확인

- `GET http://localhost:8001/health` → `"ready": true`, `"model_version": "det-ko-review-v1.0"`
- `GET http://localhost:8000/api/health` → `detector.ready=true`, `preprocess.realstar_model=true`
- 분석 결과 JSON의 `model.version`이 `det-ko-review-v…`이고 `warnings`에 `dummy_detector`, `preprocess_unavailable`이 없으면 완료.
- 모델이 없거나 로드에 실패하면 detector `/predict`는 503, 분석은 `failed / detector_unavailable`("AI 판별 모델을 사용할 수 없어요")로 끝난다. 더미로 대신 계산하지 않는다.

## 4. 모델 교체·재학습 시

- 예측은 `(review_id, model_version)`으로 저장되므로 버전이 바뀌면 자동으로 다시 판별한다. 이전 버전 결과는 남는다.
- 결과 캐시(24시간)는 이전 모델 버전 결과를 보여줄 수 있다. 즉시 반영하려면 `force_refresh=true`로 다시 분석한다.
- 학습용 쿠팡 과거 리뷰 수집은 이 서비스에 없다(라이브 스크래퍼 제거). 저장소 루트의 별도 스크립트 `coupang_reviews.py`로 모은 결과를 MODEL_DEV 4.12.1 형식으로 맞춰 `model/data/raw/coupang/`에 넣는다.
