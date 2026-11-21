// The overview: key figures, the systems as a matrix of products (pools) and stages, each
// instance a status square, and "needs attention" from the rules an admin configures. Each
// user can switch rules off and hide systems or pools for themselves.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { hasRole } from "../lib/i18n";
import { StatusDot, formatTime, useApp, useLiveUpdates } from "../landscape/ui";

interface OverviewSystem {
  id: number;
  name: string;
  pool_id: number | null;
  stage: string | null;
  status: string;
  activity: { id: number; kind: string; status: string } | null;
  instances: { id: number; label: string; status: string; agent: boolean }[];
}

interface AttentionItem {
  rule: string;
  severity: "error" | "warning";
  key: string;
  values: Record<string, string | number>;
  link: string;
  at: string | null;
  system_id: number | null;
  host_id: number | null;
}

interface Exceptions {
  disabled_rules: string[];
  hidden_systems: number[];
  hidden_pools: number[];
}

export interface Overview {
  kpis: Record<"systems" | "instances" | "hosts" | "activities", { total: number; by: Record<string, number> }>;
  columns: string[];
  pools: { id: number; name: string; description: string | null }[];
  systems: OverviewSystem[];
  attention: AttentionItem[];
  exceptions: Exceptions;
  rules: Record<string, boolean>;
}

const KPI_ORDER: Record<string, string[]> = {
  systems: ["GREEN", "YELLOW", "RED", "GRAY", "UNKNOWN"],
  instances: ["GREEN", "YELLOW", "RED", "GRAY", "UNKNOWN"],
  hosts: ["GREEN", "RED", "UNKNOWN"],
  activities: ["RUNNING", "PENDING", "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"],
};
const KPI_LINK: Record<string, string> = {
  systems: "/landscape",
  instances: "/landscape",
  hosts: "/landscape?tab=hosts",
  activities: "/activities",
};

/** Rows of the matrix: the pools, then the systems without a pool (if any). */
export function matrixRows(data: Overview): { id: number | null; name: string | null }[] {
  const rows: { id: number | null; name: string | null }[] = data.pools.map((p) => ({ id: p.id, name: p.name }));
  if (data.systems.some((s) => s.pool_id === null)) rows.push({ id: null, name: null });
  return rows;
}

