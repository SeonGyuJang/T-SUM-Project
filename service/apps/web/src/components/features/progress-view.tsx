"use client";

import { Check, Loader2, MinusCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import type { AnalysisView, StarKey } from "@/lib/api/schema";
import { STARS } from "@/lib/api/schema";
import { cn } from "@/lib/cn";
import { fmtCount, fmtDuration } from "@/lib/format";
import { ProductThumb } from "./product-thumb";

const STEPS = [
  { key: "resolve", label: "상품 확인" },
  { key: "collect", label: "리뷰 수집" },
  { key: "detect", label: "AI 판별" },
  { key: "aggregate", label: "결과 정리" },
] as const;

/** 수집기(coupang_reviews.py) 실행 단계. progress.crawl_stage 값과 같다. */
const CRAWL_STEPS = [
  { key: "browser", label: "브라우저 실행" },
  { key: "open_page", label: "상품 페이지 열기" },
  { key: "summary", label: "별점별 개수 확인" },
  { key: "reviews", label: "별점별 리뷰 수집" },
  { key: "saved", label: "저장" },
] as const;

function crawlIndex(stage: string | undefined, collecting: boolean): number {
  switch (stage) {
    case "start":
    case "browser":
      return 0;
    case "open_page":
      return 1;
    case "page_loaded":
    case "summary":
      return collecting ? 3 : 2;
    case "saved":
      return 4;
    default:
      return collecting ? 3 : -1;
  }
}

function stepIndex(v: AnalysisView): number {
  switch (v.status) {
    case "queued":
      return 0;
    case "collecting":
      return 1;
    case "detecting":
      return 2;
    case "aggregating":
      return 3;
    default:
      return 4;
  }
}

function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

function fmtElapsed(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return m > 0 ? `${m}분 ${String(s).padStart(2, "0")}초` : `${s}초`;
}

function fmtClock(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(d);
}

export function ProgressView({ view }: { view: AnalysisView }) {
  const now = useNow();
  const idx = stepIndex(view);
  const p = view.progress;
  const product = p.product;
  const stars = p.stars ?? {};
  const skipDetect = p.detection_available === false;

  const totals = STARS.reduce(
    (acc, k) => {
      const s = stars[k];
      if (!s || s.status === "skipped") return acc;
      return { collected: acc.collected + Math.min(s.collected ?? 0, s.target ?? 0), target: acc.target + (s.target ?? 0) };
    },
    { collected: 0, target: 0 },
  );
  const overallPct = totals.target ? Math.min(100, Math.round((totals.collected / totals.target) * 100)) : 0;
  const startedMs = p.started_at ? new Date(p.started_at).getTime() : view.created_at ? new Date(view.created_at).getTime() : NaN;
  const elapsed = Number.isFinite(startedMs) ? Math.max(0, (now - startedMs) / 1000) : null;
  const collectingStar = STARS.some((k) => stars[k]?.status === "collecting" || stars[k]?.status === "done" || stars[k]?.status === "partial");
  const cIdx = crawlIndex(p.crawl_stage, collectingStar);
  const showCrawl = view.status === "collecting" && !p.from_cache && p.crawl_stage !== undefined;
  const logs = p.logs ?? [];

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div className="flex items-center gap-4">
        <ProductThumb src={product?.image_url} alt={product?.name ?? "상품 이미지"} size={72} />
        <div className="min-w-0">
          <p className="text-caption text-muted">분석 중인 상품</p>
          <h1 className="line-clamp-2 text-h2">{product?.name ?? `상품 ${view.product_id}`}</h1>
        </div>
      </div>

      <ol className="grid grid-cols-4 gap-2" aria-label="진행 단계">
        {STEPS.map((s, i) => {
          const skipped = s.key === "detect" && skipDetect;
          const state = skipped ? "skipped" : i < idx ? "done" : i === idx ? "active" : "todo";
          return (
            <li key={s.key} className="flex flex-col items-center gap-2 text-center" aria-current={state === "active" ? "step" : undefined}>
              <span className={cn("flex size-10 items-center justify-center rounded-full border-2 text-caption font-bold",
                state === "done" && "border-primary bg-primary text-primary-fg",
                state === "active" && "border-primary text-primary",
                state === "todo" && "border-border text-muted",
                state === "skipped" && "border-dashed border-border-strong text-muted")}>
                {state === "done" ? <Check aria-hidden className="size-5" /> : state === "active" ? <Loader2 aria-hidden className="size-5 animate-spin" /> : state === "skipped" ? <MinusCircle aria-hidden className="size-5" /> : i + 1}
              </span>
              <span className={cn("text-caption font-medium", state === "todo" || state === "skipped" ? "text-muted" : "text-text")}>
                {s.label}
                {skipped && <span className="block text-[0.75rem] font-normal">모델 준비 중 · 건너뜀</span>}
              </span>
              <span className="sr-only">{state === "done" ? "완료" : state === "active" ? "진행 중" : state === "skipped" ? "건너뜀" : "대기"}</span>
            </li>
          );
        })}
      </ol>

      <Card className="space-y-6 p-6 md:p-8">
        <div aria-live="polite" aria-atomic="true" className="space-y-1">
          <p className="text-h3">{p.message ?? (view.status === "queued" ? "대기열에서 순서를 기다리고 있어요" : "분석하고 있어요")}</p>
          <p className="text-caption text-muted num">
            {view.status === "queued" && p.queue_position ? `대기 순번 ${p.queue_position}번 · ` : ""}
            {elapsed != null && view.status !== "queued" ? `경과 ${fmtElapsed(elapsed)} · ` : ""}
            {view.status === "collecting" || view.status === "queued" ? `예상 남은 시간 ${fmtDuration(p.eta_seconds)}` : "곧 결과가 나와요"}
            {p.pages_loaded ? ` · 요청한 리뷰 페이지 ${fmtCount(p.pages_loaded)}개` : ""}
            {p.from_cache ? " · 저장된 리뷰 표본을 사용해요" : ""}
            {p.from_saved_file ? " · 이미 수집해 둔 파일을 사용해요" : ""}
          </p>
        </div>

        {showCrawl && (
          <ol className="flex flex-wrap gap-x-4 gap-y-2 text-caption" aria-label="수집기 진행 단계">
            {CRAWL_STEPS.map((s, i) => {
              const state = i < cIdx ? "done" : i === cIdx ? "active" : "todo";
              return (
                <li key={s.key} className={cn("inline-flex items-center gap-1.5", state === "todo" ? "text-muted" : "text-text", state === "active" && "font-semibold")}>
                  {state === "done" ? <Check aria-hidden className="size-4 text-primary" /> : state === "active" ? <Loader2 aria-hidden className="size-4 animate-spin text-primary" /> : <span aria-hidden className="inline-block size-4 rounded-full border border-border-strong" />}
                  {s.label}
                </li>
              );
            })}
          </ol>
        )}

        {totals.target > 0 && (
          <div className="space-y-2">
            <div className="flex items-baseline justify-between text-caption">
              <span className="font-semibold">전체 수집 진행률</span>
              <span className="num text-muted">{fmtCount(totals.collected)} / {fmtCount(totals.target)}개 · {overallPct}%</span>
            </div>
            <span className="block h-3 overflow-hidden rounded-full bg-subtle" role="progressbar" aria-label="전체 리뷰 수집" aria-valuemin={0} aria-valuemax={100} aria-valuenow={overallPct}>
              <span className="block h-full rounded-full bg-primary transition-all duration-300" style={{ width: `${overallPct}%` }} />
            </span>
          </div>
        )}

        <div>
          <p className="mb-3 text-caption font-semibold text-muted">
            별점별 수집 현황 (별점마다 최대 {fmtCount(STARS.map((k) => stars[k]?.target ?? 0).reduce((a, b) => Math.max(a, b), 0) || 100)}개)
            {p.total_reviews ? ` · 전체 리뷰 ${fmtCount(p.total_reviews)}개` : ""}
          </p>
          <ul className="space-y-3">
            {STARS.map((k: StarKey) => {
              const s = stars[k];
              const target = s?.target ?? 0;
              const collected = s?.collected ?? 0;
              const pct = target ? Math.min(100, Math.round((collected / target) * 100)) : s?.status === "skipped" ? 100 : 0;
              const label =
                s?.status === "skipped" ? "리뷰 없음"
                : s ? `${fmtCount(collected)} / ${fmtCount(target)}${s.status === "partial" ? " (일부)" : ""}`
                : "대기";
              return (
                <li key={k} className="grid grid-cols-[2.5rem_1fr_6.5rem] items-center gap-3 sm:grid-cols-[3rem_1fr_8rem]">
                  <span className="text-caption font-semibold num">{k}점</span>
                  <span className="h-2.5 overflow-hidden rounded-full bg-subtle" role="progressbar" aria-label={`${k}점 리뷰 수집`} aria-valuemin={0} aria-valuemax={target || 100} aria-valuenow={target ? collected : pct}>
                    <span className={cn("block h-full rounded-full transition-all duration-200", s?.status === "partial" ? "bg-warning" : "bg-primary", s?.status === "collecting" && "animate-pulse")} style={{ width: `${pct}%` }} />
                  </span>
                  <span className="text-right text-caption text-muted num">{label}</span>
                </li>
              );
            })}
          </ul>
        </div>

        {view.status === "detecting" && p.detect_total ? (
          <p className="text-caption text-muted num">판별한 리뷰 {fmtCount(p.detected ?? 0)} / {fmtCount(p.detect_total)}</p>
        ) : null}

        {logs.length > 0 && (
          <details className="rounded-lg border border-border bg-subtle" open>
            <summary className="cursor-pointer px-4 py-2.5 text-caption font-semibold">수집 기록</summary>
            <ol className="max-h-56 space-y-1 overflow-y-auto px-4 pb-3 font-mono text-[0.8rem] leading-relaxed text-muted" aria-live="off">
              {logs.map((l, i) => (
                <li key={`${l.at ?? ""}-${i}`} className="break-all">
                  {l.at && <span className="mr-2 text-text num">{fmtClock(l.at)}</span>}
                  {l.message}
                </li>
              ))}
            </ol>
          </details>
        )}
      </Card>
      <p className="text-center text-caption text-muted">이 창을 닫아도 수집은 계속돼요. 같은 주소로 다시 들어오면 진행 상황과 결과를 볼 수 있어요.</p>
    </div>
  );
}
