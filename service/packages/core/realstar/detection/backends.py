"""탐지 백엔드. 서비스는 이 인터페이스만 쓴다.

- RealstarModelBackend: `realstar_model.inference.Detector.load(artifact)` (MODEL_DEV.md 4.12.2). 모델 완성 후 운영 경로.
- HttpDetectorBackend: detector_server(`POST /predict`) 호출. 워커 기본값.
- DummyDetectorBackend: 개발·테스트 전용. 텍스트 해시로 만든 가짜 확률이며 결과에 `dummy_detector` 경고가 붙는다.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Protocol

import httpx

from realstar.detection.schemas import DetectInput, DetectOutput, ModelInfo, PredictRequest, PredictResponse
from realstar.errors import DetectorUnavailableError

log = logging.getLogger(__name__)


class DetectorBackend(Protocol):
    def info(self) -> ModelInfo: ...
    def predict(self, items: list[DetectInput], batch_size: int = 64) -> list[DetectOutput]: ...


def _to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # type: ignore[no-any-return]
    return dict(vars(obj))


def read_manifest(artifact: Path) -> dict[str, Any]:
    path = Path(artifact) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def ensure_artifact(artifact_path: Path, url: str, timeout: float = 600.0) -> None:
    """아티팩트 폴더가 없고 URL이 있으면 tar.gz를 받아 풀어 둔다(볼륨 없는 배포용: Heroku 등).

    tar.gz 안에 manifest.json이 최상위에 있거나, 아티팩트 폴더 하나가 들어 있어도 된다.
    """
    import io
    import shutil
    import tarfile
    import tempfile

    artifact_path = Path(artifact_path)
    if (artifact_path / "manifest.json").exists() or not url:
        return
    log.info("downloading model artifact from %s", url.split("?")[0])
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as r:
        r.raise_for_status()
        buf = io.BytesIO(r.read())
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(fileobj=buf, mode="r:*") as tar:
        tar.extractall(tmp, filter="data")  # 경로 탈출·링크 공격 차단
        found = next(iter(sorted(Path(tmp).rglob("manifest.json"), key=lambda p: len(p.parts))), None)
        if found is None:
            raise ValueError("artifact archive has no manifest.json")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(found.parent), str(artifact_path))


class RealstarModelBackend:
    def __init__(self, artifact_path: Path, artifact_url: str = "") -> None:
        self.artifact_path = Path(artifact_path)
        self.artifact_url = artifact_url
        self._detector: Any = None
        self._error: str | None = None
        self._manifest: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.artifact_url:
            try:
                ensure_artifact(self.artifact_path, self.artifact_url)
            except Exception as e:
                self._error = f"모델 아티팩트 다운로드 실패: {type(e).__name__}: {e}"
                return
        try:
            from realstar_model.inference import Detector  # type: ignore[import-not-found]
        except Exception as e:
            self._error = f"realstar_model 패키지를 불러올 수 없음: {type(e).__name__}: {e}"
            return
        if not (self.artifact_path / "manifest.json").exists():
            self._error = f"모델 아티팩트가 없음: {self.artifact_path}/manifest.json"
            return
        try:
            self._manifest = read_manifest(self.artifact_path)
            self._detector = Detector.load(str(self.artifact_path))
        except Exception as e:  # pragma: no cover - 모델 패키지 의존
            log.exception("Detector.load failed")
            self._error = f"Detector.load 실패: {type(e).__name__}: {e}"

    def info(self) -> ModelInfo:
        m = self._manifest
        metrics = m.get("metrics_summary") or {}
        return ModelInfo(
            ready=self._detector is not None,
            backend="realstar_model",
            model_version=m.get("model_version"),
            thresholds=m.get("thresholds"),
            min_chars=m.get("min_chars"),
            sensitivity=metrics.get("sensitivity"),
            specificity=metrics.get("specificity"),
            error=self._error,
        )

    def predict(self, items: list[DetectInput], batch_size: int = 64) -> list[DetectOutput]:
        if self._detector is None:
            raise DetectorUnavailableError(self._error or "detector not loaded")
        from realstar_model.inference import ReviewInput  # type: ignore[import-not-found]

        inputs = [ReviewInput(review_id=i.review_id, title=i.title, content=i.content, star=i.star) for i in items]
        preds = self._detector.predict(inputs, batch_size=batch_size)
        out = []
        for p in preds:
            d = _to_dict(p)
            d.setdefault("p_human", 1.0 - float(d["p_ai"]))
            d.setdefault("model_version", self._manifest.get("model_version", "unknown"))
            out.append(DetectOutput.model_validate(d))
        return out


class HttpDetectorBackend:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def info(self) -> ModelInfo:
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=5.0)
            r.raise_for_status()
            return ModelInfo.model_validate(r.json())
        except Exception as e:
            return ModelInfo(ready=False, backend="http", error=f"detector_server 연결 실패: {type(e).__name__}")

    def predict(self, items: list[DetectInput], batch_size: int = 64) -> list[DetectOutput]:
        try:
            r = httpx.post(
                f"{self.base_url}/predict",
                json=PredictRequest(reviews=items, batch_size=batch_size).model_dump(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise DetectorUnavailableError(f"detector_server unreachable: {e}") from e
        if r.status_code == 503:
            raise DetectorUnavailableError(r.text)
        r.raise_for_status()
        return PredictResponse.model_validate(r.json()).predictions


class DummyDetectorBackend:
    """⚠️ 개발·테스트 전용 가짜 판별기. 실제 AI 작성 여부와 무관하다."""

    VERSION = "dummy-dev-0"

    def __init__(self, min_chars: int = 20, t_ai: float = 0.8, t_human: float = 0.3, overrides: dict[str, str] | None = None) -> None:
        self.min_chars = min_chars
        self.t_ai = t_ai
        self.t_human = t_human
        self.overrides = overrides or {}  # review_id → 고정 라벨 (테스트용)

    def info(self) -> ModelInfo:
        return ModelInfo(
            ready=True,
            backend="dummy",
            model_version=self.VERSION,
            thresholds={"T_AI": self.t_ai, "T_HUMAN": self.t_human},
            min_chars=self.min_chars,
            is_dummy=True,
        )

    def predict(self, items: list[DetectInput], batch_size: int = 64) -> list[DetectOutput]:
        out = []
        for it in items:
            text = f"{it.title or ''} {it.content}".strip()
            if it.review_id in self.overrides:
                label = self.overrides[it.review_id]
                p_ai = {"ai": 0.95, "human": 0.05, "uncertain": 0.55}[label]
                p_ai = p_ai - (int(hashlib.sha1(it.review_id.encode()).hexdigest()[:4], 16) / 65535) * 0.04
            else:
                p_ai = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
                label = "ai" if p_ai >= self.t_ai else "human" if p_ai <= self.t_human else "uncertain"
            if len(text) < self.min_chars:
                label = "uncertain"
            p_ai = round(min(1.0, max(0.0, p_ai)), 4)
            out.append(
                DetectOutput(
                    review_id=it.review_id,
                    p_ai=p_ai,
                    p_human=round(1.0 - p_ai, 4),
                    label=label,  # type: ignore[arg-type]
                    len_bucket="S" if len(text) < 30 else "M" if len(text) < 100 else "L",
                    model_version=self.VERSION,
                )
            )
        return out


class NoDetectorBackend:
    """AI 판별 모델이 아직 없을 때. info().ready=False → 파이프라인이 판별을 건너뛴다."""

    MESSAGE = "AI 판별 모델이 아직 연결되지 않았어요."

    def info(self) -> ModelInfo:
        return ModelInfo(ready=False, backend="none", error=self.MESSAGE)

    def predict(self, items: list[DetectInput], batch_size: int = 64) -> list[DetectOutput]:
        raise DetectorUnavailableError(self.MESSAGE)


def light_info(mode: str, *, detector_url: str, artifact_path: Path, min_chars: int) -> ModelInfo:
    """상태 확인용: 모델을 메모리에 올리지 않고 준비 여부만 본다(/api/health)."""
    if mode == "none":
        return NoDetectorBackend().info()
    if mode == "dummy":
        return DummyDetectorBackend(min_chars=min_chars).info()
    if mode == "http":
        return HttpDetectorBackend(detector_url).info()
    m = read_manifest(artifact_path)
    try:
        import realstar_model.inference  # type: ignore[import-not-found]  # noqa: F401

        pkg_ok, err = True, None
    except Exception as e:
        pkg_ok, err = False, f"realstar_model 패키지를 불러올 수 없음: {type(e).__name__}"
    if pkg_ok and not m:
        err = f"모델 아티팩트가 아직 없음(첫 판별 때 MODEL_ARTIFACT_URL에서 받음): {artifact_path}"
    return ModelInfo(ready=pkg_ok and bool(m), backend="realstar_model(inprocess)", model_version=m.get("model_version"),
                     thresholds=m.get("thresholds"), min_chars=m.get("min_chars"), error=err)


def make_backend(
    mode: str, *, detector_url: str, artifact_path: Path, min_chars: int, timeout: float = 120.0, artifact_url: str = ""
) -> DetectorBackend:
    if mode == "inprocess":
        return RealstarModelBackend(artifact_path, artifact_url)
    if mode == "dummy":
        return DummyDetectorBackend(min_chars=min_chars)
    if mode == "none":
        return NoDetectorBackend()
    return HttpDetectorBackend(detector_url, timeout=timeout)
