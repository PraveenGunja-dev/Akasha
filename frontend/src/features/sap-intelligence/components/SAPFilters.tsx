import React, { useEffect, useRef, useState } from 'react';
import { Search, SlidersHorizontal, X, ChevronDown, Package, Building2, FileText, User, FolderKanban } from 'lucide-react';
import { useDebounced, useFilterOptions, useMirroredInput } from '../hooks';
import { useSAPStore } from '../store';
import { sapApi } from '../api';
import { STATUS_LABEL } from '../format';
import { Btn } from './Drawer';
import { cx } from '../../../components/ui/primitives';
import { formatProjectName } from '../../../lib/projectName';
import type { POStatus, SearchResult } from '../types';

/* One filter bar, one store. Primary scope (portfolio, project, dates) is
   always visible; the long tail lives behind "Filters". Search is global and
   actionable: a result opens its record rather than only filtering. */

const Select = ({ label, value, onChange, options, placeholder }: {
  label: string; value: string | null; onChange: (v: string | null) => void;
  options: { value: string; label: string }[]; placeholder: string;
}) => (
  <label className="relative inline-flex items-center">
    <span className="sr-only">{label}</span>
    <select
      value={value ?? ''}
      onChange={e => onChange(e.target.value || null)}
      className={cx('h-8 appearance-none rounded-md border bg-surface-1 pl-3 pr-8 text-[13px] text-fg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        value ? 'border-primary/50 bg-primary-50' : 'border-border-default')}
    >
      <option value="">{placeholder}</option>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
    <ChevronDown className="pointer-events-none absolute right-2.5 h-3.5 w-3.5 text-fg-tertiary" />
  </label>
);

const ICON: Record<SearchResult['type'], React.ComponentType<{ className?: string }>> = { po: FileText, vendor: Building2, material: Package, buyer: User, project: FolderKanban };

export const SAPFilters = () => {
  const filters = useSAPStore(s => s.filters);
  const setFilter = useSAPStore(s => s.setFilter);
  const setFilters = useSAPStore(s => s.setFilters);
  const clear = useSAPStore(s => s.clearFilters);
  const count = useSAPStore(s => s.activeFilterCount());
  const openDrawer = useSAPStore(s => s.openDrawer);
  const { data: opts } = useFilterOptions();

  // Global search: type-ahead against /search, Enter applies as a text filter.
  const [q, setQ] = useMirroredInput(filters.search);
  const dq = useDebounced(q, 250);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const box = useRef<HTMLDivElement>(null);
  const searching = dq.trim().length >= 2 && dq !== filters.search;
  useEffect(() => {
    if (!searching) return;
    const ctrl = new AbortController();
    sapApi.search(dq.trim(), ctrl.signal).then(r => { setResults(r.results); setOpen(true); setActive(-1); }).catch(() => {});
    return () => ctrl.abort();
  }, [dq, searching]);
  const visible = searching ? results : [];
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onDoc); return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const pick = (r: SearchResult) => {
    setOpen(false); setQ('');
    switch (r.type) {
      case 'po': openDrawer({ kind: 'po', id: r.id }); break;
      case 'vendor': setFilters({ vendor: r.id, search: '' }); openDrawer({ kind: 'vendor', id: r.id }); break;
      case 'material': setFilters({ material: r.id, search: '' }); openDrawer({ kind: 'material', id: r.id }); break;
      case 'buyer': setFilters({ search: r.id }); break;
      case 'project': setFilters({ project: r.id, search: '' }); break;
    }
  };

  const chips: { k: string; label: string; clear: () => void }[] = [];
  if (filters.vendor) chips.push({ k: 'vendor', label: `Vendor: ${filters.vendor}`, clear: () => setFilter('vendor', null) });
  if (filters.material) chips.push({ k: 'material', label: `Material: ${filters.material}`, clear: () => setFilter('material', null) });
  if (filters.status) chips.push({ k: 'status', label: STATUS_LABEL[filters.status], clear: () => setFilter('status', null) });
  if (filters.state) chips.push({ k: 'state', label: `State: ${filters.state}`, clear: () => setFilter('state', null) });
  if (filters.cluster) chips.push({ k: 'cluster', label: `Cluster: ${filters.cluster}`, clear: () => setFilter('cluster', null) });
  if (filters.search) chips.push({ k: 'search', label: `“${filters.search}”`, clear: () => setFilter('search', '') });
  if (filters.codes.length) chips.push({ k: 'codes', label: `Company scope (${filters.codes.length} codes)`, clear: () => setFilter('codes', []) });

  return (
    <div className="sticky top-0 z-30 -mx-1 rounded-lg border border-border-subtle bg-surface-1/95 px-3 py-2.5 backdrop-blur-sm">
      <div className="flex flex-wrap items-center gap-2">
        <div ref={box} className="relative min-w-[220px] flex-1 md:max-w-[360px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-tertiary" />
          <input
            role="combobox" aria-expanded={open} aria-controls="sap-search-list" aria-autocomplete="list" aria-label="Search PO, vendor, material, project"
            value={q}
            onChange={e => setQ(e.target.value)}
            onFocus={() => visible.length && setOpen(true)}
            onKeyDown={e => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, visible.length - 1)); }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, -1)); }
              else if (e.key === 'Enter') { e.preventDefault(); if (active >= 0 && visible[active]) pick(visible[active]); else { setFilter('search', q.trim()); setOpen(false); } }
              else if (e.key === 'Escape') setOpen(false);
            }}
            placeholder="Search PO, vendor, material, project…"
            className="h-8 w-full rounded-md border border-border-default bg-surface-1 pl-8 pr-8 text-[13px] text-fg-primary placeholder:text-fg-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          {q && <button type="button" onClick={() => { setQ(''); setFilter('search', ''); }} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-fg-tertiary hover:text-fg-primary" aria-label="Clear search"><X className="h-3.5 w-3.5" /></button>}
          {open && visible.length > 0 && (
            <ul id="sap-search-list" role="listbox" className="absolute left-0 right-0 top-full z-40 mt-1 max-h-72 overflow-y-auto rounded-md border border-border-subtle bg-surface-2 py-1 shadow-overlay">
              {visible.map((r, i) => { const I = ICON[r.type]; return (
                <li key={`${r.type}:${r.id}`} role="option" aria-selected={i === active}
                  onMouseDown={e => { e.preventDefault(); pick(r); }} onMouseEnter={() => setActive(i)}
                  className={cx('flex cursor-pointer items-center gap-2.5 px-3 py-1.5 text-[13px]', i === active ? 'bg-surface-sunken text-fg-primary' : 'text-fg-secondary')}>
                  <I className="h-3.5 w-3.5 shrink-0 text-fg-tertiary" />
                  <span className="truncate">{r.type === 'project' ? formatProjectName(r.label) : r.label}</span>
                  <span className="ml-auto shrink-0 text-[11px] uppercase tracking-wide text-fg-tertiary">{r.type}</span>
                </li>); })}
            </ul>
          )}
        </div>

        <Select label="Portfolio" value={filters.portfolio} onChange={v => setFilters({ portfolio: v, project: null })} placeholder="All portfolios"
          options={(opts?.portfolios ?? []).map(p => ({ value: p, label: p }))} />
        <Select label="Project" value={filters.project} onChange={v => setFilter('project', v)} placeholder="All projects"
          options={(opts?.projects ?? []).map(p => ({ value: p.id, label: formatProjectName(p.name) }))} />

        <div className="inline-flex items-center gap-1 rounded-md border border-border-default bg-surface-1 px-2 text-[13px]" role="group" aria-label="PO date range">
          <input type="date" aria-label="From" value={filters.dateFrom ?? ''} min={opts?.date_min ?? undefined} max={filters.dateTo ?? opts?.date_max ?? undefined}
            onChange={e => setFilter('dateFrom', e.target.value || null)} className="h-[30px] w-[118px] bg-transparent text-fg-primary focus-visible:outline-none" />
          <span className="text-fg-tertiary">–</span>
          <input type="date" aria-label="To" value={filters.dateTo ?? ''} min={filters.dateFrom ?? opts?.date_min ?? undefined} max={opts?.date_max ?? undefined}
            onChange={e => setFilter('dateTo', e.target.value || null)} className="h-[30px] w-[118px] bg-transparent text-fg-primary focus-visible:outline-none" />
        </div>

        <Btn variant="secondary" onClick={() => openDrawer({ kind: 'filters' })} aria-label="More filters">
          <SlidersHorizontal className="h-3.5 w-3.5" /> Filters{count > 0 && <span className="rounded-full bg-primary px-1.5 text-[11px] text-primary-foreground tabular-nums">{count}</span>}
        </Btn>
        {count > 0 && <Btn variant="ghost" onClick={clear}>Clear all</Btn>}
      </div>

      {chips.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Active filters">
          {chips.map(c => (
            <span key={c.k} className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary-50 py-0.5 pl-2.5 pr-1 text-[12px] text-primary-700">
              {c.label}
              <button type="button" onClick={c.clear} className="rounded-full p-0.5 hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={`Remove filter ${c.label}`}><X className="h-3 w-3" /></button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

/* The long tail — opened from the "Filters" button as a drawer. */
export const MoreFilters = () => {
  const filters = useSAPStore(s => s.filters);
  const setFilter = useSAPStore(s => s.setFilter);
  const { data: opts } = useFilterOptions();
  const statuses: POStatus[] = opts?.statuses ?? ['pending', 'partial', 'delivered', 'cancelled'];
  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="section-label mb-1.5">PO status</div>
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="PO status">
          {[null, ...statuses].map(s => (
            <button key={s ?? 'all'} type="button" role="radio" aria-checked={filters.status === s} onClick={() => setFilter('status', s)}
              className={cx('h-8 rounded-md border px-3 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                filters.status === s ? 'border-primary bg-primary-50 text-primary-700' : 'border-border-default text-fg-secondary hover:bg-surface-sunken')}>
              {s ? STATUS_LABEL[s] : 'Any'}
            </button>
          ))}
        </div>
      </div>
      <div>
        <div className="section-label mb-1.5">State</div>
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="State">
          {[null, ...(opts?.states ?? [])].map(s => (
            <button key={s ?? 'all'} type="button" role="radio" aria-checked={filters.state === s} onClick={() => setFilter('state', s)}
              className={cx('h-8 rounded-md border px-3 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                filters.state === s ? 'border-primary bg-primary-50 text-primary-700' : 'border-border-default text-fg-secondary hover:bg-surface-sunken')}>
              {s ?? 'All India'}
            </button>
          ))}
        </div>
      </div>
      <label className="block">
        <div className="section-label mb-1.5">Vendor</div>
        <input list="sap-vendor-list" value={filters.vendor ?? ''} onChange={e => setFilter('vendor', e.target.value || null)} placeholder="Type to pick a vendor"
          className="h-8 w-full rounded-md border border-border-default bg-surface-1 px-3 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        <datalist id="sap-vendor-list">{(opts?.vendors ?? []).map(v => <option key={v} value={v} />)}</datalist>
      </label>
      <label className="block">
        <div className="section-label mb-1.5">Material code</div>
        <input value={filters.material ?? ''} onChange={e => setFilter('material', e.target.value.trim() || null)} placeholder="e.g. 9922522933"
          className="h-8 w-full rounded-md border border-border-default bg-surface-1 px-3 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
      </label>
      <label className="block">
        <div className="section-label mb-1.5">Company scope (plant / WBS codes)</div>
        <input value={filters.codes.join(', ')} onChange={e => setFilter('codes', e.target.value.split(/[\s,]+/).filter(Boolean))} placeholder="H-6061, H-51ZQ"
          className="h-8 w-full rounded-md border border-border-default bg-surface-1 px-3 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        <p className="mt-1 text-[12px] text-fg-tertiary">Matches plant code or WBS element, with or without the H- prefix.</p>
      </label>
    </div>
  );
};
