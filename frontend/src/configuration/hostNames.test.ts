import { describe, expect, it } from "vitest";
import { hostNames } from "./Hosts";

describe("hostNames", () => {
  it("splits at commas and drops empty names", () => {
    expect(hostNames("sapapp1, sapapp2 ,,sapdb1, ")).toEqual(["sapapp1", "sapapp2", "sapdb1"]);
  });
  it("keeps a single name", () => {
    expect(hostNames(" sapapp1 ")).toEqual(["sapapp1"]);
    expect(hostNames("")).toEqual([]);
  });
});
