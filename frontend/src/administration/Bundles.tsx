// Administration → OSLO operations: the bundle of operations OSLO installs into operations.d
// of the host agents. Settings (public key of the signature, address of OSLO for the hosts),
// upload of a signed bundle, earlier bundles, the bootstrap package for the first
// installation and the state of every host, with an update of all hosts that need one.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../lib/api";
import { BUNDLE_BADGE, NEEDS_UPDATE, bundleState, type BundleFields } from "../lib/bundle";
import { categoryPath } from "../lib/categories";
import { ActionForm, Messages, PageHead, Section, errorMessage, useAction } from "../lib/forms";
import { activityNumber } from "../lib/numbers";
import { formatTime, useApp, useLiveUpdates } from "../landscape/ui";

const PAGE = "/administration/bundle";
const ROLES = ["viewer", "operator", "configurator", "admin"];
// The roles an admin may require for an operation of the bundle: its own or higher.
const rolesFrom = (role: string) => ROLES.slice(Math.max(ROLES.indexOf(role), 0));

interface Settings {
  public_key: string;
  base_url: string;
  ca_path: string;
}

interface BundleRow {
  id: number;
  version: string;
  sha256: string;
  active: boolean;
  uploaded_at: string;
  uploaded_by: string | null;
  files: string[];
}

interface HostRow extends BundleFields {
  id: number;
  name: string;
}

export function BundlePage() {
  const { t } = useApp();
  useLiveUpdates(["bundles", "hosts"]);
  const { data, isPending } = useQuery({ queryKey: ["bundles"], queryFn: () => api<{ settings: Settings; bundles: BundleRow[] }>("/bundles") });
  if (isPending || !data) return <p className="oslo-muted">{t("ui.loading")}</p>;
  const active = data.bundles.find((b) => b.active) ?? null;
  return (
    <div className="oslo-page">
      <PageHead title={t("tab.bundle")} tabs={[{ href: PAGE, label: t("tab.overview"), current: true }]} />
      <p className="oslo-muted">{t("bundle.intro")}</p>
      <div className="oslo-columns">
        <div className="oslo-column">
          <SettingsSection settings={data.settings} />
          <UploadSection hasKey={Boolean(data.settings.public_key)} />
        </div>
        <div className="oslo-column">
          <BootstrapSection active={active} settings={data.settings} />
          <BundlesSection bundles={data.bundles} />
        </div>
      </div>
      {active && <OperationsSection />}
      <HostsSection active={active?.version ?? null} />
    </div>
  );
}

function SettingsSection({ settings }: { settings: Settings }) {
  const { t } = useApp();
  const queries = useQueryClient();
  const [key, setKey] = useState(settings.public_key);
  const [url, setUrl] = useState(settings.base_url);
  const [ca, setCa] = useState(settings.ca_path);
  return (
    <Section title={t("bundle.settings")} hint={t("bundle.settings_hint")}>
      <ActionForm
        submit={t("action.save")}
        onSubmit={async () => {
          await api("/bundles/settings", { method: "PUT", body: { public_key: key, base_url: url, ca_path: ca } });
          await queries.invalidateQueries({ queryKey: ["bundles"] });
        }}
      >
        <label className="oslo-field">
          {t("bundle.public_key")}
          <textarea className="oslo-pem" rows={4} value={key} placeholder="-----BEGIN PUBLIC KEY-----" onChange={(e) => setKey(e.target.value)} />
        </label>
        <label className="oslo-field">
          {t("bundle.base_url")}
          <input value={url} placeholder={window.location.origin} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label className="oslo-field">
          {t("bundle.ca_path")}
          <input value={ca} placeholder="/etc/pki/oslo-ca.pem" onChange={(e) => setCa(e.target.value)} />
        </label>
      </ActionForm>
    </Section>
  );
}

