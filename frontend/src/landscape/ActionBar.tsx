// The bar at the bottom while something is selected: the operations that fit the whole
// selection. Several targets run as one mass operation (no extra question, as wished);
// stopping or restarting asks once more with a second click on the same button.

import { useEffect, useState } from "react";
import type { InstanceRow, OperationDef } from "../lib/types";
import { type RunOptions, type Selection, operationLabel, operationsFor } from "./selection";
import { useApp } from "./ui";

interface Props {
  selection: Selection;
  operations: OperationDef[];
  instances: Map<number, InstanceRow>;
  onRun: (op: OperationDef, selection: Selection, options?: RunOptions) => void;
  onClear: () => void;
}

const PARALLEL = [1, 2, 5, 10, 20];

export function ActionBar({ selection, operations, instances, onRun, onClear }: Props) {
  const { t } = useApp();
  const [armed, setArmed] = useState<string | null>(null);
  const [parallel, setParallel] = useState(5);
  const [stopOnError, setStopOnError] = useState(false);

  useEffect(() => setArmed(null), [selection]);
  useEffect(() => {
    if (!armed) return;
    const timer = window.setTimeout(() => setArmed(null), 4000);
    return () => window.clearTimeout(timer);
  }, [armed]);

  if (!selection.ids.length) return null;
  const available = operationsFor(operations, selection, instances);
  const count = selection.ids.length;
  const several = count > 1;

  return (
    <div className="oslo-actionbar" role="region" aria-label={t("ui.selection")}>
      <span className="oslo-actionbar-count">
        {t(`ui.selected_${selection.kind.toLowerCase()}`, { count })}
      </span>
      <div className="oslo-actionbar-ops">
        {available.length ? (
          available.map((op) => {
            const label = operationLabel(op, selection.kind, t);
            const isArmed = armed === op.key;
            return (
              <button
                key={op.key}
                type="button"
                className={`${op.danger ? "oslo-danger" : ""}${isArmed ? " oslo-armed" : ""}`}
                onClick={() => {
                  if (op.danger && !isArmed) {
                    setArmed(op.key);
                    return;
                  }
                  setArmed(null);
                  onRun(op, selection, several ? { parallel, stopOnError } : {});
                }}
              >
                {isArmed ? t("ui.confirm_operation", { operation: label }) : label}
                {op.custom && (op.parameters.length || op.template) ? "…" : ""}
              </button>
            );
          })
        ) : (
          <span className="oslo-muted">{t("ui.no_operations")}</span>
        )}
      </div>
      {several && available.length > 0 && (
        <div className="oslo-actionbar-options">
          <label>
            {t("mass.parallel")}
            <select value={parallel} onChange={(e) => setParallel(Number(e.target.value))}>
              {PARALLEL.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label>
            <input type="checkbox" checked={stopOnError} onChange={(e) => setStopOnError(e.target.checked)} />
            {t("ui.stop_on_error")}
          </label>
        </div>
      )}
      <button type="button" className="oslo-clear" onClick={onClear} aria-label={t("ui.clear_selection")}>
        {t("ui.clear_selection")}
      </button>
    </div>
  );
}
