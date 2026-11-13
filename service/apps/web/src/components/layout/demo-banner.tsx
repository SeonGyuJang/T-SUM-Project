import { isDemoMode } from "@/lib/site";

export function DemoBanner() {
  if (!isDemoMode) return null;
  return (
    <div role="note" className="bg-primary text-center text-caption font-medium text-primary-fg">
      <p className="container-page py-2">발표 모드 · 미리 분석해 저장한 예시 상품 결과를 보여드려요</p>
    </div>
  );
}
