import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { LayoutList, Boxes, Truck } from 'lucide-react';
import { cx } from '../../components/ui/primitives/cx';
import { useChartTheme } from '../../lib/chartTheme';

/* ═══════════════════════════════════════════════════════════════════════════
   SAP MATERIAL PIPELINE — value flowing from order to site

   Two corrections over the quantity chart this replaces:

   1. VALUE, NOT QUANTITY. mt_poamount mixes units of measure across lines, so
      adding quantities adds different things. The columns show it: ordered
      354,213,226 against still-to-deliver 380,898,647 and delivered
      671,042,584 — figures that cannot all describe the same orders. The
      VALUE columns reconcile exactly (delivered + in transit = ordered), so
      value is what a stacked bar can honestly carry.

   2. STAGES THAT PARTITION. The old stack was PO Raised + In-Transit +
      Inventory. "PO raised" already CONTAINS what is in transit, so the bar
      counted the same money twice and every total was inflated. Delivered and
      In transit are disjoint and sum to ordered, so the bar length is the
      order value and the split is how far it has travelled.
   ═══════════════════════════════════════════════════════════════════════════ */

type Mode = 'project' | 'category' | 'supplier';

interface Group {
  name: string;
  ordered_cr: number;
  delivered_cr: number;
  in_transit_cr: number;
  pos: number;
  delivered_pct: number;
}

const CR = 10000000;
const fmtCr = (n: number) => (n >= 1000 ? Math.round(n).toLocaleString('en-IN') : n.toFixed(1));

const TABS: { key: Mode; label: string; icon: any }[] = [
  { key: 'project', label: 'By Project', icon: LayoutList },
  { key: 'category', label: 'By Category', icon: Boxes },
  { key: 'supplier', label: 'By Supplier', icon: Truck },
];

