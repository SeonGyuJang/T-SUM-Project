/**
 * API 스키마 (README 5.7) — 백엔드 service/packages/core/realstar/pipeline/result_schema.py와 같은 구조.
 * 응답은 zod로 검증한다(README 14.8).
 */
import { z } from "zod";

export const STARS = ["5", "4", "3", "2", "1"] as const;
export type StarKey = (typeof STARS)[number];

const starRecord = <T extends z.ZodTypeAny>(v: T) =>
  z.object({ "5": v, "4": v, "3": v, "2": v, "1": v });

export const candidateSchema = z.object({
  product_id: z.string(),
  item_id: z.string().nullish(),
  vendor_item_id: z.string().nullish(),
  name: z.string().nullish(),
  price: z.number().nullish(),
  image_url: z.string().nullish(),
  url: z.string().nullish(),
  is_ad: z.boolean().default(false),
  rating: z.number().nullish(),
  review_count: z.number().nullish(),
  match_score: z.number().nullish(),
});
export type Candidate = z.infer<typeof candidateSchema>;

export const resolveResultSchema = z.object({
  status: z.enum(["resolved", "needs_selection", "not_found", "blocked"]),
  candidates: z.array(candidateSchema).default([]),
  input_type: z.enum(["url", "query", "image"]),
  query: z.string().nullish(),
  extracted: z.record(z.unknown()).nullish(),
  message: z.string().nullish(),
  cached: z.boolean().default(false),
});
export type ResolveResult = z.infer<typeof resolveResultSchema>;

export const createAnalysisSchema = z.object({
  analysis_id: z.string(),
  status: z.string(),
  queue_position: z.number().default(0),
  cached: z.boolean().default(false),
});
export type CreateAnalysisResponse = z.infer<typeof createAnalysisSchema>;

const warningSchema = z.object({
  code: z.string(),
  level: z.string().default("warning"),
  message: z.string(),
  star: z.number().nullish(),
});
export type ResultWarning = z.infer<typeof warningSchema>;

const topReviewSchema = z.object({
  review_id: z.string(),
  title: z.string().nullish(),
  text: z.string(),
  p_human: z.number(),
  created_at: z.string().nullish(),
  has_photo: z.boolean().default(false),
  len_chars: z.number(),
  reason_tags: z.array(z.string()).default([]),
});
export type TopReview = z.infer<typeof topReviewSchema>;

const perStarSchema = z.object({
  total: z.number(),
  collected: z.number(),
  human: z.number(),
  ai: z.number(),
  uncertain: z.number(),
  human_ratio: z.number().nullable(),
  ratio_substituted: z.boolean().default(false),
});
export type PerStar = z.infer<typeof perStarSchema>;

const ci = z.tuple([z.number(), z.number()]).nullish();

export const analysisResultSchema = z.object({
  analysis_id: z.string(),
  product: z.object({
    product_id: z.string(),
    name: z.string().nullish(),
    image_url: z.string().nullish(),
    url: z.string().nullish(),
  }),
  platform_stats: z.object({
    displayed_avg: z.number().nullish(),
    total_reviews: z.number(),
    star_counts: starRecord(z.number()),
  }),
  sampling: z.object({
    per_star_limit: z.number(),
    sort: z.string(),
    collected_at: z.string().nullish(),
    pages_loaded: z.number().default(0),
    selectors_version: z.string().nullish(),
    from_cache: z.boolean().default(false),
  }),
  per_star: starRecord(perStarSchema),
  ratings: z.object({
    avg_all: z.number().nullable(),
    avg_human: z.number().nullable(),
    diff: z.number().nullable(),
    avg_human_ci95: ci,
    diff_ci95: ci,
    ai_share: z.number().nullable(),
    ai_share_ci95: ci,
    corrected: z.record(z.unknown()).nullish(),
  }),
  top_human_reviews: starRecord(z.array(topReviewSchema)),
  flags: z.object({
    sponsored_count: z.number().default(0),
    cash_event_count: z.number().default(0),
    near_duplicate_groups: z.number().default(0),
  }),
  warnings: z.array(warningSchema).default([]),
  model: z.object({
    version: z.string(),
    T_AI: z.number().nullish(),
    T_HUMAN: z.number().nullish(),
    thresholds: z.record(z.unknown()).nullish(),
    is_dummy: z.boolean().default(false),
  }),
  assumptions: z.array(z.string()).default([]),
  /** AI 판별을 했는지. 모델이 아직 없으면 available=false이고 사람 리뷰 기준 값은 비어 있다. */
  detection: z.object({ available: z.boolean().default(true), message: z.string().nullish() }).default({ available: true }),
  review_stats: z
    .record(
      z.object({
        collected: z.number().default(0),
        avg_chars: z.number().nullish(),
        photo_count: z.number().default(0),
        sponsored_count: z.number().default(0),
      }),
    )
    .nullish(),
});
export type AnalysisResult = z.infer<typeof analysisResultSchema>;

