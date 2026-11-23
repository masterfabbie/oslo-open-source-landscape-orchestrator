// Shapes of the REST API used by the configuration pages (see api/schemas.py).

export interface InstanceInfo {
  id: number;
  host_id: number;
  sid_id: number;
  sid: string;
  system_id: number | null;
  number: string;
  label: string;
  role: string;
  hostname: string;
  sap_version_info: string | null;
  features: string | null;
  type_key?: string | null;
  start_priority: string | null;
  last_status: string;
  suggested_system_id?: number | null;
}

export interface HostInfo {
  id: number;
  name: string;
  address: string;
  hostagent_port: number | null;
  https: boolean;
  verify_tls: boolean;
  verify_hostname: boolean;
  sapcontrol_port_offset: number;
  username: string | null;
  has_credentials: boolean;
  os_name: string | null;
  os_version: string | null;
  cpu_count: number | null;
  memory_kb: number | null;
  reachable: boolean | null;
  last_error: string | null;
  last_discovery_at: string | null;
  hostagent_version: string | null;
  // The OSLO operations on the host (lib/bundle.ts).
  bundle_version: string | null;
  bundle_integrity: string | null;
  bundle_checked_at: string | null;
  tags: string[];
}

export interface DatabaseInfo {
  id: number;
  name: string;
  type: string;
  instance_name: string | null;
  vendor: string | null;
  release: string | null;
  last_status: string;
}

export interface HostDetail extends HostInfo {
  instances: InstanceInfo[];
  databases: DatabaseInfo[];
}

export interface SystemInfo {
  id: number;
  name: string;
  description: string | null;
  tags: string[];
  pool_id: number | null;
  stage: string | null;
  depends_on_ids: number[];
  required_by_ids: number[];
  instances: InstanceInfo[];
}

export interface PoolInfo {
  id: number;
  name: string;
  description: string | null;
  system_ids: number[];
}

export interface SidInfo {
  id: number;
  name: string;
  username: string | null;
  has_credentials: boolean;
}

export const STAGES = ["sandbox", "development", "quality", "preprod", "production"];

/** A certificate as the server reads it (Administration → Certificates, a host's certificate). */
export interface CertificateInfo {
  subject: string;
  issuer: string;
  fingerprint: string;
  not_before: string;
  not_after: string;
  self_signed: boolean;
  expired: boolean;
}

export interface HostCertificate extends CertificateInfo {
  pem: string;
  trusted_id: number | null;
}

export interface TrustedCertificate extends CertificateInfo {
  id: number;
  name: string;
  pem: string;
  created_at: string;
  created_by: string | null;
}
