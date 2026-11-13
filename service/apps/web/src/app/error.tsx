"use client";

import { useEffect } from "react";
import { Button, ButtonLink } from "@/components/ui/button";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="container-page section text-center">
      <p className="text-caption font-semibold text-danger">500</p>
      <h1 className="mt-2 text-h1">잠시 문제가 생겼어요</h1>
      <p className="mt-3 text-muted">화면을 불러오지 못했어요. 다시 시도하거나 홈으로 돌아가 주세요.</p>
      <div className="mt-8 flex justify-center gap-3">
        <Button onClick={reset}>다시 시도</Button>
        <ButtonLink href="/" variant="secondary">홈으로</ButtonLink>
      </div>
    </div>
  );
}
