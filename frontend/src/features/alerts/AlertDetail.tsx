/* One alert: where it stands, the acknowledgement form for a To recipient
   (or an administrator recording one for them), who it went to at which
   level, and its timeline. Used by the /alerts/:id page and the admin
   console's Alerts view. */
import { useState } from 'react';
import { ArrowUpRight, Check, CheckCircle2, Clock, Mail, PauseCircle, ShieldCheck, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { StatusPill, cx } from '../../components/ui/primitives';
import type { Tone } from '../../components/ui/primitives';
import { btn, field, fmtWhen } from '../admin/adminApi';
import { alertsApi, fmtDay, isoFromDay, todayIst } from './alertsApi';
import { ApprovalDialog } from '../modules/OrderApproval';
import type { ModuleProject } from '../modules/types';
import type { AlertDetailData, AlertEvent, Level } from './alertsApi';

export function LevelBadge({ level, title }: { level: Level | number; title?: string }) {
  return (
    <span title={title ?? `Level ${level} of 3`}
      className={cx('inline-flex h-5 min-w-[26px] items-center justify-center rounded px-1.5 text-[11px] font-semibold tabular-nums',
        level === 1 ? 'bg-muted text-foreground' : 'bg-primary/10 text-primary')}>L{level}</span>
  );
}

/** Where an open alert stands, in one line and one tone. */
export function alertState(a: Pick<AlertDetailData, 'status' | 'acknowledged_at' | 'holds' | 'late_commitment' | 'expected_date' | 'level'>):
  { label: string; tone: Tone } {
  if (a.status === 'resolved') return { label: 'Closed', tone: 'healthy' };
  if (!a.acknowledged_at) return { label: 'Awaiting acknowledgement', tone: 'watch' };
  if (a.late_commitment) return { label: 'Expected after ordering date', tone: 'risk' };
  if (a.holds) return { label: `Held at L${a.level}`, tone: 'done' };
  if (a.expected_date) return { label: 'Expected date passed', tone: 'risk' };
  return { label: 'Acknowledged, no date', tone: 'watch' };
}

const EVENT_META: Record<AlertEvent['kind'], { label: string; icon: typeof Mail }> = {
  opened: { label: 'Alert opened', icon: Mail },
  sent: { label: 'Email sent', icon: Mail },
  escalated: { label: 'Escalated', icon: TrendingUp },
  held: { label: 'Held - not escalated', icon: PauseCircle },
  acknowledged: { label: 'Acknowledged', icon: ShieldCheck },
  updated: { label: 'Update', icon: Clock },
  resolved: { label: 'Closed', icon: CheckCircle2 },
};

export default function AlertDetail({ data, onChange }: { data: AlertDetailData; onChange: (d: AlertDetailData) => void }) {
  const a = data;
  const state = alertState(a);
  const order = a.kind === 'order';
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="section-label">{a.template_name}</p>
          <h2 className="mt-0.5 text-[16px] font-semibold leading-snug text-foreground">
            {a.project_name || 'Akasha'}{a.phase && <span className="font-normal text-muted-foreground"> · {a.phase}</span>}
          </h2>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            {order && a.due_date && <>Ordering date <span className="font-medium text-foreground">{a.due_date}</span> · </>}
            {a.emails} email{a.emails === 1 ? '' : 's'} · first {fmtWhen(a.opened_at)}
            {a.project_link && <> · <Link to={a.project_link} className="inline-flex items-center gap-0.5 text-primary hover:underline">Project<ArrowUpRight className="h-3 w-3" /></Link></>}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {a.test && <StatusPill tone="ai">Test</StatusPill>}
          <LevelBadge level={a.level} title={`Emailed up to level ${a.level} of 3`} />
          <StatusPill tone={state.tone}>{state.label}</StatusPill>
        </div>
      </div>

      <StatusLine data={a} />

      {a.kind === 'approval' && a.approval_id
        ? <ApprovalLink data={a} />
        : a.status === 'open' && (a.can_acknowledge || a.is_admin)
        ? <AckForm data={a} onDone={onChange} />
        : a.status === 'open' && !a.can_acknowledge && (
          <p className="rounded-lg border border-border bg-[var(--surface-sunken)] px-3 py-2 text-[12px] text-muted-foreground">
            You were copied on this alert. Only its To recipients acknowledge it.
          </p>
        )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <section aria-labelledby="alert-recipients">
          <h3 id="alert-recipients" className="mb-1.5 text-[12px] font-semibold text-foreground">Sent to (To)</h3>
          <ul className="divide-y divide-[var(--border-subtle)] rounded-lg border border-border">
            {a.recipients.map(r => (
              <li key={r.email} className="flex items-center gap-2.5 px-3 py-2">
                <LevelBadge level={r.level} title={`First emailed at level ${r.level}`} />
                <div className="min-w-0 flex-1 leading-tight">
                  <div className="truncate text-[12.5px] font-medium text-foreground">{r.name || r.email}</div>
                  {r.name && <div className="truncate text-[11.5px] text-muted-foreground">{r.email}</div>}
                </div>
                {r.acknowledged_at
                  ? <span className="inline-flex shrink-0 items-center gap-1 text-[11.5px] text-[var(--status-healthy-fg)]"><Check className="h-3.5 w-3.5" />{fmtWhen(r.acknowledged_at)}</span>
                  : <span className="shrink-0 text-[11.5px] text-muted-foreground">Not acknowledged</span>}
              </li>
            ))}
            {a.recipients.length === 0 && <li className="px-3 py-2 text-[12px] text-muted-foreground">No To recipients recorded.</li>}
          </ul>
        </section>
        <section aria-labelledby="alert-timeline">
          <h3 id="alert-timeline" className="mb-1.5 text-[12px] font-semibold text-foreground">Timeline</h3>
          <ol className="space-y-2.5">
            {a.timeline.map((e, i) => {
              const m = EVENT_META[e.kind] ?? EVENT_META.sent;
              const Icon = m.icon;
              return (
                <li key={i} className="flex gap-2.5">
                  <span className={cx('mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
                    e.kind === 'escalated' ? 'bg-[var(--status-risk-bg)] text-[var(--status-risk-fg)]'
                      : e.kind === 'acknowledged' || e.kind === 'resolved' ? 'bg-[var(--status-healthy-bg)] text-[var(--status-healthy-fg)]'
                        : 'bg-muted text-muted-foreground')} aria-hidden><Icon className="h-3.5 w-3.5" /></span>
                  <div className="min-w-0 flex-1 text-[12px] leading-snug">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="font-semibold text-foreground">{m.label}</span>
                      {e.level && <span className="text-[11px] text-muted-foreground">L{e.level}</span>}
                      <span className="text-[11px] text-muted-foreground">{fmtWhen(e.at)}{e.actor && ` · ${e.actor}`}</span>
                    </div>
                    {e.detail && <p className="mt-0.5 text-muted-foreground">{e.detail}</p>}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      </div>
    </div>
  );
}

function StatusLine({ data: a }: { data: AlertDetailData }) {
  if (a.status === 'resolved') {
    return <Callout tone="healthy">Closed {fmtWhen(a.resolved_at)} - {a.resolved_reason}</Callout>;
  }
  return (
    <div className="space-y-2">
      {a.acknowledged_at && (
        <div className="rounded-lg border border-border px-3 py-2.5 text-[12.5px]">
          <p className="text-foreground">
            <span className="font-semibold">{a.acknowledged_by}</span> acknowledged at L{a.ack_level ?? a.level} on {fmtWhen(a.acknowledged_at)}
            {a.expected_date && <> · expects it done by <span className="font-semibold">{fmtDay(a.expected_date)}</span></>}
          </p>
          {a.update_note && <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{a.update_note}</p>}
        </div>
      )}
      {a.late_commitment && <Callout tone="risk">The expected date is after the ordering date ({a.due_date}), so it does not hold the alert - it keeps escalating as scheduled.</Callout>}
      {a.next_step && <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground"><Clock className="h-3.5 w-3.5" aria-hidden />{a.next_step}</p>}
    </div>
  );
}

const CALLOUT = {
  healthy: 'border-[var(--status-healthy-border)] bg-[var(--status-healthy-bg)] text-[var(--status-healthy-fg)]',
  risk: 'border-[var(--status-risk-border)] bg-[var(--status-risk-bg)] text-[var(--status-risk-fg)]',
};

function Callout({ tone, children }: { tone: keyof typeof CALLOUT; children: React.ReactNode }) {
  return <p className={cx('rounded-lg border px-3 py-2 text-[12px]', CALLOUT[tone])}>{children}</p>;
}

/* An approval request: approvers decide in the approval itself (history,
   Approve / Return), and the alert closes with the decision. */
function ApprovalLink({ data: a }: { data: AlertDetailData }) {
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-primary/30 bg-primary/[0.03] p-3">
      <p className="text-[12.5px] text-foreground">
        {a.status === 'open' && !done ? 'This order is waiting for approval. Approvers decide in the approval: Approve and freeze it in its month, or Return it with remarks.'
          : 'This approval has been decided - its history shows who, when and the remarks.'}
      </p>
      <button type="button" className={btn.primary} onClick={() => setOpen(true)}>
        <ShieldCheck className="h-3.5 w-3.5" />{a.status === 'open' && !done ? 'Review and decide' : 'View the approval'}
      </button>
      <ApprovalDialog target={open ? { mapping: { id: 0, project_name: a.project_name ?? '' } as unknown as ModuleProject, month: '', id: a.approval_id ?? undefined } : null}
        onClose={() => setOpen(false)} onChanged={() => setDone(true)} />
    </div>
  );
}

function AckForm({ data: a, onDone }: { data: AlertDetailData; onDone: (d: AlertDetailData) => void }) {
  const behalf = !a.can_acknowledge;            // an administrator recording it for a recipient
  const order = a.kind === 'order';
  const updating = !behalf && !!a.my_ack;
  const [note, setNote] = useState('');
  const [date, setDate] = useState(a.expected_date ?? '');
  const [who, setWho] = useState(a.recipients.find(r => !r.acknowledged_at)?.email ?? a.recipients[0]?.email ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const today = todayIst();
  const due = isoFromDay(a.due_date);
  const late = order && !!date && !!due && date > due;

  if (behalf && a.recipients.length === 0) return null;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      onDone(await alertsApi.acknowledge(a.id, { note: note.trim() || undefined, expected_date: date || undefined,
        on_behalf_of: behalf ? who : undefined }));
      setNote('');
    } catch (err) {
      setError((err as Error).message);
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="rounded-lg border border-primary/30 bg-primary/[0.03] p-3">
      <h3 className="text-[13px] font-semibold text-foreground">
        {behalf ? 'Record an acknowledgement for a recipient' : updating ? 'Update' : 'Acknowledge'}
      </h3>
      <p className="mt-0.5 text-[12px] text-muted-foreground">
        {behalf ? 'When a recipient confirmed outside Akasha (by phone, in a meeting). Your name is recorded with it.'
          : a.kind === 'one_off' ? 'Confirms you have seen this. It closes the alert.'
            : `An expected date${order && a.due_date ? ` on or before the ordering date (${a.due_date})` : ''} holds the next reminder at level ${a.level}. Without one, it escalates as scheduled.`}
      </p>
      {behalf && (
        <label className="mt-2.5 block text-[12px] font-medium text-foreground">Recipient
          <select className={`${field} mt-1`} value={who} onChange={e => setWho(e.target.value)}>
            {a.recipients.map(r => <option key={r.email} value={r.email}>{r.name ? `${r.name} · ${r.email}` : r.email}{r.acknowledged_at ? ' (acknowledged)' : ''}</option>)}
          </select>
        </label>
      )}
      <div className={cx('mt-2.5 grid gap-3', a.kind !== 'one_off' && 'sm:grid-cols-[minmax(0,1fr)_180px]')}>
        <label className="block text-[12px] font-medium text-foreground">{behalf ? 'How they confirmed, and what is being done' : 'What is being done'}{behalf && <span className="text-[var(--status-critical-fg)]"> *</span>}
          <textarea rows={2} maxLength={1000} className={`${field} mt-1`} value={note} required={behalf}
            placeholder={order ? 'e.g. PR raised, vendor slot confirmed for March' : 'Optional'} onChange={e => setNote(e.target.value)} />
        </label>
        {a.kind !== 'one_off' && (
          <label className="block text-[12px] font-medium text-foreground">{order ? 'Expected PO date' : 'Expected done by'}
            <input type="date" className={`${field} mt-1`} value={date} min={today}
              onChange={e => setDate(e.target.value)} aria-describedby={late ? 'ack-late' : undefined} />
          </label>
        )}
      </div>
      {late && <p id="ack-late" className="mt-1.5 text-[11.5px] text-[var(--status-risk-fg)]">This is after the ordering date ({a.due_date}): it is recorded, but it will not hold the alert.</p>}
      {error && <p role="alert" className="mt-1.5 text-[12px] text-[var(--status-critical-fg)]">{error}</p>}
      <div className="mt-3 flex items-center gap-2">
        <button type="submit" className={btn.primary} disabled={busy || (behalf && (!who || !note.trim())) || (updating && !note.trim() && date === (a.expected_date ?? ''))}>
          <ShieldCheck className="h-3.5 w-3.5" />{busy ? 'Saving…' : behalf ? 'Record acknowledgement' : updating ? 'Save update' : 'Acknowledge'}
        </button>
        {a.emails_sent.length > 0 && !behalf && (
          <span className="text-[11.5px] text-muted-foreground">Signed in as {a.you.name}{a.you.email && ` (${a.you.email})`}</span>
        )}
      </div>
    </form>
  );
}
