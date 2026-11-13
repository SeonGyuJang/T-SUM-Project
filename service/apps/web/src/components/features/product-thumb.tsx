import { Package } from "lucide-react";
import Image from "next/image";
import { cn } from "@/lib/cn";

/** 상품 썸네일: 분석 결과·후보 화면에서만 쓴다(README 14.5). 없으면 자체 아이콘. */
export function ProductThumb({ src, alt, size = 96, className }: { src?: string | null; alt: string; size?: number; className?: string }) {
  const box = cn("relative shrink-0 overflow-hidden rounded-lg border border-border bg-subtle", className);
  if (!src) {
    return (
      <div className={box} style={{ width: size, height: size }} aria-hidden>
        <Package className="absolute inset-0 m-auto size-1/3 text-muted" />
      </div>
    );
  }
  const local = src.startsWith("/");
  return (
    <div className={box} style={{ width: size, height: size }}>
      <Image src={src} alt={alt} fill sizes={`${size}px`} className="object-contain p-1" unoptimized={local && src.endsWith(".svg")} />
    </div>
  );
}
