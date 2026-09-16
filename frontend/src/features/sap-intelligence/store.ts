/* SAP Intelligence — single source of truth.

   Filters, selection, drawer state, watchlist and ledger table state live
   here. Every panel reads the same filters, so the KPI row, trend, vendor
   bars, map, ledger and insights always describe the same slice. Drawers
   stack on top of the dashboard without touching filters, so closing one
   returns to exactly the state the reader left.

   Persistence follows what the app already does (sessionStorage for tab
   memory in CEODashboard): watchlist and column preferences go to
   localStorage; filters go to the URL so a view can be shared. */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { DrawerState, KpiId, LedgerColumn, POStatus, SAPFilters, WatchItem, WatchKind } from './types';

export const EMPTY_FILTERS: SAPFilters = {
  portfolio: null, phase: null, project: null, state: null, cluster: null, dateFrom: null, dateTo: null,
  vendor: null, material: null, status: null, search: '', codes: [],
};

export const DEFAULT_COLUMNS: LedgerColumn[] = ['po', 'buyer', 'vendor', 'material_code', 'material', 'date', 'status', 'ordered_cr', 'delivered_cr', 'outstanding_cr'];
export const ALL_COLUMNS: LedgerColumn[] = [...DEFAULT_COLUMNS, 'wbs'];

export type LedgerSort = 'po' | 'buyer' | 'vendor' | 'material' | 'date' | 'value' | 'delivered' | 'status';

interface LedgerState {
  page: number; size: number; sort: LedgerSort; order: 'asc' | 'desc';
  columns: LedgerColumn[]; selected: Set<number>;
}

interface SAPStore {
  filters: SAPFilters;
  setFilter: <K extends keyof SAPFilters>(k: K, v: SAPFilters[K]) => void;
  setFilters: (patch: Partial<SAPFilters>) => void;
  clearFilters: () => void;
  activeFilterCount: () => number;

  drawers: DrawerState[];
  openDrawer: (d: DrawerState) => void;
  closeDrawer: () => void;
  closeAllDrawers: () => void;
  openPO: (id: string) => void;
  openVendor: (id: string) => void;
  openMaterial: (id: string) => void;
  openInsight: (id: string) => void;
  openKpi: (id: KpiId) => void;

  watchlist: WatchItem[];
  isWatched: (kind: WatchKind, id: string) => boolean;
  toggleWatch: (kind: WatchKind, id: string, label: string) => void;
  removeWatch: (kind: WatchKind, id: string) => void;

  ledger: LedgerState;
  setLedger: (patch: Partial<Omit<LedgerState, 'selected'>>) => void;
  toggleRow: (id: number) => void;
  selectRows: (ids: number[], on: boolean) => void;
  clearSelection: () => void;
  toggleColumn: (c: LedgerColumn) => void;
  resetColumns: () => void;

  dismissedInsights: string[];
  dismissInsight: (id: string) => void;
}

