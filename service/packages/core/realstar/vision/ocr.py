"""로컬 OCR 엔진 래퍼 (README 5.1 (c) 2). 외부 유료 API를 쓰지 않는다.

PaddleOCR(한국어) 1순위, EasyOCR 대안. 패키지가 없으면 NullOcrEngine(사용 불가)으로 동작하고
/api/health에 표시된다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image

log = logging.getLogger(__name__)


@dataclass
class OcrLine:
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 (픽셀)
    confidence: float

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def top(self) -> float:
        return self.bbox[1]


class OcrEngine(Protocol):
    name: str
    available: bool

    def read(self, image: Image.Image) -> list[OcrLine]: ...


class NullOcrEngine:
    name = "none"
    available = False

    def __init__(self, reason: str = "OCR 엔진이 설치되지 않았습니다") -> None:
        self.reason = reason

    def read(self, image: Image.Image) -> list[OcrLine]:
        from realstar.errors import VisionUnavailableError

        raise VisionUnavailableError(self.reason)


def _quad_to_bbox(quad: Any) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in quad]
    ys = [float(p[1]) for p in quad]
    return (min(xs), min(ys), max(xs), max(ys))


class PaddleOcrEngine:
    name = "paddleocr"
    available = True

    def __init__(self) -> None:
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]

        self._ocr = PaddleOCR(lang="korean", use_angle_cls=True, show_log=False)

    def read(self, image: Image.Image) -> list[OcrLine]:
        import numpy as np

        from realstar.errors import VisionUnavailableError

        try:
            result = self._ocr.ocr(np.asarray(image.convert("RGB")), cls=True)
        except Exception as e:  # 엔진 내부 오류는 사용자에게 '이미지 인식 불가'로 안내
            log.exception("paddleocr failed")
            raise VisionUnavailableError(f"paddleocr error: {type(e).__name__}") from e
        lines: list[OcrLine] = []
        for page in result or []:
            for quad, (text, conf) in page or []:
                if text and text.strip():
                    lines.append(OcrLine(text.strip(), _quad_to_bbox(quad), float(conf)))
        return lines


class EasyOcrEngine:
    name = "easyocr"
    available = True

    def __init__(self) -> None:
        import easyocr  # type: ignore[import-not-found]

        self._reader = easyocr.Reader(["ko", "en"], gpu=False)

    def read(self, image: Image.Image) -> list[OcrLine]:
        import numpy as np

        lines = []
        for quad, text, conf in self._reader.readtext(np.asarray(image.convert("RGB"))):
            if text and text.strip():
                lines.append(OcrLine(text.strip(), _quad_to_bbox(quad), float(conf)))
        return lines


_engine_cache: dict[str, OcrEngine] = {}


def get_ocr_engine(name: str) -> OcrEngine:
    if name in _engine_cache:
        return _engine_cache[name]
    engine: OcrEngine
    try:
        if name == "paddleocr":
            engine = PaddleOcrEngine()
        elif name == "easyocr":
            engine = EasyOcrEngine()
        else:
            engine = NullOcrEngine("OCR_ENGINE=none")
    except Exception as e:  # ImportError 포함: 기능 저하 모드
        log.warning("OCR engine %s unavailable: %s", name, e)
        engine = NullOcrEngine(f"{name} 사용 불가: {type(e).__name__}")
    _engine_cache[name] = engine
    return engine