export function OverviewPage() {
  const { t, language, role } = useApp();
  const queries = useQueryClient();
  useLiveUpdates(["overview"]);
  const { data, isPending, error } = useQuery({ queryKey: ["overview"], queryFn: () => api<Overview>("/overview") });
  const [customizing, setCustomizing] = useState(false);

  if (isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (error || !data) return <p className="flash error">{(error as Error)?.message}</p>;

  const saveExceptions = async (next: Exceptions) => {
    await api("/me/attention", { method: "PUT", body: next });
    await queries.invalidateQueries({ queryKey: ["overview"] });
  };
  const hideSystem = (id: number) =>
    saveExceptions({ ...data.exceptions, hidden_systems: [...data.exceptions.hidden_systems, id] });
  const ruleOff = (rule: string) =>
    saveExceptions({ ...data.exceptions, disabled_rules: [...data.exceptions.disabled_rules, rule] });
  const exceptionCount =
    data.exceptions.disabled_rules.length + data.exceptions.hidden_systems.length + data.exceptions.hidden_pools.length;
  const systemName = new Map(data.systems.map((s) => [s.id, s.name]));
  const poolName = new Map(data.pools.map((p) => [p.id, p.name]));
  const rows = matrixRows(data);

  return (
    <div className="oslo-overview">
      <h1>{t("nav.overview")}</h1>
      <section className="oslo-kpis" aria-label={t("ov.kpis")}>
        {(["systems", "instances", "hosts", "activities"] as const).map((key) => {
          const kpi = data.kpis[key];
          return (
            <a key={key} className="oslo-kpi" href={KPI_LINK[key]}>
              <span className="oslo-kpi-label">{t(`overview.${key === "activities" ? "activities_24h" : key}`)}</span>
              <span className="oslo-kpi-value">{kpi.total}</span>
              <span className="oslo-kpi-bar" aria-hidden>
                {KPI_ORDER[key].map((s) =>
                  kpi.by[s] ? <span key={s} className={`oslo-kpi-part oslo-kpi-${s.toLowerCase()}`} style={{ flexGrow: kpi.by[s] }} /> : null,
                )}
              </span>
              <span className="oslo-kpi-legend">
                {KPI_ORDER[key]
                  .filter((s) => kpi.by[s])
                  .map((s) => `${kpi.by[s]} ${t(`${key === "hosts" ? "reach" : key === "activities" ? "activity" : "status"}.${s}`)}`)
                  .join(" · ")}
              </span>
            </a>
          );
        })}
      </section>

      <div className="oslo-overview-grid">
        <section className="oslo-card oslo-matrix-card" aria-label={t("ov.matrix")}>
          <h2>{t("ov.matrix")}</h2>
          {!data.systems.length ? (
            <p className="oslo-muted">{t("config.no_systems")}</p>
          ) : (
            <div className="oslo-table-wrap">
              <table className="oslo-matrix">
                <thead>
                  <tr>
                    <th scope="col">{t("ov.product")}</th>
                    {data.columns.map((c) => (
                      <th key={c} scope="col">
                        {t(c ? `stage.${c}` : "stage.none")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id ?? "none"}>
                      <th scope="row">{row.name ?? <span className="oslo-muted">{t("pool.none")}</span>}</th>
                      {data.columns.map((column) => {
                        const cell = data.systems.filter((s) => s.pool_id === row.id && (s.stage ?? "") === column);
                        return (
                          <td key={column}>
                            {cell.map((s) => (
                              <a key={s.id} className={`oslo-cell oslo-cell-${s.status.toLowerCase()}`} href={`/landscape?system=${s.id}`} title={t(`status.${s.status}`)}>
                                <span className="oslo-cell-name">
                                  {s.name}
                                  {s.activity && <span className="oslo-cell-running" title={t(`kind.${s.activity.kind}`)} aria-label={t("activity.RUNNING")} />}
                                </span>
                                <span className="oslo-cell-squares">
                                  {s.instances.map((i) => (
                                    <StatusDot key={i.id} status={i.status} label={`${i.label}: ${t(`status.${i.status}`)}`} />
                                  ))}
                                </span>
                              </a>
                            ))}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="oslo-muted oslo-matrix-hint">{t("ov.matrix_hint")}</p>
        </section>

        <section className="oslo-card oslo-attention" aria-label={t("ov.attention")}>
          <div className="oslo-attention-head">
            <h2>
              {t("ov.attention")} <span className="oslo-count">{data.attention.length}</span>
            </h2>
            <button type="button" className="link" onClick={() => setCustomizing(!customizing)} aria-expanded={customizing}>
              {t("ov.customize")}
              {exceptionCount ? ` (${exceptionCount})` : ""}
            </button>
          </div>
          {customizing && (
            <div className="oslo-attention-custom">
              <p className="oslo-muted">{t("ov.customize_hint")}</p>
              <fieldset>
                <legend>{t("ov.rules_for_me")}</legend>
                {Object.entries(data.rules).map(([rule, enabled]) => (
                  <label key={rule} className="oslo-inline">
                    <input
                      type="checkbox"
                      disabled={!enabled}
                      checked={enabled && !data.exceptions.disabled_rules.includes(rule)}
                      onChange={(e) =>
                        void saveExceptions({
                          ...data.exceptions,
                          disabled_rules: e.target.checked
                            ? data.exceptions.disabled_rules.filter((r) => r !== rule)
                            : [...data.exceptions.disabled_rules, rule],
                        })
                      }
                    />
                    {t(`att.rule.${rule}`)}
                    {!enabled && <span className="oslo-muted"> · {t("ov.rule_off_globally")}</span>}
                  </label>
                ))}
              </fieldset>
              {(data.exceptions.hidden_systems.length > 0 || data.exceptions.hidden_pools.length > 0) && (
                <fieldset>
                  <legend>{t("ov.hidden")}</legend>
                  {data.exceptions.hidden_systems.map((id) => (
                    <span key={`s${id}`} className="oslo-hidden-chip">
                      {systemName.get(id) ?? `#${id}`}
                      <button type="button" aria-label={t("ov.show_again")} onClick={() => void saveExceptions({ ...data.exceptions, hidden_systems: data.exceptions.hidden_systems.filter((x) => x !== id) })}>
                        ×
                      </button>
                    </span>
                  ))}
                  {data.exceptions.hidden_pools.map((id) => (
                    <span key={`p${id}`} className="oslo-hidden-chip">
                      {t("field.pool")} {poolName.get(id) ?? `#${id}`}
                      <button type="button" aria-label={t("ov.show_again")} onClick={() => void saveExceptions({ ...data.exceptions, hidden_pools: data.exceptions.hidden_pools.filter((x) => x !== id) })}>
                        ×
                      </button>
                    </span>
                  ))}
                </fieldset>
              )}
              {data.pools.length > 0 && (
                <label>
                  {t("ov.hide_pool")}
                  <select
                    value=""
                    onChange={(e) => e.target.value && void saveExceptions({ ...data.exceptions, hidden_pools: [...data.exceptions.hidden_pools, Number(e.target.value)] })}
                  >
                    <option value="">–</option>
                    {data.pools
                      .filter((p) => !data.exceptions.hidden_pools.includes(p.id))
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                  </select>
                </label>
              )}
              {hasRole(role, "admin") && <a href="/administration/attention">{t("ov.edit_rules")}</a>}
            </div>
          )}
          {!data.attention.length ? (
            <p className="oslo-empty">{t("ov.all_fine")}</p>
          ) : (
            <ul className="oslo-attention-list">
              {data.attention.map((item, index) => (
                <li key={`${item.rule}-${index}`} className={`oslo-attention-${item.severity}`}>
                  <a href={item.link}>
                    <span className="oslo-attention-text">{t(item.key, translatedValues(item, t))}</span>
                    {item.values.error && <span className="oslo-attention-detail">{item.values.error}</span>}
                    <span className="oslo-muted oslo-attention-meta">
                      {t(`att.rule.${item.rule}`)}
                      {item.at ? ` · ${formatTime(item.at, language)}` : ""}
                    </span>
                  </a>
                  <span className="oslo-attention-tools">
                    {item.system_id !== null && (
                      <button type="button" className="link" onClick={() => void hideSystem(item.system_id as number)}>
                        {t("ov.hide_system")}
                      </button>
                    )}
                    <button type="button" className="link" onClick={() => void ruleOff(item.rule)}>
                      {t("ov.rule_off")}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

/** Values of an item with codes (status, kind) translated. */
function translatedValues(item: AttentionItem, t: (k: string) => string): Record<string, string | number> {
  const values = { ...item.values };
  if (typeof values.status === "string") values.status = t(`status.${values.status}`);
  if (typeof values.kind === "string") values.kind = t(`kind.${values.kind}`);
  return values;
}
