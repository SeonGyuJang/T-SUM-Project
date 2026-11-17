"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { api, ApiError, type ResolveResult } from "@/lib/api";
import type { ResolveInput } from "@/lib/api/types";
import { saveResolve } from "@/lib/resolve-store";

export type FlowState = { busy: false } | { busy: true; label: string };

const BLOCKED_MSG = "지금은 쿠팡에서 정보를 가져올 수 없어요. 잠시 후 다시 시도하거나 저장된 결과를 확인해 주세요.";

/** 입력 → 상품 식별 → (자동 선택이면) 분석 시작 → 진행 화면 이동 */
export function useStartAnalysis() {
  const router = useRouter();
  const [state, setState] = useState<FlowState>({ busy: false });
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(
    async (productId: string, source?: Record<string, unknown>, opts?: { forceRefresh?: boolean }) => {
      setState({ busy: true, label: opts?.forceRefresh ? "리뷰를 다시 수집하도록 요청하고 있어요" : "분석을 준비하고 있어요" });
      setError(null);
      try {
        const res = await api.createAnalysis(productId, { source, forceRefresh: opts?.forceRefresh });
        router.push(`/analyses/${res.analysis_id}`);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "분석을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.");
        setState({ busy: false });
      }
    },
    [router],
  );

  const submit = useCallback(
    async (input: ResolveInput) => {
      setError(null);
      setState({ busy: true, label: "image" in input ? "이미지에서 상품명을 찾고 있어요" : "상품을 찾고 있어요" });
      let res: ResolveResult;
      try {
        res = await api.resolve(input);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "상품을 찾지 못했어요. 잠시 후 다시 시도해 주세요.");
        setState({ busy: false });
        return;
      }
      if (res.status === "blocked" && res.candidates.length === 0) {
        setError(res.message || BLOCKED_MSG);
        setState({ busy: false });
        return;
      }
      if (res.status === "not_found" || res.candidates.length === 0) {
        setError(res.message || "상품을 찾지 못했어요. 입력을 확인해 주세요.");
        setState({ busy: false });
        return;
      }
      if (res.status === "resolved" && res.candidates[0]) {
        const c = res.candidates[0];
        await start(c.product_id, { type: res.input_type, query: res.query ?? undefined, url: c.url ?? undefined });
        return;
      }
      saveResolve(res);
      router.push("/analyze/select");
    },
    [router, start],
  );

  return { state, error, submit, start, setError };
}
