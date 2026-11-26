/**
 * 브라우저 안에서 동작하는 API 구현.
 * - 발표 모드(NEXT_PUBLIC_DEMO_MODE=true): 네트워크 없이 저장된 예시 결과로 전체 흐름을 재생한다.
 * - 목업 모드(NEXT_PUBLIC_API_MODE=mock): MSW 핸들러가 이 로직을 써서 5.7 스키마 응답을 만든다.
 * 저장된 결과를 실시간 결과처럼 꾸미지 않는다: 결과에는 cached=true와 원래 수집 시각이 그대로 들어간다.
 */
import { DEMO_EXAMPLES, exampleByKey, exampleByProductId, type DemoExample } from "@/demo/examples";
import { ApiError, DEMO_ONLY_MESSAGE } from "./errors";
import type { AnalysisView, Candidate, CreateAnalysisResponse, DetectLabel, DetectResult, ProductSummary, Progress, ResolveResult, ReviewItem, ReviewPage, StarKey } from "./schema";
import type { ReviewQuery } from "./types";

export type LocalMode = "demo" | "mock";
export const REPLAY_MS = 12_000;

/** 목업 전용 상태 시나리오(차단·오류) — 상태 화면 개발과 E2E 테스트용 */
export const MOCK_SCENARIOS: Record<string, { name: string; kind: "blocked" | "failed" }> = {
  "9000000001": { name: "[모의] 수집 차단 시나리오", kind: "blocked" },
  "9000000002": { name: "[모의] 화면 구조 변경 시나리오", kind: "failed" },
};

const SHORT_LINKS: Record<string, string> = { "https://link.coupang.com/a/demo01": "1000000001" };

function candidateOf(ex: DemoExample, score = 1): Candidate {
  const p = ex.result.product;
  return {
    product_id: p.product_id,
    name: p.name,
    image_url: p.image_url,
    url: p.url,
    price: null,
    is_ad: false,
    rating: ex.result.platform_stats.displayed_avg ?? null,
    review_count: ex.result.platform_stats.total_reviews,
    match_score: score,
  };
}

function productIdFromText(text: string): string | null {
  const t = text.trim();
  const short = Object.keys(SHORT_LINKS).find((k) => t.includes(k));
  if (short) return SHORT_LINKS[short] ?? null;
  const m = /coupang\.com\/(?:vp|vm)\/products\/(\d+)/.exec(t);
  return m?.[1] ?? null;
}

const norm = (s: string) => s.toLowerCase().replace(/[[\]()]/g, " ").replace(/\s+/g, " ").trim();

function scoreQuery(query: string, ex: DemoExample): number {
  const q = norm(query).split(" ").filter((t) => t.length >= 2);
  const name = norm(`${ex.result.product.name ?? ""} ${ex.input_examples.query ?? ""}`);
  if (!q.length) return 0;
  const hits = q.filter((t) => name.includes(t)).length;
  return Math.round((hits / q.length) * 100) / 100;
}

