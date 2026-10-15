/* Admin console - Email notifications. Four views over one module
   (backend/services/email_notify): Overview (is it on, where does it send,
   what would go out next), Templates (edit, preview, test, history), the
   distribution groups, and the email log. Needs email.manage. */
import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CalendarClock, CheckCircle2, Eye, FlaskConical, Mail, MailX, PlayCircle, Rocket, Send, UserX } from 'lucide-react';
import { Dialog, KPITile, PageHeader, StatusPill, cx } from '../../../components/ui/primitives';
import { btn, field, fmtWhen } from '../adminApi';
import { useAuth } from '../../../context/AuthContext';
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
      {view === 'overview' && <Overview onOpenLog={() => setView('log')} onGo={setView} />}
      {view === 'templates' && <TemplatesView />}
      {view === 'alerts' && <AlertsView />}
      {view === 'recipients' && <RecipientsView />}
      {view === 'log' && <LogView />}
    </div>
  );
}

function Overview({ onOpenLog, onGo }: { onOpenLog: () => void; onGo: (v: View) => void }) {
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

      {status && <SetupChecklist status={status} onGo={onGo} onChanged={load} />}

      <section className="bento-card space-y-3 p-4" aria-labelledby="run-title">
        <div>
          <h2 id="run-title" className="text-[13px] font-semibold text-foreground">Run the alerts by hand</h2>
          <p className="text-[12px] text-muted-foreground">Akasha checks every switched-on template once a day (09:00-11:00 IST). These run that check now.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <RunAction icon={<Eye className="h-3.5 w-3.5" />} label={busy === 'dry' ? 'Checking…' : 'Preview next run'} disabled={!!busy}
            onClick={() => act('dry')} text="Lists what the daily check would send right now, and to whom. Sends nothing, records nothing." />
          <RunAction primary icon={<Send className="h-3.5 w-3.5" />} label="Send now" disabled={!!busy || !s?.enabled} onClick={() => setConfirm('run')}
            text={s?.enabled ? (s.test_mode ? `Runs the daily check now. Test mode: everything goes only to ${s.test_recipients.join(', ') || 'the test recipients'}.`
              : 'Runs the daily check now and emails the real distribution groups.')
              : 'Off: email sending is switched off on this server. Set EMAIL_ENABLED=true in backend/.env and restart.'}
            warn={!s?.enabled} />
          <RunAction icon={<Rocket className="h-3.5 w-3.5" />} label="Go-live: start from today" disabled={!!busy} onClick={() => setConfirm('baseline')}
            text={status?.baseline_done ? 'Already done. Use once only: it marks everything already overdue as handled, so going live does not flood people.'
              : 'Use once, on the day email goes live: marks today\'s backlog as handled so only new events are emailed.'} />
        </div>
        {result && <RunTable result={result} />}
      </section>

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
      {(result.items ?? []).length > 0 && (
        <div className="max-h-[360px] overflow-auto rounded-lg border border-border">
          <table className="w-full min-w-[720px] text-[12px]">
            <thead className="sticky top-0 bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold"><th>Status</th><th>Level</th><th>Subject</th><th>To</th><th>Cc</th></tr>
            </thead>
            <tbody>
              {(result.items ?? []).map((it, i) => {
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

function RunAction({ icon, label, text, onClick, disabled, primary, warn }: {
  icon: React.ReactNode; label: string; text: string; onClick: () => void; disabled?: boolean; primary?: boolean; warn?: boolean;
}) {
  return (
    <div className="flex flex-col items-start gap-1.5 rounded-lg border border-border p-3">
      <button type="button" className={primary ? btn.primary : btn.secondary} disabled={disabled} onClick={onClick}>{icon}{label}</button>
      <p className={cx('text-[11.5px] leading-snug', warn ? 'text-[var(--status-watch-fg)]' : 'text-muted-foreground')}>{text}</p>
    </div>
  );
}

/* Setting up email, in order, each step checked against the live settings and
   data - so "is it ready?" is answered on the screen, not from memory. */
function SetupChecklist({ status, onGo, onChanged }: { status: EmailStatus; onGo: (v: View) => void; onChanged: () => void }) {
  const { user } = useAuth();
  const s = status.settings;
  const g = status.groups ?? {};
  const [to, setTo] = useState(user?.email ?? '');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [sending, setSending] = useState(false);
  const sendTest = async () => {
    setSending(true); setMsg(null);
    try { const r = await emailApi.testSmtp(to || undefined); setMsg({ ok: true, text: r.message }); onChanged(); }
    catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    finally { setSending(false); }
  };
  const steps: { done: boolean; title: string; body: React.ReactNode }[] = [
    { done: s.configured, title: 'Mail server settings',
      body: <>In <code>backend/.env</code>: <code>SMTP_SERVER</code>, <code>SMTP_PORT</code>, <code>SMTP_USERNAME</code> / <code>SMTP_PASSWORD</code> (if the server needs them) and <code>EMAIL_FROM</code>. Restart the backend after any change.{s.configured && <> Now: {s.server}:{s.port}, from {s.from_addr}.</>}</> },
    { done: status.test_sent, title: 'Send a test email',
      body: (
        <div className="space-y-1.5">
          <p>Checks the mail server and the From address. Works while sending is still off - it goes only to this address.</p>
          <div className="flex flex-wrap items-center gap-2">
            <input aria-label="Send the test to" type="email" className={`${field.replace('w-full ', '')} w-64 py-1.5 text-[12px]`} value={to} onChange={e => setTo(e.target.value)} placeholder="you@adani.com" />
            <button type="button" className={btn.secondary} disabled={sending || !s.configured || !to} onClick={sendTest}><Mail className="h-3.5 w-3.5" />{sending ? 'Sending…' : 'Send test email'}</button>
          </div>
          {msg && <p role="status" className={msg.ok ? 'text-[var(--status-healthy-fg)]' : 'text-[var(--status-critical-fg)]'}>{msg.text}</p>}
        </div>
      ) },
    { done: !!s.public_url, title: 'Link back to Akasha',
      body: <><code>AKASHA_PUBLIC_URL</code> (e.g. <code>https://your-server/akasha</code>) - the Acknowledge and Approve buttons in emails open this address.{s.public_url && <> Now: {s.public_url}.</>}</> },
    { done: (g.tc_ordering ?? 0) > 0 && (g.tc_head ?? 0) > 0, title: 'Put people in the distribution groups',
      body: <>At least TC Ordering (ordering reminders; can raise approval requests) and TC Head (approves). Users with the TC Ordering or TC Head role (Users & roles) can request or approve, and approvers get the approval email, even outside the groups. Now: {
        ['tc_ordering', 'tc_head', 'projects', 'pmag', 'executive'].map(k => `${GROUP_LABEL[k]} ${g[k] ?? 0}`).join(' · ')}. <button type="button" className="font-medium text-primary hover:underline" onClick={() => onGo('recipients')}>Distribution groups</button></> },
    { done: status.enabled_templates > 0, title: 'Switch on the templates to use',
      body: <>{status.enabled_templates} of {status.templates} on. Check each one's L1 / L2 / L3 days and recipients first. <button type="button" className="font-medium text-primary hover:underline" onClick={() => onGo('templates')}>Templates</button></> },
    { done: s.enabled, title: 'Turn sending on - in test mode first',
      body: <><code>EMAIL_ENABLED=true</code>, <code>EMAIL_TEST_MODE=true</code> and <code>EMAIL_TEST_RECIPIENTS=you@adani.com</code>: every email then goes only to you, marked [TEST], showing who it would have gone to.</> },
    { done: false, title: 'Try it on the demo projects',
      body: (
        <div className="space-y-1">
          <p>On the server, in <code>backend/</code> - the demo projects show in Module Ordering only, and only your tester address gets their emails:</p>
          <ul className="ml-4 list-disc space-y-0.5">
            <li><code>python scripts/demo_email_project.py --find</code> lists the demo projects (the Solar &quot;Demo DPR&quot; and the &quot;(Digital)&quot; copies in P6).</li>
            <li><code>python scripts/demo_email_project.py --from-p6 &quot;Demo DPR&quot; --recipient you@adani.com</code> brings one in (repeat <code>--from-p6</code> for more).</li>
            <li>Switch on <i>Module ordering - overdue</i> and <i>Project delayed against AOP</i>, then &quot;Preview next run&quot; and &quot;Send now&quot; below.</li>
            <li>After &quot;Go-live: start from today&quot;, <code>--reset-emails</code> lets the demos email again. <code>--remove</code> takes them all out.</li>
          </ul>
        </div>
      ) },
    { done: !s.test_mode && status.baseline_done, title: 'Go live',
      body: <>Set <code>EMAIL_TEST_MODE=false</code>, restart, then "Go-live: start from today" once, so the backlog is not emailed.</> },
  ];
  const done = steps.filter(x => x.done).length;
  return (
    <details className="bento-card p-4" open={!(status.baseline_done && !s.test_mode)}>
      <summary className="cursor-pointer text-[13px] font-semibold text-foreground">
        Setting up email <span className="font-normal text-muted-foreground">· {done} of {steps.length - 1} done</span>
      </summary>
      <ol className="mt-3 space-y-2.5">
        {steps.map((st, i) => (
          <li key={st.title} className="flex gap-3 text-[12px]">
            <span aria-hidden className={cx('mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10.5px] font-bold',
              st.done ? 'bg-[var(--status-healthy-bg)] text-[var(--status-healthy-fg)]' : 'bg-muted text-muted-foreground')}>
              {st.done ? <CheckCircle2 className="h-3.5 w-3.5" /> : i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-foreground">{st.title}{st.done && <span className="sr-only"> (done)</span>}</p>
              <div className="mt-0.5 leading-relaxed text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-px [&_code]:text-[11px] [&_code]:text-foreground">{st.body}</div>
            </div>
          </li>
        ))}
      </ol>
    </details>
  );
}

const GROUP_LABEL: Record<string, string> = { tc_ordering: 'TC Ordering', tc_head: 'TC Head', projects: 'Projects', pmag: 'PMAG', executive: 'Executive' };
