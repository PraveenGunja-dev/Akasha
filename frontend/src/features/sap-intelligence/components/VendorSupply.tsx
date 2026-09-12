import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Truck } from 'lucide-react';
import { ChartFrame, SourceTag } from '../../../components/ui/primitives';
import { useChartTheme } from '../../../lib/chartTheme';
import { useVendors } from '../hooks';
import { useSAPStore } from '../store';
import { fmtCr, fmtNum } from '../format';
import { ErrorBox, Empty } from './Drawer';
import { Seg } from './ConsumptionTrend';
import type { ChartParam } from '../types';

/* Where the outstanding PO value sits, by vendor. Delivered and
   still-to-deliver partition the ordered value exactly (ZSPS). One hue in
   two weights — one quantity in two parts, not two categories. Click a bar
   to open the vendor. */
export const VendorSupply = () => {
  const [limit, setLimit] = useState<10 | 20 | 0>(10);
  const { data, loading, error, refetch } = useVendors(limit || 0);
  const openVendor = useSAPStore(s => s.openVendor);
  const { themeName, chrome, categorical, sequential } = useChartTheme();
  const host = useRef<HTMLDivElement>(null); const chart = useRef<ReactECharts>(null);
  const [hostH, setHostH] = useState(0);
  useEffect(() => { if (!host.current) return; const ro = new ResizeObserver(([e]) => { setHostH(e.contentRect.height); chart.current?.getEchartsInstance().resize(); }); ro.observe(host.current); return () => ro.disconnect(); }, []);

  const rows = useMemo(() => (data?.vendors ?? []).slice().reverse(), [data]);
  const max = Math.max(0, ...rows.map(r => r.ordered_cr));
  const step = max > 20000 ? 5000 : max > 8000 ? 2000 : max > 3000 ? 1000 : max > 1000 ? 500 : max > 300 ? 100 : 50;
  const axisMax = Math.ceil((max * 1.12) / step) * step || step;
  const outstandingColor = themeName.includes('dark') ? sequential[4] : sequential[2];

  const option = useMemo(() => ({
    animationDuration: 200,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: chrome.surface2, borderColor: chrome.borderSubtle, borderWidth: 1, padding: [10, 14], textStyle: { color: chrome.fgPrimary, fontSize: 12 },
      formatter: (ps: ChartParam[]) => { const g = rows[ps[0].dataIndex]; if (!g) return '';
        const row = (l: string, v: string, b = false) => `<div style="display:flex;justify-content:space-between;gap:24px;${b ? 'font-weight:600' : ''}"><span style="color:${chrome.fgSecondary}">${l}</span><span style="font-variant-numeric:tabular-nums">${v}</span></div>`;
        return `<div style="font-weight:600;margin-bottom:6px">${g.name}</div>` + row('Ordered', fmtCr(g.ordered_cr), true) + row('Delivered', fmtCr(g.delivered_cr)) + row('Still to deliver', fmtCr(g.outstanding_cr)) + row('Purchase orders', fmtNum(g.pos)) + row('Share of PO value', `${g.share_pct}%`) + row('Share of outstanding', `${g.outstanding_share_pct}%`)
          + `<div style="margin-top:6px;padding-top:6px;border-top:1px solid ${chrome.borderSubtle};color:${chrome.fgSecondary}">${g.delivered_pct}% delivered · click to open vendor</div>`; } },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 10, itemGap: 16, textStyle: { color: chrome.fgSecondary, fontSize: 12 } },
    grid: { left: 0, right: 56, top: 28, bottom: 0, containLabel: true },
    xAxis: { type: 'value', max: axisMax, interval: step, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: chrome.gridLine } },
      axisLabel: { color: chrome.fgTertiary, fontSize: 11, formatter: (v: number) => v === 0 ? '0' : v >= 1000 ? `${(v / 1000).toFixed(v % 1000 ? 1 : 0)}k` : String(v) } },
    yAxis: { type: 'category', data: rows.map(r => r.name), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: chrome.fgPrimary, fontSize: 12, width: 190, overflow: 'truncate' }, triggerEvent: true },
    series: [
      { name: 'Delivered', type: 'bar', stack: 'v', barWidth: 16, data: rows.map(r => r.delivered_cr), itemStyle: { color: categorical[0] }, cursor: 'pointer' },
      { name: 'Still to deliver', type: 'bar', stack: 'v', barWidth: 16, data: rows.map(r => r.outstanding_cr), itemStyle: { color: outstandingColor }, cursor: 'pointer',
        label: { show: true, position: 'right', distance: 8, color: chrome.fgSecondary, fontSize: 11, formatter: (p: ChartParam) => `${rows[p.dataIndex]?.delivered_pct ?? 0}%` } },
    ],
  }), [rows, chrome, categorical, outstandingColor, axisMax, step]);

  const onEvents = useMemo(() => ({
    click: (p: ChartParam) => { const name = p.componentType === 'yAxis' ? String(p.value) : rows[p.dataIndex]?.name; if (name) openVendor(name); },
  }), [rows, openVendor]);

  return (
    <ChartFrame icon={Truck} eyebrow="Supply position" title="Where the outstanding PO value sits, by vendor"
      right={<>
        <Seg<'10' | '20' | '0'> label="Vendor count" value={String(limit) as '10' | '20' | '0'} onChange={v => setLimit(Number(v) as 10 | 20 | 0)} opts={[['10', 'Top 10'], ['20', 'Top 20'], ['0', 'All']]} />
        {data && <span className="hidden text-[12px] text-fg-tertiary lg:inline">{data.vendors.length} of {fmtNum(data.vendor_count)} · ₹ Cr</span>}
        <SourceTag system="SAP" stamp="ZSPS" />
      </>}
      className="h-full"
    >
      <div ref={host} className="custom-scrollbar h-full w-full overflow-y-auto">
        {error ? <ErrorBox message={error} onRetry={refetch} />
          : loading && !data ? <div className="h-full w-full animate-pulse rounded-md bg-surface-sunken" aria-busy />
            : rows.length === 0 ? <Empty message="No purchase orders in this scope." />
              : <div role="img" aria-label={`Delivered and still-to-deliver PO value for ${rows.length} vendors`} className="w-full"
                  style={{ height: Math.max(hostH, 28 + rows.length * (limit === 0 ? 22 : 30)) }}>
                <ReactECharts ref={chart} theme={themeName} option={option} notMerge onEvents={onEvents} style={{ height: '100%', width: '100%' }} />
              </div>}
      </div>
    </ChartFrame>
  );
};
