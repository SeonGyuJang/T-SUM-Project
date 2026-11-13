import type { Metadata } from "next";
import { LegalDraftNote } from "@/components/features/legal-draft-note";
import { site } from "@/lib/site";

export const metadata: Metadata = { title: "개인정보처리방침", description: `${site.name} 개인정보처리방침` };

// Q10(2026-11-13): 실서비스 전환 시 검토 예정. 현재 초안(법률 자문 아님). 확정 시 개인정보 보호책임자·연락처 기입.
export default function PrivacyPage() {
  return (
    <article className="container-page section">
      <div className="prose-ko mx-auto max-w-prose">
        <h1 className="text-h1">개인정보처리방침</h1>
        <div className="mt-8"><LegalDraftNote /></div>
        <h2>1. 처리하는 정보</h2>
        <ul>
          <li>서비스는 회원가입이 없으며 이용자의 이름, 연락처 등 개인정보를 받지 않아요.</li>
          <li>분석 요청 시 입력한 상품 링크·상품명과 분석 결과를 서비스 운영(결과 재사용, 오류 확인)을 위해 저장해요.</li>
          <li>서버 운영 과정에서 접속 기록(IP 주소, 접속 시각)이 일시적으로 남을 수 있어요.</li>
        </ul>
        <h2>2. 업로드한 이미지</h2>
        <p>캡처 이미지는 상품명을 읽는 데만 메모리에서 쓰고 저장하지 않아요. 이미지 속 메타데이터(촬영 정보 등)는 읽기 전에 지워요.</p>
        <h2>3. 리뷰 데이터</h2>
        <p>분석을 위해 쿠팡에 공개된 리뷰의 본문, 별점, 작성일을 모아요. 작성자 닉네임 등 작성자를 알아볼 수 있는 정보는 저장하지 않아요.</p>
        <h2>4. 쿠키와 분석 도구</h2>
        <p>서비스는 방문자 분석 도구나 광고 쿠키를 쓰지 않아요. 화면 이동에 필요한 정보만 브라우저에 잠시 보관해요.</p>
        <h2>5. 보관 기간</h2>
        <p>분석 결과와 리뷰 표본은 결과 재사용을 위해 보관하며, 운영 목적이 끝나면 지체 없이 파기해요.</p>
        <h2>6. 문의</h2>
        <p>개인정보 관련 문의는 {site.contactEmail ?? "서비스 운영자"}에게 연락해 주세요.</p>
      </div>
    </article>
  );
}
