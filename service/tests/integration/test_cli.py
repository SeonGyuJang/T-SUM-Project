from __future__ import annotations

import json
from pathlib import Path

import pytest

from realstar import cli
from realstar.config import Settings


def test_cli_analyze_fixture(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    out = tmp_path / "r.json"
    code = cli.main(["analyze", "--url", "https://www.coupang.com/vp/products/1000000002", "--out", str(out)])
    assert code == 0
    data = json.loads(out.read_text())
    assert data["product"]["product_id"] == "1000000002" and data["ratings"]["avg_all"] is not None


def test_cli_cooldown(settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert cli.main(["cooldown"]) == 0
    assert '"active": false' in capsys.readouterr().out
    assert cli.main(["cooldown", "--clear"]) == 0


def test_cli_export_demo_refuses_dummy(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    out = tmp_path / "r.json"
    cli.main(["analyze", "--url", "https://www.coupang.com/vp/products/1000000002", "--out", str(out)])
    aid = json.loads(out.read_text())["analysis_id"]
    assert cli.main(["export-demo", "--analysis-id", aid, "--key", "x", "--out", str(tmp_path / "d.json")]) == 1
