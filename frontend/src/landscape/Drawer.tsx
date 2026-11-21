// Panel on the right. A system shows a short summary and its last activities; an instance
// shows details in tabs (general, processes from GetProcessList, its activities); a host its
// facts and instances.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";
import { api } from "../lib/api";
import { hasRole } from "../lib/i18n";
import type { Activity, HostRow, InstanceRow, OperationDef, ProcessList, SystemRow } from "../lib/types";
import { reachOf } from "./filter";
import { type Selection, operationLabel, operationsFor } from "./selection";
import { Tags } from "./SystemsTable";
import type { Toast } from "./Toasts";
import { StatusBadge, StatusDot, formatTime, useApp } from "./ui";

type Run = (op: OperationDef, selection: Selection) => void;

export const RECENT_ACTIVITIES = 5;

function useEscape(onClose: () => void) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !document.querySelector("dialog[open]")) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
}

function Header({ title, subtitle, onClose, children }: { title: string; subtitle?: string; onClose: () => void; children?: ReactNode }) {
  const { t } = useApp();
  return (
    <div className="oslo-drawer-head">
      <div>
        <h2>{title}</h2>
        {subtitle && <span className="oslo-sub">{subtitle}</span>}
      </div>
      {children}
      <button type="button" className="oslo-close" onClick={onClose} aria-label={t("ui.close")}>
        ×
      </button>
    </div>
  );
}

function Operations({ operations, selection, onRun }: { operations: OperationDef[]; selection: Selection; onRun: Run }) {
  const { t } = useApp();
  const available = operationsFor(operations, selection, new Map());
  if (!available.length) return null;
  return (
    <div className="oslo-drawer-ops">
      {available.map((op) => (
        <button
          key={op.key}
          type="button"
          className={op.danger ? "oslo-danger" : "secondary"}
          onClick={() => {
            if (!op.danger || window.confirm(t("op.confirm"))) onRun(op, selection);
          }}
        >
          {operationLabel(op, selection.kind, t)}
          {op.custom && (op.parameters.length || op.template) ? "…" : ""}
        </button>
      ))}
    </div>
  );
}

