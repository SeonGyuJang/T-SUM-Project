/**
 * 발표 모드 예시 데이터 (README 14.7).
 * 각 JSON은 `python -m realstar export-demo`로 실제 분석 결과를 내보낸 것이어야 한다.
 * TODO(owner): Q5 예시 상품 확정 후 실제 분석 결과로 교체 — 현재 파일은 is_placeholder=true인 가상 예시다.
 */
import { analysisResultSchema, type AnalysisResult } from "@/lib/api/schema";
import airfryer from "./data/airfryer.json";
import tumbler from "./data/tumbler.json";
import vacuum from "./data/vacuum.json";

export type ReplayStep = { stage: string; star?: number; collected?: number; target?: number };

export type DemoExample = {
  key: string;
  is_placeholder: boolean;
  input_examples: { url?: string | null; query?: string | null };
  result: AnalysisResult;
  replay: ReplayStep[];
};

function load(raw: unknown): DemoExample {
  const r = raw as Omit<DemoExample, "result"> & { result: unknown };
  return { ...r, result: analysisResultSchema.parse(r.result) };
}

export const DEMO_EXAMPLES: DemoExample[] = [load(vacuum), load(tumbler), load(airfryer)];

export function exampleByKey(key: string): DemoExample | undefined {
  return DEMO_EXAMPLES.find((e) => e.key === key);
}

export function exampleByProductId(pid: string): DemoExample | undefined {
  return DEMO_EXAMPLES.find((e) => e.result.product.product_id === pid);
}
