// The operations for a selection: start, stop and restart (discovery for hosts) as buttons,
// everything else in menus by category, with a second level as a flyout and a search field
// in each menu. Operations that do not fit the selection stay visible, greyed out, with the
// reason. Stopping operations need a second click on the same entry.

import { useEffect, useRef, useState } from "react";
import { type Choice, type Menu, categoryLabel, filterMenu, groupOperations, operationChoices } from "../lib/categories";
import type { InstanceRow, OperationDef, TargetType } from "../lib/types";
import { operationLabel } from "./selection";
import { useApp } from "./ui";

interface Props {
  kind: TargetType;
  ids: number[];
  operations: OperationDef[];
  instances: Map<number, InstanceRow>;
  bundleReady?: (ids: number[]) => boolean;
  onRun: (op: OperationDef) => void;
  // "up" in the bar at the bottom, "down" in the detail panel.
  direction: "up" | "down";
}

export function OperationMenus({ kind, ids, operations, instances, bundleReady, onRun, direction }: Props) {
  const { t, language } = useApp();
  const [armed, setArmed] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const key = ids.join(",");

  useEffect(() => {
    setArmed(null);
    setOpen(null);
  }, [key, kind]);
  useEffect(() => {
    if (!armed) return;
    const timer = window.setTimeout(() => setArmed(null), 4000);
    return () => window.clearTimeout(timer);
  }, [armed]);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(null);
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(null);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const grouped = groupOperations(operationChoices(operations, kind, ids, instances, bundleReady));
  const label = (op: OperationDef) => operationLabel(op, kind, t, language);
  const run = (choice: Choice) => {
    const { op } = choice;
    if (choice.reason) return;
    if (op.danger && armed !== op.key) {
      setArmed(op.key);
      return;
    }
    setArmed(null);
    setOpen(null);
    onRun(op);
  };
  const text = (choice: Choice) => {
    const name = label(choice.op);
    const ellipsis = choice.op.custom && (choice.op.parameters.length || choice.op.template) ? "…" : "";
    return armed === choice.op.key ? t("ui.confirm_operation", { operation: name }) : name + ellipsis;
  };

  if (!grouped.main.length && !grouped.menus.length) return <span className="oslo-muted">{t("ui.no_operations")}</span>;
  return (
    <div className={`oslo-opmenus oslo-opmenus-${direction}`} ref={root}>
      {grouped.main.map((choice) => (
        <button
          key={choice.op.key}
          type="button"
          disabled={Boolean(choice.reason)}
          title={choice.reason ? t(choice.reason) : undefined}
          className={`${choice.op.danger ? "oslo-danger" : ""}${armed === choice.op.key ? " oslo-armed" : ""}`}
          onClick={() => run(choice)}
        >
          {text(choice)}
        </button>
      ))}
      {grouped.menus.map((menu) => (
        <MenuButton
          key={menu.key}
          menu={menu}
          open={open === menu.key}
          onToggle={() => setOpen(open === menu.key ? null : menu.key)}
          label={label}
          text={text}
          armed={armed}
          run={run}
          direction={direction}
        />
      ))}
    </div>
  );
}

function MenuButton({
  menu,
  open,
  onToggle,
  label,
  text,
  armed,
  run,
  direction,
}: {
  menu: Menu;
  open: boolean;
  onToggle: () => void;
  label: (op: OperationDef) => string;
  text: (choice: Choice) => string;
  armed: string | null;
  run: (choice: Choice) => void;
  direction: "up" | "down";
}) {
  const { t } = useApp();
  const [search, setSearch] = useState("");
  const [sub, setSub] = useState<string | null>(null);
  // The flyout of a second level sits outside the scrolling menu (which would cut it off),
  // next to its row: the position is computed relative to the menu's wrapper.
  const wrapper = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ left: number; top?: number; bottom?: number } | null>(null);
  const openSub = (key: string, row: HTMLElement) => {
    const box = wrapper.current?.getBoundingClientRect();
    const rect = row.getBoundingClientRect();
    if (!box) return;
    setSub(key);
    const left = rect.right - box.left + 2;
    setPlace(direction === "up" ? { left, bottom: box.bottom - rect.bottom } : { left, top: rect.top - box.top });
  };
  useEffect(() => {
    if (!open) {
      setSearch("");
      setSub(null);
    }
  }, [open]);
  const shown = filterMenu(menu, search, (op) => `${label(op)} ${op.key}`);
  const searching = search.trim().length > 0;
  const entry = (choice: Choice) => (
    <button
      key={choice.op.key}
      type="button"
      role="menuitem"
      className={`oslo-opmenu-item${choice.op.danger ? " oslo-danger" : ""}${armed === choice.op.key ? " oslo-armed" : ""}`}
      aria-disabled={choice.reason ? true : undefined}
      title={choice.reason ? t(choice.reason) : choice.op.description ?? undefined}
      onClick={() => run(choice)}
    >
      <span>{text(choice)}</span>
      {choice.reason && <small>{t(choice.reason)}</small>}
    </button>
  );
  return (
    <div className="oslo-opmenu" ref={wrapper} onMouseLeave={() => setSub(null)}>
      <button type="button" aria-haspopup="menu" aria-expanded={open} className="oslo-opmenu-toggle" onClick={onToggle}>
        {categoryLabel(menu.key, t)} {direction === "up" ? "▴" : "▾"}
      </button>
      {open && (
        <div className="oslo-opmenu-panel" role="menu">
          <input
            type="search"
            className="oslo-opmenu-search"
            value={search}
            placeholder={t("ui.search")}
            aria-label={t("ui.search")}
            autoFocus
            onChange={(e) => setSearch(e.target.value)}
          />
          {shown.items.map((choice) => (
            <div key={choice.op.key} onMouseEnter={() => setSub(null)}>
              {entry(choice)}
            </div>
          ))}
          {shown.subs.map((s) =>
            searching ? (
              <div key={s.key} className="oslo-opmenu-group">
                <span className="oslo-opmenu-heading">{s.key}</span>
                {s.items.map(entry)}
              </div>
            ) : (
              <div key={s.key} className="oslo-opmenu-sub" onMouseEnter={(e) => openSub(s.key, e.currentTarget)}>
                <button
                  type="button"
                  role="menuitem"
                  aria-haspopup="menu"
                  aria-expanded={sub === s.key}
                  className="oslo-opmenu-item"
                  onClick={(e) => (sub === s.key ? setSub(null) : openSub(s.key, e.currentTarget.parentElement as HTMLElement))}
                >
                  <span>{s.key}</span>
                  <span aria-hidden="true">›</span>
                </button>
              </div>
            ),
          )}
          {!shown.items.length && !shown.subs.length && <span className="oslo-opmenu-empty">{t("ui.no_operations")}</span>}
        </div>
      )}
      {open && !searching && place && shown.subs.find((s) => s.key === sub) && (
        <div className="oslo-opmenu-panel oslo-opmenu-flyout" role="menu" style={place}>
          {shown.subs.find((s) => s.key === sub)?.items.map(entry)}
        </div>
      )}
    </div>
  );
}
