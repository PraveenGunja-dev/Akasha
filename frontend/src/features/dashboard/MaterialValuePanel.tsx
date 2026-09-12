import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  Sparkles, Truck, PackageCheck, IndianRupee, TrendingUp, AlertTriangle, Info, ArrowRight,
} from 'lucide-react';
import { cx } from '../../components/ui/primitives/cx';
import { useChartTheme } from '../../lib/chartTheme';

/* ═══════════════════════════════════════════════════════════════════════════
   MATERIAL VALUE — where the money sits, and how far along it is

   The ring is what was bought; the stage cards are how far it has travelled.
   Both come off one endpoint so they cannot disagree, and the three stage
   figures reconcile exactly — delivered + in-transit = ordered — because ZSPS
   records Actual Amount and Commitment Amt separately.

   The split is by MATERIAL, not by business segment: `material_type` is null
   on all 87,899 PO lines, so there is no generation / transmission column to
   group on. Inventing one would be a caption, not a measurement.

   Every insight below is arithmetic on those same figures. Nothing is
   generated, which is why each one names the numbers it came from.
   ═══════════════════════════════════════════════════════════════════════════ */

interface Category { name: string; value_cr: number; lines: number; share: number; rolled_up?: number }

interface Mix {
  ordered_cr: number;
  delivered_cr: number;
  in_transit_cr: number;
  po_count: number;
  delivered_pct: number;
  in_transit_pct: number;
  categories: Category[];
  category_count: number;
  laggard: { name: string; ordered_cr: number; delivered_cr: number; delivered_pct: number } | null;
  leader: { name: string; ordered_cr: number; delivered_cr: number; delivered_pct: number } | null;
  top_vendor: { name: string; cr: number; pos: number; share: number } | null;
  unattributed_cr: number;
  unattributed_pos: number;
  unattributed_pct: number;
  has_delivery_dates: boolean;
}

/* Brand ramp first, then supporting hues — a slice is a material, not a
   state, so none of the status colours appear here. */
const SLICE = ['#0b74b1', '#4aa3dd', '#76489d', '#a855f7', '#bc3860', '#e37b9d', '#0891b2', '#94a3b8'];

const fmtCr = (n: number) => (n >= 1000 ? Math.round(n).toLocaleString('en-IN') : n.toFixed(1));

