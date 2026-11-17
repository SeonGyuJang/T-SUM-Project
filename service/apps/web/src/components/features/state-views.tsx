import type { LucideIcon } from "lucide-react";
import { Ban, CircleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { AnalysisError } from "@/lib/api/schema";
import { fmtDateTime } from "@/lib/format";

export function EmptyState({ icon: Icon, title, body, action }: { icon: LucideIcon; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <Card className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <Icon aria-hidden className="size-10 text-muted" />
      <h2 className="text-h3">{title}</h2>
      {body && <p className="max-w-md text-muted">{body}</p>}
      {action && <div className="mt-2">{action}</div>}
    </Card>
  );
}

const ERROR_NEXT: Record<string, string> = {
  parser_broken: "쿠팡 화면이 바뀌면 이런 일이 생겨요. 확인 후 다시 열어 둘게요.",
  detector_unavailable: "판별 모델 서버를 점검하고 있어요.",
  page_budget_exceeded: "오늘 수집할 수 있는 양을 모두 썼어요.",
  scraper_busy: "다른 분석이 끝나면 다시 시도해 주세요.",
  crawler_unavailable: "서버에서 수집기(coupang_reviews.py)와 scrapling 설치 상태를 확인해 주세요.",
};

export function ErrorState({ error, productId }: { error?: AnalysisError | null; productId?: string }) {
  const msg = error?.message ?? "분석 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.";
  return (
    <Card role="alert" className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <CircleAlert aria-hidden className="size-10 text-danger" />
      <h2 className="text-h3">분석을 마치지 못했어요</h2>
      <p className="max-w-md text-muted">{msg}</p>
      {error?.code && ERROR_NEXT[error.code] && <p className="max-w-md text-caption text-muted">{ERROR_NEXT[error.code]}</p>}
      <div className="mt-2 flex flex-wrap justify-center gap-3">
        <ButtonLink href="/analyze">다시 분석하기</ButtonLink>
        {error?.cached_analysis_id && (
          <ButtonLink href={`/analyses/${error.cached_analysis_id}`} variant="secondary">저장된 결과 보기</ButtonLink>
        )}
      </div>
      {productId && <p className="text-caption text-muted">상품 번호 {productId}</p>}
    </Card>
  );
}

export function BlockedState({ error }: { error?: AnalysisError | null }) {
  return (
    <Card role="alert" className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <Ban aria-hidden className="size-10 text-warning" />
      <h2 className="text-h3">지금은 리뷰를 가져올 수 없어요</h2>
      <p className="max-w-md text-muted">
        쿠팡이 잠시 자동 접근을 막고 있어요. 무리하게 다시 시도하지 않고 잠시 쉬었다가 다시 열어요.
      </p>
      {error?.cooldown_until && <p className="text-caption text-muted">다시 시도 가능 시각: {fmtDateTime(error.cooldown_until)}</p>}
      <div className="mt-2 flex flex-wrap justify-center gap-3">
        {error?.cached_analysis_id ? (
          <ButtonLink href={`/analyses/${error.cached_analysis_id}`}>저장된 결과 보기</ButtonLink>
        ) : (
          <ButtonLink href="/">홈으로</ButtonLink>
        )}
        <ButtonLink href="/analyze" variant="secondary">다른 상품 분석하기</ButtonLink>
      </div>
      {error?.cached_collected_at && <p className="text-caption text-muted">저장된 결과 수집 시각: {fmtDateTime(error.cached_collected_at)}</p>}
    </Card>
  );
}
