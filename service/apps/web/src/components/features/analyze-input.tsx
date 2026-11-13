"use client";

import { ImagePlus, Link2, Loader2, Search, X } from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DEMO_EXAMPLES } from "@/demo/examples";
import { cn } from "@/lib/cn";
import { isDemoMode } from "@/lib/site";
import { useStartAnalysis } from "@/lib/use-start-analysis";

type Tab = "url" | "query" | "image";
const MAX_IMAGE_MB = 10;

export function AnalyzeInput({ size = "lg", autoFocus = false }: { size?: "lg" | "md"; autoFocus?: boolean }) {
  const [tab, setTab] = useState<Tab>("url");
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { state, error, submit, setError } = useStartAnalysis();
  const errId = useId();

  const pickFile = useCallback(
    (f: File | null | undefined) => {
      if (!f) return;
      if (!f.type.startsWith("image/")) return setError("이미지 파일(PNG, JPG, WEBP)만 올릴 수 있어요.");
      if (f.size > MAX_IMAGE_MB * 1024 * 1024) return setError(`이미지는 ${MAX_IMAGE_MB}MB 이하만 올릴 수 있어요.`);
      setError(null);
      setFile(f);
      setTab("image");
    },
    [setError],
  );

  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  // 캡처 이미지 붙여넣기(Ctrl/⌘+V) 지원
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = Array.from(e.clipboardData?.items ?? []).find((i) => i.type.startsWith("image/"));
      if (item) {
        e.preventDefault();
        pickFile(item.getAsFile());
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [pickFile]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (state.busy) return;
    if (tab === "url") {
      if (!url.trim()) return setError("쿠팡 상품 링크를 붙여 넣어 주세요.");
      void submit({ url: url.trim() });
    } else if (tab === "query") {
      if (query.trim().length < 2) return setError("상품명을 두 글자 이상 입력해 주세요.");
      void submit({ query: query.trim() });
    } else {
      if (!file) return setError("이미지를 올리거나 붙여 넣어 주세요.");
      void submit({ image: file });
    }
  };

  const inputCls = cn(
    "w-full rounded border border-border-strong bg-surface px-4 text-body text-text placeholder:text-muted/80 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20",
    size === "lg" ? "h-14" : "h-12",
  );
  const describedBy = error ? errId : undefined;

  return (
    <form onSubmit={onSubmit} className="w-full" aria-busy={state.busy} noValidate>
      <Tabs value={tab} onValueChange={(v) => { setTab(v as Tab); setError(null); }}>
        <TabsList aria-label="입력 방법">
          <TabsTrigger value="url"><Link2 aria-hidden className="size-4" />링크</TabsTrigger>
          <TabsTrigger value="query"><Search aria-hidden className="size-4" />상품명</TabsTrigger>
          <TabsTrigger value="image"><ImagePlus aria-hidden className="size-4" />이미지</TabsTrigger>
        </TabsList>

        <div className="mt-4">
          <TabsContent value="url">
            <label htmlFor="input-url" className="sr-only">쿠팡 상품 링크</label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input id="input-url" name="url" type="url" inputMode="url" autoComplete="off" autoFocus={autoFocus}
                placeholder="쿠팡 상품 링크를 붙여 넣어 주세요" value={url} onChange={(e) => setUrl(e.target.value)}
                aria-invalid={!!error} aria-describedby={describedBy} className={inputCls} />
              <SubmitButton busy={state.busy} size={size} />
            </div>
            <p className="mt-2 text-caption text-muted">PC·모바일 주소와 공유하기 링크 모두 넣을 수 있어요.</p>
          </TabsContent>

          <TabsContent value="query">
            <label htmlFor="input-query" className="sr-only">상품명</label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input id="input-query" name="query" type="search" autoComplete="off" placeholder="예: 브랜드 + 상품명 + 용량"
                value={query} onChange={(e) => setQuery(e.target.value)} aria-invalid={!!error} aria-describedby={describedBy} className={inputCls} />
              <SubmitButton busy={state.busy} size={size} label="상품 찾기" />
            </div>
            <p className="mt-2 text-caption text-muted">모델명이나 용량을 함께 쓰면 더 정확하게 찾아요.</p>
          </TabsContent>

          <TabsContent value="image">
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); pickFile(e.dataTransfer.files?.[0]); }}
              className={cn("flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors",
                dragging ? "border-primary bg-primary-soft" : "border-border-strong bg-subtle")}
            >
              {preview && file ? (
                <div className="flex w-full flex-col items-center gap-3 sm:flex-row sm:justify-center">
                  <Image src={preview} alt="올린 캡처 이미지 미리보기" width={160} height={120} unoptimized className="h-28 w-auto rounded border border-border object-contain" />
                  <div className="text-left">
                    <p className="max-w-64 truncate text-caption font-medium">{file.name}</p>
                    <button type="button" onClick={() => setFile(null)} className="mt-1 inline-flex items-center gap-1 text-caption text-muted hover:text-text">
                      <X aria-hidden className="size-4" />다른 이미지 고르기
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <ImagePlus aria-hidden className="size-8 text-muted" />
                  <p className="text-body font-medium">캡처 이미지를 끌어다 놓거나 붙여 넣으세요</p>
                  <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>파일 고르기</Button>
                </>
              )}
              <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" tabIndex={-1}
                aria-label="캡처 이미지 파일" onChange={(e) => pickFile(e.target.files?.[0])} />
            </div>
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-caption text-muted">올린 이미지는 상품명을 읽는 데만 쓰고 저장하지 않아요.</p>
              <SubmitButton busy={state.busy} size="md" label="이미지로 찾기" />
            </div>
          </TabsContent>
        </div>
      </Tabs>

      <div aria-live="polite" className="min-h-6">
        {state.busy && <p className="mt-3 text-caption text-muted">{state.label}…</p>}
        {error && <p id={errId} role="alert" className="mt-3 text-caption font-medium text-danger md:text-body">{error}</p>}
      </div>

      {isDemoMode && (
        <div className="mt-4">
          <p className="text-caption text-muted">발표용 예시 상품</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {DEMO_EXAMPLES.map((ex) => (
              <li key={ex.key}>
                <button type="button" className="rounded-full border border-border bg-surface px-3 py-1 text-caption hover:border-primary hover:text-primary"
                  onClick={() => { setTab("url"); setUrl(ex.input_examples.url ?? ""); setQuery(ex.input_examples.query ?? ""); setError(null); }}>
                  {ex.result.product.name}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </form>
  );
}

function SubmitButton({ busy, size, label = "분석하기" }: { busy: boolean; size: "lg" | "md"; label?: string }) {
  return (
    <Button type="submit" size={size} disabled={busy} className="shrink-0 sm:min-w-32">
      {busy ? <Loader2 aria-hidden className="size-5 animate-spin" /> : null}
      {busy ? "확인 중" : label}
    </Button>
  );
}
