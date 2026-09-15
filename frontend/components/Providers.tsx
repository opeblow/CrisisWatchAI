"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 15_000, refetchInterval: 30_000 },
        },
      })
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}