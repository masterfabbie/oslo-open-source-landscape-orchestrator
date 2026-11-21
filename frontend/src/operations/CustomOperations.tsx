// Operations → Custom operations: list, create and edit (definition, flags, parameters,
// context parameters). They run a script configured in operations.d of the host agent.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { ActionForm, ConfirmButton, PageHead, Section, go } from "../lib/forms";
import { useApp } from "../landscape/ui";

const LIST = "/operations/custom";
const TARGETS = ["INSTANCE", "SYSTEM", "HOST"];
const ORDERINGS = ["parallel", "roles", "sequential"];
const TYPES = ["hana", "scs", "ers", "abap", "java", "dual", "agent"];
const ROLES = ["viewer", "operator", "configurator", "admin"];
const PARAMETER_TYPES = ["STRING", "INTEGER", "BOOLEAN"] as const;
// Passed along with the own parameters (see customspec.py and the README).
const INSTANCE_CONTEXT = ["SAPSYSTEMNAME", "SAPSYSTEM", "SAPLOCALHOST", "PHYSICAL_HOSTNAME", "SERVICE_CLASS", "SERVICE_SUBTYPE"];
const HOST_CONTEXT = ["PHYSICAL_HOSTNAME", "RealHostName", "OS_TYPE", "OS_VERSION", "CPUS", "MEMAV"];

interface Parameter {
  name: string;
  label: string;
  type: (typeof PARAMETER_TYPES)[number];
  required: boolean;
  default: string | null;
  pattern: string | null;
  help: string | null;
}

interface CustomOperation {
  id: number;
  key: string;
  name: string;
  description: string | null;
  agent_operation: string;
  target: string;
  instance_types: string[];
  ordering: string;
  role: string;
  mass: boolean;
  locks: boolean;
  standalone: boolean;
  timeout_seconds: number;
  parameters: Parameter[];
}

type Draft = Omit<CustomOperation, "id">;

const EMPTY: Draft = {
  key: "",
  name: "",
  description: "",
  agent_operation: "",
  target: "INSTANCE",
  instance_types: [],
  ordering: "parallel",
  role: "configurator",
  mass: true,
  locks: true,
  standalone: true,
  timeout_seconds: 600,
  parameters: [],
};

