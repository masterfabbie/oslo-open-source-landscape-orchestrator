// Operations → Schedules: every planned run of every operation and template, with filters,
// the status of the last run and deleting several at once; and the page to plan or change
// one (any operation of the catalog, its targets and parameter values, once / daily / every
// N minutes). Needs an operator; the server checks the role of the operation again when the
// run is due.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { ActionForm, ConfirmButton, PageHead, Section, go } from "../lib/forms";
import { hasRole } from "../lib/i18n";
import { describeSchedule } from "../lib/schedules";
import type { Parameter, ScheduleRow, Snapshot, TargetType } from "../lib/types";
import { formatTime, useApp, useLiveUpdates } from "../landscape/ui";

const LIST = "/operations/schedules";
// Colors of the last run's status.
const RUN_BADGE: Record<string, string> = {
  SUCCEEDED: "green",
  PARTIAL: "yellow",
  FAILED: "red",
  CANCELLED: "gray",
  RUNNING: "running",
  PENDING: "running",
};
const DAYS = ["1", "2", "3", "4", "5", "6", "7"];

/** An operation as /api/operations lists it. */
interface CatalogOperation {
  key: string;
  name: string | null;
  targets: TargetType[];
  mass: boolean;
  custom: boolean;
  standalone: boolean;
  parameters: Parameter[];
}

function useCatalog() {
  const operations = useQuery({ queryKey: ["operations"], queryFn: () => api<CatalogOperation[]>("/operations") });
  const landscape = useQuery({ queryKey: ["landscape"], queryFn: () => api<Snapshot>("/landscape") });
  return { operations, landscape };
}

/** Names of the targets the landscape knows, per target type. */
function targetNames(snapshot: Snapshot | undefined): Record<TargetType, Map<number, string>> {
  return {
    SYSTEM: new Map((snapshot?.systems ?? []).map((s) => [s.id, s.name])),
    // The label already names the host when SID/number exist on several hosts.
    INSTANCE: new Map((snapshot?.systems ?? []).flatMap((s) => s.instances.map((i) => [i.id, i.label.includes("(") ? i.label : `${i.label} (${i.host.name})`] as [number, string]))),
    HOST: new Map((snapshot?.hosts ?? []).map((h) => [h.id, h.name])),
  };
}

function operationName(op: { key: string; name: string | null } | undefined, key: string, t: (k: string) => string): string {
  return op?.name ?? t(`op.${key}`);
}

// --- list ---------------------------------------------------------------------------------

/** "planned", "paused" or "expired" (a single run that is over, or nothing due any more). */
function nextState(s: ScheduleRow): "planned" | "paused" | "expired" {
  if (!s.enabled) return "paused";
  return s.next_run_at ? "planned" : "expired";
}

