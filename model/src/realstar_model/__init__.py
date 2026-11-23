"""리얼별점 AI 작성 리뷰 탐지 — 서비스용 추론 런타임.

모델 학습은 model/kor-ai-detector/ 에서 하고, export_for_service.py가 model/artifacts/<버전>/ 으로 내보낸다.
공개 API(service ↔ model 계약)
  from realstar_model.preprocess import clean_review
  from realstar_model.inference import Detector, ReviewInput
"""

__version__ = "0.2.0"
