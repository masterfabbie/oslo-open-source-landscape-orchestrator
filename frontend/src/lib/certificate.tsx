// The facts of a certificate (subject, issuer, validity, fingerprint), shared by
// Administration → Certificates and the page of a host.

import { formatTime, useApp } from "../landscape/ui";
import type { CertificateInfo } from "../configuration/types";

export function CertificateFacts({ cert }: { cert: CertificateInfo }) {
  const { t, language } = useApp();
  return (
    <dl className="oslo-facts">
      <dt>{t("field.subject")}</dt>
      <dd className="oslo-wrap">
        <span className="oslo-mono">{cert.subject}</span>
        {cert.self_signed && <span className="oslo-badge oslo-badge-gray oslo-cert-tag">{t("cert.self_signed")}</span>}
      </dd>
      <dt>{t("field.issuer")}</dt>
      <dd className="oslo-mono oslo-wrap">{cert.issuer}</dd>
      <dt>{t("field.valid_from")}</dt>
      <dd>{formatTime(cert.not_before, language)}</dd>
      <dt>{t("field.valid_until")}</dt>
      <dd>
        {formatTime(cert.not_after, language)} {cert.expired && <span className="oslo-badge oslo-badge-red">{t("cert.expired")}</span>}
      </dd>
      <dt>{t("field.fingerprint")}</dt>
      <dd className="oslo-mono oslo-wrap oslo-fingerprint">{cert.fingerprint}</dd>
    </dl>
  );
}
