import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { HardHat, CheckCircle2, Hourglass, IndianRupee, Truck, PackageCheck, CalendarClock, Flag } from 'lucide-react';
import { KPITile, ChartFrame, Card, CardHeader, StatusDot } from '../../components/ui/primitives';
import { NotAvailable } from '../sap-intelligence/components/Drawer';
import { sapApi } from '../sap-intelligence/api';
import { EMPTY_FILTERS } from '../sap-intelligence/store';
import type { Trends } from '../sap-intelligence/types';
import { useChartTheme } from '../../lib/chartTheme';
import { formatDate } from '../../lib/utils';

/* One project's build chain, from the systems that actually carry it:
     Installation  — P6 "Module Installation" activities, planned vs completed
                     by month (a direct read of p6_activity.status and dates).
     Materials     — SAP ZSPS order value (₹). Value, never quantity: the
                     quantity columns mix units and do not reconcile.
     Transmission  — the lines this project depends on, current status only.
     ECOD          — P6 scheduled vs baseline finish.
   What is deliberately absent: a delivery / GRN date. ZSPS carries none, so
   "materials received by month" cannot be drawn honestly — the closest dated
   signal is MB51 site consumption, which is shown and named as exactly that. */

interface MonthRow { month: string; planned: number; baseline: number; completed: number; planned_cum: number; baseline_cum: number; completed_cum: number }
interface Progress {
  not_applicable: boolean; reason?: string;
  summary?: { planned: number; completed: number; in_progress: number; not_started: number; remaining: number; pct_complete: number; basis: string };
  monthly?: MonthRow[];
}

