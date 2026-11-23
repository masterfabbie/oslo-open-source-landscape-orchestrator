import { describe, expect, it } from "vitest";
import { bundleState } from "./bundle";

const at = "2026-11-23T10:00:00Z";

describe("bundleState", () => {
  it("compares a host with the active bundle", () => {
    expect(bundleState({ bundle_version: null, bundle_integrity: null, bundle_checked_at: null }, "1.0.0")).toBe("unknown");
    expect(bundleState({ bundle_version: "none", bundle_integrity: null, bundle_checked_at: at }, "1.0.0")).toBe("missing");
    expect(bundleState({ bundle_version: "1.0.0", bundle_integrity: "modified", bundle_checked_at: at }, "1.0.0")).toBe("modified");
    expect(bundleState({ bundle_version: "0.9.0", bundle_integrity: "ok", bundle_checked_at: at }, "1.0.0")).toBe("outdated");
    expect(bundleState({ bundle_version: "1.0.0", bundle_integrity: "ok", bundle_checked_at: at }, "1.0.0")).toBe("current");
    expect(bundleState({ bundle_version: "1.0.0", bundle_integrity: "ok", bundle_checked_at: at }, null)).toBe("installed");
  });
});
