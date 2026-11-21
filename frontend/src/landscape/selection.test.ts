import { afterEach, describe, expect, it, vi } from "vitest";
import type { InstanceRow } from "../lib/types";
import { DEV, HDV, OPERATIONS } from "./fixtures";
import { operationLabel, operationsFor, runOperation } from "./selection";

const instances = new Map<number, InstanceRow>([...DEV.instances, ...HDV.instances].map((i) => [i.id, i]));
const keys = (kind: "SYSTEM" | "INSTANCE" | "HOST", ids: number[]) =>
  operationsFor(OPERATIONS, { kind, ids }, instances).map((op) => op.key);

describe("operations for a selection", () => {
  it("fits target type, mass and instance types", () => {
    expect(keys("SYSTEM", [])).toEqual([]);
    expect(keys("SYSTEM", [1])).toEqual(["start", "stop", "single"]);
    expect(keys("SYSTEM", [1, 2])).toEqual(["start", "stop"]); // "single" allows no mass
    expect(keys("INSTANCE", [2])).toEqual(["start", "stop", "copy_kernel"]); // ABAP
    expect(keys("INSTANCE", [1, 2])).toEqual(["start", "stop"]); // DEV/01 is no ABAP server
    expect(keys("HOST", [1, 2])).toEqual(["discover"]);
  });

  it("labels built-in operations by target and custom ones by name", () => {
    const t = (key: string) => `[${key}]`;
    expect(operationLabel(OPERATIONS[0], "SYSTEM", t)).toBe("[op.start_system]");
    expect(operationLabel(OPERATIONS[0], "INSTANCE", t)).toBe("[op.start]");
    expect(operationLabel(OPERATIONS[3], "INSTANCE", t)).toBe("Copy kernel");
  });
});

describe("starting operations", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubFetch() {
    const calls: { url: string; init: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit) => {
        calls.push({ url, init });
        return new Response(JSON.stringify({ id: 7 }), { status: 202 });
      }),
    );
    return calls;
  }

  it("runs one target directly, with the header of the interface", async () => {
    const calls = stubFetch();
    expect(await runOperation(OPERATIONS[0], { kind: "SYSTEM", ids: [1] })).toBe(7);
    expect(calls[0].url).toBe("/api/systems/1/start");
    expect((calls[0].init.headers as Record<string, string>)["X-OSLO-Request"]).toBe("1");
  });

  it("runs custom operations with their parameters", async () => {
    const calls = stubFetch();
    await runOperation(OPERATIONS[3], { kind: "INSTANCE", ids: [2] }, { parameters: { KRNLREL: "793" } });
    expect(calls[0].url).toBe("/api/instances/2/operations/copy_kernel");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ parameters: { KRNLREL: "793" } });
  });

  it("runs several targets and host operations as a mass operation", async () => {
    const calls = stubFetch();
    await runOperation(OPERATIONS[1], { kind: "SYSTEM", ids: [1, 2] }, { parallel: 2, stopOnError: true });
    await runOperation(OPERATIONS[2], { kind: "HOST", ids: [1] });
    expect(calls.map((c) => c.url)).toEqual(["/api/mass-operations", "/api/mass-operations"]);
    expect(JSON.parse(String(calls[0].init.body))).toMatchObject({
      operation: "stop",
      target_type: "SYSTEM",
      target_ids: [1, 2],
      parallel: 2,
      stop_on_error: true,
    });
  });
});
