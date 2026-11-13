"""CLI: `python -m realstar <명령>` (README Phase 4, Phase 0, Phase 8).

  analyze --url <쿠팡 링크>         링크 하나로 끝까지 분석하고 결과 JSON을 출력
  init-db                            개발용 테이블 생성(SQLite). 운영은 `alembic upgrade head`
  spike --url <링크> [--url ...]     Phase 0 수집 가능성 점검 리포트 (실사이트, 수동 실행)
  smoke --url <링크>                 일일 셀렉터 스모크 테스트 (상품 1개)
  export-training --targets <파일>   학습용 과거 리뷰를 model/data/raw/coupang/로 내보냄
  export-demo --analysis-id <id>     저장된 실제 분석 결과를 웹 발표 모드 데이터로 내보냄
  cooldown [--clear]                 차단 쿨다운 상태 확인/해제
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from realstar.config import Settings, get_settings


def _settings(args: argparse.Namespace) -> Settings:
    overrides: dict[str, Any] = {}
    if getattr(args, "provider", None):
        overrides["review_provider"] = args.provider
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


def cmd_spike(args: argparse.Namespace) -> int:
    """Phase 0: 실제 상품 몇 개로 메타·정렬·필터·별점당 수집을 규칙 속도로 확인하고 리포트를 남긴다."""
    from realstar.collectors.base import STARS
    from realstar.collectors.coupang.provider import CoupangScraperProvider
    from realstar.errors import RealstarError
    from realstar.resolver.url import classify
    from realstar.state.store import Cooldown, get_state_store

    s = _settings(args).model_copy(update={"scraper_debug_html_keep": 200})
    state = get_state_store(s)
    cooldown = Cooldown(state, s.scraper_block_cooldown_min)
    if cooldown.status():
        print(f"cooldown active: {cooldown.status()}", file=sys.stderr)
        return 3
    report: dict[str, Any] = {"started_at": datetime.now(UTC).isoformat(), "products": [], "settings": {
        "delay": [s.scraper_delay_min_sec, s.scraper_delay_max_sec], "per_star": args.per_star, "headless": s.scraper_headless}}
    provider = CoupangScraperProvider(s, state)
    try:
        for url in args.url:
            entry: dict[str, Any] = {"url": url}
            t0 = time.time()
            try:
                link, parsed = classify(url)
                pid = parsed.product_id if parsed else classify(provider.resolve_short_url(link))[1].product_id  # type: ignore[union-attr]
                entry["product_id"] = pid
                meta = provider.get_product_meta(pid)
                entry["meta"] = meta.model_dump()
                entry["star_counts"] = meta.resolved_star_counts() if meta.total_reviews else {}
                entry["per_star"] = {}
                for star in STARS:
                    if not entry["star_counts"].get(star):
                        continue
                    revs = provider.get_reviews(pid, star, args.per_star, sort="latest")
                    entry["per_star"][star] = {"collected": len(revs), "sample": [r.content[:60] for r in revs[:2]],
                                               "dates": [r.created_at for r in revs[:3]]}
                entry["outcome"] = "ok"
            except RealstarError as e:
                entry["outcome"] = e.code
                entry["detail"] = e.detail
                if e.code == "blocked":
                    cooldown.start(getattr(e, "signal", "blocked"))
                    entry["blocked_at_page"] = provider.pages_loaded
                    report["products"].append(entry)
                    break  # 차단되면 우회하지 않고 중단 → 오너에게 보고
            entry["elapsed_sec"] = round(time.time() - t0, 1)
            entry["pages_loaded_total"] = provider.pages_loaded
            report["products"].append(entry)
    finally:
        provider.close()
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["selectors_version"] = provider.selectors_version
    out = Path(args.out or f"var/spike_report_{datetime.now():%Y%m%d_%H%M}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"spike report: {out}  (HTML 스냅샷: {s.scraper_debug_html_dir})")
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    """Phase 8: 고정 상품 1개로 메타 + 별점 1개 첫 페이지만 확인. 실패하면 종료 코드 1."""
    args.per_star = 10
    args.url = [args.url]
    args.out = args.out or "var/smoke_last.json"
    cmd_spike(args)
    report = json.loads(Path(args.out).read_text(encoding="utf-8"))
    ok = bool(report["products"]) and all(p.get("outcome") == "ok" for p in report["products"])
    print("SMOKE OK" if ok else "SMOKE FAILED — selectors.yaml 점검 필요")
    return 0 if ok else 1


def cmd_export_training(args: argparse.Namespace) -> int:
    from realstar.collectors import make_provider
    from realstar.collectors.export_training import export_training_batch, read_targets
    from realstar.state.store import Cooldown, get_state_store

    s = _settings(args)
    state = get_state_store(s)
    cooldown = Cooldown(state, s.scraper_block_cooldown_min)
    if cooldown.status():
        print(f"cooldown active: {cooldown.status()}", file=sys.stderr)
        return 3
    provider = make_provider(s, state, training=True)
    try:
        path, n, outcome = export_training_batch(
            provider, read_targets(Path(args.targets)), Path(args.out_dir or s.training_export_dir),
            batch=args.batch, cutoff=s.training_cutoff_date, per_star_limit=s.training_per_star_limit, sort=args.sort,
        )
    finally:
        provider.close()
    if outcome == "blocked":
        cooldown.start("training_export")
    print(f"{outcome}: {n} reviews → {path}")
    return 0 if outcome == "ok" else 1


def cmd_export_demo(args: argparse.Namespace) -> int:
    """실제로 분석해 저장한 결과를 웹 발표 모드 데이터(JSON)로 내보낸다(README 14.7)."""
    from realstar.db.models import Analysis
    from realstar.db.session import session_scope

    s = _settings(args)
    with session_scope(s.database_url) as sess:
        a = sess.get(Analysis, args.analysis_id)
        if a is None or a.status != "done":
            print("analysis not found or not done", file=sys.stderr)
            return 1
        if (a.result or {}).get("model", {}).get("is_dummy"):
            print("더미 판별기 결과는 발표 데이터로 내보낼 수 없어요.", file=sys.stderr)
            return 1
        stars = (a.progress or {}).get("stars", {})
        log = [
            {"stage": "resolve", "t": 0},
            *[{"stage": "collect", "star": int(k), "collected": v.get("collected", 0), "target": v.get("target", 0)} for k, v in stars.items()],
            {"stage": "detect"}, {"stage": "aggregate"},
        ]
        example = {"key": args.key, "is_placeholder": False, "input_examples": {"url": (a.result or {}).get("product", {}).get("url"), "query": args.query},
                   "result": a.result, "replay": log}
    out = Path(args.out or f"../apps/web/src/demo/data/{args.key}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"demo example written: {out}")
    return 0


def cmd_cooldown(args: argparse.Namespace) -> int:
    from realstar.state.store import Cooldown, get_state_store

    s = _settings(args)
    cd = Cooldown(get_state_store(s), s.scraper_block_cooldown_min)
    if args.clear:
        cd.clear()
        print("cooldown cleared")
    else:
        print(json.dumps(cd.status() or {"active": False}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="realstar", description="리얼별점 서비스 CLI")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--provider", choices=["coupang", "fixture"])
        sp.add_argument("--detector", choices=["http", "inprocess", "dummy"])
        sp.add_argument("--db", help="DATABASE_URL 덮어쓰기")

    sp = sub.add_parser("init-db"); common(sp); sp.set_defaults(fn=cmd_init_db)  # noqa: E702
    sp = sub.add_parser("analyze"); common(sp)  # noqa: E702
    sp.add_argument("--url", required=True)
    sp.add_argument("--out")
    sp.add_argument("--force-refresh", action="store_true")
    sp.set_defaults(fn=cmd_analyze)
    sp = sub.add_parser("spike"); common(sp)  # noqa: E702
    sp.add_argument("--url", action="append", required=True)
    sp.add_argument("--per-star", type=int, default=100)
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_spike)
    sp = sub.add_parser("smoke"); common(sp)  # noqa: E702
    sp.add_argument("--url", required=True)
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_smoke)
    sp = sub.add_parser("export-training"); common(sp)  # noqa: E702
    sp.add_argument("--targets", required=True)
    sp.add_argument("--batch", default="b001")
    sp.add_argument("--out-dir")
    sp.add_argument("--sort", choices=["latest", "best"], default="best")
    sp.set_defaults(fn=cmd_export_training)
    sp = sub.add_parser("export-demo"); common(sp)  # noqa: E702
    sp.add_argument("--analysis-id", required=True)
    sp.add_argument("--key", required=True)
    sp.add_argument("--query")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_export_demo)
    sp = sub.add_parser("cooldown"); common(sp)  # noqa: E702
    sp.add_argument("--clear", action="store_true")
    sp.set_defaults(fn=cmd_cooldown)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