export default function MaterialValuePanel() {
  const [mix, setMix] = useState<Mix | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { themeName, chrome } = useChartTheme();
  const plotRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    let live = true;
    fetch('/akasha/api/financials/material-mix')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { if (live) setMix(d); })
      .catch((e) => { if (live) setError(String(e.message || e)); });
    return () => { live = false; };
  }, []);

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

  const option = useMemo(() => {
    if (!mix?.categories?.length) return null;
    return {
      tooltip: {
        trigger: 'item',
        formatter: (p: any) =>
          `<b>${p.name}</b><br/>₹${fmtCr(p.value)} Cr · ${p.percent}%` +
          `<br/><span style="font-size:10px;opacity:.7">${mix.categories[p.dataIndex]?.lines ?? 0} PO lines</span>`,
      },
      series: [{
        type: 'pie',
        radius: ['60%', '86%'],
        center: ['50%', '50%'],
        padAngle: 2,
        itemStyle: { borderRadius: 4, borderColor: chrome.surface1, borderWidth: 2 },
        label: { show: false },
        emphasis: { scale: true, scaleSize: 6 },
        data: mix.categories.map((c, i) => ({
          name: c.name, value: c.value_cr, itemStyle: { color: SLICE[i % SLICE.length] },
        })),
      }],
      animationDuration: 700,
    };
  }, [mix, chrome]);

  if (error) {
    return <div className="flex h-full items-center justify-center p-6 text-center text-[12px] text-status-critical-fg">
      Could not load material mix — {error}
    </div>;
  }
  if (!mix) {
    return <div className="flex h-full items-center justify-center p-6 text-[12px] text-fg-tertiary">
      Reading ZSPS purchase orders…
    </div>;
  }

  const top = mix.categories[0];

  const stages = [
    { label: 'Ordered', icon: IndianRupee, cr: mix.ordered_cr, pct: 100, tone: 'text-brand-blue', bar: 'bg-brand-blue' },
    { label: 'Delivered', icon: PackageCheck, cr: mix.delivered_cr, pct: mix.delivered_pct, tone: 'text-status-healthy-fg', bar: 'bg-status-healthy-solid' },
    { label: 'In transit', icon: Truck, cr: mix.in_transit_cr, pct: mix.in_transit_pct, tone: 'text-status-watch-fg', bar: 'bg-status-watch-solid' },
  ];

  /* Each insight is something the cards and the ring do NOT already say, and
     every figure is computed from a fully-populated column. Restating
     "delivered is 53.6%" next to a card reading 53.6% is a caption, not an
     insight, so those are gone. */
  const insights = [
    ...(mix.top_vendor ? [{
      icon: AlertTriangle,
      chip: 'bg-status-critical-bg text-status-critical-fg',
      head: `${mix.top_vendor.share}% of undelivered value sits with one vendor`,
      body: `${mix.top_vendor.name} owes ₹${fmtCr(mix.top_vendor.cr)} Cr across just ${mix.top_vendor.pos} POs.`,
    }] : []),
    ...(mix.laggard && mix.leader ? [{
      icon: TrendingUp,
      chip: 'bg-status-watch-bg text-status-watch-fg',
      head: `${mix.laggard.name} is only ${mix.laggard.delivered_pct}% delivered`,
      body: `₹${fmtCr(mix.laggard.ordered_cr)} Cr ordered, ₹${fmtCr(mix.laggard.delivered_cr)} Cr landed — against ${mix.leader.name} at ${mix.leader.delivered_pct}%.`,
    }] : []),
    ...(mix.unattributed_pos > 0 ? [{
      icon: Info,
      chip: 'bg-status-done-bg text-status-done-fg',
      head: `₹${fmtCr(mix.unattributed_cr)} Cr undelivered has no vendor recorded`,
      body: `${mix.unattributed_pos.toLocaleString('en-IN')} POs (${mix.unattributed_pct}% of in-transit) cannot be chased to a counterparty.`,
    }] : []),
  ];

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 lg:flex-row">
      {/* ── Ring + category legend ── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div ref={plotRef} className="relative min-h-[180px] flex-1">
          {option && (
            <ReactECharts ref={chartRef} theme={themeName} option={option} notMerge style={{ height: '100%', width: '100%' }} />
          )}
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="metric-lg leading-none">
              ₹{fmtCr(mix.ordered_cr)} <span className="text-[11px] font-medium text-fg-tertiary">Cr</span>
            </span>
            <span className="mt-1 text-[10px] font-bold uppercase tracking-wider text-fg-tertiary">Total ordered</span>
            <span className="text-[10px] font-medium text-fg-tertiary">{mix.po_count.toLocaleString('en-IN')} POs</span>
          </div>
        </div>

        <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1">
          {mix.categories.map((c, i) => (
            <div key={c.name} className="flex items-center gap-1.5 text-[10px]">
              <span className="h-2 w-2 shrink-0 rounded-[2px]" style={{ background: SLICE[i % SLICE.length] }} />
              <span className="min-w-0 flex-1 truncate text-fg-secondary" title={c.name}>{c.name}</span>
              <span className="shrink-0 font-semibold tabular-nums text-fg-primary">{c.share}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Stages + insights ── */}
      <div className="flex min-w-0 flex-1 flex-col gap-2 lg:max-w-[52%]">
        {stages.map((s) => (
          <div key={s.label} className="kpi-card shrink-0 rounded-xl border border-border bg-card p-2.5">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5">
                <s.icon className={cx('h-3.5 w-3.5 shrink-0', s.tone)} strokeWidth={1.8} />
                <span className="section-label truncate">{s.label}</span>
              </span>
              <span className="shrink-0 text-[10px] font-bold tabular-nums text-fg-tertiary">{s.pct}%</span>
            </div>
            <div className="metric-md leading-none">
              ₹{fmtCr(s.cr)} <span className="text-[10px] font-medium text-fg-tertiary">Cr</span>
            </div>
            <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-fg-tertiary/15">
              <div className={cx('h-full rounded-full', s.bar)} style={{ width: `${Math.min(100, s.pct)}%` }} />
            </div>
          </div>
        ))}

        {/* AI Insights */}
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-brand-purple/25 bg-gradient-to-br from-brand-purple/[0.06] to-brand-blue/[0.03]">
          <div className="flex shrink-0 items-center justify-between gap-2 px-2.5 pb-1 pt-2">
            <span className="flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-brand-purple" strokeWidth={2} />
              <span className="text-[11px] font-bold text-fg-primary">AI Insights</span>
              <span className="rounded-full bg-brand-purple/15 px-1.5 py-px text-[8px] font-bold uppercase tracking-wide text-brand-purple">
                Beta
              </span>
            </span>
            <button
              className="flex items-center gap-0.5 text-[10px] font-semibold text-brand-blue hover:underline"
              title="Computed from ZSPS vendor and delivery columns. No delivery_date is recorded on any PO line, so no overdue or ageing signal is available."
            >
              View all <ArrowRight className="h-2.5 w-2.5" />
            </button>
          </div>

          <div className="custom-scrollbar min-h-0 flex-1 space-y-1.5 overflow-y-auto px-2.5 pb-2.5">
            {insights.map((n) => (
              <div key={n.head} className="flex items-start gap-2 rounded-lg bg-card/70 p-1.5">
                <span className={cx('grid h-5 w-5 shrink-0 place-items-center rounded-md', n.chip)}>
                  <n.icon className="h-3 w-3" strokeWidth={2} />
                </span>
                <div className="min-w-0">
                  <p className="text-[10.5px] font-semibold leading-snug text-fg-primary">{n.head}</p>
                  <p className="text-[9.5px] leading-snug text-fg-tertiary">{n.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
