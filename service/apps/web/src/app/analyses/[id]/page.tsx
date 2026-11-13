import type { Metadata } from "next";
import { AnalysisScreen } from "./analysis-screen";

export const metadata: Metadata = { title: "분석 결과", description: "AI 작성 추정 리뷰를 제외한 사람 리뷰 기준 별점과 Top 5 리뷰", robots: { index: false } };

export default async function AnalysisPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AnalysisScreen id={id} />;
}
