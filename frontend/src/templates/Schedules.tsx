// Schedules of one operation (here: a template): once, daily at a time on weekdays, or
// every N minutes. They run with the rights of the user who planned them. A template with
// fixed targets only is planned without targets; one on the selection with its targets.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { ApiError, api } from "../lib/api";
import { describeSchedule } from "../lib/schedules";
import type { ScheduleRow, Snapshot, TargetType } from "../lib/types";
import { formatTime, fromInputValue, timesInUtc, useApp } from "../landscape/ui";

const DAYS = ["1", "2", "3", "4", "5", "6", "7"];

interface Props {
  operation: string;
  // Type of the selection; null: the template has fixed targets only.
  selection: TargetType | null;
  snapshot: Snapshot;
  disabled?: boolean;
}

export function Schedules({ operation, selection, snapshot, disabled }: Props) {
  const { t, language, timezone } = useApp();
  const queries = useQueryClient();
  const key = ["schedules", operation];
  const { data } = useQuery({ queryKey: key, queryFn: () => api<ScheduleRow[]>(`/schedules?operation=${operation}`) });
  const targets =
    selection === "SYSTEM"
      ? snapshot.systems.map((s) => ({ id: s.id, name: s.name }))
      : selection === "HOST"
        ? snapshot.hosts.map((h) => ({ id: h.id, name: h.name }))
        : selection === "INSTANCE"
          ? snapshot.systems.flatMap((s) => s.instances.map((i) => ({ id: i.id, name: `${i.label} (${i.host.name})` })))
          : [];
  const names = new Map(targets.map((x) => [x.id, x.name]));

  const [chosen, setChosen] = useState<number[]>([]);
  const [recurrence, setRecurrence] = useState<ScheduleRow["recurrence"]>("once");
  const [runAt, setRunAt] = useState("");
  const [time, setTime] = useState("22:00");
  const [weekdays, setWeekdays] = useState("12345");
  const [interval, setIntervalMinutes] = useState(60);
  const [error, setError] = useState<string | null>(null);

  const describe = (s: ScheduleRow) => describeSchedule(s, t, language);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const body = {
      operation,
      target_type: selection ?? "",
      target_ids: selection ? chosen : [],
      recurrence,
      run_at: recurrence === "once" && runAt ? fromInputValue(runAt) : null,
      time_of_day: recurrence === "daily" ? time : null,
      weekdays,
      interval_minutes: recurrence === "interval" ? interval : null,
      enabled: true,
    };
    try {
      await api("/schedules", { method: "POST", body });
      setChosen([]);
      await queries.invalidateQueries({ queryKey: key });
    } catch (exc) {
      const e = exc as ApiError;
      setError(e.code ? `${t(`error.${e.code}`)} ${e.message}` : e.message);
    }
  };

  const toggle = async (s: ScheduleRow) => {
    const { id, created_by: _by, next_run_at: _n, last_run_at: _l, last_activity_id: _a, last_error: _e, ...body } = s;
    await api(`/schedules/${id}`, { method: "PUT", body: { ...body, enabled: !s.enabled } });
    await queries.invalidateQueries({ queryKey: key });
  };
  const remove = async (s: ScheduleRow) => {
    if (!window.confirm(t("sched.delete_confirm"))) return;
    await api(`/schedules/${s.id}`, { method: "DELETE" });
    await queries.invalidateQueries({ queryKey: key });
  };

  return (
    <section className="oslo-card oslo-schedule" aria-label={t("sched.title")}>
      <h2>{t("sched.title")}</h2>
      {data && data.length > 0 ? (
        <ul className="oslo-schedule-list">
          {data.map((s) => (
            <li key={s.id} className={s.enabled ? undefined : "oslo-off"}>
              <span className="oslo-strong">{s.target_ids.length ? s.target_ids.map((id) => names.get(id) ?? `#${id}`).join(", ") : t("tpl.fixed_targets")}</span>
              <span>{describe(s)}</span>
              <span className="oslo-muted">
                {s.next_run_at ? t("sched.next", { time: formatTime(s.next_run_at, language) }) : t("sched.none_next")}
                {s.last_run_at && " · "}
                {s.last_run_at && (s.last_activity_id ? <a href={`/activities/${s.last_activity_id}`}>{t("sched.last", { time: formatTime(s.last_run_at, language) })}</a> : t("sched.last", { time: formatTime(s.last_run_at, language) }))}
                {` · ${s.created_by}`}
              </span>
              {s.last_error && <span className="error-text">{s.last_error}</span>}
              <span className="oslo-schedule-tools">
                <button type="button" className="link" onClick={() => void toggle(s)}>
                  {s.enabled ? t("sched.pause") : t("sched.resume")}
                </button>
                <button type="button" className="link" onClick={() => void remove(s)}>
                  {t("sched.delete")}
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="oslo-muted">{t("sched.empty")}</p>
      )}

      <form onSubmit={submit} className="oslo-schedule-form">
        <h3>{t("sched.add")}</h3>
        {disabled && <p className="oslo-muted">{t("sched.save_first")}</p>}
        {selection && (
        <fieldset>
          <legend>{t(`target.${selection}`)}</legend>
          <div className="oslo-target-list">
            {targets.map((x) => (
              <label key={x.id} className="oslo-inline">
                <input
                  type="checkbox"
                  checked={chosen.includes(x.id)}
                  onChange={(e) => setChosen(e.target.checked ? [...chosen, x.id] : chosen.filter((c) => c !== x.id))}
                />
                {x.name}
              </label>
            ))}
          </div>
        </fieldset>
        )}
        <div className="oslo-segmented" role="radiogroup" aria-label={t("sched.recurrence")}>
          {(["once", "daily", "interval"] as const).map((r) => (
            <button key={r} type="button" role="radio" aria-checked={recurrence === r} className={recurrence === r ? "oslo-on" : undefined} onClick={() => setRecurrence(r)}>
              {t(`sched.${r}`)}
            </button>
          ))}
        </div>
        {recurrence === "once" && (
          <label>
            {timesInUtc() ? t("time.input_utc") : t("sched.when")}
            <input type="datetime-local" value={runAt} required onChange={(e) => setRunAt(e.target.value)} />
          </label>
        )}
        {recurrence === "daily" && (
          <>
            <label>
              {t("sched.time")}
              <input type="time" value={time} required onChange={(e) => setTime(e.target.value)} />
            </label>
            <div className="oslo-target-list" aria-label={t("sched.weekdays")}>
              {DAYS.map((d) => (
                <label key={d} className="oslo-inline">
                  <input
                    type="checkbox"
                    checked={weekdays.includes(d)}
                    onChange={(e) => setWeekdays((e.target.checked ? weekdays + d : weekdays.replace(d, "")).split("").sort().join(""))}
                  />
                  {t(`sched.day.${d}`)}
                </label>
              ))}
            </div>
            <p className="oslo-muted">{t("sched.timezone_hint", { zone: timezone ?? "" })}</p>
          </>
        )}
        {recurrence === "interval" && (
          <label>
            {t("sched.interval")}
            <input type="number" min={5} value={interval} onChange={(e) => setIntervalMinutes(Number(e.target.value))} />
          </label>
        )}
        {error && (
          <p className="flash error" role="alert">
            {error}
          </p>
        )}
        <div>
          <button type="submit" className="oslo-primary" disabled={disabled || (selection !== null && !chosen.length)}>
            {t("sched.plan")}
          </button>
        </div>
      </form>
    </section>
  );
}
