/* Client for /api/admin/email (backend/routers/email_admin.py). */
import type { Tone } from '../../../components/ui/primitives';

const BASE = '/akasha/api/admin/email';

export type Severity = 'info' | 'action' | 'critical';
export type LogStatus = 'sent' | 'test' | 'failed' | 'no_recipients' | 'baseline' | 'would_send';

export interface EmailSettings {
  server: string; port: number; username: string; password_set: boolean; starttls: string;
  from_addr: string; from_name: string; enabled: boolean; test_mode: boolean;
  test_recipients: string[]; allowed_domains: string[]; public_url: string; support_contact: string;
  configured: boolean; problems: string[];
}

export interface EmailStatus {
  settings: EmailSettings;
  templates: number;
  enabled_templates: number;
  recipients: number;
  last_7_days: Partial<Record<LogStatus, number>>;
  schedule: { enabled: boolean; next_run_at: string | null; last_run_at: string | null } | null;
}

export interface Variable { key: string; label: string; meaning: string; sample: string }
export interface Option { key: string; label: string }
export interface Catalogue { variables: Variable[]; groups: Option[]; triggers: Option[]; portfolios: string[] }

export interface EmailTemplate {
  key: string; name: string; category: string; trigger: string; trigger_label: string;
  description: string | null; severity: Severity; subject: string; body: string;
  to_groups: string[]; cc_groups: string[]; config: Record<string, unknown>;
  attach_snapshot: boolean; enabled: boolean; version: number;
  updated_by: string | null; updated_at: string | null; last_sent_at: string | null; problems: string[];
}

export interface TemplateVersion {
  version: number; name: string; subject: string; body: string; to_groups: string[]; cc_groups: string[];
  config: Record<string, unknown>; attach_snapshot: boolean; enabled: boolean; note: string | null;
  changed_by: string | null; changed_at: string | null;
}

export interface Preview {
  subject: string; html: string; problems: string[]; empty: string[];
  project_id: string | null; project_name: string | null; to: string[]; cc: string[];
}

export interface Recipient {
  id: number; group_key: string; group: string; name: string; email: string;
  portfolios: string[]; active: boolean; created_at: string | null; created_by: string | null;
}

export interface LogEntry {
  id: number; at: string | null; template_key: string; template_version: number | null; severity: Severity | null;
  project_id: string | null; project_name: string | null; phase: string | null; to: string[]; cc: string[];
  subject: string | null; status: LogStatus; detail: string | null; attempts: number; attachments: string[];
  triggered_by: string | null;
}

export interface LogFilters { since?: string; until?: string; status?: string; template?: string; q?: string }

export interface RunItem {
  template: string; event_key?: string; project_id?: string | null; project_name?: string | null; phase?: string;
  to?: string[]; cc?: string[]; subject?: string; status: LogStatus | 'error'; detail?: string | null;
}
export interface RunResult { message: string; items: RunItem[]; counts?: Record<string, number>; dry_run?: boolean }

export interface ProjectOption { project_id: string; name: string; portfolio: string }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'same-origin', ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body as T;
}
const send = <T,>(method: string, path: string, data?: unknown) =>
  call<T>(path, { method, body: data === undefined ? undefined : JSON.stringify(data) });

function query(params: object): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '' && v !== null) qs.set(k, String(v)); });
  return qs.toString();
}

async function download(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { credentials: 'same-origin' });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Export failed (${res.status})`);
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'akasha-email.csv';
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const emailApi = {
  status: () => call<EmailStatus>('/status'),
  catalogue: () => call<Catalogue>('/catalogue'),
  projects: () => call<ProjectOption[]>('/projects'),
  templates: () => call<EmailTemplate[]>('/templates'),
  saveTemplate: (key: string, t: Partial<EmailTemplate> & { note?: string }) => send<EmailTemplate>('PUT', `/templates/${key}`, t),
  versions: (key: string) => call<TemplateVersion[]>(`/templates/${key}/versions`),
  restore: (key: string, version: number) => send<EmailTemplate>('POST', `/templates/${key}/restore/${version}`),
  reset: (key: string) => send<EmailTemplate>('POST', `/templates/${key}/reset`),
  preview: (key: string, draft: { project_id?: string; subject?: string; body?: string; severity?: string }) =>
    send<Preview>('POST', `/templates/${key}/preview`, draft),
  test: (key: string, to: string, project_id?: string) => send<RunItem>('POST', `/templates/${key}/test`, { to, project_id }),
  sendFor: (key: string, project_id: string) => send<RunItem>('POST', `/templates/${key}/send`, { project_id }),
  exportTemplates: () => download('/templates/export'),
  recipients: () => call<Recipient[]>('/recipients'),
  addRecipient: (r: Partial<Recipient>) => send<{ id: number }>('POST', '/recipients', r),
  updateRecipient: (id: number, r: Partial<Recipient>) => send<{ id: number }>('PUT', `/recipients/${id}`, r),
  removeRecipient: (id: number) => send<{ ok: boolean }>('DELETE', `/recipients/${id}`),
  log: (f: LogFilters & { limit?: number; offset?: number }) =>
    call<{ total: number; by_status: Partial<Record<LogStatus, number>>; entries: LogEntry[] }>(`/log?${query(f)}`),
  logEntry: (id: number) => call<LogEntry & { html: string; event_key: string }>(`/log/${id}`),
  resend: (id: number) => send<RunItem>('POST', `/log/${id}/resend`),
  exportLog: (f: LogFilters) => download(`/log-export?${query(f)}`),
  run: (dry_run: boolean) => send<RunResult>('POST', '/run', { dry_run }),
  baseline: () => send<RunResult>('POST', '/baseline'),
};

export const STATUS_META: Record<string, { label: string; tone: Tone }> = {
  sent: { label: 'Sent', tone: 'healthy' },
  test: { label: 'Test', tone: 'ai' },
  failed: { label: 'Failed', tone: 'critical' },
  no_recipients: { label: 'No recipients', tone: 'watch' },
  baseline: { label: 'Go-live baseline', tone: 'neutral' },
  would_send: { label: 'Would send', tone: 'done' },
  error: { label: 'Error', tone: 'critical' },
};

export const SEVERITY_META: Record<Severity, { label: string; tone: Tone }> = {
  info: { label: 'Information', tone: 'done' },
  action: { label: 'Action needed', tone: 'watch' },
  critical: { label: 'Critical', tone: 'critical' },
};