export const useSAPStore = create<SAPStore>()(
  persist(
    (set, get) => ({
      filters: EMPTY_FILTERS,
      setFilter: (k, v) => set(s => ({ filters: { ...s.filters, [k]: v }, ledger: { ...s.ledger, page: 1, selected: new Set() } })),
      setFilters: (patch) => set(s => ({ filters: { ...s.filters, ...patch }, ledger: { ...s.ledger, page: 1, selected: new Set() } })),
      clearFilters: () => set(s => ({ filters: { ...EMPTY_FILTERS, portfolio: s.filters.portfolio, phase: s.filters.phase }, ledger: { ...s.ledger, page: 1, selected: new Set() } })),
      activeFilterCount: () => {
        const f = get().filters;
        return (['project', 'state', 'cluster', 'vendor', 'material', 'status'] as const).filter(k => f[k]).length
          + (f.dateFrom || f.dateTo ? 1 : 0) + (f.search ? 1 : 0) + (f.codes.length ? 1 : 0);
      },

      drawers: [],
      openDrawer: (d) => set(s => ({ drawers: [...s.drawers.filter(x => !(x.kind === d.kind && (x as { id?: string }).id === (d as { id?: string }).id)), d] })),
      closeDrawer: () => set(s => ({ drawers: s.drawers.slice(0, -1) })),
      closeAllDrawers: () => set({ drawers: [] }),
      openPO: (id) => get().openDrawer({ kind: 'po', id }),
      openVendor: (id) => get().openDrawer({ kind: 'vendor', id }),
      openMaterial: (id) => get().openDrawer({ kind: 'material', id }),
      openInsight: (id) => get().openDrawer({ kind: 'insight', id }),
      openKpi: (id) => get().openDrawer({ kind: 'kpi', id }),

      watchlist: [],
      isWatched: (kind, id) => get().watchlist.some(w => w.kind === kind && w.id === id),
      toggleWatch: (kind, id, label) => set(s => s.watchlist.some(w => w.kind === kind && w.id === id)
        ? { watchlist: s.watchlist.filter(w => !(w.kind === kind && w.id === id)) }
        : { watchlist: [{ kind, id, label, addedAt: new Date().toISOString() }, ...s.watchlist] }),
      removeWatch: (kind, id) => set(s => ({ watchlist: s.watchlist.filter(w => !(w.kind === kind && w.id === id)) })),

      ledger: { page: 1, size: 25, sort: 'value', order: 'desc', columns: DEFAULT_COLUMNS, selected: new Set() },
      setLedger: (patch) => set(s => ({ ledger: { ...s.ledger, ...patch } })),
      toggleRow: (id) => set(s => { const n = new Set(s.ledger.selected); if (n.has(id)) n.delete(id); else n.add(id); return { ledger: { ...s.ledger, selected: n } }; }),
      selectRows: (ids, on) => set(s => { const n = new Set(s.ledger.selected); ids.forEach(i => on ? n.add(i) : n.delete(i)); return { ledger: { ...s.ledger, selected: n } }; }),
      clearSelection: () => set(s => ({ ledger: { ...s.ledger, selected: new Set() } })),
      toggleColumn: (c) => set(s => ({ ledger: { ...s.ledger, columns: s.ledger.columns.includes(c) ? s.ledger.columns.filter(x => x !== c) : ALL_COLUMNS.filter(x => x === c || s.ledger.columns.includes(x)) } })),
      resetColumns: () => set(s => ({ ledger: { ...s.ledger, columns: DEFAULT_COLUMNS } })),

      dismissedInsights: [],
      dismissInsight: (id) => set(s => ({ dismissedInsights: [...new Set([...s.dismissedInsights, id])], drawers: s.drawers.filter(d => !(d.kind === 'insight' && d.id === id)) })),
    }),
    {
      name: 'akasha.sap-intelligence',
      storage: createJSONStorage(() => localStorage),
      // Only preferences persist. Filters live in the URL; drawers and selection are per visit.
      partialize: (s) => ({ watchlist: s.watchlist, dismissedInsights: s.dismissedInsights, ledger: { columns: s.ledger.columns, size: s.ledger.size } }) as unknown as SAPStore,
      merge: (persisted, current) => {
        const p = persisted as Partial<SAPStore> | undefined;
        return { ...current, watchlist: p?.watchlist ?? [], dismissedInsights: p?.dismissedInsights ?? [],
          ledger: { ...current.ledger, columns: p?.ledger?.columns ?? DEFAULT_COLUMNS, size: p?.ledger?.size ?? 25 } };
      },
    },
  ),
);

/* ── URL ⇄ filters ──
   `portfolio` and `phase` are the top bar's own keys, shared on purpose so the
   header drives this page. Everything else is prefixed to stay out of its way. */
const URL_KEYS: Record<keyof SAPFilters, string> = {
  portfolio: 'portfolio', phase: 'phase', project: 'spr', state: 'sst', cluster: 'scl', dateFrom: 'sdf', dateTo: 'sdt',
  vendor: 'sv', material: 'sm', status: 'sss', search: 'sq', codes: 'sc',
};

export function filtersToParams(f: SAPFilters, base: URLSearchParams): URLSearchParams {
  const p = new URLSearchParams(base);
  (Object.keys(URL_KEYS) as (keyof SAPFilters)[]).forEach(k => {
    const v = f[k];
    const key = URL_KEYS[k];
    if (Array.isArray(v) ? v.length : v) p.set(key, Array.isArray(v) ? v.join(',') : String(v)); else p.delete(key);
  });
  return p;
}

export function paramsToFilters(p: URLSearchParams): SAPFilters {
  const g = (k: keyof SAPFilters) => p.get(URL_KEYS[k]);
  return {
    portfolio: g('portfolio'), phase: g('phase'), project: g('project'), state: g('state'), cluster: g('cluster'),
    dateFrom: g('dateFrom'), dateTo: g('dateTo'), vendor: g('vendor'), material: g('material'),
    status: (g('status') as POStatus | null) ?? null, search: g('search') ?? '',
    codes: (g('codes') ?? '').split(',').filter(Boolean),
  };
}

export const DRAWER_KEY = 'sd'; // e.g. sd=po:4510022800
export function drawerToParam(d: DrawerState | undefined): string | null {
  if (!d || d.kind === 'none' || d.kind === 'filters') return null;
  return 'id' in d ? `${d.kind}:${d.id}` : d.kind;
}
export function paramToDrawer(v: string | null): DrawerState | null {
  if (!v) return null;
  const [kind, ...rest] = v.split(':'); const id = rest.join(':');
  switch (kind) {
    case 'po': case 'vendor': case 'material': case 'insight': return id ? ({ kind, id } as DrawerState) : null;
    case 'kpi': return id ? { kind: 'kpi', id: id as KpiId } : null;
    case 'ask': case 'watchlist': return { kind } as DrawerState;
    default: return null;
  }
}
