/**
 * 사이트 전역 설정. 오너 답변이 필요한 값은 TODO(owner)로 표시했다(README 14.2, docs/decisions.md).
 */
export const site = {
  // TODO(owner): Q1 서비스 이름과 한 줄 소개 — 현재 추천 기본값 사용
  name: "리얼별점",
  tagline: "AI가 쓴 리뷰를 걸러낸 진짜 별점",
  description:
    "쿠팡 상품 리뷰에서 AI 작성으로 추정되는 리뷰를 골라내고, 사람이 쓴 리뷰만으로 별점을 다시 계산해 보여드려요.",
  // TODO(owner): Q6 배포 주소 — 환경 변수 NEXT_PUBLIC_SITE_URL로 지정
  url: process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000",
  // TODO(owner): Q7 문의 이메일 — 기본값(노출 안 함). 값을 넣으면 푸터에 표시된다.
  contactEmail: null as string | null,
  // TODO(owner): Q8 모델 성능 공개 — 기본값(공개). 첫 평가 리포트가 나오면 값을 채운다.
  modelMetrics: null as null | {
    evaluatedAt: string;
    tprAt1Fpr: number;
    samples: number;
    note?: string;
  },
};

export const DISCLAIMER =
  "AI 작성 여부는 통계 모델로 추정한 값이며 오차가 있을 수 있습니다. '사람 리뷰 기준 별점'은 별점별 표본(최대 100개)에서 추정한 사람 리뷰 비율을 상품 전체 별점 분포에 반영해 계산했습니다. 이 서비스는 쿠팡과 관련이 없습니다.";

export const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
export const apiMode: "live" | "mock" = process.env.NEXT_PUBLIC_API_MODE === "mock" ? "mock" : "live";
export const apiBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
