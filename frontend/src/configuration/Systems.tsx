// Configuration → Systems: the systems with their instances, the unassigned instances,
// creating a system and the page of a system (general data with stage, pool, tags,
// instances, dependencies, credentials per SID, delete).

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { RecentChanges } from "../lib/changes";
import { ActionForm, ConfirmButton, CredentialsForm, Messages, PageHead, Section, TagsForm, go, useAction } from "../lib/forms";
import { StatusBadge, useApp } from "../landscape/ui";
import { type InstanceInfo, type PoolInfo, STAGES, type SidInfo, type SystemInfo } from "./types";

const LIST = "/configuration/systems";

/** Main instances in their order, then the diagnostics agents by label. */
function splitAgents(instances: InstanceInfo[]): { main: InstanceInfo[]; agents: InstanceInfo[] } {
  return {
    main: instances.filter((i) => i.role !== "agent"),
    agents: instances.filter((i) => i.role === "agent").sort((a, b) => a.label.localeCompare(b.label)),
  };
}

/** Systems in alphabetical order, regardless of case. */
function byName<T extends { name: string }>(list: T[] | undefined): T[] {
  return [...(list ?? [])].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base", numeric: true }));
}

function useSystemsData() {
  const systems = useQuery({ queryKey: ["systems"], queryFn: async () => byName(await api<SystemInfo[]>("/systems")) });
  const instances = useQuery({ queryKey: ["instances"], queryFn: () => api<InstanceInfo[]>("/instances") });
  const pools = useQuery({ queryKey: ["pools"], queryFn: () => api<PoolInfo[]>("/pools") });
  const hosts = useQuery({ queryKey: ["hosts"], queryFn: () => api<{ id: number; name: string }[]>("/hosts") });
  return { systems, instances, pools, hosts };
}

function SystemTabs({ current, unassigned }: { current: "overview" | "unassigned"; unassigned: number }) {
  const { t } = useApp();
  return (
    <PageHead
      title={t("tab.systems")}
      action={{ href: `${LIST}/new`, label: t("system.create") }}
      tabs={[
        { href: LIST, label: t("tab.overview"), current: current === "overview" },
        { href: `${LIST}/unassigned`, label: `${t("tab.unassigned")} (${unassigned})`, current: current === "unassigned" },
      ]}
    />
  );
}

function InstanceType({ instance }: { instance: InstanceInfo }) {
  const { t } = useApp();
  return <>{instance.type_key ? t(instance.type_key) : (instance.features ?? "")}</>;
}

