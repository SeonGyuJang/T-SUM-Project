import type { Metadata } from "next";
import { ReviewChecker } from "@/components/features/review-checker";
import { ButtonLink } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "리뷰 직접 확인",
  description: "리뷰 글을 붙여 넣으면 AI가 쓴 리뷰인지 사람이 쓴 리뷰인지 바로 확인할 수 있어요.",
};

export default function CheckPage() {
  return (
    <div className="container-page section">
      <div className="mx-auto max-w-prose">
        <h1 className="text-h1">이 리뷰, 사람이 썼을까요?</h1>
        <p className="mt-3 text-muted">
          리뷰 글을 붙여 넣으면 AI가 썼을 확률을 바로 알려 드려요. 상품 전체 리뷰를 모아 별점을 다시 계산하고 싶다면 상품 분석을 이용하세요.
        </p>
        <div className="mt-10">
          <ReviewChecker />
        </div>
        <div className="mt-16 rounded-xl border border-border p-5">
          <p className="font-semibold">상품 리뷰 전체를 확인하고 싶나요?</p>
          <p className="mt-1 text-caption text-muted">쿠팡 상품 링크를 넣으면 리뷰를 모아 AI 추정 리뷰를 뺀 별점을 계산해 드려요.</p>
          <ButtonLink href="/analyze" variant="secondary" size="sm" className="mt-4">
            상품 분석하기
          </ButtonLink>
        </div>
      </div>
    </div>
  );
}
