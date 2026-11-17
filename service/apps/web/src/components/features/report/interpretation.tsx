import { Accordion } from "@/components/ui/accordion";
import type { AnalysisResult } from "@/lib/api/schema";
import { fmtCount, fmtDateTime } from "@/lib/format";
import { DISCLAIMER } from "@/lib/site";

export function Interpretation({ result }: { result: AnalysisResult }) {
  const s = result.sampling;
  const sampled = Object.values(result.per_star).reduce((a, x) => a + x.collected, 0);
  const uncertain = Object.values(result.per_star).reduce((a, x) => a + x.uncertain, 0);
  const detected = result.detection.available;
  return (
    <div className="space-y-4">
      <p className="rounded-xl border border-border bg-subtle p-5 text-caption text-muted md:text-body">{DISCLAIMER}</p>
      <Accordion
        items={[
          ...(detected ? [] : [{
            id: "no-model",
            title: "AI 판별은 언제 되나요?",
            body: (
              <p>
                AI 작성 판별 모델이 아직 연결되지 않았어요. 지금은 쿠팡 별점 분포와 수집한 리뷰 원문만 보여드려요.
                모델이 연결되면 같은 리뷰로 사람 리뷰 기준 별점과 AI 리뷰 비중을 계산해요.
              </p>
            ),
          }]),
          ...(!detected ? [] : [{
            id: "uncertain",
            title: "‘판단 보류’는 무슨 뜻인가요?",
            body: (
              <p>
                너무 짧거나 모델이 확신하지 못한 리뷰예요. 이번 분석에서는 {fmtCount(sampled)}개 중 {fmtCount(uncertain)}개가 판단 보류였어요.
                판단 보류 리뷰는 판정된 리뷰와 사람 비율이 같다고 가정하고 계산에서 뺐어요.
              </p>
            ),
          }]),
          {
            id: "sampling",
            title: "표본은 어떻게 모았나요?",
            body: (
              <ul className="list-disc space-y-1 pl-5">
                <li>별점마다 {s.sort === "latest" ? "최신순" : "쿠팡 기본 정렬(베스트순)"}으로 최대 {s.per_star_limit}개씩 모았어요. 리뷰가 그보다 적으면 전부 모았어요.</li>
                {detected && <li>별점별 사람 비율을 표본에서 구한 뒤, 상품 전체 별점 분포(리뷰 {fmtCount(result.platform_stats.total_reviews)}개)에 반영했어요.</li>}
                {detected && <li>신뢰구간은 별점별 표본을 1,000번 다시 뽑아(부트스트랩) 계산했어요.</li>}
                <li>수집 시각 {fmtDateTime(s.collected_at)}{s.pages_loaded ? ` · 페이지 ${fmtCount(s.pages_loaded)}개 확인` : ""}</li>
              </ul>
            ),
          },
          {
            id: "assumptions",
            title: "계산에 쓴 가정과 참고 사항",
            body: (
              <ul className="list-disc space-y-1 pl-5">
                {result.assumptions.map((a) => <li key={a}>{a}</li>)}
                {result.flags.sponsored_count + result.flags.cash_event_count > 0 && (
                  <li>체험단·리뷰 이벤트 고지가 있는 리뷰 {fmtCount(result.flags.sponsored_count + result.flags.cash_event_count)}개는 고지 문구를 빼고 판별했어요.</li>
                )}
                {result.flags.near_duplicate_groups > 0 && <li>거의 같은 내용의 리뷰 묶음 {result.flags.near_duplicate_groups}개를 찾았어요(Top 5에는 묶음당 1개만).</li>}
                <li>체험단·대가성 리뷰처럼 사람이 쓴 광고성 리뷰는 이 분석으로 걸러지지 않아요.</li>
              </ul>
            ),
          },
          {
            id: "model",
            title: "판별 모델 정보",
            body: (
              <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-caption">
                <dt>모델 버전</dt>
                <dd className="font-mono">{detected ? result.model.version : "연결 전"}</dd>
                {result.model.T_AI != null && (<><dt>판정 기준</dt><dd className="num">AI 추정 ≥ {result.model.T_AI} · 사람 ≤ {result.model.T_HUMAN}</dd></>)}
                <dt>수집기</dt>
                <dd className="font-mono">{s.selectors_version ?? "–"}</dd>
              </dl>
            ),
          },
        ]}
      />
    </div>
  );
}
