// Administration: platform information, users (list, create, edit, reset password), the
// rules of "needs attention" on the overview, which apply to everyone, and the certificates
// OSLO trusts for HTTPS to hosts.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { RecentChanges } from "../lib/changes";
import { CertificateFacts } from "../lib/certificate";
import { ActionForm, ConfirmButton, PageHead, Section, go } from "../lib/forms";
import type { CertificateInfo, TrustedCertificate } from "../configuration/types";
import { StatusBadge, formatTime, useApp } from "../landscape/ui";

const ROLES = ["viewer", "operator", "configurator", "admin"];
const STAGES = ["sandbox", "development", "quality", "preprod", "production"];
const STATUSES = ["RED", "YELLOW", "GRAY", "UNKNOWN"];

interface UserRow {
  id: number;
  username: string;
  display_name: string | null;
  role: string;
  active: boolean;
  must_change_password: boolean;
  created_at: string;
  last_login_at: string | null;
}

export function GeneralPage() {
  const { t } = useApp();
  const { data } = useQuery({
    queryKey: ["platform"],
    queryFn: () => api<{ version: string; database: string; session_hours: number; timezone: string }>("/platform"),
  });
  return (
    <div className="oslo-page">
      <PageHead title={t("tab.general")} tabs={[{ href: "/administration", label: t("tab.overview"), current: true }]} />
      <Section hint={t("admin.planned")}>
        {data && (
          <dl className="oslo-facts">
            <dt>{t("admin.version")}</dt>
            <dd className="oslo-mono">{data.version}</dd>
            <dt>{t("admin.database")}</dt>
            <dd className="oslo-mono">{data.database}</dd>
            <dt>{t("admin.session")}</dt>
            <dd>{t("admin.session_hours", { hours: data.session_hours })}</dd>
            <dt>{t("admin.timezone")}</dt>
            <dd className="oslo-mono">{data.timezone}</dd>
          </dl>
        )}
      </Section>
      <RetentionSection />
    </div>
  );
}

function RetentionSection() {
  const { t } = useApp();
  const { data } = useQuery({ queryKey: ["config-log-settings"], queryFn: () => api<{ retention_days: number }>("/config-log-settings") });
  const [days, setDays] = useState<string | null>(null);
  if (!data) return null;
  const shown = days ?? String(data.retention_days);
  return (
    <Section title={t("cfg.retention")} hint={t("cfg.retention_hint")}>
      <ActionForm
        submit={t("action.save")}
        onSubmit={() => api("/config-log-settings", { method: "PUT", body: { retention_days: Number(shown) } })}
      >
        <label>
          {t("cfg.retention_days")}
          <input type="number" min={1} max={3650} required value={shown} onChange={(e) => setDays(e.target.value)} />
        </label>
      </ActionForm>
    </Section>
  );
}

