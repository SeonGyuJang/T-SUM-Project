"""CLI: `python -m realstar <명령>`.

  init-db                            개발용 테이블 생성(SQLite). 운영은 `alembic upgrade head`
  analyze --url <쿠팡 링크>          상품 하나를 끝까지 분석(REVIEW_PROVIDER에 따라 수집기 실행 또는 fixture)해 결과 JSON 출력
  export-demo --analysis-id <id>     저장된 분석 결과를 웹 발표 모드 데이터로 내보냄
  prepare-demo --products <파일>     상품 목록을 분석 → 발표 모드 데이터로 한 번에 교체

참고: REVIEW_PROVIDER=crawler(기본)면 저장소 루트의 coupang_reviews.py를 실행해 수집한다.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

from realstar.config import Settings, get_settings


def _settings(args: argparse.Namespace) -> Settings:
    overrides: dict[str, Any] = {}
    if getattr(args, "detector", None):
        overrides["detector_mode"] = args.detector
    if getattr(args, "db", None):
        overrides["database_url"] = args.db
    base = get_settings()
    return base.model_copy(update=overrides) if overrides else base


def cmd_init_db(args: argparse.Namespace) -> int:
    from realstar.db.session import init_db

    s = _settings(args)
    init_db(s.database_url)
    print(f"initialized {s.database_url}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    from realstar.db.session import init_db
    from realstar.pipeline.service import InlineDispatcher, RealstarService

    s = _settings(args)
    init_db(s.database_url)
    dispatcher = InlineDispatcher(s)
    svc = RealstarService(s, dispatcher)
    res = svc.resolve_link(args.url)
    if res.status != "resolved" or not res.candidates:
        print(json.dumps(res.model_dump(), ensure_ascii=False, indent=2))
        return 2
    started = svc.start_analysis(res.candidates[0].product_id, force_refresh=args.force_refresh, input_={"type": "url", "value": args.url})
    print(f"analysis {started['analysis_id']} ({started['status']})", file=sys.stderr)
    last = None
    while True:
        view = svc.get_analysis(started["analysis_id"])
        assert view is not None
        msg = view["progress"].get("message")
        if msg != last:
            print(f"  [{view['status']}] {msg}", file=sys.stderr)
            last = msg
        if view["status"] in ("done", "failed", "blocked"):
            break
        time.sleep(0.5)
    out = view["result"] if view["status"] == "done" else view
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"written {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0 if view["status"] == "done" else 1


DEMO_DATA_DIR_PARTS = ("apps", "web", "src", "demo", "data")


def export_demo_example(settings: Settings, analysis_id: str, key: str, query: str | None, out: Path | None = None) -> Path:
    """저장된 분석 결과를 웹 발표 모드 데이터(JSON)로 내보낸다(README 14.7)."""
    from realstar.config import SERVICE_ROOT
    from realstar.db.models import Analysis
    from realstar.db.session import session_scope

    with session_scope(settings.database_url) as sess:
        a = sess.get(Analysis, analysis_id)
        if a is None or a.status != "done":
            raise SystemExit(f"analysis {analysis_id} not found or not done")
        if (a.result or {}).get("model", {}).get("is_dummy"):
            raise SystemExit("더미 판별기 결과는 발표 데이터로 내보낼 수 없어요. 실제 모델을 연결한 뒤 다시 분석하세요.")
        stars = (a.progress or {}).get("stars", {})
        replay = [
            {"stage": "resolve"},
            *[{"stage": "collect", "star": int(k), "collected": v.get("collected", 0), "target": v.get("target", 0)}
              for k, v in sorted(stars.items(), key=lambda kv: -int(kv[0]))],
            {"stage": "detect"}, {"stage": "aggregate"},
        ]
        example = {"key": key, "is_placeholder": False,
                   "input_examples": {"url": (a.result or {}).get("product", {}).get("url"), "query": query},
                   "result": a.result, "replay": replay}
    path = out or SERVICE_ROOT.joinpath(*DEMO_DATA_DIR_PARTS, f"{key}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_demo_index(keys: list[str]) -> Path:
    """웹이 읽는 예시 목록(src/demo/data/index.ts)을 다시 만든다."""
    from realstar.config import SERVICE_ROOT

    lines = ["// 자동 생성: python -m realstar prepare-demo", ""]
    lines += [f'import ex{i} from "./{k}.json";' for i, k in enumerate(keys)]
    lines += ["", f"export const DEMO_DATA: unknown[] = [{', '.join(f'ex{i}' for i in range(len(keys)))}];", ""]
    path = SERVICE_ROOT.joinpath(*DEMO_DATA_DIR_PARTS, "index.ts")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def cmd_export_demo(args: argparse.Namespace) -> int:
    s = _settings(args)
    try:
        path = export_demo_example(s, args.analysis_id, args.key, args.query, Path(args.out) if args.out else None)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1
    print(f"demo example written: {path}")
    return 0


def cmd_prepare_demo(args: argparse.Namespace) -> int:
    """상품 목록을 차례로 분석하고 발표 모드 데이터로 내보낸다(이전 예시는 목록에서 빠진다)."""
    from urllib.parse import parse_qs, urlparse

    from realstar.db.session import init_db
    from realstar.pipeline.service import InlineDispatcher, RealstarService
    from realstar.resolver.url import classify

    s = _settings(args)
    if s.database_url.startswith("sqlite"):
        init_db(s.database_url)
    links = [ln.strip() for ln in Path(args.products).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    svc = RealstarService(s, InlineDispatcher(s))
    keys: list[str] = []
    failed = 0
    for link in links:
        url, parsed = classify(link)
        res = svc.resolve_link(link) if parsed is None else None
        pid = parsed.product_id if parsed else res.candidates[0].product_id  # type: ignore[union-attr]
        if f"p{pid}" in keys:
            print(f"[{pid}] 목록에 이미 있어 건너뜀", file=sys.stderr)
            continue
        query = (parse_qs(urlparse(url).query).get("q") or [""])[0] or None
        started = svc.start_analysis(pid, force_refresh=args.force_refresh, input_={"type": "url", "value": link})
        print(f"[{pid}] {started['analysis_id']} {started['status']}", file=sys.stderr)
        while True:
            view = svc.get_analysis(started["analysis_id"])
            assert view is not None
            if view["status"] in ("done", "failed", "blocked"):
                break
            time.sleep(2)
        if view["status"] != "done":
            failed += 1
            print(f"[{pid}] {view['status']}: {(view['error'] or {}).get('message')}", file=sys.stderr)
            continue
        try:
            path = export_demo_example(s, started["analysis_id"], f"p{pid}", query)
        except SystemExit as e:
            print(e, file=sys.stderr)
            return 1
        keys.append(f"p{pid}")
        print(f"[{pid}] → {path}", file=sys.stderr)
    # 이전 실행에서 이미 내보낸 상품(이번에 못 한 것)도 목록 순서대로 포함한다
    from realstar.config import SERVICE_ROOT

    data_dir = SERVICE_ROOT.joinpath(*DEMO_DATA_DIR_PARTS)
    ordered = []
    for link in links:
        m = re.search(r"/(?:vp|vm)/products/(\d+)", link)
        k = f"p{m.group(1)}" if m else None
        if k and k not in ordered and (data_dir / f"{k}.json").exists():
            ordered.append(k)
    ordered += [k for k in keys if k not in ordered]
    if ordered:
        print(f"index: {write_demo_index(ordered)}  ({len(ordered)}개)")
        print("웹을 다시 빌드하면 발표 모드에 반영돼요.")
    return 0 if keys and not failed else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="realstar", description="리얼별점 서비스 CLI")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--detector", choices=["http", "inprocess", "dummy", "none"])
        sp.add_argument("--db", help="DATABASE_URL 덮어쓰기")

    sp = sub.add_parser("init-db"); common(sp); sp.set_defaults(fn=cmd_init_db)  # noqa: E702
    sp = sub.add_parser("analyze"); common(sp)  # noqa: E702
    sp.add_argument("--url", required=True)
    sp.add_argument("--out")
    sp.add_argument("--force-refresh", action="store_true")
    sp.set_defaults(fn=cmd_analyze)
    sp = sub.add_parser("export-demo"); common(sp)  # noqa: E702
    sp.add_argument("--analysis-id", required=True)
    sp.add_argument("--key", required=True)
    sp.add_argument("--query")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_export_demo)
    sp = sub.add_parser("prepare-demo"); common(sp)  # noqa: E702
    sp.add_argument("--products", required=True, help="한 줄에 상품 링크 하나")
    sp.add_argument("--force-refresh", action="store_true")
    sp.set_defaults(fn=cmd_prepare_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
