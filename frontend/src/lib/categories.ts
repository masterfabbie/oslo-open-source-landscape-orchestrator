// Operations grouped for the menus of the landscape: start, stop, restart (and discovery for
// hosts) stay buttons; everything else is listed in menus by category, at most two levels
// ("Automation/Kernel"). Built-in categories are translation keys ("cat.instance_agent");
// custom operations and templates without a category go to "More".

import type { InstanceRow, OperationDef, TargetType } from "./types";

export const MORE = "cat.more";

export interface Choice {
  op: OperationDef;
  // Why it cannot run on this selection; null: it can.
  reason: string | null;
}

export interface Menu {
  key: string; // first level, e.g. "Automation" or "cat.instance_agent"
  items: Choice[];
  subs: { key: string; items: Choice[] }[];
}

export interface Grouped {
  main: Choice[];
  menus: Menu[];
}

export function categoryLabel(part: string, t: (key: string) => string): string {
  return part.startsWith("cat.") ? t(part) : part;
}

/** "Automation/Kernel" → "Automation › Kernel", translated. */
export function categoryPath(category: string, t: (key: string) => string): string {
  return category
    ? category
        .split("/")
        .map((part) => categoryLabel(part, t))
        .join(" › ")
    : "";
}

function isMain(op: OperationDef): boolean {
  return !op.custom && !op.category;
}

/** Every operation for the kind of the selection, with the reason if it cannot run on all
 * selected targets (several targets but no mass operation, instance type does not fit, the
 * OSLO operations on a host are not current). */
export function operationChoices(
  operations: OperationDef[],
  kind: TargetType,
  ids: number[],
  instances: Map<number, InstanceRow>,
  bundleReady: (ids: number[]) => boolean = () => true,
): Choice[] {
  return operations
    .filter((op) => op.targets.includes(kind) && op.standalone !== false)
    .map((op) => {
      let reason: string | null = null;
      if (ids.length > 1 && !op.mass) reason = "op.reason.not_mass";
      else if (kind === "INSTANCE" && op.instance_types.length) {
        const fits = ids.every((id) => {
          const type = instances.get(id)?.type;
          return !!type && op.instance_types.includes(type);
        });
        if (!fits) reason = "op.reason.instance_type";
      }
      if (!reason && op.bundle && !bundleReady(ids)) reason = "op.reason.bundle";
      return { op, reason };
    });
}

function order(key: string): string {
  // Built-in categories first, "More" last, the others alphabetically.
  if (key === MORE) return "￿";
  return key.startsWith("cat.") ? ` ${key}` : key.toLowerCase();
}

export function groupOperations(choices: Choice[]): Grouped {
  const main: Choice[] = [];
  const menus = new Map<string, Menu>();
  for (const choice of choices) {
    if (isMain(choice.op)) {
      main.push(choice);
      continue;
    }
    const [first, second] = (choice.op.category || MORE).split("/");
    let menu = menus.get(first);
    if (!menu) {
      menu = { key: first, items: [], subs: [] };
      menus.set(first, menu);
    }
    if (second) {
      let sub = menu.subs.find((s) => s.key === second);
      if (!sub) {
        sub = { key: second, items: [] };
        menu.subs.push(sub);
      }
      sub.items.push(choice);
    } else {
      menu.items.push(choice);
    }
  }
  const sorted = [...menus.values()].sort((a, b) => order(a.key).localeCompare(order(b.key)));
  for (const menu of sorted) menu.subs.sort((a, b) => a.key.toLowerCase().localeCompare(b.key.toLowerCase()));
  return { main, menus: sorted };
}

/** The choices of a menu whose label, category or name contains the search text. */
export function filterMenu(menu: Menu, text: string, label: (op: OperationDef) => string): Menu {
  const words = text.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return menu;
  const fits = (c: Choice) => words.every((w) => label(c.op).toLowerCase().includes(w));
  return {
    ...menu,
    items: menu.items.filter(fits),
    subs: menu.subs.map((s) => ({ ...s, items: s.items.filter(fits) })).filter((s) => s.items.length),
  };
}
