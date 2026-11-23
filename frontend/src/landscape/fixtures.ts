// Test data shaped like /api/landscape for the simulated landscape: DEV (ABAP) and HDV.
import type { InstanceRow, OperationDef, Snapshot, SystemRow } from "../lib/types";

export const instance = (id: number, label: string, type: string, host: [number, string, string[]], role: InstanceRow["role"]): InstanceRow => ({
  id,
  label,
  sid: label.split("/")[0],
  number: label.split("/")[1],
  host: { id: host[0], name: host[1], tags: host[2] },
  hostname: host[1],
  role,
  type,
  agent: role === "agent",
  status: "GRAY",
  status_checked_at: null,
  start_priority: null,
  version: null,
  depends_on: [],
});

export const DEV: SystemRow = {
  id: 1,
  name: "DEV",
  description: null,
  status: "GRAY",
  pool: { id: 1, name: "xDV" },
  tags: ["dev", "sla=1"],
  depends_on: ["HDV"],
  activity: null,
  instances: [
    instance(1, "DEV/01", "scs", [1, "sapapp1", []], "central"),
    instance(2, "DEV/00", "abap", [1, "sapapp1", []], "application"),
  ],
};

export const HDV: SystemRow = {
  id: 2,
  name: "HDV",
  description: "HANA",
  status: "GRAY",
  pool: null,
  tags: ["sla=2"],
  depends_on: [],
  activity: null,
  instances: [instance(3, "HDV/02", "hana", [2, "sapdb1", ["db"]], "database")],
};

const op = (key: string, targets: OperationDef["targets"], extra: Partial<OperationDef> = {}): OperationDef => ({
  key,
  labels: Object.fromEntries(targets.map((t) => [t, t === "SYSTEM" ? `op.${key}_system` : `op.${key}`])),
  name: null,
  description: null,
  targets,
  mass: true,
  danger: false,
  custom: false,
  instance_types: [],
  parameters: [],
  ...extra,
});

export const OPERATIONS: OperationDef[] = [
  op("start", ["INSTANCE", "SYSTEM"]),
  op("stop", ["INSTANCE", "SYSTEM"], { danger: true }),
  op("discover", ["HOST"]),
  op("copy_kernel", ["INSTANCE"], {
    custom: true,
    name: "Copy kernel",
    instance_types: ["abap"],
    parameters: [{ name: "KRNLREL", label: "Release", type: "STRING", required: true, default: "793", pattern: null, help: null }],
  }),
  op("single", ["SYSTEM"], { custom: true, name: "Only one", mass: false }),
];

export const SNAPSHOT: Snapshot = {
  user: { name: "admin", role: "admin" },
  systems: [DEV, HDV],
  hosts: [
    { id: 1, name: "sapapp1", address: "127.0.0.1", reachable: true, hostagent_version: "7.22 PL72", os: "Linux", tags: [], last_discovery_at: null, last_error: null, instance_count: 2, activity: null },
    { id: 2, name: "sapdb1", address: "127.0.0.1", reachable: null, hostagent_version: "7.22 PL70", os: "Linux", tags: ["db"], last_discovery_at: null, last_error: null, instance_count: 1, activity: null },
  ],
  pools: [{ id: 1, name: "xDV" }],
  operations: OPERATIONS,
};
