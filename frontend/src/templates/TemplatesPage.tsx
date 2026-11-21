// Operation templates: a list, and the editor of one template. The steps form a graph like
// in LaMa: a step starts when its predecessors have finished, steps side by side run in
// parallel. Each step has its operation (chosen by search, favorites, most used), fixed
// targets or the "$selection" of the run, its parameter values (fixed or asked for at the
// start) and its behavior on error. A template with fixed targets only runs as it is (e.g.
// scheduled); one on the selection is started from the landscape.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type Edge, type Node, type NodeProps, Handle, Position, ReactFlow, ReactFlowProvider, useReactFlow } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../lib/api";
import type { BuildingBlocks, OperationDef, Snapshot, Template, TemplateStep, TargetType } from "../lib/types";
import { useApp } from "../landscape/ui";
import { NODE_HEIGHT, NODE_WIDTH, addStep, canConnect, connect, disconnect, layout, removeStep, selectionType } from "./graph";
import { OperationPicker, preferredTarget } from "./OperationPicker";
import { Schedules } from "./Schedules";

type Draft = Omit<Template, "id" | "valid" | "selection"> & { id: number | null };

const EMPTY: Draft = { id: null, key: "", name: "", description: "", role: "operator", steps: [] };
const ROLES = ["viewer", "operator", "configurator", "admin"];

function currentId(): number | "new" | null {
  const params = new URLSearchParams(window.location.search);
  if (params.get("new") !== null) return "new";
  const id = Number(params.get("id"));
  return id > 0 ? id : null;
}

