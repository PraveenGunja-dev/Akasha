import type { Tone } from '../../components/ui/primitives';
import type { AuditEntry, Severity } from './adminApi';

/* How each audit action (backend: services/security.py SEVERITY, the auth
   guard and the admin router) reads on screen. */

export const EVENT_LABEL: Record<string, [string, Tone]> = {
  'login.success': ['Signed in', 'healthy'],
  'login.failed': ['Failed sign-in', 'watch'],
  'login.locked': ['Locked after failures', 'critical'],
  'login.blocked_locked': ['Sign-in while locked', 'critical'],
  'login.burst': ['Many failed sign-ins', 'critical'],
  logout: ['Signed out', 'neutral'],
  'password.changed': ['Changed own password', 'neutral'],
  'password.change_failed': ['Wrong current password', 'watch'],
  'user.created': ['Created user', 'done'],
  'user.updated': ['Updated user', 'done'],
  'user.privileged_change': ['Admin rights changed', 'risk'],
  'user.password_reset': ['Reset password', 'risk'],
  'user.unlocked': ['Unlocked user', 'done'],
  'user.sessions_ended': ['Ended sessions', 'risk'],
  'user.bootstrap': ['Superadmin created', 'ai'],
  'user.superadmin_reset': ['Superadmin reset (CLI)', 'ai'],
  'user.password_expired': ['Password expired', 'watch'],
  'session.ended': ['Ended a session', 'risk'],
  'role.created': ['Created role', 'done'],
  'role.updated': ['Changed role', 'done'],
  'role.admin_grant': ['Admin permissions changed', 'risk'],
  'role.deleted': ['Deleted role', 'risk'],
  'api_key.created': ['Issued API key', 'done'],
  'api_key.revoked': ['Revoked API key', 'risk'],
  'api_key.invalid': ['Bad API key used', 'watch'],
  'data.change': ['Data edited', 'ai'],
  'data.sync': ['Data sync run', 'ai'],
  'notification.action': ['Acted on a notification', 'neutral'],
  'access.denied': ['Access refused', 'watch'],
  'access.denied_repeated': ['Repeated refusals', 'critical'],
  'audit.exported': ['Exported activity log', 'neutral'],
  'audit.users_exported': ['Exported user list', 'neutral'],
  'audit.alerts_acknowledged': ['Acknowledged alerts', 'neutral'],
};

export const eventLabel = (action: string): [string, Tone] => EVENT_LABEL[action] ?? [action, 'neutral'];

export const SEVERITY_TONE: Record<Severity, Tone> = { info: 'neutral', warning: 'watch', critical: 'critical' };

/** The detail object as one readable line. */
export function describe(e: Pick<AuditEntry, 'action' | 'detail'>): string {
  const d = e.detail;
  if (!d) return '';
  if (e.action.startsWith('data.') || e.action === 'notification.action') {
    const ok = d.ok === false ? `failed (${d.status})` : 'completed';
    return `${d.method ?? ''} ${ok}${d.query ? ` · ${d.query}` : ''}`.trim();
  }
  return Object.entries(d).map(([k, v]) => {
    if (Array.isArray(v) && v.length === 2 && !['added', 'removed', 'permissions'].includes(k)) return `${k}: ${v[0] ?? '—'} → ${v[1] ?? '—'}`;
    if (Array.isArray(v)) return v.length ? `${k}: ${v.join(', ')}` : '';
    if (v && typeof v === 'object') return `${k}: ${Object.entries(v).map(([a, b]) => `${a}=${b}`).join(', ')}`;
    return `${k}: ${v}`;
  }).filter(Boolean).join(' · ');
}

/** One sentence for a security alert: what happened, to whom. */
export function alertSentence(e: AuditEntry): string {
  const who = e.actor_name ?? e.actor ?? 'Someone';
  const d = e.detail ?? {};
  switch (e.action) {
    case 'login.locked': return `${e.target} was locked after 5 wrong passwords in a row.`;
    case 'login.blocked_locked': return `Someone tried to sign in as ${e.target} while the account was locked.`;
    case 'login.burst': return `${d.failed_attempts} failed sign-ins from ${e.target} in ${d.minutes} minutes, across ${d.usernames_tried} username(s).`;
    case 'access.denied': return `${who} asked for something outside their access: ${e.target}.`;
    case 'access.denied_repeated': return `${who} was refused ${d.refused_calls} times in ${d.minutes} minutes.`;
    case 'api_key.invalid': return `A system called ${String((d as { call?: string }).call ?? 'the API')} with a wrong, expired or revoked key (${e.target}…).`;
    case 'password.change_failed': return `${who} entered a wrong current password while changing it.`;
    case 'user.privileged_change': {
      const r = (d as { role?: [string | null, string | null] }).role;
      return `${who} changed ${e.target}'s role ${r?.[0] ? `from ${r[0]} ` : ''}to ${r?.[1] ?? '—'} (administration rights).`;
    }
    case 'role.admin_grant': return `${who} changed administration permissions on the ${e.target} role.`;
    default: return `${eventLabel(e.action)[0]}${e.target ? `: ${e.target}` : ''}.`;
  }
}

const SCREENS: [RegExp, string][] = [
  [/^\/workspaces/, 'Dashboard picker'],
  [/^\/ceo-dashboard\/project/, 'Executive · project 360'],
  [/^\/ceo-dashboard\/knowledge-graph/, 'Executive · knowledge graph'],
  [/^\/ceo-dashboard/, 'Executive dashboard'],
  [/^\/wind-dashboard/, 'Wind dashboard'],
  [/^\/pmag/, 'PMAG dashboard'],
  [/^\/projects/, 'Projects dashboard'],
  [/^\/tc-ordering/, 'TC Ordering dashboard'],
  [/^\/tc-stores/, 'TC Stores dashboard'],
  [/^\/admin\/?([\w-]*)/, 'Admin console'],
  [/^\/account\/password/, 'Change password'],
];

/** App path -> the screen's name. */
export function screenName(path: string | null): string {
  if (!path) return '—';
  for (const [re, name] of SCREENS) {
    const m = re.exec(path);
    if (m) return m[1] ? `${name} · ${m[1].replace(/-/g, ' ')}` : name;
  }
  return path;
}

/** '3 min ago' from a UTC ISO string (with or without Z). */
export function ago(iso: string | null, now = Date.now()): string {
  if (!iso) return '—';
  const t = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z').getTime();
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}
