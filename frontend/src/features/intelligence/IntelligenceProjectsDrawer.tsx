import React, { useMemo, useState } from 'react';
import { Search, ArrowUpDown, ExternalLink, Sun, Wind } from 'lucide-react';
import Drawer from '../capacity/Drawer';
import { useProjectLink } from '../capacity/useProjectLink';
import { cx } from '../../components/ui/primitives/cx';
import { formatProjectName } from '../../lib/projectName';

/* ═══════════════════════════════════════════════════════════════════════════
   INTELLIGENCE PROJECT DRILL-DOWN

   The portfolio counters (Total / Critical / At risk / Delayed) were figures
   with nowhere to go. Each now opens the projects behind it, and every row
   links to that project's workspace — which is the whole point of a portfolio
   view: it should end at the project you have to do something about.

   Reuses the capacity module's Drawer and useProjectLink so the shell and the
   route are identical across the app.
   ═══════════════════════════════════════════════════════════════════════════ */

export interface IntelProject {
  project_id: string;
  project_name: string;
  cluster: string | null;
  category: string | null;
  capacity_mw: number;
  progress_pct: number;
  total_delay_days: number;
  schedule_health: number;
  overall_health: number;
  overall_status: string;
  baseline_finish: string | null;
  forecast_finish: string | null;
}

type SortKey = 'project_name' | 'capacity_mw' | 'progress_pct' | 'total_delay_days' | 'overall_health';

const COLUMNS: { key: SortKey; label: string; align?: string }[] = [
  { key: 'project_name', label: 'Project' },
  { key: 'capacity_mw', label: 'MW', align: 'text-right' },
  { key: 'progress_pct', label: 'Progress', align: 'text-right' },
  { key: 'total_delay_days', label: 'Delay', align: 'text-right' },
  { key: 'overall_health', label: 'Health', align: 'text-right' },
];

const STATUS_CHIP: Record<string, string> = {
  CRITICAL: 'bg-status-critical-bg text-status-critical-fg border-status-critical-border',
  AT_RISK: 'bg-status-watch-bg text-status-watch-fg border-status-watch-border',
  ON_TRACK: 'bg-status-healthy-bg text-status-healthy-fg border-status-healthy-border',
};

const healthTone = (h: number) =>
  h < 40 ? 'text-status-critical-fg' : h < 70 ? 'text-status-watch-fg' : 'text-status-healthy-fg';

export default function IntelligenceProjectsDrawer({
  open, onClose, title, subtitle, projects,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  projects: IntelProject[];
}) {
  const { open: openProject, href } = useProjectLink();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'overall_health', dir: 'asc' });

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? projects.filter((p) =>
        (p.project_name || '').toLowerCase().includes(q) || (p.category || '').toLowerCase().includes(q))
      : projects;

    return [...filtered].sort((a, b) => {
      const av = sort.key === 'project_name' ? (a.project_name || '').toLowerCase() : Number(a[sort.key] ?? 0);
      const bv = sort.key === 'project_name' ? (b.project_name || '').toLowerCase() : Number(b[sort.key] ?? 0);
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sort.dir === 'asc' ? cmp : -cmp;
    });
  }, [projects, query, sort]);

  const totalMW = rows.reduce((s, p) => s + (p.capacity_mw || 0), 0);
  const toggle = (key: SortKey) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === 'asc' ? 'desc' : 'asc' }));

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="max-w-4xl"
      title={title}
      subtitle={
        <span className="flex flex-wrap gap-x-3 gap-y-1">
          {subtitle && <span>{subtitle}</span>}
          <span><strong className="text-fg-secondary">{rows.length}</strong> projects</span>
          <span><strong className="text-fg-secondary">{totalMW.toFixed(1)}</strong> MW</span>
          <span className="text-fg-tertiary">· click a row to open the project</span>
        </span>
      }
    >
      <div className="relative mb-3">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-tertiary" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search projects…"
          aria-label="Search projects"
          className="w-full rounded-lg border border-border bg-card py-1.5 pl-8 pr-3 text-[12px] text-foreground placeholder:text-fg-tertiary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        />
      </div>

      {rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border py-12 text-center text-[12px] text-fg-tertiary">
          {projects.length === 0 ? 'No projects in this group.' : `No project matches “${query}”.`}
        </div>
      ) : (
        <table className="w-full border-collapse text-left">
          <thead className="sticky top-0 bg-card">
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} scope="col" className={cx('border-b border-border pb-2', c.align)}>
                  <button
                    onClick={() => toggle(c.key)}
                    aria-sort={sort.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                    className={cx(
                      'inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider transition-colors hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                      sort.key === c.key ? 'text-foreground' : 'text-fg-tertiary',
                    )}
                  >
                    {c.label} <ArrowUpDown className="h-2.5 w-2.5" />
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr
                key={p.project_id}
                onClick={() => openProject(p.project_id)}
                className="group cursor-pointer border-b border-border-subtle transition-colors hover:bg-muted/50"
              >
                <td className="max-w-[260px] py-2 pr-2">
                  <a
                    href={href(p.project_id)}
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); openProject(p.project_id); }}
                    className="flex items-center gap-1.5 truncate text-[12px] font-semibold text-foreground hover:text-primary hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    title={`Open ${p.project_name}`}
                  >
                    {p.category === 'Wind'
                      ? <Wind className="h-3 w-3 shrink-0 text-blue-500" aria-label="Wind" />
                      : <Sun className="h-3 w-3 shrink-0 text-amber-500" aria-label="Solar" />}
                    <span className="truncate">{formatProjectName(p.project_name)}</span>
                    <ExternalLink className="h-2.5 w-2.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-60" />
                  </a>
                  <span className={cx(
                    'mt-0.5 inline-block rounded-full border px-1.5 text-[9px] font-bold',
                    STATUS_CHIP[p.overall_status] || 'border-border text-fg-tertiary',
                  )}>
                    {(p.overall_status || '').replace('_', ' ')}
                  </span>
                </td>
                <td className="py-2 text-right text-[12px] font-bold tabular-nums text-foreground">{(p.capacity_mw || 0).toFixed(1)}</td>
                <td className="py-2 text-right text-[12px] tabular-nums text-fg-secondary">{(p.progress_pct || 0).toFixed(0)}%</td>
                <td className={cx(
                  'py-2 text-right text-[12px] font-semibold tabular-nums',
                  (p.total_delay_days || 0) > 0 ? 'text-status-critical-fg' : 'text-fg-tertiary',
                )}>
                  {(p.total_delay_days || 0) > 0 ? `${p.total_delay_days}d` : '—'}
                </td>
                <td className={cx('py-2 text-right text-[12px] font-bold tabular-nums', healthTone(p.overall_health || 0))}>
                  {(p.overall_health ?? 0).toFixed(0)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Drawer>
  );
}
