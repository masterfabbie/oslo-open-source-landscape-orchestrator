// My account: who I am, change password (server page, also used at the first sign-in),
// language and color scheme, personal API tokens.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { ActionForm, ConfirmButton, PageHead, Section } from "../lib/forms";
import { formatTime, useApp } from "../landscape/ui";

interface Me {
  username: string;
  display_name: string | null;
  role: string;
}

interface Token {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
}

export function AccountPage() {
  const { t, language } = useApp();
  const queries = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/me") });
  const tokens = useQuery({ queryKey: ["tokens"], queryFn: () => api<Token[]>("/me/tokens") });
  const [name, setName] = useState("");
  const [days, setDays] = useState("");
  const [created, setCreated] = useState<string | null>(null);

  return (
    <div className="oslo-page">
      <PageHead title={t("account.title")} />
      <div className="oslo-columns">
        <div className="oslo-column">
          <Section title={t("system.general")}>
            {me.data && (
              <dl className="oslo-facts">
                <dt>{t("field.username")}</dt>
                <dd className="oslo-mono">{me.data.username}</dd>
                <dt>{t("field.display_name")}</dt>
                <dd>{me.data.display_name ?? ""}</dd>
                <dt>{t("field.role")}</dt>
                <dd>{t(`role.${me.data.role}`)}</dd>
              </dl>
            )}
            <p>
              <a className="button-link" href="/account/password">
                {t("account.password")}
              </a>
            </p>
          </Section>
          <DisplaySection />
        </div>
        <div className="oslo-column">
          <Section title={t("token.create")} hint={t("token.hint")}>
            <ActionForm
              submit={t("token.create")}
              onSubmit={async () => {
                const expires = days ? new Date(Date.now() + Number(days) * 86_400_000).toISOString() : null;
                const out = await api<{ token: string }>("/me/tokens", { method: "POST", body: { name, expires_at: expires } });
                setCreated(out.token);
                setName("");
                setDays("");
                await queries.invalidateQueries({ queryKey: ["tokens"] });
              }}
            >
              <div className="oslo-form-grid">
                <label className="oslo-field">
                  {t("field.name")}
                  <input value={name} required maxLength={64} placeholder={t("token.name_hint")} onChange={(e) => setName(e.target.value)} />
                </label>
                <label className="oslo-field">
                  {t("token.expires_days")}
                  <input type="number" min={1} max={3650} value={days} placeholder={t("token.never")} onChange={(e) => setDays(e.target.value)} />
                </label>
              </div>
            </ActionForm>
            {created && (
              <div className="flash notice" role="status">
                <strong>{t("token.created")}</strong>
                <p className="oslo-mono oslo-token">{created}</p>
              </div>
            )}
          </Section>
        </div>
      </div>
      <Section title={t("token.title")}>
        {!tokens.data?.length ? (
          <p className="oslo-muted">{t("token.none")}</p>
        ) : (
          <div className="oslo-table-wrap">
            <table className="oslo-table oslo-compact">
              <thead>
                <tr>
                  <th>{t("field.name")}</th>
                  <th>{t("token.prefix")}</th>
                  <th>{t("token.created_at")}</th>
                  <th>{t("token.expires")}</th>
                  <th>{t("token.last_used")}</th>
                  <th>{t("field.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {tokens.data.map((token) => (
                  <tr key={token.id}>
                    <td>{token.name}</td>
                    <td className="oslo-mono">{token.prefix}…</td>
                    <td className="oslo-muted">{formatTime(token.created_at, language)}</td>
                    <td className="oslo-muted">{token.expires_at ? formatTime(token.expires_at, language) : t("token.never")}</td>
                    <td className="oslo-muted">{token.last_used_at ? formatTime(token.last_used_at, language) : t("hosts.never")}</td>
                    <td>
                      <ConfirmButton
                        label={t("token.delete")}
                        confirm={t("token.delete_confirm")}
                        onConfirm={async () => {
                          await api(`/me/tokens/${token.id}`, { method: "DELETE" });
                          await queries.invalidateQueries({ queryKey: ["tokens"] });
                        }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}

interface Preferences {
  language: string;
  theme: string;
}

/** Language and color scheme; the page reloads so that the server applies them. */
function DisplaySection() {
  const loaded = useQuery({ queryKey: ["preferences"], queryFn: () => api<Preferences>("/me/preferences") });
  if (!loaded.data) return null;
  return <DisplayForm initial={loaded.data} />;
}

function DisplayForm({ initial }: { initial: Preferences }) {
  const { t } = useApp();
  const [language, setLanguage] = useState(initial.language);
  const [theme, setTheme] = useState(initial.theme);
  return (
    <Section title={t("account.display")} hint={t("account.display_hint")}>
      <ActionForm
        submit={t("action.save")}
        onSubmit={async () => {
          await api("/me/preferences", { method: "PUT", body: { language, theme } });
          window.location.reload();
        }}
      >
        <div className="oslo-form-grid">
          <label className="oslo-field">
            {t("account.language")}
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="">{t("account.language_auto")}</option>
              <option value="en">English</option>
              <option value="de">Deutsch</option>
            </select>
          </label>
          <label className="oslo-field">
            {t("account.theme")}
            <select value={theme} onChange={(e) => setTheme(e.target.value)}>
              {["system", "light", "dark"].map((value) => (
                <option key={value} value={value}>
                  {t(`theme.${value}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </ActionForm>
    </Section>
  );
}
