/* Module order approvals - a section of the TC Ordering workspace (sidebar:
   Ordering > Order approvals) and a standalone page at /approvals.

   TC Ordering requests approval for a month's order from the Ordering
   Schedule; TC Head (the approval template's To group, or the TC Head role)
   approves or returns it. The tiles are the filters: what is waiting for the
   signed-in approver, everything pending, what is approved and frozen, and
   what is closed. */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Archive, ArrowLeft, CheckCircle2, Clock, Inbox, Lock } from 'lucide-react';
import { KPITile, Loader, PageHeader, StatusPill } from '../../components/ui/primitives';
import { btn, fmtWhen } from '../admin/adminApi';
import { useAuth } from '../../context/AuthContext';
import { APPROVAL_META, ApprovalDialog, useApprovalRole } from './OrderApproval';
import type { OrderApprovalRow } from './OrderApproval';
import type { ModuleProject } from './types';

type View = 'waiting' | 'pending' | 'approved' | 'closed';

async function load(path: string): Promise<OrderApprovalRow[]> {
  const res = await fetch(`/akasha/api/module-approvals${path}`, { credentials: 'same-origin' });
  const body = await res.json().catch(() => ([]));
  if (!res.ok) throw new Error((body as { detail?: string }).detail || `Request failed (${res.status})`);
  return body as OrderApprovalRow[];
}

const mw = (v: number) => v.toLocaleString('en-IN', { maximumFractionDigits: 1 });

