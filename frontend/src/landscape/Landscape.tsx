// The landscape: systems and hosts in dense tables, select several, run operations from the
// bar at the bottom, details in a panel on the right, Ctrl+K for the command palette.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../lib/api";
import { bundleReadiness } from "../lib/categories";
import type { InstanceRow, OperationDef, Snapshot, TargetType } from "../lib/types";
import { ActionBar } from "./ActionBar";
import { CommandPalette } from "./CommandPalette";
import { HostDrawer, InstanceDrawer, SystemDrawer } from "./Drawer";
import { FilterBar } from "./FilterBar";
import {
  HOST_FILTER_KEYS,
  type HostFilter,
  SYSTEM_FILTER_KEYS,
  type SystemFilter,
  emptyHostFilter,
  emptySystemFilter,
  filterHosts,
  filterSystems,
  readFilter,
  writeFilter,
} from "./filter";
import { HostsTable } from "./HostsTable";
import { ParameterDialog } from "./ParameterDialog";
import { type RunOptions, type Selection, operationLabel, runOperation } from "./selection";
import { SystemsTable } from "./SystemsTable";
import { type Toast, Toasts } from "./Toasts";
import { useApp, useLiveUpdates } from "./ui";

type Tab = "systems" | "hosts";
type Detail = { kind: "SYSTEM" | "INSTANCE" | "HOST"; id: number } | null;

const EMPTY: Selection = { kind: "SYSTEM", ids: [] };

function currentParams(): URLSearchParams {
  return new URLSearchParams(window.location.search);
}

