import type { Metadata } from "next";
import { LegalDraftNote } from "@/components/features/legal-draft-note";
import { site } from "@/lib/site";

export const metadata: Metadata = { title: "이용약관", description: `${site.name} 이용약관` };

// Q10(2026-11-13): 실서비스 전환 시 검토 예정. 현재 에이전트 초안(법률 자문 아님). 확정 시 시행일·운영자 정보 기입.
export default function TermsPage() {
  return (
    <article className="container-page section">
      <div className="prose-ko mx-auto max-w-prose">
        <h1 className="text-h1">이용약관</h1>
        <div className="mt-8"><LegalDraftNote /></div>
        <h2>제1조 (목적)</h2>
        <p>이 약관은 {site.name}(이하 ‘서비스’)이 제공하는 상품 리뷰 분석 서비스의 이용 조건과 절차를 정해요.</p>
        <h2>제2조 (서비스 내용)</h2>
        <ul>
          <li>서비스는 이용자가 지정한 쿠팡 상품의 공개 리뷰를 표본으로 모아 AI 작성 가능성을 통계적으로 추정하고, 그 결과로 다시 계산한 별점을 보여줘요.</li>
          <li>서비스는 쿠팡과 관련이 없는 독립 서비스예요.</li>
        </ul>
        <h2>제3조 (결과의 성격)</h2>
        <ul>
          <li>분석 결과는 통계 모델의 추정치이며 오차가 있을 수 있어요. 서비스는 결과의 정확성이나 특정 목적 적합성을 보증하지 않아요.</li>
          <li>이용자는 분석 결과를 특정 개인이나 판매자를 비방·공격하는 근거로 써서는 안 돼요.</li>
        </ul>
        <h2>제4조 (이용자의 의무)</h2>
        <ul>
          <li>서비스를 자동화된 방법으로 대량 호출하거나, 서비스 운영을 방해하는 행위를 해서는 안 돼요.</li>
          <li>타인의 권리를 침해하는 이미지를 올려서는 안 돼요.</li>
        </ul>
        <h2>제5조 (서비스의 중단)</h2>
        <p>외부 사이트의 접근 제한, 화면 구조 변경, 점검 등으로 서비스의 전부 또는 일부가 일시적으로 중단될 수 있어요.</p>
        <h2>제6조 (약관의 변경)</h2>
        <p>약관을 바꾸면 시행 7일 전부터 이 페이지에 알려요.</p>
      </div>
    </article>
  );
}