function UploadSection({ hasKey }: { hasKey: boolean }) {
  const { t } = useApp();
  const queries = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const action = useAction();
  const upload = () =>
    action.run(async () => {
      if (!file) return;
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      const row = await api<BundleRow>("/bundles", { method: "POST", body: { data: btoa(binary) } });
      await queries.invalidateQueries({ queryKey: ["bundles"] });
      return row;
    }, t("bundle.uploaded"));
  return (
    <Section title={t("bundle.upload")} hint={t("bundle.upload_hint")}>
      <label className="oslo-field">
        {t("bundle.file")}
        <input type="file" accept=".oslobundle" disabled={!hasKey} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      {!hasKey && <p className="oslo-muted">{t("bundle.key_first")}</p>}
      <Messages error={action.error} notice={action.notice} />
      <div className="oslo-form-buttons">
        <button type="button" className="oslo-primary" disabled={!file || action.busy} onClick={() => void upload()}>
          {t("bundle.upload_button")}
        </button>
      </div>
    </Section>
  );
}

function BootstrapSection({ active, settings }: { active: BundleRow | null; settings: Settings }) {
  const { t } = useApp();
  const [error, setError] = useState<string | null>(null);
  const ready = Boolean(active && settings.public_key && settings.base_url);
  const download = async () => {
    setError(null);
    try {
      const response = await fetch("/api/bundles/bootstrap", { credentials: "same-origin" });
      if (!response.ok) throw new ApiError(response.status, await response.text());
      const name = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? "oslo-bootstrap.tar.gz";
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.click();
      URL.revokeObjectURL(url);
    } catch (exc) {
      setError(errorMessage(exc, t));
    }
  };
  const file = `oslo-bootstrap-${active?.version ?? "<version>"}.tar.gz`;
  return (
    <Section title={t("bundle.bootstrap")} hint={t("bundle.bootstrap_hint")}>
      <pre className="oslo-code">{`tar -xzf ${file}\nsh oslo-bootstrap/install.sh`}</pre>
      {!ready && <p className="oslo-muted">{t("bundle.bootstrap_missing")}</p>}
      {error && (
        <p className="flash error" role="alert">
          {error}
        </p>
      )}
      <div className="oslo-form-buttons">
        <button type="button" className="oslo-secondary" disabled={!ready} onClick={() => void download()}>
          {t("bundle.bootstrap_download")}
        </button>
      </div>
    </Section>
  );
}

