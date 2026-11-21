import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { readBoot } from "../lib/boot";
import { makeTranslate } from "../lib/i18n";
import { AppContext } from "../landscape/ui";
import "@xyflow/react/dist/style.css";
import "../landscape/landscape.css";
import "../activity/activity.css";
import "./templates.css";
import { TemplatesPage } from "./TemplatesPage";

const boot = readBoot();
const queries = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 5_000, refetchOnWindowFocus: false } } });
const root = document.getElementById("oslo-app");
if (root) {
  root.textContent = "";
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queries}>
        <AppContext.Provider
          value={{ t: makeTranslate(boot.texts), role: boot.user.role, language: boot.language, timezone: boot.timezone }}
        >
          <TemplatesPage />
        </AppContext.Provider>
      </QueryClientProvider>
    </StrictMode>,
  );
}
