import { describe, expect, it } from "vitest";
import { splitList } from "./Tls";

describe("splitList", () => {
  it("splits names by commas, spaces and semicolons", () => {
    expect(splitList(" oslo.example, oslo ;10.0.0.1  ")).toEqual(["oslo.example", "oslo", "10.0.0.1"]);
    expect(splitList("")).toEqual([]);
  });
});
