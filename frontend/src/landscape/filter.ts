// Filters of the landscape, as on the server before (filters.py): within one filter one
// match is enough, all filters must match. The values live in the address (?status=RED...).

import type { HostRow, InstanceRow, SystemRow } from "../lib/types";

export interface SystemFilter {
  q: string;
  status: string[];
  pool: string[]; // pool ids as text, "none" for systems without pool
  type: string[];
  tag: string[];
  hosttag: string[]; // tags of the hosts the instances run on
}

export interface HostFilter {
  q: string;
  reach: string[]; // GREEN, RED, UNKNOWN
  agent: string[];
  htag: string[];
  hpool: string[]; // pool ids as text, "none" for hosts without pool
  hstage: string[]; // stages, "none" for hosts without stage
}

export const SYSTEM_FILTER_KEYS = ["status", "pool", "type", "tag", "hosttag"] as const;
export const HOST_FILTER_KEYS = ["reach", "agent", "htag", "hpool", "hstage"] as const;

const contains = (value: string | null | undefined, q: string) =>
  !!value && value.toLowerCase().includes(q);

export function emptySystemFilter(): SystemFilter {
  return { q: "", status: [], pool: [], type: [], tag: [], hosttag: [] };
}

export function emptyHostFilter(): HostFilter {
  return { q: "", reach: [], agent: [], htag: [], hpool: [], hstage: [] };
}

function tagMatches(tags: string[], wanted: string[]): boolean {
  // "sla" matches "sla=1"; "sla=1" only itself.
  return wanted.some((w) => tags.some((t) => t === w || (!w.includes("=") && t.startsWith(`${w}=`))));
}

/** Systems that match, each with the instances to show. With the instance type filter
 * only matching instances are shown (and the system opens), as a basis for selecting them. */
export function filterSystems(
  systems: SystemRow[],
  f: SystemFilter,
): { system: SystemRow; instances: InstanceRow[] }[] {
  const q = f.q.trim().toLowerCase();
  const result: { system: SystemRow; instances: InstanceRow[] }[] = [];
  for (const system of systems) {
    if (f.status.length && !f.status.includes(system.status)) continue;
    if (f.pool.length && !f.pool.includes(system.pool ? String(system.pool.id) : "none")) continue;
    if (f.tag.length && !tagMatches(system.tags, f.tag)) continue;
    if (f.hosttag.length && !system.instances.some((i) => tagMatches(i.host.tags, f.hosttag))) continue;
    const instances = f.type.length
      ? system.instances.filter((i) => i.type !== null && f.type.includes(i.type))
      : system.instances;
    if (f.type.length && !instances.length) continue;
    if (q) {
      const hit =
        contains(system.name, q) ||
        contains(system.description, q) ||
        system.tags.some((t) => contains(t, q)) ||
        system.instances.some(
          (i) => contains(i.label, q) || contains(i.host.name, q) || contains(i.hostname, q),
        );
      if (!hit) continue;
    }
    result.push({ system, instances });
  }
  return result;
}

export function reachOf(host: HostRow): string {
  if (host.reachable === null) return "UNKNOWN";
  return host.reachable ? "GREEN" : "RED";
}

export function filterHosts(hosts: HostRow[], f: HostFilter): HostRow[] {
  const q = f.q.trim().toLowerCase();
  return hosts.filter((h) => {
    if (f.reach.length && !f.reach.includes(reachOf(h))) return false;
    if (f.agent.length && !f.agent.includes(h.hostagent_version ?? "")) return false;
    if (f.htag.length && !tagMatches(h.tags, f.htag)) return false;
    if (f.hpool.length && !f.hpool.includes(h.pool ? String(h.pool.id) : "none")) return false;
    if (f.hstage.length && !f.hstage.includes(h.stage ?? "none")) return false;
    if (q && !(contains(h.name, q) || contains(h.address, q) || contains(h.os, q) || h.tags.some((t) => contains(t, q))))
      return false;
    return true;
  });
}

export function tagOptions(items: { tags: string[] }[]): string[] {
  const values = new Set<string>();
  for (const item of items)
    for (const tag of item.tags) {
      values.add(tag.split("=")[0]);
      values.add(tag);
    }
  return [...values].sort();
}

// --- address ---------------------------------------------------------------------------

export function readFilter<T extends { q: string }>(
  params: URLSearchParams,
  empty: T,
  keys: readonly string[],
  search = "q",
): T {
  const f = { ...empty, q: params.get(search) ?? "" } as Record<string, unknown>;
  for (const key of keys) f[key] = params.getAll(key);
  return f as T;
}

export function writeFilter(
  params: URLSearchParams,
  f: { q: string } & Record<string, unknown>,
  keys: readonly string[],
  search = "q",
): URLSearchParams {
  const next = new URLSearchParams(params);
  next.delete(search);
  if (f.q) next.set(search, f.q);
  for (const key of keys) {
    next.delete(key);
    for (const value of f[key] as string[]) next.append(key, value);
  }
  return next;
}