export function TemplatesPage() {
  const [selected, setSelected] = useState(currentId);
  const open = (id: number | "new" | null) => {
    const query = id === null ? "" : id === "new" ? "?new" : `?id=${id}`;
    window.history.pushState(null, "", `${window.location.pathname}${query}`);
    setSelected(id);
  };
  useEffect(() => {
    const onPop = () => setSelected(currentId());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return selected === null ? <TemplateList onOpen={open} /> : <Editor id={selected} onOpen={open} />;
}

function selectionText(selection: string | null, t: (k: string, v?: Record<string, string | number>) => string) {
  return selection ? t("tpl.on_selection", { type: t(`target.${selection}`) }) : t("tpl.fixed_targets");
}

// --- list ------------------------------------------------------------------------------

function TemplateList({ onOpen }: { onOpen: (id: number | "new") => void }) {
  const { t } = useApp();
  const { data, isPending } = useQuery({ queryKey: ["templates"], queryFn: () => api<Template[]>("/templates") });
  return (
    <div className="oslo-templates">
      <div className="page-head">
        <h1>{t("tpl.title")}</h1>
        <span className="buttons">
          <a
            className="button-primary"
            href="?new"
            onClick={(event) => {
              event.preventDefault();
              onOpen("new");
            }}
          >
            {t("tpl.new")}
          </a>
        </span>
      </div>
      <nav className="tabs" aria-label={t("tpl.title")}>
        <a href={window.location.pathname} aria-current="page">
          {t("tab.overview")}
        </a>
      </nav>
      <p className="oslo-muted">{t("tpl.intro")}</p>
      {isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !data?.length ? (
        <p className="oslo-empty">{t("tpl.empty")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("field.name")}</th>
                <th>{t("custom.key")}</th>
                <th>{t("field.target")}</th>
                <th>{t("tpl.steps")}</th>
                <th>{t("custom.role")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((tpl) => (
                <tr key={tpl.id}>
                  <td>
                    <button type="button" className="oslo-open" onClick={() => onOpen(tpl.id)}>
                      {tpl.name}
                    </button>
                    {!tpl.valid && <span className="oslo-sub error-text">{t("tpl.invalid")}</span>}
                    {tpl.description && <span className="oslo-sub">{tpl.description}</span>}
                  </td>
                  <td className="oslo-mono">{tpl.key}</td>
                  <td>{selectionText(tpl.selection, t)}</td>
                  <td>{tpl.steps.length}</td>
                  <td>{t(`role.${tpl.role}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// --- editor ----------------------------------------------------------------------------

type EditorTab = "general" | "steps" | "schedules";

/** Names of the possible targets of each type, from the landscape. */
function targetNames(snapshot: Snapshot | undefined): Record<TargetType, Map<number, string>> {
  const instances = new Map<number, string>();
  for (const system of snapshot?.systems ?? []) {
    for (const i of system.instances) instances.set(i.id, `${i.label} (${i.host.name})`);
  }
  return {
    SYSTEM: new Map((snapshot?.systems ?? []).map((s) => [s.id, s.name])),
    INSTANCE: instances,
    HOST: new Map((snapshot?.hosts ?? []).map((h) => [h.id, h.name])),
  };
}

function errorText(exc: unknown, t: (k: string) => string): string {
  const e = exc as ApiError;
  return e.code ? `${t(`error.${e.code}`)} ${e.message}` : e.message;
}

function Editor({ id, onOpen }: { id: number | "new"; onOpen: (id: number | "new" | null) => void }) {
  const { t } = useApp();
  const queries = useQueryClient();
  const landscape = useQuery({ queryKey: ["landscape"], queryFn: () => api<Snapshot>("/landscape") });
  const blocks = useQuery({ queryKey: ["blocks"], queryFn: () => api<BuildingBlocks>("/templates-blocks") });
  const loaded = useQuery({ queryKey: ["template", id], queryFn: () => api<Template>(`/templates/${id}`), enabled: id !== "new" });
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState<EditorTab>(id === "new" ? "general" : "steps");
  const [current, setCurrent] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (id === "new") setDraft(EMPTY);
    else if (loaded.data) setDraft({ ...loaded.data, description: loaded.data.description ?? "" });
    setDirty(false);
  }, [id, loaded.data]);

  const operations = useMemo(() => new Map((blocks.data?.operations ?? []).map((op) => [op.key, op])), [blocks.data]);
  const names = useMemo(() => targetNames(landscape.data), [landscape.data]);
  const change = (next: Partial<Draft>) => {
    setDraft((d) => ({ ...d, ...next }));
    setDirty(true);
  };
  const setSteps = (steps: TemplateStep[]) => change({ steps });
  const selection = selectionType(draft.steps);

  const save = async () => {
    setSaving(true);
    setError(null);
    setNotice(null);
    const body = {
      key: draft.key,
      name: draft.name,
      description: draft.description || null,
      role: draft.role,
      steps: draft.steps.map((s) => ({
        position: s.position,
        operation: s.operation,
        target_type: s.target_type,
        targets: s.targets,
        after: s.after,
        ask: s.ask,
        on_error: s.on_error,
        parameters: Object.fromEntries(Object.entries(s.parameters).filter(([, v]) => v !== "")),
      })),
    };
    try {
      const saved =
        draft.id === null
          ? await api<Template>("/templates", { method: "POST", body })
          : await api<Template>(`/templates/${draft.id}`, { method: "PUT", body });
      await queries.invalidateQueries({ queryKey: ["templates"] });
      await queries.invalidateQueries({ queryKey: ["landscape"] });
      queries.setQueryData(["template", saved.id], saved);
      setDirty(false);
      if (draft.id === null) onOpen(saved.id);
      else setDraft({ ...saved, description: saved.description ?? "" });
    } catch (exc) {
      setError(errorText(exc, t));
    } finally {
      setSaving(false);
    }
  };

  const destroy = async () => {
    if (draft.id === null || !window.confirm(t("tpl.delete_confirm"))) return;
    try {
      await api(`/templates/${draft.id}`, { method: "DELETE" });
      await queries.invalidateQueries({ queryKey: ["templates"] });
      onOpen(null);
    } catch (exc) {
      setError(errorText(exc, t));
    }
  };

  const toggleFavorite = async (key: string) => {
    const favorites = blocks.data?.favorites ?? [];
    const next = favorites.includes(key) ? favorites.filter((f) => f !== key) : [...favorites, key];
    const saved = await api<BuildingBlocks>("/me/favorites", { method: "PUT", body: { operations: next } });
    queries.setQueryData(["blocks"], saved);
  };

  if (id !== "new" && loaded.isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  const tabs: [EditorTab, string][] = [
    ["general", t("tab.general")],
    ["steps", t("tpl.steps_tab", { count: draft.steps.length })],
  ];
  if (draft.id !== null) tabs.push(["schedules", t("sched.title")]);

  return (
    <div className="oslo-templates">
      <p className="crumbs">
        <a
          href="?"
          onClick={(event) => {
            event.preventDefault();
            if (!dirty || window.confirm(t("tpl.discard"))) onOpen(null);
          }}
        >
          {t("tpl.title")}
        </a>
      </p>
      <div className="page-head">
        <h1>{draft.name || t("tpl.new_title")}</h1>
        <span className="oslo-muted">{dirty ? t("tpl.unsaved") : draft.id !== null ? t("tpl.saved") : ""}</span>
        <span className="buttons">
          {draft.id !== null && (
            <button type="button" className="oslo-danger-outline" onClick={destroy}>
              {t("tpl.delete")}
            </button>
          )}
          {draft.id !== null && selection === null && (
            <button type="button" className="oslo-secondary" disabled={dirty} onClick={() => setRunning(true)}>
              {t("tpl.run")}
            </button>
          )}
          <button type="button" className="oslo-primary" onClick={save} disabled={saving || !dirty}>
            {t("action.save")}
          </button>
        </span>
      </div>
      <nav className="tabs" aria-label={draft.name || t("tpl.new_title")}>
        {tabs.map(([key, label]) => (
          <a
            key={key}
            href={`#${key}`}
            aria-current={tab === key ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              setTab(key);
            }}
          >
            {label}
          </a>
        ))}
      </nav>
      {error && (
        <p className="flash error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="flash notice" role="status">
          {notice}
        </p>
      )}
      <p className="oslo-muted oslo-selection-note">
        {selection === "mixed" ? (
          <span className="error-text">{t("tpl.selection_mixed")}</span>
        ) : (
          `${selectionText(selection, t)} · ${t(selection === null ? "tpl.fixed_hint" : "tpl.selection_hint")}`
        )}
      </p>

      {tab === "general" && (
        <section className="oslo-card oslo-fields-row">
          <label>
            {t("field.name")}
            <input value={draft.name} maxLength={128} onChange={(e) => change({ name: e.target.value })} />
          </label>
          <label>
            {t("custom.key")}
            <input value={draft.key} maxLength={64} pattern="[a-z][a-z0-9_]*" className="oslo-mono" placeholder="kernel_update" onChange={(e) => change({ key: e.target.value })} />
          </label>
          <label>
            {t("custom.role")}
            <select value={draft.role} onChange={(e) => change({ role: e.target.value })}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`role.${r}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="oslo-wide">
            {t("field.description")}
            <input value={draft.description ?? ""} maxLength={1000} onChange={(e) => change({ description: e.target.value })} />
          </label>
        </section>
      )}

      {tab === "steps" && (
        <ReactFlowProvider>
          <StepsEditor
            steps={draft.steps}
            operations={operations}
            blocks={blocks.data}
            names={names}
            snapshot={landscape.data}
            current={current}
            onCurrent={setCurrent}
            onSteps={setSteps}
            onToggleFavorite={(key) => void toggleFavorite(key)}
          />
        </ReactFlowProvider>
      )}

      {tab === "schedules" && draft.id !== null && landscape.data && (
        <Schedules operation={draft.key} selection={selection === "mixed" ? null : (selection as TargetType | null)} snapshot={landscape.data} disabled={dirty} />
      )}

      {running && draft.id !== null && (
        <RunDialog
          template={draft}
          operations={operations}
          onClose={() => setRunning(false)}
          onStarted={(activity) => {
            setRunning(false);
            setNotice(null);
            window.location.href = `/activities/${activity}`;
          }}
        />
      )}
    </div>
  );
}

// --- steps: graph and panel ---------------------------------------------------------------

interface StepsProps {
  steps: TemplateStep[];
  operations: Map<string, OperationDef>;
  blocks: BuildingBlocks | undefined;
  names: Record<TargetType, Map<number, string>>;
  snapshot: Snapshot | undefined;
  current: number | null;
  onCurrent: (position: number | null) => void;
  onSteps: (steps: TemplateStep[]) => void;
  onToggleFavorite: (key: string) => void;
}

type Picking = { mode: "add"; after: number | null } | { mode: "change"; position: number };

interface StepNodeData extends Record<string, unknown> {
  step: TemplateStep;
  title: string;
  target: string;
  selected: boolean;
  connecting: boolean;
  invalid: boolean;
  onAdd: () => void;
  onConnect: () => void;
  onRemove: () => void;
}

function StepNode({ data }: NodeProps<Node<StepNodeData>>) {
  const { t } = useApp();
  const { step, title, target, selected, connecting, invalid } = data;
  return (
    <div className={`oslo-node${selected ? " oslo-on" : ""}${connecting ? " oslo-connecting" : ""}${invalid ? " oslo-invalid" : ""}`}>
      <Handle type="target" position={Position.Top} />
      <span className="oslo-node-number" aria-label={t("tpl.step_number", { n: step.position })}>
        {step.position}
      </span>
      <span className="oslo-node-title">{title}</span>
      <span className="oslo-node-target">{target}</span>
      {step.on_error !== "stop" && <span className="oslo-node-flag">{t(`tpl.on_error.${step.on_error}`)}</span>}
      <Handle type="source" position={Position.Bottom} />
      {selected && (
        <span className="oslo-node-tools nodrag">
          <button type="button" aria-label={t("tpl.add_after")} title={t("tpl.add_after")} onClick={data.onAdd}>
            +
          </button>
          <button type="button" aria-label={t("tpl.connect")} title={t("tpl.connect")} onClick={data.onConnect}>
            →
          </button>
          <button type="button" aria-label={t("tpl.remove")} title={t("tpl.remove")} onClick={data.onRemove}>
            🗑
          </button>
        </span>
      )}
    </div>
  );
}

const NODE_TYPES = { step: StepNode };

function stepTitle(step: TemplateStep, operations: Map<string, OperationDef>, t: (k: string) => string): string {
  const op = operations.get(step.operation);
  if (!op) return step.name ?? step.operation;
  if (op.custom) return op.name ?? op.key;
  return t(op.labels[step.target_type] ?? `op.${op.key}`);
}

function targetSummary(step: TemplateStep, names: Record<TargetType, Map<number, string>>, t: (k: string, v?: Record<string, string | number>) => string): string {
  if (!step.targets.length) return t("tpl.selection_placeholder", { type: t(`target.${step.target_type}`) });
  const labels = step.targets.map((id) => names[step.target_type].get(id) ?? step.target_labels?.find((l) => l.id === id)?.label ?? `#${id}`);
  return labels.length > 2 ? `${labels.slice(0, 2).join(", ")} +${labels.length - 2}` : labels.join(", ");
}

function StepsEditor({ steps, operations, blocks, names, snapshot, current, onCurrent, onSteps, onToggleFavorite }: StepsProps) {
  const { t } = useApp();
  const flow = useReactFlow();
  const [picking, setPicking] = useState<Picking | null>(null);
  const [connectFrom, setConnectFrom] = useState<number | null>(null);

  const positions = useMemo(() => layout(steps), [steps]);
  const nodes: Node<StepNodeData>[] = steps.map((step) => ({
    id: String(step.position),
    type: "step",
    position: positions.get(step.position) ?? { x: 0, y: 0 },
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    draggable: false,
    deletable: false,
    data: {
      step,
      title: stepTitle(step, operations, t),
      target: targetSummary(step, names, t),
      selected: current === step.position,
      connecting: connectFrom !== null && canConnect(steps, connectFrom, step.position),
      invalid: !operations.has(step.operation),
      onAdd: () => setPicking({ mode: "add", after: step.position }),
      onConnect: () => setConnectFrom(step.position),
      onRemove: () => {
        onSteps(removeStep(steps, step.position));
        onCurrent(null);
      },
    },
  }));
  const edges: Edge[] = steps.flatMap((step) =>
    step.after.map((from) => ({ id: `${from}-${step.position}`, source: String(from), target: String(step.position) })),
  );

  const count = steps.length;
  useEffect(() => {
    const timer = window.setTimeout(() => void flow.fitView({ padding: 0.25, maxZoom: 1 }), 30);
    return () => window.clearTimeout(timer);
  }, [count, flow]);

  const pick = (op: OperationDef) => {
    const target = preferredTarget(op);
    if (picking?.mode === "change") {
      onSteps(
        steps.map((s) =>
          s.position === picking.position
            ? { ...s, operation: op.key, target_type: op.targets.includes(s.target_type) ? s.target_type : target, targets: op.targets.includes(s.target_type) ? s.targets : [], parameters: {}, ask: [] }
            : s,
        ),
      );
    } else if (picking) {
      const previous = steps.find((s) => s.position === picking.after);
      // A new step runs on the same kind of target as the one before, if it can.
      const type = previous && op.targets.includes(previous.target_type) ? previous.target_type : target;
      const added = addStep(steps, { operation: op.key, target_type: type, targets: [], parameters: {}, ask: [], on_error: "stop" }, picking.after);
      onSteps(added.steps);
      onCurrent(added.position);
    }
    setPicking(null);
  };

  const onNodeClick = useCallback(
    (_: unknown, node: Node) => {
      const position = Number(node.id);
      if (connectFrom !== null) {
        if (canConnect(steps, connectFrom, position)) onSteps(connect(steps, connectFrom, position));
        setConnectFrom(null);
        return;
      }
      onCurrent(position);
    },
    [connectFrom, steps, onSteps, onCurrent],
  );

  const step = steps.find((s) => s.position === current);
  return (
    <div className="oslo-graph-editor">
      <div className="oslo-graph" aria-label={t("tpl.steps")}>
        {connectFrom !== null && (
          <p className="oslo-graph-hint" role="status">
            {t("tpl.connect_hint", { n: connectFrom })}{" "}
            <button type="button" className="link" onClick={() => setConnectFrom(null)}>
              {t("mass.cancel")}
            </button>
          </p>
        )}
        {!steps.length ? (
          <div className="oslo-graph-empty">
            <p className="oslo-muted">{t("tpl.graph_empty")}</p>
            <button type="button" className="oslo-primary" onClick={() => setPicking({ mode: "add", after: null })}>
              {t("tpl.add_first")}
            </button>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            nodesDraggable={false}
            nodesConnectable
            elementsSelectable
            onNodeClick={onNodeClick}
            onPaneClick={() => {
              setConnectFrom(null);
              onCurrent(null);
            }}
            onConnect={(c) => {
              if (c.source && c.target) onSteps(connect(steps, Number(c.source), Number(c.target)));
            }}
            isValidConnection={(c) => !!c.source && !!c.target && canConnect(steps, Number(c.source), Number(c.target))}
            onEdgesDelete={(deleted) => {
              let next = steps;
              for (const e of deleted) next = disconnect(next, Number(e.source), Number(e.target));
              onSteps(next);
            }}
            deleteKeyCode={["Delete", "Backspace"]}
            proOptions={{ hideAttribution: true }}
            minZoom={0.3}
            maxZoom={1.5}
            fitView
          />
        )}
        {steps.length > 0 && (
          <div className="oslo-graph-actions">
            <button type="button" className="oslo-secondary" onClick={() => setPicking({ mode: "add", after: null })}>
              {t("tpl.add_parallel")}
            </button>
            <span className="oslo-muted">{t("tpl.graph_hint")}</span>
          </div>
        )}
      </div>
      <aside className="oslo-step-editor" aria-label={t("tpl.step")}>
        {step ? (
          <StepPanel
            key={step.position}
            step={step}
            steps={steps}
            operation={operations.get(step.operation)}
            operations={operations}
            snapshot={snapshot}
            names={names}
            onChange={(next) => onSteps(steps.map((s) => (s.position === step.position ? next : s)))}
            onChangeOperation={() => setPicking({ mode: "change", position: step.position })}
          />
        ) : (
          <p className="oslo-muted oslo-card">{t("tpl.choose_step")}</p>
        )}
      </aside>
      {picking && blocks && (
        <OperationPicker
          operations={blocks.operations}
          top={blocks.top}
          favorites={blocks.favorites}
          onToggleFavorite={onToggleFavorite}
          onPick={pick}
          onClose={() => setPicking(null)}
        />
      )}
    </div>
  );
}

interface PanelProps {
  step: TemplateStep;
  steps: TemplateStep[];
  operation: OperationDef | undefined;
  operations: Map<string, OperationDef>;
  snapshot: Snapshot | undefined;
  names: Record<TargetType, Map<number, string>>;
  onChange: (step: TemplateStep) => void;
  onChangeOperation: () => void;
}

function StepPanel({ step, steps, operation, operations, snapshot, names, onChange, onChangeOperation }: PanelProps) {
  const { t } = useApp();
  const [filter, setFilter] = useState("");
  const set = (next: Partial<TemplateStep>) => onChange({ ...step, ...next });
  const fixed = step.targets.length > 0;
  const [fixedMode, setFixedMode] = useState(fixed);

  // Possible fixed targets; instances only of the types the operation applies to.
  const choices = useMemo(() => {
    const words = filter.trim().toLowerCase();
    let entries = [...names[step.target_type]].map(([id, label]) => ({ id, label }));
    if (step.target_type === "INSTANCE" && operation?.instance_types.length) {
      const types = new Map((snapshot?.systems ?? []).flatMap((s) => s.instances.map((i) => [i.id, i.type] as const)));
      entries = entries.filter((e) => operation.instance_types.includes(types.get(e.id) ?? ""));
    }
    return entries.filter((e) => !words || e.label.toLowerCase().includes(words));
  }, [names, step.target_type, operation, snapshot, filter]);

  return (
    <section className="oslo-card oslo-step-panel">
      <h2>
        <span className="oslo-node-number">{step.position}</span> {stepTitle(step, operations, t)}
      </h2>
      {operation?.description && <p className="oslo-muted">{operation.description}</p>}
      {!operation && <p className="error-text">{t("tpl.invalid")}</p>}

      <details open>
        <summary>{t("tpl.current_operation")}</summary>
        <div className="oslo-fields">
          <button type="button" className="oslo-secondary" onClick={onChangeOperation}>
            {t("tpl.change_operation")}
          </button>
          {operation && operation.targets.length > 1 && (
            <label>
              {t("tpl.target_type")}
              <select value={step.target_type} onChange={(e) => set({ target_type: e.target.value as TargetType, targets: [] })}>
                {operation.targets.map((x) => (
                  <option key={x} value={x}>
                    {t(`target.${x}`)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            {t("tpl.on_error")}
            <select value={step.on_error} onChange={(e) => set({ on_error: e.target.value as TemplateStep["on_error"] })}>
              <option value="stop">{t("tpl.on_error.stop")}</option>
              <option value="continue">{t("tpl.on_error.continue")}</option>
              {step.target_type !== "HOST" && <option value="stop_and_start">{t("tpl.on_error.stop_and_start")}</option>}
            </select>
          </label>
          {operation?.locks === false && <p className="oslo-muted">{t("tpl.locks_nothing")}</p>}
        </div>
      </details>

      <details open>
        <summary>{t("tpl.parameters")}</summary>
        <div className="oslo-fields">
          {(operation?.parameters ?? []).map((p) => {
            const asked = step.ask.includes(p.name);
            const missing = p.required && !asked && !step.parameters[p.name] && !p.default;
            const value = step.parameters[p.name] ?? "";
            const setValue = (v: string) => set({ parameters: { ...step.parameters, [p.name]: v } });
            return (
              <div key={p.name} className={`oslo-param${missing ? " oslo-invalid" : ""}`}>
                <label>
                  <span>
                    {p.required ? "*" : ""}
                    {p.label} <span className="oslo-mono oslo-muted">{p.name}</span>
                  </span>
                  {p.type === "BOOLEAN" ? (
                    <select value={value} onChange={(e) => setValue(e.target.value)}>
                      <option value="">{t("tpl.param_default", { value: p.default ?? "false" })}</option>
                      <option value="true">{t("yes")}</option>
                      <option value="false">{t("no")}</option>
                    </select>
                  ) : (
                    <input value={value} placeholder={p.default ?? (p.type === "INTEGER" ? t("custom.type.INTEGER") : "")} inputMode={p.type === "INTEGER" ? "numeric" : undefined} onChange={(e) => setValue(e.target.value)} />
                  )}
                </label>
                <label className="oslo-inline oslo-ask">
                  <input type="checkbox" checked={asked} onChange={(e) => set({ ask: e.target.checked ? [...step.ask, p.name] : step.ask.filter((a) => a !== p.name) })} />
                  {t("tpl.ask")}
                </label>
                {missing && <small className="error-text">{t("tpl.param_missing")}</small>}
                {p.help && <small className="oslo-muted">{p.help}</small>}
              </div>
            );
          })}
          {!operation?.parameters.length && <p className="oslo-muted">{t("tpl.no_parameters")}</p>}
        </div>
      </details>

      <details open>
        <summary>{t("tpl.entities")}</summary>
        <div className="oslo-fields">
          <div className="oslo-segmented" role="radiogroup" aria-label={t("tpl.entities")}>
            <button
              type="button"
              role="radio"
              aria-checked={!fixedMode}
              className={!fixedMode ? "oslo-on" : undefined}
              onClick={() => {
                setFixedMode(false);
                set({ targets: [] });
              }}
            >
              {t("tpl.selection_placeholder", { type: t(`target.${step.target_type}`) })}
            </button>
            <button type="button" role="radio" aria-checked={fixedMode} className={fixedMode ? "oslo-on" : undefined} onClick={() => setFixedMode(true)}>
              {t("tpl.fixed")}
            </button>
          </div>
          <p className="oslo-muted">{fixedMode ? t("tpl.fixed_step_hint") : t("tpl.selection_step_hint")}</p>
          {fixedMode && (
            <>
              <input type="search" value={filter} placeholder={t("tpl.filter_targets")} aria-label={t("tpl.filter_targets")} onChange={(e) => setFilter(e.target.value)} />
              <div className="oslo-target-list oslo-target-scroll">
                {choices.map((c) => (
                  <label key={c.id} className="oslo-inline">
                    <input
                      type="checkbox"
                      checked={step.targets.includes(c.id)}
                      onChange={(e) => set({ targets: e.target.checked ? [...step.targets, c.id] : step.targets.filter((x) => x !== c.id) })}
                    />
                    {c.label}
                  </label>
                ))}
                {!choices.length && <span className="oslo-muted">{t("tpl.no_targets")}</span>}
              </div>
            </>
          )}
        </div>
      </details>

      <details open>
        <summary>{t("tpl.predecessors")}</summary>
        <div className="oslo-target-list">
          {steps
            .filter((s) => s.position !== step.position)
            .map((s) => {
              const checked = step.after.includes(s.position);
              const allowed = checked || canConnect(steps, s.position, step.position);
              return (
                <label key={s.position} className="oslo-inline">
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={!allowed}
                    onChange={(e) => set({ after: e.target.checked ? [...step.after, s.position].sort((a, b) => a - b) : step.after.filter((a) => a !== s.position) })}
                  />
                  {s.position}. {stepTitle(s, operations, t)}
                </label>
              );
            })}
          {steps.length < 2 && <span className="oslo-muted">{t("tpl.no_predecessors")}</span>}
        </div>
      </details>
    </section>
  );
}

// --- running a template with fixed targets -----------------------------------------------

function RunDialog({
  template,
  operations,
  onClose,
  onStarted,
}: {
  template: Draft;
  operations: Map<string, OperationDef>;
  onClose: () => void;
  onStarted: (activity: number) => void;
}) {
  const { t } = useApp();
  const asked = template.steps.flatMap((s) =>
    (operations.get(s.operation)?.parameters ?? [])
      .filter((p) => s.ask.includes(p.name))
      .map((p) => ({ step: s, parameter: p, name: `${s.position}.${p.name}` })),
  );
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(asked.map((a) => [a.name, a.step.parameters[a.parameter.name] ?? a.parameter.default ?? ""])),
  );
  const [error, setError] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal?.();
  }, []);
  const start = async () => {
    setError(null);
    try {
      const parameters = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ""));
      const activity = await api<{ id: number }>(`/templates/${template.id}/run`, { method: "POST", body: { parameters } });
      onStarted(activity.id);
    } catch (exc) {
      setError(errorText(exc, t));
    }
  };
  return (
    <dialog
      ref={dialog}
      className="oslo-dialog oslo-run-dialog"
      aria-labelledby="oslo-run-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void start();
        }}
      >
        <h2 id="oslo-run-title">{t("tpl.run_title", { name: template.name })}</h2>
        <p className="oslo-muted">{t("tpl.run_hint")}</p>
        <div className="oslo-fields">
          {asked.map((a) => (
            <label key={a.name}>
              <span>
                {a.step.position}. {stepTitle(a.step, operations, t)}: {a.parameter.label}
              </span>
              <input value={values[a.name] ?? ""} onChange={(e) => setValues({ ...values, [a.name]: e.target.value })} />
            </label>
          ))}
        </div>
        {error && (
          <p className="flash error" role="alert">
            {error}
          </p>
        )}
        <div className="oslo-dialog-buttons">
          <button type="submit">{t("tpl.run")}</button>
          <button type="button" className="secondary" onClick={onClose}>
            {t("mass.cancel")}
          </button>
        </div>
      </form>
    </dialog>
  );
}
