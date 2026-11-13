"""CLI: `python -m realstar <명령>` (README Phase 4, Phase 0, Phase 8).

  analyze --url <쿠팡 링크>         링크 하나로 끝까지 분석하고 결과 JSON을 출력
  init-db                            개발용 테이블 생성(SQLite). 운영은 `alembic upgrade head`
  spike --url <링크> [--url ...]     Phase 0 수집 가능성 점검 리포트 (실사이트, 수동 실행)
  diagnose-html <파일|폴더>          저장된 HTML에 셀렉터 후보를 대어 보고 파서 결과를 보여줌
  smoke --url <링크>                 일일 셀렉터 스모크 테스트 (상품 1개)
  export-training --targets <파일>   학습용 과거 리뷰를 model/data/raw/coupang/로 내보냄
  export-demo --analysis-id <id>     저장된 실제 분석 결과를 웹 발표 모드 데이터로 내보냄
  prepare-demo --products <파일>     시연 상품 목록을 실제 분석 → 발표 모드 데이터로 한 번에 교체
  cooldown [--clear]                 차단 쿨다운 상태 확인/해제
"""

from __future__ import annotations

import argparse
import json
import logging
import re
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


def _say(ok: bool | None, msg: str) -> None:
    mark = {True: "✓", False: "✗", None: "·"}[ok]
    print(f"  {mark} {msg}", flush=True)


def provider_version() -> str:
    from realstar.collectors.coupang.selectors import load_selectors

    return load_selectors().version


def cmd_spike(args: argparse.Namespace) -> int:
    """Phase 0: 실제 상품으로 메타·정렬·필터·별점별 수집을 규칙 속도로 확인하고 리포트·HTML 스냅샷을 남긴다."""
    from realstar.collectors.base import STARS
    from realstar.collectors.coupang.provider import CoupangScraperProvider
    from realstar.errors import RealstarError
    from realstar.resolver.url import classify
    from realstar.state.store import Cooldown, get_state_store

    s = _settings(args).model_copy(update={"scraper_debug_html_keep": 500})
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir or f"var/spike/{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    state = get_state_store(s)
    cooldown = Cooldown(state, s.scraper_block_cooldown_min)
    if cooldown.status():
        print(f"차단 쿨다운 중이라 실행하지 않아요: {cooldown.status()}\n(확인 후 해제: python -m realstar cooldown --clear)", file=sys.stderr)
        return 3
    print(f"수집 점검 시작 — 상품 {len(args.url)}개, 별점당 최대 {args.per_star}개, 대기 {s.scraper_delay_min_sec:g}~{s.scraper_delay_max_sec:g}초,"
          f" Chrome 창 {'숨김' if s.scraper_headless else '표시'}, 셀렉터 {provider_version()}")
    print(f"결과 폴더: {out_dir.resolve()}\n")
    report: dict[str, Any] = {"started_at": datetime.now(UTC).isoformat(), "products": [], "settings": {
        "delay": [s.scraper_delay_min_sec, s.scraper_delay_max_sec], "per_star": args.per_star, "headless": s.scraper_headless}}
    provider = CoupangScraperProvider(s, state, snapshot_dir=out_dir / "html")
    stopped = False
    try:
        for n, url in enumerate(args.url, 1):
            entry: dict[str, Any] = {"url": url}
            t0 = time.time()
            print(f"[{n}/{len(args.url)}] {url[:90]}")
            step = "링크 해석"
            try:
                link, parsed = classify(url)
                pid = parsed.product_id if parsed else classify(provider.resolve_short_url(link))[1].product_id  # type: ignore[union-attr]
                entry["product_id"] = pid
                _say(True, f"상품번호 {pid}")
                step = "상품 페이지"
                meta = provider.get_product_meta(pid)
                entry["meta"] = meta.model_dump()
                counts = meta.resolved_star_counts() if meta.total_reviews else {}
                entry["star_counts"] = counts
                _say(True, f"상품명: {meta.name[:50]}")
                _say(True, f"표시 평균 ★{meta.displayed_avg} · 리뷰 {meta.total_reviews:,}개 · 별점 분포 {dict(counts)}"
                           f" ({'개수' if meta.star_counts else '비율에서 계산'})")
                entry["per_star"] = {}
                for star in STARS:
                    if not counts.get(star):
                        _say(None, f"{star}점 리뷰 없음 — 건너뜀")
                        continue
                    step = f"{star}점 리뷰 수집"
                    ts = time.time()
                    revs = provider.get_reviews(pid, star, args.per_star, sort="latest")
                    target = min(args.per_star, counts[star])
                    dates = [r.created_at for r in revs if r.created_at]
                    ok = len(revs) >= target
                    _say(ok, f"{star}점 {len(revs)}/{target}개 ({time.time() - ts:.0f}초, 페이지 누적 {provider.pages_loaded})"
                             + (f" · 작성일 {max(dates)}~{min(dates)}" if dates else ""))
                    entry["per_star"][star] = {"collected": len(revs), "target": target, "dates": dates[:5],
                                               "sample": [r.content[:80] for r in revs[:3]]}
                entry["outcome"] = "ok"
            except RealstarError as e:
                entry["outcome"] = e.code
                entry["failed_step"] = step
                entry["detail"] = e.detail
                if getattr(e, "failed_selectors", None):
                    entry["failed_selectors"] = e.failed_selectors  # type: ignore[attr-defined]
                _say(False, f"{step} 실패 — {e.code}: {e.detail[:160]}")
                if provider.browser.started:
                    provider.browser.save_snapshot(provider.browser.page_source, label=f"FAILED_{e.code}")
                if e.code == "blocked":
                    cooldown.start(getattr(e, "signal", "blocked"))
                    entry["blocked_at_page"] = provider.pages_loaded
                    _say(False, "차단 신호 → 우회하지 않고 즉시 중단, 60분 쿨다운")
                    stopped = True
            entry["elapsed_sec"] = round(time.time() - t0, 1)
            entry["pages_loaded_total"] = provider.pages_loaded
            report["products"].append(entry)
            print(f"  → {entry['outcome']} ({entry['elapsed_sec']}초)\n")
            if stopped:
                break
    finally:
        provider.close()
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["selectors_version"] = provider.selectors_version
    out = Path(args.out) if args.out else out_dir / "report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    ok_n = sum(1 for p in report["products"] if p.get("outcome") == "ok")
    print(f"요약: 성공 {ok_n}/{len(args.url)} · 페이지 {provider.pages_loaded}개 · 리포트 {out}")
    print(f"HTML 스냅샷(닉네임 가림): {out_dir / 'html'}")
    if ok_n < len(args.url):
        print("실패한 경우: 위 폴더를 통째로 공유해 주시면 셀렉터를 실제 화면에 맞게 고칠 수 있어요.")
        print(f"  직접 확인: python -m realstar diagnose-html {out_dir / 'html'}")
    return 0 if ok_n == len(args.url) else 1


