// Small shared pieces: translation context, status badges, the event stream.

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect } from "react";
import type { Translate } from "../lib/i18n";

export interface AppInfo {
  t: Translate;
  role: string;
  language: string;
  /** Time zone of the server for times of day in schedules (OSLO_TIMEZONE). */
  timezone?: string;
}

export const AppContext = createContext<AppInfo>({ t: (k) => k, role: "viewer", language: "en" });

export const useApp = () => useContext(AppContext);

const BADGE: Record<string, string> = {
  GREEN: "green",
  YELLOW: "yellow",
  RED: "red",
  GRAY: "gray",
  UNKNOWN: "unknown",
};

export function StatusBadge({ status, prefix = "status" }: { status: string; prefix?: string }) {
  const { t } = useApp();
  return <span className={`oslo-badge oslo-badge-${BADGE[status] ?? "unknown"}`}>{t(`${prefix}.${status}`)}</span>;
}

export function StatusDot({ status, label }: { status: string; label?: string }) {
  return <span className={`oslo-dot oslo-dot-${BADGE[status] ?? "unknown"}`} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true} />;
}

export function formatTime(value: string | null, language: string, seconds = false): string {
  if (!value) return "";
  const date = new Date(value);
  return date.toLocaleString(language === "de" ? "de-DE" : "en-GB", {
    dateStyle: "short",
    timeStyle: seconds ? "medium" : "short",
  });
}

/** Reloads what the page shows when the server reports a change (``queryKey``: the
 * queries to reload, by default the landscape and its activity lists). */
export function useLiveUpdates(queryKey: unknown[] = ["landscape"]): void {
  const queries = useQueryClient();
  const key = JSON.stringify(queryKey);
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource("/api/events");
    const reload = () => {
      void queries.invalidateQueries({ queryKey: JSON.parse(key) });
    };
    source.addEventListener("change", reload);
    return () => source.close();
  }, [queries, key]);
}
