import { describe, expect, it } from "vitest";
import { operationLabel } from "../landscape/selection";
import { MORE, bundleReadiness, categoryPath, filterMenu, groupOperations, operationChoices } from "./categories";
import type { HostRow, InstanceRow, OperationDef, SystemRow } from "./types";

function op(key: string, extra: Partial<OperationDef> = {}): OperationDef {
  return {
    key,
    labels: {},
    name: key,
    description: null,
    targets: ["INSTANCE"],
    mass: true,
    danger: false,
    custom: false,
    instance_types: [],
    parameters: [],
    category: "",
    ...extra,
  };
}

const t = (key: string) => ({ "cat.instance_agent": "Instanz-Agent", "cat.more": "Weitere" })[key] ?? key;

describe("categories", () => {
  const ops = [
    op("start"),
    op("stop"),
    op("register", { category: "cat.instance_agent" }),
    op("getkernel", { custom: true, category: "Automation/Kernel" }),
    op("plik", { custom: true, category: "Automation" }),
    op("waittimer", { custom: true }),
    op("hdb_only", { custom: true, category: "Automation", instance_types: ["hana"] }),
    op("single", { custom: true, category: "Automation", mass: false }),
    op("host_only", { custom: true, targets: ["HOST"] }),
  ];
  const instances = new Map<number, InstanceRow>([
    [1, { type: "abap" } as InstanceRow],
    [2, { type: "abap" } as InstanceRow],
  ]);

  it("keeps start and stop as buttons and groups the rest", () => {
    const grouped = groupOperations(operationChoices(ops, "INSTANCE", [1], instances));
    expect(grouped.main.map((c) => c.op.key)).toEqual(["start", "stop"]);
    expect(grouped.menus.map((m) => m.key)).toEqual(["cat.instance_agent", "Automation", MORE]);
    const automation = grouped.menus[1];
    expect(automation.items.map((c) => c.op.key)).toEqual(["plik", "hdb_only", "single"]);
    expect(automation.subs).toEqual([{ key: "Kernel", items: [expect.objectContaining({ reason: null })] }]);
    expect(grouped.menus[2].items.map((c) => c.op.key)).toEqual(["waittimer"]);
  });

  it("says why an operation cannot run instead of hiding it", () => {
    const choices = operationChoices(ops, "INSTANCE", [1, 2], instances, () => false);
    const reason = (key: string) => choices.find((c) => c.op.key === key)?.reason;
    expect(reason("hdb_only")).toBe("op.reason.instance_type");
    expect(reason("single")).toBe("op.reason.not_mass");
    expect(reason("plik")).toBeNull();
    expect(choices.some((c) => c.op.key === "host_only")).toBe(false);
    const bundled = operationChoices([op("restart_agent", { custom: true, bundle: true })], "INSTANCE", [1], instances, () => false);
    expect(bundled[0].reason).toBe("op.reason.bundle");
  });

  it("labels and filters", () => {
    expect(categoryPath("cat.instance_agent", t)).toBe("Instanz-Agent");
    expect(categoryPath("Automation/Kernel", t)).toBe("Automation › Kernel");
    const grouped = groupOperations(operationChoices(ops, "INSTANCE", [1], instances));
    const found = filterMenu(grouped.menus[1], "kern", (o) => o.key);
    expect(found.items).toEqual([]);
    expect(found.subs[0].items.map((c) => c.op.key)).toEqual(["getkernel"]);
  });

  it("knows where the OSLO operations are current", () => {
    const instance = (id: number, host: number, agent = false) => ({ id, host: { id: host }, agent }) as InstanceRow;
    const systems = [{ id: 7, instances: [instance(1, 10), instance(2, 11), instance(3, 12, true)] }] as SystemRow[];
    const hosts = [
      { id: 10, bundle_state: "current" },
      { id: 11, bundle_state: "outdated" },
      { id: 12, bundle_state: "missing" },
    ] as HostRow[];
    const ready = bundleReadiness(systems, hosts);
    expect(ready("INSTANCE", [1])).toBe(true);
    expect(ready("INSTANCE", [1, 2])).toBe(false);
    expect(ready("HOST", [10])).toBe(true);
    expect(ready("HOST", [12])).toBe(false);
    // Diagnostics agents do not count for a system.
    expect(ready("SYSTEM", [7])).toBe(false);
    hosts[1].bundle_state = "current";
    expect(bundleReadiness(systems, hosts)("SYSTEM", [7])).toBe(true);
  });

  it("names operations of the bundle in the user's language", () => {
    const bundled = op("oslo.restart_service", { custom: true, bundle: true, names: { en: "Restart", de: "Neu starten" } });
    expect(operationLabel(bundled, "INSTANCE", t, "de")).toBe("Neu starten");
    expect(operationLabel(bundled, "INSTANCE", t, "fr")).toBe("Restart");
    // An empty set of names does not hide the translation of built-in operations.
    expect(operationLabel(op("start", { names: {}, labels: { INSTANCE: "cat.more" } }), "INSTANCE", t)).toBe("Weitere");
  });
});
