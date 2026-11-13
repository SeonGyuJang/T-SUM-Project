"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { apiMode, isDemoMode } from "@/lib/site";

const needsMsw = apiMode === "mock" && !isDemoMode;

export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } }),
  );
  const [ready, setReady] = useState(!needsMsw);

  useEffect(() => {
    if (!needsMsw) return;
    let active = true;
    import("@/mocks/browser")
      .then(({ worker }) => worker.start({ onUnhandledRequest: "bypass", quiet: true }))
      .finally(() => active && setReady(true));
    return () => {
      active = false;
    };
  }, []);

  return <QueryClientProvider client={client}>{ready ? children : null}</QueryClientProvider>;
}
