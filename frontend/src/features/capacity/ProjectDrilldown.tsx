import React, { useMemo, useState } from 'react';
import { Search, ArrowUpDown, Sun, Wind, ExternalLink } from 'lucide-react';
import Drawer from './Drawer';
import type { ProjectBreakdown } from './types';
import { cx } from '../../components/ui/primitives/cx';
import { formatProjectName } from '../../lib/projectName';
import { useProjectLink } from './useProjectLink';

/* ═══════════════════════════════════════════════════════════════════════════
   PROJECT DRILL-DOWN

   Every capacity figure on the page ends here: the same table, filtered to
   whatever was clicked. Search and sort are real, and the totals in the header
   recompute from the visible rows so the drawer always reconciles with itself.
   ═══════════════════════════════════════════════════════════════════════════ */

type SortKey = 'project_name' | 'total_capacity' | 'cod_mw' | 'tr_mw' | 'remaining_capacity' | 'progress';

const COLUMNS: { key: SortKey; label: string; align?: string }[] = [
  { key: 'project_name', label: 'Project' },
  { key: 'total_capacity', label: 'Capacity', align: 'text-right' },
  { key: 'cod_mw', label: 'COD', align: 'text-right' },
  { key: 'tr_mw', label: 'Trial run', align: 'text-right' },
  { key: 'remaining_capacity', label: 'Remaining', align: 'text-right' },
  { key: 'progress', label: 'Commissioned', align: 'text-right' },
];

const progressOf = (p: ProjectBreakdown) =>
  p.total_capacity > 0 ? ((p.cod_mw + p.tr_mw) / p.total_capacity) * 100 : 0;

export default function ProjectDrilldown({
  open, onClose, title, subtitle, projects,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  projects: ProjectBreakdown[];
}) {
  const { open: openProject, href } = useProjectLink();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'total_capacity', dir: 'desc' });

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? projects.filter((p) => (p.project_name || '').toLowerCase().includes(q) || (p.type || '').toLowerCase().includes(q))
      : projects;

    const val = (p: ProjectBreakdown) =>
      sort.key === 'progress' ? progressOf(p)
        : sort.key === 'project_name' ? (p.project_name || '').toLowerCase()
          : Number(p[sort.key] ?? 0);

    return [...filtered].sort((a, b) => {
      const av = val(a); const bv = val(b);
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sort.dir === 'asc' ? cmp : -cmp;
    });
  }, [projects, query, sort]);

  const totals = useMemo(() => ({
    capacity: rows.reduce((s, p) => s + (p.total_capacity || 0), 0),
    cod: rows.reduce((s, p) => s + (p.cod_mw || 0), 0),
    tr: rows.reduce((s, p) => s + (p.tr_mw || 0), 0),
  }), [rows]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }));

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
          <span><strong className="text-fg-secondary">{totals.capacity.toFixed(1)}</strong> MW capacity</span>
          <span><strong className="text-fg-secondary">{totals.cod.toFixed(1)}</strong> MW COD</span>
          <span><strong className="text-fg-secondary">{totals.tr.toFixed(1)}</strong> MW trial run</span>
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
          {projects.length === 0
            ? 'No projects match this selection.'
            : `No project matches “${query}”.`}
        </div>
      ) : (
        <table className="w-full border-collapse text-left">
          <thead className="sticky top-0 bg-card">
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} scope="col" className={cx('border-b border-border pb-2', c.align)}>
                  <button
                    onClick={() => toggleSort(c.key)}
                    aria-sort={sort.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                    className={cx(
                      'inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider transition-colors hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                      sort.key === c.key ? 'text-foreground' : 'text-fg-tertiary',
                    )}
                  >
                    {c.label}
                    <ArrowUpDown className="h-2.5 w-2.5" />
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const pct = progressOf(p);
              return (
                <tr
                  key={`${p.project_id}-${p.project_name}`}
                  onClick={() => openProject(p.project_id)}
                  className="group cursor-pointer border-b border-border-subtle transition-colors hover:bg-muted/50"
                >
                  <td className="max-w-[240px] py-2 pr-2" title={`Open ${p.project_name}`}>
                    {/* A real anchor: middle-click and "open in new tab" work,
                        which they do not on a div with a click handler. */}
                    <a
                      href={href(p.project_id)}
                      onClick={(e) => { e.preventDefault(); e.stopPropagation(); openProject(p.project_id); }}
                      className="flex items-center gap-1.5 truncate text-[12px] font-semibold text-foreground hover:text-primary hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      {p.type === 'Wind'
                        ? <Wind className="h-3 w-3 shrink-0 text-blue-500" aria-label="Wind" />
                        : <Sun className="h-3 w-3 shrink-0 text-amber-500" aria-label="Solar" />}
                      <span className="truncate">{formatProjectName(p.project_name)}</span>
                      <ExternalLink className="h-2.5 w-2.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-60" />
                    </a>
                  </td>
                  <td className="py-2 text-right text-[12px] font-bold tabular-nums text-foreground">{p.total_capacity.toFixed(1)}</td>
                  <td className="py-2 text-right text-[12px] tabular-nums text-fg-secondary">{p.cod_mw > 0 ? p.cod_mw.toFixed(1) : '—'}</td>
                  <td className="py-2 text-right text-[12px] tabular-nums text-fg-secondary">{p.tr_mw > 0 ? p.tr_mw.toFixed(1) : '—'}</td>
                  <td className="py-2 text-right text-[12px] tabular-nums text-fg-secondary">{(p.remaining_capacity || 0).toFixed(1)}</td>
                  <td className="py-2 pl-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-fg-tertiary/15">
                        <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(pct, 100)}%` }} />
                      </div>
                      <span className="w-9 text-[11px] font-semibold tabular-nums text-fg-secondary">{pct.toFixed(0)}%</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Drawer>
  );
}
