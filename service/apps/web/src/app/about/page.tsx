import type { Metadata } from "next";
import { ButtonLink } from "@/components/ui/button";
import { site } from "@/lib/site";

export const metadata: Metadata = { title: "소개", description: `${site.name}을 만든 이유` };

// TODO(owner): Q7 팀/제작자 소개 노출 여부 — 기본값(노출 안 함)에 따라 프로젝트 배경만 싣는다.
export default function AboutPage() {
  return (
    <article className="container-page section">
      <div className="prose-ko mx-auto max-w-prose">
        <h1 className="text-h1">{site.name}을 만든 이유</h1>
        <p className="mt-6">
          생성형 AI로 만든 상품 리뷰가 늘면서, 별점과 리뷰가 실제 구매 경험을 그대로 보여주지 못하는 경우가 생기고 있어요.
          연구에 따르면 사람은 AI가 쓴 상품 리뷰를 거의 구분하지 못해요(정답률 약 50%).
        </p>
        <p>
          {site.name}은 AI 작성으로 추정되는 리뷰를 걸러낸 뒤의 별점을 보여드려서, 구매를 고민할 때 참고할 수 있는 한 가지 기준을 더하려고 해요.
          결과는 확률적 추정이라는 점을 늘 함께 알려드려요.
        </p>
        <h2>원칙</h2>
        <ul>
          <li>‘가짜 리뷰’라고 단정하지 않고 ‘AI 작성 추정’이라고 말해요.</li>
          <li>모든 숫자에 표본 수와 수집 시각 같은 근거를 붙여요.</li>
          <li>공개된 정보만 다루고, 작성자를 알아볼 수 있는 정보는 저장하지 않아요.</li>
        </ul>
      </div>
      <div className="mx-auto mt-10 max-w-prose"><ButtonLink href="/analyze">상품 분석하기</ButtonLink></div>
    </article>
  );
}
