/* Client for /api/alerts (backend/routers/alerts.py) - the alerts a person
   was emailed and must acknowledge - and the shared alert types the admin
   console's Alerts view uses too. */

export type AlertKind = 'order' | 'condition' | 'one_off' | 'approval';
export type Level = 1 | 2 | 3;

export interface AlertRecipient { email: string; name: string; level: Level; acknowledged_at: string | null }

export interface AlertEvent {
  at: string | null; kind: 'opened' | 'sent' | 'escalated' | 'held' | 'acknowledged' | 'updated' | 'resolved';
  level: Level | null; actor: string | null; detail: string | null; log_id: number | null;
}

export interface AlertEmail { id: number; at: string | null; subject: string | null; level: Level | null; status: string; to: string[]; cc: string[] }

export interface Alert {
  id: number; kind: AlertKind; status: 'open' | 'resolved'; test: boolean;
  template_key: string; template_name: string; severity: 'info' | 'action' | 'critical' | null;
  project_id: string | null; project_name: string | null; phase: string | null; due_date: string | null;
  level: Level; emails: number; opened_at: string | null; last_sent_at: string | null;
  acknowledged_at: string | null; acknowledged_by: string | null; ack_level: Level | null;
  update_note: string | null; expected_date: string | null; updated_at: string | null;
  holds: boolean; late_commitment: boolean;
  resolved_at: string | null; resolved_reason: string | null; next_step: string | null;
  recipients: AlertRecipient[];
  my_ack?: string | null;
  /** kind 'approval': the module order approval it asks a decision on. */
  approval_id?: number | null;
}

export interface AlertDetailData extends Alert {
  timeline: AlertEvent[]; emails_sent: AlertEmail[]; project_link: string | null;
  can_acknowledge: boolean; is_admin: boolean; you: { email: string | null; name: string };
}

export interface AckInput { note?: string; expected_date?: string; on_behalf_of?: string }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/akasha/api/alerts${path}`, {
    credentials: 'same-origin', ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body as T;
}

export const alertsApi = {
  mine: (status: 'open' | 'all') => call<{ email: string | null; alerts: Alert[] }>(`/mine?status=${status}`),
  get: (id: number) => call<AlertDetailData>(`/${id}`),
  acknowledge: (id: number, body: AckInput) =>
    call<AlertDetailData>(`/${id}/acknowledge`, { method: 'POST', body: JSON.stringify(body) }),
};

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** '2027-01-26' -> '26-Jan-27', the Ordering Schedule's date format. */
export function fmtDay(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  return m ? `${m[3]}-${MON[Number(m[2]) - 1]}-${m[1].slice(2)}` : '';
}

/** '28-Jan-27' -> '2027-01-28' (for date inputs), or ''. */
export function isoFromDay(day: string | null | undefined): string {
  const m = /(\d{1,2})-([A-Za-z]{3})-(\d{2,4})/.exec(day ?? '');
  if (!m) return '';
  const mi = MON.findIndex(x => x.toLowerCase() === m[2].toLowerCase());
  if (mi < 0) return '';
  const y = m[3].length === 2 ? `20${m[3]}` : m[3];
  return `${y}-${String(mi + 1).padStart(2, '0')}-${m[1].padStart(2, '0')}`;
}

/** Today in India, as 'YYYY-MM-DD' - what the server checks dates against. */
export function todayIst(): string {
  return new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);
}
