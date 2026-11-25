// The configuration log: who changed what, as a table (Activities → Configuration) and as
// "Recent changes" on the page of a host, system, pool, custom operation or schedule.

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { Section } from "./forms";
import type { Translate } from "./i18n";
import { formatTime, useApp } from "../landscape/ui";

export interface ConfigChange {
  id: number;
  changed_at: string;
  username: string | null;
  object_type: string;
  object_id: number | null;
  object_name: string;
  action: string;
  changes: Record<string, [unknown, unknown]>;
}

export const OBJECT_TYPES = [
  "host",
  "sid",
  "system",
  "pool",
  "custom_operation",
  "template",
  "schedule",
  "certificate",
  "attention_rules",
  "platform",
  "user",
  "import",
];

// Fields that are lists: their entries are added ("+") or removed ("−").
const LISTS = new Set(["tags", "instances", "systems", "hosts", "depends_on"]);

// Shown as "(changed)": secrets and long values.
const CHANGED = "(changed)";

/** Where the object of an entry is configured; none for deleted objects. */
export function objectHref(change: ConfigChange): string | null {
  const id = change.object_id;
  if (change.action === "deleted") return null;
  switch (change.object_type) {
    case "host":
      return id ? `/configuration/hosts/${id}` : null;
    case "system":
      return id ? `/configuration/systems/${id}` : null;
    case "pool":
      return id ? `/configuration/pools/${id}` : null;
    case "custom_operation":
      return id ? `/operations/custom/${id}` : null;
    case "template":
      return "/operations/templates";
    case "schedule":
      return id ? `/operations/schedules/${id}` : null;
    case "user":
      return id ? `/administration/users/${id}` : null;
    case "certificate":
      return "/administration/certificates";
    case "attention_rules":
      return "/administration/attention";
    case "platform":
      return "/administration";
    default:
      return null;
  }
}

function value(v: unknown, t: Translate): string {
  if (v === CHANGED) return t("cfg.changed");
  if (v === true) return t("cfg.yes");
  if (v === false) return t("cfg.no");
  return String(v);
}

/** One line per field: "Address: sapapp1 → 10.0.0.9", "Tags: + dev", "Tags: − sla=1". */
export function changeLines(change: ConfigChange, t: Translate): string[] {
  return Object.entries(change.changes).map(([name, [before, after]]) => {
    const label = t(`cfg.field.${name}`) === `cfg.field.${name}` ? name : t(`cfg.field.${name}`);
    if (change.action === "imported") return `${t(`cfg.count.${name}`)}: ${value(after, t)}`;
    if (before === null && after === null) return label;
    if (after === CHANGED) return `${label}: ${t("cfg.changed")}`;
    if (before === null && change.action === "created") return `${label}: ${value(after, t)}`;
    if (LISTS.has(name)) {
      if (before === null) return `${label}: + ${value(after, t)}`;
      if (after === null) return `${label}: − ${value(before, t)}`;
    }
    if (before === null) return `${label}: — → ${value(after, t)}`;
    if (after === null) return `${label}: ${value(before, t)} → —`;
    return `${label}: ${value(before, t)} → ${value(after, t)}`;
  });
}

export function ChangesTable({ rows, showObject = true }: { rows: ConfigChange[]; showObject?: boolean }) {
  const { t, language } = useApp();
  return (
    <div className="oslo-table-wrap">
      <table className="oslo-table">
        <thead>
          <tr>
            <th>{t("field.time")}</th>
            <th>{t("field.username")}</th>
            {showObject && <th>{t("cfg.object")}</th>}
            <th>{t("cfg.action")}</th>
            <th>{t("cfg.changes")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const href = objectHref(c);
            return (
              <tr key={c.id}>
                <td className="oslo-muted">{formatTime(c.changed_at, language)}</td>
                <td className="oslo-mono">{c.username ?? ""}</td>
                {showObject && (
                  <td>
                    {t(`cfg.type.${c.object_type}`)}{" "}
                    {href ? (
                      <a className="oslo-mono" href={href}>
                        {c.object_name}
                      </a>
                    ) : (
                      <span className="oslo-mono">{c.object_name}</span>
                    )}
                  </td>
                )}
                <td>{t(`cfg.action.${c.action}`)}</td>
                <td>
                  <ul className="oslo-change-lines">
                    {changeLines(c, t).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** The latest changes of one object, with a link to all of them. */
export function RecentChanges({ type, id }: { type: string; id: number }) {
  const { t } = useApp();
  const { data } = useQuery({
    queryKey: ["config-changes", type, id],
    queryFn: () => api<ConfigChange[]>(`/config-changes?object_type=${type}&object_id=${id}&limit=10`),
  });
  return (
    <Section title={t("cfg.recent")}>
      {!data ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !data.length ? (
        <p className="oslo-muted">{t("cfg.none")}</p>
      ) : (
        <>
          <ChangesTable rows={data} showObject={false} />
          <p>
            <a href={`/activities?tab=changes&type=${type}&id=${id}`}>{t("cfg.all_of_object")}</a>
          </p>
        </>
      )}
    </Section>
  );
}