export function SystemsPage() {
  const { t } = useApp();
  const { systems, instances, pools, hosts } = useSystemsData();
  const [open, setOpen] = useState<Set<number>>(new Set());
  // Systems whose diagnostics agents are shown (closed at first).
  const [openAgents, setOpenAgents] = useState<Set<number>>(new Set());
  const poolName = new Map((pools.data ?? []).map((p) => [p.id, p.name]));
  const hostName = new Map((hosts.data ?? []).map((h) => [h.id, h.name]));
  const unassigned = (instances.data ?? []).filter((i) => i.system_id === null).length;
  const toggle = (id: number) => {
    const next = new Set(open);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpen(next);
  };
  return (
    <div className="oslo-page">
      <SystemTabs current="overview" unassigned={unassigned} />
      <p className="oslo-muted">{t("config.systems_hint")}</p>
      {systems.isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !systems.data?.length ? (
        <p className="oslo-empty">{t("config.no_systems")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th className="oslo-expand" aria-label={t("ui.expand")} />
                <th>{t("field.name")}</th>
                <th>{t("field.stage")}</th>
                <th>{t("field.pool")}</th>
                <th>{t("field.instances")}</th>
                <th>{t("deps.depends_on")}</th>
                <th>{t("field.tags")}</th>
              </tr>
            </thead>
            <tbody>
              {systems.data.map((s) => (
                <Fragment key={s.id}>
                  <tr>
                    <td className="oslo-expand">
                      <button type="button" aria-expanded={open.has(s.id)} aria-label={s.name} onClick={() => toggle(s.id)}>
                        {open.has(s.id) ? "▾" : "▸"}
                      </button>
                    </td>
                    <td>
                      <a className="oslo-strong" href={`${LIST}/${s.id}`}>
                        {s.name}
                      </a>
                      {s.description && <span className="oslo-sub">{s.description}</span>}
                    </td>
                    <td>{s.stage ? t(`stage.${s.stage}`) : <span className="oslo-muted">{t("stage.none")}</span>}</td>
                    <td>{s.pool_id ? poolName.get(s.pool_id) : <span className="oslo-muted">{t("pool.none")}</span>}</td>
                    <td>{s.instances.length}</td>
                    <td>{s.depends_on_ids.map((d) => systems.data.find((x) => x.id === d)?.name ?? `#${d}`).join(", ")}</td>
                    <td>{s.tags.join(", ")}</td>
                  </tr>
                  {open.has(s.id) &&
                    (() => {
                      const { main, agents } = splitAgents(s.instances);
                      const row = (i: InstanceInfo) => (
                        <tr key={`i${i.id}`} className="oslo-nested">
                          <td />
                          <td className="oslo-mono">{i.label}</td>
                          <td colSpan={2}>
                            <InstanceType instance={i} />
                          </td>
                          <td>{hostName.get(i.host_id) ?? ""}</td>
                          <td colSpan={2}>
                            <StatusBadge status={i.last_status} />
                          </td>
                        </tr>
                      );
                      const agentsOpen = openAgents.has(s.id);
                      return (
                        <>
                          {main.map(row)}
                          {agents.length > 0 && (
                            <tr className="oslo-nested">
                              <td />
                              <td colSpan={6}>
                                <button
                                  type="button"
                                  className="link"
                                  aria-expanded={agentsOpen}
                                  onClick={() => {
                                    const next = new Set(openAgents);
                                    if (agentsOpen) next.delete(s.id);
                                    else next.add(s.id);
                                    setOpenAgents(next);
                                  }}
                                >
                                  {agentsOpen ? "▾" : "▸"} {t("agents.group")} ({agents.length})
                                </button>
                              </td>
                            </tr>
                          )}
                          {agentsOpen && agents.map(row)}
                        </>
                      );
                    })()}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="oslo-muted">{t("system.depends_hint")}</p>
    </div>
  );
}

export function UnassignedPage() {
  const { t } = useApp();
  const queries = useQueryClient();
  const { systems, instances, hosts } = useSystemsData();
  const [chosen, setChosen] = useState<number[]>([]);
  const [target, setTarget] = useState<number | "">("");
  const action = useAction();
  const hostName = new Map((hosts.data ?? []).map((h) => [h.id, h.name]));
  const systemName = new Map((systems.data ?? []).map((s) => [s.id, s.name]));
  const rows = (instances.data ?? []).filter((i) => i.system_id === null);
  const assign = (systemId: number, ids: number[]) =>
    action.run(async () => {
      await api(`/systems/${systemId}/instances`, { method: "POST", body: { instance_ids: ids } });
      setChosen([]);
      await queries.invalidateQueries();
    }, t("notice.instances_assigned"));

  return (
    <div className="oslo-page">
      <SystemTabs current="unassigned" unassigned={rows.length} />
      <Messages error={action.error} notice={action.notice} />
      {instances.isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !rows.length ? (
        <p className="oslo-empty">{t("unassigned.none")}</p>
      ) : (
        <>
          <div className="oslo-table-wrap">
            <table className="oslo-table">
              <thead>
                <tr>
                  <th>{t("unassigned.select")}</th>
                  <th>{t("field.instance")}</th>
                  <th>{t("field.sid")}</th>
                  <th>{t("field.type")}</th>
                  <th>{t("field.host")}</th>
                  <th>{t("field.status")}</th>
                  <th>{t("unassigned.suggestion")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={i.label}
                        checked={chosen.includes(i.id)}
                        onChange={(e) => setChosen(e.target.checked ? [...chosen, i.id] : chosen.filter((c) => c !== i.id))}
                      />
                    </td>
                    <td className="oslo-mono">{i.label}</td>
                    <td className="oslo-mono">{i.sid}</td>
                    <td>
                      <InstanceType instance={i} />
                    </td>
                    <td>{hostName.get(i.host_id) ?? ""}</td>
                    <td>
                      <StatusBadge status={i.last_status} />
                    </td>
                    <td>
                      {i.suggested_system_id && (
                        <button type="button" className="link" disabled={action.busy} onClick={() => void assign(i.suggested_system_id as number, [i.id])}>
                          {t("unassigned.assign_to", { name: systemName.get(i.suggested_system_id) ?? "" })}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="oslo-form-buttons">
            <a
              className={`button-primary${chosen.length ? "" : " oslo-disabled"}`}
              aria-disabled={!chosen.length}
              href={`${LIST}/new?${chosen.map((c) => `instance_id=${c}`).join("&")}`}
            >
              {t("system.create")}
            </a>
            {(systems.data?.length ?? 0) > 0 && (
              <>
                <label className="oslo-inline">
                  {t("field.system")}
                  <select value={target} onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : "")}>
                    <option value="">–</option>
                    {systems.data?.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="button" className="oslo-secondary" disabled={!chosen.length || target === "" || action.busy} onClick={() => target !== "" && void assign(target, chosen)}>
                  {t("system.assign")}
                </button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export function SystemNewPage() {
  const { t } = useApp();
  const { instances, pools, hosts } = useSystemsData();
  const preselected = useMemo(() => new URLSearchParams(window.location.search).getAll("instance_id").map(Number), []);
  const [chosen, setChosen] = useState<number[]>(preselected);
  const [name, setName] = useState("");
  const [named, setNamed] = useState(false);
  const [description, setDescription] = useState("");
  const [pool, setPool] = useState<number | "">("");
  const [stage, setStage] = useState("");
  const hostName = new Map((hosts.data ?? []).map((h) => [h.id, h.name]));
  const rows = (instances.data ?? []).filter((i) => i.system_id === null);

  // The name follows the suggestion (SID of the application instances) until it is typed.
  useEffect(() => {
    if (named || !chosen.length) return;
    const query = chosen.map((c) => `instance_ids=${c}`).join("&");
    void api<{ name: string }>(`/systems/suggestion?${query}`).then((s) => setName(s.name));
  }, [chosen, named]);

  return (
    <div className="oslo-page">
      <PageHead title={t("system.create_title")} crumbs={[{ href: LIST, label: t("tab.systems") }]} />
      <Section>
        {instances.isPending ? (
          <p className="oslo-muted">{t("ui.loading")}</p>
        ) : !rows.length ? (
          <p>{t("system.create_none")}</p>
        ) : (
          <ActionForm
            submit={t("system.create_title")}
            onSubmit={async () => {
              const system = await api<SystemInfo>("/systems", {
                method: "POST",
                body: { name: name.trim(), description: description || null, instance_ids: chosen, pool_id: pool === "" ? null : pool },
              });
              if (stage) await api(`/systems/${system.id}`, { method: "PATCH", body: { name: system.name, description: system.description, stage } });
              go(`${LIST}/${system.id}`, "system_saved");
            }}
          >
            <p className="oslo-muted">{t("system.create_hint")}</p>
            <div className="oslo-form-grid">
              <label className="oslo-field">
                {t("field.name")}
                <input
                  value={name}
                  required
                  maxLength={64}
                  onChange={(e) => {
                    setName(e.target.value);
                    setNamed(true);
                  }}
                />
              </label>
              <label className="oslo-field">
                {t("field.description")}
                <input value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} />
              </label>
              <label className="oslo-field">
                {t("field.pool")}
                <select value={pool} onChange={(e) => setPool(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">{t("pool.none")}</option>
                  {pools.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <StageField value={stage} onChange={setStage} />
            </div>
            <h3>{t("system.choose_instances")}</h3>
            <div className="oslo-table-wrap">
              <table className="oslo-table oslo-compact">
                <thead>
                  <tr>
                    <th>{t("unassigned.select")}</th>
                    <th>{t("field.instance")}</th>
                    <th>{t("field.type")}</th>
                    <th>{t("field.host")}</th>
                    <th>{t("field.status")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((i) => (
                    <tr key={i.id}>
                      <td>
                        <input type="checkbox" aria-label={i.label} checked={chosen.includes(i.id)} onChange={(e) => setChosen(e.target.checked ? [...chosen, i.id] : chosen.filter((c) => c !== i.id))} />
                      </td>
                      <td className="oslo-mono">{i.label}</td>
                      <td>
                        <InstanceType instance={i} />
                      </td>
                      <td>{hostName.get(i.host_id) ?? ""}</td>
                      <td>
                        <StatusBadge status={i.last_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </ActionForm>
        )}
      </Section>
    </div>
  );
}

function StageField({ value, onChange }: { value: string; onChange: (stage: string) => void }) {
  const { t } = useApp();
  return (
    <label className="oslo-field">
      {t("field.stage")}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("stage.none")}</option>
        {STAGES.map((s) => (
          <option key={s} value={s}>
            {t(`stage.${s}`)}
          </option>
        ))}
      </select>
    </label>
  );
}

export function SystemPage({ id }: { id: number }) {
  const { t } = useApp();
  const queries = useQueryClient();
  const key = ["system", id];
  const { data: system, isPending, error } = useQuery({ queryKey: key, queryFn: () => api<SystemInfo>(`/systems/${id}`) });
  const { systems, pools, hosts } = useSystemsData();
  const sids = useQuery({ queryKey: ["sids"], queryFn: () => api<SidInfo[]>("/sids") });
  const remove = useAction();
  const reload = async () => {
    await queries.invalidateQueries({ queryKey: key });
    await queries.invalidateQueries({ queryKey: ["systems"] });
    await queries.invalidateQueries({ queryKey: ["sids"] });
  };

  if (isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (error || !system) return <p className="flash error">{(error as Error)?.message}</p>;
  const hostName = new Map((hosts.data ?? []).map((h) => [h.id, h.name]));
  const others = (systems.data ?? []).filter((s) => s.id !== id);
  const systemSids = (sids.data ?? []).filter((s) => system.instances.some((i) => i.sid_id === s.id));

  return (
    <div className="oslo-page">
      <PageHead
        title={`${t("field.system")} ${system.name}`}
        crumbs={[{ href: LIST, label: t("tab.systems") }]}
        extra={
          <>
            <a className="button-link" href={`/landscape?system=${id}`}>
              {t("action.view")}
            </a>
            <ConfirmButton
              label={t("system.delete")}
              confirm={t("system.delete_confirm")}
              onConfirm={async () => {
                await api(`/systems/${id}`, { method: "DELETE" });
                go(LIST, "system_deleted");
              }}
            />
          </>
        }
      />
      <div className="oslo-two">
        <Section title={t("system.general")}>
          <GeneralForm system={system} onSaved={reload} />
        </Section>
        <Section title={t("field.pool")} hint={t("pool.explanation")}>
          <PoolForm system={system} pools={pools.data ?? []} onSaved={reload} />
        </Section>
        <Section title={t("field.tags")}>
          <TagsForm
            tags={system.tags}
            onSave={async (tags) => {
              await api(`/systems/${id}/tags`, { method: "PUT", body: { tags } });
              await reload();
            }}
          />
        </Section>
        <Section title={t("deps.title")} hint={t("deps.explanation")}>
          <DependenciesForm system={system} others={others} onSaved={reload} />
          {system.required_by_ids.length > 0 && (
            <p>
              {t("deps.required_by")}:{" "}
              {system.required_by_ids.map((r, i) => (
                <span key={r}>
                  {i > 0 && ", "}
                  <a href={`${LIST}/${r}`}>{others.find((o) => o.id === r)?.name ?? `#${r}`}</a>
                </span>
              ))}
              <span className="oslo-sub">{t("deps.required_note")}</span>
            </p>
          )}
        </Section>
      </div>
      <Section title={t("field.instances")}>
        <Messages error={remove.error} />
        {!system.instances.length ? (
          <p className="oslo-muted">{t("system.no_instances")}</p>
        ) : (
          (() => {
            const { main, agents } = splitAgents(system.instances);
            const table = (list: InstanceInfo[]) => (
              <div className="oslo-table-wrap">
                <table className="oslo-table oslo-compact">
                  <thead>
                    <tr>
                      <th>{t("field.instance")}</th>
                      <th>{t("field.type")}</th>
                      <th>{t("field.host")}</th>
                      <th>{t("field.priority")}</th>
                      <th>{t("field.status")}</th>
                      <th>{t("field.actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((i) => (
                      <tr key={i.id}>
                        <td className="oslo-mono">{i.label}</td>
                        <td>
                          <InstanceType instance={i} />
                        </td>
                        <td>{hostName.get(i.host_id) ?? ""}</td>
                        <td className="oslo-mono">{i.start_priority ?? ""}</td>
                        <td>
                          <StatusBadge status={i.last_status} />
                        </td>
                        <td>
                          <button
                            type="button"
                            className="link"
                            disabled={remove.busy}
                            onClick={() => {
                              if (window.confirm(t("system.remove_instance_confirm")))
                                void remove.run(async () => {
                                  await api(`/systems/${id}/instances/${i.id}`, { method: "DELETE" });
                                  await reload();
                                  await queries.invalidateQueries({ queryKey: ["instances"] });
                                });
                            }}
                          >
                            {t("system.remove_instance")}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
            return (
              <>
                {main.length > 0 && table(main)}
                {agents.length > 0 && (
                  <details className="oslo-agent-group">
                    <summary>
                      {t("agents.group")} ({agents.length})
                    </summary>
                    <p className="oslo-muted">{t("agents.hint")}</p>
                    {table(agents)}
                  </details>
                )}
              </>
            );
          })()
        )}
        <p>
          <a href={`${LIST}/unassigned`}>{t("unassigned.title")}</a>
        </p>
      </Section>
      <Section title={t("credentials.per_sid")} hint={t("credentials.sid_hint")}>
        {systemSids.map((sid) => (
          <div key={sid.id} className="oslo-form-section">
            <h3 className="oslo-mono">{sid.name}</h3>
            <CredentialsForm
              username={sid.username}
              hasCredentials={sid.has_credentials}
              hint={sid.has_credentials ? undefined : t("credentials.host_used")}
              onSave={async (body) => {
                await api(`/sids/${sid.id}/credentials`, { method: "PUT", body });
                await reload();
              }}
            />
          </div>
        ))}
      </Section>
      <RecentChanges type="system" id={id} />
    </div>
  );
}

function GeneralForm({ system, onSaved }: { system: SystemInfo; onSaved: () => Promise<unknown> }) {
  const { t } = useApp();
  const [name, setName] = useState(system.name);
  const [description, setDescription] = useState(system.description ?? "");
  const [stage, setStage] = useState(system.stage ?? "");
  return (
    <ActionForm
      submit={t("action.save")}
      onSubmit={async () => {
        await api(`/systems/${system.id}`, { method: "PATCH", body: { name: name.trim(), description: description || null, stage: stage || null } });
        await onSaved();
      }}
    >
      <div className="oslo-form-grid">
        <label className="oslo-field">
          {t("field.name")}
          <input value={name} required maxLength={64} onChange={(e) => setName(e.target.value)} />
        </label>
        <StageField value={stage} onChange={setStage} />
      </div>
      <label className="oslo-field">
        {t("field.description")}
        <input value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} />
      </label>
    </ActionForm>
  );
}

function PoolForm({ system, pools, onSaved }: { system: SystemInfo; pools: PoolInfo[]; onSaved: () => Promise<unknown> }) {
  const { t } = useApp();
  const [pool, setPool] = useState<number | "">(system.pool_id ?? "");
  if (!pools.length)
    return (
      <p className="oslo-muted">
        {t("pool.none_defined")} <a href="/configuration/pools/new">{t("pool.add")}</a>
      </p>
    );
  return (
    <ActionForm
      submit={t("action.save")}
      onSubmit={async () => {
        await api(`/systems/${system.id}/pool`, { method: "PUT", body: { pool_id: pool === "" ? null : pool } });
        await onSaved();
      }}
    >
      <label className="oslo-field">
        {t("field.pool")}
        <select value={pool} onChange={(e) => setPool(e.target.value ? Number(e.target.value) : "")}>
          <option value="">{t("pool.none")}</option>
          {pools.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
    </ActionForm>
  );
}

function DependenciesForm({ system, others, onSaved }: { system: SystemInfo; others: SystemInfo[]; onSaved: () => Promise<unknown> }) {
  const { t } = useApp();
  const [chosen, setChosen] = useState<number[]>(system.depends_on_ids);
  if (!others.length) return <p className="oslo-muted">{t("deps.no_candidates")}</p>;
  return (
    <ActionForm
      submit={t("action.save")}
      onSubmit={async () => {
        await api(`/systems/${system.id}/dependencies`, { method: "PUT", body: { depends_on: chosen } });
        await onSaved();
      }}
    >
      <fieldset className="oslo-checks">
        <legend>{t("deps.depends_on")}</legend>
        {others.map((o) => (
          <label key={o.id} className="oslo-inline">
            <input type="checkbox" checked={chosen.includes(o.id)} onChange={(e) => setChosen(e.target.checked ? [...chosen, o.id] : chosen.filter((c) => c !== o.id))} />
            {o.name}
          </label>
        ))}
      </fieldset>
    </ActionForm>
  );
}
