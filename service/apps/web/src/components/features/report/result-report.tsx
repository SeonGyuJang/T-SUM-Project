import { ExternalLink, MessageSquareOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import type { AnalysisResult, ResultWarning } from "@/lib/api/schema";
import { fmtDateTime } from "@/lib/format";
import { ProductThumb } from "../product-thumb";
import { EmptyState } from "../state-views";
import { Interpretation } from "./interpretation";
import { RatingCompareCard } from "./rating-compare-card";
import { CollectionSummaryCard } from "./collection-summary-card";
import { RecollectButton } from "./recollect-button";
import { ReviewBrowser } from "./review-browser";
import { ShareActions } from "./share-actions";
import { StarDistribution } from "./star-distribution";
import { StarBreakdownChart } from "./star-breakdown-chart";
import { TopReviews } from "./top-reviews";

/** 결과 화면 경고 중 화면 상단에 크게 보여 줄 것 */
const PROMINENT = new Set(["dummy_detector", "placeholder", "no_human_reviews", "no_judged_reviews", "displayed_avg_mismatch", "collect_partial"]);
const TITLES: Record<string, string> = { placeholder: "샘플 데이터", dummy_detector: "개발용 결과", collect_partial: "일부만 수집했어요" };
const HIDDEN = new Set(["top_insufficient", "no_reviews"]);

function WarningList({ warnings }: { warnings: ResultWarning[] }) {
  const prominent = warnings.filter((w) => PROMINENT.has(w.code));
  const detection = warnings.find((w) => w.code === "detection_unavailable");
  const sample = warnings.filter((w) => w.code === "insufficient_sample" || w.code === "star_ratio_substituted");
  const rest = warnings.filter((w) => !PROMINENT.has(w.code) && !HIDDEN.has(w.code) && !sample.includes(w) && w.code !== "detection_unavailable");
  if (!prominent.length && !sample.length && !rest.length && !detection) return null;
  return (
    <div className="space-y-3">
      {detection && <Notice tone="info" role="status" title="AI 판별은 준비 중이에요">{detection.message}</Notice>}
      {prominent.map((w) => (
        <Notice key={w.code} tone="warning" role="status" title={TITLES[w.code] ?? "확인해 주세요"}>
          {w.message}
        </Notice>
      ))}
      {sample.length > 0 && (
        <Notice tone="warning" title="표본이 부족한 별점이 있어요">
          <ul className="list-disc space-y-0.5 pl-5">{sample.map((w) => <li key={`${w.code}-${w.star}`}>{w.message}</li>)}</ul>
        </Notice>
      )}
      {rest.map((w) => (
        <Notice key={`${w.code}-${w.star ?? ""}`} tone="info">{w.message}</Notice>
      ))}
    </div>
  );
}

export function ResultReport({ result, cached, demo }: { result: AnalysisResult; cached: boolean; demo?: boolean }) {
  const p = result.product;
  const noReviews = result.platform_stats.total_reviews === 0;
  const detected = result.detection.available;
  return (
    <div className="space-y-12 md:space-y-16">
      <header className="flex flex-col gap-5 sm:flex-row sm:items-center">
        <ProductThumb src={p.image_url} alt={p.name ?? "상품 이미지"} size={96} />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap gap-2">
            {(cached || demo) && <Badge tone="primary">저장된 분석 결과</Badge>}
            {!detected && <Badge tone="neutral">수집 결과 · AI 판별 제외</Badge>}
            {result.warnings.some((w) => w.code === "placeholder") && <Badge tone="warning">샘플 데이터</Badge>}
          </div>
          <h1 className="text-h2 md:text-h1">{p.name ?? `상품 ${p.product_id}`}</h1>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-muted">
            <span>수집 시각 {fmtDateTime(result.sampling.collected_at)}</span>
            {p.url && (
              <a href={p.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
                쿠팡에서 보기<ExternalLink aria-hidden className="size-4" /><span className="sr-only">(새 탭)</span>
              </a>
            )}
          </p>
        </div>
        {!demo && <RecollectButton productId={p.product_id} url={p.url} />}
      </header>

      <WarningList warnings={result.warnings} />

      {noReviews ? (
        <EmptyState icon={MessageSquareOff} title="아직 리뷰가 없는 상품이에요" body="리뷰가 쌓이면 다시 분석해 주세요." action={<ButtonLink href="/analyze">다른 상품 분석하기</ButtonLink>} />
      ) : (
        <>
          {detected ? (
            <>
            <section aria-labelledby="sec-compare">
              <h2 id="sec-compare" className="sr-only">별점 비교</h2>
              <RatingCompareCard result={result} />
            </section>

            <section aria-labelledby="sec-breakdown" className="print-break">
              <h2 id="sec-breakdown" className="text-h2">별점별 리뷰 구성</h2>
              <p className="mt-2 text-muted">별점마다 모은 표본에서 사람 리뷰, AI 추정 리뷰, 판단 보류 리뷰가 몇 개인지 보여드려요.</p>
              <Card className="mt-6 p-5 md:p-8">
                <StarBreakdownChart result={result} />
              </Card>
            </section>

            <section aria-labelledby="sec-top">
              <h2 id="sec-top" className="text-h2">사람이 쓴 것으로 보이는 리뷰 Top 5</h2>
              <p className="mt-2 text-muted">별점마다 사람이 썼을 확률이 가장 높은 리뷰예요. 비슷한 내용은 하나만 골랐어요.</p>
              <div className="mt-6">
                <TopReviews result={result} />
              </div>
            </section>
            </>
          ) : (
            <>
              <section aria-labelledby="sec-compare">
                <h2 id="sec-compare" className="sr-only">별점 요약</h2>
                <CollectionSummaryCard result={result} />
              </section>
              <section aria-labelledby="sec-breakdown" className="print-break">
                <h2 id="sec-breakdown" className="text-h2">별점 분포</h2>
                <p className="mt-2 text-muted">쿠팡에 등록된 전체 리뷰의 별점 분포와, 별점마다 모은 리뷰 수예요.</p>
                <Card className="mt-6 p-5 md:p-8">
                  <StarDistribution result={result} />
                </Card>
              </section>
            </>
          )}

          <section aria-labelledby="sec-reviews">
            <h2 id="sec-reviews" className="text-h2">수집한 리뷰</h2>
            <p className="mt-2 text-muted">
              {demo ? "예시 데이터에는 Top 5 리뷰만 들어 있어요." : "이번에 모은 리뷰 원문이에요. 별점을 골라 넘겨 볼 수 있어요."}
            </p>
            <div className="mt-6">
              <ReviewBrowser result={result} />
            </div>
          </section>
        </>
      )}

      <section aria-labelledby="sec-guide">
        <h2 id="sec-guide" className="text-h2">결과를 읽는 방법</h2>
        <div className="mt-6">
          <Interpretation result={result} />
        </div>
      </section>

      <ShareActions />
    </div>
  );
}
