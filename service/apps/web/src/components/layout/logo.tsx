import Link from "next/link";
import { site } from "@/lib/site";

/** 텍스트 로고 (Q2 기본값). 별 모양 마크는 자체 제작 SVG. */
export function Logo() {
  return (
    <Link href="/" className="inline-flex items-center gap-2 text-h3 font-extrabold tracking-tight text-text" aria-label={`${site.name} 홈`}>
      <svg aria-hidden viewBox="0 0 24 24" className="size-7">
        <rect width="24" height="24" rx="7" className="fill-primary" />
        <path d="M12 5.2l2 4.1 4.5.6-3.3 3.1.8 4.5-4-2.2-4 2.2.8-4.5L5.5 9.9l4.5-.6z" className="fill-white" />
      </svg>
      {site.name}
    </Link>
  );
}
