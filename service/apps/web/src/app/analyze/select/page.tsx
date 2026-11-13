import type { Metadata } from "next";
import { SelectView } from "./select-view";

export const metadata: Metadata = { title: "상품 선택", description: "분석할 상품을 골라 주세요.", robots: { index: false } };

export default function SelectPage() {
  return <SelectView />;
}
