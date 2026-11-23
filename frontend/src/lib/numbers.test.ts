import { describe, expect, it } from "vitest";
import { activityNumber, formatDuration, stepNumber } from "./numbers";

describe("numbers", () => {
  it("numbers activities and steps from 100000 on", () => {
    expect(activityNumber(2)).toBe("A100002");
    expect(stepNumber(2)).toBe("O100002");
  });

  it("formats durations", () => {
    const start = "2026-11-23T10:00:00Z";
    expect(formatDuration(start, "2026-11-23T10:01:02Z")).toBe("1:02");
    expect(formatDuration(start, "2026-11-23T10:00:05Z")).toBe("0:05");
    expect(formatDuration(start, "2026-11-23T11:02:03Z")).toBe("1:02:03");
    expect(formatDuration(null, null)).toBe("");
    // Still running: up to now.
    expect(formatDuration(start, null, Date.parse("2026-11-23T10:00:30Z"))).toBe("0:30");
  });
});
