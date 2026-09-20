import React, { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowUpDown, Check, X, Calendar, AlertTriangle, ChevronDown, ChevronUp, Layers } from 'lucide-react';
import { cx } from '../../components/ui/primitives/cx';
import { MiniMeter, StatusDot, type Tone } from '../../components/ui/primitives';
import { formatProjectName } from '../../lib/projectName';
import { useProjectLink } from '../capacity/useProjectLink';
import type { PlannerProject, BasisKey, UnitKey } from './types';
import { monthLabel } from './types';

/* Rows = projects, columns = months. A cell is "plan · done" for that month.
   Cell tone is a rule, not a colour choice:
     past month, done ≥ plan       → healthy
     past month, done < plan       → critical, and the shortfall is written in
     current month                 → watch outline (open)
     future month with a plan      → neutral outline
     nothing planned or done       → blank
   "Behind" (row leader) is cumulative plan through this month minus cumulative
   done — computed once on the server, shown as a count of blocks or modules. */

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

export default function PlannerGrid({ projects, months, today, basis, unit }: {
  projects: PlannerProject[]; months: string[]; today: string; basis: BasisKey; unit: UnitKey;
}) {
  const { href, open } = useProjectLink();
  const [sort, setSort] = useState<SortKey>('behind');
  const [selectedCell, setSelectedCell] = useState<{ p: PlannerProject, m: string } | null>(null);

  const isModules = unit === 'modules';
  const unitLabel = isModules ? 'mod' : 'blk';

  const rows = useMemo(() => {
    const r = [...projects];
    const cmp: Record<SortKey, (a: PlannerProject, b: PlannerProject) => number> = {
      behind: (a, b) => (isModules ? b.modules_behind - a.modules_behind : b.behind - a.behind) || (a.next_due ?? '9999').localeCompare(b.next_due ?? '9999'),
      next_due: (a, b) => (a.next_due ?? '9999').localeCompare(b.next_due ?? '9999') || (isModules ? b.modules_behind - a.modules_behind : b.behind - a.behind),
      pct: (a, b) => (a.summary?.pct_complete ?? -1) - (b.summary?.pct_complete ?? -1),
      name: (a, b) => (a.name ?? '').localeCompare(b.name ?? ''),
    };
    r.sort((a, b) => Number(a.not_applicable) - Number(b.not_applicable) || cmp[sort](a, b));
    return r;
  }, [projects, sort, isModules]);

  const colTotals = useMemo(() => months.map(m => projects.reduce((acc, p) => {
    const c = p.monthly[m]; if (!c) return acc;
    if (isModules) {
      return { plan: acc.plan + c.modules_planned, done: acc.done + c.modules_completed };
    }
    return { plan: acc.plan + c[basis], done: acc.done + c.completed };
  }, { plan: 0, done: 0 })), [projects, months, basis, isModules]);

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
            <span className="rounded bg-surface-sunken px-1.5 py-0.5 font-medium">cell = plan · done <span className="text-brand-blue">({isModules ? 'modules' : 'blocks'})</span></span>
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
                const displayPct = isModules ? (s?.modules_pct ?? 0) : (s?.pct_complete ?? 0);
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
                          {isModules
                            ? <Chip>{Math.round(s!.modules_completed)}/{Math.round(s!.modules_scope)} mod</Chip>
                            : <Chip>{s!.completed}/{s!.planned} blk</Chip>}
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
                          <div className={cx('text-[16px] font-bold tabular-nums leading-none', displayPct >= 100 ? 'text-status-done-fg' : 'text-fg-primary')}>{Math.round(displayPct)}%</div>
                          <MiniMeter pct={displayPct} tone={displayPct >= 100 ? 'done' : 'healthy'} className="mt-1.5" />
                        </>
                      )}
                    </td>
                    <td style={{ left: LEADER_W + DONE_W }} className="sticky z-10 border-b border-r border-border-subtle bg-surface-1 px-2 py-3 text-right group-hover:bg-surface-sunken">
                      {p.not_applicable ? <span className="text-fg-tertiary">—</span>
                        : (isModules ? p.modules_behind : p.behind) > 0
                          ? <span className="inline-flex min-w-[28px] items-center justify-center rounded-full bg-status-critical-bg px-2 py-1 text-[13px] font-bold tabular-nums text-status-critical-fg">{isModules ? Math.round(p.modules_behind) : p.behind}</span>
                          : <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-status-healthy-bg text-status-healthy-fg"><Check className="h-3.5 w-3.5" /></span>}
                    </td>
                    {months.map(m => {
                      const c = p.monthly[m];
                      let plan: number, done: number;
                      if (isModules) {
                        plan = c ? Math.round(c.modules_planned) : 0;
                        done = c ? Math.round(c.modules_completed) : 0;
                      } else {
                        plan = c ? c[basis] : 0;
                        done = c ? c.completed : 0;
                      }
                      const short = m < today && plan > done ? plan - done : 0;
                      return (
                        <td key={m} className="border-b border-border-subtle p-[3px] text-center">
                          {plan || done ? (
                            <button
                              type="button"
                              onClick={() => setSelectedCell({ p, m })}
                              className={cx('flex w-full h-7 items-center justify-center gap-1 rounded border px-1 tabular-nums transition-colors hover:ring-2 hover:ring-brand-blue/50 cursor-pointer', cellClass(m, plan, done))} title={`${monthLabel(m)}: ${plan} ${isModules ? 'modules' : 'blocks'} planned, ${done} completed${short ? `, ${short} short` : ''}`}>
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
                <td className="sticky left-0 z-10 border-r border-t border-border-subtle bg-surface-1 px-3 py-2 text-[10.5px] font-semibold uppercase tracking-wider text-fg-tertiary">Portfolio · plan · done ({isModules ? 'modules' : 'blocks'})</td>
                <td style={{ left: LEADER_W }} className="sticky z-10 border-t border-border-subtle bg-surface-1 px-2 py-2" />
                <td style={{ left: LEADER_W + DONE_W }} className="sticky z-10 border-r border-t border-border-subtle bg-surface-1 px-2 py-2 text-right tabular-nums text-fg-tertiary">
                  {isModules ? Math.round(projects.reduce((a, p) => a + p.modules_behind, 0)) : projects.reduce((a, p) => a + p.behind, 0)}
                </td>
                {colTotals.map((t, i) => (
                  <td key={months[i]} className={cx('border-t border-border-subtle px-1 py-2 text-center tabular-nums', months[i] === today ? 'bg-status-watch-bg text-status-watch-fg font-semibold' : 'text-fg-secondary')}>
                    {t.plan || t.done ? <><span className="font-medium">{isModules ? Math.round(t.plan) : t.plan}</span><span className="opacity-60"> · </span>{isModules ? Math.round(t.done) : t.done}</> : <span className="text-fg-disabled">·</span>}
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
            unit={unit}
          />
        )}
      </AnimatePresence>
    </>
  );
}

/* ─── Status group component for the redesigned modal ─── */
function StatusGroup({ title, tone, activities, defaultOpen = false }: {
  title: string;
  tone: 'critical' | 'healthy' | 'watch' | 'neutral';
  activities: { name: string; status: string; baseline_start: string | null; baseline_finish: string | null; forecast_start: string | null; forecast_finish: string | null; actual_start: string | null; actual_finish: string | null; modules_scope: number; modules_actual: number }[];
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  if (activities.length === 0) return null;

  const toneClasses = {
    critical: 'border-status-critical-border bg-status-critical-bg/50 text-status-critical-fg',
    healthy: 'border-status-healthy-border bg-status-healthy-bg/50 text-status-healthy-fg',
    watch: 'border-status-watch-border bg-status-watch-bg/50 text-status-watch-fg',
    neutral: 'border-border-default bg-surface-sunken text-fg-secondary',
  };
  const badgeClasses = {
    critical: 'bg-status-critical-bg text-status-critical-fg',
    healthy: 'bg-status-healthy-bg text-status-healthy-fg',
    watch: 'bg-status-watch-bg text-status-watch-fg',
    neutral: 'bg-surface-2 text-fg-secondary',
  };

  return (
    <div className={cx('overflow-hidden rounded-lg border', toneClasses[tone])}>
      <button
        type="button"
        onClick={() => setIsOpen(o => !o)}
        className="flex w-full items-center justify-between px-3 py-2.5 text-left transition-colors hover:opacity-80"
      >
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-semibold">{title}</span>
          <span className={cx('rounded-full px-2 py-0.5 text-[10px] font-bold', badgeClasses[tone])}>{activities.length}</span>
        </div>
        {isOpen ? <ChevronUp className="h-3.5 w-3.5 opacity-60" /> : <ChevronDown className="h-3.5 w-3.5 opacity-60" />}
      </button>
      {isOpen && (
        <div className="border-t border-inherit">
          <table className="w-full whitespace-nowrap text-left text-xs">
            <thead className="bg-black/5 text-fg-tertiary dark:bg-white/5">
              <tr>
                <th className="border-b border-inherit px-3 py-2 font-medium">Block Name</th>
                <th className="border-b border-inherit px-3 py-2 font-medium">Modules</th>
                <th className="border-b border-inherit px-3 py-2 font-medium">Baseline Start</th>
                <th className="border-b border-inherit px-3 py-2 font-medium">Baseline Finish</th>
                <th className="border-b border-inherit px-3 py-2 font-medium">Start</th>
                <th className="border-b border-inherit px-3 py-2 font-medium">Finish</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-inherit">
              {activities.map((act, i) => (
                <tr key={i} className="transition-colors hover:bg-black/5 dark:hover:bg-white/5">
                  <td className="px-3 py-2 font-medium text-fg-primary">{act.name}</td>
                  <td className="px-3 py-2 tabular-nums">
                    <span className="font-medium text-fg-primary">{act.modules_actual || 0}</span>
                    <span className="text-fg-tertiary"> / {act.modules_scope || 0}</span>
                  </td>
                  <td className="px-3 py-2 tabular-nums text-fg-tertiary">{act.baseline_start || '—'}</td>
                  <td className="px-3 py-2 tabular-nums text-fg-tertiary">{act.baseline_finish || '—'}</td>
                  <td className="px-3 py-2 tabular-nums">
                    {act.actual_start ? (
                      <span className="font-medium text-fg-primary">{act.actual_start}</span>
                    ) : (
                      <span className="text-fg-secondary">{act.forecast_start || '—'}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 tabular-nums">
                    {act.actual_finish ? (
                      <span className="font-medium text-fg-primary">{act.actual_finish}</span>
                    ) : (
                      <span className="text-fg-secondary">{act.forecast_finish || '—'}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CellDetailsModal({ project, month, onClose, today, unit }: { project: PlannerProject; month: string; onClose: () => void; today: string; unit: UnitKey }) {
  const c = project.monthly[month] || { planned: 0, baseline: 0, completed: 0, activities: [], modules_planned: 0, modules_baseline: 0, modules_completed: 0 };
  const [sapOpen, setSapOpen] = useState(false);

  const isModules = unit === 'modules';
  const activities = c.activities || [];

  // Use the temporal buckets for scope/plan to preserve the original cell schedule for the Shortfall calculation.
  const schedPlan = c.planned || 0;
  const schedModPlan = c.modules_planned ? Math.round(c.modules_planned) : 0;

  // For the Compact Stats Row, summarize the exact list of activities shown in this modal
  const listPlan = activities.length;
  const listModPlan = Math.round(activities.reduce((sum, a) => sum + (a.modules_scope || 0), 0));

  const done = activities.filter(a => a.status === 'Completed').length;
  const modDone = Math.round(activities.reduce((sum, a) => sum + (a.modules_actual || 0), 0));

  const short = Math.max(0, schedPlan - done);
  const modShort = Math.max(0, schedModPlan - modDone);

  const pendingSap = Math.max(0, project.ordered_cr - project.delivered_cr);
  const pctDel = project.ordered_cr ? Math.round((project.delivered_cr / project.ordered_cr) * 100) : 0;

  const schedDisplayPlan = isModules ? schedModPlan : schedPlan;
  const displayDone = isModules ? modDone : done;
  const displayShort = isModules ? modShort : short;

  // Group activities by status, priority order
  // When in 'modules' view, we track status based on actual module completion, 
  // since P6 activity status often lags behind the physical modules installed.

  const isModCompleted = (a: typeof activities[0]) => a.modules_scope > 0 && a.modules_actual >= a.modules_scope;
  const isModInProgress = (a: typeof activities[0]) => a.modules_actual > 0 && a.modules_actual < a.modules_scope;
  const isModNotStarted = (a: typeof activities[0]) => a.modules_actual === 0;

  const grouped = {
    behind: activities.filter(a => isModules ? (!isModCompleted(a) && month < today) : (a.status !== 'Completed' && month < today)),
    inProgress: activities.filter(a => isModules ? (isModInProgress(a) && month >= today) : (a.status === 'In Progress' && month >= today)),
    notStarted: activities.filter(a => isModules ? (isModNotStarted(a) && month >= today) : (a.status === 'Not Started' && month >= today)),
    completed: activities.filter(a => isModules ? isModCompleted(a) : (a.status === 'Completed')),
  };

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        onClick={(e) => e.stopPropagation()}
        className="relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface-1 shadow-2xl"
      >
        {/* Header */}
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
            {/* Priority Status Banner */}
            {displayShort > 0 ? (
              <div className="flex items-center gap-3 rounded-lg border border-status-critical-border bg-status-critical-bg px-4 py-3">
                <AlertTriangle className="h-5 w-5 shrink-0 text-status-critical-fg" />
                <div className="flex-1">
                  <div className="text-[13px] font-bold text-status-critical-fg">
                    Behind Plan — {displayShort} {isModules ? 'modules' : 'blocks'} short
                  </div>
                  <div className="mt-0.5 text-[11px] text-status-critical-fg/80">
                    {displayDone} of {schedDisplayPlan} {isModules ? 'modules' : 'blocks'} completed for {monthLabel(month)}
                  </div>
                </div>
              </div>
            ) : month <= today && schedDisplayPlan > 0 ? (
              <div className="flex items-center gap-3 rounded-lg border border-status-healthy-border bg-status-healthy-bg px-4 py-3">
                <Check className="h-5 w-5 shrink-0 text-status-healthy-fg" />
                <div className="flex-1">
                  <div className="text-[13px] font-bold text-status-healthy-fg">On Track</div>
                  <div className="mt-0.5 text-[11px] text-status-healthy-fg/80">
                    All {schedDisplayPlan} {isModules ? 'modules' : 'blocks'} completed for {monthLabel(month)}
                  </div>
                </div>
              </div>
            ) : null}

            {/* SAP Pending — collapsible (Moved to top as requested) */}
            <div className="rounded-lg border border-border-subtle bg-surface-1 shadow-sm">
              <button
                type="button"
                onClick={() => setSapOpen(o => !o)}
                className="flex w-full items-center justify-between px-3 py-2.5 text-left transition-colors hover:bg-surface-sunken/50"
              >
                <h4 className="text-xs font-semibold uppercase tracking-wider text-fg-secondary">SAP Pending</h4>
                <div className="flex items-center gap-2">
                  {!sapOpen && <span className="text-[11px] tabular-nums text-fg-tertiary">{pctDel}% delivered</span>}
                  {sapOpen ? <ChevronUp className="h-3.5 w-3.5 text-fg-tertiary" /> : <ChevronDown className="h-3.5 w-3.5 text-fg-tertiary" />}
                </div>
              </button>
              {sapOpen && (
                <div className="border-t border-border-subtle p-3">
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
              )}
            </div>

            {/* Compact Stats Row */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div className="rounded-lg border border-border-default bg-surface-sunken p-2.5">
                <div className="mb-0.5 text-[10px] font-medium uppercase tracking-wider text-fg-tertiary">Blocks</div>
                <div className="flex items-baseline gap-1">
                  <span className="text-lg font-bold tabular-nums text-fg-primary">{listPlan}</span>
                  <span className="text-[10px] text-fg-tertiary">plan</span>
                  <span className="text-[10px] text-fg-disabled">·</span>
                  <span className="text-lg font-bold tabular-nums text-status-healthy-fg">{done}</span>
                  <span className="text-[10px] text-fg-tertiary">done</span>
                </div>
              </div>
              <div className="rounded-lg border border-border-default bg-surface-sunken p-2.5">
                <div className="mb-0.5 text-[10px] font-medium uppercase tracking-wider text-fg-tertiary">Modules</div>
                <div className="flex items-baseline gap-1">
                  <span className="text-lg font-bold tabular-nums text-fg-primary">{listModPlan}</span>
                  <span className="text-[10px] text-fg-tertiary">scope</span>
                  <span className="text-[10px] text-fg-disabled">·</span>
                  <span className="text-lg font-bold tabular-nums text-status-healthy-fg">{modDone}</span>
                  <span className="text-[10px] text-fg-tertiary">done</span>
                </div>
              </div>
              <div className="rounded-lg border border-border-default bg-surface-sunken p-2.5">
                <div className="mb-0.5 text-[10px] font-medium uppercase tracking-wider text-fg-tertiary">Baseline</div>
                <div className="text-lg font-bold tabular-nums text-fg-primary">{c.baseline} <span className="text-[10px] font-normal text-fg-tertiary">blocks</span></div>
              </div>
              <div className={cx('rounded-lg border p-2.5', short > 0 ? 'border-status-critical-border bg-status-critical-bg' : 'border-border-default bg-surface-sunken')}>
                <div className={cx('mb-0.5 text-[10px] font-medium uppercase tracking-wider', short > 0 ? 'text-status-critical-fg' : 'text-fg-tertiary')}>Shortfall</div>
                <div className="flex items-baseline gap-2">
                  <span className={cx('text-lg font-bold tabular-nums', short > 0 ? 'text-status-critical-fg' : 'text-fg-primary')}>
                    {short > 0 ? `−${short}` : '0'} <span className="text-[10px] font-normal">blk</span>
                  </span>
                  {modShort > 0 && <span className="text-[11px] font-medium tabular-nums text-status-critical-fg">−{modShort} mod</span>}
                </div>
              </div>
            </div>

            {/* Activities grouped by status */}
            <div className="flex flex-col gap-2">
              <StatusGroup
                title="⚠️ Behind / Overdue"
                tone="critical"
                activities={grouped.behind}
                defaultOpen={true}
              />
              <StatusGroup
                title="🔄 In Progress"
                tone="watch"
                activities={grouped.inProgress}
                defaultOpen={grouped.behind.length === 0}
              />
              <StatusGroup
                title="⏳ Not Started"
                tone="neutral"
                activities={grouped.notStarted}
                defaultOpen={false}
              />
              <StatusGroup
                title="✅ Completed"
                tone="healthy"
                activities={grouped.completed}
                defaultOpen={false}
              />
            </div>
          </div>
        </div>
      </motion.div>
    </div>,
    document.body
  );
}
