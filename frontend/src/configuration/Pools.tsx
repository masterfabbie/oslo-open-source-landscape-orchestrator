// Configuration → Pools: list with the systems of each pool, create, delete.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { ActionForm, ConfirmButton, PageHead, Section, go } from "../lib/forms";
import { useApp } from "../landscape/ui";
import type { PoolInfo, SystemInfo } from "./types";

const LIST = "/configuration/pools";

export function PoolsPage() {
  const { t } = useApp();
  const queries = useQueryClient();
  const pools = useQuery({ queryKey: ["pools"], queryFn: () => api<PoolInfo[]>("/pools") });
  const systems = useQuery({ queryKey: ["systems"], queryFn: () => api<SystemInfo[]>("/systems") });
  const name = new Map((systems.data ?? []).map((s) => [s.id, s.name]));
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
                <th>{t("field.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {pools.data.map((p) => (
                <tr key={p.id}>
                  <td className="oslo-strong">{p.name}</td>
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
