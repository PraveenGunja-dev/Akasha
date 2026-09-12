/* SAP Intelligence — API client. One place that knows the URL shape; every
   hook calls through here so a filter is serialised exactly once. */
import type {
  FilterOptions, Geography, Granularity, Insight, LedgerPage, MaterialDetail, MaterialRow,
  Overview, PODetail, SAPFilters, SearchResult, Trends, VendorDetail, VendorRow,
} from './types';

const BASE = '/akasha/api/sap';

export class SAPApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export function filterParams(f: SAPFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.portfolio) p.set('portfolio', f.portfolio);
  if (f.project) p.set('project', f.project);
  if (f.state) p.set('state', f.state);
  if (f.cluster) p.set('cluster', f.cluster);
  if (f.dateFrom) p.set('date_from', f.dateFrom);
  if (f.dateTo) p.set('date_to', f.dateTo);
  if (f.vendor) p.set('vendor', f.vendor);
  if (f.material) p.set('material', f.material);
  if (f.status) p.set('status', f.status);
  if (f.search) p.set('q', f.search);
  if (f.codes.length) p.set('codes', f.codes.join(','));
  return p;
}

async function get<T>(path: string, params?: URLSearchParams, signal?: AbortSignal): Promise<T> {
  const qs = params && [...params.keys()].length ? `?${params}` : '';
  const r = await fetch(`${BASE}${path}${qs}`, { signal });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* keep statusText */ }
    throw new SAPApiError(r.status, detail);
  }
  return r.json();
}

export const sapApi = {
  overview: (f: SAPFilters, s?: AbortSignal) => get<Overview>('/overview', filterParams(f), s),
  trends: (f: SAPFilters, g: Granularity, s?: AbortSignal) => {
    const p = filterParams(f); p.set('granularity', g); return get<Trends>('/trends', p, s);
  },
  vendors: (f: SAPFilters, limit: number, s?: AbortSignal) => {
    const p = filterParams(f); p.set('limit', String(limit)); return get<{ vendors: VendorRow[]; vendor_count: number }>('/vendors', p, s);
  },
  vendor: (name: string, f: SAPFilters, s?: AbortSignal) => get<VendorDetail>(`/vendors/${encodeURIComponent(name)}`, filterParams(f), s),
  materials: (f: SAPFilters, by: 'value' | 'outstanding' | 'consumption' | 'inventory', limit: number, s?: AbortSignal) => {
    const p = filterParams(f); p.set('by', by); p.set('limit', String(limit));
    return get<{ by: string; materials: MaterialRow[]; material_count: number; no_material_code: MaterialRow | null }>('/materials', p, s);
  },
  material: (code: string, f: SAPFilters, s?: AbortSignal) => get<MaterialDetail>(`/materials/${encodeURIComponent(code)}`, filterParams(f), s),
  geography: (f: SAPFilters, s?: AbortSignal) => get<Geography>('/geography', filterParams(f), s),
  pos: (f: SAPFilters, page: number, size: number, sort: string, order: 'asc' | 'desc', s?: AbortSignal) => {
    const p = filterParams(f); p.set('page', String(page)); p.set('size', String(size)); p.set('sort', sort); p.set('order', order);
    return get<LedgerPage>('/pos', p, s);
  },
  po: (po: string, s?: AbortSignal) => get<PODetail>(`/pos/${encodeURIComponent(po)}`, undefined, s),
  search: (q: string, s?: AbortSignal) => { const p = new URLSearchParams({ q }); return get<{ results: SearchResult[] }>('/search', p, s); },
  filters: (s?: AbortSignal) => get<FilterOptions>('/filters', undefined, s),
  insights: (f: SAPFilters, enrich: boolean, s?: AbortSignal) => {
    const p = filterParams(f); if (enrich) p.set('enrich', 'true'); return get<{ insights: Insight[]; generatedAt: string }>('/insights', p, s);
  },
  ask: async (question: string, context: unknown, history: { role: string; content: string }[]) => {
    const r = await fetch(`${BASE}/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, context, history }) });
    if (!r.ok) { let d = r.statusText; try { d = (await r.json()).detail ?? d; } catch { /* */ } throw new SAPApiError(r.status, d); }
    return r.json() as Promise<{ answer: string; model: string }>;
  },
};
