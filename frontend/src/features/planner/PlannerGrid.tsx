import React, { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowUpDown, Check, X, Calendar, AlertTriangle } from 'lucide-react';
import { cx } from '../../components/ui/primitives/cx';
import { MiniMeter, StatusDot, type Tone } from '../../components/ui/primitives';
import { formatProjectName } from '../../lib/projectName';
import { useProjectLink } from '../capacity/useProjectLink';
import type { PlannerProject, BasisKey } from './types';
import { monthLabel } from './types';

/* Rows = projects, columns = months. A cell is "plan · done" for that month.
   Cell tone is a rule, not a colour choice:
     past month, done ≥ plan       → healthy
     past month, done < plan       → critical, and the shortfall is written in
     current month                 → watch outline (open)
     future month with a plan      → neutral outline
     nothing planned or done       → blank
   "Behind" (row leader) is cumulative plan through this month minus cumulative
   done — computed once on the server, shown as a count of blocks. */

type SortKey = 'behind' | 'next_due' | 'pct' | 'name';

/* A fact as a small tinted pill instead of bare text — gives each one a
   boundary to scan, without inventing a new colour: tone is one of the
   reserved status triads, or plain neutral when the fact carries no status. */
const Chip = ({ tone, children }: { tone?: Extract<Tone, 'critical' | 'healthy' | 'watch'>; children: React.ReactNode }) => (
  <span className={cx('rounded-md px-1.5 py-0.5 text-[10.5px] font-medium leading-none',
    tone === 'critical' ? 'bg-status-critical-bg text-status-critical-fg'
      : tone === 'healthy' ? 'bg-status-healthy-bg text-status-healthy-fg'
      : tone === 'watch' ? 'bg-status-watch-bg text-status-watch-fg'
      : 'bg-surface-sunken text-fg-secondary')}>
    {children}
  </span>
);

const LEADER_W = 300;   // sticky project column
const DONE_W = 72;      // sticky % complete column
const BEHIND_W = 60;

const SORTS: { key: SortKey; label: string }[] = [
  { key: 'behind', label: 'Behind plan' }, { key: 'next_due', label: 'Next due' }, { key: 'pct', label: '% complete' }, { key: 'name', label: 'Name' },
];