function BundlesSection({ bundles }: { bundles: BundleRow[] }) {
  const { t, language } = useApp();
  const queries = useQueryClient();
  const action = useAction();
  return (
    <Section title={t("bundle.list")}>
      {!bundles.length ? (
        <p className="oslo-muted">{t("bundle.none")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("bundle.version")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {bundles.map((b) => (
                <tr key={b.id}>
                  <td>
                    <span className="oslo-mono oslo-strong">{b.version}</span> {b.active && <span className="oslo-badge oslo-badge-green">{t("bundle.active")}</span>}
                    <span className="oslo-sub">
                      {t("bundle.files", { count: b.files.length })} · {formatTime(b.uploaded_at, language)}
                      {b.uploaded_by ? ` · ${b.uploaded_by}` : ""}
                    </span>
                  </td>
                  <td className="oslo-row-actions">
                    {!b.active && (
                      <button
                        type="button"
                        className="oslo-secondary"
                        disabled={action.busy}
                        onClick={() =>
                          void action.run(async () => {
                            await api(`/bundles/${b.id}/activate`, { method: "POST" });
                            await queries.invalidateQueries({ queryKey: ["bundles"] });
                          })
                        }
                      >
                        {t("bundle.activate")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Messages error={action.error} />
    </Section>
  );
}

interface BundleOperation {
  key: string;
  names: Record<string, string>;
  descriptions: Record<string, string>;
  agent_operation: string;
  target: string;
  category: string;
  bundle_role: string;
  role: string;
  hidden: boolean;
}

/** The operations of operations.json: hide them from menus or require a higher role. */
function OperationsSection() {
  const { t, language } = useApp();
  const queries = useQueryClient();
  const { data } = useQuery({ queryKey: ["bundle-operations"], queryFn: () => api<BundleOperation[]>("/bundle-operations") });
  const action = useAction();
  const save = (op: BundleOperation, change: { hidden?: boolean; role?: string }) =>
    action.run(async () => {
      await api(`/bundle-operations/${op.key}`, { method: "PUT", body: { hidden: op.hidden, role: op.role, ...change } });
      await queries.invalidateQueries({ queryKey: ["bundle-operations"] });
    });
  const operations = data ?? [];
  return (
    <Section title={t("bundle.operations")} hint={t("bundle.operations_hint")}>
      {!operations.length ? (
        <p className="oslo-muted">{t("bundle.operations_none")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("field.name")}</th>
                <th>{t("field.target")}</th>
                <th>{t("field.category")}</th>
                <th>{t("field.role")}</th>
                <th>{t("bundle.in_menus")}</th>
              </tr>
            </thead>
            <tbody>
              {operations.map((op) => (
                <tr key={op.key}>
                  <td>
                    <span className="oslo-strong">{op.names[language] ?? op.names.en}</span>
                    <span className="oslo-sub oslo-mono">{op.agent_operation}</span>
                  </td>
                  <td>{t(`target.${op.target}`)}</td>
                  <td>{categoryPath(op.category, t)}</td>
                  <td>
                    <select
                      value={op.role}
                      aria-label={t("field.role")}
                      disabled={action.busy}
                      onChange={(e) => void save(op, { role: e.target.value })}
                    >
                      {rolesFrom(op.bundle_role).map((role) => (
                        <option key={role} value={role}>
                          {t(`role.${role}`)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={!op.hidden}
                      aria-label={t("bundle.in_menus")}
                      disabled={action.busy}
                      onChange={(e) => void save(op, { hidden: !e.target.checked })}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Messages error={action.error} />
    </Section>
  );
}

function HostsSection({ active }: { active: string | null }) {
  const { t, language } = useApp();
  const { data } = useQuery({ queryKey: ["hosts"], queryFn: () => api<HostRow[]>("/hosts") });
  const action = useAction();
  const [started, setStarted] = useState<number | null>(null);
  const hosts = data ?? [];
  const outdated = hosts.filter((h) => NEEDS_UPDATE.includes(bundleState(h, active)));
  const updateAll = () =>
    action.run(async () => {
      const activity = await api<{ id: number }>("/mass-operations", {
        method: "POST",
        body: { operation: "update_bundle", target_type: "HOST", target_ids: outdated.map((h) => h.id), parallel: 5, stop_on_error: false },
      });
      setStarted(activity.id);
    });
  return (
    <Section title={t("bundle.hosts")} hint={t("bundle.hosts_hint")}>
      <div className="oslo-form-buttons">
        <button type="button" className="oslo-primary" disabled={!active || !outdated.length || action.busy} onClick={() => void updateAll()}>
          {t("bundle.update_all", { count: outdated.length })}
        </button>
        {started !== null && (
          <a href={`/activities/${started}`}>{t("bundle.update_started", { number: activityNumber(started) })}</a>
        )}
      </div>
      <Messages error={action.error} />
      {!hosts.length ? (
        <p className="oslo-muted">{t("hosts.empty")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("field.host")}</th>
                <th>{t("bundle.state")}</th>
                <th>{t("bundle.version")}</th>
                <th>{t("bundle.checked")}</th>
              </tr>
            </thead>
            <tbody>
              {hosts.map((h) => {
                const state = bundleState(h, active);
                return (
                  <tr key={h.id}>
                    <td>
                      <a className="oslo-mono" href={`/configuration/hosts/${h.id}`}>
                        {h.name}
                      </a>
                    </td>
                    <td>
                      <span className={`oslo-badge oslo-badge-${BUNDLE_BADGE[state]}`}>{t(`bundle.state.${state}`)}</span>
                    </td>
                    <td className="oslo-mono">{h.bundle_version && h.bundle_version !== "none" ? h.bundle_version : ""}</td>
                    <td className="oslo-muted">{formatTime(h.bundle_checked_at, language)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