const CR = 1e7;
const cr = (v: number | null | undefined) => v == null ? '—' : `₹${(v / CR).toLocaleString('en-IN', { maximumFractionDigits: 1 })}`;
const monthLabel = (ym: string) => { const [y, m] = ym.split('-'); return new Date(+y, +m - 1, 1).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' }); };

/* echarts-for-react measures once at mount; inside a flex column it must be told to resize. */
const useResize = (ref: React.RefObject<any>) => {
  useEffect(() => {
    const el = ref.current?.ele as HTMLElement | undefined;
    if (!el?.parentElement) return;
    const ro = new ResizeObserver(() => ref.current?.getEchartsInstance()?.resize());
    ro.observe(el.parentElement);
    return () => ro.disconnect();
  }, [ref]);
};

export default function InstallationProcurementTab({ projectId, detail }: { projectId: string; detail: any }) {
  const { themeName, categorical, status, chrome } = useChartTheme();
  const [progress, setProgress] = useState<Progress | null>(null);
  const [trends, setTrends] = useState<Trends | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const instRef = useRef<any>(null); const matRef = useRef<any>(null);
  useResize(instRef); useResize(matRef);

  useEffect(() => {
    setProgress(null); setTrends(null); setErr(null);
    const ctrl = new AbortController();
    fetch(`/akasha/api/dashboard/api/projects/${encodeURIComponent(projectId)}/installation-progress`, { signal: ctrl.signal })
      .then(r => r.json()).then(setProgress).catch(e => { if (e.name !== 'AbortError') setErr(String(e)); });
    // phase 'ALL': one project is already the scope; the default 'Ongoing' would hide a commissioned project from itself.
    sapApi.trends({ ...EMPTY_FILTERS, project: projectId, phase: 'ALL' }, 'month', ctrl.signal)
      .then(setTrends).catch(() => setTrends({ granularity: 'month', series: [], events: [], inventory_total_qty: 0 }));
    return () => ctrl.abort();
  }, [projectId]);

  const sap = detail?.sap?.summary;
  const p6 = detail?.p6;
  const edges: any[] = [...(detail?.tc?.khavdaEdges ?? []), ...(detail?.tc?.rajasthanEdges ?? [])];
  const s = progress?.summary;

  const installOption = useMemo(() => {
    const rows = progress?.monthly ?? [];
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { top: 0, itemHeight: 8, itemWidth: 16, textStyle: { fontSize: 11, color: chrome.fgSecondary } },
      grid: { left: 8, right: 8, top: 34, bottom: 8, containLabel: true },
      xAxis: { type: 'category', data: rows.map(r => monthLabel(r.month)), axisLabel: { fontSize: 10, color: chrome.fgTertiary }, axisLine: { lineStyle: { color: chrome.axisLine } } },
      yAxis: [
        { type: 'value', name: 'Blocks / month', minInterval: 1, nameTextStyle: { fontSize: 10, color: chrome.fgTertiary }, axisLabel: { fontSize: 10, color: chrome.fgTertiary }, splitLine: { lineStyle: { color: chrome.gridLine } } },
        { type: 'value', name: 'Cumulative', minInterval: 1, nameTextStyle: { fontSize: 10, color: chrome.fgTertiary }, axisLabel: { fontSize: 10, color: chrome.fgTertiary }, splitLine: { show: false } },
      ],
      series: [
        { name: 'Planned (month)', type: 'bar', data: rows.map(r => r.planned), itemStyle: { color: categorical[0], opacity: 0.45 }, barMaxWidth: 18 },
        { name: 'Completed (month)', type: 'bar', data: rows.map(r => r.completed), itemStyle: { color: status.healthy }, barMaxWidth: 18 },
        { name: 'Planned cumulative', type: 'line', yAxisIndex: 1, data: rows.map(r => r.planned_cum), symbol: 'none', lineStyle: { width: 1.5, type: 'dashed', color: categorical[0] }, itemStyle: { color: categorical[0] } },
        { name: 'Completed cumulative', type: 'line', yAxisIndex: 1, data: rows.map(r => r.completed_cum), symbol: 'circle', symbolSize: 4, lineStyle: { width: 2, color: status.healthy }, itemStyle: { color: status.healthy } },
      ],
    };
  }, [progress, chrome, categorical, status]);

  const matOption = useMemo(() => {
    const rows = (trends?.series ?? []).filter(b => b.ordered_cr > 0 || b.consumed_cr > 0);
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })} Cr` },
      legend: { top: 0, itemHeight: 8, itemWidth: 16, textStyle: { fontSize: 11, color: chrome.fgSecondary } },
      grid: { left: 8, right: 8, top: 34, bottom: 8, containLabel: true },
      xAxis: { type: 'category', data: rows.map(b => monthLabel(b.bucket)), axisLabel: { fontSize: 10, color: chrome.fgTertiary }, axisLine: { lineStyle: { color: chrome.axisLine } } },
      yAxis: { type: 'value', name: '₹ Cr', nameTextStyle: { fontSize: 10, color: chrome.fgTertiary }, axisLabel: { fontSize: 10, color: chrome.fgTertiary }, splitLine: { lineStyle: { color: chrome.gridLine } } },
      series: [
        { name: 'Ordered (PO date)', type: 'bar', data: rows.map(b => b.ordered_cr), itemStyle: { color: categorical[0] }, barMaxWidth: 18 },
        { name: 'Consumed on site (MB51)', type: 'bar', data: rows.map(b => b.consumed_cr), itemStyle: { color: categorical[1] }, barMaxWidth: 18 },
      ],
    };
  }, [trends, chrome, categorical]);

  const orderedInr = sap?.totalBudgetINR ?? 0;
  const deliveredInr = sap?.totalDeliveredINR ?? 0;
  // P6's own finish_date_variance is null on every project in this database, so
  // the slip is computed from the two real dates it does carry. Shown in words
  // ("91 days late") to avoid P6's sign convention being misread.
  const slipDays = useMemo(() => {
    if (!p6?.scheduledFinishDate || !p6?.baselineFinishDate) return null;
    const a = new Date(p6.scheduledFinishDate).getTime(), b = new Date(p6.baselineFinishDate).getTime();
    return Number.isNaN(a) || Number.isNaN(b) ? null : Math.round((a - b) / 86400000);
  }, [p6?.scheduledFinishDate, p6?.baselineFinishDate]);

  return (
    <div className="flex w-full flex-col gap-5">
      {/* ── Installation ── */}
      <section className="flex flex-col gap-3">
        <div className="section-label">Module installation · P6</div>
        {err && <NotAvailable what="Installation progress" why={err} />}
        {progress?.not_applicable && <NotAvailable what="Module installation" why={progress.reason ?? 'Not tracked in P6 for this project.'} />}
        {s && (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <KPITile label="Planned" value={s.planned} unit="blocks" icon={HardHat} subtext="Module Installation activities in P6" source="P6" />
              <KPITile label="Completed" value={s.completed} unit="blocks" icon={CheckCircle2} tone="healthy" subtext={`${s.pct_complete}% of planned`} source="P6" />
              <KPITile label="In progress" value={s.in_progress} unit="blocks" icon={Hourglass} tone="watch" source="P6" />
              <KPITile label="Not started" value={s.not_started} unit="blocks" icon={Flag} subtext={`Remaining ${s.remaining}`} source="P6" />
            </div>
            <ChartFrame title="Planned vs completed, by month" eyebrow="Bars: blocks finishing that month · Lines: cumulative" height={280}>
              <ReactECharts ref={instRef} theme={themeName} option={installOption} notMerge style={{ height: '100%', width: '100%' }} />
            </ChartFrame>
          </>
        )}
      </section>

      {/* ── Materials ── */}
      <section className="flex flex-col gap-3">
        <div className="section-label">Materials · SAP purchase orders</div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <KPITile label="Ordered" value={cr(orderedInr)} unit="Cr" icon={IndianRupee} subtext="PO value (ZSPS, POrd only)" source="SAP" />
          <KPITile label="Delivered" value={cr(deliveredInr)} unit="Cr" icon={PackageCheck} tone="healthy" subtext={orderedInr ? `${((deliveredInr / orderedInr) * 100).toFixed(0)}% of ordered` : undefined} source="SAP" />
          <KPITile label="Still to deliver" value={cr(Math.max(0, orderedInr - deliveredInr))} unit="Cr" icon={Truck} tone="watch" subtext="Ordered − delivered" source="SAP" />
        </div>
        <NotAvailable what="Delivery / GRN date" why="ZSPS carries no delivery date on any line and there is no goods-receipt extract, so 'received by month' cannot be drawn. Delivered is a cumulative value only." />
        {trends && trends.series.length > 0 && (
          <ChartFrame title="Ordered vs consumed on site, by month" eyebrow="Ordered by PO date · Consumed = MB51 issues to site, not vendor delivery" height={260}>
            <ReactECharts ref={matRef} theme={themeName} option={matOption} notMerge style={{ height: '100%', width: '100%' }} />
          </ChartFrame>
        )}
      </section>

      {/* ── ECOD + Transmission ── */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card pad="md">
          <CardHeader icon={CalendarClock} title="ECOD" eyebrow="P6 project finish" />
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12px]">
            <dt className="text-fg-tertiary">Current (scheduled)</dt><dd className="font-mono text-fg-primary">{formatDate(p6?.scheduledFinishDate)}</dd>
            <dt className="text-fg-tertiary">Original (baseline)</dt><dd className="font-mono text-fg-primary">{formatDate(p6?.baselineFinishDate)}</dd>
            <dt className="text-fg-tertiary">Slip vs baseline</dt>
            <dd className={`font-mono ${slipDays != null && slipDays > 0 ? 'text-status-critical-fg' : slipDays != null && slipDays < 0 ? 'text-status-healthy-fg' : 'text-fg-primary'}`}>
              {slipDays == null ? '—' : slipDays === 0 ? 'On baseline' : `${Math.abs(slipDays)} days ${slipDays > 0 ? 'late' : 'early'}`}
            </dd>
          </dl>
          <p className="mt-2 text-[11px] text-fg-tertiary">Slip = scheduled − baseline finish. P6 holds one current and one baseline date; a full revision history is not recorded.</p>
        </Card>

        <Card pad="md">
          <CardHeader icon={Flag} title="Transmission dependency" eyebrow={`${edges.length} linked line${edges.length === 1 ? '' : 's'} · current status`} />
          {edges.length === 0 ? (
            <p className="text-[12px] text-fg-tertiary">No transmission lines are mapped to this project.</p>
          ) : (
            <ul className="divide-y divide-border-subtle">
              {edges.map((e, i) => {
                const st = String(e.normalizedStatus ?? '').toLowerCase();
                const tone = st === 'charged' ? 'done' : st === 'in_progress' ? 'watch' : 'neutral';
                return (
                  <li key={i} className="flex items-center justify-between gap-3 py-1.5 text-[12px]">
                    <span className="flex min-w-0 items-center gap-2"><StatusDot tone={tone} /><span className="truncate text-fg-primary">{e.fromLabel} → {e.toLabel}</span></span>
                    <span className="shrink-0 font-mono text-[11px] text-fg-tertiary">{e.voltage}{e.chargedDate ? ` · charged ${e.chargedDate}` : e.expectedDate ? ` · exp. ${e.expectedDate}` : ''}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