export function CustomOperationsPage() {
  const { t } = useApp();
  const { data, isPending } = useQuery({ queryKey: ["custom"], queryFn: () => api<CustomOperation[]>("/custom-operations") });
  return (
    <div className="oslo-page">
      <PageHead title={t("tab.custom_operations")} action={{ href: `${LIST}/new`, label: t("custom.add") }} tabs={[{ href: LIST, label: t("tab.overview"), current: true }]} />
      <p className="oslo-muted">{t("custom.intro")}</p>
      {isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !data?.length ? (
        <p className="oslo-empty">{t("custom.empty")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("field.name")}</th>
                <th>{t("custom.key")}</th>
                <th>{t("custom.agent_operation")}</th>
                <th>{t("field.target")}</th>
                <th>{t("custom.role")}</th>
                <th>{t("custom.parameters")}</th>
                <th>{t("custom.flags")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((op) => (
                <tr key={op.id}>
                  <td>
                    <a className="oslo-strong" href={`${LIST}/${op.id}`}>
                      {op.name}
                    </a>
                    {op.description && <span className="oslo-sub">{op.description}</span>}
                  </td>
                  <td className="oslo-mono">{op.key}</td>
                  <td className="oslo-mono">{op.agent_operation}</td>
                  <td>{t(`target.${op.target}`)}</td>
                  <td>{t(`role.${op.role}`)}</td>
                  <td className="oslo-mono">{op.parameters.map((p) => p.name).join(", ")}</td>
                  <td>
                    {[op.locks ? t("custom.flag_locks") : t("custom.flag_no_lock"), op.standalone ? "" : t("tpl.template_only"), op.mass ? t("custom.flag_mass") : ""]
                      .filter(Boolean)
                      .join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function CustomOperationPage({ id }: { id: number | null }) {
  const { t } = useApp();
  const loaded = useQuery({ queryKey: ["custom", id], queryFn: () => api<CustomOperation>(`/custom-operations/${id}`), enabled: id !== null });
  if (id !== null && loaded.isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (loaded.error) return <p className="flash error">{(loaded.error as Error).message}</p>;
  return <Editor id={id} initial={loaded.data ?? EMPTY} />;
}

function Editor({ id, initial }: { id: number | null; initial: Draft }) {
  const { t } = useApp();
  const [draft, setDraft] = useState<Draft>({ ...initial, description: initial.description ?? "" });
  const set = (next: Partial<Draft>) => setDraft({ ...draft, ...next });
  const setParameter = (index: number, next: Partial<Parameter>) =>
    set({ parameters: draft.parameters.map((p, i) => (i === index ? { ...p, ...next } : p)) });
  const context = draft.target === "HOST" ? HOST_CONTEXT : INSTANCE_CONTEXT;

  const save = async () => {
    const body = {
      ...draft,
      description: draft.description || null,
      parameters: draft.parameters.map((p) => ({ ...p, default: p.default || null, pattern: p.pattern || null, help: p.help || null })),
    };
    if (id === null) {
      const created = await api<CustomOperation>("/custom-operations", { method: "POST", body });
      go(`${LIST}/${created.id}`, "operation_saved");
    } else {
      await api(`/custom-operations/${id}`, { method: "PUT", body });
    }
  };

  return (
    <div className="oslo-page">
      <PageHead
        title={id === null ? t("custom.add") : draft.name}
        crumbs={[{ href: LIST, label: t("tab.custom_operations") }]}
        extra={
          id !== null && (
            <ConfirmButton
              label={t("custom.delete")}
              confirm={t("custom.delete_confirm")}
              onConfirm={async () => {
                await api(`/custom-operations/${id}`, { method: "DELETE" });
                go(LIST, "operation_deleted");
              }}
            />
          )
        }
      />
      {id === null && <p className="oslo-muted">{t("custom.intro")}</p>}
      <ActionForm submit={t("action.save")} onSubmit={save}>
        <Section title={t("system.general")}>
          <div className="oslo-form-grid">
            <label className="oslo-field">
              {t("field.name")}
              <input value={draft.name} required maxLength={128} placeholder={t("custom.name_hint")} onChange={(e) => set({ name: e.target.value })} />
            </label>
            <label className="oslo-field">
              {t("custom.key")}
              <input value={draft.key} required maxLength={64} pattern="[a-z][a-z0-9_]*" className="oslo-mono" placeholder="copy_kernel" onChange={(e) => set({ key: e.target.value })} />
            </label>
            <label className="oslo-field">
              {t("custom.agent_operation")}
              <input value={draft.agent_operation} required maxLength={128} pattern="[A-Za-z0-9_.\-]+" className="oslo-mono" onChange={(e) => set({ agent_operation: e.target.value })} />
            </label>
            <label className="oslo-field">
              {t("field.target")}
              <select value={draft.target} onChange={(e) => set({ target: e.target.value })}>
                {TARGETS.map((x) => (
                  <option key={x} value={x}>
                    {t(`target.${x}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="oslo-field">
              {t("custom.ordering")}
              <select value={draft.ordering} onChange={(e) => set({ ordering: e.target.value })}>
                {ORDERINGS.map((o) => (
                  <option key={o} value={o}>
                    {t(`custom.ordering.${o}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="oslo-field">
              {t("custom.role")}
              <select value={draft.role} onChange={(e) => set({ role: e.target.value })}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {t(`role.${r}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="oslo-field">
              {t("custom.timeout")}
              <input type="number" min={10} max={86400} required value={draft.timeout_seconds} onChange={(e) => set({ timeout_seconds: Number(e.target.value) })} />
            </label>
            <label className="oslo-field">
              {t("field.description")}
              <input value={draft.description ?? ""} maxLength={1000} onChange={(e) => set({ description: e.target.value })} />
            </label>
          </div>
          <fieldset className="oslo-checks">
            <legend>{t("custom.instance_types")}</legend>
            {TYPES.map((type) => (
              <label key={type} className="oslo-inline">
                <input
                  type="checkbox"
                  checked={draft.instance_types.includes(type)}
                  onChange={(e) => set({ instance_types: e.target.checked ? [...draft.instance_types, type] : draft.instance_types.filter((x) => x !== type) })}
                />
                {t(`itype.${type}`)}
              </label>
            ))}
          </fieldset>
          <p className="oslo-muted">{t("custom.instance_types_hint")}</p>
          <div className="oslo-checks">
            <label className="oslo-inline">
              <input type="checkbox" checked={draft.mass} onChange={(e) => set({ mass: e.target.checked })} /> {t("custom.mass")}
            </label>
            <label className="oslo-inline">
              <input type="checkbox" checked={draft.locks} onChange={(e) => set({ locks: e.target.checked })} /> {t("custom.locks")}
            </label>
            <label className="oslo-inline">
              <input type="checkbox" checked={!draft.standalone} onChange={(e) => set({ standalone: !e.target.checked })} /> {t("custom.template_only")}
            </label>
          </div>
          <p className="oslo-muted">{t("custom.flags_hint")}</p>
          <p className="oslo-muted">{t("custom.agent_hint")}</p>
        </Section>

        <Section title={t("custom.parameters")} hint={t("custom.parameters_intro")}>
          {!draft.parameters.length && <p className="oslo-muted">{t("custom.no_parameters")}</p>}
          {draft.parameters.map((p, index) => (
            <div key={index} className="oslo-param-row">
              <div className="oslo-form-grid">
                <label className="oslo-field">
                  {t("custom.parameter_name")}
                  <input value={p.name} required maxLength={64} pattern="[A-Z0-9][A-Z0-9_]*" className="oslo-mono" onChange={(e) => setParameter(index, { name: e.target.value.toUpperCase() })} />
                  <small className="oslo-mono">PARAM-{p.name}</small>
                </label>
                <label className="oslo-field">
                  {t("custom.parameter_label")}
                  <input value={p.label} required maxLength={128} onChange={(e) => setParameter(index, { label: e.target.value })} />
                </label>
                <label className="oslo-field">
                  {t("custom.parameter_type")}
                  <select value={p.type} onChange={(e) => setParameter(index, { type: e.target.value as Parameter["type"] })}>
                    {PARAMETER_TYPES.map((x) => (
                      <option key={x} value={x}>
                        {t(`custom.type.${x}`)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="oslo-field">
                  {t("custom.default")}
                  <input value={p.default ?? ""} maxLength={255} onChange={(e) => setParameter(index, { default: e.target.value })} />
                </label>
                <label className="oslo-field">
                  {t("custom.pattern")}
                  <input value={p.pattern ?? ""} maxLength={255} className="oslo-mono" placeholder="[A-Za-z0-9._-]*" disabled={p.type !== "STRING"} onChange={(e) => setParameter(index, { pattern: e.target.value })} />
                </label>
                <label className="oslo-field">
                  {t("custom.help")}
                  <input value={p.help ?? ""} onChange={(e) => setParameter(index, { help: e.target.value })} />
                </label>
              </div>
              <div className="oslo-form-buttons">
                <label className="oslo-inline">
                  <input type="checkbox" checked={p.required} onChange={(e) => setParameter(index, { required: e.target.checked })} /> {t("custom.required")}
                </label>
                <button type="button" className="link" disabled={index === 0} onClick={() => set({ parameters: swap(draft.parameters, index, index - 1) })}>
                  ↑
                </button>
                <button type="button" className="link" disabled={index === draft.parameters.length - 1} onClick={() => set({ parameters: swap(draft.parameters, index, index + 1) })}>
                  ↓
                </button>
                <button type="button" className="link" onClick={() => set({ parameters: draft.parameters.filter((_, i) => i !== index) })}>
                  {t("custom.parameter_delete")}
                </button>
              </div>
            </div>
          ))}
          <div>
            <button
              type="button"
              className="oslo-secondary"
              onClick={() => set({ parameters: [...draft.parameters, { name: "", label: "", type: "STRING", required: false, default: "", pattern: "", help: "" }] })}
            >
              {t("custom.parameter_add")}
            </button>
          </div>
          <p className="oslo-muted">{t("custom.parameters_hint")}</p>
        </Section>

        <Section title={t("custom.context")} hint={t("custom.context_intro")}>
          <p className="oslo-mono">{context.join(", ")}</p>
        </Section>
      </ActionForm>
    </div>
  );
}

function swap<T>(list: T[], a: number, b: number): T[] {
  const next = [...list];
  [next[a], next[b]] = [next[b], next[a]];
  return next;
}
