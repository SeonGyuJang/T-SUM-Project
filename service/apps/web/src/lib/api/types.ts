import type { AnalysisView, CreateAnalysisResponse, ResolveResult } from "./schema";

export type ResolveInput = { url: string } | { query: string } | { image: File };

export interface RealstarApi {
  resolve(input: ResolveInput): Promise<ResolveResult>;
  createAnalysis(productId: string, opts?: { forceRefresh?: boolean; source?: Record<string, unknown> }): Promise<CreateAnalysisResponse>;
  getAnalysis(id: string): Promise<AnalysisView>;
}