/** The last activities of a system, instance or host, newest first, each linked. */
export function RecentActivities({ filter }: { filter: string }) {
  const { t, language } = useApp();
  const { data, isPending } = useQuery({
    queryKey: ["landscape", "activities", filter],
    queryFn: () => api<Activity[]>(`/activities?limit=${RECENT_ACTIVITIES}&${filter}`),
  });
  if (isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (!data?.length) return <p className="oslo-muted">{t("ui.no_activities")}</p>;
  return (
    <ul className="oslo-recent">
      {data.map((activity) => (
        <li key={activity.id}>
          <a href={`/activities/${activity.id}`}>
            <span className={`oslo-badge oslo-badge-${activityTone(activity.status)}`}>{t(`activity.${activity.status}`)}</span>
            <span className="oslo-recent-what">
              {t(`kind.${activity.kind}`)} <span className="oslo-mono">{activity.target_label}</span>
            </span>
            <span className="oslo-muted">
              {formatTime(activity.requested_at, language)}
              {activity.requested_by ? ` · ${activity.requested_by}` : ""}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

export function activityTone(status: string): string {
  switch (status) {
    case "SUCCEEDED":
      return "green";
    case "FAILED":
      return "red";
    case "PARTIAL":
      return "yellow";
    case "RUNNING":
    case "PENDING":
      return "running";
    default:
      return "gray";
  }
}

function instanceKind(instance: InstanceRow, t: (key: string) => string): string {
  return instance.type ? t(`itype.${instance.type}`) : t(`ui.role.${instance.role}`);
}

// --- system ----------------------------------------------------------------------------

export function SystemDrawer({
  system,
  operations,
  onClose,
  onRun,
  notify,
  onOpenInstance,
}: {
  system: SystemRow | undefined;
  operations: OperationDef[];
  onClose: () => void;
  onRun: Run;
  notify: (toast: Omit<Toast, "id">) => void;
  onOpenInstance: (id: number) => void;
}) {
  const { t, role } = useApp();
  const queries = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  useEscape(onClose);
  if (!system) return null;

  // As the system status: diagnostics agents do not count.
  const counted = system.instances.filter((i) => !i.agent);
  const running = counted.filter((i) => i.status === "GREEN").length;
  const hosts = [...new Set(system.instances.map((i) => i.host.name))];

  const refresh = async () => {
    setRefreshing(true);
    try {
      const result = await api<{ warnings: string[] }>(`/systems/${system.id}/refresh`, { method: "POST" });
      for (const warning of result.warnings) notify({ kind: "error", text: warning });
      await queries.invalidateQueries({ queryKey: ["landscape"] });
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <aside className="oslo-drawer" aria-label={system.name}>
      <Header title={system.name} subtitle={system.description ?? t("field.system")} onClose={onClose}>
        <StatusBadge status={system.status} />
      </Header>
      <p className={`oslo-summary-line oslo-tone-${system.status.toLowerCase()}`}>
        {t("ui.instances_running", { running, total: counted.length })}
      </p>
      <dl className="oslo-facts">
        {system.pool && (
          <>
            <dt>{t("field.pool")}</dt>
            <dd>{system.pool.name}</dd>
          </>
        )}
        <dt>{t("deps.depends_on")}</dt>
        <dd>{system.depends_on.join(", ") || t("deps.none")}</dd>
        <dt>{t("overview.hosts")}</dt>
        <dd>{hosts.join(", ")}</dd>
        {system.tags.length > 0 && (
          <>
            <dt>{t("field.tags")}</dt>
            <dd>
              <Tags tags={system.tags} />
            </dd>
          </>
        )}
      </dl>
      <Operations operations={operations} selection={{ kind: "SYSTEM", ids: [system.id] }} onRun={onRun} />
      <div className="oslo-drawer-links">
        <button type="button" className="secondary" onClick={refresh} disabled={refreshing}>
          {t("ui.refresh_status")}
        </button>
        <a href={`/systems/${system.id}`}>{t("ui.open_page")}</a>
        {hasRole(role, "configurator") && <a href={`/configuration/systems/${system.id}`}>{t("action.configure")}</a>}
      </div>

      <h3>{t("ui.instances_in_order")}</h3>
      <ul className="oslo-instance-list">
        {system.instances.map((instance) => (
          <li key={instance.id}>
            <button type="button" onClick={() => onOpenInstance(instance.id)} className={instance.agent ? "oslo-agent" : undefined}>
              <StatusDot status={instance.status} label={t(`status.${instance.status}`)} />
              <span className="oslo-mono">{instance.label}</span>
              <span className="oslo-muted">{instanceKind(instance, t)}</span>
              <span className="oslo-muted oslo-right">{instance.host.name}</span>
            </button>
          </li>
        ))}
      </ul>

      <h3>{t("ui.recent_activities")}</h3>
      <RecentActivities filter={`system_id=${system.id}`} />
    </aside>
  );
}

// --- instance --------------------------------------------------------------------------

type InstanceTab = "general" | "status" | "log";

function Processes({ instance }: { instance: InstanceRow }) {
  const { t, language } = useApp();
  const { data, isPending, isError, dataUpdatedAt, refetch, isFetching } = useQuery({
    queryKey: ["processes", instance.id],
    queryFn: () => api<ProcessList>(`/instances/${instance.id}/processes`),
    refetchInterval: 15_000,
  });
  if (isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (isError || !data) return <p className="error-text">{t("ui.load_failed")}</p>;
  return (
    <>
      <div className="oslo-drawer-links">
        <StatusBadge status={data.status} />
        <span className="oslo-muted">{t("ui.checked_at", { time: formatTime(new Date(dataUpdatedAt).toISOString(), language) })}</span>
        <button type="button" className="link" onClick={() => void refetch()} disabled={isFetching}>
          {t("ui.read_again")}
        </button>
      </div>
      {data.error ? (
        <p className="error-text">
          {t("ui.processes_unavailable")}: {data.error}
        </p>
      ) : !data.processes.length ? (
        <p className="oslo-muted">{t("ui.no_processes")}</p>
      ) : (
        <table className="oslo-processes">
          <thead>
            <tr>
              <th>{t("ui.process")}</th>
              <th>{t("field.status")}</th>
              <th>{t("ui.started_at")}</th>
              <th>PID</th>
            </tr>
          </thead>
          <tbody>
            {data.processes.map((p) => (
              <tr key={`${p.name}-${p.pid}`}>
                <td>
                  <span className="oslo-mono">{p.name}</span>
                  <span className="oslo-sub">{p.description}</span>
                </td>
                <td>
                  <span className="oslo-process-status">
                    <StatusDot status={p.status} />
                    {p.text}
                  </span>
                  {p.elapsed && <span className="oslo-sub">{p.elapsed}</span>}
                </td>
                <td className="oslo-muted">{p.started}</td>
                <td className="oslo-mono">{p.pid || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

export function InstanceDrawer({
  instance,
  system,
  operations,
  onClose,
  onRun,
  onOpenSystem,
}: {
  instance: InstanceRow | undefined;
  system: SystemRow | undefined;
  operations: OperationDef[];
  onClose: () => void;
  onRun: Run;
  onOpenSystem: (id: number) => void;
}) {
  const { t, language } = useApp();
  const [tab, setTab] = useState<InstanceTab>("general");
  useEscape(onClose);
  useEffect(() => setTab("general"), [instance?.id]);
  if (!instance) return null;

  const tabs: [InstanceTab, string][] = [
    ["general", t("tab.general")],
    ["status", t("ui.tab_status")],
    ["log", t("ui.tab_log")],
  ];
  return (
    <aside className="oslo-drawer" aria-label={instance.label}>
      <Header title={instance.label} subtitle={`${instanceKind(instance, t)} · ${instance.host.name}`} onClose={onClose}>
        <StatusBadge status={instance.status} />
      </Header>
      <nav className="tabs oslo-drawer-tabs" aria-label={instance.label}>
        {tabs.map(([key, label]) => (
          <a
            key={key}
            href={`#${key}`}
            aria-current={tab === key ? "page" : undefined}
            onClick={(event) => {
              event.preventDefault();
              setTab(key);
            }}
          >
            {label}
          </a>
        ))}
      </nav>

      {tab === "general" && (
        <>
          <dl className="oslo-facts">
            <dt>{t("field.type")}</dt>
            <dd>{instanceKind(instance, t)}</dd>
            <dt>{t("field.system")}</dt>
            <dd>
              {system ? (
                <button type="button" className="link" onClick={() => onOpenSystem(system.id)}>
                  {system.name}
                </button>
              ) : (
                "–"
              )}
            </dd>
            <dt>{t("field.sid")}</dt>
            <dd className="oslo-mono">{instance.sid}</dd>
            <dt>{t("ui.instance_number")}</dt>
            <dd className="oslo-mono">{instance.number}</dd>
            <dt>{t("field.host")}</dt>
            <dd>
              <a href={`/hosts/${instance.host.id}`}>{instance.host.name}</a>
            </dd>
            <dt>{t("field.hostname")}</dt>
            <dd className="oslo-mono">{instance.hostname}</dd>
            {instance.version && (
              <>
                <dt>{t("ui.kernel")}</dt>
                <dd className="oslo-mono">{instance.version}</dd>
              </>
            )}
            <dt>{t("field.priority")}</dt>
            <dd>{instance.start_priority ?? "–"}</dd>
            <dt>{t("deps.depends_on")}</dt>
            <dd>{instance.depends_on.join(", ") || t("deps.none")}</dd>
            <dt>{t("field.checked")}</dt>
            <dd>{formatTime(instance.status_checked_at, language) || "–"}</dd>
          </dl>
          <Operations operations={operations} selection={{ kind: "INSTANCE", ids: [instance.id] }} onRun={onRun} />
        </>
      )}
      {tab === "status" && <Processes instance={instance} />}
      {tab === "log" && <RecentActivities filter={`instance_id=${instance.id}`} />}
    </aside>
  );
}

// --- host ------------------------------------------------------------------------------

export function HostDrawer({
  host,
  systems,
  operations,
  onClose,
  onRun,
}: {
  host: HostRow | undefined;
  systems: SystemRow[];
  operations: OperationDef[];
  onClose: () => void;
  onRun: Run;
}) {
  const { t, role, language } = useApp();
  useEscape(onClose);
  if (!host) return null;
  const onHost = systems.flatMap((s) => s.instances.filter((i) => i.host.id === host.id).map((i) => ({ system: s, instance: i })));
  return (
    <aside className="oslo-drawer" aria-label={host.name}>
      <Header title={host.name} subtitle={t("field.host")} onClose={onClose}>
        <StatusBadge status={reachOf(host)} prefix="reach" />
      </Header>
      <dl className="oslo-facts">
        <dt>{t("field.address")}</dt>
        <dd className="oslo-mono">{host.address}</dd>
        <dt>{t("field.hostagent")}</dt>
        <dd>{host.hostagent_version ?? "–"}</dd>
        <dt>{t("field.os")}</dt>
        <dd>{host.os ?? "–"}</dd>
        <dt>{t("field.last_discovery")}</dt>
        <dd>{formatTime(host.last_discovery_at, language) || t("hosts.never")}</dd>
        {host.last_error && (
          <>
            <dt>{t("field.last_error")}</dt>
            <dd className="error-text">{host.last_error}</dd>
          </>
        )}
      </dl>
      <Operations operations={operations} selection={{ kind: "HOST", ids: [host.id] }} onRun={onRun} />
      <div className="oslo-drawer-links">
        <a href={`/hosts/${host.id}`}>{t("ui.open_page")}</a>
        {hasRole(role, "configurator") && <a href={`/configuration/hosts/${host.id}`}>{t("action.configure")}</a>}
      </div>
      <h3>{t("field.instances")}</h3>
      {onHost.length ? (
        <ul className="oslo-instance-list">
          {onHost.map(({ system, instance }) => (
            <li key={instance.id}>
              <span className="oslo-instance-row">
                <StatusDot status={instance.status} label={t(`status.${instance.status}`)} />
                <span className="oslo-mono">{instance.label}</span>
                <span className="oslo-muted">{system.name}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="oslo-muted">{t("ui.no_instances_on_host")}</p>
      )}
      <h3>{t("ui.recent_activities")}</h3>
      <RecentActivities filter={`host_id=${host.id}`} />
    </aside>
  );
}
