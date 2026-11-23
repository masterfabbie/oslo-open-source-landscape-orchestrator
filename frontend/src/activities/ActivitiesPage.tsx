// Activities: the top-level activities (newest first, with filters) and their steps, the
// activities that do the work themselves (one per single operation, one per target and step
// of a mass operation or template). Live: reloads when the server reports a change.

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { PageHead } from "../lib/forms";
import { activityNumber, formatDuration, stepNumber } from "../lib/numbers";
import { StatusBadge, formatTime, useApp, useLiveUpdates } from "../landscape/ui";

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

interface StepRow {
  id: number;
  activity_id: number;
  kind: string;
  target_type: string;
  target_label: string;
  status: string;
  requested_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export type ActivitiesTab = "activities" | "steps";

const STATUSES = ["RUNNING", "PENDING", "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"];

export function ActivitiesPage({ tab }: { tab: ActivitiesTab }) {
  const { t } = useApp();
  useLiveUpdates(["activities"]);
  return (
    <div className="oslo-page">
      <PageHead
        title={t("nav.activities")}
        tabs={[
          { href: "/activities", label: t("tab.activities"), current: tab === "activities" },
          { href: "/activities?tab=steps", label: t("tab.steps"), current: tab === "steps" },
        ]}
      />
      {tab === "activities" ? <ActivityList /> : <StepList />}
    </div>
  );
}

function StatusFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useApp();
  return (
    <label className="oslo-inline">
      {t("field.status")}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("pool.all")}</option>
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {t(`activity.${s}`)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ActivityList() {
  const { t, language } = useApp();
  const { data, isPending } = useQuery({ queryKey: ["activities", "list"], queryFn: () => api<ActivityRow[]>("/activities?limit=300") });
  const [status, setStatus] = useState("");
  const [text, setText] = useState("");
  const rows = useMemo(() => {
    const words = text.trim().toLowerCase();
    return (data ?? []).filter(
      (a) =>
        a.parent_id === null &&
        (!status || a.status === status) &&
        (!words || `${activityNumber(a.id)} ${a.kind} ${t(`kind.${a.kind}`)} ${a.target_label} ${a.requested_by ?? ""}`.toLowerCase().includes(words)),
    );
  }, [data, status, text, t]);
  return (
    <>
      <div className="oslo-form-buttons">
        <input className="oslo-filter-input" type="search" value={text} placeholder={t("ui.search")} aria-label={t("ui.search")} onChange={(e) => setText(e.target.value)} />
        <StatusFilter value={status} onChange={setStatus} />
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
                <th>{t("field.activity_number")}</th>
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
                    <a className="oslo-mono" href={`/activities/${a.id}`}>
                      {activityNumber(a.id)}
                    </a>
                  </td>
                  <td>{t(`kind.${a.kind}`)}</td>
                  <td>
                    {t(`target.${a.target_type}`)} <span className="oslo-mono">{a.target_label}</span>
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

function StepList() {
  const { t, language } = useApp();
  // ?activity=<id>: only the steps of that activity, e.g. from the page of a mass operation.
  const only = Number(new URLSearchParams(window.location.search).get("activity")) || null;
  const { data, isPending } = useQuery({
    queryKey: ["activities", "steps", only],
    queryFn: () => api<StepRow[]>(only ? `/steps?activity_id=${only}&limit=1000` : "/steps?limit=500"),
  });
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const [text, setText] = useState("");
  const kinds = useMemo(() => [...new Set((data ?? []).map((s) => s.kind))].sort(), [data]);
  const rows = useMemo(() => {
    const words = text.trim().toLowerCase();
    return (data ?? []).filter(
      (s) =>
        (!status || s.status === status) &&
        (!kind || s.kind === kind) &&
        (!words ||
          `${stepNumber(s.id)} ${activityNumber(s.activity_id)} ${t(`kind.${s.kind}`)} ${s.target_label}`.toLowerCase().includes(words)),
    );
  }, [data, status, kind, text, t]);
  return (
    <>
      <div className="oslo-form-buttons">
        <input className="oslo-filter-input" type="search" value={text} placeholder={t("ui.search")} aria-label={t("ui.search")} onChange={(e) => setText(e.target.value)} />
        <label className="oslo-inline">
          {t("field.operation")}
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{t("pool.all")}</option>
            {kinds.map((k) => (
              <option key={k} value={k}>
                {t(`kind.${k}`)}
              </option>
            ))}
          </select>
        </label>
        <StatusFilter value={status} onChange={setStatus} />
        {only && (
          <span className="oslo-muted">
            {t("steps.only", { number: activityNumber(only) })} <a href="/activities?tab=steps">{t("steps.all")}</a>
          </span>
        )}
      </div>
      {isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !rows.length ? (
        <p className="oslo-empty">{t("steps.empty")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("field.time")}</th>
                <th>{t("field.operation")}</th>
                <th>{t("field.id")}</th>
                <th>{t("field.target")}</th>
                <th>{t("field.duration")}</th>
                <th>{t("field.activity_number")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td className="oslo-muted">{formatTime(s.started_at ?? s.requested_at, language)}</td>
                  <td>{t(`kind.${s.kind}`)}</td>
                  <td>
                    <a className="oslo-mono" href={`/activities/${s.id}`}>
                      {stepNumber(s.id)}
                    </a>
                  </td>
                  <td className="oslo-mono">{s.target_label}</td>
                  <td>
                    {formatDuration(s.started_at, s.finished_at)}{" "}
                    {s.status !== "SUCCEEDED" && <StatusBadge status={s.status} prefix="activity" />}
                  </td>
                  <td>
                    <a className="oslo-mono" href={`/activities/${s.activity_id}`}>
                      {activityNumber(s.activity_id)}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
