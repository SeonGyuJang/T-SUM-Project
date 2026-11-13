"""배포(Heroku) 관련 설정: DB URL 정규화, Redis TLS, 모델 아티팩트 다운로드."""

from __future__ import annotations

import io
import json
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from realstar.config import Settings
from realstar.detection.backends import ensure_artifact, light_info


def test_heroku_database_url_normalized() -> None:
    s = Settings(_env_file=None, database_url="postgres://u:p@host:5432/db")  # type: ignore[call-arg]
    assert s.database_url == "postgresql+psycopg://u:p@host:5432/db"
    s2 = Settings(_env_file=None, database_url="postgresql://u:p@h/db")  # type: ignore[call-arg]
    assert s2.database_url == "postgresql+psycopg://u:p@h/db"
    s3 = Settings(_env_file=None, database_url="sqlite:///x.db")  # type: ignore[call-arg]
    assert s3.database_url == "sqlite:///x.db"


def test_redis_tls_kwargs() -> None:
    assert Settings(_env_file=None, redis_url="rediss://:pw@h:1").redis_ssl_kwargs == {"ssl_cert_reqs": None}  # type: ignore[call-arg]
    assert Settings(_env_file=None, redis_url="redis://h:1").redis_ssl_kwargs == {}  # type: ignore[call-arg]


def _tar_bytes(top: str | None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in {"manifest.json": json.dumps({"model_version": "det-ko-review-v1.0"}).encode(), "meta_lgbm.txt": b"x"}.items():
            info = tarfile.TarInfo(f"{top}/{name}" if top else name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.mark.parametrize("top", [None, "det-ko-review-v1.0"])
def test_ensure_artifact_downloads(tmp_path: Path, top: str | None) -> None:
    payload = _tar_bytes(top)

    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a: object) -> None: ...

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        dest = tmp_path / "artifacts" / "det-ko-review-v1.0"
        ensure_artifact(dest, f"http://127.0.0.1:{srv.server_port}/a.tar.gz")
        assert json.loads((dest / "manifest.json").read_text())["model_version"] == "det-ko-review-v1.0"
        assert (dest / "meta_lgbm.txt").exists()
        ensure_artifact(dest, "http://127.0.0.1:9/unused")  # 이미 있으면 다시 받지 않는다
    finally:
        srv.shutdown()


def test_light_info_does_not_load_model(tmp_path: Path) -> None:
    info = light_info("inprocess", detector_url="", artifact_path=tmp_path / "none", min_chars=20)
    assert info.ready is False and info.error
    assert light_info("dummy", detector_url="", artifact_path=tmp_path, min_chars=20).is_dummy
