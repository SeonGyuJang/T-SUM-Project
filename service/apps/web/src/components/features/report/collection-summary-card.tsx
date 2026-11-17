import { Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";
import type { AnalysisResult } from "@/lib/api/schema";
import { fmtCount, fmtStar } from "@/lib/format";

/** AI 판별 모델이 없을 때의 상단 요약: 전체 평균·리뷰 수·수집 표본. 사람 리뷰 기준 별점 자리는 '준비 중'으로 둔다. */
export function CollectionSummaryCard({ result }: { result: AnalysisResult }) {
  const r = result.ratings;
  const total = result.platform_stats.total_reviews;
  const sampled = Object.values(result.per_star).reduce((a, s) => a + s.collected, 0);
  const photos = Object.values(result.review_stats ?? {}).reduce((a, s) => a + (s.photo_count ?? 0), 0);
  return (
    <Card className="print-break overflow-hidden">
      <div className="grid gap-8 p-6 md:grid-cols-2 md:items-center md:p-10">
        <div>
          <p className="text-caption font-semibold text-muted md:text-body">전체 평균</p>
          <p className="mt-1 text-display text-text num" aria-label={`전체 평균 별점 ${fmtStar(r.avg_all)}점`}>
            <span aria-hidden className="text-star">★</span>{fmtStar(r.avg_all)}
          </p>
          <p className="text-caption text-muted num">리뷰 {fmtCount(total)}개 별점 분포 기준</p>
          {result.platform_stats.displayed_avg != null && (
            <p className="text-caption text-muted num">쿠팡 표시 평균 ★{result.platform_stats.displayed_avg.toFixed(1)}</p>
          )}
        </div>
        <div className="rounded-xl border border-dashed border-border-strong p-5">
          <p className="inline-flex items-center gap-1.5 text-caption font-semibold text-primary md:text-body">
            <Sparkles aria-hidden className="size-4" />사람 리뷰 기준 별점
          </p>
          <p className="mt-2 text-h3 text-muted">AI 판별 모델 준비 중</p>
          <p className="mt-1 text-caption text-muted">모델이 연결되면 수집해 둔 리뷰로 바로 다시 계산할 수 있어요.</p>
        </div>
      </div>
      <dl className="grid grid-cols-3 gap-4 border-t border-border bg-subtle px-6 py-5 text-caption md:px-10">
        <div>
          <dt className="text-muted">수집한 리뷰</dt>
          <dd className="text-h3 num">{fmtCount(sampled)}개</dd>
        </div>
        <div>
          <dt className="text-muted">사진 포함 리뷰</dt>
          <dd className="text-h3 num">{fmtCount(photos)}개</dd>
        </div>
        <div>
          <dt className="text-muted">체험단·이벤트 고지</dt>
          <dd className="text-h3 num">{fmtCount(result.flags.sponsored_count + result.flags.cash_event_count)}개</dd>
        </div>
      </dl>
      <p className="border-t border-border px-6 py-3 text-caption text-muted md:px-10">
        별점마다 최대 {result.sampling.per_star_limit}개씩 모았어요. 리뷰가 그보다 적으면 전부 모았어요.
      </p>
    </Card>
  );
}