export function ApprovalsView() {
  const [key, setKey] = useState(0);
  const role = useApprovalRole(key);
  const [all, setAll] = useState<OrderApprovalRow[] | null>(null);
  const [waiting, setWaiting] = useState<OrderApprovalRow[]>([]);
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<OrderApprovalRow | null>(null);

  const refresh = useCallback(() => {
    setError('');
    Promise.all([load(''), load('/waiting')])
      .then(([a, w]) => { setAll(a); setWaiting(w); })
      .catch(e => setError((e as Error).message));
  }, []);
  useEffect(refresh, [refresh, key]);

  const isApprover = !!role && (role.superadmin || role.approve.all || role.approve.portfolios.length > 0);
  // An approver lands on what waits for them; everyone else on what is pending.
  useEffect(() => {
    if (view === null && role && all) setView(isApprover && waiting.length ? 'waiting' : 'pending');
  }, [view, role, all, isApprover, waiting.length]);

  const groups = useMemo(() => {
    const rows = all ?? [];
    const approved = rows.filter(a => a.status === 'approved');
    const pending = rows.filter(a => a.status === 'pending');
    return {
      waiting, pending, approved,
      closed: rows.filter(a => ['returned', 'cancelled', 'ordered'].includes(a.status)),
      pendingMwp: pending.reduce((s, a) => s + a.mwp, 0),
      frozenMwp: approved.reduce((s, a) => s + (a.remaining_mwp ?? a.mwp), 0),
    };
  }, [all, waiting]);
  const current = view ? groups[view] : [];

  return (
    <div className="space-y-4">
      <PageHeader title="Order approvals"
        subtitle="TC Ordering requests approval for a month's module order; TC Head approves or returns it. An approved quantity stays frozen in its month until its PO is in SAP." />
      {error && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-[12px] text-[var(--status-critical-fg)]">{error}</p>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KPITile icon={Inbox} label="Waiting for me" value={String(groups.waiting.length)} loading={!all}
          tone={groups.waiting.length ? 'watch' : 'neutral'} selected={view === 'waiting'} onClick={() => setView('waiting')}
          subtext={isApprover ? 'Requests you can decide' : 'You are not an approver'} />
        <KPITile icon={Clock} label="Pending" value={String(groups.pending.length)} loading={!all}
          selected={view === 'pending'} onClick={() => setView('pending')}
          subtext={`${mw(groups.pendingMwp)} MWp awaiting a decision`} />
        <KPITile icon={Lock} label="Approved · frozen" value={String(groups.approved.length)} loading={!all}
          tone={groups.approved.length ? 'done' : 'neutral'} selected={view === 'approved'} onClick={() => setView('approved')}
          subtext={`${mw(groups.frozenMwp)} MWp held in its month until the PO`} />
        <KPITile icon={Archive} label="Closed" value={String(groups.closed.length)} loading={!all}
          selected={view === 'closed'} onClick={() => setView('closed')} subtext="Ordered in SAP, returned or cancelled" />
      </div>

      <div className="bento-card overflow-x-auto p-0">
        {!all || !view ? <div className="flex justify-center py-12"><Loader size="md" label="Loading approvals…" /></div>
          : current.length === 0 ? (
            <div className="flex flex-col items-center gap-1.5 px-4 py-12 text-center">
              <CheckCircle2 className="h-6 w-6 text-muted-foreground" aria-hidden />
              <p className="text-[13px] font-medium text-foreground">
                {view === 'waiting' ? 'Nothing is waiting for your approval' : view === 'pending' ? 'No requests pending'
                  : view === 'approved' ? 'Nothing approved and frozen' : 'No closed requests yet'}
              </p>
              {view === 'waiting' && !isApprover && (
                <p className="max-w-md text-[12px] text-muted-foreground">Approvers hold the TC Head role (Admin › Users & roles) or are in the TC Head group (Email notifications › Distribution groups).</p>
              )}
              {view === 'pending' && (
                <p className="max-w-md text-[12px] text-muted-foreground">TC Ordering raises a request from the Ordering Schedule: click a month's MWp, then Request approval.</p>
              )}
            </div>
          ) : (
            <table className="w-full min-w-[900px] text-[12px]">
              <thead className="border-b border-border bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold">
                  <th>Project</th><th>Month</th><th className="text-right">MWp</th><th>Status</th><th>Schedule risk</th><th>Requested</th><th>Decision</th><th />
                </tr>
              </thead>
              <tbody>
                {current.map(a => {
                  const warn = a.basis?.warnings ?? [];
                  return (
                    <tr key={a.id} className="border-b border-[var(--border-subtle)] align-top last:border-0 hover:bg-[var(--surface-sunken)]">
                      <td className="px-3 py-2.5 font-semibold text-foreground">{a.project_name}</td>
                      <td className="whitespace-nowrap px-3 py-2.5">{a.month}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        {mw(a.mwp)}
                        {a.status === 'approved' && a.remaining_mwp != null && a.remaining_mwp < a.mwp && (
                          <span className="block text-[11px] text-muted-foreground">{mw(a.remaining_mwp)} still frozen</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2.5"><StatusPill tone={APPROVAL_META[a.status].tone}>{APPROVAL_META[a.status].label}</StatusPill></td>
                      <td className="max-w-[280px] px-3 py-2.5">
                        {!a.basis || !Object.keys(a.basis).length ? <span className="text-muted-foreground">—</span>
                          : warn.length ? <span className="text-[var(--status-risk-fg)]" title={warn.join('\n')}>{warn[0]}{warn.length > 1 && ` (+${warn.length - 1})`}</span>
                            : <span className="text-[var(--status-healthy-fg)]">None</span>}
                      </td>
                      <td className="px-3 py-2.5 text-muted-foreground">{a.requested_by}<span className="block text-[11px]">{fmtWhen(a.requested_at)}</span></td>
                      <td className="px-3 py-2.5 text-muted-foreground">
                        {a.decided_by ? <>{a.decided_by}<span className="block text-[11px]">{fmtWhen(a.decided_at)}</span></> : '—'}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <button type="button" className={a.can_decide ? btn.primary : btn.secondary} onClick={() => setOpen(a)}>
                          {a.can_decide ? 'Review and decide' : 'View'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
      </div>
      <ApprovalDialog
        target={open ? { mapping: { id: open.mapping_id, project_name: open.project_name ?? '' } as unknown as ModuleProject, month: open.month, id: open.id } : null}
        onClose={() => setOpen(null)} onChanged={() => setKey(k => k + 1)} />
    </div>
  );
}

/* /approvals - the same view on its own, for links from emails and the
   Ordering Schedule's Approvals button. */
export default function ApprovalsPage() {
  const { user, homeFor } = useAuth();
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:py-8">
        <Link to={user ? homeFor(user, null) : '/workspaces'} className="mb-3 inline-flex items-center gap-1 rounded text-[12px] font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
          <ArrowLeft className="h-3.5 w-3.5" />Back to Akasha
        </Link>
        <ApprovalsView />
      </div>
    </main>
  );
}
