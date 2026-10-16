import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CheckCheck, Search } from 'lucide-react';
import { PageHeader, StatusPill } from '../../components/ui/primitives';
import type { Tone } from '../../components/ui/primitives';
import { adminApi, btn, field, fmtWhen } from './adminApi';
import type { AuditEntry } from './adminApi';
import { refreshAlerts, useAlertSummary } from './securityAlerts';

/* Append-only record of sign-ins and every change to accounts and roles
   (backend: akasha_audit_log). */

const PAGE = 100;
const FILTERS = [
  { value: '', label: 'All events' },
  { value: 'login', label: 'Sign-ins' },
  { value: 'login.failed', label: 'Failed sign-ins' },
  { value: 'user', label: 'User changes' },
  { value: 'role', label: 'Role changes' },
  { value: 'password', label: 'Password changes' },
];

const LABEL: Record<string, [string, Tone]> = {
  'login.success': ['Signed in', 'healthy'],
  'login.failed': ['Failed sign-in', 'watch'],
  'login.locked': ['Locked after failures', 'critical'],
  'login.blocked_locked': ['Sign-in while locked', 'critical'],
  logout: ['Signed out', 'neutral'],
  'password.changed': ['Changed own password', 'neutral'],
  'password.change_failed': ['Wrong current password', 'watch'],
  'user.created': ['Created user', 'done'],
  'user.updated': ['Updated user', 'done'],
  'user.password_reset': ['Reset password', 'risk'],
  'user.unlocked': ['Unlocked user', 'done'],
  'user.sessions_ended': ['Ended sessions', 'risk'],
  'user.bootstrap': ['Superadmin created', 'ai'],
  'user.superadmin_reset': ['Superadmin reset (CLI)', 'ai'],
  'user.password_expired': ['Password expired', 'watch'],
  'role.created': ['Created role', 'done'],
  'role.updated': ['Changed role', 'done'],
  'role.deleted': ['Deleted role', 'risk'],
  'api_key.created': ['Issued API key', 'done'],
  'api_key.revoked': ['Revoked API key', 'risk'],
  'email.template_saved': ['Edited email template', 'done'],
  'email.template_restored': ['Restored email template', 'done'],
  'email.template_reset': ['Reset email template', 'done'],
  'email.test_sent': ['Sent test email', 'ai'],
  'email.manual_sent': ['Sent email manually', 'done'],
  'email.recipient_added': ['Added email recipient', 'done'],
  'email.recipient_changed': ['Changed email recipient', 'done'],
  'email.recipient_removed': ['Removed email recipient', 'risk'],
  'email.resent': ['Resent email', 'done'],
  'email.log_exported': ['Exported email log', 'neutral'],
  'email.run': ['Ran email alerts', 'done'],
  'email.baseline': ['Email go-live baseline', 'watch'],
};

function describe(detail: AuditEntry['detail']): string {
  if (!detail) return '';
  return Object.entries(detail).map(([k, v]) => {
    if (Array.isArray(v) && v.length === 2 && !['added', 'removed', 'permissions'].includes(k)) return `${k}: ${v[0] ?? '—'} → ${v[1] ?? '—'}`;
    if (Array.isArray(v)) return v.length ? `${k}: ${v.join(', ')}` : '';
    return `${k}: ${v}`;
  }).filter(Boolean).join(' · ');
}

export default function AuditPanel() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState('');
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // Security alerts (the badge and the toast's Review): the open ones only,
  // and marking them reviewed once someone has checked them.
  const [params, setParams] = useSearchParams();
  const onlyAlerts = params.get('alerts') === 'open';
  const alerts = useAlertSummary();
  const [acking, setAcking] = useState(false);
  const setOnlyAlerts = (on: boolean) => setParams(on ? { alerts: 'open' } : {}, { replace: true });

  useEffect(() => { const t = window.setTimeout(() => setDebounced(query.trim()), 300); return () => window.clearTimeout(t); }, [query]);

  const load = useCallback(async (offset = 0) => {
    setLoading(true);
    setError('');
    try {
      const r = await adminApi.audit({ action, q: debounced, limit: PAGE, offset, ...(onlyAlerts ? { open_alerts: true } : {}) });
      setTotal(r.total);
      setEntries(prev => (offset ? [...prev, ...r.entries] : r.entries));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [action, debounced, onlyAlerts]);
  useEffect(() => { load(0); }, [load]);

  const markReviewed = async () => {
    setAcking(true);
    setError('');
    try {
      await adminApi.acknowledge();
      await refreshAlerts();
      await load(0);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAcking(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Audit log" subtitle={`${total.toLocaleString('en-IN')} event${total === 1 ? '' : 's'} · times in your local zone`} />
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Show" className="inline-flex rounded-lg border border-border p-0.5 text-[12px]">
          {[[false, 'All events'], [true, `Open security alerts${alerts ? ` (${alerts.open})` : ''}`]].map(([on, label]) => (
            <button key={String(on)} type="button" aria-pressed={onlyAlerts === on} onClick={() => setOnlyAlerts(on as boolean)}
              className={`rounded-md px-2.5 py-1 font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${onlyAlerts === on ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
              {label as string}
            </button>
          ))}
        </div>
        {onlyAlerts && total > 0 && (
          <button type="button" className={btn.secondary} disabled={acking} onClick={markReviewed}>
            <CheckCheck className="h-3.5 w-3.5" />{acking ? 'Marking…' : `Mark all ${total} reviewed`}
          </button>
        )}
        <select aria-label="Event type" value={action} onChange={e => setAction(e.target.value)} className={`${field.replace("w-full ", "")} w-auto py-1.5`}>
          {FILTERS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
        <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input aria-label="Search by user" value={query} onChange={e => setQuery(e.target.value)} placeholder="Username (who or whom)" className={`${field} py-1.5 pl-8`} />
        </div>
      </div>
      {error && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}

      <div className="bento-card overflow-x-auto p-0">
        <table className="w-full min-w-[820px] text-[12px]">
          <thead className="border-b border-border bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold">
              <th>When</th><th>Event</th><th>By</th><th>On</th><th>Details</th><th>IP</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(e => {
              const [label, tone] = LABEL[e.action] ?? [e.action, 'neutral' as Tone];
              return (
                <tr key={e.id} className="border-b border-[var(--border-subtle)] align-top last:border-0 hover:bg-[var(--surface-sunken)]">
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted-foreground">{fmtWhen(e.at)}</td>
                  <td className="whitespace-nowrap px-3 py-2"><StatusPill tone={tone}>{label}</StatusPill></td>
                  <td className="px-3 py-2">{e.actor ?? <span className="text-muted-foreground">—</span>}</td>
                  <td className="px-3 py-2 font-medium text-foreground">{e.target ?? '—'}</td>
                  <td className="max-w-[360px] px-3 py-2 text-[11px] leading-snug text-muted-foreground">{describe(e.detail)}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] text-muted-foreground">{e.ip ?? ''}</td>
                </tr>
              );
            })}
            {!loading && entries.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">{onlyAlerts ? 'No open security alerts - all reviewed.' : 'No events match.'}</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Showing {entries.length.toLocaleString('en-IN')} of {total.toLocaleString('en-IN')}</span>
        {entries.length < total && <button type="button" className={btn.secondary} disabled={loading} onClick={() => load(entries.length)}>{loading ? 'Loading…' : 'Load more'}</button>}
      </div>
    </div>
  );
}
