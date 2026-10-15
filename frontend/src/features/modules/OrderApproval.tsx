/* Module order approvals from the Ordering Schedule
   (backend/routers/order_approvals.py, services/order_approvals.py).

   A month cell's popover shows that month's approval for the project and a
   "Request approval" button; the dialog (rendered at page level, because the
   popover closes on any outside click) raises the request, and lets an
   approver approve or return it and anyone see its history. Approved, the
   quantity is frozen in its month until the PO is in SAP. */
import { useEffect, useState } from 'react';
import { CheckCircle2, Clock, Lock, Send, Undo2, XCircle } from 'lucide-react';
import { Dialog, Loader, StatusPill, cx } from '../../components/ui/primitives';
import type { Tone } from '../../components/ui/primitives';
import { btn, field, fmtWhen } from '../admin/adminApi';
import type { ModuleProject } from './types';

export type ApprovalStatus = 'pending' | 'approved' | 'returned' | 'cancelled' | 'ordered';

export interface ApprovalEvent { at: string | null; kind: string; actor: string | null; detail: string | null }
export interface OrderApprovalRow {
  id: number; mapping_id: number; project_name: string | null; month: string; mwp: number;
  phases: ApprovalPhase[];
  /** The plan as it stood when requested - what the approver decides on. */
  basis: {
    lta?: string; scod?: string; capacity_mwp?: number; ordered_mwp?: number; balance_mwp?: number;
    month_planned_mwp?: number; vendor_type?: string; priority?: string; warnings?: string[];
  };
  status: ApprovalStatus; remaining_mwp: number | null; request_note: string | null;
  requested_by: string; requested_at: string | null; decided_by: string | null; decided_at: string | null;
  decision_note: string | null; ordered_at: string | null; alert_id: number | null; history: ApprovalEvent[];
  can_decide?: boolean; can_cancel?: boolean; approvers?: string[];
  own_request?: boolean; you_are?: 'superadmin' | 'approver' | null;
}

export interface ApprovalPhase {
  phase_label: string; mwp: number; order_date?: string; tc_date?: string; ftc_date?: string;
  ftc_reachable?: boolean; ftc_short_days?: number; overdue?: boolean; delay_months?: number;
}

export const APPROVAL_META: Record<ApprovalStatus, { label: string; tone: Tone }> = {
  pending: { label: 'Approval pending', tone: 'watch' },
  approved: { label: 'Approved · frozen', tone: 'done' },
  returned: { label: 'Returned', tone: 'risk' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
  ordered: { label: 'Ordered in SAP', tone: 'healthy' },
};

const API = '/akasha/api/module-approvals';
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...init });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body as T;
}
const post = <T,>(path: string, data: unknown) => call<T>(path, { method: 'POST', body: JSON.stringify(data) });

/** Window event that closes the Ordering Schedule's cell popovers. */
export const CLOSE_POPOVERS = 'akasha:close-popovers';
const closePopovers = () => window.dispatchEvent(new Event(CLOSE_POPOVERS));

const mw = (v: number | null | undefined) => (v ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 1 });

/** What the signed-in user may do (backend: GET /api/module-approvals/me):
    TC Ordering raises requests, the approval template's To group (TC Head)
    decides - each for the portfolios they cover. */
export interface ApprovalRole {
  superadmin: boolean;
  request: { all: boolean; portfolios: string[] };
  approve: { all: boolean; portfolios: string[] };
  waiting: number;
}
const DEMO_PORTFOLIO = 'akasha demo';   // never covered by "all portfolios" (engine.DEMO_PORTFOLIO)

export function covers(r: { all: boolean; portfolios: string[] }, cluster: string | null | undefined): boolean {
  const c = (cluster ?? '').toLowerCase();
  if (r.portfolios.some(x => x.toLowerCase() === c)) return true;
  return r.all && !c.startsWith(DEMO_PORTFOLIO);
}

export function useApprovalRole(refreshKey = 0): ApprovalRole | null {
  const [role, setRole] = useState<ApprovalRole | null>(null);
  useEffect(() => { call<ApprovalRole>('/me').then(setRole).catch(() => setRole(null)); }, [refreshKey]);
  return role;
}

/** The month's open (or latest) approval for a project, if any. */
export function approvalFor(p: ModuleProject, month: string): OrderApprovalRow | undefined {
  const rows = (p.approvals ?? []).filter(a => a.month === month);
  return rows.find(a => a.status === 'pending' || a.status === 'approved') ?? rows[0];
}

