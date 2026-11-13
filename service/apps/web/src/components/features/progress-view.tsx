import { Check, Loader2 } from "lucide-react";
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
  { key: "aggregate", label: "결과 계산" },
] as const;

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

export function ProgressView({ view }: { view: AnalysisView }) {
  const idx = stepIndex(view);
  const p = view.progress;
  const product = p.product;
  const stars = p.stars ?? {};
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
          const state = i < idx ? "done" : i === idx ? "active" : "todo";
          return (
            <li key={s.key} className="flex flex-col items-center gap-2 text-center" aria-current={state === "active" ? "step" : undefined}>
              <span className={cn("flex size-10 items-center justify-center rounded-full border-2 text-caption font-bold",
                state === "done" && "border-primary bg-primary text-primary-fg",
                state === "active" && "border-primary text-primary",
                state === "todo" && "border-border text-muted")}>
                {state === "done" ? <Check aria-hidden className="size-5" /> : state === "active" ? <Loader2 aria-hidden className="size-5 animate-spin" /> : i + 1}
              </span>
              <span className={cn("text-caption font-medium", state === "todo" ? "text-muted" : "text-text")}>{s.label}</span>
              <span className="sr-only">{state === "done" ? "완료" : state === "active" ? "진행 중" : "대기"}</span>
            </li>
          );
        })}
      </ol>

      <Card className="space-y-6 p-6 md:p-8">
        <div aria-live="polite" aria-atomic="true" className="space-y-1">
          <p className="text-h3">{p.message ?? (view.status === "queued" ? "대기열에서 순서를 기다리고 있어요" : "분석하고 있어요")}</p>
          <p className="text-caption text-muted">
            {view.status === "queued" && p.queue_position ? `대기 순번 ${p.queue_position}번 · ` : ""}
            {view.status === "collecting" || view.status === "queued" ? `예상 남은 시간 ${fmtDuration(p.eta_seconds)}` : "곧 결과가 나와요"}
            {p.from_cache ? " · 저장된 리뷰 표본을 사용해요" : ""}
          </p>
        </div>

        <div>
          <p className="mb-3 text-caption font-semibold text-muted">별점별 수집 현황 (별점마다 최신순 최대 100개)</p>
          <ul className="space-y-3">
            {STARS.map((k: StarKey) => {
              const s = stars[k];
              const target = s?.target ?? 0;
              const collected = s?.collected ?? 0;
              const pct = target ? Math.min(100, Math.round((collected / target) * 100)) : s?.status === "skipped" ? 100 : 0;
              return (
                <li key={k} className="grid grid-cols-[3rem_1fr_6.5rem] items-center gap-3">
                  <span className="text-caption font-semibold num">{k}점</span>
                  <span className="h-2.5 overflow-hidden rounded-full bg-subtle" role="progressbar" aria-label={`${k}점 리뷰 수집`} aria-valuemin={0} aria-valuemax={target || 100} aria-valuenow={target ? collected : pct}>
                    <span className="block h-full rounded-full bg-primary transition-all duration-200" style={{ width: `${pct}%` }} />
                  </span>
                  <span className="text-right text-caption text-muted num">
                    {s?.status === "skipped" ? "리뷰 없음" : s ? `${fmtCount(collected)} / ${fmtCount(target)}` : "대기"}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>

        {view.status === "detecting" && p.detect_total ? (
          <p className="text-caption text-muted num">판별한 리뷰 {fmtCount(p.detected ?? 0)} / {fmtCount(p.detect_total)}</p>
        ) : null}
      </Card>
      <p className="text-center text-caption text-muted">이 창을 닫아도 분석은 계속돼요. 같은 주소로 다시 들어오면 결과를 볼 수 있어요.</p>
    </div>
  );
}
