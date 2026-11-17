"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Database } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { fmtCount, fmtDateTime, fmtStar } from "@/lib/format";
import { useStartAnalysis } from "@/lib/use-start-analysis";
import { ProductThumb } from "./product-thumb";

/**
 * 수집을 마친 상품 목록 (GET /api/products).
 * 수집기(coupang_reviews.py)를 직접 실행해 output/products 에 모은 상품도 여기에 바로 나온다.
 */
export function CollectedProducts({ limit = 6, title = "수집한 상품" }: { limit?: number; title?: string }) {
  const q = useQuery({ queryKey: ["products"], queryFn: () => api.listProducts(), staleTime: 10_000 });
  const { state, error, start } = useStartAnalysis();
  const items = (q.data ?? []).slice(0, limit);
  if (q.isError || (q.data && q.data.length === 0)) return null;

  return (
    <section aria-labelledby="collected" className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Database aria-hidden className="size-5 text-primary" />
        <h2 id="collected" className="text-h3">{title}</h2>
        {q.data && <Badge tone="neutral">{fmtCount(q.data.length)}개</Badge>}
      </div>
      <p className="text-caption text-muted">이미 리뷰를 모아 둔 상품은 다시 수집하지 않고 바로 결과를 볼 수 있어요.</p>
      {q.isPending ? (
        <div className="grid gap-4 md:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-28" />)}</div>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {items.map((p) => (
            <li key={p.product_id}>
              <Card className="flex h-full gap-4 p-4">
                <ProductThumb src={p.image_url} alt={p.name ?? "상품 이미지"} size={72} />
                <div className="min-w-0 flex-1 space-y-1.5">
                  <p className="line-clamp-2 font-semibold">{p.name ?? `상품 ${p.product_id}`}</p>
                  <p className="text-caption text-muted num">
                    {p.avg_all != null && <><span aria-hidden className="text-star">★</span>{fmtStar(p.avg_all)} · </>}
                    리뷰 {fmtCount(p.total_reviews)}개 중 {fmtCount(p.collected_reviews)}개 수집
                    {!p.complete && " · 일부"}
                  </p>
                  <p className="text-caption text-muted">수집 {fmtDateTime(p.collected_at)}</p>
                  <div className="pt-1">
                    {p.analysis_id ? (
                      <ButtonLink href={`/analyses/${p.analysis_id}`} size="sm" variant="secondary">
                        결과 보기<ArrowRight aria-hidden className="size-4" />
                      </ButtonLink>
                    ) : (
                      <Button size="sm" variant="secondary" disabled={state.busy}
                        onClick={() => void start(p.product_id, { type: "collected", url: p.url ?? undefined })}>
                        결과 보기<ArrowRight aria-hidden className="size-4" />
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <div aria-live="polite">{error && <p role="alert" className="font-medium text-danger">{error}</p>}</div>
    </section>
  );
}
