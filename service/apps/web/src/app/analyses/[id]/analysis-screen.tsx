"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { BlockedState, ErrorState } from "@/components/features/state-views";
import { ProgressView } from "@/components/features/progress-view";
import { ResultReport } from "@/components/features/report/result-report";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, TERMINAL } from "@/lib/api";
import { site } from "@/lib/site";

const POLL_MS = 2500;

export function AnalysisScreen({ id }: { id: string }) {
  const q = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => api.getAnalysis(id),
    refetchInterval: (query) => {
      const d = query.state.data;
      return d && TERMINAL.includes(d.status) ? false : POLL_MS; // 완료·실패 시 폴링 중단
    },
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });
  const v = q.data;

  useEffect(() => {
    const name = v?.result?.product.name ?? v?.progress.product?.name;
    if (name) document.title = `${v?.status === "done" ? "분석 결과" : "분석 중"} · ${name} | ${site.name}`;
  }, [v]);

  return (
    <div className="container-page section">
      {q.isPending && <LoadingSkeleton />}
      {q.isError && (
        <div className="mx-auto max-w-2xl">
          <ErrorState error={{ code: q.error instanceof ApiError ? q.error.code : "error", message: q.error.message }} />
        </div>
      )}
      {v && v.status === "done" && v.result && <ResultReport result={v.result} cached={v.cached} demo={v.demo} />}
      {v && v.status === "blocked" && <div className="mx-auto max-w-2xl"><BlockedState error={v.error} /></div>}
      {v && v.status === "failed" && <div className="mx-auto max-w-2xl"><ErrorState error={v.error} productId={v.product_id} /></div>}
      {v && !TERMINAL.includes(v.status) && <ProgressView view={v} />}
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="분석 정보를 불러오는 중">
      <div className="flex items-center gap-4">
        <Skeleton className="size-24" />
        <div className="flex-1 space-y-3"><Skeleton className="h-5 w-32" /><Skeleton className="h-9 w-2/3" /></div>
      </div>
      <Skeleton className="h-64" />
      <Skeleton className="h-80" />
    </div>
  );
}
