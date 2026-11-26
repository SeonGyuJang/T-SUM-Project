"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { api, ApiError, type DetectLabel, type DetectResult } from "@/lib/api";
import { cn } from "@/lib/cn";

const MAX_CHARS = 3000;
const MAX_REVIEWS = 20;

const VERDICT: Record<DetectLabel, { badge: string; title: string; tone: "ai" | "human" | "uncertain"; bar: string; body: string }> = {
  ai: {
    badge: "AI 추정",
    title: "AI가 쓴 리뷰일 가능성이 높아요",
    tone: "ai",
    bar: "bg-ai",
    body: "학습한 AI 리뷰들과 말투·구성이 비슷해요. 사람이 쓴 리뷰도 드물게 이렇게 나올 수 있어요.",
  },
  human: {
    badge: "사람 추정",
    title: "사람이 쓴 리뷰로 보여요",
    tone: "human",
    bar: "bg-human",
    body: "실제 구매자 리뷰에서 흔한 표현과 말투에 가까워요.",
  },
  uncertain: {
    badge: "판단 보류",
    title: "어느 쪽이라고 말하기 어려워요",
    tone: "uncertain",
    bar: "bg-uncertain",
    body: "점수가 사람과 AI 기준 사이에 있어서 판정을 미뤘어요.",
  },
};

const EXAMPLES = [
  { label: "예시 1", text: "배송 빨라요 근데 생각보다 사이즈가 작아서 좀 아쉽 ㅠㅠ 그래도 이 가격이면 그냥 쓸만해요" },
  {
    label: "예시 2",
    text: "이 제품은 가볍고 휴대가 간편하여 외출 시 활용도가 매우 높습니다. 수납 공간도 넉넉해 실용적이며 전반적으로 만족스러운 구매였습니다.",
  },
];

function splitReviews(text: string, multiple: boolean): string[] {
  const t = text.trim();
  if (!t) return [];
  if (!multiple) return [t];
  return t.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean);
}

export function ReviewChecker() {
  const [text, setText] = useState("");
  const [multiple, setMultiple] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<string[]>([]);
  const ids = { text: useId(), help: useId(), err: useId(), multi: useId() };

  const m = useMutation({
    mutationFn: (texts: string[]) => api.detectReviews(texts),
  });

  const reviews = splitReviews(text, multiple);
  const tooLong = reviews.find((r) => r.length > MAX_CHARS);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (m.isPending) return;
    if (!reviews.length) return setInputError("판별할 리뷰를 입력해 주세요.");
    if (reviews.length > MAX_REVIEWS) return setInputError(`한 번에 ${MAX_REVIEWS}개까지 확인할 수 있어요. 지금 ${reviews.length}개예요.`);
    if (tooLong) return setInputError(`리뷰 하나는 ${MAX_CHARS.toLocaleString()}자까지 입력할 수 있어요.`);
    setInputError(null);
    setSubmitted(reviews);
    m.mutate(reviews);
  };

  const apiError = m.error ? (m.error instanceof ApiError ? m.error.message : "판별하지 못했어요. 잠시 후 다시 시도해 주세요.") : null;

  return (
    <div className="space-y-10">
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <label htmlFor={ids.text} className="text-h3">
            판별할 리뷰
          </label>
          <div className="flex gap-2">
            {EXAMPLES.map((ex) => (
              <Button
                key={ex.label}
                variant="ghost"
                size="sm"
                onClick={() => {
                  setText(ex.text);
                  setMultiple(false);
                  setInputError(null);
                }}
              >
                {ex.label} 넣기
              </Button>
            ))}
          </div>
        </div>
        <textarea
          id={ids.text}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={multiple ? 10 : 6}
          placeholder={multiple ? "리뷰를 빈 줄로 나누어 붙여 넣으세요.\n\n예) 첫 번째 리뷰\n\n두 번째 리뷰" : "쇼핑몰에서 본 리뷰 내용을 그대로 붙여 넣으세요."}
          aria-describedby={`${ids.help}${inputError ? ` ${ids.err}` : ""}`}
          aria-invalid={!!inputError}
          className="w-full resize-y rounded-lg border border-border-strong bg-surface p-4 text-body leading-relaxed placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary"
        />
        <div id={ids.help} className="flex flex-wrap items-center justify-between gap-2 text-caption text-muted">
          <span>
            {multiple ? `리뷰 ${reviews.length}개 · 한 번에 최대 ${MAX_REVIEWS}개` : `${text.trim().length.toLocaleString()}자`} · 20자 미만은 정보가 적어 판단 보류로 나와요
          </span>
          <label htmlFor={ids.multi} className="flex cursor-pointer items-center gap-2">
            <input id={ids.multi} type="checkbox" checked={multiple} onChange={(e) => setMultiple(e.target.checked)} className="size-4 accent-primary" />
            여러 리뷰를 한 번에 (빈 줄로 구분)
          </label>
        </div>
        {inputError && (
          <p id={ids.err} role="alert" className="text-caption font-medium text-danger">
            {inputError}
          </p>
        )}
        <Button type="submit" size="lg" className="w-full sm:w-auto" disabled={m.isPending}>
          {m.isPending ? <Loader2 aria-hidden className="size-5 animate-spin" /> : <Sparkles aria-hidden className="size-5" />}
          {m.isPending ? "판별 중…" : "판별하기"}
        </Button>
        <p className="text-caption text-muted">입력한 글은 판별에만 쓰고 서버에 저장하지 않아요.</p>
      </form>

      {apiError && (
        <Notice tone="danger" role="alert" title="판별하지 못했어요">
          {apiError}
        </Notice>
      )}

      {m.data && !m.isPending && <Results data={m.data} texts={submitted} />}
    </div>
  );
}