export function UsersPage() {
  const { t, language } = useApp();
  const { data, isPending } = useQuery({ queryKey: ["users"], queryFn: () => api<UserRow[]>("/users") });
  return (
    <div className="oslo-page">
      <PageHead title={t("tab.users")} action={{ href: "/administration/users/new", label: t("users.add") }} tabs={[{ href: "/administration/users", label: t("tab.overview"), current: true }]} />
      <p className="oslo-muted">{t("users.roles_hint")}</p>
      {isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("field.username")}</th>
                <th>{t("field.display_name")}</th>
                <th>{t("field.role")}</th>
                <th>{t("field.status")}</th>
                <th>{t("users.last_login")}</th>
              </tr>
            </thead>
            <tbody>
              {data?.map((u) => (
                <tr key={u.id}>
                  <td>
                    <a className="oslo-strong oslo-mono" href={`/administration/users/${u.id}`}>
                      {u.username}
                    </a>
                  </td>
                  <td>{u.display_name ?? ""}</td>
                  <td>{t(`role.${u.role}`)}</td>
                  <td>
                    <StatusBadge status={u.active ? "GREEN" : "GRAY"} prefix="userstate" />
                    {u.must_change_password && <span className="oslo-sub">{t("users.must_change")}</span>}
                  </td>
                  <td className="oslo-muted">{u.last_login_at ? formatTime(u.last_login_at, language) : t("hosts.never")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function UserNewPage() {
  const { t } = useApp();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState("viewer");
  const [password, setPassword] = useState("");
  return (
    <div className="oslo-page">
      <PageHead title={t("users.add")} crumbs={[{ href: "/administration/users", label: t("tab.users") }]} />
      <Section>
        <ActionForm
          submit={t("users.add")}
          onSubmit={async () => {
            const user = await api<UserRow>("/users", { method: "POST", body: { username, display_name: displayName || null, role, password } });
            go(`/administration/users/${user.id}`, "user_created");
          }}
        >
          <div className="oslo-form-grid">
            <label className="oslo-field">
              {t("field.username")}
              <input value={username} required maxLength={64} autoComplete="off" onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="oslo-field">
              {t("field.display_name")}
              <input value={displayName} maxLength={255} onChange={(e) => setDisplayName(e.target.value)} />
            </label>
            <label className="oslo-field">
              {t("field.role")}
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {t(`role.${r}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="oslo-field">
              {t("users.start_password")}
              <input type="password" value={password} required minLength={12} autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
            </label>
          </div>
          <p className="oslo-muted">{t("users.start_password_hint")}</p>
        </ActionForm>
      </Section>
    </div>
  );
}

export function UserPage({ id }: { id: number }) {
  const { t } = useApp();
  const { data, isPending } = useQuery({ queryKey: ["users"], queryFn: () => api<UserRow[]>("/users") });
  const user = data?.find((u) => u.id === id);
  if (isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (!user) return <p className="flash error">404</p>;
  return (
    <>
      <UserEditor user={user} />
      <div className="oslo-page"><RecentChanges type="user" id={id} /></div>
    </>
  );
}

function UserEditor({ user }: { user: UserRow }) {
  const { t } = useApp();
  const [displayName, setDisplayName] = useState(user.display_name ?? "");
  const [role, setRole] = useState(user.role);
  const [active, setActive] = useState(user.active);
  const [password, setPassword] = useState("");
  return (
    <div className="oslo-page">
      <PageHead title={`${t("users.user")} ${user.username}`} crumbs={[{ href: "/administration/users", label: t("tab.users") }]} />
      <div className="oslo-two">
        <Section title={t("system.general")}>
          <ActionForm submit={t("action.save")} onSubmit={() => api(`/users/${user.id}`, { method: "PATCH", body: { display_name: displayName || null, role, active } })}>
            <div className="oslo-form-grid">
              <label className="oslo-field">
                {t("field.display_name")}
                <input value={displayName} maxLength={255} onChange={(e) => setDisplayName(e.target.value)} />
              </label>
              <label className="oslo-field">
                {t("field.role")}
                <select value={role} onChange={(e) => setRole(e.target.value)}>
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {t(`role.${r}`)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="oslo-inline">
              <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> {t("users.active")}
            </label>
            <p className="oslo-muted">{t("users.save_hint")}</p>
          </ActionForm>
        </Section>
        <Section title={t("users.reset_password")}>
          <ActionForm submit={t("users.reset_password")} onSubmit={() => api(`/users/${user.id}/password`, { method: "PUT", body: { password } })}>
            <label className="oslo-field">
              {t("users.start_password")}
              <input type="password" value={password} required minLength={12} autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
            </label>
            <p className="oslo-muted">{t("users.start_password_hint")}</p>
          </ActionForm>
        </Section>
      </div>
    </div>
  );
}

// --- rules of "needs attention" ---------------------------------------------------------------

type Rules = Record<string, Record<string, boolean | number | string[]>>;

/** Settings of each rule with their kind, in the order shown. */
const SETTINGS: Record<string, [string, "number" | "bool" | "stages" | "statuses" | "operations"][]> = {
  failed_activities: [
    ["hours", "number"],
    ["hide_scheduled_every_minutes", "number"],
    ["hide_when_succeeded_later", "bool"],
    ["hide_operations", "operations"],
    ["stages", "stages"],
  ],
  system_status: [
    ["statuses", "statuses"],
    ["stages", "stages"],
  ],
  stopped_systems: [["stages", "stages"]],
  long_running: [["minutes", "number"]],
  host_unreachable: [],
  schedule_errors: [],
  stale_discovery: [["days", "number"]],
  bundle_outdated: [],
};

export function AttentionPage() {
  const { t } = useApp();
  const loaded = useQuery({ queryKey: ["rules"], queryFn: () => api<{ rules: Rules }>("/attention-rules") });
  const operations = useQuery({ queryKey: ["operations"], queryFn: () => api<{ key: string; name: string | null }[]>("/operations") });
  if (loaded.isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (!loaded.data) return <p className="flash error">{(loaded.error as Error)?.message}</p>;
  return <RulesEditor initial={loaded.data.rules} operations={operations.data ?? []} />;
}

function RulesEditor({ initial, operations }: { initial: Rules; operations: { key: string; name: string | null }[] }) {
  const { t } = useApp();
  const [rules, setRules] = useState<Rules>(initial);
  const set = (rule: string, key: string, value: boolean | number | string[]) => setRules({ ...rules, [rule]: { ...rules[rule], [key]: value } });
  const toggleIn = (rule: string, key: string, item: string, on: boolean) => {
    const list = (rules[rule][key] as string[]) ?? [];
    set(rule, key, on ? [...list, item] : list.filter((x) => x !== item));
  };
  const opName = (op: { key: string; name: string | null }) => op.name ?? t(`op.${op.key}`);

  return (
    <div className="oslo-page">
      <PageHead title={t("ov.attention")} tabs={[{ href: "/administration/attention", label: t("tab.overview"), current: true }]} />
      <p className="oslo-muted">{t("att.rules_intro")}</p>
      <ActionForm submit={t("action.save")} onSubmit={() => api("/attention-rules", { method: "PUT", body: { rules } })}>
        <div className="oslo-two">
          {Object.entries(SETTINGS).map(([rule, settings]) => (
            <Section key={rule} title={t(`att.rule.${rule}`)} hint={t(`att.hint.${rule}`)}>
              <label className="oslo-inline">
                <input type="checkbox" checked={rules[rule].enabled as boolean} onChange={(e) => set(rule, "enabled", e.target.checked)} /> {t("att.enabled")}
              </label>
              {settings.map(([key, kind]) => {
                const value = rules[rule][key];
                if (kind === "number")
                  return (
                    <label key={key} className="oslo-field">
                      {t(`att.setting.${key}`)}
                      <input type="number" min={0} max={100000} value={value as number} disabled={!rules[rule].enabled} onChange={(e) => set(rule, key, Number(e.target.value))} />
                    </label>
                  );
                if (kind === "bool")
                  return (
                    <label key={key} className="oslo-inline">
                      <input type="checkbox" checked={value as boolean} disabled={!rules[rule].enabled} onChange={(e) => set(rule, key, e.target.checked)} /> {t(`att.setting.${key}`)}
                    </label>
                  );
                const items =
                  kind === "stages"
                    ? STAGES.map((s) => [s, t(`stage.${s}`)])
                    : kind === "statuses"
                      ? STATUSES.map((s) => [s, t(`status.${s}`)])
                      : operations.map((op) => [op.key, opName(op)]);
                return (
                  <fieldset key={key} className="oslo-checks" disabled={!rules[rule].enabled}>
                    <legend>{t(`att.setting.${key}`)}</legend>
                    {items.map(([item, label]) => (
                      <label key={item} className="oslo-inline">
                        <input type="checkbox" checked={(value as string[]).includes(item)} onChange={(e) => toggleIn(rule, key, item, e.target.checked)} />
                        {label}
                      </label>
                    ))}
                  </fieldset>
                );
              })}
            </Section>
          ))}
        </div>
      </ActionForm>
    </div>
  );
}

// --- trusted certificates -------------------------------------------------------------------

const CERTS = "/administration/certificates";

export function CertificatesPage() {
  const { t } = useApp();
  const { data, isPending, refetch } = useQuery({
    queryKey: ["trusted-certificates"],
    queryFn: () => api<TrustedCertificate[]>("/trusted-certificates"),
  });
  return (
    <div className="oslo-page">
      <PageHead title={t("tab.certificates")} action={{ href: `${CERTS}/new`, label: t("cert.add") }} tabs={[{ href: CERTS, label: t("tab.overview"), current: true }]} />
      <p className="oslo-muted">{t("cert.intro")}</p>
      {isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !data?.length ? (
        <p className="oslo-empty">{t("cert.empty")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("field.name")}</th>
                <th>{t("field.valid_until")}</th>
                <th>{t("cert.added_by")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <CertificateRow key={c.id} cert={c} onDeleted={() => void refetch()} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** One trusted certificate; subject, issuer and fingerprint can be long, so they open below
 * the row with "Details" and do not widen the table. */
function CertificateRow({ cert, onDeleted }: { cert: TrustedCertificate; onDeleted: () => void }) {
  const { t, language } = useApp();
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr>
        <td>
          <span className="oslo-strong">{cert.name}</span>
          {cert.self_signed && <span className="oslo-badge oslo-badge-gray oslo-cert-tag">{t("cert.self_signed")}</span>}
        </td>
        <td>
          {formatTime(cert.not_after, language)} {cert.expired && <span className="oslo-badge oslo-badge-red">{t("cert.expired")}</span>}
        </td>
        <td className="oslo-muted">
          {formatTime(cert.created_at, language)}
          {cert.created_by && <span className="oslo-sub">{cert.created_by}</span>}
        </td>
        <td className="oslo-row-actions">
          <button type="button" className="oslo-secondary" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? t("cert.hide_details") : t("cert.details")}
          </button>
          <ConfirmButton
            label={t("cert.delete")}
            confirm={t("cert.delete_confirm")}
            onConfirm={async () => {
              await api(`/trusted-certificates/${cert.id}`, { method: "DELETE" });
              onDeleted();
            }}
          />
        </td>
      </tr>
      {open && (
        <tr className="oslo-details-row">
          <td colSpan={4}>
            <CertificateFacts cert={cert} />
          </td>
        </tr>
      )}
    </>
  );
}

export function CertificateNewPage() {
  const { t } = useApp();
  const [name, setName] = useState("");
  const [pem, setPem] = useState("");
  const [preview, setPreview] = useState<CertificateInfo | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const check = async (text: string) => {
    setPreview(null);
    setCheckError(null);
    if (!text.trim()) return;
    try {
      setPreview(await api<CertificateInfo>("/trusted-certificates/check", { method: "POST", body: { name: name || "-", pem: text } }));
    } catch (exc) {
      setCheckError(exc instanceof Error ? exc.message : String(exc));
    }
  };
  return (
    <div className="oslo-page">
      <PageHead title={t("cert.add")} crumbs={[{ href: CERTS, label: t("tab.certificates") }]} />
      <Section hint={t("cert.intro")}>
        <ActionForm
          submit={t("cert.add")}
          onSubmit={async () => {
            await api("/trusted-certificates", { method: "POST", body: { name: name.trim(), pem } });
            go(CERTS, "certificate_added");
          }}
        >
          <label className="oslo-field">
            {t("field.name")}
            <input value={name} required maxLength={255} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="oslo-field">
            {t("cert.pem")}
            <textarea
              className="oslo-pem"
              value={pem}
              required
              spellCheck={false}
              placeholder="-----BEGIN CERTIFICATE-----"
              onChange={(e) => {
                setPem(e.target.value);
                setPreview(null);
              }}
              onBlur={() => void check(pem)}
            />
          </label>
          <label className="oslo-field">
            {t("cert.file")}
            <input
              type="file"
              accept=".pem,.crt,.cer,.txt"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                void file.text().then((text) => {
                  setPem(text);
                  void check(text);
                });
              }}
            />
          </label>
          <p className="oslo-muted">{t("cert.pem_hint")}</p>
          {checkError && (
            <p className="flash error" role="alert">
              {checkError}
            </p>
          )}
          {preview && <CertificateFacts cert={preview} />}
        </ActionForm>
      </Section>
    </div>
  );
}