export default function PlannerGrid({ projects, months, today, basis }: {
  projects: PlannerProject[]; months: string[]; today: string; basis: BasisKey;
}) {
  const { href, open } = useProjectLink();
  const [sort, setSort] = useState<SortKey>('behind');
  const [selectedCell, setSelectedCell] = useState<{ p: PlannerProject, m: string } | null>(null);

  const rows = useMemo(() => {
    const r = [...projects];
    const cmp: Record<SortKey, (a: PlannerProject, b: PlannerProject) => number> = {
      behind: (a, b) => b.behind - a.behind || (a.next_due ?? '9999').localeCompare(b.next_due ?? '9999'),
      next_due: (a, b) => (a.next_due ?? '9999').localeCompare(b.next_due ?? '9999') || b.behind - a.behind,
      pct: (a, b) => (a.summary?.pct_complete ?? -1) - (b.summary?.pct_complete ?? -1),
      name: (a, b) => (a.name ?? '').localeCompare(b.name ?? ''),
    };
    r.sort((a, b) => Number(a.not_applicable) - Number(b.not_applicable) || cmp[sort](a, b));
    return r;
  }, [projects, sort]);

  const colTotals = useMemo(() => months.map(m => projects.reduce((acc, p) => {
    const c = p.monthly[m]; if (!c) return acc;
    return { plan: acc.plan + c[basis], done: acc.done + c.completed };
  }, { plan: 0, done: 0 })), [projects, months, basis]);

  const cellClass = (m: string, plan: number, done: number) => {
    if (!plan && !done) return 'text-fg-disabled';
    if (m < today) return done >= plan ? 'border-status-healthy-border bg-status-healthy-bg text-status-healthy-fg' : 'border-status-critical-border bg-status-critical-bg text-status-critical-fg';
    if (m === today) return 'border-status-watch-border bg-status-watch-bg text-status-watch-fg';
    return 'border-border-default text-fg-secondary';
  };

  return (
    <>
      <div className="flex flex-col">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 text-[11px] text-fg-tertiary">
          <ArrowUpDown className="h-3 w-3" /> Sort
          {SORTS.map(s => (
            <button key={s.key} onClick={() => setSort(s.key)} aria-pressed={sort === s.key}
              className={cx('rounded px-2 py-0.5 transition-colors', sort === s.key ? 'bg-brand-blue/10 font-semibold text-brand-blue' : 'hover:bg-surface-sunken hover:text-fg-primary')}>
              {s.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 text-[10.5px] text-fg-tertiary">
          <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm border border-status-healthy-border bg-status-healthy-bg" />met</span>
          <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm border border-status-critical-border bg-status-critical-bg" />short</span>
          <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm border border-status-watch-border bg-status-watch-bg" />this month</span>
          <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm border border-border-default" />planned</span>
          <span>cell = plan · done</span>
        </div>
      </div>

      <div className="custom-scrollbar overflow-x-auto rounded-lg border border-border-subtle">
        <table className="w-full table-fixed border-separate border-spacing-0 text-[11.5px]" style={{ minWidth: LEADER_W + DONE_W + BEHIND_W + months.length * 60 }}>
          <colgroup>
            <col style={{ width: LEADER_W }} />
            <col style={{ width: DONE_W }} />
            <col style={{ width: BEHIND_W }} />
            {months.map(m => <col key={m} />)}
          </colgroup>
          <thead>
            <tr>
              <th className="sticky left-0 z-20 border-b border-r border-border-subtle bg-surface-1 px-3 py-2 text-left text-[10.5px] font-semibold uppercase tracking-wider text-fg-tertiary">Project</th>
              <th className="sticky z-20 border-b border-border-subtle bg-surface-1 px-2 py-2 text-right text-[10.5px] font-semibold uppercase tracking-wider text-fg-tertiary" style={{ left: LEADER_W }}>Done</th>
              <th className="sticky z-20 border-b border-r border-border-subtle bg-surface-1 px-2 py-2 text-right text-[10.5px] font-semibold uppercase tracking-wider text-fg-tertiary" style={{ left: LEADER_W + DONE_W }}>Behind</th>
              {months.map(m => (
                <th key={m} className={cx('border-b border-border-subtle px-1 py-2 text-center text-[10.5px] font-semibold uppercase tracking-wider',
                  m === today ? 'bg-status-watch-bg text-status-watch-fg' : 'bg-surface-1 text-fg-tertiary')}>
                  {monthLabel(m)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(p => {
              const s = p.summary;
              const slip = p.ecod.slip_days;
              const pctDel = p.ordered_cr ? Math.round((p.delivered_cr / p.ordered_cr) * 100) : null;
              return (
                <tr key={p.project_id} className={cx('group', p.not_applicable && 'opacity-60')}>
                  <td className="sticky left-0 z-10 border-b border-border-subtle bg-surface-1 px-3 py-3 group-hover:bg-surface-sunken">
                    {/* Facts as pill chips, not run-on text: each one a discrete,
                        scannable unit. Colour only on the two chips that actually
                        carry a status (ECOD, TC); the rest are neutral. */}
                    <div className="flex items-baseline justify-between gap-2">
                      <a href={href(p.project_id, 'installation')} onClick={e => { e.preventDefault(); open(p.project_id, 'installation'); }}
                        className="min-w-0 truncate text-[13px] font-semibold text-fg-primary hover:text-brand-blue" title={p.name}>
                        {formatProjectName(p.name)}
                      </a>
                      {p.capacity_mwac > 0 && <span className="shrink-0 text-[11px] tabular-nums text-fg-tertiary">{p.capacity_mwac} MW</span>}
                    </div>
                    {p.not_applicable ? (
                      <div className="mt-1.5 text-[11px] text-fg-tertiary">No module activities in P6</div>
                    ) : (
                      <div className="mt-1.5 flex flex-wrap items-center gap-1">
                        <Chip>{s!.completed}/{s!.planned} blk</Chip>
                        {slip == null ? null : slip === 0 ? <Chip tone="healthy">ECOD on plan</Chip>
                          : <Chip tone={slip > 0 ? 'critical' : 'healthy'}>ECOD {slip > 0 ? '+' : '−'}{Math.abs(slip)}d</Chip>}
                        <Chip>{pctDel == null ? 'SAP —' : `SAP ${pctDel}%`}</Chip>
                        {p.tc.lines > 0 && <Chip tone={p.tc.charged < p.tc.lines ? 'watch' : undefined}>TC {p.tc.charged}/{p.tc.lines}</Chip>}
                      </div>
                    )}
                  </td>
                  <td style={{ left: LEADER_W }} className="sticky z-10 border-b border-border-subtle bg-surface-1 px-2 py-3 text-right group-hover:bg-surface-sunken">
                    {!p.not_applicable && (
                      <>
                        <div className={cx('text-[16px] font-bold tabular-nums leading-none', s!.pct_complete >= 100 ? 'text-status-done-fg' : 'text-fg-primary')}>{Math.round(s!.pct_complete)}%</div>
                        <MiniMeter pct={s!.pct_complete} tone={s!.pct_complete >= 100 ? 'done' : 'healthy'} className="mt-1.5" />
                      </>
                    )}
                  </td>
                  <td style={{ left: LEADER_W + DONE_W }} className="sticky z-10 border-b border-r border-border-subtle bg-surface-1 px-2 py-3 text-right group-hover:bg-surface-sunken">
                    {p.not_applicable ? <span className="text-fg-tertiary">—</span>
                      : p.behind > 0
                        ? <span className="inline-flex min-w-[28px] items-center justify-center rounded-full bg-status-critical-bg px-2 py-1 text-[13px] font-bold tabular-nums text-status-critical-fg">{p.behind}</span>
                        : <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-status-healthy-bg text-status-healthy-fg"><Check className="h-3.5 w-3.5" /></span>}
                  </td>
                  {months.map(m => {
                    const c = p.monthly[m];
                    const plan = c ? c[basis] : 0, done = c ? c.completed : 0;
                    const short = m < today && plan > done ? plan - done : 0;
                    return (
                      <td key={m} className="border-b border-border-subtle p-[3px] text-center">
                        {plan || done ? (
                          <button 
                            type="button"
                            onClick={() => setSelectedCell({ p, m })}
                            className={cx('flex w-full h-7 items-center justify-center gap-1 rounded border px-1 tabular-nums transition-colors hover:ring-2 hover:ring-brand-blue/50 cursor-pointer', cellClass(m, plan, done))} title={`${monthLabel(m)}: ${plan} planned, ${done} completed${short ? `, ${short} short` : ''}`}>
                            <span className="text-[12px] font-semibold">{plan}</span><span className="opacity-50">·</span><span className="text-[12px]">{done}</span>
                            {short > 0 && <span className="ml-0.5 rounded bg-status-critical-solid/15 px-1 text-[9.5px] font-semibold leading-4">−{short}</span>}
                          </button>
                        ) : <span className="text-fg-disabled/60">·</span>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <td className="sticky left-0 z-10 border-r border-t border-border-subtle bg-surface-1 px-3 py-2 text-[10.5px] font-semibold uppercase tracking-wider text-fg-tertiary">Portfolio · plan · done</td>
              <td style={{ left: LEADER_W }} className="sticky z-10 border-t border-border-subtle bg-surface-1 px-2 py-2" />
              <td style={{ left: LEADER_W + DONE_W }} className="sticky z-10 border-r border-t border-border-subtle bg-surface-1 px-2 py-2 text-right tabular-nums text-fg-tertiary">{projects.reduce((a, p) => a + p.behind, 0)}</td>
              {colTotals.map((t, i) => (
                <td key={months[i]} className={cx('border-t border-border-subtle px-1 py-2 text-center tabular-nums', months[i] === today ? 'bg-status-watch-bg text-status-watch-fg font-semibold' : 'text-fg-secondary')}>
                  {t.plan || t.done ? <><span className="font-medium">{t.plan}</span><span className="opacity-60"> · </span>{t.done}</> : <span className="text-fg-disabled">·</span>}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
      <AnimatePresence>
        {selectedCell && (
          <CellDetailsModal 
            project={selectedCell.p} 
            month={selectedCell.m} 
            onClose={() => setSelectedCell(null)} 
            today={today}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function CellDetailsModal({ project, month, onClose, today }: { project: PlannerProject; month: string; onClose: () => void; today: string }) {
  const c = project.monthly[month] || { planned: 0, baseline: 0, completed: 0, activities: [] };
  const plan = c.planned || 0;
  const done = c.completed || 0;
  const short = month < today && plan > done ? plan - done : 0;
  
  const pendingSap = Math.max(0, project.ordered_cr - project.delivered_cr);
  const pctDel = project.ordered_cr ? Math.round((project.delivered_cr / project.ordered_cr) * 100) : 0;

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        onClick={(e) => e.stopPropagation()}
        className="relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface-1 shadow-2xl"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-border-subtle bg-surface-sunken px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold text-fg-primary">{formatProjectName(project.name)}</h3>
            <p className="mt-0.5 flex items-center gap-1 text-xs text-fg-tertiary">
              <Calendar className="h-3 w-3" /> {monthLabel(month)}
            </p>
          </div>
          <button onClick={onClose} className="rounded p-1 text-fg-tertiary transition-colors hover:bg-surface-2 hover:text-fg-primary">
            <X className="h-4 w-4" />
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg border border-border-default bg-surface-sunken p-3">
                <div className="mb-1 text-[11px] font-medium uppercase tracking-wider text-fg-tertiary">Baseline</div>
                <div className="text-xl font-semibold tabular-nums text-fg-primary">{c.baseline}</div>
              </div>
              <div className="rounded-lg border border-border-default bg-surface-sunken p-3">
                <div className="mb-1 text-[11px] font-medium uppercase tracking-wider text-fg-tertiary">Planned</div>
                <div className="text-xl font-semibold tabular-nums text-fg-primary">{plan}</div>
              </div>
              <div className="rounded-lg border border-status-healthy-border bg-status-healthy-bg p-3">
                <div className="mb-1 text-[11px] font-medium uppercase tracking-wider text-status-healthy-fg">Actual (Done)</div>
                <div className="text-xl font-semibold tabular-nums text-status-healthy-fg">{done}</div>
              </div>
              <div className={cx('rounded-lg border p-3', short > 0 ? 'border-status-critical-border bg-status-critical-bg' : 'border-border-default bg-surface-sunken')}>
                <div className={cx('mb-1 text-[11px] font-medium uppercase tracking-wider', short > 0 ? 'text-status-critical-fg' : 'text-fg-tertiary')}>
                  Forecast / Shortfall
                </div>
                <div className={cx('flex items-center gap-2 text-xl font-semibold tabular-nums', short > 0 ? 'text-status-critical-fg' : 'text-fg-primary')}>
                  {short > 0 ? `-${short}` : '0'}
                  {short > 0 && <AlertTriangle className="h-4 w-4" />}
                </div>
              </div>
            </div>
            
            <div className="flex flex-col overflow-hidden rounded-lg border border-border-default bg-surface-1 shadow-sm">
              <div className="border-b border-border-default bg-surface-sunken p-3">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-fg-secondary">Block Details</h4>
              </div>
              {c.activities && c.activities.length > 0 ? (
                <div className="w-full overflow-x-auto custom-scrollbar">
                  <table className="w-full whitespace-nowrap text-left text-xs">
                    <thead className="bg-surface-sunken/50 text-fg-tertiary">
                      <tr>
                        <th className="border-b border-border-subtle px-4 py-2.5 font-medium">Block Name</th>
                        <th className="border-b border-border-subtle px-4 py-2.5 font-medium">Status</th>
                        <th className="border-b border-border-subtle px-4 py-2.5 font-medium">Baseline</th>
                        <th className="border-b border-border-subtle px-4 py-2.5 font-medium">Planned</th>
                        <th className="border-b border-border-subtle px-4 py-2.5 font-medium">Actual</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle">
                      {c.activities.map((act, i) => (
                        <tr key={i} className="transition-colors hover:bg-surface-sunken/30">
                          <td className="px-4 py-2.5 font-medium text-fg-primary">{act.name}</td>
                          <td className="px-4 py-2.5">
                            <span className={cx('inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium', act.status === 'Completed' ? 'border-status-healthy-border bg-status-healthy-bg text-status-healthy-fg' : 'border-border-default bg-surface-2 text-fg-secondary')}>
                              {act.status}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 tabular-nums text-fg-secondary">{act.baseline || '—'}</td>
                          <td className="px-4 py-2.5 tabular-nums text-fg-secondary">{act.planned || '—'}</td>
                          <td className="px-4 py-2.5 font-medium tabular-nums text-status-healthy-fg">{act.actual || <span className="font-normal text-fg-disabled">—</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-4 text-xs italic text-fg-tertiary">No specific block activities recorded for this month.</div>
              )}
            </div>
          
          <div className="rounded-lg border border-border-subtle bg-surface-1 p-3 shadow-sm">
            <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-secondary">SAP Pending</h4>
            <div className="space-y-3">
              <div>
                <div className="mb-1 flex justify-between text-xs">
                  <span className="text-fg-tertiary">Ordered CR</span>
                  <span className="font-medium tabular-nums text-fg-primary">{project.ordered_cr}</span>
                </div>
                <div className="mb-1 flex justify-between text-xs">
                  <span className="text-fg-tertiary">Delivered CR</span>
                  <span className="font-medium tabular-nums text-fg-primary">{project.delivered_cr}</span>
                </div>
                <div className="mt-2 flex justify-between border-t border-border-subtle pt-2 text-xs">
                  <span className="font-medium text-fg-secondary">Pending from SAP</span>
                  <span className={cx('font-semibold tabular-nums', pendingSap > 0 ? 'text-status-risk-solid' : 'text-fg-primary')}>
                    {pendingSap > 0 ? pendingSap.toFixed(1) : 0}
                  </span>
                </div>
              </div>
              
              {project.ordered_cr > 0 && (
                <div className="pt-1">
                  <div className="mb-1 flex justify-between text-[10px]">
                    <span className="text-fg-tertiary">Delivery Progress</span>
                    <span className="font-medium text-fg-secondary">{pctDel}%</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
                    <div 
                      className="h-full rounded-full bg-brand-blue transition-all" 
                      style={{ width: `${Math.min(pctDel, 100)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
        </div>
      </motion.div>
    </div>,
    document.body
  );
}