export function localResolve(mode: LocalMode, input: { url?: string; query?: string; image?: boolean }): ResolveResult {
  if (input.url !== undefined) {
    const pid = productIdFromText(input.url);
    if (!pid) {
      if (!/coupang\.com|coupa\.ng/.test(input.url)) throw new ApiError("invalid_input", "지금은 쿠팡 상품 링크만 분석할 수 있어요.", 422);
      if (mode === "demo") throw new ApiError("demo_only", DEMO_ONLY_MESSAGE, 422);
      throw new ApiError("invalid_input", "상품 상세 페이지 링크를 넣어 주세요. (검색·장바구니 페이지는 분석할 수 없어요)", 422);
    }
    const ex = exampleByProductId(pid);
    if (ex) return { status: "resolved", candidates: [candidateOf(ex)], input_type: "url", query: input.url, cached: false };
    if (mode === "mock" && MOCK_SCENARIOS[pid]) {
      return {
        status: "resolved",
        candidates: [{ product_id: pid, name: MOCK_SCENARIOS[pid].name, url: `https://www.coupang.com/vp/products/${pid}`, is_ad: false, match_score: 1 }],
        input_type: "url",
        query: input.url,
        cached: false,
      };
    }
    if (mode === "demo") throw new ApiError("demo_only", DEMO_ONLY_MESSAGE, 422);
    return { status: "resolved", candidates: [{ product_id: pid, is_ad: false, match_score: 1, url: `https://www.coupang.com/vp/products/${pid}` }], input_type: "url", query: input.url, cached: false };
  }
  if (input.query !== undefined) {
    const q = input.query.trim();
    if (q.replace(/\s/g, "").length < 2) throw new ApiError("invalid_input", "상품명을 두 글자 이상 입력해 주세요.", 422);
    const scored = DEMO_EXAMPLES.map((ex) => ({ ex, s: scoreQuery(q, ex) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s);
    if (!scored.length) {
      if (mode === "demo") throw new ApiError("demo_only", DEMO_ONLY_MESSAGE, 422);
      return { status: "not_found", candidates: [], input_type: "query", query: q, message: "검색 결과가 없어요. 상품명을 조금 더 간단히 입력해 보세요.", cached: false };
    }
    return { status: "needs_selection", candidates: scored.map((x) => candidateOf(x.ex, x.s)), input_type: "query", query: q, cached: false };
  }
  // 이미지: 발표 모드에서는 이미지 인식을 하지 않고 예시 상품 후보를 그대로 보여준다(그렇다고 화면에 안내한다).
  return {
    status: "needs_selection",
    candidates: DEMO_EXAMPLES.map((ex) => candidateOf(ex, 0.5)),
    input_type: "image",
    query: null,
    extracted: { local_mode: mode, note: "예시 상품 후보" },
    message: mode === "demo" ? "발표 모드에서는 이미지 인식 대신 예시 상품 후보를 보여드려요." : null,
    cached: false,
  };
}

export function localCreate(mode: LocalMode, productId: string): CreateAnalysisResponse {
  const ex = exampleByProductId(productId);
  const ts = Date.now();
  if (ex) return { analysis_id: `${mode}-${ex.key}-${ts}`, status: "queued", queue_position: 1, cached: false };
  if (mode === "mock" && MOCK_SCENARIOS[productId]) return { analysis_id: `mock-s${productId}-${ts}`, status: "queued", queue_position: 1, cached: false };
  if (mode === "demo") throw new ApiError("demo_only", DEMO_ONLY_MESSAGE, 422);
  return { analysis_id: `mock-unknown${productId}-${ts}`, status: "queued", queue_position: 2, cached: false };
}

function collectProgress(ex: DemoExample | null, f: number): Progress {
  const steps = (ex?.replay ?? []).filter((r) => r.stage === "collect");
  const stars: Record<string, { collected: number; target: number; total: number; status: string }> = {};
  const per = ex?.result.per_star;
  const share = steps.length ? 1 / steps.length : 1;
  let current: number | undefined;
  let msg = "상품 정보를 확인하고 있어요";
  steps.forEach((st, i) => {
    const key = String(st.star) as StarKey;
    const target = st.target ?? 0;
    const local = Math.min(1, Math.max(0, (f - i * share) / share));
    const collected = target === 0 ? 0 : Math.floor(local * (st.collected ?? target));
    const status = target === 0 ? "skipped" : local >= 1 ? "done" : local > 0 ? "collecting" : "pending";
    if (status === "collecting") {
      current = st.star;
      msg = `${st.star}점 리뷰 수집 중 ${collected}/${target}`;
    }
    stars[key] = { collected, target, total: per?.[key]?.total ?? target, status };
  });
  return { stage: "collect", stars, current_star: current, message: msg, eta_seconds: Math.round(((1 - f) * REPLAY_MS) / 1000) };
}

export function localGet(id: string, now = Date.now()): AnalysisView {
  const m = /^(demo|mock)-([a-z0-9]+)(?:-(\d+))?$/.exec(id);
  if (!m) throw new ApiError("not_found", "분석 결과를 찾지 못했어요. 주소를 확인하거나 다시 분석해 주세요.", 404);
  const [, mode, key, tsRaw] = m as unknown as [string, LocalMode, string, string | undefined];
  const scenarioPid = key.startsWith("s") ? key.slice(1) : null;
  const scenario = scenarioPid ? MOCK_SCENARIOS[scenarioPid] : undefined;
  const unknown = key.startsWith("unknown");
  const ex = scenario || unknown ? null : exampleByKey(key);
  if (!ex && !scenario && !unknown) throw new ApiError("not_found", "분석 결과를 찾지 못했어요. 주소를 확인하거나 다시 분석해 주세요.", 404);
  const productId = ex?.result.product.product_id ?? scenarioPid ?? key.replace("unknown", "");
  const ts = tsRaw ? Number(tsRaw) : now - REPLAY_MS * 2;
  const f = Math.min(1, Math.max(0, (now - ts) / REPLAY_MS));
  const base = {
    analysis_id: id,
    product_id: productId,
    cached: true,
    created_at: new Date(ts).toISOString(),
    demo: mode === "demo",
  };
  const product = ex ? { product_id: productId, name: ex.result.product.name, image_url: ex.result.product.image_url } : { product_id: productId, name: scenario?.name ?? null };

  if (scenario && f >= (scenario.kind === "blocked" ? 0.45 : 0.3)) {
    const until = new Date(ts + 60 * 60 * 1000).toISOString();
    return {
      ...base,
      status: scenario.kind,
      progress: { stage: scenario.kind, product },
      result: null,
      error:
        scenario.kind === "blocked"
          ? { code: "blocked", message: "지금은 쿠팡에서 정보를 가져올 수 없어요. 잠시 후 다시 시도하거나 저장된 결과를 확인해 주세요.", cooldown_until: until, cached_analysis_id: "mock-vacuum", cached_collected_at: DEMO_EXAMPLES[0]?.result.sampling.collected_at }
          : { code: "parser_broken", message: "쿠팡 화면 구조가 바뀌어 리뷰를 읽지 못했어요. 운영팀이 확인 중이에요." },
      finished_at: new Date(now).toISOString(),
    };
  }
  if (unknown && f >= 0.2) {
    return { ...base, status: "failed", progress: { stage: "failed" }, result: null, error: { code: "invalid_input", message: "상품을 찾지 못했어요. 링크를 확인해 주세요." } };
  }
  if (f < 0.08) return { ...base, status: "queued", progress: { stage: "resolve", queue_position: 1, message: "대기열에서 순서를 기다리고 있어요", product }, result: null };
  if (f < 0.7) {
    const p = collectProgress(ex ?? DEMO_EXAMPLES[0] ?? null, (f - 0.08) / 0.62);
    return { ...base, status: "collecting", progress: { ...p, product }, result: null };
  }
  const total = ex ? Object.values(ex.result.per_star).reduce((a, s) => a + s.collected, 0) : 0;
  const finishedStars = collectProgress(ex ?? null, 1).stars;
  if (f < 0.88) {
    const detected = Math.floor(((f - 0.7) / 0.18) * total);
    return { ...base, status: "detecting", progress: { stage: "detect", stars: finishedStars, detected, detect_total: total, message: "AI 작성 여부를 판별하고 있어요", product }, result: null };
  }
  if (f < 1 || !ex) return { ...base, status: "aggregating", progress: { stage: "aggregate", stars: finishedStars, message: "별점을 다시 계산하고 있어요", product }, result: null };
  return {
    ...base,
    status: "done",
    progress: { stage: "done", stars: finishedStars, message: "분석이 끝났어요", product },
    result: { ...ex.result, analysis_id: id, sampling: { ...ex.result.sampling, from_cache: true } },
    finished_at: new Date(ts + REPLAY_MS).toISOString(),
  };
}

/** 예시 상품 목록 (발표·목업 모드에서 '수집한 상품' 영역에 쓴다) */
export function localProducts(mode: LocalMode): ProductSummary[] {
  return DEMO_EXAMPLES.map((ex) => ({
    product_id: ex.result.product.product_id,
    name: ex.result.product.name,
    image_url: ex.result.product.image_url,
    url: ex.result.product.url,
    total_reviews: ex.result.platform_stats.total_reviews,
    collected_reviews: Object.values(ex.result.per_star).reduce((a, s) => a + s.collected, 0),
    collected_at: ex.result.sampling.collected_at,
    complete: true,
    avg_all: ex.result.ratings.avg_all,
    analysis_id: `${mode}-${ex.key}`,
    source: "example",
  }));
}

/** 예시 데이터에는 리뷰 원문 전체가 없어 Top 5 리뷰를 원문 목록처럼 보여준다. */
export function localReviews(productId: string, q: ReviewQuery = {}): ReviewPage {
  const ex = exampleByProductId(productId);
  const keys = (q.star ? [String(q.star)] : ["5", "4", "3", "2", "1"]) as StarKey[];
  const all: ReviewItem[] = ex
    ? keys.flatMap((k) =>
        ex.result.top_human_reviews[k].map((r) => ({
          review_id: r.review_id, star: Number(k), title: r.title, content: r.text, created_at: r.created_at,
          has_photo: r.has_photo, option_name: null, len_chars: r.len_chars, is_sponsored: false, label: "human", p_ai: 1 - r.p_human,
        })),
      )
    : [];
  const offset = q.offset ?? 0;
  const limit = q.limit ?? 10;
  return { product_id: productId, star: q.star ?? null, total: all.length, offset, limit, items: all.slice(offset, offset + limit) };
}

/**
 * 리뷰 직접 판별의 발표·목업용 예시 판정. 실제 모델이 아니라 글의 겉모습(맞춤법·문장부호·말투)만 보는 간단한 규칙이다.
 * 화면에 "예시 판정"이라고 표시된다(model.note).
 */
export function localDetect(mode: LocalMode, texts: string[]): DetectResult {
  const MIN = 20;
  const T = { T_AI: 0.8, T_HUMAN: 0.35 };
  const results = texts.map((raw, index) => {
    const t = raw.replace(/\s+/g, " ").trim();
    const n = [...t].length;
    let score = 0.5;
    if (/(습니다|입니다|합니다)[.!]?/.test(t)) score += 0.18;
    if (/(전반적으로|만족스러운|추천드립니다|활용도|실용적)/.test(t)) score += 0.17;
    if (/[ㅋㅎㅠㅜ]{2,}|[~!?]{2,}|\.\.+/.test(t)) score -= 0.3;
    if (!/[.!?]$/.test(t)) score -= 0.08;
    const p_ai = Math.round(Math.min(0.99, Math.max(0.01, score)) * 1000) / 1000;
    const too_short = n < MIN;
    const label: DetectLabel = too_short ? "uncertain" : p_ai > T.T_AI ? "ai" : p_ai <= T.T_HUMAN ? "human" : "uncertain";
    return { index, label, p_ai, len_chars: n, too_short, thresholds: T, reason_tags: too_short ? ["짧은 리뷰(판단 보류)"] : [] };
  });
  return {
    model: {
      version: `${mode}-example`,
      is_dummy: true,
      min_chars: MIN,
      note: mode === "demo" ? "발표 모드: 실제 AI 판별 모델이 아니라 예시 규칙으로 판정한 결과예요." : "목업 모드: 실제 AI 판별 모델이 아니라 예시 규칙으로 판정한 결과예요.",
    },
    results,
  };
}

export function localApiFor(mode: LocalMode) {
  const delay = <T,>(v: () => T, ms = 350) =>
    new Promise<T>((resolve, reject) => setTimeout(() => {
      try { resolve(v()); } catch (e) { reject(e); }
    }, ms));
  return {
    resolve: (input: { url: string } | { query: string } | { image: File }) =>
      delay(() => localResolve(mode, "url" in input ? { url: input.url } : "query" in input ? { query: input.query } : { image: true }), 600),
    createAnalysis: (pid: string) => delay(() => localCreate(mode, pid)),
    getAnalysis: (id: string) => delay(() => localGet(id), 120),
    listProducts: () => delay(() => localProducts(mode), 150),
    getReviews: (pid: string, q?: ReviewQuery) => delay(() => localReviews(pid, q), 150),
    detectReviews: (texts: string[]) => delay(() => localDetect(mode, texts), 400),
  };
}
