import React, { useEffect, useRef, useState } from 'react';
import type { ComponentType } from 'react';
import { ChevronDown, CalendarRange, GitBranch, Filter, RefreshCw, Search, HardHat } from 'lucide-react';
import { cx } from '../../components/ui/primitives/cx';
import type { PlannerFilters, WindowKey, BasisKey, ShowKey } from './types';
import { WINDOW_LABELS, BASIS_LABELS, SHOW_LABELS } from './types';

/* Same header grammar as Capacity Overview: title + kicker on the left,
   dropdown menus + refresh on the right. Menu is copied from CapacityHeader
   (it is file-local there by design). */

function Menu<T extends string>({ label, icon: Icon, value, options, onChange, labels }: {
  label: string; icon: ComponentType<{ className?: string }>; value: T; options: T[];
  onChange: (v: T) => void; labels?: Record<string, string>;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown); document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(o => !o)} aria-haspopup="listbox" aria-expanded={open} aria-label={`${label}: ${labels?.[value] ?? value}`}
        className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[12px] font-semibold text-fg-secondary transition-colors hover:border-brand-blue/40 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
        <Icon className="h-3.5 w-3.5 text-fg-tertiary" />{labels?.[value] ?? value}
        <ChevronDown className={cx('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <ul role="listbox" aria-label={label} className="surface-raised absolute right-0 top-full z-40 mt-1 min-w-[170px] overflow-hidden py-1">
          {options.map(o => (
            <li key={o} role="option" aria-selected={o === value}>
              <button onClick={() => { onChange(o); setOpen(false); }}
                className={cx('block w-full px-3 py-1.5 text-left text-[12px] transition-colors hover:bg-brand-blue/10 focus:outline-none focus-visible:bg-brand-blue/10', o === value ? 'font-bold text-brand-blue' : 'text-fg-secondary')}>
                {labels?.[o] ?? o}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function PlannerHeader({ filters, onChange, onRefresh, refreshing, scopeLabel }: {
  filters: PlannerFilters; onChange: (p: Partial<PlannerFilters>) => void; onRefresh: () => void; refreshing: boolean; scopeLabel: string;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[19px] font-bold leading-tight text-foreground">Installation Planner</h1>
          <span className="inline-flex items-center gap-1 rounded-full border border-brand-blue/25 bg-brand-blue/10 px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wider text-brand-blue">
            <HardHat className="h-2.5 w-2.5" /> P6 · SAP
          </span>
        </div>
        <p className="mt-1 text-[12px] text-fg-tertiary">Module installation by project and month — P6 plan vs completed · {scopeLabel}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-tertiary" />
          <input value={filters.search} onChange={e => onChange({ search: e.target.value })} placeholder="Find project…" aria-label="Find project"
            className="h-[34px] w-[190px] rounded-lg border border-border bg-card pl-8 pr-3 text-[12px] text-foreground placeholder:text-fg-tertiary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary" />
        </label>
        <Menu<WindowKey> label="Window" icon={CalendarRange} value={filters.window} options={['NEXT6', 'FY', 'ALL']} labels={WINDOW_LABELS} onChange={window => onChange({ window })} />
        <Menu<BasisKey> label="Plan basis" icon={GitBranch} value={filters.basis} options={['planned', 'baseline']} labels={BASIS_LABELS} onChange={basis => onChange({ basis })} />
        <Menu<ShowKey> label="Show" icon={Filter} value={filters.show} options={['all', 'behind', 'notstarted', 'done']} labels={SHOW_LABELS} onChange={show => onChange({ show })} />
        <button onClick={onRefresh} disabled={refreshing} aria-label="Refresh"
          className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-border bg-card text-fg-tertiary transition-colors hover:text-foreground disabled:opacity-50">
          <RefreshCw className={cx('h-3.5 w-3.5', refreshing && 'animate-spin')} />
        </button>
      </div>
    </header>
  );
}