export function SchedulesPage() {
  const { t, language, role } = useApp();
  const queries = useQueryClient();
  useLiveUpdates(["schedules"]);
  const schedules = useQuery({ queryKey: ["schedules", "all"], queryFn: () => api<ScheduleRow[]>("/schedules") });
  const clock = useQuery({ queryKey: ["server-time"], queryFn: () => api<{ now: string; timezone: string }>("/server-time"), refetchInterval: 60_000 });
  const { operations, landscape } = useCatalog();
  const ops = new Map((operations.data ?? []).map((o) => [o.key, o]));
  const names = targetNames(landscape.data);
  const operator = hasRole(role, "operator");

  const [text, setText] = useState("");
  const [operation, setOperation] = useState("");
  const [last, setLast] = useState("");
  const [next, setNext] = useState("");
  const [selected, setSelected] = useState<number[]>([]);

  const label = (s: ScheduleRow) => s.name || operationName(ops.get(s.operation), s.operation, t);
  const targetsOf = (s: ScheduleRow) => {
    const map = s.target_type ? names[s.target_type] : null;
    return map ? s.target_ids.map((id) => map.get(id) ?? `#${id}`).join(", ") : t("tpl.fixed_targets");
  };
  const rows = useMemo(() => {
    const words = text.trim().toLowerCase();
    return (schedules.data ?? []).filter(
      (s) =>
        (!operation || s.operation === operation) &&
        (!last || (last === "never" ? !s.last_run_at : s.last_status === last)) &&
        (!next || nextState(s) === next) &&
        (!words || `${label(s)} ${operationName(ops.get(s.operation), s.operation, t)} ${targetsOf(s)} ${s.created_by}`.toLowerCase().includes(words)),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schedules.data, operations.data, landscape.data, text, operation, last, next]);
  const used = [...new Set((schedules.data ?? []).map((s) => s.operation))];
  const chosen = selected.filter((id) => rows.some((r) => r.id === id));

  const toggle = async (s: ScheduleRow) => {
    const { id, created_by: _by, next_run_at: _n, last_run_at: _l, last_activity_id: _a, last_error: _e, last_status: _s, ...body } = s;
    await api(`/schedules/${id}`, { method: "PUT", body: { ...body, enabled: !s.enabled } });
    await queries.invalidateQueries({ queryKey: ["schedules"] });
  };

  return (
    <div className="oslo-page">
      <PageHead
        title={t("tab.schedules")}
        action={operator ? { href: `${LIST}/new`, label: t("sched.new") } : undefined}
        extra={
          operator && chosen.length > 0 ? (
            <ConfirmButton
              label={t("sched.delete_selected", { count: chosen.length })}
              confirm={t("sched.delete_selected_confirm", { count: chosen.length })}
              onConfirm={async () => {
                for (const id of chosen) await api(`/schedules/${id}`, { method: "DELETE" });
                setSelected([]);
                await queries.invalidateQueries({ queryKey: ["schedules"] });
              }}
            />
          ) : undefined
        }
        tabs={[{ href: LIST, label: t("tab.overview"), current: true }]}
      />
      <p className="oslo-muted">
        {clock.data && t("sched.clock", { zone: clock.data.timezone, time: formatTime(clock.data.now, language, true) })}
      </p>
      <div className="oslo-form-buttons">
        <input className="oslo-filter-input" type="search" value={text} placeholder={t("ui.search")} aria-label={t("ui.search")} onChange={(e) => setText(e.target.value)} />
        <label className="oslo-inline">
          {t("sched.operation")}
          <select value={operation} onChange={(e) => setOperation(e.target.value)}>
            <option value="">{t("pool.all")}</option>
            {used.map((key) => (
              <option key={key} value={key}>
                {operationName(ops.get(key), key, t)}
              </option>
            ))}
          </select>
        </label>
        <label className="oslo-inline">
          {t("sched.last_run")}
          <select value={last} onChange={(e) => setLast(e.target.value)}>
            <option value="">{t("pool.all")}</option>
            {["SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED", "RUNNING"].map((x) => (
              <option key={x} value={x}>
                {t(`activity.${x}`)}
              </option>
            ))}
            <option value="never">{t("sched.never_run")}</option>
          </select>
        </label>
        <label className="oslo-inline">
          {t("sched.next_run")}
          <select value={next} onChange={(e) => setNext(e.target.value)}>
            <option value="">{t("pool.all")}</option>
            {(["planned", "paused", "expired"] as const).map((x) => (
              <option key={x} value={x}>
                {t(`sched.state.${x}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {schedules.isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !rows.length ? (
        <p className="oslo-empty">{t("sched.list_empty")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <caption className="oslo-table-caption">{t("sched.count", { count: rows.length })}</caption>
            <thead>
              <tr>
                {operator && (
                  <th className="oslo-check">
                    <input
                      type="checkbox"
                      aria-label={t("ui.select_all")}
                      checked={chosen.length === rows.length}
                      onChange={(e) => setSelected(e.target.checked ? rows.map((r) => r.id) : [])}
                    />
                  </th>
                )}
                <th>{t("sched.name")}</th>
                <th>{t("sched.operation")}</th>
                <th>{t("sched.targets")}</th>
                <th>{t("sched.next_run")}</th>
                <th>{t("sched.last_run")}</th>
                <th>{t("sched.recurrence")}</th>
                <th>{t("sched.planned_by")}</th>
                {operator && <th />}
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => {
                const state = nextState(s);
                return (
                  <tr key={s.id}>
                    {operator && (
                      <td className="oslo-check">
                        <input type="checkbox" aria-label={label(s)} checked={chosen.includes(s.id)} onChange={(e) => setSelected(e.target.checked ? [...chosen, s.id] : chosen.filter((x) => x !== s.id))} />
                      </td>
                    )}
                    <td className="oslo-strong">{operator ? <a href={`${LIST}/${s.id}`}>{label(s)}</a> : label(s)}</td>
                    <td>{operationName(ops.get(s.operation), s.operation, t)}</td>
                    <td>{targetsOf(s)}</td>
                    <td>{state === "planned" ? formatTime(s.next_run_at, language) : <span className={`oslo-badge oslo-badge-${state === "paused" ? "yellow" : "gray"}`}>{t(`sched.state.${state}`)}</span>}</td>
                    <td>
                      {s.last_run_at ? (
                        <>
                          {s.last_status ? (
                            <a className={`oslo-badge oslo-badge-${RUN_BADGE[s.last_status] ?? "unknown"}`} href={`/activities/${s.last_activity_id}`}>
                              {t(`activity.${s.last_status}`)}
                            </a>
                          ) : (
                            <span className={`oslo-badge oslo-badge-${s.last_error ? "red" : "unknown"}`}>{t(s.last_error ? "sched.not_started" : "sched.unknown_run")}</span>
                          )}
                          <span className="oslo-sub">{formatTime(s.last_run_at, language)}</span>
                        </>
                      ) : (
                        <span className="oslo-muted">{t("sched.never_run")}</span>
                      )}
                      {s.last_error && <span className="oslo-sub error-text">{s.last_error}</span>}
                    </td>
                    <td>{describeSchedule(s, t, language)}</td>
                    <td className="oslo-muted">{s.created_by}</td>
                    {operator && (
                      <td>
                        <button type="button" className="link" onClick={() => void toggle(s)}>
                          {s.enabled ? t("sched.pause") : t("sched.resume")}
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// --- plan or change -----------------------------------------------------------------------

/** "2026-11-22T06:30" in local time, as a datetime-local input wants it. */
function localInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function SchedulePage({ id }: { id?: number }) {
  const { t } = useApp();
  const existing = useQuery({ queryKey: ["schedules", id], queryFn: () => api<ScheduleRow>(`/schedules/${id}`), enabled: id !== undefined });
  const { operations, landscape } = useCatalog();
  if ((id !== undefined && existing.isPending) || operations.isPending || landscape.isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (existing.error || operations.error || landscape.error) return <p className="flash error">{((existing.error ?? operations.error ?? landscape.error) as Error).message}</p>;
  return <ScheduleForm schedule={existing.data} operations={operations.data ?? []} snapshot={landscape.data as Snapshot} />;
}

function ScheduleForm({ schedule, operations, snapshot }: { schedule?: ScheduleRow; operations: CatalogOperation[]; snapshot: Snapshot }) {
  const { t, timezone } = useApp();
  const choices = operations.filter((o) => o.standalone).sort((a, b) => operationName(a, a.key, t).localeCompare(operationName(b, b.key, t)));
  const [name, setName] = useState(schedule?.name ?? "");
  const [key, setKey] = useState(schedule?.operation ?? "");
  const op = choices.find((o) => o.key === key);
  const [targetType, setTargetType] = useState<TargetType | "">(schedule?.target_type ?? "");
  // Systems first, then instances, then hosts, when an operation runs on several kinds.
  const kinds = op ? (["SYSTEM", "INSTANCE", "HOST"] as const).filter((x) => op.targets.includes(x)) : [];
  const type: TargetType | "" = op ? (kinds.includes(targetType as TargetType) ? (targetType as TargetType) : (kinds[0] ?? "")) : "";
  const [targets, setTargets] = useState<number[]>(schedule?.target_ids ?? []);
  const [values, setValues] = useState<Record<string, string | number | boolean>>(schedule?.parameters ?? {});
  const [recurrence, setRecurrence] = useState<ScheduleRow["recurrence"]>(schedule?.recurrence ?? "once");
  const [runAt, setRunAt] = useState(localInput(schedule?.run_at ?? null));
  const [time, setTime] = useState(schedule?.time_of_day ?? "22:00");
  const [weekdays, setWeekdays] = useState(schedule?.weekdays ?? "12345");
  const [interval, setIntervalMinutes] = useState(schedule?.interval_minutes ?? 60);
  const [enabled, setEnabled] = useState(schedule?.enabled ?? true);

  const names = targetNames(snapshot)[type || "SYSTEM"];
  const chosen = type ? targets.filter((id) => names.has(id)) : [];
  const isTemplate = op !== undefined && !op.custom && (op.targets.length === 0 || snapshot.operations.some((o) => o.key === op.key && o.template));
  const problem = !op ? t("sched.choose_operation") : type && !chosen.length ? t("sched.choose_targets") : type && chosen.length > 1 && !op.mass ? t("sched.one_target") : null;

  const pick = (next: string) => {
    setKey(next);
    setTargets([]);
    setTargetType("");
  };

  return (
    <div className="oslo-page">
      <PageHead
        title={schedule ? t("sched.edit") : t("sched.new")}
        crumbs={[{ href: LIST, label: t("tab.schedules") }]}
        extra={
          schedule && (
            <ConfirmButton
              label={t("sched.delete")}
              confirm={t("sched.delete_confirm")}
              onConfirm={async () => {
                await api(`/schedules/${schedule.id}`, { method: "DELETE" });
                go(LIST, "schedule_deleted");
              }}
            />
          )
        }
      />
      <Section hint={t("sched.intro")}>
        <ActionForm
          submit={schedule ? t("action.save") : t("sched.plan")}
          onSubmit={async () => {
            if (problem) throw new Error(problem);
            const body = {
              name: name.trim() || null,
              operation: key,
              target_type: type,
              target_ids: type ? chosen : [],
              parameters: values,
              recurrence,
              run_at: recurrence === "once" && runAt ? new Date(runAt).toISOString() : null,
              time_of_day: recurrence === "daily" ? time : null,
              weekdays,
              interval_minutes: recurrence === "interval" ? interval : null,
              enabled,
            };
            await api(schedule ? `/schedules/${schedule.id}` : "/schedules", { method: schedule ? "PUT" : "POST", body });
            go(LIST, "schedule_saved");
          }}
        >
          <div className="oslo-form-grid">
            <label className="oslo-field">
              {t("sched.name")}
              <input value={name} maxLength={128} placeholder={op ? operationName(op, op.key, t) : ""} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="oslo-field">
              {t("sched.operation")}
              <select value={key} required onChange={(e) => pick(e.target.value)}>
                <option value="">{t("sched.choose_operation")}</option>
                {choices.map((o) => (
                  <option key={o.key} value={o.key}>
                    {operationName(o, o.key, t)}
                  </option>
                ))}
              </select>
            </label>
            {op && op.targets.length > 1 && (
              <label className="oslo-field">
                {t("field.type")}
                <select
                  value={type}
                  onChange={(e) => {
                    setTargetType(e.target.value as TargetType);
                    setTargets([]);
                  }}
                >
                  {kinds.map((x) => (
                    <option key={x} value={x}>
                      {t(`target.${x}`)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {op && !type && <p className="oslo-muted">{t("sched.fixed")}</p>}
          {op && type && (
            <fieldset className="oslo-checks">
              <legend>{`${t("sched.targets")}: ${t(`target.${type}`)}`}</legend>
              {[...names].map(([id, name]) => (
                <label key={id} className="oslo-inline">
                  <input type="checkbox" checked={chosen.includes(id)} onChange={(e) => setTargets(e.target.checked ? [...chosen, id] : chosen.filter((c) => c !== id))} />
                  {name}
                </label>
              ))}
            </fieldset>
          )}

          {op?.parameters.length ? (
            <div className="oslo-form-grid">
              {op.parameters.map((p) =>
                p.type === "BOOLEAN" ? (
                  <label key={p.name} className="oslo-inline">
                    <input type="checkbox" checked={values[p.name] === true || (values[p.name] === undefined && p.default === "true")} onChange={(e) => setValues({ ...values, [p.name]: e.target.checked })} />
                    {p.label}
                  </label>
                ) : (
                  <label key={p.name} className="oslo-field">
                    {p.label}
                    <input
                      type={p.type === "INTEGER" ? "number" : "text"}
                      value={String(values[p.name] ?? "")}
                      required={p.required}
                      placeholder={p.default ?? ""}
                      onChange={(e) => setValues({ ...values, [p.name]: p.type === "INTEGER" && e.target.value !== "" ? Number(e.target.value) : e.target.value })}
                    />
                    {p.help && <small>{p.help}</small>}
                  </label>
                ),
              )}
            </div>
          ) : null}
          {isTemplate && <p className="oslo-muted">{t("sched.template_values")}</p>}

          <div className="oslo-segmented" role="radiogroup" aria-label={t("sched.recurrence")}>
            {(["once", "daily", "interval"] as const).map((r) => (
              <button key={r} type="button" role="radio" aria-checked={recurrence === r} className={recurrence === r ? "oslo-on" : undefined} onClick={() => setRecurrence(r)}>
                {t(`sched.${r}`)}
              </button>
            ))}
          </div>
          {recurrence === "once" && (
            <label className="oslo-field">
              {t("sched.when")}
              <input type="datetime-local" value={runAt} required onChange={(e) => setRunAt(e.target.value)} />
            </label>
          )}
          {recurrence === "daily" && (
            <>
              <label className="oslo-field">
                {t("sched.time")}
                <input type="time" value={time} required onChange={(e) => setTime(e.target.value)} />
              </label>
              <fieldset className="oslo-checks">
                <legend>{t("sched.weekdays")}</legend>
                {DAYS.map((d) => (
                  <label key={d} className="oslo-inline">
                    <input
                      type="checkbox"
                      checked={weekdays.includes(d)}
                      onChange={(e) =>
                        setWeekdays(
                          (e.target.checked ? weekdays + d : weekdays.replace(d, ""))
                            .split("")
                            .sort()
                            .join(""),
                        )
                      }
                    />
                    {t(`sched.day.${d}`)}
                  </label>
                ))}
              </fieldset>
              <p className="oslo-muted">{t("sched.timezone_hint", { zone: timezone ?? "" })}</p>
            </>
          )}
          {recurrence === "interval" && (
            <label className="oslo-field">
              {t("sched.interval")}
              <input type="number" min={5} value={interval} onChange={(e) => setIntervalMinutes(Number(e.target.value))} />
            </label>
          )}
          <label className="oslo-inline">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> {t("sched.enabled")}
          </label>
          {problem && op && <p className="oslo-muted">{problem}</p>}
        </ActionForm>
      </Section>
    </div>
  );
}
