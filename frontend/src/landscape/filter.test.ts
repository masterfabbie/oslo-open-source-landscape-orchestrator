import { describe, expect, it } from "vitest";
import { SNAPSHOT } from "./fixtures";
import {
  HOST_FILTER_KEYS,
  SYSTEM_FILTER_KEYS,
  emptyHostFilter,
  emptySystemFilter,
  filterHosts,
  filterSystems,
  readFilter,
  tagOptions,
  writeFilter,
} from "./filter";

const shown = (f: Partial<ReturnType<typeof emptySystemFilter>>) =>
  new Set(filterSystems(SNAPSHOT.systems, { ...emptySystemFilter(), ...f }).map((r) => r.system.name));

describe("system filters (same cases as the server filters before)", () => {
  it("matches like before", () => {
    expect(shown({})).toEqual(new Set(["DEV", "HDV"]));
    expect(shown({ q: "d" })).toEqual(new Set(["DEV", "HDV"]));
    expect(shown({ q: "hd" })).toEqual(new Set(["HDV"]));
    expect(shown({ q: "sapapp" })).toEqual(new Set(["DEV"]));
    expect(shown({ q: "DEV/00" })).toEqual(new Set(["DEV"]));
    expect(shown({ pool: ["1"] })).toEqual(new Set(["DEV"]));
    expect(shown({ pool: ["1", "none"] })).toEqual(new Set(["DEV", "HDV"]));
    expect(shown({ tag: ["sla"] })).toEqual(new Set(["DEV", "HDV"]));
    expect(shown({ tag: ["sla=2"] })).toEqual(new Set(["HDV"]));
    expect(shown({ tag: ["dev", "sla=2"] })).toEqual(new Set(["DEV", "HDV"]));
    expect(shown({ hosttag: ["db"] })).toEqual(new Set(["HDV"]));
    expect(shown({ type: ["hana"] })).toEqual(new Set(["HDV"]));
    expect(shown({ type: ["scs", "hana"] })).toEqual(new Set(["DEV", "HDV"]));
    expect(shown({ status: ["GRAY"] })).toEqual(new Set(["DEV", "HDV"]));
    expect(shown({ status: ["GREEN"] })).toEqual(new Set());
    expect(shown({ tag: ["sla"], pool: ["1"] })).toEqual(new Set(["DEV"])); // all must match
  });

  it("shows only the instances of the chosen type", () => {
    const [row] = filterSystems(SNAPSHOT.systems, { ...emptySystemFilter(), type: ["abap"] });
    expect(row.instances.map((i) => i.label)).toEqual(["DEV/00"]);
  });
});

describe("host filters", () => {
  const names = (f: Partial<ReturnType<typeof emptyHostFilter>>) =>
    filterHosts(SNAPSHOT.hosts, { ...emptyHostFilter(), ...f }).map((h) => h.name);
  it("filters by tag, search, reach and agent", () => {
    expect(names({ htag: ["db"] })).toEqual(["sapdb1"]);
    expect(names({ q: "app" })).toEqual(["sapapp1"]);
    expect(names({ reach: ["UNKNOWN"] })).toEqual(["sapdb1"]);
    expect(names({ agent: ["7.22 PL72"] })).toEqual(["sapapp1"]);
  });
  it("filters by pool and stage", () => {
    expect(names({ hpool: ["1"] })).toEqual(["sapapp1"]);
    expect(names({ hpool: ["none"] })).toEqual(["sapdb1"]);
    expect(names({ hstage: ["development", "none"] })).toEqual(["sapapp1", "sapdb1"]);
    expect(names({ hstage: ["production"] })).toEqual([]);
  });
});

describe("address", () => {
  it("round-trips the filters", () => {
    const f = { ...emptySystemFilter(), q: "x", status: ["RED"], pool: ["1", "none"] };
    const params = writeFilter(new URLSearchParams("tab=systems"), f, SYSTEM_FILTER_KEYS);
    expect(params.toString()).toBe("tab=systems&q=x&status=RED&pool=1&pool=none");
    expect(readFilter(params, emptySystemFilter(), SYSTEM_FILTER_KEYS)).toEqual(f);
    const h = writeFilter(params, { ...emptyHostFilter(), q: "db" }, HOST_FILTER_KEYS, "hq");
    expect(h.get("hq")).toBe("db");
    expect(h.get("q")).toBe("x"); // the host search does not touch the system search
  });

  it("offers keys and key=value tags", () => {
    expect(tagOptions(SNAPSHOT.systems)).toEqual(["dev", "sla", "sla=1", "sla=2"]);
  });
});
