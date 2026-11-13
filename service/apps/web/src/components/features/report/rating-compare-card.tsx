"use client";

import { ArrowDown, ArrowRight, ArrowUp, Minus } from "lucide-react";
import { Card } from "@/components/ui/card";
import type { AnalysisResult } from "@/lib/api/schema";
import { cn } from "@/lib/cn";
import { diffSentence, fmtCount, fmtDiff, fmtPct, fmtStar } from "@/lib/format";
import { useCountUp } from "@/lib/use-count-up";

export function RatingCompareCard({ result, animate = true }: { result: AnalysisResult; animate?: boolean }) {
  const r = result.ratings;
  const counted = useCountUp(animate ? r.avg_human : null);
  const shownHuman = animate ? counted : r.avg_human;
  const diff = r.diff;
  const rounded = diff == null ? null : Math.round(diff * 100) / 100;
  const DirIcon = rounded == null || rounded === 0 ? Minus : rounded < 0 ? ArrowDown : ArrowUp;
  const total = result.platform_stats.total_reviews;
  const sampled = Object.values(result.per_star).reduce((a, s) => a + s.collected, 0);

  return (
    <Card className="print-break overflow-hidden">
      <div className="grid gap-8 p-6 md:grid-cols-[1fr_auto_1fr] md:items-center md:p-10">
        <div>
          <p className="text-caption font-semibold text-muted md:text-body">전체 평균</p>
          <p className="mt-1 text-display text-text num" aria-label={`전체 평균 별점 ${fmtStar(r.avg_all)}점`}>
            <span aria-hidden className="text-star">★</span>{fmtStar(r.avg_all)}
          </p>
          <p className="text-caption text-muted num">리뷰 {fmtCount(total)}개 별점 분포 기준</p>
        </div>
        <ArrowRight aria-hidden className="hidden size-8 text-muted md:block" />
        <div>
          <p className="text-caption font-semibold text-primary md:text-body">사람 리뷰 기준</p>
          <p className="mt-1 text-display text-primary num" aria-label={`사람 리뷰 기준 별점 ${fmtStar(r.avg_human)}점`}>
            <span aria-hidden className="text-star">★</span>{shownHuman == null ? "–" : fmtStar(shownHuman)}
          </p>
          <p className="text-caption text-muted num">
            {r.avg_human_ci95 ? `95% 신뢰구간 ★${fmtStar(r.avg_human_ci95[0])} ~ ★${fmtStar(r.avg_human_ci95[1])}` : "신뢰구간 계산 불가"}
          </p>
        </div>
      </div>
      <div className="grid gap-4 border-t border-border bg-subtle px-6 py-5 md:grid-cols-[1fr_auto] md:items-center md:px-10">
        <p className="flex flex-wrap items-center gap-3 text-h3">
          <span className={cn("inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-3 py-1 text-body font-bold num",
            rounded == null || rounded === 0 ? "bg-surface text-muted" : rounded < 0 ? "bg-ai-soft text-ai" : "bg-human-soft text-human")}>
            <DirIcon aria-hidden className="size-4" />
            {fmtDiff(diff)}
          </span>
          <span>{diffSentence(diff)}</span>
        </p>
        <dl className="flex gap-6 text-caption">
          <div>
            <dt className="text-muted">추정 AI 리뷰 비중</dt>
            <dd className="text-h3 num">{fmtPct(r.ai_share)}</dd>
          </div>
          <div>
            <dt className="text-muted">분석한 리뷰</dt>
            <dd className="text-h3 num">{fmtCount(sampled)}개</dd>
          </div>
        </dl>
      </div>
      <p className="border-t border-border px-6 py-3 text-caption text-muted md:px-10">
        별점별 최신순 최대 {result.sampling.per_star_limit}개 표본에서 추정한 값이에요. 확률적 추정이라 오차가 있을 수 있어요.
      </p>
    </Card>
  );
}
