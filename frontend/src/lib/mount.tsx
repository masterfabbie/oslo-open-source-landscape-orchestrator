// Starts a React page: reads the start data, provides texts, role and queries, and renders
// into #oslo-app of app_page.html.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppContext } from "../landscape/ui";
import { type Boot, readBoot } from "./boot";
import { makeTranslate } from "./i18n";

export function mount(render: (boot: Boot & Record<string, unknown>) => ReactNode): void {
  const boot = readBoot() as Boot & Record<string, unknown>;
  const queries = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 2_000, refetchOnWindowFocus: false } } });
  const root = document.getElementById("oslo-app");
  if (!root) return;
  root.textContent = "";
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queries}>
        <AppContext.Provider value={{ t: makeTranslate(boot.texts), role: boot.user.role, language: boot.language, timezone: boot.timezone }}>
          {render(boot)}
        </AppContext.Provider>
      </QueryClientProvider>
    </StrictMode>,
  );
}
