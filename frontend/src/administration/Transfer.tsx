// Administration → Import/Export: download chosen parts of the configuration as JSON (with
// the passwords of hosts and SIDs only when an export password is given), and import such a
// file: preview first, then import. An import never deletes anything.

import { useState } from "react";
import { ApiError, api } from "../lib/api";
import { PageHead, Section, errorMessage } from "../lib/forms";
import { formatTime, useApp } from "../landscape/ui";

const PARTS = ["hosts", "sids", "pools", "systems", "custom_operations", "templates", "schedules", "attention_rules", "certificates"];
const PAGE = "/administration/transfer";
const BADGE: Record<string, string> = { created: "green", updated: "running", skipped: "gray", failed: "red", warning: "yellow" };

interface Report {
  applied: boolean;
  counts: Record<string, number>;
  items: { part: string; name: string; action: string; message: string }[];
}

interface ExportFile {
  format?: string;
  exported_at?: string;
  parts?: string[];
  credentials?: unknown;
}

export function TransferPage() {
  const { t } = useApp();
  return (
    <div className="oslo-page">
      <PageHead title={t("tab.transfer")} tabs={[{ href: PAGE, label: t("tab.overview"), current: true }]} />
      <div className="oslo-columns">
        <div className="oslo-column">
          <ExportSection />
        </div>
        <div className="oslo-column">
          <ImportSection />
        </div>
      </div>
    </div>
  );
}

function ExportSection() {
  const { t } = useApp();
  const [parts, setParts] = useState<string[]>(PARTS);
  const [withPasswords, setWithPasswords] = useState(false);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = async () => {
    setError(null);
    if (withPasswords && password !== repeat) {
      setError(t("transfer.password_mismatch"));
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/export", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-OSLO-Request": "1" },
        body: JSON.stringify({ parts, password: withPasswords ? password : null }),
      });
      if (!response.ok) throw new ApiError(response.status, await response.text());
      const name = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? "oslo-export.json";
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.click();
      URL.revokeObjectURL(url);
    } catch (exc) {
      setError(errorMessage(exc, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section title={t("transfer.export")} hint={t("transfer.export_hint")}>
      <fieldset className="oslo-checks oslo-checks-column">
        <legend>{t("transfer.part")}</legend>
        {PARTS.map((part) => (
          <label key={part} className="oslo-inline">
            <input type="checkbox" checked={parts.includes(part)} onChange={(e) => setParts(e.target.checked ? [...parts, part] : parts.filter((p) => p !== part))} />
            {t(`transfer.part.${part}`)}
          </label>
        ))}
      </fieldset>
      <label className="oslo-inline">
        <input type="checkbox" checked={withPasswords} onChange={(e) => setWithPasswords(e.target.checked)} /> {t("transfer.with_passwords")}
      </label>
      {withPasswords && (
        <>
          <div className="oslo-form-grid">
            <label className="oslo-field">
              {t("transfer.password")}
              <input type="password" value={password} minLength={8} autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
            </label>
            <label className="oslo-field">
              {t("transfer.password_repeat")}
              <input type="password" value={repeat} minLength={8} autoComplete="new-password" onChange={(e) => setRepeat(e.target.value)} />
            </label>
          </div>
          <p className="oslo-muted">{t("transfer.password_hint")}</p>
        </>
      )}
      {error && (
        <p className="flash error" role="alert">
          {error}
        </p>
      )}
      <div className="oslo-form-buttons">
        <button type="button" className="oslo-primary" disabled={busy || !parts.length || (withPasswords && password.length < 8)} onClick={() => void download()}>
          {t("transfer.download")}
        </button>
      </div>
    </Section>
  );
}

function ImportSection() {
  const { t, language } = useApp();
  const [data, setData] = useState<ExportFile | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [mode, setMode] = useState<"add" | "update">("add");
  const [password, setPassword] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (apply: boolean) => {
    if (!data) return;
    if (apply && !window.confirm(t("transfer.apply_confirm"))) return;
    setBusy(true);
    setError(null);
    try {
      setReport(await api<Report>("/import", { method: "POST", body: { data, mode, password: password || null, apply } }));
    } catch (exc) {
      setError(errorMessage(exc, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section title={t("transfer.import")} hint={t("transfer.import_hint")}>
      <label className="oslo-field">
        {t("transfer.file")}
        <input
          type="file"
          accept=".json,application/json"
          onChange={(e) => {
            setData(null);
            setReport(null);
            setFileError(null);
            const file = e.target.files?.[0];
            if (!file) return;
            void file.text().then((text) => {
              try {
                setData(JSON.parse(text) as ExportFile);
              } catch {
                setFileError(t("transfer.bad_file"));
              }
            });
          }}
        />
      </label>
      {fileError && (
        <p className="flash error" role="alert">
          {fileError}
        </p>
      )}
      {data && (
        <p className="oslo-muted">
          {t("transfer.file_info", {
            date: data.exported_at ? formatTime(data.exported_at, language) : "?",
            parts: (data.parts ?? []).map((p) => t(`transfer.part.${p}`)).join(", "),
          })}
          {data.credentials ? ` ${t("transfer.file_passwords")}` : ""}
        </p>
      )}
      <fieldset className="oslo-checks oslo-checks-column">
        <legend>{t("transfer.mode")}</legend>
        {(["add", "update"] as const).map((m) => (
          <label key={m} className="oslo-inline">
            <input type="radio" name="transfer-mode" checked={mode === m} onChange={() => setMode(m)} /> {t(`transfer.mode.${m}`)}
          </label>
        ))}
      </fieldset>
      {Boolean(data?.credentials) && (
        <label className="oslo-field">
          {t("transfer.import_password")}
          <input type="password" value={password} autoComplete="off" onChange={(e) => setPassword(e.target.value)} />
        </label>
      )}
      {error && (
        <p className="flash error" role="alert">
          {error}
        </p>
      )}
      <div className="oslo-form-buttons">
        <button type="button" className="oslo-secondary" disabled={!data || busy} onClick={() => void run(false)}>
          {t("transfer.preview")}
        </button>
        <button type="button" className="oslo-primary" disabled={!data || busy || !report || report.applied} onClick={() => void run(true)}>
          {t("transfer.apply")}
        </button>
      </div>
      {report && <ReportTable report={report} />}
    </Section>
  );
}

function ReportTable({ report }: { report: Report }) {
  const { t } = useApp();
  const c = report.counts;
  return (
    <>
      <p className={`flash ${report.applied ? "notice" : "warning"}`} role="status">
        {report.applied ? t("transfer.applied_note") : t("transfer.preview_note")}{" "}
        {t("transfer.counts", { created: c.created ?? 0, updated: c.updated ?? 0, skipped: c.skipped ?? 0, failed: c.failed ?? 0 })}
      </p>
      <div className="oslo-table-wrap">
        <table className="oslo-table oslo-compact">
          <thead>
            <tr>
              <th>{t("transfer.part")}</th>
              <th>{t("field.name")}</th>
              <th>{t("transfer.result")}</th>
              <th>{t("transfer.note")}</th>
            </tr>
          </thead>
          <tbody>
            {report.items.map((item, index) => (
              <tr key={index}>
                {/* The short name of the part, without the explanation in brackets. */}
                <td>{t(`transfer.part.${item.part}`).split(" (")[0]}</td>
                <td className="oslo-mono">{item.name}</td>
                <td>
                  <span className={`oslo-badge oslo-badge-${BADGE[item.action] ?? "unknown"}`}>{t(`transfer.action.${item.action}`)}</span>
                </td>
                <td className="oslo-wrap">{item.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
