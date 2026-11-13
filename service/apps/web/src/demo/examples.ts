/**
 * 발표 모드 예시 데이터 (README 14.7).
 * 데이터 목록은 data/index.ts. `python -m realstar prepare-demo --products ../docs/demo-products.txt`가
 * 오너가 고른 실제 상품(docs/demo-products.txt)을 분석해 이 목록을 실제 결과로 바꾼다.
 * 현재는 실제 모델이 없어 is_placeholder=true인 가상 예시 3개가 들어 있다(화면에 "샘플 데이터" 표시).
 */
import { analysisResultSchema, type AnalysisResult } from "@/lib/api/schema";
import { DEMO_DATA } from "./data";

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

export const DEMO_EXAMPLES: DemoExample[] = DEMO_DATA.map(load);

export function exampleByKey(key: string): DemoExample | undefined {
  return DEMO_EXAMPLES.find((e) => e.key === key);
}

export function exampleByProductId(pid: string): DemoExample | undefined {
  return DEMO_EXAMPLES.find((e) => e.result.product.product_id === pid);
}
