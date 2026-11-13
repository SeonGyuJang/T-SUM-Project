"use client";

import { ArrowRight, Loader2 } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import type { Candidate } from "@/lib/api/schema";
import { fmtCount, fmtPrice, fmtStar } from "@/lib/format";
import { ProductThumb } from "./product-thumb";

export function CandidateList({ candidates, onSelect, busy }: { candidates: Candidate[]; onSelect: (c: Candidate) => void; busy: boolean }) {
  const [picked, setPicked] = useState<string | null>(null);
  return (
    <ul className="grid gap-4 md:grid-cols-2" aria-label="상품 후보">
      {candidates.map((c) => {
        const score = c.match_score ?? null;
        const loading = busy && picked === c.product_id;
        return (
          <li key={`${c.product_id}-${c.item_id ?? ""}`}>
            <button
              type="button"
              disabled={busy}
              onClick={() => { setPicked(c.product_id); onSelect(c); }}
              className="group flex h-full w-full items-start gap-4 rounded-xl border border-border bg-surface p-4 text-left shadow-card transition-colors hover:border-primary disabled:opacity-60"
            >
              <ProductThumb src={c.image_url} alt={c.name ?? "상품 이미지"} size={88} />
              <span className="min-w-0 flex-1 space-y-2">
                <span className="flex flex-wrap gap-1.5">
                  {score != null && <Badge tone="primary">일치도 {Math.round(score * 100)}%</Badge>}
                  {c.is_ad && <Badge tone="warning">광고</Badge>}
                </span>
                <span className="line-clamp-2 block font-semibold text-text">{c.name ?? `상품 ${c.product_id}`}</span>
                <span className="block text-caption text-muted num">
                  {[fmtPrice(c.price), c.rating != null ? `★${fmtStar(c.rating)}` : "", c.review_count != null ? `리뷰 ${fmtCount(c.review_count)}개` : ""].filter(Boolean).join(" · ")}
                </span>
              </span>
              {loading ? <Loader2 aria-hidden className="mt-1 size-5 animate-spin text-primary" /> : <ArrowRight aria-hidden className="mt-1 size-5 text-muted group-hover:text-primary" />}
              <span className="sr-only">이 상품 분석하기</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
