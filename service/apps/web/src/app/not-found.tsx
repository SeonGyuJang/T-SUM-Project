import { ButtonLink } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="container-page section text-center">
      <p className="text-caption font-semibold text-primary">404</p>
      <h1 className="mt-2 text-h1">페이지를 찾을 수 없어요</h1>
      <p className="mt-3 text-muted">주소가 바뀌었거나 없어진 페이지예요.</p>
      <div className="mt-8 flex justify-center gap-3">
        <ButtonLink href="/">홈으로</ButtonLink>
        <ButtonLink href="/analyze" variant="secondary">분석 다시 시작</ButtonLink>
      </div>
    </div>
  );
}
