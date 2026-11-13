import Link from "next/link";
import { ButtonLink } from "@/components/ui/button";
import { Logo } from "./logo";

const NAV = [
  { href: "/how-it-works", label: "작동 원리" },
  { href: "/faq", label: "자주 묻는 질문" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/95 backdrop-blur">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded focus:bg-surface focus:px-4 focus:py-2">
        본문으로 바로가기
      </a>
      <div className="container-page flex h-16 items-center justify-between gap-4">
        <Logo />
        <nav aria-label="주요 메뉴" className="flex items-center gap-1 sm:gap-2">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="hidden rounded-sm px-3 py-2 text-caption font-medium text-muted hover:text-text sm:inline-block md:text-body">
              {n.label}
            </Link>
          ))}
          <ButtonLink href="/analyze" size="sm" className="ml-1">
            분석하기
          </ButtonLink>
        </nav>
      </div>
      <nav aria-label="모바일 메뉴" className="container-page flex gap-4 pb-2 sm:hidden">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} className="text-caption font-medium text-muted hover:text-text">
            {n.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