/** Lock (frozen) or clock (pending) beside a month figure. */
export function ApprovalMark({ p, month }: { p: ModuleProject; month: string }) {
  const frozen = p.month_frozen_mwp?.[month] ?? 0;
  if (frozen > 0) return <Lock className="mr-1 h-2.5 w-2.5 shrink-0" aria-label={`${mw(frozen)} MWp approved and frozen`} />;
  const a = approvalFor(p, month);
  if (a?.status === 'pending') return <Clock className="mr-1 h-2.5 w-2.5 shrink-0" aria-label="Approval pending" />;
  return null;
}

/* Inside the month popover: where this month's approval stands. */
export function ApprovalSummary({ p, month, planned, canRequest, onOpen }: {
  p: ModuleProject; month: string; planned: number; canRequest: boolean;
  onOpen: (o: { mapping: ModuleProject; month: string; id?: number }) => void;
}) {
  const a = approvalFor(p, month);
  const open = a && (a.status === 'pending' || a.status === 'approved');
  const frozen = p.month_frozen_mwp?.[month] ?? 0;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border-subtle pt-2">
      <div className="min-w-0 text-[10.5px] leading-relaxed text-fg-secondary">
        {a ? (
          <>
            <StatusPill tone={APPROVAL_META[a.status].tone}>{APPROVAL_META[a.status].label}</StatusPill>
            <span className="ml-1.5">
              {mw(a.mwp)} MWp · requested by {a.requested_by} {fmtWhen(a.requested_at)}
              {a.decided_by && <> · {a.status === 'returned' ? 'returned' : 'decided'} by {a.decided_by}</>}
              {a.status === 'approved' && frozen > 0 && <> · <span className="font-semibold text-foreground">{mw(frozen)} MWp frozen in {month}</span> until the PO is in SAP</>}
            </span>
          </>
        ) : planned > 0 && canRequest ? (
          <>Ask TC Head to approve this month's order. Once approved it is frozen in <span className="font-semibold">{month}</span> - vendor levelling will no longer move it.</>
        ) : planned > 0 ? (
          <>Approval requests for this order are raised by TC Ordering.</>
        ) : null}
      </div>
      <div className="flex shrink-0 gap-1.5">
        {a && <button type="button" className={btn.secondary} onClick={() => { closePopovers(); onOpen({ mapping: p, month, id: a.id }); }}>Details</button>}
        {!open && planned > 0 && canRequest && (
          <button type="button" className={btn.primary} onClick={() => { closePopovers(); onOpen({ mapping: p, month }); }}>
            <Send className="h-3.5 w-3.5" />Request approval
          </button>
        )}
      </div>
    </div>
  );
}

