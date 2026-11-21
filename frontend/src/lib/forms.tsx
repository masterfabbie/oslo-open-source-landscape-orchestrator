// Shared pieces of the form pages (configuration, operations, administration, account):
// page head with create button and tabs, sections, error and notice lines, actions that
// call the API, tags and credentials.

import { type FormEvent, type ReactNode, useState } from "react";
import { useApp } from "../landscape/ui";
import { ApiError } from "./api";

export interface TabLink {
  href: string;
  label: string;
  current?: boolean;
}

/** Title, the create button on the right and the tabs below, as on every page of an area. */
export function PageHead({
  title,
  action,
  tabs,
  crumbs,
  extra,
}: {
  title: ReactNode;
  action?: { href: string; label: string };
  tabs?: TabLink[];
  crumbs?: { href: string; label: string }[];
  extra?: ReactNode;
}) {
  return (
    <>
      {crumbs && crumbs.length > 0 && (
        <p className="crumbs">
          {crumbs.map((c, i) => (
            <span key={c.href}>
              {i > 0 && " / "}
              <a href={c.href}>{c.label}</a>
            </span>
          ))}
        </p>
      )}
      <div className="page-head">
        <h1>{title}</h1>
        {(action || extra) && (
          <span className="buttons">
            {extra}
            {action && (
              <a className="button-primary" href={action.href}>
                {action.label}
              </a>
            )}
          </span>
        )}
      </div>
      {tabs && (
        <nav className="tabs" aria-label={typeof title === "string" ? title : undefined}>
          {tabs.map((tab) => (
            <a key={tab.href} href={tab.href} aria-current={tab.current ? "page" : undefined}>
              {tab.label}
            </a>
          ))}
        </nav>
      )}
    </>
  );
}

export function errorMessage(exc: unknown, t: (key: string) => string): string {
  if (exc instanceof ApiError && exc.code) return `${t(`error.${exc.code}`)} ${exc.message}`;
  return exc instanceof Error ? exc.message : String(exc);
}

/** Runs API calls of a form: ``busy`` while running, ``error`` and ``notice`` afterwards. */
export function useAction() {
  const { t } = useApp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const run = async (action: () => Promise<unknown>, done?: string): Promise<boolean> => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      if (done) setNotice(done);
      return true;
    } catch (exc) {
      setError(errorMessage(exc, t));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, notice, run, setError };
}

export function Messages({ error, notice }: { error: string | null; notice?: string | null }) {
  return (
    <>
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
    </>
  );
}

export function Section({ title, children, hint }: { title?: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <section className="oslo-card oslo-form-section">
      {title && <h2>{title}</h2>}
      {hint && <p className="oslo-muted">{hint}</p>}
      {children}
    </section>
  );
}

/** A form that runs ``onSubmit`` with the action state and shows its messages. */
export function ActionForm({
  onSubmit,
  submit,
  children,
  danger,
  className,
}: {
  onSubmit: () => Promise<unknown>;
  submit: string;
  children?: ReactNode;
  danger?: boolean;
  className?: string;
}) {
  const action = useAction();
  const { t } = useApp();
  return (
    <form
      className={`oslo-form ${className ?? ""}`}
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        void action.run(onSubmit, t("ui.saved"));
      }}
    >
      {children}
      <Messages error={action.error} notice={action.notice} />
      <div className="oslo-form-buttons">
        <button type="submit" className={danger ? "oslo-danger-outline" : "oslo-primary"} disabled={action.busy}>
          {submit}
        </button>
      </div>
    </form>
  );
}

/** A button that asks first and then calls the API. */
export function ConfirmButton({
  label,
  confirm,
  onConfirm,
  className = "oslo-danger-outline",
}: {
  label: string;
  confirm: string;
  onConfirm: () => Promise<unknown>;
  className?: string;
}) {
  const action = useAction();
  return (
    <>
      <button
        type="button"
        className={className}
        disabled={action.busy}
        onClick={() => {
          if (window.confirm(confirm)) void action.run(onConfirm);
        }}
      >
        {label}
      </button>
      {action.error && (
        <span className="error-text" role="alert">
          {action.error}
        </span>
      )}
    </>
  );
}

export function TagsForm({ tags, onSave }: { tags: string[]; onSave: (tags: string[]) => Promise<unknown> }) {
  const { t } = useApp();
  const [value, setValue] = useState(tags.join(", "));
  return (
    <ActionForm
      submit={t("action.save")}
      onSubmit={() =>
        onSave(
          value
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
        )
      }
    >
      <label className="oslo-field">
        {t("field.tags")}
        <input value={value} placeholder="dev, sla=1" onChange={(e) => setValue(e.target.value)} />
      </label>
      <p className="oslo-muted">{t("tags.hint")}</p>
    </ActionForm>
  );
}

export function CredentialsForm({
  username,
  hasCredentials,
  hint,
  onSave,
}: {
  username: string | null;
  hasCredentials: boolean;
  hint?: string;
  onSave: (credentials: { username: string; password: string }) => Promise<unknown>;
}) {
  const { t } = useApp();
  const [user, setUser] = useState(username ?? "");
  const [password, setPassword] = useState("");
  return (
    <ActionForm submit={t("credentials.save")} onSubmit={() => onSave({ username: user, password })}>
      <p className="oslo-muted">
        {hasCredentials ? `${username} (${t("credentials.set")})` : t("credentials.missing")}
        {hint ? ` · ${hint}` : ""}
      </p>
      <div className="oslo-form-grid">
        <label className="oslo-field">
          {t("field.username")}
          <input value={user} required autoComplete="off" onChange={(e) => setUser(e.target.value)} />
        </label>
        <label className="oslo-field">
          {t("field.password")}
          <input type="password" value={password} required autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
        </label>
      </div>
    </ActionForm>
  );
}

/** Go to a page, with a notice the server shows there (?notice=…). */
export function go(path: string, notice?: string): void {
  const separator = path.includes("?") ? "&" : "?";
  window.location.assign(notice ? `${path}${separator}notice=${notice}` : path);
}