export default function MaterialPipelinePanel({ projects }: { projects: any[] }) {
  const [mode, setMode] = useState<Mode>('project');
  const [remote, setRemote] = useState<Record<string, Group[]>>({});
  const [loading, setLoading] = useState(false);
  const { themeName, status: statusColors, chrome } = useChartTheme();
  const plotRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    if (mode === 'project' || remote[mode]) return;
    let live = true;
    setLoading(true);
    fetch(`/akasha/api/financials/material-breakdown?by=${mode}&limit=6`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (live) { setRemote((m) => ({ ...m, [mode]: d.groups || [] })); setLoading(false); } })
      .catch(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [mode, remote]);

  useEffect(() => {
    const el = plotRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    let frame = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        try { chartRef.current?.getEchartsInstance?.().resize(); } catch { /* not mounted */ }
      });
    });
    ro.observe(el);
    return () => { cancelAnimationFrame(frame); ro.disconnect(); };
  }, []);

  /* By project comes from the dashboard payload, which already carries the
     per-project PO value and delivered value. */
  const byProject: Group[] = useMemo(() => {
    return (projects || [])
      .map((p: any) => {
        const ordered_cr = (p.sap?.po_value || 0) / CR;
        const delivered_cr = p.sap?.po_delivered_cr || 0;
        return {
          name: p.p6_project_name || p.project_name || 'Unnamed',
          ordered_cr: Number(ordered_cr.toFixed(1)),
          delivered_cr: Number(delivered_cr.toFixed(1)),
          in_transit_cr: Number(Math.max(ordered_cr - delivered_cr, 0).toFixed(1)),
          pos: 0,
          delivered_pct: ordered_cr ? Number((delivered_cr * 100 / ordered_cr).toFixed(1)) : 0,
        };
      })
      .filter((g) => g.ordered_cr > 0)
      .sort((a, b) => b.ordered_cr - a.ordered_cr)
      .slice(0, 6);
  }, [projects]);

  const groups = mode === 'project' ? byProject : (remote[mode] || []);

  const option = useMemo(() => {
    if (!groups.length) return null;
    const rows = [...groups].reverse();   // largest at the top of a bar chart
    return {
      grid: { left: 8, right: 44, bottom: 34, top: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (ps: any[]) => {
          if (!ps?.length) return '';
          const g = rows[ps[0].dataIndex];
          if (!g) return '';
          const row = (c: string, k: string, v: string) =>
            `<div style="display:flex;gap:14px;justify-content:space-between">
               <span style="color:${c}">&#9679; ${k}</span><b>${v}</b></div>`;
          return `<b>${g.name}</b>
            ${row(statusColors.healthy, 'Delivered', `₹${fmtCr(g.delivered_cr)} Cr · ${g.delivered_pct}%`)}
            ${row(statusColors.watch, 'In transit', `₹${fmtCr(g.in_transit_cr)} Cr`)}
            <div style="margin-top:4px;padding-top:4px;border-top:1px solid rgba(128,128,128,.25);
                        display:flex;gap:14px;justify-content:space-between">
              <span>Ordered</span><b>₹${fmtCr(g.ordered_cr)} Cr</b></div>
            ${g.pos ? `<div style="font-size:10px;opacity:.7;margin-top:3px">${g.pos.toLocaleString('en-IN')} purchase orders</div>` : ''}`;
        },
      },
      legend: {
        bottom: 0, itemHeight: 8, itemWidth: 14,
        textStyle: { fontSize: 11, color: chrome.fgSecondary },
        data: ['Delivered', 'In transit'],
      },
      xAxis: {
        type: 'value',
        name: 'Material value (₹ Cr)', nameLocation: 'middle', nameGap: 26,
        nameTextStyle: { fontSize: 10, color: chrome.fgTertiary },
        axisLabel: { fontSize: 10, formatter: (v: number) => (v >= 1000 ? `${Math.round(v / 1000)}k` : v) },
      },
      yAxis: {
        type: 'category',
        data: rows.map((g) => g.name),
        axisLabel: {
          fontSize: 10.5, fontWeight: 600, width: 150, overflow: 'truncate',
          color: chrome.fgSecondary,
        },
      },
      series: [
        {
          name: 'Delivered', type: 'bar', stack: 'flow',
          data: rows.map((g) => g.delivered_cr),
          itemStyle: { color: statusColors.healthy, borderRadius: [3, 0, 0, 3] },
          barMaxWidth: 22,
        },
        {
          name: 'In transit', type: 'bar', stack: 'flow',
          data: rows.map((g) => g.in_transit_cr),
          itemStyle: { color: statusColors.watch, borderRadius: [0, 3, 3, 0] },
          barMaxWidth: 22,
        },
      ],
      animationDuration: 600,
    };
  }, [groups, statusColors, chrome]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 pb-2">
        <div className="flex overflow-hidden rounded-lg border border-border">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setMode(t.key)}
              className={cx(
                'flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-semibold transition-colors',
                mode === t.key
                  ? 'bg-gradient-to-r from-brand-blue to-brand-purple text-white'
                  : 'bg-card text-fg-secondary hover:bg-brand-blue/10'
              )}
            >
              <t.icon className="h-3 w-3" />
              {t.label}
            </button>
          ))}
        </div>
        <span className="text-[10px] font-medium text-fg-tertiary">
          Bar length = ordered value · split by how far it has travelled
        </span>
      </div>

      <div ref={plotRef} className="relative min-h-0 flex-1">
        {loading && !groups.length ? (
          <div className="flex h-full items-center justify-center text-[12px] text-fg-tertiary">Loading…</div>
        ) : option ? (
          <ReactECharts ref={chartRef} theme={themeName} option={option} notMerge style={{ height: '100%', width: '100%' }} />
        ) : (
          <div className="flex h-full items-center justify-center text-[12px] text-fg-tertiary">
            No purchase-order value recorded for this grouping.
          </div>
        )}
      </div>
    </div>
  );
}
