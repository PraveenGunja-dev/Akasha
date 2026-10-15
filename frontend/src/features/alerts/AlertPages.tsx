/* My alerts - the alerts the signed-in person was emailed (To) and must
   acknowledge. A section of every role workspace (sidebar: Dashboard > My
   alerts), and pages for the email links: /alerts and /alerts/:id, where
   the email's "Acknowledge in Akasha" button lands. Sign-in (RequireAuth,
   then back here) is what identifies who acknowledges. */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Archive, ArrowLeft, CheckCircle2, Inbox, ShieldCheck } from 'lucide-react';
import { KPITile, Loader, PageHeader, StatusPill } from '../../components/ui/primitives';
import { useAuth } from '../../context/AuthContext';
import { btn, fmtWhen } from '../admin/adminApi';
import { AlertDialog } from '../admin/email/AlertsView';
import AlertDetail, { LevelBadge, alertState } from './AlertDetail';
import { alertsApi, fmtDay } from './alertsApi';
import type { Alert, AlertDetailData } from './alertsApi';

function Shell({ children, back, wide }: { children: React.ReactNode; back?: { to: string; label: string }; wide?: boolean }) {
  const { user, homeFor } = useAuth();
  const home = back ?? { to: user ? homeFor(user, null) : '/workspaces', label: 'Back to Akasha' };
  return (
    <main className="min-h-screen bg-background">
      <div className={`mx-auto w-full ${wide ? 'max-w-6xl' : 'max-w-4xl'} px-4 py-6 sm:py-8`}>
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

type View = 'waiting' | 'acknowledged' | 'closed';

export function MyAlertsView() {
  const [rows, setRows] = useState<Alert[] | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [view, setView] = useState<View | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const load = useCallback(() => {
    alertsApi.mine('all').then(r => { setRows(r.alerts); setEmail(r.email); }).catch(e => setError((e as Error).message));
  }, []);
  useEffect(load, [load]);

  const groups = useMemo(() => {
    const all = rows ?? [];
    return {
      waiting: all.filter(a => a.status === 'open' && !a.my_ack),
      acknowledged: all.filter(a => a.status === 'open' && !!a.my_ack),
      closed: all.filter(a => a.status !== 'open'),
    };
  }, [rows]);
  useEffect(() => {
    if (view === null && rows) setView(groups.waiting.length || !groups.acknowledged.length ? 'waiting' : 'acknowledged');
  }, [view, rows, groups]);
  const current = view ? groups[view] : [];

  return (
    <div className="space-y-4">
      <PageHeader title="My alerts"
        subtitle={email ? `Alerts emailed to ${email} as a To recipient. Acknowledge with an expected date to hold an alert at its level; without one, the next reminder goes to the next level.`
          : 'Alerts are matched to you by email address.'} />
      {error && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-[12px] text-[var(--status-critical-fg)]">{error}</p>}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <KPITile icon={Inbox} label="Waiting for me" value={String(groups.waiting.length)} loading={!rows}
          tone={groups.waiting.length ? 'watch' : 'neutral'} selected={view === 'waiting'} onClick={() => setView('waiting')}
          subtext="Open, not yet acknowledged by you" />
        <KPITile icon={ShieldCheck} label="Acknowledged · open" value={String(groups.acknowledged.length)} loading={!rows}
          selected={view === 'acknowledged'} onClick={() => setView('acknowledged')}
          subtext="You acknowledged; the work is not done yet" />
        <KPITile icon={Archive} label="Closed" value={String(groups.closed.length)} loading={!rows}
          selected={view === 'closed'} onClick={() => setView('closed')} subtext="PO in SAP, condition cleared or decided" />
      </div>

      <div className="bento-card overflow-x-auto p-0">
        {!rows || !view ? <div className="flex justify-center py-12"><Loader size="md" label="Loading your alerts…" /></div>
          : !email ? (
            <Empty title="Your account has no email address" text="Alerts are matched by email - ask an administrator to add it in Users & roles." />
          ) : current.length === 0 ? (
            <Empty title={view === 'waiting' ? 'Nothing waiting for you' : view === 'acknowledged' ? 'No open alerts you have acknowledged' : 'No closed alerts yet'}
              text="An alert appears here when Akasha emails you as a To recipient - from the daily run or Send now, not from a template's Send test." />
          ) : (
            <table className="w-full min-w-[860px] text-[12px]">
              <thead className="border-b border-border bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold">
                  <th>Level</th><th>Project</th><th>Alert</th><th>Ordering date</th><th>Last email</th><th>Status · next</th><th />
                </tr>
              </thead>
              <tbody>
                {current.map(a => {
                  const st = a.status === 'open' && !a.my_ack ? { label: 'Waiting for you', tone: 'watch' as const } : alertState(a);
                  return (
                    <tr key={a.id} className="border-b border-[var(--border-subtle)] align-top last:border-0 hover:bg-[var(--surface-sunken)]">
                      <td className="px-3 py-2.5"><LevelBadge level={a.level} /></td>
                      <td className="px-3 py-2.5">
                        <span className="font-semibold text-foreground">{a.project_name || '—'}</span>
                        {a.phase && <span className="block text-[11px] text-muted-foreground">{a.phase}</span>}
                      </td>
                      <td className="px-3 py-2.5 text-foreground">{a.template_name}<span className="block text-[11px] text-muted-foreground">{a.emails} email{a.emails === 1 ? '' : 's'}</span></td>
                      <td className="whitespace-nowrap px-3 py-2.5 tabular-nums text-muted-foreground">{a.due_date || '—'}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 text-muted-foreground">{fmtWhen(a.last_sent_at)}</td>
                      <td className="max-w-[300px] px-3 py-2.5">
                        <StatusPill tone={st.tone}>{st.label}</StatusPill>
                        <span className="mt-0.5 block text-[11px] text-muted-foreground">
                          {a.status === 'open' ? (a.expected_date ? `Expected by ${fmtDay(a.expected_date)} · ` : '') + (a.next_step ?? '') : a.resolved_reason}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <button type="button" className={a.status === 'open' && !a.my_ack ? btn.primary : btn.secondary} onClick={() => setOpen(a.id)}>
                          {a.status === 'open' && !a.my_ack ? 'Acknowledge' : a.status === 'open' ? 'Update' : 'View'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
      </div>
      <AlertDialog id={open} onClose={() => setOpen(null)} onChanged={load} />
    </div>
  );
}

function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5 px-4 py-12 text-center">
      <CheckCircle2 className="h-6 w-6 text-muted-foreground" aria-hidden />
      <p className="text-[13px] font-medium text-foreground">{title}</p>
      <p className="max-w-md text-[12px] text-muted-foreground">{text}</p>
    </div>
  );
}

/* /alerts - the same view on its own page, for the links in emails. */
export function MyAlertsPage() {
  return <Shell wide><MyAlertsView /></Shell>;
}

