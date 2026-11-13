import { Calculator, ListChecks, ScanSearch } from "lucide-react";

const STEPS = [
  { icon: ListChecks, title: "리뷰 모으기", body: "별점마다 최신 리뷰를 최대 100개씩 모아요. 상품 전체 별점 분포도 함께 확인해요." },
  { icon: ScanSearch, title: "AI 작성 판별", body: "리뷰마다 AI가 썼을 확률을 계산하고 사람 · AI 추정 · 판단 보류로 나눠요." },
  { icon: Calculator, title: "별점 다시 계산", body: "별점별 사람 비율을 전체 분포에 반영해 사람 리뷰 기준 별점을 구해요." },
];

export function HowSteps() {
  return (
    <ol className="grid gap-6 md:grid-cols-3">
      {STEPS.map((s, i) => (
        <li key={s.title} className="rounded-xl border border-border bg-surface p-6">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-full bg-primary-soft text-primary">
              <s.icon aria-hidden className="size-5" />
            </span>
            <span className="text-caption font-semibold text-muted">STEP {i + 1}</span>
          </div>
          <h3 className="mt-4 text-h3">{s.title}</h3>
          <p className="mt-2 text-muted">{s.body}</p>
        </li>
      ))}
    </ol>
  );
}
