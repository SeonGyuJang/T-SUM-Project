"use client";

import * as A from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Accordion({ items, className, defaultValue, headingLevel = 3 }: { items: { id: string; title: ReactNode; body: ReactNode }[]; className?: string; defaultValue?: string[]; headingLevel?: 2 | 3 }) {
  const H = headingLevel === 2 ? "h2" : "h3";
  return (
    <A.Root type="multiple" defaultValue={defaultValue} className={cn("divide-y divide-border rounded-xl border border-border bg-surface", className)}>
      {items.map((it) => (
        <A.Item key={it.id} value={it.id}>
          <A.Header asChild>
            <H>
              <A.Trigger className="group flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-body font-semibold hover:bg-subtle md:px-6">
                <span>{it.title}</span>
                <ChevronDown aria-hidden className="size-5 shrink-0 text-muted transition-transform group-data-[state=open]:rotate-180" />
              </A.Trigger>
            </H>
          </A.Header>
          <A.Content className="px-5 pb-5 text-body text-muted md:px-6">{it.body}</A.Content>
        </A.Item>
      ))}
    </A.Root>
  );
}
