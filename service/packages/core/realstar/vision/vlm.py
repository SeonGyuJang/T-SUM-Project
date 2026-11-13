"""로컬 VLM(선택) — 저신뢰 OCR 결과나 글자 없는 사진에서 상품 정보를 JSON으로 뽑는다 (README 5.1 (c) 3~4).

TBD-5: 모델 미정, 기본값은 미사용(VLM_ENABLED=false). 켜면 VLM_MODEL_PATH의 Qwen2.5-VL 계열을
transformers로 로컬 로드한다. GPU가 없거나 로드에 실패하면 None을 돌려 OCR만으로 동작한다(기능 저하 모드).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from PIL import Image

log = logging.getLogger(__name__)

VLM_PROMPT = (
    "이 이미지는 쇼핑 상품 사진이거나 쇼핑몰 화면 캡처다. 아래 JSON 형식으로만 답하라. 모르는 값은 null.\n"
    '{"has_text": true, "brand": "", "product_name": "", "model_number": "", "spec": "", '
    '"category_guess": "", "is_coupang_screenshot": false, "confidence": 0.0, '
    '"search_queries": ["검색어1", "검색어2"]}'
)


class VlmExtractor(Protocol):
    available: bool

    def extract(self, image: Image.Image) -> dict[str, Any] | None: ...


class DisabledVlm:
    available = False

    def extract(self, image: Image.Image) -> dict[str, Any] | None:
        return None


def parse_vlm_json(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        data["confidence"] = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        data["confidence"] = 0.0
    queries = data.get("search_queries") or []
    data["search_queries"] = [str(q) for q in queries if q][:3] if isinstance(queries, list) else []
    return data


class QwenVlVlm:
    available = True

    def __init__(self, model_path: str) -> None:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self._torch = torch
        self.processor = AutoProcessor.from_pretrained(model_path)
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_path, torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32, device_map="auto"
        ).eval()

    def extract(self, image: Image.Image) -> dict[str, Any] | None:
        messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": VLM_PROMPT}]}]
        prompt = self.processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = self.processor(text=[prompt], images=[image.convert("RGB")], return_tensors="pt").to(self.model.device)
        with self._torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=256, do_sample=False)
        text = self.processor.batch_decode(out[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True)[0]
        return parse_vlm_json(text)


_vlm: VlmExtractor | None = None


def get_vlm(enabled: bool, model_path: str) -> VlmExtractor:
    global _vlm
    if _vlm is not None:
        return _vlm
    if not enabled or not model_path:
        _vlm = DisabledVlm()
        return _vlm
    try:
        _vlm = QwenVlVlm(model_path)
    except Exception as e:
        log.warning("VLM unavailable, OCR-only mode: %s", e)
        _vlm = DisabledVlm()
    return _vlm
