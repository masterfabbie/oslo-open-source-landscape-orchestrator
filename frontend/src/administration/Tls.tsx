// Administration → HTTPS: the certificate OSLO itself serves with `oslo-server --tls`. The
// private key is always created on the server, never uploaded: either with a self-signed
// certificate, or with a certificate signing request (CSR) for your own CA, whose signed
// certificate is then uploaded.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { ActionForm, PageHead, Section } from "../lib/forms";
import { formatTime, useApp } from "../landscape/ui";

const PAGE = "/administration/tls";

interface TlsCertificate {
  subject: string;
  issuer: string;
  names: string[];
  not_before: string;
  not_after: string;
  self_signed: boolean;
  expired: boolean;
  pem: string;
}

interface TlsStatus {
  https: boolean;
  certificate: TlsCertificate | null;
  csr: string | null;
}

const IP = /^(\d{1,3}(\.\d{1,3}){3}|[0-9a-fA-F:]+:[0-9a-fA-F:]*)$/;

/** "a, b c" → ["a", "b", "c"] */
export function splitList(text: string): string[] {
  return text
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function saveText(text: string, name: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/x-pem-file" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export function TlsPage() {
  const { t } = useApp();
  const { data, isPending } = useQuery({ queryKey: ["tls"], queryFn: () => api<TlsStatus>("/tls") });
  if (isPending || !data) return <p className="oslo-muted">{t("ui.loading")}</p>;
  return (
    <div className="oslo-page">
      <PageHead title={t("tab.tls")} tabs={[{ href: PAGE, label: t("tab.overview"), current: true }]} />
      <p className="oslo-muted">{t("tls.intro")}</p>
      <StatusSection status={data} />
      <div className="oslo-columns">
        <div className="oslo-column">
          <SelfSignedSection hasCertificate={Boolean(data.certificate)} />
        </div>
        <div className="oslo-column">
          <RequestSection csr={data.csr} />
        </div>
      </div>
    </div>
  );
}

function StatusSection({ status }: { status: TlsStatus }) {
  const { t, language } = useApp();
  const cert = status.certificate;
  return (
    <Section title={t("tls.status")}>
      <dl className="oslo-facts">
        <dt>{t("tls.connection")}</dt>
        <dd>
          <span className={`oslo-badge oslo-badge-${status.https ? "green" : "yellow"}`}>{status.https ? "HTTPS" : "HTTP"}</span>
        </dd>
        <dt>{t("tls.certificate")}</dt>
        <dd>{cert ? cert.names.join(", ") : t("tls.none")}</dd>
        {cert && (
          <>
            <dt>{t("field.valid_until")}</dt>
            <dd>
              {formatTime(cert.not_after, language)} {cert.expired && <span className="oslo-badge oslo-badge-red">{t("cert.expired")}</span>}
            </dd>
            <dt>{t("field.issuer")}</dt>
            <dd className="oslo-mono oslo-wrap">
              {cert.self_signed ? <span className="oslo-badge oslo-badge-gray">{t("cert.self_signed")}</span> : cert.issuer}
            </dd>
          </>
        )}
      </dl>
      {cert && !status.https && (
        <>
          <p>{t("tls.restart")}</p>
          <pre className="oslo-code">oslo-server --tls</pre>
        </>
      )}
      {cert && (
        <div className="oslo-form-buttons">
          <button type="button" className="oslo-secondary" onClick={() => saveText(cert.pem, "oslo-certificate.pem")}>
            {t("tls.download_cert")}
          </button>
          {cert.self_signed && <span className="oslo-muted">{t("tls.ca_hint")}</span>}
        </div>
      )}
    </Section>
  );
}

function defaults(): { names: string; ips: string } {
  const host = window.location.hostname;
  return IP.test(host) ? { names: "", ips: host } : { names: host, ips: "" };
}

function NameFields({ names, ips, setNames, setIps }: { names: string; ips: string; setNames: (v: string) => void; setIps: (v: string) => void }) {
  const { t } = useApp();
  return (
    <>
      <label className="oslo-field">
        {t("tls.names")}
        <input value={names} placeholder="oslo.example.com" onChange={(e) => setNames(e.target.value)} />
      </label>
      <label className="oslo-field">
        {t("tls.ips")}
        <input value={ips} placeholder="10.0.0.10" onChange={(e) => setIps(e.target.value)} />
      </label>
    </>
  );
}

function SelfSignedSection({ hasCertificate }: { hasCertificate: boolean }) {
  const { t } = useApp();
  const queries = useQueryClient();
  const start = defaults();
  const [names, setNames] = useState(start.names);
  const [ips, setIps] = useState(start.ips);
  const [days, setDays] = useState("730");
  return (
    <Section title={t("tls.self_signed")} hint={t("tls.self_signed_hint")}>
      <ActionForm
        submit={t("tls.create")}
        onSubmit={async () => {
          if (hasCertificate && !window.confirm(t("tls.replace_confirm"))) return;
          await api("/tls/self-signed", { method: "POST", body: { names: splitList(names), ips: splitList(ips), days: Number(days) } });
          await queries.invalidateQueries({ queryKey: ["tls"] });
        }}
      >
        <NameFields names={names} ips={ips} setNames={setNames} setIps={setIps} />
        <label className="oslo-field">
          {t("tls.days")}
          <input type="number" min={1} max={3650} value={days} onChange={(e) => setDays(e.target.value)} />
        </label>
      </ActionForm>
    </Section>
  );
}

function RequestSection({ csr }: { csr: string | null }) {
  const { t } = useApp();
  const queries = useQueryClient();
  const start = defaults();
  const [names, setNames] = useState(start.names);
  const [ips, setIps] = useState(start.ips);
  const [signed, setSigned] = useState("");
  const reload = () => queries.invalidateQueries({ queryKey: ["tls"] });
  if (!csr) {
    return (
      <Section title={t("tls.request")} hint={t("tls.request_hint")}>
        <ActionForm
          submit={t("tls.create_request")}
          onSubmit={async () => {
            await api("/tls/request", { method: "POST", body: { names: splitList(names), ips: splitList(ips) } });
            await reload();
          }}
        >
          <NameFields names={names} ips={ips} setNames={setNames} setIps={setIps} />
        </ActionForm>
      </Section>
    );
  }
  return (
    <Section title={t("tls.request")} hint={t("tls.request_open")}>
      <textarea className="oslo-pem" readOnly rows={6} value={csr} aria-label="CSR" />
      <div className="oslo-form-buttons">
        <button type="button" className="oslo-secondary" onClick={() => saveText(csr, "oslo.csr")}>
          {t("tls.download_csr")}
        </button>
      </div>
      <ActionForm
        submit={t("tls.upload_signed")}
        onSubmit={async () => {
          await api("/tls/certificate", { method: "POST", body: { pem: signed } });
          setSigned("");
          await reload();
        }}
      >
        <label className="oslo-field">
          {t("tls.signed")}
          <textarea className="oslo-pem" rows={6} value={signed} placeholder="-----BEGIN CERTIFICATE-----" onChange={(e) => setSigned(e.target.value)} />
        </label>
        <label className="oslo-field">
          {t("tls.signed_file")}
          <input type="file" accept=".pem,.crt,.cer" onChange={(e) => void e.target.files?.[0]?.text().then(setSigned)} />
        </label>
      </ActionForm>
      <ActionForm
        submit={t("tls.cancel_request")}
        danger
        onSubmit={async () => {
          await api("/tls/request", { method: "DELETE" });
          await reload();
        }}
      />
    </Section>
  );
}
