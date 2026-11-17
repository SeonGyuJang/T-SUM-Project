import type { AnalysisView, CreateAnalysisResponse, ProductSummary, ResolveResult, ReviewPage } from "./schema";

export type ResolveInput = { url: string } | { query: string } | { image: File };

export type ReviewQuery = { star?: number | null; offset?: number; limit?: number; modelVersion?: string | null };

export interface RealstarApi {
  resolve(input: ResolveInput): Promise<ResolveResult>;
  createAnalysis(productId: string, opts?: { forceRefresh?: boolean; source?: Record<string, unknown> }): Promise<CreateAnalysisResponse>;
  getAnalysis(id: string): Promise<AnalysisView>;
  /** 수집을 마친 상품 목록 (수집기 output/ + 분석 기록) */
  listProducts(): Promise<ProductSummary[]>;
  /** 수집한 리뷰 원문 (별점 필터·페이지) */
  getReviews(productId: string, q?: ReviewQuery): Promise<ReviewPage>;
}
