import React, { useEffect, useRef, useState } from 'react';
import { List, ArrowUpDown, ArrowUp, ArrowDown, Columns3, Download, MoreHorizontal, Eye, Building2, Package, Bookmark, BookmarkCheck, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { Card, CardHeader, StatusPill, SourceTag, cx } from '../../../components/ui/primitives';
import { useLedger, useDebounced, useMirroredInput } from '../hooks';
import { useSAPStore, ALL_COLUMNS, type LedgerSort } from '../store';
import { fmtCr, fmtDate, fmtNum, STATUS_LABEL, STATUS_TONE } from '../format';
import { COLUMN_LABEL, exportCSV, exportName, exportXLSX, fetchAllLines } from '../export';
import { Btn, Skeleton, ErrorBox, Empty } from './Drawer';
import type { LedgerColumn, POLine } from '../types';

const SORT_FOR: Partial<Record<LedgerColumn, LedgerSort>> = { po: 'po', buyer: 'buyer', vendor: 'vendor', material_code: 'material', date: 'date', status: 'status', ordered_cr: 'value', delivered_cr: 'delivered' };
const RIGHT: LedgerColumn[] = ['ordered_cr', 'delivered_cr', 'outstanding_cr'];

const Menu = ({ items, label }: { items: { label: string; icon: React.ComponentType<{ className?: string }>; onClick: () => void }[]; label: string }) => {
  const [open, setOpen] = useState(false); const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!open) return; const on = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); }; document.addEventListener('mousedown', on); return () => document.removeEventListener('mousedown', on); }, [open]);
  return (
    <div ref={ref} className="relative">
      <button type="button" aria-haspopup="menu" aria-expanded={open} aria-label={label} onClick={e => { e.stopPropagation(); setOpen(o => !o); }}
        className="rounded p-1 text-fg-tertiary hover:bg-surface-sunken hover:text-fg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><MoreHorizontal className="h-4 w-4" /></button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-20 mt-1 w-48 rounded-md border border-border-subtle bg-surface-2 py-1 shadow-overlay" onClick={e => e.stopPropagation()}>
          {items.map(it => (<button key={it.label} role="menuitem" type="button" onClick={() => { setOpen(false); it.onClick(); }} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] text-fg-secondary hover:bg-surface-sunken hover:text-fg-primary"><it.icon className="h-3.5 w-3.5" />{it.label}</button>))}
        </div>)}
    </div>
  );
};

