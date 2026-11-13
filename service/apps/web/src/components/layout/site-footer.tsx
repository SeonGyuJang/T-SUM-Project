import Link from "next/link";
import { site } from "@/lib/site";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-border bg-subtle">
      <div className="container-page grid gap-8 py-12 md:grid-cols-[1fr_auto]">
        <div className="space-y-2">
          <p className="font-bold">{site.name}</p>
          <p className="text-caption text-muted">{site.tagline}</p>
          <p className="text-caption text-muted">쿠팡과 무관한 독립 서비스예요. 분석 결과는 통계적 추정이며 오차가 있을 수 있어요.</p>
        </div>
        <nav aria-label="하단 메뉴" className="flex flex-wrap items-start gap-x-6 gap-y-2 text-caption">
          <Link href="/how-it-works" className="text-muted hover:text-text">작동 원리</Link>
          <Link href="/faq" className="text-muted hover:text-text">자주 묻는 질문</Link>
          <Link href="/about" className="text-muted hover:text-text">소개</Link>
          <Link href="/terms" className="text-muted hover:text-text">이용약관</Link>
          <Link href="/privacy" className="font-semibold text-muted hover:text-text">개인정보처리방침</Link>
          {site.contactEmail && (
            <a href={`mailto:${site.contactEmail}`} className="text-muted hover:text-text">문의 {site.contactEmail}</a>
          )}
        </nav>
      </div>
      <div className="container-page border-t border-border py-6 text-caption text-muted">© {new Date().getFullYear()} {site.name}</div>
    </footer>
  );
}
