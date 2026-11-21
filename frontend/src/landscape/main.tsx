import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { readBoot } from "../lib/boot";
import { makeTranslate } from "../lib/i18n";
import { Landscape } from "./Landscape";
import { AppContext } from "./ui";
import "./landscape.css";

const boot = readBoot();
const queries = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: true, retry: 1, staleTime: 5_000 } },
});
const root = document.getElementById("oslo-app");
if (root) {
  root.textContent = "";
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queries}>
        <AppContext.Provider
          value={{ t: makeTranslate(boot.texts), role: boot.user.role, language: boot.language }}
        >
          <Landscape />
        </AppContext.Provider>
      </QueryClientProvider>
    </StrictMode>,
  );
}
