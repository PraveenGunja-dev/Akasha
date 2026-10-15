/* /alerts - the alerts the signed-in person was emailed (To) - and
   /alerts/:id, where the email's "Acknowledge in Akasha" button lands.
   Sign-in (RequireAuth, then back here) is what identifies who
   acknowledges. */
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, BellRing, ChevronRight, Inbox } from 'lucide-react';
import { Loader, StatusPill, cx } from '../../components/ui/primitives';
import { useAuth } from '../../context/AuthContext';
import { fmtWhen } from '../admin/adminApi';
import AlertDetail, { LevelBadge, alertState } from './AlertDetail';
import { alertsApi } from './alertsApi';
import type { Alert, AlertDetailData } from './alertsApi';

function Shell({ children, back }: { children: React.ReactNode; back?: { to: string; label: string } }) {
  const { user, homeFor } = useAuth();
  const home = back ?? { to: user ? homeFor(user, null) : '/workspaces', label: 'Back to Akasha' };
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto w-full max-w-4xl px-4 py-6 sm:py-8">
        <Link to={home.to} className="mb-3 inline-flex items-center gap-1 rounded text-[12px] font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
          <ArrowLeft className="h-3.5 w-3.5" />{home.label}
        </Link>
        {children}
      </div>
    </main>
  );
}

export function AlertPage() {
  const id = Number(useParams().id);
  const [data, setData] = useState<AlertDetailData | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!Number.isFinite(id)) { setError('No such alert'); return; }
    alertsApi.get(id).then(setData).catch(e => setError((e as Error).message));
  }, [id]);
  return (
    <Shell back={{ to: '/alerts', label: 'My alerts' }}>
      <div className="bento-card p-4 sm:p-5">
        {error ? <p role="alert" className="text-[13px] text-[var(--status-critical-fg)]">{error}</p>
          : !data ? <div className="flex justify-center py-10"><Loader size="md" label="Loading the alert…" /></div>
            : <AlertDetail data={data} onChange={setData} />}
      </div>
    </Shell>
  );
}

export function MyAlertsPage() {
  const [scope, setScope] = useState<'open' | 'all'>('open');
  const [rows, setRows] = useState<Alert[] | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setRows(null);
    alertsApi.mine(scope).then(r => { setRows(r.alerts); setEmail(r.email); }).catch(e => setError((e as Error).message));
  }, [scope]);
  useEffect(load, [load]);
  const awaiting = (rows ?? []).filter(a => a.status === 'open' && !a.my_ack).length;

  return (
    <Shell>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="flex items-center gap-2 text-[17px] font-semibold text-foreground"><BellRing className="h-4 w-4 text-primary" aria-hidden />My alerts</h1>
          <p className="text-[12.5px] text-muted-foreground">
            Alerts emailed to {email ?? 'you'} that need acknowledging{rows && scope === 'open' && awaiting > 0 ? ` - ${awaiting} waiting for you` : ''}.
          </p>
        </div>
        <div role="tablist" aria-label="Which alerts" className="inline-flex rounded-lg border border-border p-0.5">
          {(['open', 'all'] as const).map(s => (
            <button key={s} type="button" role="tab" aria-selected={scope === s} onClick={() => setScope(s)}
              className={cx('rounded-md px-3 py-1 text-[12px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
                scope === s ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground')}>{s === 'open' ? 'Open' : 'All'}</button>
          ))}
        </div>
      </div>
      {error && <p role="alert" className="mb-3 text-[12.5px] text-[var(--status-critical-fg)]">{error}</p>}
      <div className="bento-card overflow-hidden p-0">
        {!rows ? <div className="flex justify-center py-10"><Loader size="md" label="Loading…" /></div>
          : rows.length === 0 ? (
            <div className="flex flex-col items-center gap-1.5 px-4 py-12 text-center">
              <Inbox className="h-6 w-6 text-muted-foreground" aria-hidden />
              <p className="text-[13px] font-medium text-foreground">{email ? (scope === 'open' ? 'Nothing waiting for you' : 'No alerts yet') : 'Your account has no email address'}</p>
              <p className="text-[12px] text-muted-foreground">{email ? 'Alerts emailed to you appear here.' : 'Ask an administrator to add it - alerts are matched by email.'}</p>
            </div>
          ) : (
            <ul className="divide-y divide-[var(--border-subtle)]">
              {rows.map(a => {
                const st = a.status === 'open' && !a.my_ack ? { label: 'Waiting for you', tone: 'watch' as const } : alertState(a);
                return (
                  <li key={a.id}>
                    <Link to={`/alerts/${a.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-[var(--surface-sunken)] focus-visible:bg-[var(--surface-sunken)] focus-visible:outline-none">
                      <LevelBadge level={a.level} />
                      <div className="min-w-0 flex-1 leading-tight">
                        <div className="truncate text-[13px] font-semibold text-foreground">
                          {a.project_name || a.template_name}{a.phase && <span className="font-normal text-muted-foreground"> · {a.phase}</span>}
                        </div>
                        <div className="truncate text-[11.5px] text-muted-foreground">
                          {a.template_name}{a.due_date && ` · ordering date ${a.due_date}`} · last email {fmtWhen(a.last_sent_at)}
                        </div>
                      </div>
                      <StatusPill tone={st.tone}>{st.label}</StatusPill>
                      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
      </div>
    </Shell>
  );
}
