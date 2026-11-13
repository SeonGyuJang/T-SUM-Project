import { AlertTriangle, Info, OctagonAlert } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

const tones = {
  info: { box: "border-border bg-subtle text-text", icon: Info, iconCls: "text-primary" },
  warning: { box: "border-warning/30 bg-warning-soft text-text", icon: AlertTriangle, iconCls: "text-warning" },
  danger: { box: "border-danger/30 bg-danger-soft text-text", icon: OctagonAlert, iconCls: "text-danger" },
} as const;

export function Notice({
  tone = "info",
  title,
  children,
  className,
  role,
}: {
  tone?: keyof typeof tones;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  role?: "status" | "alert";
}) {
  const t = tones[tone];
  const Icon = t.icon;
  return (
    <div role={role} className={cn("flex gap-3 rounded-lg border p-4", t.box, className)}>
      <Icon aria-hidden className={cn("mt-1 size-5 shrink-0", t.iconCls)} />
      <div className="min-w-0 space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="text-caption text-muted md:text-body">{children}</div>}
      </div>
    </div>
  );
}