def cmd_diagnose_html(args: argparse.Namespace) -> int:
    """저장된 HTML에 selectors.yaml의 후보 셀렉터를 대어 보고 몇 개가 맞는지 보여준다."""
    from realstar.collectors.coupang.product_page import parse_product_page
    from realstar.collectors.coupang.review_page import parse_reviews
    from realstar.collectors.coupang.search_page import parse_search_page
    from realstar.collectors.coupang.selectors import load_selectors, make_soup
    from realstar.errors import RealstarError

    sel = load_selectors()
    target = Path(args.path)
    files = sorted(target.glob("*.html")) if target.is_dir() else [target]
    for f in files:
        html = f.read_text(encoding="utf-8", errors="replace")
        soup = make_soup(html)
        print(f"\n== {f.name} ({len(html):,}자, 제목: {(soup.title.get_text(strip=True) if soup.title else '')[:40]})")
        for section in ("product", "reviews", "search", "block"):
            for key, val in sel.section(section).items():
                if not isinstance(val, list) or not val or not all(isinstance(v, str) for v in val):
                    continue
                if section == "block" and key != "element_selectors":
                    continue
                hits = [(css, len(soup.select(css))) for css in val]
                if any(h for _, h in hits) or args.all:
                    print(f"  {section}.{key}: " + ", ".join(f"{css!r}={h}" for css, h in hits if h or args.all))
        for name, fn in (
            ("상품 파서", lambda h: parse_product_page(h, sel, "0").model_dump(include={"name", "displayed_avg", "total_reviews", "star_counts", "star_ratio"})),
            ("리뷰 파서", lambda h: f"{len(parse_reviews(h, sel, '0')[0])}개, 누락률 {parse_reviews(h, sel, '0')[1].missing_rates()}"),
            ("검색 파서", lambda h: f"{len(parse_search_page(h, sel))}개 후보"),
        ):
            try:
                print(f"  → {name}: {fn(html)}")
            except RealstarError as e:
                print(f"  → {name}: 실패 {e.code} {getattr(e, 'failed_selectors', '')}")
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    """Phase 8: 고정 상품 1개로 메타 + 별점 1개 첫 페이지만 확인. 실패하면 종료 코드 1."""
    args.per_star = 10
    args.url = [args.url]
    args.out = args.out or "var/smoke_last.json"
    args.out_dir = None
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


DEMO_DATA_DIR_PARTS = ("apps", "web", "src", "demo", "data")


def export_demo_example(settings: Settings, analysis_id: str, key: str, query: str | None, out: Path | None = None) -> Path:
    """실제로 분석해 저장한 결과를 웹 발표 모드 데이터(JSON)로 내보낸다(README 14.7)."""
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

    lines = ["// 자동 생성: python -m realstar prepare-demo / export-demo --update-index", ""]
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
    """시연 상품 목록을 차례로 실제 분석하고 발표 모드 데이터로 내보낸다(이전 예시는 목록에서 빠진다)."""
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
            if view["status"] == "blocked":
                print("차단되어 중단합니다(쿨다운 후 다시 실행). 이미 내보낸 예시는 유지돼요.", file=sys.stderr)
                break
            continue
        try:
            path = export_demo_example(s, started["analysis_id"], f"p{pid}", query)
        except SystemExit as e:
            print(e, file=sys.stderr)
            return 1
        keys.append(f"p{pid}")
        print(f"[{pid}] → {path}", file=sys.stderr)
    # 이전 실행에서 이미 내보낸 상품(차단 등으로 이번에 못 한 것)도 목록 순서대로 포함한다
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
    sp.add_argument("--out-dir", help="리포트·HTML 스냅샷 폴더 (기본 var/spike/<시각>)")
    sp.set_defaults(fn=cmd_spike)
    sp = sub.add_parser("diagnose-html"); common(sp)  # noqa: E702
    sp.add_argument("path", help="HTML 파일 또는 폴더")
    sp.add_argument("--all", action="store_true", help="맞지 않은 셀렉터도 표시")
    sp.set_defaults(fn=cmd_diagnose_html)
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
    sp = sub.add_parser("prepare-demo"); common(sp)  # noqa: E702
    sp.add_argument("--products", required=True, help="한 줄에 상품 링크 하나 (예: ../docs/demo-products.txt)")
    sp.add_argument("--force-refresh", action="store_true")
    sp.set_defaults(fn=cmd_prepare_demo)
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
