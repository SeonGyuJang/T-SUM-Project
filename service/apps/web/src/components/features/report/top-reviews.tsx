"use client";

import { Camera } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { AnalysisResult, StarKey, TopReview } from "@/lib/api/schema";
import { STARS } from "@/lib/api/schema";
import { fmtDate, fmtPct } from "@/lib/format";

const FOLD = 180;

function ReviewCard({ r }: { r: TopReview }) {
  const [open, setOpen] = useState(false);
  const long = r.text.length > FOLD;
  const text = !long || open ? r.text : r.text.slice(0, FOLD).trimEnd() + "…";
  return (
    <li className="print-break rounded-xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="human">사람일 확률 {fmtPct(r.p_human, 0)}</Badge>
        {r.has_photo && (
          <Badge tone="neutral"><Camera aria-hidden className="size-3.5" />사진 포함</Badge>
        )}
        {r.reason_tags.map((t) => <Badge key={t} tone="neutral">{t}</Badge>)}
        <span className="ml-auto text-caption text-muted num">{fmtDate(r.created_at)}</span>
      </div>
      {r.title && <p className="mt-3 font-semibold">{r.title}</p>}
      <p className="mt-2 whitespace-pre-line text-body text-text">{text}</p>
      {long && (
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="mt-2 text-caption font-semibold text-primary hover:underline">
          {open ? "접기" : "더보기"}
        </button>
      )}
    </li>
  );
}

export function TopReviews({ result }: { result: AnalysisResult }) {
  const first = STARS.find((k) => result.top_human_reviews[k].length > 0) ?? "5";
  return (
    <Tabs defaultValue={first}>
      <TabsList aria-label="별점 선택" className="flex w-full justify-between sm:inline-flex sm:w-auto">
        {STARS.map((k: StarKey) => (
          <TabsTrigger key={k} value={k} className="flex-1 gap-0.5 px-2 sm:flex-none sm:px-4">
            <span aria-hidden className="text-star">★</span>{k}점
          </TabsTrigger>
        ))}
      </TabsList>
      {STARS.map((k: StarKey) => {
        const list = result.top_human_reviews[k];
        const ps = result.per_star[k];
        return (
          <TabsContent key={k} value={k} className="mt-6">
            {list.length === 0 ? (
              <p className="rounded-xl border border-dashed border-border-strong px-5 py-8 text-center text-muted">
                {ps.total === 0 ? `${k}점 리뷰가 없어요.` : `${k}점에서는 조건(사람 리뷰 판정, ${40}자 이상)에 맞는 리뷰를 찾지 못했어요.`}
              </p>
            ) : (
              <>
                <ul className="grid gap-4 lg:grid-cols-2">{list.map((r) => <ReviewCard key={r.review_id} r={r} />)}</ul>
                {list.length < 5 && (
                  <p className="mt-4 text-caption text-muted">조건에 맞는 사람 리뷰가 {list.length}개뿐이라 있는 만큼만 보여드려요.</p>
                )}
              </>
            )}
          </TabsContent>
        );
      })}
    </Tabs>
  );
}
