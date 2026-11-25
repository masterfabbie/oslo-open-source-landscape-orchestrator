// The bar at the bottom while something is selected: start, stop and restart as buttons, the
// other operations in menus by category (OperationMenus). Several targets run as one mass
// operation (no extra question, as wished); stopping or restarting asks once more with a
// second click on the same button.

import { useState } from "react";
import type { InstanceRow, OperationDef } from "../lib/types";
import { OperationMenus } from "./OperationMenus";
import { type RunOptions, type Selection, operationsFor } from "./selection";
import { useApp } from "./ui";

interface Props {
  selection: Selection;
  operations: OperationDef[];
  instances: Map<number, InstanceRow>;
  onRun: (op: OperationDef, selection: Selection, options?: RunOptions) => void;
  onClear: () => void;
  // Whether the OSLO operations are current on the hosts of these targets.
  bundleReady?: (ids: number[]) => boolean;
}

const PARALLEL = [1, 2, 5, 10, 20];

export function ActionBar({ selection, operations, instances, onRun, onClear, bundleReady }: Props) {
  const { t } = useApp();
  const [parallel, setParallel] = useState(5);
  const [stopOnError, setStopOnError] = useState(false);

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
        <OperationMenus
          kind={selection.kind}
          ids={selection.ids}
          operations={operations}
          instances={instances}
          bundleReady={bundleReady}
          direction="up"
          onRun={(op) => onRun(op, selection, several ? { parallel, stopOnError } : {})}
        />
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
