// Which operations fit a selection, and how they are started.

import { api } from "../lib/api";
import type { InstanceRow, OperationDef, TargetType } from "../lib/types";

export interface Selection {
  kind: TargetType;
  ids: number[];
}

export const PATHS: Record<TargetType, string> = {
  SYSTEM: "systems",
  INSTANCE: "instances",
  HOST: "hosts",
};

/** Operations that can run on every selected target: the target type fits, several
 * targets need a mass operation, and a custom operation limited to instance types must
 * fit each selected instance. */
export function operationsFor(
  operations: OperationDef[],
  selection: Selection,
  instances: Map<number, InstanceRow>,
): OperationDef[] {
  if (!selection.ids.length) return [];
  return operations.filter((op) => {
    if (!op.targets.includes(selection.kind)) return false;
    if (selection.ids.length > 1 && !op.mass) return false;
    if (selection.kind === "INSTANCE" && op.instance_types.length) {
      return selection.ids.every((id) => {
        const type = instances.get(id)?.type;
        return !!type && op.instance_types.includes(type);
      });
    }
    return true;
  });
}

export function operationLabel(
  op: OperationDef,
  kind: TargetType,
  t: (key: string) => string,
  language = "en",
): string {
  const named = op.names?.[language] ?? op.names?.en;
  if (named) return named;
  if (op.custom) return op.name ?? op.key;
  return t(op.labels[kind] ?? `op.${op.key}`);
}

export interface RunOptions {
  parameters?: Record<string, string | number | boolean>;
  parallel?: number;
  stopOnError?: boolean;
}

/** Starts the operation and returns the id of the activity to follow. One system or
 * instance runs directly; several targets, and host operations, run as a mass operation
 * (a discovery started directly would not be an activity). */
export async function runOperation(
  op: OperationDef,
  selection: Selection,
  options: RunOptions = {},
): Promise<number> {
  const [first] = selection.ids;
  const single = selection.ids.length === 1 && (op.custom || selection.kind !== "HOST");
  if (single) {
    const path = op.custom
      ? `/${PATHS[selection.kind]}/${first}/operations/${op.key}`
      : `/${PATHS[selection.kind]}/${first}/${op.key}`;
    const activity = await api<{ id: number }>(path, {
      method: "POST",
      body: op.custom ? { parameters: options.parameters ?? {} } : undefined,
    });
    return activity.id;
  }
  const activity = await api<{ id: number }>("/mass-operations", {
    method: "POST",
    body: {
      operation: op.key,
      target_type: selection.kind,
      target_ids: selection.ids,
      parallel: options.parallel ?? 5,
      stop_on_error: options.stopOnError ?? false,
      parameters: options.parameters ?? {},
    },
  });
  return activity.id;
}