/* The request form, or one approval with its history and actions. */
export function ApprovalDialog({ target, onClose, onChanged }: {
  target: { mapping: ModuleProject; month: string; id?: number } | null;
  onClose: () => void; onChanged: () => void;
}) {
  const [row, setRow] = useState<OrderApprovalRow | null>(null);
  const [qty, setQty] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const p = target?.mapping;
  const month = target?.month ?? '';
  const planned = p?.month_mwp?.[month] ?? 0;

  useEffect(() => {
    setRow(null); setError(''); setNote(''); setBusy('');
    setQty(planned ? String(Math.round(planned * 10) / 10) : '');
    if (target?.id) call<OrderApprovalRow>(`/${target.id}`).then(setRow).catch(e => setError((e as Error).message));
  }, [target?.id, target?.month, target?.mapping?.id, planned]);

  const act = async (kind: 'request' | 'approve' | 'return' | 'cancel') => {
    setBusy(kind); setError('');
    try {
      const r = kind === 'request'
        ? await post<OrderApprovalRow>('', { mapping_id: p!.id, month, mwp: Number(qty), note: note.trim() || undefined })
        : kind === 'cancel'
          ? await post<OrderApprovalRow>(`/${row!.id}/cancel`, { note })
          : await post<OrderApprovalRow>(`/${row!.id}/decide`, { decision: kind, note: note.trim() || undefined });
      setRow(r); setNote('');
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(''); }
  };

  const phases = (p?.month_phases?.[month] ?? []);
  const requesting = !target?.id && !row;
  const qtyNum = Number(qty);
  const qtyOk = qtyNum > 0 && qtyNum <= planned + 0.05;

  return (
    <Dialog open={!!target} onClose={onClose} size="lg"
      title={requesting ? 'Request approval' : `Approval #${row?.id ?? target?.id ?? ''}`}
      description={p ? `${p.project_name} · ${month}` : undefined}
      footer={<button type="button" className={btn.secondary} onClick={onClose}>Close</button>}>
      {error && <p role="alert" className="mb-3 rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-[12px] text-[var(--status-critical-fg)]">{error}</p>}

      {requesting ? (
        <div className="space-y-3">
          <p className="text-[12.5px] text-muted-foreground">
            The approval email goes to the approvers (the approval template's To group - TC Head), with you on Cc.
            Once approved, the quantity is <span className="font-semibold text-foreground">frozen in {month}</span>: vendor levelling and the overdue
            carry-forward no longer move it, until its PO is in SAP.
          </p>
          <table className="w-full text-[12px]">
            <thead className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <PhaseHead month={month} />
            </thead>
            <tbody>{phases.map((ph, i) => <PhaseRow key={i} ph={ph} month={month} />)}</tbody>
          </table>
          <p className="text-[11.5px] text-muted-foreground">These figures, with the project's LTA, ordered and balance, are saved with the request as the basis the approver decides on.</p>
          <div className="grid gap-3 sm:grid-cols-[160px_minmax(0,1fr)]">
            <label className="block text-[12px] font-medium text-foreground">Quantity (MWp)
              <input type="text" inputMode="decimal" autoComplete="off" className={`${field} mt-1 tabular-nums`}
                value={qty} aria-invalid={qty !== '' && !qtyOk} aria-describedby="appr-qty-hint"
                onChange={e => { if (/^\d{0,5}(\.\d?)?$/.test(e.target.value)) setQty(e.target.value); }} />
              <span id="appr-qty-hint" className={cx('mt-0.5 block text-[11px] font-normal', qty !== '' && !qtyOk ? 'text-[var(--status-critical-fg)]' : 'text-muted-foreground')}>
                {qty !== '' && !qtyOk ? `Enter 0.1 to ${mw(planned)} MWp` : `Up to ${mw(planned)} MWp planned`}
              </span>
            </label>
            <label className="block text-[12px] font-medium text-foreground">Note for the approver
              <textarea rows={3} maxLength={1000} className={`${field} mt-1`} value={note} placeholder="e.g. Vendor slot confirmed for this month"
                onChange={e => setNote(e.target.value)} />
            </label>
          </div>
          <div className="flex justify-end">
            <button type="button" className={btn.primary} disabled={!qtyOk || !!busy} onClick={() => act('request')}>
              <Send className="h-3.5 w-3.5" />{busy ? 'Sending…' : 'Send for approval'}
            </button>
          </div>
        </div>
      ) : !row ? (
        <div className="flex justify-center py-8"><Loader size="md" label="Loading…" /></div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone={APPROVAL_META[row.status].tone}>{APPROVAL_META[row.status].label}</StatusPill>
            <span className="text-[13px] font-semibold text-foreground">{mw(row.mwp)} MWp in {row.month}</span>
            {row.status === 'approved' && row.remaining_mwp != null && (
              <span className="text-[12px] text-muted-foreground">· {mw(row.remaining_mwp)} MWp still frozen (no PO yet)</span>
            )}
          </div>
          <Basis row={row} />
          <dl className="grid gap-x-6 gap-y-2 text-[12px] sm:grid-cols-2">
            <Fact label="Requested">{row.requested_by} · {fmtWhen(row.requested_at)}{row.request_note && <span className="block text-muted-foreground">“{row.request_note}”</span>}</Fact>
            <Fact label="Decision">{row.decided_by ? <>{row.decided_by} · {fmtWhen(row.decided_at)}{row.decision_note && <span className="block text-muted-foreground">“{row.decision_note}”</span>}</> : <span className="text-muted-foreground">Not decided yet</span>}</Fact>
            {row.alert_id && <Fact label="Email alert"><a className="text-primary hover:underline" href={`/akasha/alerts/${row.alert_id}`}>Alert #{row.alert_id}</a></Fact>}
          </dl>

          {row.status === 'pending' && <WhoDecides row={row} />}

          {(row.can_decide || row.can_cancel) && (
            <div className="rounded-lg border border-primary/30 bg-primary/[0.03] p-3">
              <label className="block text-[12px] font-medium text-foreground">Remarks {row.can_decide ? '(required to return or cancel)' : '(required to cancel)'}
                <textarea rows={2} maxLength={1000} className={`${field} mt-1`} value={note} onChange={e => setNote(e.target.value)} />
              </label>
              <div className="mt-2.5 flex flex-wrap gap-2">
                {row.can_decide && <>
                  <button type="button" className={btn.primary} disabled={!!busy} onClick={() => act('approve')}><CheckCircle2 className="h-3.5 w-3.5" />{busy === 'approve' ? 'Approving…' : 'Approve and freeze'}</button>
                  <button type="button" className={btn.secondary} disabled={!!busy || note.trim().length < 5} onClick={() => act('return')}><Undo2 className="h-3.5 w-3.5" />Return</button>
                </>}
                {row.can_cancel && (
                  <button type="button" className={cx(btn.ghost, 'ml-auto')} disabled={!!busy || note.trim().length < 5} onClick={() => act('cancel')}>
                    <XCircle className="h-3.5 w-3.5" />{row.status === 'approved' ? 'Cancel and release the freeze' : 'Cancel request'}
                  </button>
                )}
              </div>
            </div>
          )}

          <section aria-labelledby="appr-history">
            <h3 id="appr-history" className="mb-1.5 text-[12px] font-semibold text-foreground">History <span className="font-normal text-muted-foreground">· latest first</span></h3>
            <ol className="space-y-2 border-l border-border pl-3">
              {row.history.slice().reverse().map((e, i) => (
                <li key={i} className="text-[12px] leading-snug">
                  <span className="font-semibold capitalize text-foreground">{e.kind}</span>
                  <span className="ml-2 text-[11px] text-muted-foreground">{fmtWhen(e.at)}{e.actor && ` · ${e.actor}`}</span>
                  {e.detail && <p className="text-muted-foreground">{e.detail}</p>}
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
    </Dialog>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-foreground">{children}</dd>
    </div>
  );
}

/* Top of the Ordering Schedule: the requests waiting for this user's
   decision (they are an approver - the approval email's To group - and did
   not raise it). Seen on opening the dashboard, whether or not the email
   arrived; one approver deciding clears it for all of them. */
export function WaitingForApproval({ projects, refreshKey, onOpen }: {
  projects: ModuleProject[]; refreshKey: number;
  onOpen: (o: { mapping: ModuleProject; month: string; id?: number }) => void;
}) {
  const [rows, setRows] = useState<OrderApprovalRow[]>([]);
  useEffect(() => {
    call<OrderApprovalRow[]>('/waiting').then(setRows).catch(() => setRows([]));
  }, [refreshKey]);
  if (rows.length === 0) return null;
  return (
    <section aria-labelledby="awaiting-approval" className="rounded-xl border border-[var(--status-watch-border)] bg-[var(--status-watch-bg)] px-4 py-3">
      <h2 id="awaiting-approval" className="flex items-center gap-2 text-[13px] font-semibold text-[var(--status-watch-fg)]">
        <Clock className="h-4 w-4" aria-hidden />
        {rows.length} module order{rows.length === 1 ? '' : 's'} waiting for your approval
      </h2>
      <ul className="mt-2 divide-y divide-[var(--status-watch-border)]">
        {rows.map(a => {
          const warn = a.basis?.warnings?.length ?? 0;
          const mapping = projects.find(x => x.id === a.mapping_id);
          return (
            <li key={a.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2 text-[12.5px]">
              <span className="min-w-0 flex-1">
                <span className="font-semibold text-foreground">{a.project_name}</span>
                <span className="text-foreground"> · {mw(a.mwp)} MWp in {a.month}</span>
                <span className="block text-[11.5px] text-muted-foreground">
                  Requested by {a.requested_by} · {fmtWhen(a.requested_at)}{a.request_note && ` · “${a.request_note}”`}
                </span>
              </span>
              {warn > 0
                ? <StatusPill tone="risk">{warn} schedule risk{warn === 1 ? '' : 's'}</StatusPill>
                : <StatusPill tone="healthy">No schedule risk</StatusPill>}
              <button type="button" className={btn.primary}
                onClick={() => onOpen({ mapping: mapping ?? ({ id: a.mapping_id, project_name: a.project_name ?? '' } as unknown as ModuleProject), month: a.month, id: a.id })}>
                Review and decide
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function PhaseHead({ month }: { month: string }) {
  return (
    <tr className="[&>th]:py-1 [&>th]:pr-3 [&>th]:font-semibold">
      <th>Phase in {month}</th><th className="text-right">MWp</th><th>Ordering date</th><th>Needed at site</th><th>FTC (P6)</th><th>Ordering in {month}</th>
    </tr>
  );
}

function PhaseRow({ ph, month }: { ph: ApprovalPhase; month: string }) {
  const verdict = ph.ftc_reachable === false
    ? { text: `Misses FTC by ${ph.ftc_short_days ?? 0} d`, cls: 'text-[var(--status-critical-fg)]' }
    : ph.ftc_reachable === true ? { text: 'Meets FTC', cls: 'text-[var(--status-healthy-fg)]' } : { text: '—', cls: 'text-muted-foreground' };
  return (
    <tr className="border-t border-[var(--border-subtle)] [&>td]:py-1.5 [&>td]:pr-3">
      <td className="text-foreground">{ph.phase_label || 'Main'}{ph.overdue && <span className="ml-1.5 text-[11px] text-[var(--status-critical-fg)]">overdue</span>}</td>
      <td className="text-right tabular-nums">{mw(ph.mwp)}</td>
      <td className="tabular-nums text-muted-foreground">{ph.order_date || '—'}</td>
      <td className="tabular-nums text-muted-foreground">{ph.tc_date || '—'}</td>
      <td className="tabular-nums text-muted-foreground">{ph.ftc_date || '—'}</td>
      <td className={cx('whitespace-nowrap font-medium', verdict.cls)} title={`If the order is placed in ${month}`}>{verdict.text}</td>
    </tr>
  );
}

/* What the approver decides on: the plan as it stood when requested. */
function Basis({ row }: { row: OrderApprovalRow }) {
  const b = row.basis ?? {};
  const warnings = b.warnings ?? [];
  const recorded = Object.keys(b).length > 0;
  return (
    <section aria-labelledby="appr-basis" className="space-y-2">
      <h3 id="appr-basis" className="text-[12px] font-semibold text-foreground">Decision basis <span className="font-normal text-muted-foreground">· the plan when it was requested</span></h3>
      {recorded && (warnings.length > 0 ? (
        <ul className="space-y-1 rounded-lg border border-[var(--status-risk-border)] bg-[var(--status-risk-bg)] px-3 py-2 text-[12px] text-[var(--status-risk-fg)]">
          {warnings.map(w => <li key={w}>{w}</li>)}
        </ul>
      ) : (
        <p className="rounded-lg border border-[var(--status-healthy-border)] bg-[var(--status-healthy-bg)] px-3 py-2 text-[12px] text-[var(--status-healthy-fg)]">
          No schedule risk in the plan: ordering in {row.month} meets every FTC below, inside the LTA.
        </p>
      ))}
      <table className="w-full text-[12px]">
        <thead className="text-left text-[10px] uppercase tracking-wider text-muted-foreground"><PhaseHead month={row.month} /></thead>
        <tbody>{row.phases.map((ph, i) => <PhaseRow key={i} ph={ph} month={row.month} />)}</tbody>
      </table>
      {recorded ? (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-[12px] sm:grid-cols-4">
          <Fact label="LTA">{b.lta || '—'}</Fact>
          <Fact label="Module origin">{b.vendor_type || '—'}</Fact>
          <Fact label="Ordered / capacity">{mw(b.ordered_mwp)} / {mw(b.capacity_mwp)} MWp</Fact>
          <Fact label="Balance to order">{mw(b.balance_mwp)} MWp</Fact>
        </dl>
      ) : (
        <p className="text-[11.5px] text-muted-foreground">Requested before the decision basis was recorded - check the project in the Ordering Schedule.</p>
      )}
    </section>
  );
}

function WhoDecides({ row }: { row: OrderApprovalRow }) {
  const people = row.approvers ?? [];
  return (
    <p className="rounded-lg border border-border bg-[var(--surface-sunken)] px-3 py-2 text-[12px] text-muted-foreground">
      {people.length > 0
        ? <>Approvers: <span className="text-foreground">{people.join(', ')}</span> (users with the TC Head role for this portfolio, and the TC Head group). </>
        : <>No approver for this portfolio yet - give someone the TC Head role (Admin › Users & roles) or add them to the TC Head group (Email notifications › Distribution groups). Until then only a superadmin can decide. </>}
      {row.own_request ? <span className="font-medium text-foreground">You raised this request, so another approver decides it.</span>
        : row.you_are === 'superadmin' && !people.length ? <span className="font-medium text-foreground">You can decide as superadmin.</span> : null}
    </p>
  );
}
