"use client";

import { useQuery } from "@tanstack/react-query";
import { Camera, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import type { AnalysisResult, ReviewItem } from "@/lib/api/schema";
import { STARS } from "@/lib/api/schema";
import { cn } from "@/lib/cn";
import { fmtCount, fmtDate, fmtPct } from "@/lib/format";

const PAGE = 10;
const FOLD = 220;
const LABEL: Record<string, { text: string; tone: "human" | "ai" | "uncertain" }> = {
  human: { text: "사람", tone: "human" },
  ai: { text: "AI 추정", tone: "ai" },
  uncertain: { text: "판단 보류", tone: "uncertain" },
};

function ReviewRow({ r }: { r: ReviewItem }) {
  const [open, setOpen] = useState(false);
  const long = r.content.length > FOLD;
  const text = !long || open ? r.content : r.content.slice(0, FOLD).trimEnd() + "…";
  const label = r.label ? LABEL[r.label] : undefined;
  return (
    <li className="rounded-xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-caption font-semibold num"><span aria-hidden className="text-star">★</span>{r.star}</span>
        {label && <Badge tone={label.tone}>{label.text}{r.p_ai != null ? ` · AI ${fmtPct(r.p_ai, 0)}` : ""}</Badge>}
        {r.has_photo && <Badge tone="neutral"><Camera aria-hidden className="size-3.5" />사진 포함</Badge>}
        {r.is_sponsored && <Badge tone="warning">체험단·이벤트 고지</Badge>}
        <span className="ml-auto text-caption text-muted num">{fmtDate(r.created_at)}</span>
      </div>
      {r.option_name && <p className="mt-2 text-caption text-muted">구매 옵션: {r.option_name}</p>}
      {r.title && <p className="mt-2 font-semibold">{r.title}</p>}
      {r.content ? (
        <p className="mt-2 whitespace-pre-line text-body text-text">{text}</p>
      ) : (
        <p className="mt-2 text-caption text-muted">(별점만 남긴 리뷰예요)</p>
      )}
      {long && (
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="mt-2 text-caption font-semibold text-primary hover:underline">
          {open ? "접기" : "더보기"}
        </button>
      )}
    </li>
  );
}

/** 수집한 리뷰 원문을 별점별로 넘겨 보는 목록 (GET /api/products/{id}/reviews) */
export function ReviewBrowser({ result }: { result: AnalysisResult }) {
  const pid = result.product.product_id;
  const firstStar = STARS.find((k) => result.per_star[k].collected > 0) ?? "5";
  const [star, setStar] = useState<string>(firstStar);
  const [page, setPage] = useState(0);
  const modelVersion = result.detection.available ? result.model.version : null;
  const q = useQuery({
    queryKey: ["reviews", pid, star, page, modelVersion],
    queryFn: () => api.getReviews(pid, { star: star === "all" ? null : Number(star), offset: page * PAGE, limit: PAGE, modelVersion }),
    placeholderData: (prev) => prev,
  });
  const total = q.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const tabs = ["all", ...STARS] as const;

  return (
    <div className="space-y-5">
      <div role="group" aria-label="수집한 리뷰 별점 필터" className="flex flex-wrap gap-2">
        {tabs.map((k) => {
          const n = k === "all" ? Object.values(result.per_star).reduce((a, s) => a + s.collected, 0) : result.per_star[k].collected;
          const active = star === k;
          return (
            <button
              key={k}
              type="button"
              aria-pressed={active}
              onClick={() => { setStar(k); setPage(0); }}
              className={cn("rounded-full border px-4 py-1.5 text-caption font-semibold num transition-colors",
                active ? "border-primary bg-primary text-primary-fg" : "border-border bg-surface text-text hover:bg-subtle")}
            >
              {k === "all" ? "전체" : <><span aria-hidden className={active ? "" : "text-star"}>★</span>{k}점</>} {fmtCount(n)}
            </button>
          );
        })}
      </div>

      {q.isPending && <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />)}</div>}
      {q.isError && (
        <p role="alert" className="rounded-xl border border-dashed border-border-strong px-5 py-8 text-center text-muted">
          {q.error instanceof ApiError ? q.error.message : "리뷰를 불러오지 못했어요."}
        </p>
      )}
      {q.data && q.data.items.length === 0 && (
        <p className="rounded-xl border border-dashed border-border-strong px-5 py-8 text-center text-muted">이 별점에서 수집한 리뷰가 없어요.</p>
      )}
      {q.data && q.data.items.length > 0 && (
        <ul className={cn("grid gap-4 lg:grid-cols-2", q.isFetching && "opacity-60")}>{q.data.items.map((r) => <ReviewRow key={r.review_id} r={r} />)}</ul>
      )}

      {total > PAGE && (
        <nav aria-label="리뷰 페이지" className="flex items-center justify-center gap-3">
          <Button variant="secondary" size="sm" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
            <ChevronLeft aria-hidden className="size-4" />이전
          </Button>
          <span className="text-caption text-muted num">{page + 1} / {pages} · {fmtCount(total)}개</span>
          <Button variant="secondary" size="sm" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
            다음<ChevronRight aria-hidden className="size-4" />
          </Button>
        </nav>
      )}
    </div>
  );
}
