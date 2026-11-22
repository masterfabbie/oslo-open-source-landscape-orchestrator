// Activities: all activities (newest first, with filters) and the latest log entries of
// all activities. Live: reloads when the server reports a change.

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { PageHead } from "../lib/forms";
import { hasRole } from "../lib/i18n";
import { StatusBadge, formatTime, useApp, useLiveUpdates } from "../landscape/ui";
import { SchedulesList } from "./SchedulesArea";

interface ActivityRow {
  id: number;
  kind: string;
  target_type: string;
  target_label: string;
  requested_by: string | null;
  parent_id: number | null;
  status: string;
  requested_at: string;
  finished_at: string | null;
}

interface LogRow {
  id: number;
  activity_id: number;
  target_label: string;
  kind: string;
  timestamp: string;
  level: string;
  message: string;
}

const STATUSES = ["RUNNING", "PENDING", "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"];

export function ActivitiesPage({ tab }: { tab: "activities" | "logs" | "schedules" }) {
  const { t, role } = useApp();
  useLiveUpdates([tab === "schedules" ? "schedules" : "activities"]);
  return (
    <div className="oslo-page">
      <PageHead
        title={t("nav.activities")}
        action={tab === "schedules" && hasRole(role, "operator") ? { href: "/activities/schedules/new", label: t("sched.new") } : undefined}
        tabs={[
          { href: "/activities", label: t("tab.activities"), current: tab === "activities" },
          { href: "/activities?tab=logs", label: t("tab.logs"), current: tab === "logs" },
          { href: "/activities?tab=schedules", label: t("tab.schedules"), current: tab === "schedules" },
        ]}
      />
      {tab === "activities" ? <ActivityList /> : tab === "logs" ? <LogList /> : <SchedulesList />}
    </div>
  );
}

function ActivityList() {
  const { t, language } = useApp();
  const { data, isPending } = useQuery({ queryKey: ["activities", "list"], queryFn: () => api<ActivityRow[]>("/activities?limit=300") });
  const [status, setStatus] = useState("");
  const [text, setText] = useState("");
  const [children, setChildren] = useState(false);
  const rows = useMemo(() => {
    const words = text.trim().toLowerCase();
    return (data ?? []).filter(
      (a) =>
        (children || a.parent_id === null) &&
        (!status || a.status === status) &&
        (!words || `${a.id} ${a.kind} ${t(`kind.${a.kind}`)} ${a.target_label} ${a.requested_by ?? ""}`.toLowerCase().includes(words)),
    );
  }, [data, status, text, children, t]);
  return (
    <>
      <div className="oslo-form-buttons">
        <input className="oslo-filter-input" type="search" value={text} placeholder={t("ui.search")} aria-label={t("ui.search")} onChange={(e) => setText(e.target.value)} />
        <label className="oslo-inline">
          {t("field.status")}
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t("pool.all")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`activity.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="oslo-inline">
          <input type="checkbox" checked={children} onChange={(e) => setChildren(e.target.checked)} /> {t("activities.with_children")}
        </label>
      </div>
      {isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !rows.length ? (
        <p className="oslo-empty">{t("activities.empty")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>#</th>
                <th>{t("field.operation")}</th>
                <th>{t("field.target")}</th>
                <th>{t("field.status")}</th>
                <th>{t("field.requested")}</th>
                <th>{t("field.requested_by")}</th>
                <th>{t("field.finished")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  <td>
                    <a href={`/activities/${a.id}`}>{a.id}</a>
                  </td>
                  <td>{t(`kind.${a.kind}`)}</td>
                  <td>
                    {t(`target.${a.target_type}`)} <span className="oslo-mono">{a.target_label}</span>
                    {a.parent_id && (
                      <a className="oslo-sub" href={`/activities/${a.parent_id}`}>
                        {t("mass.part_of", { id: a.parent_id })}
                      </a>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={a.status} prefix="activity" />
                  </td>
                  <td className="oslo-muted">{formatTime(a.requested_at, language)}</td>
                  <td className="oslo-mono">{a.requested_by ?? ""}</td>
                  <td className="oslo-muted">{formatTime(a.finished_at, language)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function LogList() {
  const { t, language } = useApp();
  const limit = 200;
  const { data, isPending } = useQuery({ queryKey: ["activities", "log"], queryFn: () => api<LogRow[]>(`/activity-log?limit=${limit}`) });
  const [level, setLevel] = useState("");
  const rows = (data ?? []).filter((e) => !level || e.level === level);
  return (
    <>
      <div className="oslo-form-buttons">
        <span className="oslo-muted">{t("logs.hint", { limit })}</span>
        <label className="oslo-inline">
          {t("ui.log_level")}
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">{t("pool.all")}</option>
            <option value="WARNING">{t("ui.log_warnings")}</option>
            <option value="ERROR">{t("ui.log_errors")}</option>
          </select>
        </label>
      </div>
      {isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !rows.length ? (
        <p className="oslo-empty">{t("logs.empty")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("field.time")}</th>
                <th>{t("activity.title")}</th>
                <th>{t("field.message")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} className={`oslo-log-${e.level.toLowerCase()}`}>
                  <td className="oslo-muted">{formatTime(e.timestamp, language, true)}</td>
                  <td>
                    <a href={`/activities/${e.activity_id}`}>{e.activity_id}</a> <span className="oslo-mono">{e.target_label}</span>
                  </td>
                  <td className="oslo-mono">{e.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {language !== "en" && <p className="oslo-muted">{t("activity.log_language")}</p>}
    </>
  );
}
