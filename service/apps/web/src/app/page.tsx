import { ArrowRight, BarChart3, ShieldCheck, Sigma } from "lucide-react";
import Link from "next/link";
import { AnalyzeInput } from "@/components/features/analyze-input";
import { CollectedProducts } from "@/components/features/collected-products";
import { HowSteps } from "@/components/features/how-steps";
import { RatingCompareCard } from "@/components/features/report/rating-compare-card";
import { Accordion } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { DEMO_EXAMPLES } from "@/demo/examples";
import { FAQ } from "@/lib/faq";
import { site } from "@/lib/site";

const TRUST = [
  { icon: BarChart3, title: "숫자마다 근거를 보여드려요", body: "표본 수, 수집 시각, 95% 신뢰구간을 결과와 함께 표시해요." },
  { icon: ShieldCheck, title: "애매하면 판단을 미뤄요", body: "확신이 낮은 리뷰는 ‘판단 보류’로 따로 빼서 실제 구매자를 함부로 AI로 판정하지 않아요." },
  { icon: Sigma, title: "전체 별점 분포에 맞춰 계산해요", body: "표본 평균이 아니라 상품 전체 별점 분포에 사람 비율을 반영해 계산해요." },
];

export default function HomePage() {
  const example = DEMO_EXAMPLES[0];
  return (
    <>
      <section className="border-b border-border bg-subtle">
        <div className="container-page grid gap-12 py-16 md:py-24 lg:grid-cols-[1.1fr_1fr] lg:items-center">
          <div>
            <h1 className="text-h1 md:text-display">{site.tagline}</h1>
            <p className="mt-5 max-w-xl text-body text-muted">{site.description}</p>
          </div>
          <div className="rounded-xl border border-border bg-surface p-5 shadow-card md:p-8">
            <AnalyzeInput />
          </div>
        </div>
      </section>

      <div className="container-page pt-12 md:pt-16">
        <CollectedProducts limit={4} title="최근 수집한 상품" />
      </div>

      <section className="container-page section" aria-labelledby="how">
        <h2 id="how" className="text-h2">어떻게 작동하나요?</h2>
        <p className="mt-2 text-muted">상품 하나를 분석하는 데 몇 분이면 충분해요.</p>
        <div className="mt-10">
          <HowSteps />
        </div>
        <Link href="/how-it-works" className="mt-6 inline-flex items-center gap-1 font-semibold text-primary hover:underline">
          작동 원리 자세히 보기<ArrowRight aria-hidden className="size-4" />
        </Link>
      </section>

      {example && (
        <section className="border-y border-border bg-subtle" aria-labelledby="preview">
          <div className="container-page section">
            <div className="flex flex-wrap items-center gap-3">
              <h2 id="preview" className="text-h2">결과는 이렇게 보여드려요</h2>
              <Badge tone="warning">예시 화면</Badge>
            </div>
            <p className="mt-2 text-muted">{example.result.product.name} · 가상의 예시 데이터로 만든 화면이에요.</p>
            <div className="mt-10">
              <RatingCompareCard result={example.result} animate={false} />
            </div>
          </div>
        </section>
      )}

      <section className="container-page section" aria-labelledby="trust">
        <h2 id="trust" className="text-h2">믿고 볼 수 있도록</h2>
        <ul className="mt-10 grid gap-6 md:grid-cols-3">
          {TRUST.map((t) => (
            <li key={t.title}>
              <t.icon aria-hidden className="size-7 text-primary" />
              <h3 className="mt-4 text-h3">{t.title}</h3>
              <p className="mt-2 text-muted">{t.body}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="container-page pb-16 md:pb-24" aria-labelledby="faq">
        <h2 id="faq" className="text-h2">자주 묻는 질문</h2>
        <div className="mt-8">
          <Accordion items={FAQ.slice(0, 3).map((f) => ({ id: f.id, title: f.q, body: <p>{f.a}</p> }))} />
        </div>
        <Link href="/faq" className="mt-6 inline-flex items-center gap-1 font-semibold text-primary hover:underline">
          질문 모두 보기<ArrowRight aria-hidden className="size-4" />
        </Link>
      </section>

      <section className="container-page" aria-labelledby="cta">
        <div className="flex flex-col items-start gap-6 rounded-xl bg-primary px-6 py-12 text-primary-fg md:flex-row md:items-center md:justify-between md:px-12">
          <div>
            <h2 id="cta" className="text-h2">지금 보고 있는 상품, 별점이 진짜일까요?</h2>
            <p className="mt-2 text-primary-fg/80">링크 하나만 붙여 넣으면 돼요.</p>
          </div>
          <ButtonLink href="/analyze" size="lg" variant="secondary" className="border-transparent">
            분석 시작하기
          </ButtonLink>
        </div>
      </section>
    </>
  );
}
