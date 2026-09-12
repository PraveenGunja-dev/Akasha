import React, { useEffect, useRef, useState } from 'react';
import type { ComponentType } from 'react';
import { ChevronDown, Calendar, Layers, Sparkles, ListChecks, RefreshCw } from 'lucide-react';
import type { CapacityFilters, Segment, DateRangeKey } from './types';
import { DATE_RANGE_LABELS } from './types';
import { cx } from '../../components/ui/primitives/cx';

/* ═══════════════════════════════════════════════════════════════════════════
   CAPACITY HEADER

   Segment options are the ones the data carries. `capacity-overview` types
   every project by ProjectMapping.cluster into Solar or Wind, so Hydro,
   Thermal and Hybrid would be permanently empty tabs — offering them would be
   a promise the data cannot keep.

   Both menus are real: keyboard reachable, Escape to close, click-outside to
   dismiss, aria-expanded reflecting state, and the selected value announced.
   ═══════════════════════════════════════════════════════════════════════════ */

function Menu<T extends string>({
  label, icon: Icon, value, options, onChange, labels,
}: {
  label: string;
  icon: ComponentType<{ className?: string }>;
  value: T;
  options: T[];
  onChange: (v: T) => void;
  labels?: Record<string, string>;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${label}: ${labels?.[value] ?? value}`}
        className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[12px] font-semibold text-fg-secondary transition-colors hover:border-brand-blue/40 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <Icon className="h-3.5 w-3.5 text-fg-tertiary" />
        {labels?.[value] ?? value}
        <ChevronDown className={cx('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <ul
          role="listbox"
          aria-label={label}
          className="surface-raised absolute right-0 top-full z-40 mt-1 min-w-[170px] overflow-hidden py-1"
        >
          {options.map((o) => (
            <li key={o} role="option" aria-selected={o === value}>
              <button
                onClick={() => { onChange(o); setOpen(false); }}
                className={cx(
                  'block w-full px-3 py-1.5 text-left text-[12px] transition-colors hover:bg-brand-blue/10 focus:outline-none focus-visible:bg-brand-blue/10',
                  o === value ? 'font-bold text-brand-blue' : 'text-fg-secondary',
                )}
              >
                {labels?.[o] ?? o}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function CapacityHeader({
  filters, onChange, onAskAi, onOpenActions, onRefresh, actionCount, refreshing,
}: {
  filters: CapacityFilters;
  onChange: (patch: Partial<CapacityFilters>) => void;
  onAskAi: () => void;
  onOpenActions: () => void;
  onRefresh: () => void;
  actionCount: number;
  refreshing: boolean;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[19px] font-bold leading-tight text-foreground">Capacity Overview</h1>
          <span className="inline-flex items-center gap-1 rounded-full border border-brand-purple/25 bg-brand-purple/10 px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wider text-brand-purple">
            <Sparkles className="h-2.5 w-2.5" /> Intelligence
          </span>
        </div>
        <p className="mt-1 text-[12px] text-fg-tertiary">
          Track commissioned, in-progress and upcoming capacity across all segments
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Menu<Segment>
          label="Segment"
          icon={Layers}
          value={filters.segment}
          options={['All', 'Solar', 'Wind']}
          labels={{ All: 'All segments' }}
          onChange={(segment) => onChange({ segment })}
        />
        <Menu<DateRangeKey>
          label="Date range"
          icon={Calendar}
          value={filters.dateRange}
          options={['3M', '6M', '12M', 'FY', 'ALL']}
          labels={DATE_RANGE_LABELS}
          onChange={(dateRange) => onChange({ dateRange })}
        />

        <button
          onClick={onOpenActions}
          className="relative flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[12px] font-semibold text-fg-secondary transition-colors hover:border-brand-blue/40 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <ListChecks className="h-3.5 w-3.5 text-fg-tertiary" />
          Actions
          {actionCount > 0 && (
            <span className="ml-0.5 rounded-full bg-brand-blue px-1.5 text-[10px] font-bold text-white">{actionCount}</span>
          )}
        </button>

        <button
          onClick={onRefresh}
          disabled={refreshing}
          aria-label="Reload capacity data"
          className="rounded-lg border border-border bg-card p-1.5 text-fg-tertiary transition-colors hover:text-foreground disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <RefreshCw className={cx('h-3.5 w-3.5', refreshing && 'animate-spin')} />
        </button>

        <button
          onClick={onAskAi}
          className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-brand-blue to-brand-purple px-3 py-1.5 text-[12px] font-semibold text-white transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <Sparkles className="h-3.5 w-3.5" /> Ask AI
        </button>
      </div>
    </header>
  );
}
