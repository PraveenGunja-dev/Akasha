/* Admin console - Email notifications. Four views over one module
   (backend/services/email_notify): Overview (is it on, where does it send,
   what would go out next), Templates (edit, preview, test, history), the
   distribution groups, and the email log. Needs email.manage. */
import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CalendarClock, CheckCircle2, Eye, FlaskConical, Mail, MailX, PlayCircle, Rocket, Send, UserX } from 'lucide-react';
import { Dialog, KPITile, PageHeader, StatusPill, cx } from '../../../components/ui/primitives';
import { btn, fmtWhen } from '../adminApi';
import { emailApi, STATUS_META } from './emailApi';
import type { EmailStatus, RunResult } from './emailApi';
import TemplatesView from './TemplatesView';
import RecipientsView from './RecipientsView';
import LogView from './LogView';
import AlertsView from './AlertsView';
import { LevelBadge } from '../../alerts/AlertDetail';

type View = 'overview' | 'templates' | 'alerts' | 'recipients' | 'log';
const VIEWS: { id: View; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'templates', label: 'Templates' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'recipients', label: 'Distribution groups' },
  { id: 'log', label: 'Email log' },
];

export default function EmailPanel() {
  const [view, setView] = useState<View>('overview');
  return (
    <div className="space-y-4">
      <PageHeader title="Email notifications"
        subtitle="Module ordering alerts, escalations and digests - templates, acknowledgements, recipients and every email sent" />
      <div role="tablist" aria-label="Email notifications" className="flex flex-wrap gap-1 border-b border-border">
        {VIEWS.map(v => (
          <button key={v.id} type="button" role="tab" aria-selected={view === v.id} onClick={() => setView(v.id)}
            className={cx('-mb-px border-b-2 px-3 py-2 text-[13px] font-semibold transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded-t-md',
              view === v.id ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground')}>
            {v.label}
          </button>
        ))}
      </div>
      {view === 'overview' && <Overview onOpenLog={() => setView('log')} />}
      {view === 'templates' && <TemplatesView />}
      {view === 'alerts' && <AlertsView />}
      {view === 'recipients' && <RecipientsView />}
      {view === 'log' && <LogView />}
    </div>
  );
}

function Overview({ onOpenLog }: { onOpenLog: () => void }) {
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<'' | 'dry' | 'run' | 'baseline'>('');
  const [result, setResult] = useState<RunResult | null>(null);
  const [confirm, setConfirm] = useState<'' | 'run' | 'baseline'>('');

  const load = useCallback(() => {
    emailApi.status().then(setStatus).catch(e => setError((e as Error).message));
  }, []);
  useEffect(load, [load]);

  const act = async (kind: 'dry' | 'run' | 'baseline') => {
    setBusy(kind); setError(''); setConfirm('');
    try {
      setResult(kind === 'baseline' ? await emailApi.baseline() : await emailApi.run(kind === 'dry'));
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };

  const s = status?.settings;
  const counts = status?.last_7_days ?? {};
  return (
    <div className="space-y-4">
      {error && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}

      {s && (
        <div className="bento-card grid gap-x-6 gap-y-3 p-4 text-[12.5px] sm:grid-cols-2 lg:grid-cols-4">
          <Fact label="Sending">
            {s.enabled ? <StatusPill tone="healthy">On</StatusPill> : <StatusPill tone="neutral">Off</StatusPill>}
            {!s.enabled && <span className="ml-1.5 text-muted-foreground">EMAIL_ENABLED=false</span>}
          </Fact>
          <Fact label="Mode">
            {s.test_mode
              ? <><StatusPill tone="ai">Test</StatusPill><span className="ml-1.5 text-muted-foreground">only to {s.test_recipients.join(', ') || '(no test recipients)'}</span></>
              : <StatusPill tone="watch">Live - real recipients</StatusPill>}
          </Fact>
          <Fact label="From">{s.from_addr ? `${s.from_name} <${s.from_addr}>` : <span className="text-muted-foreground">EMAIL_FROM not set</span>}</Fact>
          <Fact label="Mail server">{s.server ? `${s.server}:${s.port}` : <span className="text-muted-foreground">SMTP_SERVER not set</span>}{s.username && <span className="block text-[11px] text-muted-foreground">as {s.username}</span>}</Fact>
          <Fact label="Allowed domains">{s.allowed_domains.map(d => '@' + d).join(', ') || 'any'}</Fact>
          <Fact label="Schedule">
            <span className="inline-flex items-center gap-1"><CalendarClock className="h-3.5 w-3.5 text-muted-foreground" />Daily, 09:00-11:00 IST</span>
            {status?.schedule?.next_run_at && <span className="block text-[11px] text-muted-foreground">next {fmtWhen(status.schedule.next_run_at)}</span>}
          </Fact>
          <Fact label="Templates on">{status?.enabled_templates} of {status?.templates}</Fact>
          <Fact label="Recipients">{status?.recipients} active</Fact>
        </div>
      )}

      {s && s.problems.length > 0 && (
        <div className="rounded-lg border border-[var(--status-watch-border)] bg-[var(--status-watch-bg)] px-3 py-2.5 text-[12px] text-[var(--status-watch-fg)]">
          <p className="mb-1 flex items-center gap-1.5 font-semibold"><AlertTriangle className="h-3.5 w-3.5" />Settings to fix in backend/.env</p>
          <ul className="ml-5 list-disc space-y-0.5">{s.problems.map(p => <li key={p}>{p}</li>)}</ul>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {(['sent', 'test', 'failed', 'no_recipients'] as const).map(k => (
          <KPITile key={k} icon={KPI_ICON[k]} label={`${STATUS_META[k].label} · 7 days`} value={(counts[k] ?? 0).toLocaleString('en-IN')}
            tone={k === 'failed' && (counts[k] ?? 0) > 0 ? 'critical' : k === 'no_recipients' && (counts[k] ?? 0) > 0 ? 'watch' : 'neutral'}
            onClick={onOpenLog} />
        ))}
      </div>

      <div className="bento-card space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={btn.secondary} disabled={!!busy} onClick={() => act('dry')}>
            <Eye className="h-3.5 w-3.5" />{busy === 'dry' ? 'Checking…' : 'Preview next run'}
          </button>
          <button type="button" className={btn.primary} disabled={!!busy || !s?.enabled} onClick={() => setConfirm('run')}
            title={s?.enabled ? 'Send everything that is due now' : 'Turn on EMAIL_ENABLED in backend/.env first'}>
            <Send className="h-3.5 w-3.5" />Send now
          </button>
          <button type="button" className={btn.secondary} disabled={!!busy} onClick={() => setConfirm('baseline')}>
            <Rocket className="h-3.5 w-3.5" />Go-live: start from today
          </button>
          <span className="text-[11.5px] text-muted-foreground">Preview sends nothing and records nothing.</span>
        </div>
        {result && <RunTable result={result} />}
      </div>

      <Dialog open={confirm === 'run'} onClose={() => setConfirm('')} title="Send now?"
        description="Every enabled template is checked and each alert that is due and not yet sent goes out now."
        footer={<><button type="button" className={btn.secondary} onClick={() => setConfirm('')}>Cancel</button>
          <button type="button" className={btn.primary} onClick={() => act('run')}><PlayCircle className="h-3.5 w-3.5" />Send</button></>}>
        <p className="text-[12.5px] text-muted-foreground">{s?.test_mode ? `Test mode is on: everything goes only to ${s.test_recipients.join(', ')}.` : 'Live mode: emails go to the real distribution groups.'}</p>
      </Dialog>
      <Dialog open={confirm === 'baseline'} onClose={() => setConfirm('')} title="Start from today?"
        description="Every alert that is already true today (overdue orders, pending GRNs, ...) is marked as handled and will not be emailed. From now on only new events send email."
        footer={<><button type="button" className={btn.secondary} onClick={() => setConfirm('')}>Cancel</button>
          <button type="button" className={btn.primary} onClick={() => act('baseline')}><Rocket className="h-3.5 w-3.5" />Start from today</button></>}>
        <p className="text-[12.5px] text-muted-foreground">Use this once, when email goes live, so people are not flooded with the backlog. The weekly digest still lists everything that is overdue or at risk.</p>
      </Dialog>
    </div>
  );
}

const KPI_ICON = { sent: CheckCircle2, test: FlaskConical, failed: MailX, no_recipients: UserX };

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-0.5 break-words text-foreground">{children}</div>
    </div>
  );
}

function RunTable({ result }: { result: RunResult }) {
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-1.5 text-[12.5px] font-semibold text-foreground"><Mail className="h-3.5 w-3.5" />{result.dry_run ? 'Next run would: ' : ''}{result.message}</p>
      {result.items.length > 0 && (
        <div className="max-h-[360px] overflow-auto rounded-lg border border-border">
          <table className="w-full min-w-[720px] text-[12px]">
            <thead className="sticky top-0 bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold"><th>Status</th><th>Level</th><th>Subject</th><th>To</th><th>Cc</th></tr>
            </thead>
            <tbody>
              {result.items.map((it, i) => {
                const m = STATUS_META[it.status] ?? { label: it.status, tone: 'neutral' as const };
                return (
                  <tr key={i} className="border-t border-[var(--border-subtle)] align-top">
                    <td className="whitespace-nowrap px-3 py-1.5"><StatusPill tone={m.tone}>{m.label}</StatusPill></td>
                    <td className="whitespace-nowrap px-3 py-1.5">{it.level ? <span className="inline-flex items-center gap-1.5"><LevelBadge level={it.level} />{it.escalation === 'escalated' && <span className="text-[11px] text-[var(--status-risk-fg)]">escalated</span>}{it.escalation === 'held' && <span className="text-[11px] text-muted-foreground">held</span>}</span> : '—'}</td>
                    <td className="px-3 py-1.5">{it.subject ?? it.template}{(it.why || it.detail) && <span className="block text-[11px] text-muted-foreground">{it.why || it.detail}</span>}</td>
                    <td className="px-3 py-1.5 text-muted-foreground">{(it.to ?? []).join(', ') || '—'}</td>
                    <td className="px-3 py-1.5 text-muted-foreground">{(it.cc ?? []).join(', ') || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
