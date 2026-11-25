// Ctrl+K: find systems, hosts and instances, run an operation on the selection or jump to
// another page. Arrow keys choose, Enter runs, Escape closes.

import { useEffect, useMemo, useRef, useState } from "react";
import { categoryPath } from "../lib/categories";
import { hasRole } from "../lib/i18n";
import type { InstanceRow, OperationDef, Snapshot } from "../lib/types";
import { type Selection, operationLabel, operationsFor } from "./selection";
import { useApp } from "./ui";

interface Props {
  open: boolean;
  onClose: () => void;
  snapshot: Snapshot;
  selection: Selection;
  instances: Map<number, InstanceRow>;
  onRun: (op: OperationDef, selection: Selection) => void;
  onOpenSystem: (id: number) => void;
  onOpenHost: (id: number) => void;
}

interface Entry {
  id: string;
  group: string;
  label: string;
  hint?: string;
  run: () => void;
}

const MAX_PER_GROUP = 8;

export function CommandPalette(props: Props) {
  const { open, onClose, snapshot, selection, instances, onRun, onOpenSystem, onOpenHost } = props;
  const { t, role, language } = useApp();
  const dialog = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) {
      setQuery("");
      setActive(0);
      element.showModal?.();
    } else if (!open && element.open) {
      element.close();
    }
  }, [open]);

  const entries = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const fits = (text: string) => words.every((w) => text.toLowerCase().includes(w));
    const result: Entry[] = [];
    const add = (list: Entry[]) => result.push(...list.filter((e) => fits(`${e.label} ${e.hint ?? ""}`)).slice(0, MAX_PER_GROUP));

    if (selection.ids.length) {
      add(
        operationsFor(snapshot.operations, selection, instances).map((op) => ({
          id: `op-${op.key}`,
          group: t("ui.palette_operations"),
          label: operationLabel(op, selection.kind, t, language),
          hint: [categoryPath(op.category ?? "", t), t(`ui.selected_${selection.kind.toLowerCase()}`, { count: selection.ids.length })]
            .filter(Boolean)
            .join(" · "),
          run: () => {
            if (!op.danger || window.confirm(t("op.confirm"))) onRun(op, selection);
          },
        })),
      );
    }
    add(
      snapshot.systems.map((s) => ({
        id: `system-${s.id}`,
        group: t("tab.systems"),
        label: s.name,
        hint: [s.description, ...s.instances.map((i) => i.label)].filter(Boolean).join(" "),
        run: () => onOpenSystem(s.id),
      })),
    );
    add(
      snapshot.hosts.map((h) => ({
        id: `host-${h.id}`,
        group: t("tab.hosts"),
        label: h.name,
        hint: h.address,
        run: () => onOpenHost(h.id),
      })),
    );
    const pages: [string, string, string][] = [
      ["/", "nav.overview", "viewer"],
      ["/activities", "nav.activities", "viewer"],
      ["/configuration", "nav.configuration", "configurator"],
      ["/operations", "nav.operations", "admin"],
      ["/administration", "nav.administration", "admin"],
      ["/account", "ui.account", "viewer"],
    ];
    add(
      pages
        .filter(([, , needed]) => hasRole(role, needed))
        .map(([href, key]) => ({
          id: `page-${href}`,
          group: t("ui.palette_pages"),
          label: t(key),
          run: () => window.location.assign(href),
        })),
    );
    return result;
  }, [query, snapshot, selection, instances, t, role, onRun, onOpenSystem, onOpenHost]);

  const choose = (entry: Entry | undefined) => {
    if (!entry) return;
    onClose();
    entry.run();
  };

  let lastGroup = "";
  return (
    <dialog ref={dialog} className="oslo-palette" onClose={onClose} aria-label={t("ui.palette")}>
      <input
        autoFocus
        value={query}
        placeholder={t("ui.palette_placeholder")}
        aria-label={t("ui.palette_placeholder")}
        aria-controls="oslo-palette-list"
        aria-activedescendant={entries[active] ? `oslo-entry-${entries[active].id}` : undefined}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, entries.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            choose(entries[active]);
          }
        }}
      />
      <ul id="oslo-palette-list" role="listbox" className="oslo-palette-list">
        {entries.map((entry, index) => {
          const header = entry.group !== lastGroup ? entry.group : null;
          lastGroup = entry.group;
          return (
            <li key={entry.id} role="presentation">
              {header && <div className="oslo-palette-group">{header}</div>}
              <div
                id={`oslo-entry-${entry.id}`}
                role="option"
                aria-selected={index === active}
                className="oslo-palette-entry"
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(entry)}
              >
                <span>{entry.label}</span>
                {entry.hint && <span className="oslo-muted">{entry.hint}</span>}
              </div>
            </li>
          );
        })}
        {!entries.length && <li className="oslo-muted oslo-palette-empty">{t("filter.no_match")}</li>}
      </ul>
      <div className="oslo-palette-keys oslo-muted">{t("ui.palette_keys")}</div>
    </dialog>
  );
}