export const ProcurementLedger = () => {
  const { data, loading, error, refetch, stale } = useLedger();
  const filters = useSAPStore(s => s.filters);
  const setFilter = useSAPStore(s => s.setFilter);
  const clearFilters = useSAPStore(s => s.clearFilters);
  const ledger = useSAPStore(s => s.ledger);
  const setLedger = useSAPStore(s => s.setLedger);
  const toggleRow = useSAPStore(s => s.toggleRow); const selectRows = useSAPStore(s => s.selectRows); const clearSelection = useSAPStore(s => s.clearSelection);
  const toggleColumn = useSAPStore(s => s.toggleColumn); const resetColumns = useSAPStore(s => s.resetColumns);
  const openPO = useSAPStore(s => s.openPO); const openVendor = useSAPStore(s => s.openVendor); const openMaterial = useSAPStore(s => s.openMaterial);
  const toggleWatch = useSAPStore(s => s.toggleWatch); const watchlist = useSAPStore(s => s.watchlist);
  const isWatched = (kind: 'po', id: string) => watchlist.some(w => w.kind === kind && w.id === id);
  const [colsOpen, setColsOpen] = useState(false); const colsRef = useRef<HTMLDivElement>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [q, setQ] = useMirroredInput(filters.search); const dq = useDebounced(q, 350);
  // Debounced ledger search writes through to the shared filter (a store write, not React state).
  useEffect(() => { if (dq !== filters.search) setFilter('search', dq.trim()); }, [dq, filters.search, setFilter]);
  useEffect(() => { if (!colsOpen) return; const on = (e: MouseEvent) => { if (!colsRef.current?.contains(e.target as Node)) setColsOpen(false); }; document.addEventListener('mousedown', on); return () => document.removeEventListener('mousedown', on); }, [colsOpen]);

  const rows = data?.rows ?? []; const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / ledger.size));
  const cols = ledger.columns; const allOnPage = rows.length > 0 && rows.every(r => ledger.selected.has(r.id));

  const sortBy = (c: LedgerColumn) => { const s = SORT_FOR[c]; if (!s) return; setLedger({ sort: s, order: ledger.sort === s && ledger.order === 'desc' ? 'asc' : 'desc', page: 1 }); };

  const doExport = async (fmt: 'csv' | 'xlsx', scope: 'selected' | 'page' | 'all') => {
    try {
      setExporting(`${fmt}:${scope}`);
      const lines: POLine[] = scope === 'page' ? rows : scope === 'selected' ? rows.filter(r => ledger.selected.has(r.id)) : await fetchAllLines(filters, ledger.sort, ledger.order, 20_000, n => setExporting(`${fmt}:all:${n}`));
      const meta = { Scope: scope === 'all' ? `All ${fmtNum(total)} matching lines${total > 20_000 ? ' (first 20,000)' : ''}` : scope === 'page' ? `Page ${ledger.page}` : `${lines.length} selected lines`, Filters: JSON.stringify(filters), Exported: new Date().toISOString() };
      if (fmt === 'csv') exportCSV(lines, cols, exportName(scope, 'csv')); else await exportXLSX(lines, cols, exportName(scope, 'xlsx'), meta);
    } finally { setExporting(null); }
  };

  const cell = (r: POLine, c: LedgerColumn): React.ReactNode => {
    switch (c) {
      case 'po': return <button type="button" onClick={e => { e.stopPropagation(); openPO(r.po); }} className="font-mono text-primary-700 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">{r.po}</button>;
      case 'vendor': return r.vendor ? <button type="button" onClick={e => { e.stopPropagation(); openVendor(r.vendor!); }} className="truncate hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded" title={r.vendor}>{r.vendor}</button> : <span className="text-fg-tertiary">(no vendor recorded)</span>;
      case 'material_code': return r.material_code ? <button type="button" onClick={e => { e.stopPropagation(); openMaterial(r.material_code!); }} className="font-mono hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">{r.material_code}</button> : <span className="text-fg-tertiary">—</span>;
      case 'material': return <span className="truncate" title={r.material ?? undefined}>{r.material ?? '—'}</span>;
      case 'date': return r.date ? fmtDate(r.date) : <span className="text-fg-tertiary" title="No document date on this line">—</span>;
      case 'status': return <StatusPill tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</StatusPill>;
      case 'ordered_cr': case 'delivered_cr': case 'outstanding_cr': return <span className="tabular-nums">{fmtCr(r[c], { decimals: 2 })}</span>;
      case 'buyer': return r.buyer ?? <span className="text-fg-tertiary">—</span>;
      case 'wbs': return <span className="font-mono text-fg-tertiary">{r.wbs ?? '—'}</span>;
    }
  };

  return (
    <Card pad="none" className="flex flex-col">
      <div className="px-4 pt-4">
        <CardHeader icon={List} eyebrow="Procurement ledger" title="Purchase order lines"
          right={<>
            {data && <span className="text-[12px] text-fg-tertiary">{fmtNum(total)} lines{stale && ' · updating…'}</span>}
            <SourceTag system="SAP" stamp="ZSPS" />
          </>} />
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[200px] flex-1 md:max-w-[320px]">
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search PO number, vendor, material, buyer…" aria-label="Search ledger"
              className="h-8 w-full rounded-md border border-border-default bg-surface-1 px-3 pr-8 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
            {q && <button type="button" onClick={() => setQ('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-fg-tertiary hover:text-fg-primary" aria-label="Clear"><X className="h-3.5 w-3.5" /></button>}
          </div>
          <div ref={colsRef} className="relative">
            <Btn variant="secondary" onClick={() => setColsOpen(o => !o)} aria-haspopup="dialog" aria-expanded={colsOpen}><Columns3 className="h-3.5 w-3.5" /> Columns</Btn>
            {colsOpen && (
              <div role="dialog" aria-label="Choose columns" className="absolute left-0 top-full z-20 mt-1 w-56 rounded-md border border-border-subtle bg-surface-2 p-2 shadow-overlay">
                {ALL_COLUMNS.map(c => (<label key={c} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-[13px] text-fg-secondary hover:bg-surface-sunken"><input type="checkbox" checked={cols.includes(c)} onChange={() => toggleColumn(c)} disabled={cols.includes(c) && cols.length === 1} className="accent-primary" />{COLUMN_LABEL[c]}</label>))}
                <div className="mt-1 border-t border-border-subtle pt-1"><Btn variant="ghost" className="w-full justify-center" onClick={resetColumns}>Restore defaults</Btn></div>
              </div>)}
          </div>
          <Menu label="Export ledger" items={[
            { label: `CSV — this page (${rows.length})`, icon: Download, onClick: () => doExport('csv', 'page') },
            { label: `CSV — all matching (${fmtNum(total)})`, icon: Download, onClick: () => doExport('csv', 'all') },
            { label: `Excel — all matching (${fmtNum(total)})`, icon: Download, onClick: () => doExport('xlsx', 'all') },
            ...(ledger.selected.size ? [{ label: `CSV — ${ledger.selected.size} selected`, icon: Download, onClick: () => doExport('csv', 'selected') }] : []),
          ]} />
          {exporting && <span className="text-[12px] text-fg-tertiary" aria-live="polite">Exporting{exporting.split(':')[2] ? ` · ${fmtNum(Number(exporting.split(':')[2]))} lines` : '…'}</span>}
          {ledger.selected.size > 0 && <span className="ml-auto inline-flex items-center gap-2 text-[12px] text-fg-secondary">{ledger.selected.size} selected <Btn variant="ghost" onClick={clearSelection}>Clear</Btn></span>}
        </div>
      </div>

      <div className="overflow-x-auto border-t border-border-subtle">
        {error ? <div className="p-4"><ErrorBox message={error} onRetry={refetch} /></div>
          : loading && !data ? <div className="space-y-1 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-9" />)}</div>
            : rows.length === 0 ? <div className="p-4"><Empty message="No procurement data available for the selected filters." action={<Btn variant="secondary" onClick={clearFilters}>Clear filters</Btn>} /></div>
              : <table className="intel-table w-full text-[13px]">
                <thead>
                  <tr className="bg-surface-sunken text-[12px] text-fg-tertiary">
                    <th className="w-8 px-3 py-2"><input type="checkbox" aria-label="Select all on page" checked={allOnPage} onChange={e => selectRows(rows.map(r => r.id), e.target.checked)} className="accent-primary" /></th>
                    {cols.map(c => { const s = SORT_FOR[c]; const active = s && ledger.sort === s; return (
                      <th key={c} scope="col" aria-sort={active ? (ledger.order === 'asc' ? 'ascending' : 'descending') : undefined} className={cx('whitespace-nowrap px-3 py-2 font-medium', RIGHT.includes(c) ? 'text-right' : 'text-left')}>
                        {s ? <button type="button" onClick={() => sortBy(c)} className="inline-flex items-center gap-1 hover:text-fg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">{COLUMN_LABEL[c]}{active ? (ledger.order === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />) : <ArrowUpDown className="h-3 w-3 opacity-40" />}</button> : COLUMN_LABEL[c]}
                      </th>); })}
                    <th className="w-10 px-2 py-2"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {rows.map(r => (
                    <tr key={r.id} onClick={() => openPO(r.po)} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') openPO(r.po); }}
                      className={cx('cursor-pointer hover:bg-surface-sunken/60 focus-visible:outline-none focus-visible:bg-surface-sunken', ledger.selected.has(r.id) && 'bg-primary-50/60')}>
                      <td className="px-3 py-2" onClick={e => e.stopPropagation()}><input type="checkbox" aria-label={`Select line ${r.po}`} checked={ledger.selected.has(r.id)} onChange={() => toggleRow(r.id)} className="accent-primary" /></td>
                      {cols.map(c => <td key={c} className={cx('max-w-[260px] px-3 py-2 text-fg-primary', RIGHT.includes(c) && 'text-right', (c === 'material' || c === 'vendor') && 'truncate')}>{cell(r, c)}</td>)}
                      <td className="px-2 py-1" onClick={e => e.stopPropagation()}>
                        <Menu label={`Actions for ${r.po}`} items={[
                          { label: 'View PO', icon: Eye, onClick: () => openPO(r.po) },
                          ...(r.vendor ? [{ label: 'View vendor', icon: Building2, onClick: () => openVendor(r.vendor!) }] : []),
                          ...(r.material_code ? [{ label: 'View material', icon: Package, onClick: () => openMaterial(r.material_code!) }] : []),
                          { label: isWatched('po', r.po) ? 'Remove from watchlist' : 'Add to watchlist', icon: isWatched('po', r.po) ? BookmarkCheck : Bookmark, onClick: () => toggleWatch('po', r.po, `PO ${r.po} · ${r.vendor ?? 'no vendor'}`) },
                          { label: 'Export PO (CSV)', icon: Download, onClick: () => exportCSV(rows.filter(x => x.po === r.po), cols, exportName(`PO_${r.po}`, 'csv')) },
                        ]} />
                      </td>
                    </tr>))}
                </tbody>
              </table>}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border-subtle px-4 py-2 text-[12px] text-fg-tertiary">
        <div className="flex items-center gap-2">
          <span>Rows per page</span>
          <select value={ledger.size} onChange={e => setLedger({ size: Number(e.target.value), page: 1 })} aria-label="Rows per page" className="h-7 rounded border border-border-default bg-surface-1 px-1.5 text-[12px] text-fg-primary">{[25, 50, 100, 200].map(n => <option key={n} value={n}>{n}</option>)}</select>
          {total > 0 && <span>{fmtNum((ledger.page - 1) * ledger.size + 1)}–{fmtNum(Math.min(ledger.page * ledger.size, total))} of {fmtNum(total)}</span>}
        </div>
        <div className="flex items-center gap-1">
          <Btn variant="ghost" onClick={() => setLedger({ page: ledger.page - 1 })} disabled={ledger.page <= 1} aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></Btn>
          <span className="tabular-nums">Page {ledger.page} of {fmtNum(pages)}</span>
          <Btn variant="ghost" onClick={() => setLedger({ page: ledger.page + 1 })} disabled={ledger.page >= pages} aria-label="Next page"><ChevronRight className="h-4 w-4" /></Btn>
        </div>
      </div>
    </Card>
  );
};
