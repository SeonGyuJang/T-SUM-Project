"""한국어 인코더 분류기 추론 (Detector가 씀). 학습은 model/kor-ai-detector/train.py, 내보내기는 export_for_service.py.

- 점수 = logit(ai) − logit(human). 보정(Platt)·임계값은 아티팩트 manifest.json에 들어 있다.
- pip install -e "model[encoder]" (torch·transformers). GPU가 없으면 CPU·Apple MPS로 돈다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def pick_device() -> Any:
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class EncoderScorer:
    """저장된 인코더로 원점수(logit_ai − logit_human)를 낸다. Detector가 쓴다."""

    batch_call = True

    def __init__(self, path: Path, max_length: int = 256, device: Any = None) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.device = device or pick_device()
        self.tok = AutoTokenizer.from_pretrained(str(path))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(path)).to(self.device).eval()
        self.max_length = max_length

    def __call__(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        return score_texts(self.model, self.tok, texts, self.max_length, batch_size, self.device)


def score_texts(model: Any, tok: Any, texts: list[str], max_length: int, batch_size: int, device: Any) -> np.ndarray:
    import torch

    out: list[float] = []
    model.eval()
    with torch.no_grad():
        for k in range(0, len(texts), batch_size):
            enc = tok(texts[k:k + batch_size], truncation=True, max_length=max_length, padding=True, return_tensors="pt").to(device)
            logits = model(**enc).logits.float()
            out.extend((logits[:, 1] - logits[:, 0]).cpu().tolist())
    return np.asarray(out)
