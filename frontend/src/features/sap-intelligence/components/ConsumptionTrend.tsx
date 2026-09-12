import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Activity, Maximize2, Minimize2 } from 'lucide-react';
import { ChartFrame, SourceTag, cx } from '../../../components/ui/primitives';
import { useChartTheme } from '../../../lib/chartTheme';
import { useTrends } from '../hooks';
import { fmtCr, fmtNum, fmtPct } from '../format';
import { Btn, ErrorBox, Empty } from './Drawer';
import type { ChartParam, Granularity, TrendBucket, TrendEvent } from '../types';

type Mode = 'value' | 'quantity';

export const Seg = <T extends string>({ value, onChange, opts, label }: { value: T; onChange: (v: T) => void; opts: [T, string][]; label: string }) => (
  <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-border-default bg-surface-1 p-0.5">
    {opts.map(([v, l]) => (
      <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
        className={cx('h-6 rounded px-2 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', value === v ? 'bg-surface-sunken font-medium text-fg-primary' : 'text-fg-tertiary hover:text-fg-primary')}>{l}</button>
    ))}
  </div>
);

/* Value and quantity are never on one axis: ₹ Cr reconciles across
   materials, units do not. The mode toggle swaps the series set rather than
   adding a second axis that invites reading one against the other. */
const SERIES: Record<Mode, { key: keyof TrendBucket; name: string; kind: 'bar' | 'line'; dashed?: boolean }[]> = {
  value: [
    { key: 'ordered_cr', name: 'PO value ordered', kind: 'line' },
    { key: 'delivered_cr', name: 'Delivered value', kind: 'line' },
    { key: 'consumed_cr', name: 'Consumed on site (MB51)', kind: 'line' },
  ],
  quantity: [
    { key: 'consumed_qty', name: 'Consumed qty (MB51)', kind: 'bar' },
    { key: 'reversal_qty', name: 'Reversals (MB51)', kind: 'bar' },
    { key: 'inventory_qty', name: 'Inventory on hand (MB52, reconstructed)', kind: 'line', dashed: true },
  ],
};

