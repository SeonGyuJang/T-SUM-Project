import type { Metadata } from "next";
import Link from "next/link";
import { AnalyzeInput } from "@/components/features/analyze-input";
import { CollectedProducts } from "@/components/features/collected-products";

export const metadata: Metadata = {
  title: "분석 시작",
  description: "쿠팡 상품 링크, 상품명, 캡처 이미지 중 하나로 리뷰 분석을 시작하세요.",
};

const EXAMPLES = [
  { k: "링크", v: "https://www.coupang.com/vp/products/상품번호?itemId=…" },
  { k: "공유 링크", v: "https://link.coupang.com/a/…" },
  { k: "상품명", v: "브랜드 상품명 500ml 20개" },
  { k: "이미지", v: "쿠팡 상품 화면 캡처, 상품 포장 사진" },
];

export default function AnalyzePage() {
  return (
    <div className="container-page section">
      <div className="mx-auto max-w-prose">
        <h1 className="text-h1">어떤 상품을 분석할까요?</h1>
        <p className="mt-3 text-muted">링크, 상품명, 캡처 이미지 중 편한 방법으로 알려 주세요. 처음 보는 상품은 리뷰를 모으는 데 몇 분 걸려요. 진행 상황은 화면에서 실시간으로 볼 수 있어요.</p>
        <div className="mt-10">
          <AnalyzeInput autoFocus />
        </div>
        <p className="mt-4 text-caption text-muted">
          리뷰 글 하나만 확인하고 싶다면{" "}
          <Link href="/check" className="font-medium text-primary underline-offset-4 hover:underline">
            리뷰 직접 확인
          </Link>
          에서 붙여 넣어 보세요.
        </p>
        <div className="mt-16">
          <CollectedProducts limit={20} />
        </div>
        <section aria-labelledby="examples" className="mt-16">
          <h2 id="examples" className="text-h3">입력 예시</h2>
          <dl className="mt-4 divide-y divide-border rounded-xl border border-border">
            {EXAMPLES.map((e) => (
              <div key={e.k} className="grid gap-1 px-5 py-3 sm:grid-cols-[7rem_1fr]">
                <dt className="text-caption font-semibold">{e.k}</dt>
                <dd className="break-all text-caption text-muted">{e.v}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </div>
  );
}