function Results({ data, texts }: { data: DetectResult; texts: string[] }) {
  const counts = data.results.reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.label]: (acc[r.label] ?? 0) + 1 }), {});
  return (
    <section aria-labelledby="check-results" className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="check-results" className="text-h2">
          판별 결과
        </h2>
        {data.results.length > 1 && (
          <p className="text-caption text-muted">
            AI 추정 {counts.ai ?? 0} · 사람 추정 {counts.human ?? 0} · 판단 보류 {counts.uncertain ?? 0}
          </p>
        )}
      </div>
      {(data.model.note || data.model.is_dummy) && (
        <Notice tone="warning" title="예시 판정이에요">
          {data.model.note ?? "서버가 개발용 가짜 판별기(DETECTOR_MODE=dummy)로 켜져 있어요. 실제 AI 판별 결과가 아니에요."}
        </Notice>
      )}
      <ol className="space-y-4">
        {data.results.map((r) => (
          <ResultCard key={r.index} r={r} text={texts[r.index] ?? ""} numbered={data.results.length > 1} />
        ))}
      </ol>
      <p className="text-caption text-muted">
        판정은 확률적 추정이에요. 이 결과만으로 특정 리뷰나 작성자를 단정하지 마세요.
        {data.model.version && <span className="ml-1">· 모델 {data.model.version}</span>}
      </p>
    </section>
  );
}

function ResultCard({ r, text, numbered }: { r: DetectResult["results"][number]; text: string; numbered: boolean }) {
  const v = VERDICT[r.label];
  const pct = Math.round(r.p_ai * 100);
  const th = r.thresholds;
  return (
    <li className="rounded-xl border border-border bg-surface p-5 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        {numbered && <span className="text-caption font-semibold text-muted">#{r.index + 1}</span>}
        <Badge tone={v.tone}>{v.badge}</Badge>
        <span className="text-caption text-muted">{r.len_chars.toLocaleString()}자</span>
      </div>
      <p className="mt-3 text-h3">{v.title}</p>
      <blockquote className="mt-3 line-clamp-3 border-l-2 border-border-strong pl-3 text-caption text-muted">{text}</blockquote>

      <div className="mt-5">
        <div className="flex items-baseline justify-between text-caption">
          <span className="font-medium">AI가 썼을 확률</span>
          <span className="text-h3 tabular-nums">{pct}%</span>
        </div>
        <div
          role="meter"
          aria-label="AI가 썼을 확률"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-valuetext={`${pct}%`}
          className="relative mt-2 h-3 rounded-full bg-subtle"
        >
          <div className={cn("h-3 rounded-full", v.bar)} style={{ width: `${Math.max(2, pct)}%` }} />
          {th && (
            <>
              <span aria-hidden className="absolute -top-1 h-5 w-0.5 bg-human" style={{ left: `${th.T_HUMAN * 100}%` }} />
              <span aria-hidden className="absolute -top-1 h-5 w-0.5 bg-ai" style={{ left: `${th.T_AI * 100}%` }} />
            </>
          )}
        </div>
        {th && (
          <p className="mt-2 text-caption text-muted">
            {Math.round(th.T_HUMAN * 100)}% 이하면 사람, {Math.round(th.T_AI * 100)}%를 넘으면 AI로 판정해요. 그 사이는 판단 보류예요.
          </p>
        )}
      </div>

      <p className="mt-4 text-caption md:text-body">
        {r.too_short ? "글이 짧아(20자 미만) 판단할 정보가 부족해요. 조금 더 긴 리뷰로 확인해 보세요." : v.body}
      </p>
    </li>
  );
}