export const ConsumptionTrend = ({ onEvent }: { onEvent: (e: TrendEvent, b: TrendBucket) => void }) => {
  const [granularity, setGranularity] = useState<Granularity>('month');
  const [mode, setMode] = useState<Mode>('value');
  const [tall, setTall] = useState(false);
  const { data, loading, error, refetch } = useTrends(granularity);
  const { themeName, chrome, categorical, sequential } = useChartTheme();
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<ReactECharts>(null);
  useEffect(() => {
    if (!host.current) return;
    const ro = new ResizeObserver(() => chart.current?.getEchartsInstance().resize());
    ro.observe(host.current); return () => ro.disconnect();
  }, []);

  const series = useMemo(() => data?.series ?? [], [data]);
  const events = useMemo(() => (data?.events ?? []).filter(e => SERIES[mode].some(s => s.key === e.series)), [data, mode]);

  // Computed metrics for the current window (last bucket vs previous).
  const last = series[series.length - 1]; const prev = series[series.length - 2];
  const totals = useMemo(() => series.reduce((a, r) => ({ o: a.o + r.ordered_cr, d: a.d + r.delivered_cr, c: a.c + r.consumed_cr }), { o: 0, d: 0, c: 0 }), [series]);
  const strip = [
    { label: 'PO utilisation', value: fmtPct(totals.o ? (totals.d / totals.o) * 100 : 0), sub: 'delivered ÷ ordered, window' },
    { label: 'Consumption vs delivered', value: fmtPct(totals.d ? (totals.c / totals.d) * 100 : 0), sub: 'MB51 issued ÷ ZSPS delivered' },
    { label: `Last ${granularity} change`, value: last?.ordered_change_pct == null ? '—' : `${last.ordered_change_pct > 0 ? '+' : ''}${last.ordered_change_pct.toFixed(0)}%`, sub: `PO value, ${last?.bucket ?? ''} vs ${prev?.bucket ?? ''}` },
    { label: 'Inventory cover', value: (() => { const b = series.slice(-6); const burn = b.reduce((a, r) => a + r.consumed_qty, 0) / (b.length || 1); return burn ? `${(((last?.inventory_qty ?? 0) / burn)).toFixed(1)} mo` : '—'; })(), sub: 'MB52 qty ÷ 6-bucket avg issue' },
  ];

  const option = useMemo(() => {
    const defs = SERIES[mode];
    const colors = [categorical[0], sequential[3], categorical[2]];
    const evByBucket = new Map<string, TrendEvent[]>();
    events.forEach(e => evByBucket.set(e.bucket, [...(evByBucket.get(e.bucket) ?? []), e]));
    return {
      animationDuration: 200,
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'cross', label: { backgroundColor: chrome.surface2, color: chrome.fgPrimary, borderColor: chrome.borderSubtle }, crossStyle: { color: chrome.axisLine } },
        backgroundColor: chrome.surface2, borderColor: chrome.borderSubtle, borderWidth: 1, padding: [10, 14],
        textStyle: { color: chrome.fgPrimary, fontSize: 12 },
        formatter: (ps: ChartParam[]) => {
          const b = series[ps[0]?.dataIndex]; if (!b) return '';
          const row = (l: string, v: string) => `<div style="display:flex;justify-content:space-between;gap:24px"><span style="color:${chrome.fgSecondary}">${l}</span><span style="font-variant-numeric:tabular-nums">${v}</span></div>`;
          let html = `<div style="font-weight:600;margin-bottom:6px">${b.bucket}</div>`;
          if (mode === 'value') html += row('PO value ordered', fmtCr(b.ordered_cr)) + row('Delivered', fmtCr(b.delivered_cr)) + row('Consumed on site', fmtCr(b.consumed_cr)) + row('POs raised', fmtNum(b.pos)) + row('Utilisation', fmtPct(b.utilisation_pct));
          else html += row('Consumed qty', fmtNum(Math.round(b.consumed_qty))) + row('Reversals', fmtNum(Math.round(b.reversal_qty))) + row('Inventory on hand', fmtNum(Math.round(b.inventory_qty)));
          if (b.ordered_change_pct != null) html += row('PO value vs previous', `${b.ordered_change_pct > 0 ? '+' : ''}${b.ordered_change_pct}%`);
          const ev = evByBucket.get(b.bucket);
          if (ev?.length) html += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid ${chrome.borderSubtle};color:${chrome.fgSecondary}">${ev.map(e => `● ${e.label}`).join('<br/>')}<br/><span style="opacity:.7">click the marker to see why</span></div>`;
          return html;
        },
      },
      legend: { top: 0, left: 0, itemWidth: 10, itemHeight: 10, itemGap: 16, textStyle: { color: chrome.fgSecondary, fontSize: 12 } },
      grid: { left: 8, right: 16, top: 34, bottom: 44, containLabel: true },
      /* Brushable range: drag the handles to zoom a period; the strip below recomputes. */
      dataZoom: [{ type: 'inside', zoomOnMouseWheel: false, moveOnMouseMove: true }, { type: 'slider', height: 18, bottom: 6, borderColor: chrome.borderSubtle, backgroundColor: chrome.surface1, fillerColor: `${categorical[0]}22`, handleStyle: { color: categorical[0] }, textStyle: { color: chrome.fgTertiary, fontSize: 10 }, dataBackground: { lineStyle: { color: chrome.axisLine }, areaStyle: { color: chrome.gridLine } } }],
      xAxis: { type: 'category', data: series.map(s => s.bucket), axisLine: { lineStyle: { color: chrome.axisLine } }, axisTick: { show: false }, axisLabel: { color: chrome.fgTertiary, fontSize: 11, hideOverlap: true } },
      yAxis: { type: 'value', axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: chrome.gridLine } },
        axisLabel: { color: chrome.fgTertiary, fontSize: 11, formatter: (v: number) => mode === 'value' ? (v >= 1000 ? `${(v / 1000).toFixed(v % 1000 ? 1 : 0)}k` : String(v)) : (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)) } },
      series: defs.map((d, i) => ({
        name: d.name, type: d.kind, data: series.map(s => s[d.key]), barMaxWidth: 22, barGap: '10%',
        smooth: 0.35, showSymbol: false, symbol: 'circle', symbolSize: 7, itemStyle: { color: colors[i] },
        lineStyle: d.kind === 'line' ? { color: colors[i], width: 2.2, type: d.dashed ? 'dashed' : 'solid' } : undefined,
        areaStyle: d.kind === 'line' && !d.dashed ? { color: `${colors[i]}14` } : undefined,
        emphasis: { focus: 'series', lineStyle: { width: 3.2 } },
        ...(i === 0 ? {
          markPoint: {
            symbol: 'circle', symbolSize: 12,
            data: events.map(e => { const idx = series.findIndex(s => s.bucket === e.bucket); const val = series[idx]?.[e.series] ?? 0;
              return { name: e.label, coord: [idx, val], value: e.label, itemStyle: { color: e.kind === 'up' ? categorical[2] : categorical[1], borderColor: chrome.surface1, borderWidth: 2 }, label: { show: false }, __event: e }; }),
          },
        } : {}),
      })),
    };
  }, [series, events, mode, chrome, categorical, sequential]);

  const onEvents = useMemo(() => ({
    click: (p: ChartParam) => { if (p.componentType === 'markPoint' && p.data?.__event) { const e = p.data.__event; const b = series.find(s => s.bucket === e.bucket); if (b) onEvent(e, b); } },
  }), [series, onEvent]);

  return (
    <ChartFrame
      icon={Activity} eyebrow="Consumption trend" title="PO value, deliveries and site consumption over time"
      right={<>
        <Seg label="Measure" value={mode} onChange={setMode} opts={[['value', '₹ value'], ['quantity', 'Quantity']]} />
        <Seg label="Granularity" value={granularity} onChange={setGranularity} opts={[['month', 'Monthly'], ['quarter', 'Quarterly'], ['year', 'Yearly']]} />
        <Btn variant="ghost" onClick={() => setTall(t => !t)} aria-label={tall ? 'Collapse chart' : 'Expand chart'}>{tall ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}</Btn>
        <SourceTag system="SAP" stamp={mode === 'value' ? 'ZSPS · MB51' : 'MB51 · MB52'} />
      </>}
      className={cx('h-full', tall && 'min-h-[560px]')}
    >
      <div ref={host} className="flex h-full w-full flex-col">
        {error ? <ErrorBox message={error} onRetry={refetch} />
          : loading && !data ? <div className="h-full w-full animate-pulse rounded-md bg-surface-sunken" aria-busy />
            : series.length === 0 ? <Empty message="No dated PO or consumption records for the selected filters." />
              : <>
                <div className="min-h-0 flex-1" role="img" aria-label={`${mode === 'value' ? 'PO value, delivered value and consumption' : 'Consumed quantity, reversals and inventory'} by ${granularity}, ${series[0].bucket} to ${series[series.length - 1].bucket}`}>
                  <ReactECharts ref={chart} theme={themeName} option={option} notMerge onEvents={onEvents} style={{ height: '100%', width: '100%' }} />
                </div>
                <div className="mt-2 grid shrink-0 grid-cols-2 gap-2 border-t border-border-subtle pt-2 md:grid-cols-4">
                  {strip.map(s => (
                    <div key={s.label} className="min-w-0">
                      <div className="text-[11px] text-fg-tertiary">{s.label}</div>
                      <div className="text-[15px] font-semibold tabular-nums leading-tight text-fg-primary">{s.value}</div>
                      <div className="truncate text-[11px] text-fg-tertiary">{s.sub}</div>
                    </div>
                  ))}
                </div>
                {events.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Detected events">
                    {events.slice(-6).map((e, i) => (
                      <button key={i} type="button" onClick={() => { const b = series.find(s => s.bucket === e.bucket); if (b) onEvent(e, b); }}
                        className="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-surface-0 px-2 py-0.5 text-[12px] text-fg-secondary hover:border-border-strong hover:text-fg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                        <span className={cx('h-1.5 w-1.5 rounded-full', e.kind === 'up' ? 'bg-accent-500' : 'bg-secondary-500')} />{e.label} · {e.bucket}
                      </button>
                    ))}
                  </div>
                )}
              </>}
      </div>
    </ChartFrame>
  );
};
