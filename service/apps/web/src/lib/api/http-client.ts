import { apiBaseUrl } from "@/lib/site";
import { ApiError, NETWORK_ERROR_MESSAGE } from "./errors";
import {
  analysisViewSchema,
  apiErrorSchema,
  createAnalysisSchema,
  productListSchema,
  resolveResultSchema,
  reviewPageSchema,
  type AnalysisView,
  type CreateAnalysisResponse,
  type ProductSummary,
  type ResolveResult,
  type ReviewPage,
} from "./schema";
import type { RealstarApi, ResolveInput, ReviewQuery } from "./types";

async function request<T>(path: string, init: RequestInit, parse: (data: unknown) => T): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${apiBaseUrl}${path}`, { ...init, cache: "no-store" });
  } catch {
    throw new ApiError("network", NETWORK_ERROR_MESSAGE);
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) {
    const parsed = apiErrorSchema.safeParse(body);
    if (parsed.success) throw new ApiError(parsed.data.error.code, parsed.data.error.message, res.status);
    throw new ApiError("http_" + res.status, "요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.", res.status);
  }
  try {
    return parse(body);
  } catch (e) {
    console.error("API schema mismatch", path, e);
    throw new ApiError("schema", "서버 응답 형식이 올바르지 않아요. 잠시 후 다시 시도해 주세요.", res.status);
  }
}

export const httpApi: RealstarApi = {
  resolve(input: ResolveInput): Promise<ResolveResult> {
    const form = new FormData();
    if ("url" in input) form.set("url", input.url);
    else if ("query" in input) form.set("query", input.query);
    else form.set("image", input.image);
    return request("/api/resolve", { method: "POST", body: form }, (d) => resolveResultSchema.parse(d));
  },
  createAnalysis(productId, opts): Promise<CreateAnalysisResponse> {
    return request(
      "/api/analyses",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_id: productId, force_refresh: !!opts?.forceRefresh, source: opts?.source }),
      },
      (d) => createAnalysisSchema.parse(d),
    );
  },
  getAnalysis(id): Promise<AnalysisView> {
    return request(`/api/analyses/${encodeURIComponent(id)}`, { method: "GET" }, (d) => analysisViewSchema.parse(d));
  },
  listProducts(): Promise<ProductSummary[]> {
    return request("/api/products", { method: "GET" }, (d) => productListSchema.parse(d).items);
  },
  getReviews(productId: string, q: ReviewQuery = {}): Promise<ReviewPage> {
    const params = new URLSearchParams();
    if (q.star) params.set("star", String(q.star));
    params.set("offset", String(q.offset ?? 0));
    params.set("limit", String(q.limit ?? 10));
    if (q.modelVersion) params.set("model_version", q.modelVersion);
    return request(`/api/products/${encodeURIComponent(productId)}/reviews?${params}`, { method: "GET" }, (d) => reviewPageSchema.parse(d));
  },
};
