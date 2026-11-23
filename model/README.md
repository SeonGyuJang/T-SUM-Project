# model/ — AI 작성 리뷰 탐지 모델

| 폴더 | 역할 |
|---|---|
| [`kor-ai-detector/`](kor-ai-detector/START_HERE.md) | **학습 파이프라인**: 사람 리뷰 합치기 → AI 리뷰 작업표 → API로 채우기 → 데이터 분할 → 학습 → 평가 → 서비스용 내보내기 |
| `src/realstar_model/` | **서비스용 추론 런타임**: 홈페이지(service)가 `Detector.load()`로 학습된 모델을 열어 판정한다 |
| `data/` | 원천 데이터(AI Hub·네이버·XDAC). git에 올라가지 않음 |
| `artifacts/` | 내보낸 모델(`export_for_service.py` 결과). git에 올라가지 않음 |

할 일 순서는 [`kor-ai-detector/START_HERE.md`](kor-ai-detector/START_HERE.md)를 보세요.

## 서비스용 추론 런타임 (`realstar_model`)

```bash
pip install -e "model[encoder]"     # service 가상환경에서 (torch·transformers)
```
```python
from realstar_model.inference import Detector, ReviewInput
det = Detector.load("model/artifacts/det-ko-review-v1.0")   # manifest.json + encoder/
det.predict([ReviewInput(review_id="1", content="배송 빠르고 좋아요")])   # → label: ai | human | uncertain
```
- `preprocess.clean_review`: 서비스가 리뷰를 모델에 넣기 전에 쓰는 정리(쿠팡캐시 고지 문구 제거, 공백·줄바꿈 정리).
- 보정(Platt)·길이 구간별 임계값은 아티팩트의 `manifest.json`에 들어 있습니다.

점검: `cd model && pip install -e ".[dev]" && pytest -q && ruff check src tests && mypy src`