const starProgressSchema = z.object({
  collected: z.number().default(0),
  target: z.number().default(0),
  total: z.number().default(0),
  status: z.string().default("pending"),
});
export type StarProgress = z.infer<typeof starProgressSchema>;

export const progressSchema = z
  .object({
    stage: z.string().optional(),
    message: z.string().optional(),
    stars: z.record(starProgressSchema.partial()).optional(),
    current_star: z.number().optional(),
    queue_position: z.number().optional(),
    eta_seconds: z.number().optional(),
    pages_loaded: z.number().optional(),
    detected: z.number().optional(),
    detect_total: z.number().optional(),
    from_cache: z.boolean().optional(),
    product: z
      .object({ product_id: z.string(), name: z.string().nullish(), image_url: z.string().nullish() })
      .optional(),
    updated_at: z.string().optional(),
    started_at: z.string().optional(),
    /** 수집기 실행 단계: browser → open_page → page_loaded → summary → (별점별) → saved, 또는 reuse */
    crawl_stage: z.string().optional(),
    from_saved_file: z.boolean().optional(),
    total_reviews: z.number().nullish(),
    detection_available: z.boolean().optional(),
    logs: z.array(z.object({ at: z.string().optional(), message: z.string() })).optional(),
  })
  .passthrough();
export type Progress = z.infer<typeof progressSchema>;

export const analysisStatusSchema = z.enum([
  "queued",
  "collecting",
  "detecting",
  "aggregating",
  "done",
  "failed",
  "blocked",
]);
export type AnalysisStatus = z.infer<typeof analysisStatusSchema>;

export const analysisErrorSchema = z
  .object({
    code: z.string(),
    message: z.string(),
    detail: z.unknown().optional(),
    cooldown_until: z.string().optional(),
    cached_analysis_id: z.string().optional(),
    cached_collected_at: z.string().nullish(),
  })
  .passthrough();
export type AnalysisError = z.infer<typeof analysisErrorSchema>;

export const analysisViewSchema = z.object({
  analysis_id: z.string(),
  product_id: z.string(),
  status: analysisStatusSchema,
  progress: progressSchema.default({}),
  result: analysisResultSchema.nullable(),
  error: analysisErrorSchema.nullish(),
  cached: z.boolean().default(false),
  created_at: z.string().nullish(),
  finished_at: z.string().nullish(),
  demo: z.boolean().optional(),
});
export type AnalysisView = z.infer<typeof analysisViewSchema>;

export const productSummarySchema = z.object({
  product_id: z.string(),
  name: z.string().nullish(),
  image_url: z.string().nullish(),
  url: z.string().nullish(),
  total_reviews: z.number().nullish(),
  collected_reviews: z.number().nullish(),
  collected_at: z.string().nullish(),
  complete: z.boolean().default(true),
  avg_all: z.number().nullish(),
  analysis_id: z.string().nullish(),
  source: z.string().nullish(),
});
export type ProductSummary = z.infer<typeof productSummarySchema>;
export const productListSchema = z.object({ items: z.array(productSummarySchema).default([]) });

export const reviewItemSchema = z.object({
  review_id: z.string(),
  star: z.number(),
  title: z.string().nullish(),
  content: z.string(),
  created_at: z.string().nullish(),
  has_photo: z.boolean().default(false),
  option_name: z.string().nullish(),
  len_chars: z.number().default(0),
  is_sponsored: z.boolean().default(false),
  label: z.string().nullish(),
  p_ai: z.number().nullish(),
});
export type ReviewItem = z.infer<typeof reviewItemSchema>;
export const reviewPageSchema = z.object({
  product_id: z.string(),
  star: z.number().nullish(),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
  items: z.array(reviewItemSchema),
});
export type ReviewPage = z.infer<typeof reviewPageSchema>;

/** POST /api/detect: 사용자가 입력한 리뷰 글을 바로 판별 */
export const detectLabelSchema = z.enum(["ai", "human", "uncertain"]);
export type DetectLabel = z.infer<typeof detectLabelSchema>;
export const detectResultSchema = z.object({
  model: z.object({
    version: z.string().nullish(),
    is_dummy: z.boolean().default(false),
    min_chars: z.number().default(20),
    /** 발표·목업 모드처럼 실제 모델이 아닌 예시 판정일 때 화면에 보여 줄 안내 */
    note: z.string().nullish(),
  }),
  results: z.array(
    z.object({
      index: z.number(),
      label: detectLabelSchema,
      p_ai: z.number(),
      len_chars: z.number(),
      too_short: z.boolean().default(false),
      thresholds: z.object({ T_AI: z.number(), T_HUMAN: z.number() }).nullish(),
      reason_tags: z.array(z.string()).default([]),
    }),
  ),
});
export type DetectResult = z.infer<typeof detectResultSchema>;

export const apiErrorSchema = z.object({ error: z.object({ code: z.string(), message: z.string() }) });

export const TERMINAL: AnalysisStatus[] = ["done", "failed", "blocked"];
