"use client";

import { SearchX } from "lucide-react";
import { useEffect, useState } from "react";
import { CandidateList } from "@/components/features/candidate-list";
import { EmptyState } from "@/components/features/state-views";
import { ButtonLink } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import type { ResolveResult } from "@/lib/api/schema";
import { loadResolve } from "@/lib/resolve-store";
import { useStartAnalysis } from "@/lib/use-start-analysis";

export function SelectView() {
  const [res, setRes] = useState<ResolveResult | null | undefined>(undefined);
  const { state, error, start } = useStartAnalysis();
  // sessionStorage는 브라우저에서만 읽을 수 있다
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setRes(loadResolve()), []);

  return (
    <div className="container-page section">
      <div className="mx-auto max-w-4xl">
        <h1 className="text-h1">이 중에 찾는 상품이 있나요?</h1>
        {res?.query && <p className="mt-3 text-muted">‘{res.query}’(으)로 찾은 상품이에요. 분석할 상품을 골라 주세요.</p>}
        {res?.input_type === "image" && !res.query && <p className="mt-3 text-muted">이미지와 비슷한 상품이에요. 분석할 상품을 골라 주세요.</p>}
        <div className="mt-10 space-y-6">
          {res === undefined && (
            <div className="grid gap-4 md:grid-cols-2" aria-busy="true" aria-label="후보를 불러오는 중">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}
            </div>
          )}
          {res === null && (
            <EmptyState icon={SearchX} title="선택할 후보가 없어요" body="검색한 지 오래되었거나 새 창에서 열었어요. 다시 검색해 주세요." action={<ButtonLink href="/analyze">다시 검색하기</ButtonLink>} />
          )}
          {res && res.message && <Notice tone="info">{res.message}</Notice>}
          {res && res.extracted && typeof res.extracted.product_name === "string" && (
            <Notice tone="info" title="이미지에서 읽은 상품명">{res.extracted.product_name}</Notice>
          )}
          {res && res.candidates.length > 0 && <CandidateList candidates={res.candidates} busy={state.busy} onSelect={(c) => void start(c.product_id, { type: res.input_type, query: res.query ?? undefined, url: c.url ?? undefined })} />}
          {res && res.candidates.length === 0 && (
            <EmptyState icon={SearchX} title="비슷한 상품을 찾지 못했어요" body="상품명을 조금 더 간단히 입력하거나 링크로 분석해 보세요." action={<ButtonLink href="/analyze">다시 검색하기</ButtonLink>} />
          )}
          <div aria-live="polite">{error && <p role="alert" className="font-medium text-danger">{error}</p>}</div>
          {res && res.candidates.length > 0 && (
            <p className="text-caption text-muted">
              찾는 상품이 없나요? <ButtonLink href="/analyze" variant="link" size="sm" className="h-auto">링크로 분석하기</ButtonLink>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
