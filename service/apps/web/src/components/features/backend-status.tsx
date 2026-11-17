"use client";

import { useQuery } from "@tanstack/react-query";
import { Notice } from "@/components/ui/notice";
import { apiBaseUrl, apiMode, isDemoMode } from "@/lib/site";

type Health = {
  review_provider?: string;
  crawler?: { enabled?: boolean; ok?: boolean; problem?: string | null; python?: string; scrapling_installed?: boolean };
};

/**
 * 실제 API 모드에서 서버 설정이 잘못됐을 때 입력창 위에 알려 준다.
 * (예시 데이터 모드로 떠 있거나, 수집기를 실행할 수 없거나, API 서버가 꺼져 있을 때)
 */
export function BackendStatus() {
  const enabled = !isDemoMode && apiMode === "live";
  const q = useQuery({
    queryKey: ["health"],
    enabled,
    staleTime: 30_000,
    retry: 1,
    queryFn: async (): Promise<Health> => {
      const r = await fetch(`${apiBaseUrl}/api/health`, { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      return (await r.json()) as Health;
    },
  });
  if (!enabled) return null;
  if (q.isError) {
    return (
      <Notice tone="danger" className="mb-5" title="API 서버에 연결할 수 없어요">
        {apiBaseUrl} 에 응답이 없어요. service 폴더에서 <code>uvicorn --factory realstar_api.main:create_app --port 8000</code> 을 실행했는지 확인해 주세요.
      </Notice>
    );
  }
  const h = q.data;
  if (!h) return null;
  if (h.review_provider === "fixture") {
    return (
      <Notice tone="warning" className="mb-5" title="예시 데이터 모드로 실행 중이에요">
        지금은 쿠팡 수집기를 실행하지 않고 예시 상품만 분석해요. 실제로 수집하려면 <code>service/.env</code> 에서{" "}
        <code>REVIEW_PROVIDER=crawler</code> 로 바꾸고 API 서버를 다시 시작해 주세요.
      </Notice>
    );
  }
  if (h.crawler?.enabled && h.crawler.ok === false) {
    return (
      <Notice tone="warning" className="mb-5" title="리뷰 수집기를 실행할 수 없어요">
        {h.crawler.problem ?? "수집기 설치 상태를 확인해 주세요."} (수집기 파이썬: <code>{h.crawler.python}</code>) ·{" "}
        이 파이썬에 <code>pip install &quot;scrapling[fetchers]&quot;</code> 를 하거나 <code>service/.env</code> 의{" "}
        <code>CRAWLER_PYTHON</code> 에 크롤러용 파이썬 경로를 적어 주세요. 이미 수집한 상품은 그대로 볼 수 있어요.
      </Notice>
    );
  }
  return null;
}
