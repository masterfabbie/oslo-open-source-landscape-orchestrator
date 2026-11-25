// Configuration → Pools: list with the systems of each pool, create, edit, delete.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { RecentChanges } from "../lib/changes";
import { ActionForm, ConfirmButton, PageHead, Section, go } from "../lib/forms";
import { useApp } from "../landscape/ui";
import type { HostInfo, PoolInfo, SystemInfo } from "./types";

const LIST = "/configuration/pools";

export function PoolsPage() {
  const { t } = useApp();
  const queries = useQueryClient();
  const pools = useQuery({ queryKey: ["pools"], queryFn: () => api<PoolInfo[]>("/pools") });
  const systems = useQuery({ queryKey: ["systems"], queryFn: () => api<SystemInfo[]>("/systems") });
  const hosts = useQuery({ queryKey: ["hosts"], queryFn: () => api<HostInfo[]>("/hosts") });
  const name = new Map((systems.data ?? []).map((s) => [s.id, s.name]));
  const hostName = new Map((hosts.data ?? []).map((h) => [h.id, h.name]));
  return (
    <div className="oslo-page">
      <PageHead title={t("tab.pools")} action={{ href: `${LIST}/new`, label: t("pool.add") }} tabs={[{ href: LIST, label: t("tab.overview"), current: true }]} />
      <p className="oslo-muted">{t("pool.explanation")}</p>
      {pools.isPending ? (
        <p className="oslo-muted">{t("ui.loading")}</p>
      ) : !pools.data?.length ? (
        <p className="oslo-empty">{t("pool.empty")}</p>
      ) : (
        <div className="oslo-table-wrap">
          <table className="oslo-table">
            <thead>
              <tr>
                <th>{t("field.name")}</th>
                <th>{t("field.description")}</th>
                <th>{t("tab.systems")}</th>
                <th>{t("tab.hosts")}</th>
                <th>{t("field.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {pools.data.map((p) => (
                <tr key={p.id}>
                  <td>
                    <a className="oslo-strong" href={`${LIST}/${p.id}`}>
                      {p.name}
                    </a>
                  </td>
                  <td>{p.description ?? ""}</td>
                  <td>
                    {p.system_ids.length ? (
                      p.system_ids.map((id, i) => (
                        <span key={id}>
                          {i > 0 && ", "}
                          <a href={`/configuration/systems/${id}`}>{name.get(id) ?? `#${id}`}</a>
                        </span>
                      ))
                    ) : (
                      <span className="oslo-muted">{t("deps.none")}</span>
                    )}
                  </td>
                  <td>
                    {p.host_ids.length ? (
                      p.host_ids.map((id, i) => (
                        <span key={id}>
                          {i > 0 && ", "}
                          <a href={`/configuration/hosts/${id}`}>{hostName.get(id) ?? `#${id}`}</a>
                        </span>
                      ))
                    ) : (
                      <span className="oslo-muted">{t("deps.none")}</span>
                    )}
                  </td>
                  <td>
                    <ConfirmButton
                      label={t("pool.delete")}
                      confirm={t("pool.delete_confirm")}
                      onConfirm={async () => {
                        await api(`/pools/${p.id}`, { method: "DELETE" });
                        await queries.invalidateQueries();
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function PoolNewPage() {
  const { t } = useApp();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  return (
    <div className="oslo-page">
      <PageHead title={t("pool.add")} crumbs={[{ href: LIST, label: t("tab.pools") }]} />
      <Section hint={t("pool.explanation")}>
        <ActionForm
          submit={t("pool.add")}
          onSubmit={async () => {
            await api("/pools", { method: "POST", body: { name: name.trim(), description: description || null } });
            go(LIST, "pool_created");
          }}
        >
          <div className="oslo-form-grid">
            <label className="oslo-field">
              {t("field.name")}
              <input value={name} required maxLength={64} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="oslo-field">
              {t("field.description")}
              <input value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} />
            </label>
          </div>
        </ActionForm>
      </Section>
    </div>
  );
}

export function PoolPage({ id }: { id: number }) {
  const { t } = useApp();
  const pool = useQuery({ queryKey: ["pool", id], queryFn: () => api<PoolInfo>(`/pools/${id}`) });
  const systems = useQuery({ queryKey: ["systems"], queryFn: () => api<SystemInfo[]>("/systems") });
  const hosts = useQuery({ queryKey: ["hosts"], queryFn: () => api<HostInfo[]>("/hosts") });
  if (pool.isPending) return <p className="oslo-muted">{t("ui.loading")}</p>;
  if (!pool.data) return <p className="flash error">{(pool.error as Error)?.message}</p>;
  return (
    <>
      <PoolEditor pool={pool.data} systems={systems.data ?? []} hosts={hosts.data ?? []} />
      <div className="oslo-page"><RecentChanges type="pool" id={id} /></div>
    </>
  );
}

function PoolEditor({ pool, systems, hosts }: { pool: PoolInfo; systems: SystemInfo[]; hosts: HostInfo[] }) {
  const { t } = useApp();
  const queries = useQueryClient();
  const [name, setName] = useState(pool.name);
  const [description, setDescription] = useState(pool.description ?? "");
  const members = systems.filter((s) => pool.system_ids.includes(s.id));
  const memberHosts = hosts.filter((h) => pool.host_ids.includes(h.id));
  return (
    <div className="oslo-page">
      <PageHead
        title={t("pool.title", { name: pool.name })}
        crumbs={[{ href: LIST, label: t("tab.pools") }]}
        extra={
          <ConfirmButton
            label={t("pool.delete")}
            confirm={t("pool.delete_confirm")}
            onConfirm={async () => {
              await api(`/pools/${pool.id}`, { method: "DELETE" });
              go(LIST, "pool_deleted");
            }}
          />
        }
      />
      <div className="oslo-two">
        <Section title={t("system.general")}>
          <ActionForm
            submit={t("action.save")}
            onSubmit={async () => {
              await api(`/pools/${pool.id}`, { method: "PATCH", body: { name: name.trim(), description } });
              await queries.invalidateQueries();
            }}
          >
            <label className="oslo-field">
              {t("field.name")}
              <input value={name} required maxLength={64} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="oslo-field">
              {t("field.description")}
              <input value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} />
            </label>
          </ActionForm>
        </Section>
        <Section title={t("tab.systems")} hint={t("pool.systems_hint")}>
          {members.length ? (
            <ul className="oslo-plain-list">
              {members.map((s) => (
                <li key={s.id}>
                  <a href={`/configuration/systems/${s.id}`}>{s.name}</a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="oslo-muted">{t("deps.none")}</p>
          )}
        </Section>
        <Section title={t("tab.hosts")} hint={t("pool.hosts_hint")}>
          {memberHosts.length ? (
            <ul className="oslo-plain-list">
              {memberHosts.map((h) => (
                <li key={h.id}>
                  <a href={`/configuration/hosts/${h.id}`}>{h.name}</a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="oslo-muted">{t("deps.none")}</p>
          )}
        </Section>
      </div>
    </div>
  );
}
