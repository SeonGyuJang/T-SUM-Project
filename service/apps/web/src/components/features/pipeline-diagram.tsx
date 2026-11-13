/** 수집 → 탐지 → 재계산 흐름 다이어그램 (자체 제작 SVG, 텍스트는 HTML로 접근성 확보) */
const NODES = [
  { t: "상품 확인", d: "링크·상품명·이미지" },
  { t: "리뷰 수집", d: "별점별 최신 100개" },
  { t: "AI 작성 판별", d: "사람 · AI 추정 · 보류" },
  { t: "별점 재계산", d: "전체 분포에 반영" },
];

export function PipelineDiagram() {
  return (
    <figure className="rounded-xl border border-border bg-surface p-6 md:p-8">
      <ol className="grid gap-4 md:grid-cols-4 md:gap-0">
        {NODES.map((n, i) => (
          <li key={n.t} className="relative flex items-center gap-4 md:flex-col md:text-center">
            <span className="z-10 flex size-12 shrink-0 items-center justify-center rounded-full border-2 border-primary bg-surface text-h3 text-primary num">{i + 1}</span>
            {i < NODES.length - 1 && (
              <svg aria-hidden className="absolute left-6 top-12 h-4 w-px md:left-1/2 md:top-6 md:h-px md:w-full" preserveAspectRatio="none" viewBox="0 0 100 1">
                <line x1="0" y1="0.5" x2="100" y2="0.5" className="stroke-border-strong" strokeWidth="2" vectorEffect="non-scaling-stroke" />
              </svg>
            )}
            <div className="md:mt-3">
              <p className="font-semibold">{n.t}</p>
              <p className="text-caption text-muted">{n.d}</p>
            </div>
          </li>
        ))}
      </ol>
      <figcaption className="sr-only">상품 확인, 리뷰 수집, AI 작성 판별, 별점 재계산 순서로 진행돼요.</figcaption>
    </figure>
  );
}
