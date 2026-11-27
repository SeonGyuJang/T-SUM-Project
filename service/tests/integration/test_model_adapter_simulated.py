"""모델 완성 후 경로를 미리 검증: 계약(MODEL_DEV.md 4.12.2)대로 만든 가짜 realstar_model 패키지를 주입한다.

실제 모델 코드가 아니다. service 어댑터가 계약대로 호출하는지만 본다.
"""

from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from realstar.config import Settings
from realstar.detection import preprocess
from realstar.detection.backends import RealstarModelBackend
from realstar.pipeline.analysis import AnalysisPipeline
from realstar.pipeline.service import InlineDispatcher, RealstarService


@dataclass
class ReviewInput:
    review_id: str
    title: str | None
    content: str
    star: int | None = None


@dataclass
class Prediction:
    review_id: str
    p_ai: float
    p_human: float
    label: str
    len_bucket: str
    features: dict = field(default_factory=dict)  # type: ignore[type-arg]
    reason_tags: list[str] = field(default_factory=list)
    model_version: str = "det-ko-review-v1.0"


class Detector:
    loaded_from: str | None = None

    @classmethod
    def load(cls, path: str) -> Detector:
        d = cls()
        d.loaded_from = path
        return d

    def predict(self, items: list[ReviewInput], batch_size: int = 64) -> list[Prediction]:
        out = []
        for it in items:
            p_ai = 0.9 if "AI" in it.content else 0.1
            out.append(Prediction(it.review_id, p_ai, 1 - p_ai, "ai" if p_ai > 0.5 else "human", "M", {"probe_score": 0.1}, ["구어체 표현"]))
        return out


@dataclass
class Cleaned:
    clean_text: str
    text_for_model: str
    len_chars: int
    is_sponsored: bool
    is_cash_event: bool


def clean_review(title: str | None, content: str) -> Cleaned:
    cash = "쿠팡캐시" in content
    body = content.split("작성한 것입니다.")[-1].strip() if cash else content
    text = f"{title} / {body}" if title else body
    return Cleaned(body, text, len(text), False, cash)


@pytest.fixture()
def fake_model_pkg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pkg = types.ModuleType("realstar_model")
    inf = types.ModuleType("realstar_model.inference")
    pre = types.ModuleType("realstar_model.preprocess")
    inf.Detector, inf.ReviewInput = Detector, ReviewInput  # type: ignore[attr-defined]
    pre.clean_review = clean_review  # type: ignore[attr-defined]
    for name, mod in {"realstar_model": pkg, "realstar_model.inference": inf, "realstar_model.preprocess": pre}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    art = tmp_path / "det-ko-review-v1.0"
    art.mkdir()
    (art / "manifest.json").write_text(json.dumps({
        "model_version": "det-ko-review-v1.0", "min_chars": 20,
        "thresholds": {"S": {"T_AI": 0.9, "T_HUMAN": 0.2}, "M": {"T_AI": 0.8, "T_HUMAN": 0.3}, "L": {"T_AI": 0.75, "T_HUMAN": 0.3}},
        "metrics_summary": {"sensitivity": 0.85, "specificity": 0.98},
    }))
    return art


def test_backend_loads_artifact(fake_model_pkg: Path) -> None:
    b = RealstarModelBackend(fake_model_pkg)
    info = b.info()
    assert info.ready and info.model_version == "det-ko-review-v1.0"
    assert info.thresholds and info.thresholds["M"]["T_AI"] == 0.8
    from realstar.detection.schemas import DetectInput

    out = b.predict([DetectInput(review_id="x", content="AI 같은 글")])
    assert out[0].label == "ai" and out[0].reason_tags == ["구어체 표현"]


def test_preprocess_uses_model_package(fake_model_pkg: Path) -> None:
    assert preprocess.model_preprocess_available()
    c = preprocess.clean(None, "본 리뷰는 쿠팡캐시를 지급받기 위해 작성한 것입니다. 좋아요")
    assert c.source == "realstar_model" and c.is_cash_event and c.clean_text == "좋아요"


def test_full_pipeline_with_model(fake_model_pkg: Path, settings: Settings) -> None:
    pipe = AnalysisPipeline(settings, detector=RealstarModelBackend(fake_model_pkg))
    disp = InlineDispatcher(settings, pipe)
    svc = RealstarService(settings, disp)
    a = svc.start_analysis("1000000002")
    disp.wait_all(60)
    v = svc.get_analysis(a["analysis_id"])
    assert v and v["status"] == "done", v and v["error"]
    res = v["result"]
    assert res["model"]["version"] == "det-ko-review-v1.0" and not res["model"]["is_dummy"]
    assert res["model"]["T_AI"] == 0.8 and res["model"]["T_HUMAN"] == 0.3
    codes = {w["code"] for w in res["warnings"]}
    assert "dummy_detector" not in codes and "preprocess_unavailable" not in codes
    assert res["ratings"]["corrected"]["method"] == "rogan_gladen"  # manifest의 sens/spec 사용
    assert res["top_human_reviews"]["5"][0]["reason_tags"] == ["구어체 표현"]


def test_prepare_demo_with_model(fake_model_pkg: Path, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """시연 상품 목록 → 실제 분석(모델 연결 상태) → 발표 모드 데이터·index.ts 생성."""
    import realstar.config as cfg
    from realstar import cli

    s = settings.model_copy(update={"detector_mode": "inprocess", "model_artifact_path": fake_model_pkg})
    monkeypatch.setattr(cli, "get_settings", lambda: s)
    monkeypatch.setattr(cfg, "SERVICE_ROOT", tmp_path)  # 실제 웹 데이터 폴더를 건드리지 않게
    products = tmp_path / "products.txt"
    products.write_text("# 주석\nhttps://www.coupang.com/vp/products/1000000001?itemId=1&q=%EC%B2%AD%EC%86%8C%EA%B8%B0\n"
                        "https://link.coupang.com/a/demo01\n", encoding="utf-8")
    assert cli.main(["prepare-demo", "--products", str(products)]) == 0
    data_dir = tmp_path / "apps" / "web" / "src" / "demo" / "data"
    ex = json.loads((data_dir / "p1000000001.json").read_text())
    assert ex["is_placeholder"] is False and ex["input_examples"]["query"] == "청소기"
    assert ex["result"]["model"]["version"] == "det-ko-review-v1.0+th90-20"  # 서비스 판정 기준(90%·20%) 표시
    assert [r["star"] for r in ex["replay"] if r["stage"] == "collect"] == [5, 4, 3, 2, 1]
    index = (data_dir / "index.ts").read_text()
    assert 'import ex0 from "./p1000000001.json";' in index and "DEMO_DATA" in index


def test_prepare_demo_refuses_dummy(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import realstar.config as cfg
    from realstar import cli

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cfg, "SERVICE_ROOT", tmp_path)
    products = tmp_path / "p.txt"
    products.write_text("https://www.coupang.com/vp/products/1000000002\n", encoding="utf-8")
    assert cli.main(["prepare-demo", "--products", str(products)]) == 1
    assert not (tmp_path / "apps").exists()
