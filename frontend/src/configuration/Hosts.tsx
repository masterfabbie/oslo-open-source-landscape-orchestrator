// Configuration → Hosts: list, create, and the page of a host (connection, discovery,
// credentials, tags, instances, databases, delete).

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { BUNDLE_BADGE, bundleState } from "../lib/bundle";
import { RecentChanges } from "../lib/changes";
import { ActionForm, ConfirmButton, CredentialsForm, Messages, PageHead, Section, TagsForm, go, useAction } from "../lib/forms";
import { StatusBadge, formatTime, useApp } from "../landscape/ui";
import { CertificateFacts } from "../lib/certificate";
import type { HostCertificate, HostDetail, HostInfo } from "./types";

const LIST = "/configuration/hosts";

function ReachBadge({ host }: { host: HostInfo }) {
  const status = host.reachable === null ? "UNKNOWN" : host.reachable ? "GREEN" : "RED";
  return <StatusBadge status={status} prefix="reach" />;
}

function memory(kb: number | null): string {
  if (!kb) return "";
  return kb >= 1024 * 1024 ? `${(kb / 1024 / 1024).toFixed(1)} GB` : `${Math.round(kb / 1024)} MB`;
}

export function HostsPage() {
  const { t, language } = useApp();
  const { data, isPending } = useQuery({ queryKey: ["hosts"], queryFn: () => api<HostInfo[]>("/hosts") });
  return (
    <div className="oslo-page">
      <PageHead title={t("tab.hosts")} action={{ href: `${LIST}/new`, label: t("hosts.add") }} tabs={[{ href: LIST, label: t("tab.overview"), current: true }]} />
      {isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !data?.length ? (
        <p className="oslo-empty">{t("hosts.empty")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("field.name")}</th>
                <th>{t("field.address")}</th>
                <th>{t("field.hostagent_port")}</th>
                <th>{t("credentials.title")}</th>
                <th>{t("field.reachable")}</th>
                <th>{t("field.last_discovery")}</th>
                <th>{t("field.tags")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((h) => (
                <tr key={h.id}>
                  <td>
                    <a className="oslo-strong" href={`${LIST}/${h.id}`}>
                      {h.name}
                    </a>
                  </td>
                  <td className="oslo-mono">{h.address}</td>
                  <td className="oslo-mono">{h.hostagent_port ?? (h.https ? 1129 : 1128)}</td>
                  <td>{h.has_credentials ? `${h.username} (${t("credentials.set")})` : t("credentials.missing")}</td>
                  <td>
                    <ReachBadge host={h} />
                  </td>
                  <td className="oslo-muted">{h.last_discovery_at ? formatTime(h.last_discovery_at, language) : t("hosts.never")}</td>
                  <td>{h.tags.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

interface ConnectionValues {
  name: string;
  address: string;
  hostagent_port: string;
  sapcontrol_port_offset: string;
  https: boolean;
  verify_tls: boolean;
  verify_hostname: boolean;
}

/** Names separated by commas, without empty ones. */
export function hostNames(text: string): string[] {
  return text
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
}

function ConnectionFields({ values, onChange, several = false }: { values: ConnectionValues; onChange: (v: ConnectionValues) => void; several?: boolean }) {
  const { t } = useApp();
  const set = (next: Partial<ConnectionValues>) => onChange({ ...values, ...next });
  const many = several && hostNames(values.name).length > 1;
  return (
    <>
      <div className="oslo-form-grid">
        <label className="oslo-field">
          {t("field.name")}
          <input value={values.name} required maxLength={several ? 10000 : 255} onChange={(e) => set({ name: e.target.value })} />
        </label>
        <label className="oslo-field">
          {t("field.address")}
          <input
            value={many ? "" : values.address}
            maxLength={255}
            disabled={many}
            placeholder={many ? t("hosts.address_from_names") : t("field.address_hint")}
            onChange={(e) => set({ address: e.target.value })}
          />
        </label>
        <label className="oslo-field">
          {t("field.hostagent_port")}
          <input type="number" min={1} max={65535} value={values.hostagent_port} placeholder={values.https ? "1129" : "1128"} onChange={(e) => set({ hostagent_port: e.target.value })} />
        </label>
        <label className="oslo-field">
          {t("field.port_offset")}
          <input type="number" min={0} max={15000} value={values.sapcontrol_port_offset} placeholder={t("field.port_offset_hint")} onChange={(e) => set({ sapcontrol_port_offset: e.target.value })} />
        </label>
      </div>
      <div className="oslo-checks">
        <label className="oslo-inline">
          <input type="checkbox" checked={values.https} onChange={(e) => set({ https: e.target.checked })} /> {t("field.https")}
        </label>
        <label className="oslo-inline">
          <input type="checkbox" checked={values.verify_tls} disabled={!values.https} onChange={(e) => set({ verify_tls: e.target.checked })} /> {t("field.verify_tls")}
        </label>
        <label className="oslo-inline">
          <input
            type="checkbox"
            checked={values.verify_hostname}
            disabled={!values.https || !values.verify_tls}
            onChange={(e) => set({ verify_hostname: e.target.checked })}
          />{" "}
          {t("field.verify_hostname")}
        </label>
      </div>
      {values.https && <p className="oslo-muted">{t("host.verify_hint")}</p>}
    </>
  );
}

export function HostNewPage() {
  const { t } = useApp();
  const [values, setValues] = useState<ConnectionValues>({ name: "", address: "", hostagent_port: "", sapcontrol_port_offset: "", https: false, verify_tls: true, verify_hostname: true });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  return (
    <div className="oslo-page">
      <PageHead title={t("hosts.add")} crumbs={[{ href: LIST, label: t("tab.hosts") }]} />
      <Section>
        <ActionForm
          submit={hostNames(values.name).length > 1 ? t("hosts.add_many", { count: hostNames(values.name).length }) : t("hosts.add")}
          onSubmit={async () => {
            const names = hostNames(values.name);
            if (names.length > 1) {
              const hosts = await api<HostInfo[]>("/hosts/batch", {
                method: "POST",
                body: {
                  names,
                  hostagent_port: values.hostagent_port ? Number(values.hostagent_port) : null,
                  sapcontrol_port_offset: values.sapcontrol_port_offset ? Number(values.sapcontrol_port_offset) : 0,
                  https: values.https,
                  verify_tls: values.verify_tls,
                  verify_hostname: values.verify_hostname,
                  username: username.trim() || null,
                  password: password || null,
                },
              });
              go(`${LIST}?n_count=${hosts.length}`, "hosts_created");
              return;
            }
            const host = await api<HostInfo>("/hosts", {
              method: "POST",
              body: {
                name: names[0] ?? values.name.trim(),
                address: values.address.trim() || null,
                hostagent_port: values.hostagent_port ? Number(values.hostagent_port) : null,
                sapcontrol_port_offset: values.sapcontrol_port_offset ? Number(values.sapcontrol_port_offset) : 0,
                https: values.https,
                verify_tls: values.verify_tls,
                verify_hostname: values.verify_hostname,
                username: username.trim() || null,
                password: password || null,
              },
            });
            go(`${LIST}/${host.id}`, "host_created");
          }}
        >
          <ConnectionFields values={values} onChange={setValues} several />
          <p className="oslo-muted">{t("hosts.names_hint")}</p>
          <div className="oslo-form-grid">
            <label className="oslo-field">
              {t("field.username")}
              <input value={username} autoComplete="off" placeholder="sapadm" onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="oslo-field">
              {t("field.password")}
              <input type="password" value={password} autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
            </label>
          </div>
          <p className="oslo-muted">{t("credentials.host_hint")}</p>
        </ActionForm>
      </Section>
    </div>
  );
}

export function HostPage({ id }: { id: number }) {
  const { t, language } = useApp();
  const queries = useQueryClient();
  const key = ["host", id];
  const { data: host, isPending, error } = useQuery({ queryKey: key, queryFn: () => api<HostDetail>(`/hosts/${id}`) });
  const systems = useQuery({ queryKey: ["systems"], queryFn: () => api<{ id: number; name: string }[]>("/systems") });
  const bundleStatus = useQuery({ queryKey: ["bundle-status"], queryFn: () => api<{ active_version: string | null }>("/bundle-status") });
  const discovery = useAction();
  const [result, setResult] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const reload = () => queries.invalidateQueries({ queryKey: key });

  if (isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (error || !host) return <p className="flash error">{(error as Error)?.message}</p>;
  const systemName = new Map((systems.data ?? []).map((s) => [s.id, s.name]));
  const bundleNow = bundleState(host, bundleStatus.data?.active_version ?? null);

  const discover = () =>
    discovery.run(async () => {
      const out = await api<Record<string, string[]>>(`/hosts/${id}/discover`, { method: "POST" });
      setResult(
        t("notice.discovered", {
          added: out.instances_added.length + out.databases_added.length,
          updated: out.instances_updated.length + out.databases_updated.length,
          missing: out.instances_missing.length + out.databases_missing.length,
        }),
      );
      setWarnings(out.warnings);
      await reload();
    });

  return (
    <div className="oslo-page">
      <PageHead
        title={`${t("field.host")} ${host.name}`}
        crumbs={[{ href: LIST, label: t("tab.hosts") }]}
        extra={
          <>
            <ConfirmButton
              label={t("host.delete")}
              confirm={t("host.delete_confirm")}
              onConfirm={async () => {
                await api(`/hosts/${id}`, { method: "DELETE" });
                go(LIST, "host_deleted");
              }}
            />
            <button type="button" className="oslo-primary" disabled={discovery.busy} onClick={() => void discover()}>
              {t("host.discover")}
            </button>
          </>
        }
      />
      <Messages error={discovery.error} notice={result} />
      {warnings.length > 0 && (
        <div className="flash warning" role="status">
          <strong>{t("warning.discovery")}</strong>
          <ul>
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="oslo-columns">
        <div className="oslo-column">
          <Section title={t("host.system_info")}>
            <dl className="oslo-facts">
              <dt>{t("field.reachable")}</dt>
              <dd>
                <ReachBadge host={host} />
              </dd>
              <dt>{t("field.hostagent")}</dt>
              <dd>{host.hostagent_version ?? ""}</dd>
              <dt>{t("bundle.on_host")}</dt>
              <dd>
                <span className={`oslo-badge oslo-badge-${BUNDLE_BADGE[bundleNow]}`}>{t(`bundle.state.${bundleNow}`)}</span>{" "}
                {host.bundle_version && host.bundle_version !== "none" && <span className="oslo-mono">{host.bundle_version}</span>}
              </dd>
              <dt>{t("field.os")}</dt>
              <dd>{[host.os_name, host.os_version].filter(Boolean).join(" ")}</dd>
              <dt>{t("field.cpus")}</dt>
              <dd>{host.cpu_count ?? ""}</dd>
              <dt>{t("field.memory")}</dt>
              <dd>{memory(host.memory_kb)}</dd>
              <dt>{t("field.last_discovery")}</dt>
              <dd>{host.last_discovery_at ? formatTime(host.last_discovery_at, language) : t("hosts.never")}</dd>
              {host.last_error && (
                <>
                  <dt>{t("field.last_error")}</dt>
                  <dd className="error-text">{host.last_error}</dd>
                </>
              )}
            </dl>
          </Section>
          <Section title={t("credentials.title")}>
            <CredentialsForm
              username={host.username}
              hasCredentials={host.has_credentials}
              hint={t("credentials.host_hint")}
              onSave={async (body) => {
                await api(`/hosts/${id}/credentials`, { method: "PUT", body });
                await reload();
              }}
            />
          </Section>
          <Section title={t("field.tags")}>
            <TagsForm
              tags={host.tags}
              onSave={async (tags) => {
                await api(`/hosts/${id}/tags`, { method: "PUT", body: { tags } });
                await reload();
              }}
            />
          </Section>
        </div>
        <div className="oslo-column">
          <Section title={t("host.connection")} hint={t("host.connection_hint")}>
            <ConnectionForm host={host} onSaved={reload} />
          </Section>
          <Section title={t("host.certificate")} hint={host.https ? t("host.certificate_hint") : undefined}>
            <CertificateSection host={host} />
          </Section>
        </div>
      </div>
      <Section title={t("field.instances")}>
        {!host.instances.length ? (
          <p className="oslo-muted">{t("host.no_instances")}</p>
        ) : (
          <div className="oslo-table-wrap">
            <table className="oslo-table oslo-compact">
              <thead>
                <tr>
                  <th>{t("field.instance")}</th>
                  <th>{t("field.type")}</th>
                  <th>{t("field.hostname")}</th>
                  <th>{t("field.system")}</th>
                  <th>{t("field.status")}</th>
                </tr>
              </thead>
              <tbody>
                {host.instances.map((i) => (
                  <tr key={i.id}>
                    <td className="oslo-mono">{i.label}</td>
                    <td>{i.type_key ? t(i.type_key) : (i.features ?? "")}</td>
                    <td className="oslo-mono">{i.hostname}</td>
                    <td>
                      {i.system_id !== null ? (
                        <a href={`/configuration/systems/${i.system_id}`}>{systemName.get(i.system_id) ?? `#${i.system_id}`}</a>
                      ) : (
                        <a className="oslo-muted" href="/configuration/systems/unassigned">
                          {t("unassigned.label")}
                        </a>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={i.last_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      <Section title={t("field.databases")}>
        {!host.databases.length ? (
          <p className="oslo-muted">{t("host.no_databases")}</p>
        ) : (
          <div className="oslo-table-wrap">
            <table className="oslo-table oslo-compact">
              <thead>
                <tr>
                  <th>{t("field.database")}</th>
                  <th>{t("field.type")}</th>
                  <th>{t("field.release")}</th>
                  <th>{t("field.status")}</th>
                </tr>
              </thead>
              <tbody>
                {host.databases.map((d) => (
                  <tr key={d.id}>
                    <td className="oslo-mono">{d.name}</td>
                    <td>{[d.vendor, d.type].filter(Boolean).join(" ")}</td>
                    <td>{d.release ?? ""}</td>
                    <td>
                      <StatusBadge status={d.last_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      <RecentChanges type="host" id={id} />
    </div>
  );
}

function ConnectionForm({ host, onSaved }: { host: HostInfo; onSaved: () => Promise<unknown> }) {
  const { t } = useApp();
  const [values, setValues] = useState<ConnectionValues>({
    name: host.name,
    address: host.address,
    hostagent_port: host.hostagent_port ? String(host.hostagent_port) : "",
    sapcontrol_port_offset: host.sapcontrol_port_offset ? String(host.sapcontrol_port_offset) : "",
    https: host.https,
    verify_tls: host.verify_tls,
    verify_hostname: host.verify_hostname,
  });
  return (
    <ActionForm
      submit={t("host.edit_connection")}
      onSubmit={async () => {
        await api(`/hosts/${host.id}`, {
          method: "PATCH",
          body: {
            name: values.name.trim(),
            address: values.address.trim() || values.name.trim(),
            hostagent_port: values.hostagent_port ? Number(values.hostagent_port) : 0,
            sapcontrol_port_offset: values.sapcontrol_port_offset ? Number(values.sapcontrol_port_offset) : 0,
            https: values.https,
            verify_tls: values.verify_tls,
            verify_hostname: values.verify_hostname,
          },
        });
        await onSaved();
      }}
    >
      <ConnectionFields values={values} onChange={setValues} />
    </ActionForm>
  );
}

/** Reads the certificate the host agent shows; admins can trust it right here. */
function CertificateSection({ host }: { host: HostInfo }) {
  const { t, role } = useApp();
  const action = useAction();
  const [cert, setCert] = useState<HostCertificate | null>(null);
  const [name, setName] = useState(host.name);
  if (!host.https) return <p className="oslo-muted">{t("host.https_off")}</p>;
  const read = () =>
    action.run(async () => {
      setCert(null);
      setCert(await api<HostCertificate>(`/hosts/${host.id}/certificate`, { method: "POST" }));
    });
  return (
    <>
      <div className="oslo-form-buttons">
        <button type="button" className="oslo-secondary" disabled={action.busy} onClick={() => void read()}>
          {t("host.fetch_certificate")}
        </button>
      </div>
      <Messages error={action.error} notice={action.notice} />
      {cert && (
        <>
          <CertificateFacts cert={cert} />
          {cert.trusted_id !== null ? (
            <p className="flash notice" role="status">
              {t("host.certificate_trusted")}
            </p>
          ) : role !== "admin" ? (
            <p className="oslo-muted">
              {t("host.certificate_untrusted")} {t("host.trust_admin_only")}
            </p>
          ) : (
            <form
              className="oslo-form"
              onSubmit={(e) => {
                e.preventDefault();
                void action.run(async () => {
                  const added = await api<{ id: number }>("/trusted-certificates", { method: "POST", body: { name: name.trim(), pem: cert.pem } });
                  setCert({ ...cert, trusted_id: added.id });
                });
              }}
            >
              <p className="oslo-muted">{t("host.certificate_untrusted")}</p>
              <label className="oslo-field">
                {t("field.name")}
                <input value={name} required maxLength={255} onChange={(e) => setName(e.target.value)} />
              </label>
              <div className="oslo-form-buttons">
                <button type="submit" className="oslo-primary" disabled={action.busy}>
                  {t("host.trust")}
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </>
  );
}
