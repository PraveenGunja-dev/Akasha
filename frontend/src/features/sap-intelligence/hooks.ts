/* SAP Intelligence — data hooks.

   `useSAPQuery` is a small fetch-with-status cell keyed on the serialised
   filters. It aborts the in-flight request when the key changes, keeps the
   last good result visible during a refetch (so panels don't flash to
   skeleton on every filter tick), and exposes a retry. All React state is
   written from fetch callbacks only; "loading" and "stale" are derived from
   whether the stored result matches the current key. It is deliberately not
   a query library — the app has none, and adding one for one screen is the
   kind of architecture the brief says not to introduce. */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { sapApi, filterParams, SAPApiError } from './api';
import { useSAPStore } from './store';
import type {
  FilterOptions, Geography, Granularity, Insight, LedgerPage, MaterialDetail, MaterialRow,
  Overview, PODetail, SAPFilters, Trends, VendorDetail, VendorRow,
} from './types';

export interface QueryState<T> {
  data: T | null; loading: boolean; error: string | null; refetch: () => void; stale: boolean;
}

const cache = new Map<string, { at: number; data: unknown }>();
const TTL = 5 * 60_000;
const fresh = (key: string) => { const h = cache.get(key); return h && Date.now() - h.at < TTL ? h : undefined; };

interface Result<T> { key: string; data: T | null; error: string | null }

export function useSAPQuery<T>(key: string, fetcher: (signal: AbortSignal) => Promise<T>, enabled = true): QueryState<T> {
  const [res, setRes] = useState<Result<T>>(() => ({ key, data: (fresh(key)?.data as T) ?? null, error: null }));
  const [tick, setTick] = useState(0);
  const cacheKey = `${key}#${tick}`;

  useEffect(() => {
    if (!enabled) return;
    if (tick === 0 && fresh(key)) return; // render reads the cache directly
    const ctrl = new AbortController();
    fetcher(ctrl.signal)
      .then(d => { if (ctrl.signal.aborted) return; cache.set(key, { at: Date.now(), data: d }); setRes({ key: cacheKey, data: d, error: null }); })
      .catch(e => { if (ctrl.signal.aborted) return; setRes(r => ({ key: cacheKey, data: r.data, error: e instanceof SAPApiError ? `${e.status}: ${e.message}` : (e?.message ?? 'Request failed') })); });
    return () => ctrl.abort();
    // The fetcher closes over the same filters that make up `key`; re-running on key is the contract.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, enabled]);

  const refetch = useCallback(() => { cache.delete(key); setTick(t => t + 1); }, [key]);

  const hit = tick === 0 ? fresh(key) : undefined;
  const current = res.key === cacheKey || res.key === key;
  const data = (current ? res.data : null) ?? (hit?.data as T | undefined) ?? res.data ?? null;
  const settled = current || !!hit;
  return {
    data,
    loading: enabled && !settled,
    error: current ? res.error : null,
    stale: enabled && !settled && data != null,
    refetch,
  };
}

export const useFilters = () => useSAPStore(s => s.filters);
const fkey = (f: SAPFilters) => filterParams(f).toString();

export const useOverview = () => { const f = useFilters(); return useSAPQuery<Overview>(`ov:${fkey(f)}`, s => sapApi.overview(f, s)); };
export const useTrends = (g: Granularity) => { const f = useFilters(); return useSAPQuery<Trends>(`tr:${g}:${fkey(f)}`, s => sapApi.trends(f, g, s)); };
export const useVendors = (limit: number) => { const f = useFilters(); return useSAPQuery<{ vendors: VendorRow[]; vendor_count: number }>(`ve:${limit}:${fkey(f)}`, s => sapApi.vendors(f, limit, s)); };
export const useVendor = (name: string | null) => { const f = useFilters(); return useSAPQuery<VendorDetail>(`vd:${name}:${fkey(f)}`, s => sapApi.vendor(name!, f, s), !!name); };
export const useMaterials = (by: 'value' | 'outstanding' | 'consumption' | 'inventory', limit: number) => {
  const f = useFilters();
  return useSAPQuery<{ by: string; materials: MaterialRow[]; material_count: number; no_material_code: MaterialRow | null }>(`ma:${by}:${limit}:${fkey(f)}`, s => sapApi.materials(f, by, limit, s));
};
export const useMaterial = (code: string | null) => { const f = useFilters(); return useSAPQuery<MaterialDetail>(`md:${code}:${fkey(f)}`, s => sapApi.material(code!, f, s), !!code); };
export const useGeography = () => { const f = useFilters(); return useSAPQuery<Geography>(`ge:${fkey(f)}`, s => sapApi.geography(f, s)); };
export const usePO = (po: string | null) => useSAPQuery<PODetail>(`po:${po}`, s => sapApi.po(po!, s), !!po);
export const useFilterOptions = () => useSAPQuery<FilterOptions>('filters', s => sapApi.filters(s));

export const useLedger = () => {
  const f = useFilters();
  const { page, size, sort, order } = useSAPStore(s => s.ledger);
  return useSAPQuery<LedgerPage>(`led:${page}:${size}:${sort}:${order}:${fkey(f)}`, s => sapApi.pos(f, page, size, sort, order, s));
};

/** Rule-based insights load first; the AI note is fetched afterwards and
    merged in, so a slow or absent model never delays the panel. */
export const useInsights = () => {
  const f = useFilters();
  const dismissed = useSAPStore(s => s.dismissedInsights);
  const base = useSAPQuery<{ insights: Insight[]; generatedAt: string }>(`in:${fkey(f)}`, s => sapApi.insights(f, false, s));
  const enrichKey = base.data ? `en:${fkey(f)}` : null;
  const enriched = useSAPQuery<Record<string, Pick<Insight, 'aiNote' | 'aiSource'>>>(enrichKey ?? 'en:none', async s => {
    const r = await sapApi.insights(f, true, s);
    const m: Record<string, Pick<Insight, 'aiNote' | 'aiSource'>> = {};
    r.insights.forEach(i => { if (i.aiNote) m[i.id] = { aiNote: i.aiNote, aiSource: i.aiSource }; });
    return m;
  }, !!enrichKey);
  const insights = useMemo(() => (base.data?.insights ?? []).filter(i => !dismissed.includes(i.id)).map(i => ({ ...i, ...(enriched.data?.[i.id] ?? {}) })), [base.data, dismissed, enriched.data]);
  return { ...base, insights };
};

/** Debounced value — for the search box. */
export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

/** Local mirror of an external string that resets when the external value
    changes — the React-sanctioned "adjust state during render" pattern, so
    no effect is needed. */
export function useMirroredInput(external: string): [string, (v: string) => void] {
  const [st, setSt] = useState({ v: external, from: external });
  if (st.from !== external) { setSt({ v: external, from: external }); return [external, v => setSt({ v, from: external })]; }
  return [st.v, v => setSt({ v, from: external })];
}
