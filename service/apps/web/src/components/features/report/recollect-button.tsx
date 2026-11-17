"use client";

import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useStartAnalysis } from "@/lib/use-start-analysis";

/** 저장된 파일·캐시를 쓰지 않고 수집기를 다시 실행한다(force_refresh). */
export function RecollectButton({ productId, url }: { productId: string; url?: string | null }) {
  const { state, error, start } = useStartAnalysis();
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Button
        variant="secondary"
        size="sm"
        disabled={state.busy}
        onClick={() => void start(productId, { type: "refresh", url: url ?? undefined }, { forceRefresh: true })}
      >
        <RefreshCw aria-hidden className={state.busy ? "size-4 animate-spin" : "size-4"} />
        최신 리뷰로 다시 수집
      </Button>
      {error && <span role="alert" className="text-caption text-danger">{error}</span>}
    </span>
  );
}
