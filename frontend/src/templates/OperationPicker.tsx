// Choose the operation of a template step: a search over all operations a step may use,
// with the user's favorites (star) and the 5 used most often (by all users) on top. Scales
// to many custom operations, unlike a list of building blocks. Arrow keys choose, Enter
// takes, Escape closes.

import { useEffect, useMemo, useRef, useState } from "react";
import type { OperationDef, TargetType } from "../lib/types";
import { useApp } from "../landscape/ui";

interface Props {
  operations: OperationDef[];
  top: string[];
  favorites: string[];
  onToggleFavorite: (key: string) => void;
  onPick: (operation: OperationDef) => void;
  onClose: () => void;
}

/** Name of an operation without a target type, e.g. "Stop" or "Copy kernel". */
export function operationName(op: OperationDef, t: (key: string) => string): string {
  if (op.custom) return op.name ?? op.key;
  return t(`op.${op.key}`);
}

/** The target type a new step of the operation runs on: a system if it can. */
export function preferredTarget(op: OperationDef): TargetType {
  return (["SYSTEM", "INSTANCE", "HOST"] as TargetType[]).find((x) => op.targets.includes(x)) ?? op.targets[0];
}

export function OperationPicker({ operations, top, favorites, onToggleFavorite, onPick, onClose }: Props) {
  const { t } = useApp();
  const dialog = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal?.();
  }, []);

  const groups = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const text = (op: OperationDef) => `${operationName(op, t)} ${op.key} ${op.description ?? ""}`.toLowerCase();
    const fits = (op: OperationDef) => words.every((w) => text(op).includes(w));
    const byKey = new Map(operations.map((op) => [op.key, op]));
    const pick = (keys: string[]) => keys.map((k) => byKey.get(k)).filter((op): op is OperationDef => !!op && fits(op));
    const sorted = [...operations].filter(fits).sort((a, b) => operationName(a, t).localeCompare(operationName(b, t)));
    const result: { title: string; items: OperationDef[] }[] = [];
    if (!words.length) {
      result.push({ title: t("tpl.favorites"), items: pick(favorites) });
      result.push({ title: t("tpl.most_used"), items: pick(top) });
    }
    result.push({ title: words.length ? t("tpl.found") : t("tpl.all_operations"), items: sorted });
    return result.filter((g) => g.items.length);
  }, [operations, top, favorites, query, t]);

  // One entry per row: an operation may be a favorite, among the most used and in the list.
  const flat = groups.flatMap((g) => g.items.map((op) => ({ group: g.title, op })));
  const choose = (op: OperationDef | undefined) => op && onPick(op);
  let row = -1;

  return (
    <dialog
      ref={dialog}
      className="oslo-palette oslo-picker"
      aria-label={t("tpl.pick_operation")}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === dialog.current) onClose();
      }}
    >
      <input
        autoFocus
        value={query}
        placeholder={t("tpl.search_operations")}
        aria-label={t("tpl.search_operations")}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, flat.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            choose(flat[active]?.op);
          }
        }}
      />
      <ul className="oslo-palette-list" role="listbox" aria-label={t("tpl.pick_operation")}>
        {!flat.length && <li className="oslo-palette-empty oslo-muted">{t("ui.palette_nothing")}</li>}
        {groups.map((group, g) => (
          <li key={group.title + g} role="presentation">
            <div className="oslo-palette-group">{group.title}</div>
            <ul className="oslo-picker-items" role="presentation">
              {group.items.map((op) => {
                row += 1;
                const index = row;
                const starred = favorites.includes(op.key);
                return (
                  <li
                    key={`${group.title}-${op.key}`}
                    role="option"
                    aria-selected={index === active}
                    className="oslo-palette-entry"
                    onMouseEnter={() => setActive(index)}
                    onClick={() => choose(op)}
                  >
                    <span>
                      <span className="oslo-strong">{operationName(op, t)}</span>
                      <span className="oslo-muted">
                        {" · "}
                        {op.targets.map((x) => t(`target.${x}`)).join(", ")}
                        {op.custom ? ` · ${t("tpl.kind_custom")}` : ""}
                        {op.standalone === false ? ` · ${t("tpl.template_only")}` : ""}
                      </span>
                    </span>
                    <button
                      type="button"
                      className={`oslo-star${starred ? " oslo-on" : ""}`}
                      aria-pressed={starred}
                      aria-label={t(starred ? "tpl.unfavorite" : "tpl.favorite")}
                      title={t(starred ? "tpl.unfavorite" : "tpl.favorite")}
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite(op.key);
                      }}
                    >
                      {starred ? "★" : "☆"}
                    </button>
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>
      <div className="oslo-palette-keys oslo-muted">{t("tpl.picker_keys")}</div>
    </dialog>
  );
}
