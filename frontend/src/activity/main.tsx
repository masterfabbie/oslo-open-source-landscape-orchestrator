import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { readBoot } from "../lib/boot";
import { makeTranslate } from "../lib/i18n";
import { AppContext } from "../landscape/ui";
import "../landscape/landscape.css";
import "./activity.css";
import { ActivityPage } from "./ActivityPage";

const boot = readBoot() as ReturnType<typeof readBoot> & { activity_id: number };
const queries = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 1_000 } } });
const root = document.getElementById("oslo-app");
if (root) {
  root.textContent = "";
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queries}>
        <AppContext.Provider value={{ t: makeTranslate(boot.texts), role: boot.user.role, language: boot.language }}>
          <ActivityPage id={boot.activity_id} />
        </AppContext.Provider>
      </QueryClientProvider>
    </StrictMode>,
  );
}
