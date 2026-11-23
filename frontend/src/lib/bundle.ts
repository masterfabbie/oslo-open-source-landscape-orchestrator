// The OSLO operations on a host compared with the active bundle, like host_state in
// bundles.py on the server.

export interface BundleFields {
  bundle_version: string | null;
  bundle_integrity: string | null;
  bundle_checked_at: string | null;
}

export type BundleState = "unknown" | "missing" | "modified" | "outdated" | "current" | "installed";

export const NEEDS_UPDATE: BundleState[] = ["missing", "modified", "outdated"];

export function bundleState(host: BundleFields, active: string | null): BundleState {
  if (!host.bundle_checked_at) return "unknown";
  if (!host.bundle_version || host.bundle_version === "none") return "missing";
  if (host.bundle_integrity !== "ok") return "modified";
  if (!active) return "installed";
  return host.bundle_version === active ? "current" : "outdated";
}

export const BUNDLE_BADGE: Record<BundleState, string> = {
  unknown: "gray",
  missing: "red",
  modified: "yellow",
  outdated: "yellow",
  current: "green",
  installed: "gray",
};
