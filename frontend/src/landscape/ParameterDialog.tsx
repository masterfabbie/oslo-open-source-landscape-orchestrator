// Parameters of a custom operation before it runs, prefilled with the defaults. An empty
// optional field is not passed (see customops.parameter_values on the server).

import { type FormEvent, useEffect, useRef, useState } from "react";
import type { OperationDef } from "../lib/types";
import type { Selection } from "./selection";
import { useApp } from "./ui";

interface Props {
  operation: OperationDef;
  selection: Selection;
  onCancel: () => void;
  onRun: (parameters: Record<string, string | boolean>) => void;
}

export function ParameterDialog({ operation, selection, onCancel, onRun }: Props) {
  const { t } = useApp();
  const dialog = useRef<HTMLDialogElement>(null);
  const [values, setValues] = useState<Record<string, string | boolean>>(() =>
    Object.fromEntries(
      operation.parameters.map((p) => [
        p.name,
        p.type === "BOOLEAN" ? ["true", "on", "1", "yes"].includes(p.default ?? "") : (p.default ?? ""),
      ]),
    ),
  );

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal?.();
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onRun(values);
  };

  return (
    <dialog ref={dialog} className="oslo-dialog" onCancel={onCancel} aria-labelledby="oslo-param-title">
      <form onSubmit={submit}>
        <h2 id="oslo-param-title">{operation.name}</h2>
        {operation.description && <p>{operation.description}</p>}
        {operation.template && operation.steps && (
          <ol className="oslo-steps-preview">
            {operation.steps.map((step, index) => (
              <li key={index}>{t(step)}</li>
            ))}
          </ol>
        )}
        <p className="oslo-muted">{t(`ui.selected_${selection.kind.toLowerCase()}`, { count: selection.ids.length })}</p>
        <div className="oslo-fields">
          {operation.parameters.map((p) =>
            p.type === "BOOLEAN" ? (
              <label key={p.name} className="oslo-check-field">
                <input
                  type="checkbox"
                  checked={values[p.name] === true}
                  onChange={(e) => setValues({ ...values, [p.name]: e.target.checked })}
                />
                {p.label} <span className="oslo-mono oslo-muted">{p.name}</span>
              </label>
            ) : (
              <label key={p.name}>
                <span>
                  {p.label}
                  {p.required ? " *" : ""} <span className="oslo-mono oslo-muted">{p.name}</span>
                </span>
                <input
                  value={String(values[p.name] ?? "")}
                  required={p.required}
                  inputMode={p.type === "INTEGER" ? "numeric" : undefined}
                  pattern={p.type === "INTEGER" ? "-?[0-9]+" : (p.pattern ?? undefined)}
                  maxLength={1024}
                  onChange={(e) => setValues({ ...values, [p.name]: e.target.value })}
                />
                {p.help && <small className="oslo-muted">{p.help}</small>}
              </label>
            ),
          )}
        </div>
        {operation.parameters.length > 0 && <p className="oslo-muted">{t("custom.parameters_hint")}</p>}
        <div className="oslo-dialog-buttons">
          <button type="submit">{t("custom.run")}</button>
          <button type="button" className="secondary" onClick={onCancel}>
            {t("mass.cancel")}
          </button>
        </div>
      </form>
    </dialog>
  );
}
