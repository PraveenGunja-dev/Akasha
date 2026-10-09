/* Client for /api/admin (backend/routers/admin.py). The session cookie goes
   with every same-origin call; a failed call throws the server's message. */

const BASE = '/akasha/api/admin';

export interface AdminUser {
  id: number;
  username: string;
  display_name: string;
  email: string;
  /** Free text, e.g. "PMAG" or "TC Stores"; "" when not set. */
  department: string;
  role: string;
  role_name: string;
  is_active: boolean;
  locked: boolean;
  locked_until: string | null;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string | null;
  active_sessions: number;
  /** Clusters the user may see; [] = every portfolio. */
  portfolios: string[];
}

export interface AdminRole {
  key: string;
  name: string;
  description: string;
  permissions: string[];
  is_system: boolean;
  /** Super Admin: always every permission, not editable. */
  locked: boolean;
  user_count: number;
}

export interface PermissionDef {
  key: string;
  label: string;
  group: string;
  description: string;
}

export type Severity = 'info' | 'warning' | 'critical';

export interface AuditEntry {
  id: number;
  at: string | null;
  actor: string | null;
  actor_name: string | null;
  /** Of whoever did it, else of the account it was done to. */
  department: string | null;
  action: string;
  target: string | null;
  detail: Record<string, unknown> | null;
  ip: string | null;
  severity: Severity;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
}

export type AuditCategory = 'signin' | 'changes' | 'admin' | 'access';

export interface AuditFilters {
  action?: string;
  q?: string;
  category?: AuditCategory | '';
  /** Comma list of severities. */
  severity?: string;
  department?: string;
  user?: string;
  /** UTC ISO */
  since?: string;
  until?: string;
  open_alerts?: boolean;
}

export interface LiveSession {
  ref: string;
  user_id: number;
  username: string;
  name: string;
  department: string | null;
  role_name: string;
  started_at: string | null;
  last_seen_at: string | null;
  /** A call in the last 10 minutes. */
  online: boolean;
  /** App path the person last had open. */
  view: string | null;
  ip: string | null;
  device: string;
}

export interface UsageCounts { sign_ins: number; changes: number; denied: number }

export interface DepartmentActivity extends UsageCounts {
  department: string;
  users: number;
  online: number;
  /** Signed in at least once in the period. */
  active_users: number;
}

export interface PersonActivity extends UsageCounts {
  user_id: number;
  username: string;
  name: string;
  department: string | null;
  role_name: string;
  online: boolean;
  last_login_at: string | null;
}

export interface ActivityReport {
  days: number;
  summary: {
    online_now: number; signed_in: number; sign_ins_today: number; people_today: number;
    failed_today: number; changes_today: number; denied_today: number;
    alerts_open: number; critical_open: number;
  };
  sessions: LiveSession[];
  departments: DepartmentActivity[];
  people: PersonActivity[];
}

export interface AlertSummary { open: number; critical: number; latest: AuditEntry | null }

function query(params: object): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '' && v !== false && v !== null) qs.set(k, String(v)); });
  return qs.toString();
}

/** Download a CSV the server builds (same filters as the screen). Goes through
    fetch so an expired session or refusal shows as an error, not a JSON page. */
async function download(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { credentials: 'same-origin' });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Export failed (${res.status})`);
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'akasha-export.csv';
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'same-origin',
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body as T;
}

const send = <T,>(method: string, path: string, data?: unknown) =>
  call<T>(path, { method, body: data === undefined ? undefined : JSON.stringify(data) });

export const adminApi = {
  users: () => call<{ users: AdminUser[] }>('/users').then(r => r.users),
  portfolios: () => call<{ portfolios: string[] }>('/portfolios').then(r => r.portfolios),
  createUser: (u: { username: string; display_name: string; email?: string; role: string; portfolios?: string[]; department?: string }) =>
    send<{ user: AdminUser; temporary_password: string | null }>('POST', '/users', u),
  updateUser: (id: number, patch: Partial<Pick<AdminUser, 'display_name' | 'email' | 'role' | 'is_active' | 'portfolios' | 'department'>>) =>
    send<{ user: AdminUser | null; changed: boolean }>('PATCH', `/users/${id}`, patch),
  resetPassword: (id: number) => send<{ temporary_password: string }>('POST', `/users/${id}/reset-password`),
  unlock: (id: number) => send<{ success: boolean }>('POST', `/users/${id}/unlock`),
  endSessions: (id: number) => send<{ sessions_ended: number }>('POST', `/users/${id}/end-sessions`),

  roles: () => call<{ roles: AdminRole[] }>('/roles').then(r => r.roles),
  permissions: () => call<{ permissions: PermissionDef[] }>('/permissions').then(r => r.permissions),
  createRole: (r: { key: string; name: string; description: string; permissions: string[] }) =>
    send<{ role: AdminRole }>('POST', '/roles', r),
  updateRole: (key: string, patch: { name?: string; description?: string; permissions?: string[] }) =>
    send<{ role: AdminRole | null; changed: boolean }>('PATCH', `/roles/${key}`, patch),
  deleteRole: (key: string) => send<{ success: boolean }>('DELETE', `/roles/${key}`),

  audit: (params: AuditFilters & { limit?: number; offset?: number }) =>
    call<{ total: number; entries: AuditEntry[] }>(`/audit?${query(params)}`),
  exportAudit: (params: AuditFilters) => download(`/audit/export?${query(params)}`),
  exportUsers: () => download('/users/export'),
  departments: () => call<{ departments: string[] }>('/departments').then(r => r.departments),

  activity: (days: number) => call<ActivityReport>(`/activity?days=${days}`),
  endSession: (ref: string) => send<{ success: boolean }>('POST', `/sessions/${ref}/end`),
  alertSummary: () => call<AlertSummary>('/alerts/summary'),
  acknowledge: (ids?: number[]) => send<{ acknowledged: number }>('POST', '/alerts/acknowledge', ids ? { ids } : {}),
};

/** ISO (UTC, possibly without Z) -> '08 Oct 2026, 14:05' in the viewer's zone. */
export function fmtWhen(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export const btn = {
  primary: 'inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-[12px] font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
  secondary: 'inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[12px] font-semibold text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
  danger: 'inline-flex items-center justify-center gap-1.5 rounded-lg bg-[var(--status-critical-solid)] px-3 py-1.5 text-[12px] font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--status-critical-solid)] focus-visible:ring-offset-2',
  ghost: 'inline-flex items-center justify-center gap-1 rounded-md px-2 py-1 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
};

export const field = 'w-full rounded-lg border border-border bg-background px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:bg-muted disabled:text-muted-foreground';

export interface ApiKeyRow {
  id: number;
  name: string;
  prefix: string;
  portfolios: string[];
  state: 'active' | 'expired' | 'revoked';
  created_at: string | null;
  expires_at: string | null;
  last_used_at: string | null;
  use_count: number;
}

export const apiKeysApi = {
  list: () => call<{ keys: ApiKeyRow[] }>('/api-keys').then(r => r.keys),
  create: (b: { name: string; portfolios?: string[]; expires_in_days?: number | null }) =>
    send<{ key: string; api_key: ApiKeyRow }>('POST', '/api-keys', b),
  revoke: (id: number) => send<{ api_key: ApiKeyRow }>('POST', `/api-keys/${id}/revoke`),
};
