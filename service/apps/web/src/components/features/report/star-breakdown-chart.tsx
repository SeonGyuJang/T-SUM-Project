"use client";

import { Bar, BarChart, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";
import type { AnalysisResult, StarKey } from "@/lib/api/schema";
import { STARS } from "@/lib/api/schema";
import { fmtCount, fmtPct } from "@/lib/format";

const SERIES = [
  { key: "human", label: "사람", fill: "url(#pat-human)" },
  { key: "ai", label: "AI 추정", fill: "url(#pat-ai)" },
  { key: "uncertain", label: "판단 보류", fill: "url(#pat-uncertain)" },
] as const;

/** 색만으로 구분하지 않도록 패턴을 함께 쓴다(사람: 단색, AI: 사선, 보류: 점). */
function ChartPatterns() {
  return (
    <svg aria-hidden width="0" height="0" className="absolute">
      <defs>
        <pattern id="pat-human" width="8" height="8" patternUnits="userSpaceOnUse">
          <rect width="8" height="8" fill="rgb(var(--human))" />
        </pattern>
        <pattern id="pat-ai" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="8" height="8" fill="rgb(var(--ai))" />
          <rect width="3" height="8" fill="rgb(255 255 255 / 0.35)" />
        </pattern>
        <pattern id="pat-uncertain" width="8" height="8" patternUnits="userSpaceOnUse">
          <rect width="8" height="8" fill="rgb(var(--uncertain) / 0.55)" />
          <circle cx="4" cy="4" r="1.4" fill="rgb(255 255 255 / 0.7)" />
        </pattern>
      </defs>
    </svg>
  );
}

function Swatch({ pattern }: { pattern: string }) {
  return (
    <svg aria-hidden width="14" height="14">
      <rect width="14" height="14" rx="3" fill={pattern} />
    </svg>
  );
}

export function StarBreakdownChart({ result }: { result: AnalysisResult }) {
  const data = STARS.map((k: StarKey) => {
    const s = result.per_star[k];
    return { star: `${k}점`, human: s.human, ai: s.ai, uncertain: s.uncertain, collected: s.collected, total: s.total, ratio: s.human_ratio };
  });
  return (
    <div className="space-y-4">
      <ChartPatterns />
      <ul className="flex flex-wrap gap-x-5 gap-y-2 text-caption" aria-label="범례">
        {SERIES.map((s) => (
          <li key={s.key} className="inline-flex items-center gap-2">
            <Swatch pattern={s.fill} />
            {s.label}
          </li>
        ))}
      </ul>
      <div className="grid grid-cols-[1fr_auto] gap-3">
        <div className="h-[300px] min-w-0" aria-hidden>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart accessibilityLayer={false} data={data} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 0 }} barCategoryGap={14}>
              <XAxis type="number" hide domain={[0, "dataMax"]} />
              <YAxis type="category" dataKey="star" width={44} tickLine={false} axisLine={false} tick={{ fill: "rgb(var(--text))", fontSize: 15, fontWeight: 600 }} />
              {SERIES.map((s, i) => (
                <Bar key={s.key} dataKey={s.key} stackId="a" fill={s.fill} isAnimationActive={false}
                  radius={i === 0 ? [6, 0, 0, 6] : i === SERIES.length - 1 ? [0, 6, 6, 0] : 0}>
                  <LabelList dataKey={s.key} position="center" fill="#fff" fontSize={13} fontWeight={700}
                    formatter={(v: unknown) => (typeof v === "number" && v >= 8 ? String(v) : "")} />
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
        <ul className="flex h-[300px] flex-col justify-around text-right text-caption text-muted num" aria-hidden>
          {data.map((d) => (
            <li key={d.star}>
              사람 {fmtPct(d.ratio, 0)}
              <span className="hidden sm:block">표본 {d.collected} / 전체 {fmtCount(d.total)}</span>
            </li>
          ))}
        </ul>
      </div>
      <details className="rounded-lg border border-border bg-surface">
        <summary className="cursor-pointer px-4 py-3 text-caption font-semibold">표로 보기</summary>
        <div className="overflow-x-auto px-4 pb-4">
          <table className="w-full min-w-[32rem] text-caption num">
            <caption className="sr-only">별점별 표본 구성: 수집 수, 사람, AI 추정, 판단 보류, 사람 비율, 전체 리뷰 수</caption>
            <thead>
              <tr className="border-b border-border text-left text-muted">
                <th scope="col" className="py-2">별점</th>
                <th scope="col">수집</th>
                <th scope="col">사람</th>
                <th scope="col">AI 추정</th>
                <th scope="col">판단 보류</th>
                <th scope="col">사람 비율</th>
                <th scope="col">전체 리뷰 수</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.star} className="border-b border-border last:border-0">
                  <th scope="row" className="py-2 text-left">{d.star}</th>
                  <td>{d.collected}</td>
                  <td>{d.human}</td>
                  <td>{d.ai}</td>
                  <td>{d.uncertain}</td>
                  <td>{fmtPct(d.ratio)}</td>
                  <td>{fmtCount(d.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
