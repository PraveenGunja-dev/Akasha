import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { MapPin } from 'lucide-react';
import { ChartFrame, SourceTag, cx } from '../../../components/ui/primitives';
import { useChartTheme } from '../../../lib/chartTheme';
import { ensureIndiaMap } from '../../dashboard/indiaMap';
import { useGeography } from '../hooks';
import { useSAPStore } from '../store';
import { fmtCr, fmtNum, fmtPct } from '../format';
import { ErrorBox, Empty, Btn } from './Drawer';
import type { ChartParam } from '../types';

/* India, by PO value. Attribution runs WBS prefix → project_mapping →
   cluster → state, which covers 99.6% of PO value; the remainder is shown
   as a number, not hidden. This portfolio sits in two states, and the map
   says so — it does not decorate the other 32.

   Bubbles sit on the sites the clusters are built on (Khavda, Mandvi/Mundra,
   Bandha), sized by PO value; the two states are shaded underneath. The
   same India outline drives the Network Overview on the executive page. */

type Metric = 'ordered_cr' | 'outstanding_cr' | 'delivered_pct';
const METRIC_LABEL: Record<Metric, string> = { ordered_cr: 'PO value', outstanding_cr: 'Still to deliver', delivered_pct: '% delivered' };

export const LocationMap = () => {
  const { data, loading, error, refetch } = useGeography();
  const filters = useSAPStore(s => s.filters);
  const setFilters = useSAPStore(s => s.setFilters);
  const [metric, setMetric] = useState<Metric>('ordered_cr');
  const [mapTick, setMapTick] = useState(0);
  const [mapState, setMapState] = useState<{ tick: number; status: true | string }>({ tick: -1, status: true });
  const ready: boolean | string = mapState.tick === mapTick ? mapState.status : false; // true | false (loading) | error message
  const { themeName, chrome, sequential, categorical } = useChartTheme();
  const host = useRef<HTMLDivElement>(null); const chart = useRef<ReactECharts>(null);
  useEffect(() => { let on = true; ensureIndiaMap().then(() => { if (on) setMapState({ tick: mapTick, status: true }); }).catch((e: unknown) => { if (on) setMapState({ tick: mapTick, status: `Map outline could not be loaded (${e instanceof Error ? e.message : 'unknown error'}).` }); }); return () => { on = false; }; }, [mapTick]);
  useEffect(() => { if (!host.current) return; const ro = new ResizeObserver(() => chart.current?.getEchartsInstance().resize()); ro.observe(host.current); return () => ro.disconnect(); }, []);

  const states = useMemo(() => data?.states ?? [], [data]);
  const clusters = useMemo(() => (data?.clusters ?? []).filter(c => c.lat != null && c.lng != null), [data]);
  const byState = useMemo(() => Object.fromEntries(states.map(s => [s.state, s])), [states]);
  const max = Math.max(1, ...states.map(s => s[metric]));
  const cMax = Math.max(1, ...clusters.map(c => c.ordered_cr));

  const option = useMemo(() => ({
    animationDuration: 200,
    tooltip: { trigger: 'item', backgroundColor: chrome.surface2, borderColor: chrome.borderSubtle, borderWidth: 1, padding: [10, 14], textStyle: { color: chrome.fgPrimary, fontSize: 12 },
      formatter: (p: ChartParam & { seriesType?: string; data?: { c?: (typeof clusters)[number] } }) => {
        const row = (l: string, v: string) => `<div style="display:flex;justify-content:space-between;gap:24px"><span style="color:${chrome.fgSecondary}">${l}</span><span style="font-variant-numeric:tabular-nums">${v}</span></div>`;
        if (p.seriesType === 'scatter' && p.data?.c) { const c = p.data.c;
          return `<div style="font-weight:600;margin-bottom:6px">${c.cluster}<span style="font-weight:400;color:${chrome.fgTertiary}"> · ${c.site ?? ''}</span></div>` + row('PO value', fmtCr(c.ordered_cr)) + row('Delivered', `${fmtCr(c.delivered_cr)} (${fmtPct(c.delivered_pct, 0)})`) + row('Still to deliver', fmtCr(c.outstanding_cr)) + row('Purchase orders', fmtNum(c.pos)) + (c.change_pct != null ? row('PO value, 12m vs prior', `${c.change_pct > 0 ? '+' : ''}${c.change_pct}%`) : '') + `<div style="margin-top:6px;color:${chrome.fgTertiary}">click to filter the page to ${c.cluster}</div>`; }
        const s = byState[p.name]; if (!s) return `<div style="font-weight:600">${p.name}</div><div style="color:${chrome.fgSecondary}">No PO value attributed</div>`;
        return `<div style="font-weight:600;margin-bottom:6px">${p.name}</div>` + row('PO value', fmtCr(s.ordered_cr)) + row('Delivered', fmtCr(s.delivered_cr)) + row('Still to deliver', fmtCr(s.outstanding_cr)) + row('% delivered', fmtPct(s.delivered_pct)) + row('Purchase orders', fmtNum(s.pos)) + `<div style="margin-top:6px;color:${chrome.fgTertiary}">click to filter the page to ${p.name}</div>`; } },
    visualMap: { show: false, min: 0, max, seriesIndex: 0, inRange: { color: [sequential[1], sequential[3], sequential[5]] } },
    geo: { map: 'india', roam: false, aspectScale: 0.9, layoutCenter: ['50%', '52%'], layoutSize: '112%', silent: true, itemStyle: { areaColor: 'transparent', borderColor: 'transparent' } },
    series: [
      {
        type: 'map', map: 'india', roam: false, aspectScale: 0.9, layoutCenter: ['50%', '52%'], layoutSize: '112%',
        selectedMode: 'single', select: { itemStyle: { areaColor: sequential[6], borderColor: chrome.fgPrimary, borderWidth: 1.2 }, label: { show: false } },
        itemStyle: { areaColor: chrome.surface1, borderColor: chrome.axisLine, borderWidth: 0.6 },
        emphasis: { itemStyle: { areaColor: sequential[4], borderColor: chrome.fgPrimary, borderWidth: 1 }, label: { show: false } },
        label: { show: false },
        data: states.map(s => ({ name: s.state, value: s[metric], selected: filters.state === s.state })),
      },
      {
        /* Sites, on the geo above. Area ∝ PO value. */
        type: 'scatter', coordinateSystem: 'geo', z: 3,
        symbolSize: (v: number[]) => 12 + 34 * Math.sqrt((v[2] ?? 0) / cMax),
        itemStyle: { color: categorical[0], borderColor: '#fff', borderWidth: 1.5, opacity: 0.9 },
        emphasis: { scale: 1.15, itemStyle: { opacity: 1, borderColor: chrome.fgPrimary } },
        label: { show: true, position: 'right', distance: 6, color: chrome.fgPrimary, fontSize: 11, formatter: (p: ChartParam & { data?: { c?: (typeof clusters)[number] } }) => p.data?.c ? `${p.data.c.cluster} · ${fmtCr(p.data.c.ordered_cr)}` : '', backgroundColor: 'rgba(255,255,255,.85)', padding: [2, 5], borderRadius: 4 },
        data: clusters.map(c => ({ name: c.cluster, value: [c.lng, c.lat, c.ordered_cr], c, itemStyle: filters.cluster === c.cluster ? { borderColor: chrome.fgPrimary, borderWidth: 2.5 } : undefined })),
      },
    ],
  }), [states, clusters, byState, metric, max, cMax, chrome, sequential, categorical, filters.state, filters.cluster]);

  const onEvents = useMemo(() => ({
    click: (p: ChartParam & { seriesType?: string; data?: { c?: (typeof clusters)[number] } }) => {
      if (p.seriesType === 'scatter' && p.data?.c) { const c = p.data.c; setFilters({ cluster: filters.cluster === c.cluster ? null : c.cluster, state: filters.cluster === c.cluster ? null : c.state }); return; }
      if (!byState[p.name]) return; setFilters({ state: filters.state === p.name ? null : p.name, cluster: null });
    },
  }), [byState, filters.state, filters.cluster, setFilters]);

  const visibleClusters = clusters.filter(c => !filters.state || c.state === filters.state);
  const un = data?.unattributed;

  return (
    <ChartFrame icon={MapPin} eyebrow="Location" title="PO value by state and site" className="h-full"
      right={<>
        <div role="radiogroup" aria-label="Map measure" className="inline-flex rounded-md border border-border-default bg-surface-1 p-0.5">
          {(Object.keys(METRIC_LABEL) as Metric[]).map(m => (
            <button key={m} type="button" role="radio" aria-checked={metric === m} onClick={() => setMetric(m)}
              className={cx('h-6 rounded px-2 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', metric === m ? 'bg-surface-sunken font-medium text-fg-primary' : 'text-fg-tertiary hover:text-fg-primary')}>{METRIC_LABEL[m]}</button>))}
        </div>
        <SourceTag system="SAP" stamp="ZSPS · mapping" />
      </>}
    >
      <div ref={host} className="flex h-full w-full gap-4">
        {error ? <ErrorBox message={error} onRetry={refetch} />
          : typeof ready === 'string' ? <ErrorBox message={ready} onRetry={() => setMapTick(t => t + 1)} />
          : (loading && !data) || !ready ? <div className="h-full w-full animate-pulse rounded-md bg-surface-sunken" aria-busy />
            : states.length === 0 ? <Empty message="No PO value can be attributed to a state for the selected filters." />
              : <>
                <div className="min-h-0 min-w-0 flex-1" role="img" aria-label={`Map of India showing ${METRIC_LABEL[metric]} for ${states.map(s => s.state).join(' and ')} and ${clusters.length} sites`}>
                  <ReactECharts ref={chart} theme={themeName} option={option} notMerge onEvents={onEvents} style={{ height: '100%', width: '100%' }} />
                </div>
                <div className="flex w-[220px] shrink-0 flex-col gap-2 overflow-y-auto">
                  {states.map(s => (
                    <button key={s.state} type="button" onClick={() => setFilters({ state: filters.state === s.state ? null : s.state, cluster: null })} aria-pressed={filters.state === s.state}
                      className={cx('rounded-md border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', filters.state === s.state ? 'border-primary bg-primary-50' : 'border-border-subtle bg-surface-0 hover:border-border-strong')}>
                      <div className="flex items-baseline justify-between"><span className="text-[13px] font-semibold text-fg-primary">{s.state}</span><span className="text-[11px] text-fg-tertiary">{fmtNum(s.pos)} POs</span></div>
                      <div className="mt-0.5 text-[15px] font-semibold tabular-nums text-fg-primary">{metric === 'delivered_pct' ? fmtPct(s.delivered_pct) : fmtCr(s[metric])}</div>
                      <div className="mt-1 h-1 overflow-hidden rounded-sm bg-surface-sunken"><div className="h-full bg-primary" style={{ width: `${s.delivered_pct}%` }} /></div>
                      <div className="mt-0.5 text-[11px] text-fg-tertiary">{fmtPct(s.delivered_pct, 0)} delivered</div>
                    </button>))}
                  {visibleClusters.length > 0 && (
                    <div className="mt-1 border-t border-border-subtle pt-2">
                      <div className="section-label mb-1">Sites{filters.state ? ` · ${filters.state}` : ''}</div>
                      {visibleClusters.map(c => (
                        <button key={c.cluster} type="button" onClick={() => setFilters({ cluster: filters.cluster === c.cluster ? null : c.cluster, state: c.state })} aria-pressed={filters.cluster === c.cluster}
                          className={cx('flex w-full items-center justify-between rounded px-2 py-1 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', filters.cluster === c.cluster ? 'bg-primary-50 text-primary-700' : 'text-fg-secondary hover:bg-surface-sunken')}>
                          <span className="truncate">{c.cluster}</span><span className="tabular-nums">{fmtCr(c.ordered_cr)}</span>
                        </button>))}
                    </div>)}
                  {un && un.ordered_cr > 0 && (
                    <div className="mt-auto rounded-md border border-dashed border-border-default px-2.5 py-1.5 text-[11px] text-fg-tertiary">
                      <span className="font-medium text-fg-secondary">{fmtCr(un.ordered_cr)}</span> not attributed to a state ({Object.entries(un.reason).map(([k, v]) => `${k}: ${fmtCr(v)}`).join('; ')}).
                    </div>)}
                  {(filters.state || filters.cluster) && <Btn variant="ghost" className="justify-center" onClick={() => setFilters({ state: null, cluster: null })}>Clear location</Btn>}
                </div>
              </>}
      </div>
    </ChartFrame>
  );
};
