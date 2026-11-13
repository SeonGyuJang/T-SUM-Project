"use client";

import { Check, Link2, Printer } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";

export function ShareActions() {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("이 주소를 복사해 주세요", window.location.href);
    }
  };
  return (
    <div className="no-print flex flex-wrap gap-3">
      <Button variant="secondary" onClick={copy}>
        {copied ? <Check aria-hidden className="size-5 text-success" /> : <Link2 aria-hidden className="size-5" />}
        {copied ? "링크를 복사했어요" : "결과 링크 복사"}
      </Button>
      <Button variant="secondary" onClick={() => window.print()}>
        <Printer aria-hidden className="size-5" />인쇄·PDF 저장
      </Button>
      <span aria-live="polite" className="sr-only">{copied ? "결과 링크를 복사했어요" : ""}</span>
    </div>
  );
}
