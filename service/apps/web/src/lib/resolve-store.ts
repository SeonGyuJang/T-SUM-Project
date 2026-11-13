import { resolveResultSchema, type ResolveResult } from "@/lib/api/schema";

const KEY = "realstar:last-resolve";

/** 후보 선택 화면으로 넘길 식별 결과. 이미지 원본은 저장하지 않는다(추출 텍스트·후보만). */
export function saveResolve(r: ResolveResult) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(r));
  } catch {
    /* 저장 불가 환경: 선택 화면에서 다시 검색 안내 */
  }
}

export function loadResolve(): ResolveResult | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = resolveResultSchema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}
