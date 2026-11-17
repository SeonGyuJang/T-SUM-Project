import type { AnalysisResult, StarKey } from "@/lib/api/schema";
import { STARS } from "@/lib/api/schema";
import { fmtCount, fmtPct } from "@/lib/format";

/** 별점 분포(쿠팡 전체)와 별점별 수집 표본. AI 판별 없이도 보여 줄 수 있는 구성. */
export function StarDistribution({ result }: { result: AnalysisResult }) {
  const total = STARS.reduce((a, k) => a + result.platform_stats.star_counts[k], 0);
  const max = Math.max(1, ...STARS.map((k) => result.platform_stats.star_counts[k]));
  return (
    <div className="space-y-5">
      <ul className="space-y-3">
        {STARS.map((k: StarKey) => {
          const n = result.platform_stats.star_counts[k];
          const share = total ? n / total : 0;
          const ps = result.per_star[k];
          return (
            <li key={k} className="grid grid-cols-[3rem_1fr_9rem] items-center gap-3 sm:grid-cols-[3rem_1fr_13rem]">
              <span className="text-caption font-semibold num"><span aria-hidden className="text-star">★</span>{k}점</span>
              <span className="h-4 overflow-hidden rounded-full bg-subtle" aria-hidden>
                <span className="block h-full rounded-full bg-primary" style={{ width: `${(n / max) * 100}%` }} />
              </span>
              <span className="text-right text-caption text-muted num">
                {fmtCount(n)}개 · {fmtPct(share, 0)}
                <span className="hidden sm:inline"> · 수집 {fmtCount(ps.collected)}</span>
              </span>
            </li>
          );
        })}
      </ul>
      <details className="rounded-lg border border-border bg-surface">
        <summary className="cursor-pointer px-4 py-3 text-caption font-semibold">표로 보기</summary>
        <div className="overflow-x-auto px-4 pb-4">
          <table className="w-full min-w-[32rem] text-caption num">
            <caption className="sr-only">별점별 전체 리뷰 수와 수집한 표본</caption>
            <thead>
              <tr className="border-b border-border text-left text-muted">
                <th scope="col" className="py-2">별점</th>
                <th scope="col">전체 리뷰 수</th>
                <th scope="col">비율</th>
                <th scope="col">수집</th>
                <th scope="col">평균 글자 수</th>
                <th scope="col">사진 포함</th>
              </tr>
            </thead>
            <tbody>
              {STARS.map((k) => {
                const st = result.review_stats?.[k];
                const n = result.platform_stats.star_counts[k];
                return (
                  <tr key={k} className="border-b border-border last:border-0">
                    <th scope="row" className="py-2 text-left">{k}점</th>
                    <td>{fmtCount(n)}</td>
                    <td>{fmtPct(total ? n / total : null)}</td>
                    <td>{fmtCount(result.per_star[k].collected)}</td>
                    <td>{st?.avg_chars != null ? fmtCount(Math.round(st.avg_chars)) : "–"}</td>
                    <td>{fmtCount(st?.photo_count ?? 0)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
