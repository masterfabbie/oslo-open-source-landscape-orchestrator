// Search field and filter chips. Each chip opens a small list to tick values.

import { useEffect, useRef } from "react";
import type { Snapshot } from "../lib/types";
import { type HostFilter, type SystemFilter, tagOptions } from "./filter";
import { useApp } from "./ui";

type Option = { value: string; label: string };

interface Props {
  kind: "systems" | "hosts";
  filter: SystemFilter | HostFilter;
  onChange: (filter: SystemFilter | HostFilter) => void;
  snapshot: Snapshot;
  summary: string;
}

const STATUS = ["GREEN", "YELLOW", "RED", "GRAY", "UNKNOWN"];
const STAGES = ["sandbox", "development", "quality", "preprod", "production"];
const TYPES = ["hana", "scs", "ers", "abap", "java", "dual", "agent"];

export function FilterBar({ kind, filter, onChange, snapshot, summary }: Props) {
  const { t } = useApp();
  const search = useRef<HTMLInputElement>(null);

  // "/" focuses the search field, as in many tools.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) {
        event.preventDefault();
        search.current?.focus();
      }
    };
    // A click outside closes the open filter lists.
    const onClick = (event: MouseEvent) => {
      document.querySelectorAll<HTMLDetailsElement>("details.oslo-chip[open]").forEach((chip) => {
        if (!chip.contains(event.target as Node)) chip.open = false;
      });
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("click", onClick);
    };
  }, []);

  const chips: { key: string; label: string; options: Option[] }[] =
    kind === "systems"
      ? [
          { key: "status", label: t("filter.status"), options: STATUS.map((v) => ({ value: v, label: t(`status.${v}`) })) },
          {
            key: "pool",
            label: t("filter.pool"),
            options: [
              ...snapshot.pools.map((p) => ({ value: String(p.id), label: p.name })),
              { value: "none", label: t("pool.none") },
            ],
          },
          { key: "type", label: t("filter.type"), options: TYPES.map((v) => ({ value: v, label: t(`itype.${v}`) })) },
          { key: "tag", label: t("filter.tag"), options: tagOptions(snapshot.systems).map((v) => ({ value: v, label: v })) },
          { key: "hosttag", label: t("filter.hosttag"), options: tagOptions(snapshot.hosts).map((v) => ({ value: v, label: v })) },
        ]
      : [
          { key: "reach", label: t("filter.reach"), options: ["GREEN", "RED", "UNKNOWN"].map((v) => ({ value: v, label: t(`reach.${v}`) })) },
          {
            key: "agent",
            label: t("filter.agent"),
            options: [...new Set(snapshot.hosts.map((h) => h.hostagent_version).filter(Boolean) as string[])]
              .sort()
              .map((v) => ({ value: v, label: v })),
          },
          { key: "htag", label: t("filter.tag"), options: tagOptions(snapshot.hosts).map((v) => ({ value: v, label: v })) },
          {
            key: "hpool",
            label: t("filter.pool"),
            options: [...snapshot.pools.map((p) => ({ value: String(p.id), label: p.name })), { value: "none", label: t("pool.none") }],
          },
          {
            key: "hstage",
            label: t("filter.stage"),
            options: [...STAGES.map((s) => ({ value: s, label: t(`stage.${s}`) })), { value: "none", label: t("stage.none") }],
          },
        ];

  const values = filter as unknown as Record<string, string[]> & { q: string };
  const active = chips.some((c) => values[c.key].length) || filter.q;
  const set = (key: string, list: string[]) => onChange({ ...filter, [key]: list } as SystemFilter | HostFilter);

  return (
    <div className="oslo-filters">
      <label className="oslo-search">
        <span className="oslo-visually-hidden">{t("ui.search")}</span>
        <input
          ref={search}
          type="search"
          value={filter.q}
          placeholder={t(kind === "systems" ? "ui.search_systems" : "ui.search_hosts")}
          onChange={(e) => onChange({ ...filter, q: e.target.value })}
        />
      </label>
      {chips.map((chip) => {
        const chosen = values[chip.key];
        const names = chip.options.filter((o) => chosen.includes(o.value)).map((o) => o.label);
        return (
          <details key={chip.key} className={`oslo-chip${chosen.length ? " oslo-chip-on" : ""}`}>
            <summary>
              {chip.label}
              {names.length ? `: ${names.join(", ")}` : ""}
            </summary>
            <div className="oslo-chip-menu">
              {chip.options.length ? (
                chip.options.map((option) => (
                  <label key={option.value}>
                    <input
                      type="checkbox"
                      checked={chosen.includes(option.value)}
                      onChange={(e) =>
                        set(chip.key, e.target.checked ? [...chosen, option.value] : chosen.filter((v) => v !== option.value))
                      }
                    />
                    {option.label}
                  </label>
                ))
              ) : (
                <span className="oslo-muted">{t("filter.no_values")}</span>
              )}
            </div>
          </details>
        );
      })}
      {active && (
        <button
          type="button"
          className="link"
          onClick={() => onChange(Object.fromEntries(Object.entries(filter).map(([k, v]) => [k, Array.isArray(v) ? [] : ""])) as unknown as SystemFilter)}
        >
          {t("filter.reset")}
        </button>
      )}
      <span className="oslo-summary">{summary}</span>
    </div>
  );
}
