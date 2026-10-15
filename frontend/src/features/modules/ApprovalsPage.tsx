/* /approvals - module order approvals in one place. TC Head opens it to see
   what is waiting for their decision; everyone sees the open and decided
   requests with their history. Reached from the Ordering Schedule
   ("Approvals") and the approval email. */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Inbox } from 'lucide-react';
import { Loader, StatusPill, cx } from '../../components/ui/primitives';
import { fmtWhen, btn } from '../admin/adminApi';
import { APPROVAL_META, ApprovalDialog, useApprovalRole } from './OrderApproval';
import type { OrderApprovalRow } from './OrderApproval';
import type { ModuleProject } from './types';
import { useAuth } from '../../context/AuthContext';

type Tab = 'waiting' | 'open' | 'decided';
const TABS: { id: Tab; label: string; path: string }[] = [
  { id: 'waiting', label: 'Waiting for me', path: '/waiting' },
  { id: 'open', label: 'All open', path: '?status=pending,approved' },
  { id: 'decided', label: 'Closed', path: '?status=returned,cancelled,ordered' },
];

async function load(path: string): Promise<OrderApprovalRow[]> {
  const res = await fetch(`/akasha/api/module-approvals${path}`, { credentials: 'same-origin' });
  const body = await res.json().catch(() => ([]));
  if (!res.ok) throw new Error((body as { detail?: string }).detail || `Request failed (${res.status})`);
  return body as OrderApprovalRow[];
}

const mw = (v: number) => v.toLocaleString('en-IN', { maximumFractionDigits: 1 });

export default function ApprovalsPage() {
  const { user, homeFor } = useAuth();
  const [key, setKey] = useState(0);
  const role = useApprovalRole(key);
  const [tab, setTab] = useState<Tab | null>(null);
  const [rows, setRows] = useState<OrderApprovalRow[] | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<OrderApprovalRow | null>(null);

  // Approvers land on what waits for them; everyone else on the open list.
  useEffect(() => {
    if (tab === null && role) setTab(role.waiting > 0 || role.approve.all || role.approve.portfolios.length ? 'waiting' : 'open');
  }, [role, tab]);
  const refresh = useCallback(() => {
    if (!tab) return;
    setRows(null); setError('');
    load(TABS.find(t => t.id === tab)!.path).then(setRows).catch(e => setError((e as Error).message));
  }, [tab]);
  useEffect(refresh, [refresh, key]);

  const isApprover = !!role && (role.superadmin || role.approve.all || role.approve.portfolios.length > 0);
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:py-8">
        <Link to={user ? homeFor(user, null) : '/workspaces'} className="mb-3 inline-flex items-center gap-1 rounded text-[12px] font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
          <ArrowLeft className="h-3.5 w-3.5" />Back to Akasha
        </Link>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-[17px] font-semibold text-foreground">Module order approvals</h1>
            <p className="max-w-3xl text-[12.5px] text-muted-foreground">
              TC Ordering requests approval for a month's order from the Ordering Schedule; TC Head approves or returns it.
              An approved quantity is frozen in its month until its PO is in SAP.
              {role && !isApprover && ' You can see every request; deciding is for the approvers (TC Head).'}
            </p>
          </div>
          <div role="tablist" aria-label="Which approvals" className="inline-flex rounded-lg border border-border p-0.5">
            {TABS.map(t => (
              <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
                className={cx('inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-[12px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
                  tab === t.id ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground')}>
                {t.label}
                {t.id === 'waiting' && (role?.waiting ?? 0) > 0 && <span className="rounded-full bg-[var(--status-watch-solid)] px-1.5 text-[10px] font-bold text-white">{role?.waiting}</span>}
              </button>
            ))}
          </div>
        </div>

        {error && <p role="alert" className="mb-3 rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-[12px] text-[var(--status-critical-fg)]">{error}</p>}
        <div className="bento-card overflow-x-auto p-0">
          {!rows ? <div className="flex justify-center py-12"><Loader size="md" label="Loading approvals…" /></div>
            : rows.length === 0 ? (
              <div className="flex flex-col items-center gap-1.5 px-4 py-12 text-center">
                <Inbox className="h-6 w-6 text-muted-foreground" aria-hidden />
                <p className="text-[13px] font-medium text-foreground">
                  {tab === 'waiting' ? 'Nothing is waiting for your approval' : tab === 'open' ? 'No open requests' : 'No closed requests yet'}
                </p>
                {tab === 'waiting' && !isApprover && (
                  <p className="max-w-md text-[12px] text-muted-foreground">You are not an approver. Approvers hold the TC Head role (Admin › Users & roles) or are in the TC Head group (Email notifications › Distribution groups).</p>
                )}
              </div>
            ) : (
              <table className="w-full min-w-[860px] text-[12px]">
                <thead className="border-b border-border bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                  <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold">
                    <th>Project</th><th>Month</th><th className="text-right">MWp</th><th>Status</th><th>Schedule risk</th><th>Requested</th><th>Decision</th><th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map(a => {
                    const warn = a.basis?.warnings ?? [];
                    return (
                      <tr key={a.id} className="border-b border-[var(--border-subtle)] align-top last:border-0">
                        <td className="px-3 py-2 font-semibold text-foreground">{a.project_name}</td>
                        <td className="whitespace-nowrap px-3 py-2">{a.month}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{mw(a.mwp)}</td>
                        <td className="whitespace-nowrap px-3 py-2"><StatusPill tone={APPROVAL_META[a.status].tone}>{APPROVAL_META[a.status].label}</StatusPill></td>
                        <td className="max-w-[260px] px-3 py-2">
                          {!a.basis || !Object.keys(a.basis).length ? <span className="text-muted-foreground">—</span>
                            : warn.length ? <span className="text-[var(--status-risk-fg)]" title={warn.join('\n')}>{warn[0]}{warn.length > 1 && ` (+${warn.length - 1})`}</span>
                              : <span className="text-[var(--status-healthy-fg)]">None</span>}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">{a.requested_by}<span className="block text-[11px]">{fmtWhen(a.requested_at)}</span></td>
                        <td className="px-3 py-2 text-muted-foreground">{a.decided_by ? <>{a.decided_by}<span className="block text-[11px]">{fmtWhen(a.decided_at)}</span></> : '—'}</td>
                        <td className="px-3 py-2 text-right">
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
      </div>
      <ApprovalDialog
        target={open ? { mapping: { id: open.mapping_id, project_name: open.project_name ?? '' } as unknown as ModuleProject, month: open.month, id: open.id } : null}
        onClose={() => setOpen(null)} onChanged={() => setKey(k => k + 1)} />
    </main>
  );
}
