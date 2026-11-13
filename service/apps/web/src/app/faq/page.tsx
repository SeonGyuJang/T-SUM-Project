import type { Metadata } from "next";
import { Accordion } from "@/components/ui/accordion";
import { FAQ } from "@/lib/faq";

export const metadata: Metadata = { title: "자주 묻는 질문", description: "정확도, 판단 보류, 체험단 리뷰, 데이터 보관 등 자주 묻는 질문에 답해요." };

export default function FaqPage() {
  return (
    <div className="container-page section">
      <div className="mx-auto max-w-prose">
        <h1 className="text-h1">자주 묻는 질문</h1>
        <div className="mt-10">
          <Accordion headingLevel={2} items={FAQ.map((f) => ({ id: f.id, title: f.q, body: <p>{f.a}</p> }))} />
        </div>
      </div>
    </div>
  );
}
