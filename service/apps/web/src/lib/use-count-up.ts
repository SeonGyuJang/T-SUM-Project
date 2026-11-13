"use client";

import { useEffect, useState } from "react";

/** 핵심 비교 카드에만 한 번 쓰는 숫자 카운트업. prefers-reduced-motion이면 바로 최종값. */
export function useCountUp(target: number | null, durationMs = 700): number | null {
  const [v, setV] = useState<number | null>(target);
  useEffect(() => {
    if (target == null) return;
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const dur = reduce ? 0 : durationMs;
    const from = Math.max(0, target - 0.6);
    const t0 = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const k = dur ? Math.min(1, (t - t0) / dur) : 1;
      const eased = 1 - Math.pow(1 - k, 3);
      setV(from + (target - from) * eased);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs]);
  return v;
}
