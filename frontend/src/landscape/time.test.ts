import { afterEach, describe, expect, it } from "vitest";
import { formatTime, fromInputValue, setTimeDisplay, toInputValue } from "./ui";

describe("times in UTC or local time", () => {
  afterEach(() => setTimeDisplay("browser"));

  it("shows UTC with a marker when chosen", () => {
    setTimeDisplay("utc");
    expect(formatTime("2026-11-22T15:15:00Z", "de")).toBe("22.11.26, 15:15 UTC");
    expect(toInputValue("2026-11-22T15:15:00Z")).toBe("2026-11-22T15:15");
    expect(fromInputValue("2026-11-22T15:15")).toBe("2026-11-22T15:15:00.000Z");
  });

  it("uses the browser's local time otherwise", () => {
    setTimeDisplay("browser");
    const local = new Date("2026-11-22T15:15:00Z");
    expect(formatTime("2026-11-22T15:15:00Z", "de")).not.toContain("UTC");
    expect(fromInputValue(toInputValue(local.toISOString()))).toBe("2026-11-22T15:15:00.000Z");
  });
});
