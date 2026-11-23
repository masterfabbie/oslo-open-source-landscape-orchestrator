// One activity, live: what runs, a timeline per instance and the log with filters. Running
// activities can be cancelled (operator and above).

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../lib/api";
import { activityNumber, stepNumber } from "../lib/numbers";
import { hasRole } from "../lib/i18n";
import type { ActivityDetail, LogEntry } from "../lib/types";
import { activityTone } from "../landscape/Drawer";
import { formatTime, useApp, useLiveUpdates } from "../landscape/ui";
import { type Timeline, buildTimeline, formatDuration, place } from "./timeline";

type Level = "all" | "WARNING" | "ERROR";
const ACTIVE = new Set(["PENDING", "RUNNING"]);

function useNow(running: boolean): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  return now;
}

export function ActivityPage({ id }: { id: number }) {
  const { t, role, language } = useApp();
  const queries = useQueryClient();
  useLiveUpdates(["activity", id]);
  const { data, error, isPending } = useQuery({
    queryKey: ["activity", id],
    queryFn: () => api<ActivityDetail>(`/activities/${id}`),
  });
  const running = !!data && ACTIVE.has(data.status);
  const now = useNow(running);
  const [subject, setSubject] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const timeline = useMemo(() => (data ? buildTimeline(data, now, t) : null), [data, now, t]);

  if (isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (error || !data) return <p className="flash error">{t("ui.load_failed")}</p>;

  const template = (data.options?.template ?? null) as { name?: string } | null;
  const custom = (data.options?.custom ?? null) as { name?: string; agent_operation?: string } | null;
  const parameters = (data.options?.parameters ?? {}) as Record<string, string>;
  const title = template?.name ?? custom?.name ?? t(`kind.${data.kind}`);
  const started = data.started_at ? new Date(data.started_at).getTime() : null;
  const ended = data.finished_at ? new Date(data.finished_at).getTime() : now;

  const cancel = async () => {
    if (!window.confirm(t("activity.cancel_confirm"))) return;
    setCancelling(true);
    setCancelError(null);
    try {
      await api(`/activities/${id}/cancel`, { method: "POST" });
      await queries.invalidateQueries({ queryKey: ["activity", id] });
    } catch (exc) {
      setCancelError(exc instanceof ApiError && exc.status === 409 ? t("error.not_active") : String((exc as Error).message));
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div className="oslo-activity">
      <p className="crumbs">
        <a href="/activities">{t("nav.activities")}</a>
        {data.parent_id && (
          <>
            {" / "}
            <a href={`/activities/${data.parent_id}`}>{t("mass.part_of", { id: activityNumber(data.parent_id) })}</a>
          </>
        )}
      </p>
      <div className="oslo-activity-head">
        <h1>
          {data.parent_id ? t("step.title") : t("activity.title")} {data.parent_id ? stepNumber(data.id) : activityNumber(data.id)}: {title} <span className="oslo-mono">{data.target_label}</span>
        </h1>
        <span className={`oslo-badge oslo-badge-${activityTone(data.status)} oslo-badge-big`}>{t(`activity.${data.status}`)}</span>
        {running && hasRole(role, "operator") && (
          <button type="button" className="oslo-cancel" onClick={cancel} disabled={cancelling}>
            {t("activity.cancel")}
          </button>
        )}
      </div>
      <p className="oslo-activity-meta">
        <span>{t("target." + data.target_type)}</span>
        <span>
          {t("field.requested")}: {formatTime(data.requested_at, language)}
          {data.requested_by ? ` · ${data.requested_by}` : ""}
        </span>
        {started !== null && (
          <span>
            {t("ui.duration")}: {formatDuration(ended - started)}
            {running ? ` / ${t("ui.timeout_of", { minutes: Math.round(data.timeout_seconds / 60) })}` : ""}
          </span>
        )}
        {data.finished_at && (
          <span>
            {t("field.finished")}: {formatTime(data.finished_at, language)}
          </span>
        )}
      </p>
      {data.error && (
        <p className="flash error" role="alert">
          {data.error}
        </p>
      )}
      {cancelError && (
        <p className="flash error" role="alert">
          {cancelError}
        </p>
      )}
      {custom && (
        <dl className="oslo-facts oslo-card">
          <dt>{t("custom.operation")}</dt>
          <dd>
            {custom.name} <span className="oslo-mono oslo-muted">{custom.agent_operation}</span>
          </dd>
          <dt>{t("custom.parameters")}</dt>
          <dd className="oslo-mono">
            {Object.entries(parameters)
              .map(([k, v]) => `${k}=${v}`)
              .join(", ") || "–"}
          </dd>
        </dl>
      )}

      {(data.target_type === "MASS" || data.kind === "TEMPLATE") && <Children activity={data} />}

      {timeline && timeline.lanes.length > 0 && (
        <TimelineView
          timeline={timeline}
          now={now}
          selected={subject}
          onSelect={setSubject}
          mass={data.target_type === "MASS" || data.kind === "TEMPLATE"}
        />
      )}

      <Log entries={data.entries} running={running} subject={subject} onSubject={setSubject} subjects={timeline?.lanes.map((l) => l.subject) ?? []} />
    </div>
  );
}

// --- mass operation --------------------------------------------------------------------

function Children({ activity }: { activity: ActivityDetail }) {
  const { t, language } = useApp();
  const options = activity.options ?? {};
  const counts = new Map<string, number>();
  for (const child of activity.children) counts.set(child.status, (counts.get(child.status) ?? 0) + 1);
  const total = Array.isArray(options.targets) ? options.targets.length : activity.children.length;
  return (
    <section className="oslo-card">
      <h2>{activity.kind === "TEMPLATE" ? t("tpl.steps") : t("mass.children")}</h2>
      {activity.parent_id === null && (
        <p>
          <a href={`/activities?tab=steps&activity=${activity.id}`}>{t("steps.of_activity")}</a>
        </p>
      )}
      {activity.target_type === "MASS" && (
        <p className="oslo-muted">
          {t("mass.settings_summary", { parallel: String(options.parallel ?? ""), total })}{" "}
          {options.stop_on_error ? t("mass.stop") : t("mass.continue")}
        </p>
      )}
      <p className="oslo-counts">
        {[...counts].map(([status, count]) => (
          <span key={status} className={`oslo-badge oslo-badge-${activityTone(status)}`}>
            {t(`activity.${status}`)} {count}
          </span>
        ))}
      </p>
      {activity.children.length > 0 && (
        <div className="oslo-table-wrap">
          <table className="oslo-table oslo-table-small">
            <thead>
              <tr>
                <th>#</th>
                <th>{t("field.target")}</th>
                <th>{t("field.status")}</th>
                <th>{t("field.finished")}</th>
                <th>{t("field.message")}</th>
              </tr>
            </thead>
            <tbody>
              {activity.children.map((child) => (
                <tr key={child.id}>
                  <td>
                    <a className="oslo-mono" href={`/activities/${child.id}`}>
                      {child.target_type === "MASS" ? activityNumber(child.id) : stepNumber(child.id)}
                    </a>
                  </td>
                  <td>
                    {t(`target.${child.target_type}`)} <span className="oslo-mono">{child.target_label}</span>
                  </td>
                  <td>
                    <span className={`oslo-badge oslo-badge-${activityTone(child.status)}`}>{t(`activity.${child.status}`)}</span>
                  </td>
                  <td className="oslo-muted">{formatTime(child.finished_at, language)}</td>
                  <td className="error-text">{child.error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// --- timeline --------------------------------------------------------------------------

function TimelineView({
  timeline,
  now,
  selected,
  onSelect,
  mass,
}: {
  timeline: Timeline;
  now: number;
  selected: string | null;
  onSelect: (subject: string | null) => void;
  mass: boolean;
}) {
  const { t } = useApp();
  const span = timeline.end - timeline.start;
  // Ticks at quarters; a label that repeats (short activities) is left out.
  const ticks = [0, 0.25, 0.5, 0.75, 1]
    .map((f) => ({ left: f * 100, label: formatDuration(f * span) }))
    .filter((tick, index, all) => index === 0 || tick.label !== all[index - 1].label);
  const nowLeft = timeline.running ? Math.min(((now - timeline.start) / Math.max(span, 1)) * 100, 100) : null;
  return (
    <section className="oslo-card" aria-label={t("ui.timeline")}>
      <h2>{t("ui.timeline")}</h2>
      <div className="oslo-timeline">
        <div />
        <div className="oslo-axis" aria-hidden="true">
          {ticks.map((tick) => (
            <span key={tick.left} style={{ left: `${tick.left}%` }}>
              {tick.label}
            </span>
          ))}
        </div>
        {timeline.lanes.map((lane) => (
          <TimelineLane key={lane.subject} lane={lane} timeline={timeline} now={now} selected={selected === lane.subject} onSelect={onSelect} mass={mass} nowLeft={nowLeft} />
        ))}
      </div>
      <p className="oslo-legend oslo-muted">
        <span>
          <i className="oslo-seg oslo-seg-stop" /> {t("ui.seg_stop")}
        </span>
        <span>
          <i className="oslo-seg oslo-seg-start" /> {t("ui.seg_start")}
        </span>
        <span>
          <i className="oslo-seg oslo-seg-op" /> {t("ui.seg_op")}
        </span>
        <span>
          <i className="oslo-seg oslo-seg-failed" /> {t("ui.seg_failed")}
        </span>
        {!mass && <span>{t("ui.timeline_hint")}</span>}
      </p>
    </section>
  );
}

function TimelineLane({
  lane,
  timeline,
  now,
  selected,
  onSelect,
  mass,
  nowLeft,
}: {
  lane: Timeline["lanes"][number];
  timeline: Timeline;
  now: number;
  selected: boolean;
  onSelect: (subject: string | null) => void;
  mass: boolean;
  nowLeft: number | null;
}) {
  const { t } = useApp();
  const child = lane.segments.find((s) => s.activityId);
  return (
    <>
      <div className="oslo-lane-label">
        {mass && child ? (
          <a href={`/activities/${child.activityId}`} className="oslo-mono">
            {lane.subject}
          </a>
        ) : (
          <button type="button" className={`oslo-mono oslo-lane-button${selected ? " oslo-on" : ""}`} aria-pressed={selected} onClick={() => onSelect(selected ? null : lane.subject)}>
            {lane.subject}
          </button>
        )}
        {lane.status && <span className="oslo-sub">{t(mass ? `activity.${lane.status}` : `status.${lane.status}`)}</span>}
      </div>
      <div className="oslo-lane">
        {lane.segments.map((segment, index) => {
          const { left, width } = place(segment, timeline, now);
          const kind = segment.state === "failed" ? "failed" : segment.kind === "child" ? "op" : segment.kind;
          const label = t(`ui.seg_${segment.kind === "child" ? "op" : segment.kind}`);
          return (
            <span
              key={index}
              className={`oslo-seg oslo-seg-${kind}${segment.state === "running" ? " oslo-seg-running" : ""}`}
              style={{ left: `${left}%`, width: `${width}%` }}
              title={`${label}: ${formatDuration((segment.to ?? now) - segment.from)}`}
            />
          );
        })}
        {nowLeft !== null && <span className="oslo-now" style={{ left: `${nowLeft}%` }} aria-hidden="true" />}
      </div>
    </>
  );
}

// --- log -------------------------------------------------------------------------------

function Log({
  entries,
  running,
  subject,
  onSubject,
  subjects,
}: {
  entries: LogEntry[];
  running: boolean;
  subject: string | null;
  onSubject: (subject: string | null) => void;
  subjects: string[];
}) {
  const { t, language } = useApp();
  const [level, setLevel] = useState<Level>("all");
  const [query, setQuery] = useState("");
  const [follow, setFollow] = useState(true);
  const end = useRef<HTMLDivElement>(null);

  const warnings = entries.filter((e) => e.level === "WARNING").length;
  const errors = entries.filter((e) => e.level === "ERROR").length;
  const shown = entries.filter(
    (e) =>
      (level === "all" || e.level === level) &&
      (!subject || e.subject === subject || (e.data !== null && subject in e.data)) &&
      (!query || e.message.toLowerCase().includes(query.toLowerCase())),
  );

  useEffect(() => {
    if (follow && running) end.current?.scrollIntoView({ block: "nearest" });
  }, [shown.length, follow, running]);

  const chip = (value: Level, label: string) => (
    <button type="button" className={`oslo-filter-chip${level === value ? " oslo-on" : ""}`} aria-pressed={level === value} onClick={() => setLevel(value)}>
      {label}
    </button>
  );

  return (
    <section className="oslo-card" aria-label={t("activity.log")}>
      <div className="oslo-log-head">
        <h2>{t("activity.log")}</h2>
        {chip("all", `${t("ui.log_all")} ${entries.length}`)}
        {chip("WARNING", `${t("ui.log_warnings")} ${warnings}`)}
        {chip("ERROR", `${t("ui.log_errors")} ${errors}`)}
        {subjects.length > 0 && (
          <label className="oslo-inline">
            {t("ui.log_subject")}
            <select value={subject ?? ""} onChange={(e) => onSubject(e.target.value || null)}>
              <option value="">{t("ui.log_all")}</option>
              {subjects.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="oslo-search oslo-inline">
          <span className="oslo-visually-hidden">{t("ui.search")}</span>
          <input type="search" value={query} placeholder={t("ui.log_search")} onChange={(e) => setQuery(e.target.value)} />
        </label>
        {running && (
          <label className="oslo-inline">
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> {t("ui.log_follow")}
          </label>
        )}
      </div>
      <div className="oslo-log" role="log" aria-live={running ? "polite" : "off"}>
        {shown.map((entry) => (
          <div key={entry.id} className={`oslo-log-line oslo-level-${entry.level.toLowerCase()}`}>
            <span className="oslo-muted">{formatTime(entry.timestamp, language, true)}</span>
            <span className="oslo-log-subject">{entry.subject ?? ""}</span>
            <span>{entry.subject && entry.message.startsWith(`${entry.subject}: `) ? entry.message.slice(entry.subject.length + 2) : entry.message}</span>
          </div>
        ))}
        {!shown.length && <p className="oslo-muted">{t("filter.no_match")}</p>}
        <div ref={end} />
      </div>
      {language !== "en" && <p className="oslo-muted">{t("activity.log_language")}</p>}
    </section>
  );
}