export function Landscape() {
  const { t, language } = useApp();
  const queries = useQueryClient();
  useLiveUpdates();
  const { data, error, isPending } = useQuery({
    queryKey: ["landscape"],
    queryFn: () => api<Snapshot>("/landscape"),
  });

  const [tab, setTab] = useState<Tab>(() =>
    currentParams().get("tab") === "hosts" ? "hosts" : "systems",
  );
  const [systemFilter, setSystemFilter] = useState<SystemFilter>(() =>
    readFilter(currentParams(), emptySystemFilter(), SYSTEM_FILTER_KEYS),
  );
  const [hostFilter, setHostFilter] = useState<HostFilter>(() =>
    readFilter(currentParams(), emptyHostFilter(), HOST_FILTER_KEYS, "hq"),
  );
  const [selection, setSelection] = useState<Selection>(EMPTY);
  // ?system=, ?instance= or ?host= open the detail panel, e.g. from the overview.
  const [detail, setDetail] = useState<Detail>(() => {
    const params = currentParams();
    for (const [key, kind] of [["system", "SYSTEM"], ["instance", "INSTANCE"], ["host", "HOST"]] as const) {
      const id = Number(params.get(key));
      if (id > 0) return { kind, id };
    }
    return null;
  });
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [asking, setAsking] = useState<{
    op: OperationDef;
    selection: Selection;
    options: RunOptions;
  } | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Keep tab and filters in the address, so a view can be bookmarked or shared.
  useEffect(() => {
    let params = currentParams();
    for (const key of ["system", "instance", "host"]) params.delete(key);
    params.set("tab", tab);
    params = writeFilter(params, systemFilter as never, SYSTEM_FILTER_KEYS);
    params = writeFilter(params, hostFilter as never, HOST_FILTER_KEYS, "hq");
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
  }, [tab, systemFilter, hostFilter]);

  // Ctrl+K / Cmd+K: command palette. Escape: clear the selection.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      } else if (event.key === "Escape" && !paletteOpen && !asking) {
        // An open filter list closes first; only then Escape clears the selection.
        const chips = document.querySelectorAll<HTMLDetailsElement>("details.oslo-chip[open]");
        if (chips.length) chips.forEach((chip) => (chip.open = false));
        else setSelection(EMPTY);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen, asking]);

  const bundleReady = useMemo(
    () => bundleReadiness(data?.systems ?? [], data?.hosts ?? []),
    [data],
  );
  const instances = useMemo(() => {
    const map = new Map<number, InstanceRow>();
    for (const system of data?.systems ?? []) for (const i of system.instances) map.set(i.id, i);
    return map;
  }, [data]);
  const systemRows = useMemo(
    () => filterSystems(data?.systems ?? [], systemFilter),
    [data, systemFilter],
  );
  const hostRows = useMemo(() => filterHosts(data?.hosts ?? [], hostFilter), [data, hostFilter]);

  const notify = useCallback((toast: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((all) => [...all, { ...toast, id }]);
    window.setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), 12_000);
  }, []);

  const execute = useCallback(
    async (op: OperationDef, target: Selection, options: RunOptions = {}) => {
      // Custom operations with parameters and every template first show the dialog.
      if (op.custom && (op.parameters.length || op.template) && !options.parameters) {
        setAsking({ op, selection: target, options });
        return;
      }
      const label = operationLabel(op, target.kind, t, language);
      try {
        const activityId = await runOperation(op, target, options);
        notify({ kind: "success", text: t("ui.started", { operation: label }), activityId });
        setSelection(EMPTY);
        void queries.invalidateQueries({ queryKey: ["landscape"] });
      } catch (exc) {
        const text = exc instanceof ApiError && exc.status === 409 ? t("ui.busy") : String((exc as Error).message);
        notify({ kind: "error", text: `${label}: ${text}` });
      }
    },
    [notify, queries, t, language],
  );

  const select = useCallback((kind: TargetType, ids: number[], add: boolean) => {
    setSelection((current) => {
      if (current.kind !== kind) return add ? { kind, ids } : current;
      const set = new Set(current.ids);
      for (const id of ids) {
        if (add) set.add(id);
        else set.delete(id);
      }
      return { kind, ids: [...set] };
    });
  }, []);

  if (isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (error || !data) return <p className="flash error">{t("ui.load_failed")}</p>;

  const counts = {
    systems: systemRows.length,
    instances: systemRows.reduce((sum, row) => sum + row.instances.length, 0),
  };

  return (
    <div className={`oslo-landscape${detail ? " oslo-with-detail" : ""}`}>
      <div className="oslo-main">
        <div className="oslo-head">
          <h1>{t("nav.landscape")}</h1>
          <nav className="tabs" aria-label={t("nav.landscape")}>
            {(["systems", "hosts"] as Tab[]).map((name) => (
              <a
                key={name}
                href={`?tab=${name}`}
                aria-current={tab === name ? "page" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  setTab(name);
                  setSelection(EMPTY);
                  setDetail(null);
                }}
              >
                {t(`tab.${name}`)}
              </a>
            ))}
          </nav>
          <button type="button" className="oslo-palette-button" onClick={() => setPaletteOpen(true)}>
            {t("ui.palette_open")} <kbd>Ctrl K</kbd>
          </button>
        </div>

        {tab === "systems" ? (
          <>
            <FilterBar
              kind="systems"
              filter={systemFilter}
              onChange={(f) => setSystemFilter(f as SystemFilter)}
              snapshot={data}
              summary={t("ui.count_systems", counts)}
            />
            <SystemsTable
              rows={systemRows}
              expandAll={systemFilter.type.length > 0}
              selection={selection}
              onSelect={select}
              onOpen={(id) => setDetail({ kind: "SYSTEM", id })}
              onOpenInstance={(id) => setDetail({ kind: "INSTANCE", id })}
              openId={detail?.kind === "SYSTEM" ? detail.id : null}
              openInstanceId={detail?.kind === "INSTANCE" ? detail.id : null}
            />
          </>
        ) : (
          <>
            <FilterBar
              kind="hosts"
              filter={hostFilter}
              onChange={(f) => setHostFilter(f as HostFilter)}
              snapshot={data}
              summary={t("ui.count_hosts", { hosts: hostRows.length })}
            />
            <HostsTable
              rows={hostRows}
              selection={selection}
              onSelect={select}
              onOpen={(id) => setDetail({ kind: "HOST", id })}
              openId={detail?.kind === "HOST" ? detail.id : null}
            />
          </>
        )}
      </div>

      {detail?.kind === "SYSTEM" && (
        <SystemDrawer
          system={data.systems.find((s) => s.id === detail.id)}
          operations={data.operations}
          onClose={() => setDetail(null)}
          onRun={execute}
          bundleReady={bundleReady}
          notify={notify}
          onOpenInstance={(id) => setDetail({ kind: "INSTANCE", id })}
        />
      )}
      {detail?.kind === "INSTANCE" && (
        <InstanceDrawer
          instance={instances.get(detail.id)}
          system={data.systems.find((s) => s.instances.some((i) => i.id === detail.id))}
          operations={data.operations}
          onClose={() => setDetail(null)}
          onRun={execute}
          bundleReady={bundleReady}
          onOpenSystem={(id) => setDetail({ kind: "SYSTEM", id })}
        />
      )}
      {detail?.kind === "HOST" && (
        <HostDrawer
          host={data.hosts.find((h) => h.id === detail.id)}
          systems={data.systems}
          operations={data.operations}
          onClose={() => setDetail(null)}
          onRun={execute}
          bundleReady={bundleReady}
        />
      )}

      <ActionBar
        selection={selection}
        operations={data.operations}
        instances={instances}
        onRun={execute}
          bundleReady={bundleReady}
        onClear={() => setSelection(EMPTY)}
      />

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        snapshot={data}
        selection={selection}
        instances={instances}
        onRun={execute}
        onOpenSystem={(id) => {
          setTab("systems");
          setDetail({ kind: "SYSTEM", id });
        }}
        onOpenHost={(id) => {
          setTab("hosts");
          setDetail({ kind: "HOST", id });
        }}
      />

      {asking && (
        <ParameterDialog
          operation={asking.op}
          selection={asking.selection}
          onCancel={() => setAsking(null)}
          onRun={(parameters) => {
            const { op, selection: target, options } = asking;
            setAsking(null);
            void execute(op, target, { ...options, parameters });
          }}
        />
      )}

      <Toasts toasts={toasts} onClose={(id) => setToasts((all) => all.filter((x) => x.id !== id))} />
    </div>
  );
}
