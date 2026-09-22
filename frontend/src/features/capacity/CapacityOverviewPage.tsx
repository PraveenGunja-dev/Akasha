import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Zap, Sun, Wind, Activity, TrendingUp, TrendingDown, Minus, ArrowUpRight,
  Sparkles, Calculator, AlertTriangle, RefreshCw, Milestone as MilestoneIcon, Target, PieChart,
} from 'lucide-react';
import { useChartTheme } from '../../lib/chartTheme';
import { cx } from '../../components/ui/primitives/cx';
import { formatProjectName } from '../../lib/projectName';

import type { CapacityData, CapacityFilters, CapacityInsight, ProjectBreakdown, ChartSeriesKey, Aggregation } from './types';
import { DEFAULT_FILTERS } from './types';
import {
  filterProjects, filterMonths, filterMilestones, computeTotals, periodDelta,
  aggregate, seriesForFilter, computeUpcoming, computeSegmentMix, computeMilestones,
  decumulate,
} from './capacityCalculations';
import { generateCapacityInsights } from './capacityInsights';
import { useCapacityActions, defaultDueDate } from './useCapacityActions';
import CapacityHeader from './CapacityHeader';
import InsightDrawer from './InsightDrawer';
import { SEVERITY_META } from './severity';
import ProjectDrilldown from './ProjectDrilldown';
import AskAiPanel from './AskAiPanel';
import ActionsDrawer from './ActionsDrawer';

/* ═══════════════════════════════════════════════════════════════════════════
   CAPACITY OVERVIEW

   One filter object drives every section, so no two panels can describe
   different populations. Every control on this page performs a real action —
   the audit that prompted this rebuild found nine that did nothing.

   On planned vs forecast: the payload has no planned series and no per-project
   commissioning date, so this screen does not draw one. Where the reference
   design shows "Planned", we show cumulative commissioned against portfolio
   capacity, which is a target line the data can actually support. Inventing a
   time-phased plan would put a confident wrong number in front of a CEO.
   ═══════════════════════════════════════════════════════════════════════════ */

const container = { hidden: { opacity: 0 }, show: { opacity: 1, transition: { staggerChildren: 0.06 } } };
const item = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.3 } } };

const MWs = (n: number) => n.toLocaleString('en-IN', { maximumFractionDigits: 1 });

/* ── KPI card ────────────────────────────────────────────────────────────── */

function KpiCard({
  title, value, unit, sub, delta, spark, icon: Icon, tint, onClick,
}: {
  title: string; value: number; unit: string; sub: string;
  delta: number | null; spark: number[]; icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>; tint: string; onClick: () => void;
}) {
  const Trend = delta === null ? Minus : delta >= 0 ? TrendingUp : TrendingDown;
  const trendTone = delta === null ? 'text-fg-tertiary' : delta >= 0 ? 'text-status-healthy-fg' : 'text-status-critical-fg';

  const sparkOption = spark.length > 1 ? {
    grid: { left: 0, right: 0, top: 2, bottom: 0 },
    xAxis: { type: 'category', show: false, data: spark.map((_, i) => i) },
    yAxis: { type: 'value', show: false, min: 0 },
    tooltip: { show: false },
    series: [{
      type: 'bar', data: spark, barMaxWidth: 5,
      itemStyle: { color: tint, borderRadius: [2, 2, 0, 0], opacity: 0.75 },
    }],
    animationDuration: 500,
  } : null;

  return (
    <button
      onClick={onClick}
      className="kpi-card group flex w-full flex-col rounded-xl border border-border bg-card p-3 text-left transition-all hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      aria-label={`${title}: ${MWs(value)} ${unit}. Open project breakdown.`}
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: tint }} />
        <span className="section-label truncate">{title}</span>
        <ArrowUpRight className="ml-auto h-3 w-3 shrink-0 text-fg-tertiary opacity-0 transition-opacity group-hover:opacity-100" />
      </div>

      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-baseline gap-1">
            <span className="metric-lg leading-none">{MWs(value)}</span>
            <span className="text-[10px] font-medium text-fg-tertiary">{unit}</span>
          </div>
          <div className={cx('mt-1 flex items-center gap-1 text-[10.5px] font-semibold', trendTone)}>
            <Trend className="h-3 w-3" />
            {delta === null ? 'No prior period' : `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}% vs previous`}
          </div>
          <div className="mt-0.5 text-[10px] text-fg-tertiary">{sub}</div>
        </div>
        {sparkOption && (
          <div className="h-9 w-16 shrink-0" aria-hidden>
            <ReactECharts option={sparkOption} notMerge style={{ height: '100%', width: '100%' }} opts={{ renderer: 'svg' }} />
          </div>
        )}
      </div>
    </button>
  );
}

/* ── Page ────────────────────────────────────────────────────────────────── */

export default function CapacityOverviewPage() {
  const [data, setData] = useState<CapacityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [filters, setFilters] = useState<CapacityFilters>(DEFAULT_FILTERS);

  const [insightOpen, setInsightOpen] = useState<CapacityInsight | null>(null);
  const [drill, setDrill] = useState<{ title: string; subtitle?: string; projects: ProjectBreakdown[] } | null>(null);
  const [askOpen, setAskOpen] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);

  const [searchParams] = useSearchParams();
  const portfolio = searchParams.get('portfolio');
  const phase = searchParams.get('phase');
  const { themeName, chrome } = useChartTheme();
  const { createAction, openCount, trackedIds } = useCapacityActions();

  /* ── Load ── */
  useEffect(() => {
    let live = true;
    const params = new URLSearchParams();
    if (portfolio) params.append('portfolio', portfolio);
    if (phase) params.append('phase', phase);
    const qs = params.toString() ? `?${params.toString()}` : '';
    const url = `/akasha/api/dashboard/capacity-overview${qs}`;

    (async () => {
      setLoading(true);
      setError(null);
      try {
        const r = await fetch(url);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        if (live) setData(d);
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (live) setLoading(false);
      }
    })();
    return () => { live = false; };
  }, [portfolio, phase, reloadKey]);

  const patch = useCallback((p: Partial<CapacityFilters>) => setFilters((f) => ({ ...f, ...p })), []);

  /* ── Derived, all from one source of truth ── */
  const projects = useMemo(() => filterProjects(data?.projects || [], filters.segment), [data, filters.segment]);
  /* monthly_trends is a running total; difference it once here so every
     consumer below reads capacity ADDED per month. */
  const added = useMemo(() => decumulate(data?.monthly_trends || []), [data]);
  const months = useMemo(() => filterMonths(added, filters), [added, filters]);
  const totals = useMemo(() => computeTotals(projects), [projects]);
  const insights = useMemo(() => generateCapacityInsights(data, filters), [data, filters]);
  const upcoming = useMemo(() => computeUpcoming(projects), [projects]);
  const segmentMix = useMemo(() => computeSegmentMix(projects), [projects]);
  const milestones = useMemo(
    () => computeMilestones(filterMilestones(data?.recent_milestones || [], filters.segment)),
    [data, filters.segment],
  );

  /* Insights name projects; the route needs the mapping id. */
  const projectIdByName = useMemo(() => {
    const m: Record<string, string> = {};
    (data?.projects || []).forEach((p) => { if (p.project_name && p.project_id) m[p.project_name] = p.project_id; });
    return m;
  }, [data]);

  const codDelta = useMemo(() => periodDelta(data?.monthly_trends || [], filters, ['Solar COD', 'Wind COD']), [data, filters]);
  const trDelta = useMemo(() => periodDelta(data?.monthly_trends || [], filters, ['Solar Trial Run', 'Wind Trial Run']), [data, filters]);
  const solarDelta = useMemo(() => periodDelta(data?.monthly_trends || [], filters, ['Solar COD', 'Solar Trial Run']), [data, filters]);
  const windDelta = useMemo(() => periodDelta(data?.monthly_trends || [], filters, ['Wind COD', 'Wind Trial Run']), [data, filters]);

  /* ── Trajectory chart ── */
  const trajectory = useMemo(() => {
    const points = aggregate(months, filters.aggregation);
    if (!points.length) return null;
    const keys = seriesForFilter(filters.series);
    const palette: Record<string, string> = {
      'Solar COD': '#f59e0b',
      'Solar Trial Run': '#fbbf24',
      'Wind COD': '#0b74b1',
      'Wind Trial Run': '#4aa3dd',
    };

    return {
      grid: { left: 40, right: 24, top: 28, bottom: 44, containLabel: true },
      legend: { top: 0, itemHeight: 8, itemWidth: 14, textStyle: { fontSize: 11, color: chrome.fgSecondary } },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', label: { show: false } },
        formatter: (ps: { dataIndex: number }[]) => {
          if (!ps?.length) return '';
          const p = points[ps[0].dataIndex];
          if (!p) return '';
          const line = (c: string, k: string, v: number) =>
            `<div style="display:flex;gap:16px;justify-content:space-between">
               <span style="color:${c}">&#9679; ${k}</span><b>${MWs(v)} MW</b></div>`;
          const rows = keys.map((k) => line(palette[k], k, p[k])).join('');
          const shown = keys.reduce((s, k) => s + p[k], 0);
          return `<b>${p.label}</b>${rows}
            <div style="margin-top:4px;padding-top:4px;border-top:1px solid rgba(128,128,128,.25);
                        display:flex;gap:16px;justify-content:space-between">
              <span>Added in period</span><b>${MWs(shown)} MW</b></div>
            <div style="display:flex;gap:16px;justify-content:space-between">
              <span>Cumulative in view</span><b>${MWs(p.cumulative)} MW</b></div>
            <div style="font-size:10px;opacity:.7;margin-top:3px">Click to open the projects behind this period</div>`;
        },
      },
      xAxis: {
        type: 'category',
        data: points.map((p) => p.label),
        axisLabel: { fontSize: 10, rotate: points.length > 10 ? 40 : 0, color: chrome.fgTertiary },
      },
      yAxis: {
        type: 'value',
        name: 'MW added', nameLocation: 'middle', nameRotate: 90, nameGap: 44,
        nameTextStyle: { fontSize: 10, color: chrome.fgTertiary },
        axisLabel: { fontSize: 10 },
        splitLine: { lineStyle: { type: 'dashed', opacity: 0.35 } },
      },
      series: keys.map((k) => ({
        name: k, type: 'line', smooth: true, stack: 'added',
        data: points.map((p) => p[k]),
        symbol: 'circle', symbolSize: 6,
        lineStyle: { width: 2, color: palette[k] },
        itemStyle: { color: palette[k] },
        areaStyle: { color: palette[k], opacity: 0.14 },
      })),
      animationDuration: 600,
    };
  }, [months, filters.aggregation, filters.series, chrome]);

  /* Clicking a period opens the projects that make up the selected segment. */
  const onChartClick = useCallback(() => {
    setDrill({
      title: `Projects — ${filters.series === 'All' ? 'all series' : filters.series}`,
      subtitle: `${filters.segment === 'All' ? 'All segments' : filters.segment} · ${months.length} months in view`,
      projects,
    });
  }, [filters.series, filters.segment, months.length, projects]);

  const donut = useMemo(() => {
    if (!segmentMix.length) return null;
    const colors: Record<string, string> = { Solar: '#f59e0b', Wind: '#0b74b1' };
    return {
      tooltip: {
        trigger: 'item',
        formatter: (p: { name: string; value: number; percent: number }) =>
          `<b>${p.name}</b><br/>${MWs(p.value)} MW · ${p.percent}%<br/>
           <span style="font-size:10px;opacity:.7">Click to open projects</span>`,
      },
      series: [{
        type: 'pie', radius: ['62%', '86%'], center: ['50%', '50%'], padAngle: 2,
        itemStyle: { borderRadius: 4, borderColor: chrome.surface1, borderWidth: 2 },
        label: { show: false },
        data: segmentMix.map((s) => ({ name: s.label, value: s.mw, itemStyle: { color: colors[s.label] } })),
      }],
      animationDuration: 600,
    };
  }, [segmentMix, chrome]);

  /* ── States ── */
  if (loading) {
    return (
      <div className="space-y-3">
        <div className="h-14 animate-pulse rounded-xl bg-muted/60" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-[104px] animate-pulse rounded-xl bg-muted/60" />)}
        </div>
        <div className="h-[360px] animate-pulse rounded-xl bg-muted/60" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[320px] flex-col items-center justify-center rounded-xl border border-border bg-card p-8 text-center">
        <AlertTriangle className="mb-2 h-6 w-6 text-status-critical-fg" />
        <p className="text-[13px] font-semibold text-foreground">Capacity data couldn’t be loaded</p>
        <p className="mt-1 max-w-sm text-[11.5px] text-fg-tertiary">{error}</p>
        <button
          onClick={() => setReloadKey((k) => k + 1)}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-[12px] font-semibold text-white transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </button>
      </div>
    );
  }

  const empty = !projects.length;

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="flex flex-col gap-3">
      <CapacityHeader
        filters={filters}
        onChange={patch}
        onAskAi={() => setAskOpen(true)}
        onOpenActions={() => setActionsOpen(true)}
        onRefresh={() => setReloadKey((k) => k + 1)}
        actionCount={openCount}
        refreshing={loading}
      />

      {empty ? (
        <div className="rounded-xl border border-dashed border-border py-16 text-center">
          <p className="text-[13px] font-semibold text-foreground">No capacity data for this filter</p>
          <p className="mt-1 text-[11.5px] text-fg-tertiary">
            No {filters.segment === 'All' ? '' : `${filters.segment} `}projects are mapped in the current scope.
          </p>
          <button
            onClick={() => patch({ segment: 'All', dateRange: 'ALL' })}
            className="mt-3 rounded-lg border border-border px-3 py-1.5 text-[12px] font-semibold text-fg-secondary hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Reset filters
          </button>
        </div>
      ) : (
        <>
          {/* ── KPI row ── */}
          <motion.div variants={item} className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              title="COD done" value={totals.codMW} unit="MW" icon={Zap} tint="#12b76a"
              sub={`${totals.codPct.toFixed(1)}% of portfolio`}
              delta={codDelta.deltaPct} spark={codDelta.series}
              onClick={() => setDrill({
                title: 'COD done', subtitle: 'Projects with commissioned capacity',
                projects: projects.filter((p) => p.cod_mw > 0),
              })}
            />
            <KpiCard
              title="Trial run only" value={totals.trMW} unit="MW" icon={Activity} tint="#f59e0b"
              sub="Energised, not yet at COD"
              delta={trDelta.deltaPct} spark={trDelta.series}
              onClick={() => setDrill({
                title: 'Trial run only', subtitle: 'Blocks energised but not yet at COD',
                projects: projects.filter((p) => p.tr_mw > 0),
              })}
            />
            <KpiCard
              title="Solar portfolio" value={totals.solarMW} unit="MW" icon={Sun} tint="#f59e0b"
              sub={`${projects.filter((p) => p.type === 'Solar').length} projects`}
              delta={solarDelta.deltaPct} spark={solarDelta.series}
              onClick={() => setDrill({
                title: 'Solar portfolio', subtitle: 'All mapped solar projects',
                projects: projects.filter((p) => p.type === 'Solar'),
              })}
            />
            <KpiCard
              title="Wind portfolio" value={totals.windMW} unit="MW" icon={Wind} tint="#0b74b1"
              sub={`${projects.filter((p) => p.type === 'Wind').length} projects`}
              delta={windDelta.deltaPct} spark={windDelta.series}
              onClick={() => setDrill({
                title: 'Wind portfolio', subtitle: 'All mapped wind projects',
                projects: projects.filter((p) => p.type === 'Wind'),
              })}
            />
          </motion.div>

          {/* ── Trajectory + insights ── */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
            <motion.section variants={item} className="flex flex-col rounded-xl border border-border bg-card lg:col-span-8">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border-subtle px-4 py-3">
                <div className="min-w-0">
                  <h2 className="text-[14px] font-bold text-foreground">Capacity Trajectory</h2>
                  <p className="mt-0.5 text-[11px] text-fg-tertiary">
                    Capacity added per period, by segment and milestone
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex overflow-hidden rounded-lg border border-border" role="group" aria-label="Series filter">
                    {(['All', 'COD', 'Trial Run', 'Solar', 'Wind'] as ChartSeriesKey[]).map((s) => (
                      <button
                        key={s}
                        onClick={() => patch({ series: s })}
                        aria-pressed={filters.series === s}
                        className={cx(
                          'px-2 py-1 text-[11px] font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary',
                          filters.series === s ? 'bg-primary text-white' : 'bg-card text-fg-secondary hover:bg-muted',
                        )}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                  <div className="flex overflow-hidden rounded-lg border border-border" role="group" aria-label="Aggregation">
                    {(['Monthly', 'Quarterly', 'Yearly'] as Aggregation[]).map((m) => (
                      <button
                        key={m}
                        onClick={() => patch({ aggregation: m })}
                        aria-pressed={filters.aggregation === m}
                        className={cx(
                          'px-2 py-1 text-[11px] font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary',
                          filters.aggregation === m ? 'bg-primary text-white' : 'bg-card text-fg-secondary hover:bg-muted',
                        )}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="h-[320px] p-2">
                {trajectory ? (
                  <ReactECharts
                    theme={themeName}
                    option={trajectory}
                    notMerge
                    onEvents={{ click: onChartClick }}
                    style={{ height: '100%', width: '100%' }}
                  />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
                    <p className="text-[12px] text-fg-tertiary">No capacity was added in this period.</p>
                    <button
                      onClick={() => patch({ dateRange: 'ALL' })}
                      className="rounded-lg border border-border px-2.5 py-1 text-[11px] font-semibold text-fg-secondary hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      Widen to all time
                    </button>
                  </div>
                )}
              </div>
            </motion.section>

            {/* Insights */}
            <motion.aside variants={item} className="flex min-h-0 flex-col rounded-xl border border-border bg-card lg:col-span-4">
              <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border-subtle px-3 py-2.5">
                <span className="flex items-center gap-1.5">
                  <Calculator className="h-3.5 w-3.5 text-brand-purple" />
                  <span className="text-[12px] font-bold text-foreground">Insights</span>
                  <span className="rounded-full border border-border bg-muted px-1.5 py-px text-[8.5px] font-bold uppercase tracking-wide text-fg-tertiary">
                    Calculated
                  </span>
                </span>
                <button
                  onClick={() => setInsightOpen(insights[0] ?? null)}
                  disabled={!insights.length}
                  className="text-[10.5px] font-semibold text-brand-blue hover:underline disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  Open first
                </button>
              </div>

              <div className="custom-scrollbar min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2">
                {insights.length === 0 ? (
                  <p className="px-2 py-8 text-center text-[11.5px] text-fg-tertiary">
                    Nothing stands out in this window. Widen the date range to compare more periods.
                  </p>
                ) : insights.map((n) => {
                  const meta = SEVERITY_META[n.severity];
                  const Icon = meta.icon;
                  return (
                    <button
                      key={n.id}
                      onClick={() => setInsightOpen(n)}
                      className="flex w-full items-start gap-2 rounded-lg border border-transparent p-2 text-left transition-colors hover:border-border hover:bg-muted/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <span className={cx('grid h-6 w-6 shrink-0 place-items-center rounded-md border', meta.chip)}>
                        <Icon className="h-3 w-3" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-[11px] font-semibold leading-snug text-foreground">{n.title}</span>
                        <span className="mt-0.5 block text-[10px] leading-snug text-fg-tertiary">{n.summary}</span>
                        {trackedIds.has(n.id) && (
                          <span className="mt-1 inline-block rounded-full bg-status-healthy-bg px-1.5 py-px text-[9px] font-bold text-status-healthy-fg">
                            Tracked
                          </span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="shrink-0 border-t border-border-subtle p-2">
                <button
                  onClick={() => setAskOpen(true)}
                  className="flex w-full items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-left text-[11.5px] text-fg-tertiary transition-colors hover:border-brand-blue/40 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <Sparkles className="h-3.5 w-3.5 shrink-0 text-brand-purple" />
                  Ask AI anything about capacity…
                </button>
              </div>
            </motion.aside>
          </div>

          {/* ── Bottom row ── */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            {/* Segment mix */}
            <motion.section variants={item} className="flex min-h-[250px] flex-col rounded-xl border border-border bg-card p-3">
              <h3 className="mb-2 flex items-center gap-1.5 text-[12px] font-bold text-foreground">
                <PieChart className="h-3.5 w-3.5 text-primary" /> Capacity by segment
              </h3>
              <div className="relative min-h-[120px] flex-1">
                {donut && <ReactECharts option={donut} notMerge style={{ height: '100%', width: '100%' }} opts={{ renderer: 'svg' }}
                  onEvents={{ click: (e: { name?: string }) => {
                    const seg = e?.name;
                    setDrill({ title: `${seg} projects`, subtitle: 'Click a column header to sort', projects: projects.filter((p) => p.type === seg) });
                  } }} />}
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <span className="metric-md leading-none">{MWs(totals.portfolioMW)}</span>
                  <span className="text-[9.5px] font-medium text-fg-tertiary">MW total</span>
                </div>
              </div>
              <ul className="mt-2 space-y-1">
                {segmentMix.map((s) => (
                  <li key={s.label}>
                    <button
                      onClick={() => setDrill({ title: `${s.label} projects`, subtitle: `${s.projectCount} projects · ${MWs(s.mw)} MW`, projects: projects.filter((p) => p.type === s.segment) })}
                      className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-[10.5px] transition-colors hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: s.label === 'Solar' ? '#f59e0b' : '#0b74b1' }} />
                      <span className="flex-1 text-left font-semibold text-foreground">{s.label}</span>
                      <span className="text-fg-tertiary">{s.projectCount}</span>
                      <span className="w-14 text-right font-bold tabular-nums text-foreground">{MWs(s.mw)}</span>
                      <span className="w-9 text-right tabular-nums text-fg-tertiary">{s.pct.toFixed(0)}%</span>
                    </button>
                  </li>
                ))}
              </ul>
            </motion.section>

            {/* Milestones */}
            <motion.section variants={item} className="flex min-h-[250px] flex-col rounded-xl border border-border bg-card p-3">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="flex items-center gap-1.5 text-[12px] font-bold text-foreground">
                  <MilestoneIcon className="h-3.5 w-3.5 text-primary" /> Recent milestones
                </h3>
                <button
                  onClick={() => setDrill({
                    title: 'Milestone timeline',
                    subtitle: `${milestones.length} block milestones with recorded dates`,
                    projects,
                  })}
                  className="text-[10px] font-semibold text-brand-blue hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  View all
                </button>
              </div>
              {milestones.length === 0 ? (
                <p className="flex flex-1 items-center justify-center text-center text-[11px] text-fg-tertiary">
                  No block has a recorded COD or trial-run date in this scope.
                </p>
              ) : (
                <ol className="flex-1 space-y-2.5">
                  {milestones.map((m, i) => (
                    <li key={m.key} className="flex gap-2.5">
                      <div className="flex shrink-0 flex-col items-center">
                        <span className={cx('h-2 w-2 rounded-full', m.status === 'COD' ? 'bg-status-healthy-solid' : 'bg-status-watch-solid')} />
                        {i < milestones.length - 1 && <span className="mt-1 w-px flex-1 bg-border" />}
                      </div>
                      <button
                        onClick={() => setDrill({
                          title: formatProjectName(m.project),
                          subtitle: `${m.title} · ${MWs(m.capacity)} MW`,
                          projects: projects.filter((p) => p.project_name === m.project),
                        })}
                        className="min-w-0 flex-1 rounded px-1 py-0.5 text-left transition-colors hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      >
                        <span className="block text-[9.5px] font-bold uppercase tracking-wide text-primary">{m.dateLabel}</span>
                        <span className="block truncate text-[11px] font-semibold text-foreground">{m.title}</span>
                        <span className="block truncate text-[10px] text-fg-tertiary">
                          {formatProjectName(m.project)} · {MWs(m.capacity)} MW
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </motion.section>

            {/* Upcoming */}
            <motion.section variants={item} className="flex min-h-[250px] flex-col rounded-xl border border-border bg-card p-3">
              <h3 className="mb-1 flex items-center gap-1.5 text-[12px] font-bold text-foreground">
                <Target className="h-3.5 w-3.5 text-primary" /> Upcoming capacity
              </h3>
              <p className="mb-3 text-[10px] text-fg-tertiary">
                Built capacity not yet commissioned. No commissioning dates exist in this payload, so this is a
                pipeline figure rather than a schedule.
              </p>
              <div className="flex flex-1 flex-col justify-center gap-3">
                {upcoming.length === 0 ? (
                  <p className="text-center text-[11px] text-fg-tertiary">Everything in scope is commissioned.</p>
                ) : upcoming.map((u) => (
                  <button
                    key={u.segment}
                    onClick={() => setDrill({
                      title: `${u.segment} — remaining capacity`,
                      subtitle: `${u.projectCount} projects · ${MWs(u.mw)} MW outstanding`,
                      projects: u.projects,
                    })}
                    className="space-y-1.5 rounded-lg p-1.5 text-left transition-colors hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-[11px] font-semibold text-foreground">
                        {u.segment === 'Solar' ? <Sun className="h-3.5 w-3.5 text-amber-500" /> : <Wind className="h-3.5 w-3.5 text-blue-500" />}
                        {u.segment}
                        <span className="font-normal text-fg-tertiary">· {u.projectCount} projects</span>
                      </span>
                      <span className="text-[11px] font-bold tabular-nums text-foreground">{MWs(u.mw)} MW</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-fg-tertiary/15">
                        <div className="h-full rounded-full" style={{ width: `${Math.min(u.pctOfSegment, 100)}%`, background: u.segment === 'Solar' ? '#f59e0b' : '#0b74b1' }} />
                      </div>
                      <span className="w-9 text-right text-[10px] font-bold tabular-nums text-fg-tertiary">{u.pctOfSegment.toFixed(0)}%</span>
                    </div>
                  </button>
                ))}
              </div>
            </motion.section>

            {/* Risks & actions */}
            <motion.section variants={item} className="flex min-h-[250px] flex-col rounded-xl border border-border bg-card p-3">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="flex items-center gap-1.5 text-[12px] font-bold text-foreground">
                  <AlertTriangle className="h-3.5 w-3.5 text-status-watch-fg" /> Risks &amp; actions
                </h3>
                <button
                  onClick={() => setActionsOpen(true)}
                  className="text-[10px] font-semibold text-brand-blue hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  Tracked ({openCount})
                </button>
              </div>

              <div className="flex-1 space-y-2">
                {insights.filter((n) => n.severity === 'critical' || n.severity === 'warning').length === 0 ? (
                  <p className="flex h-full items-center justify-center text-center text-[11px] text-fg-tertiary">
                    No capacity risks detected in this window.
                  </p>
                ) : insights
                  .filter((n) => n.severity === 'critical' || n.severity === 'warning')
                  .map((n) => {
                    const meta = SEVERITY_META[n.severity];
                    const tracked = trackedIds.has(n.id);
                    return (
                      <div key={n.id} className="rounded-lg border border-border p-2">
                        <div className="flex items-start gap-2">
                          <span className={cx('grid h-6 w-6 shrink-0 place-items-center rounded-md border', meta.chip)}>
                            <meta.icon className="h-3 w-3" />
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="text-[11px] font-semibold leading-snug text-foreground">{n.title}</p>
                            <p className="mt-0.5 text-[10px] leading-snug text-fg-tertiary">{n.metric.value} · {n.category}</p>
                          </div>
                        </div>
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          <button
                            onClick={async () => {
                              await createAction({
                                title: n.title,
                                description: n.recommendation,
                                priority: n.severity === 'critical' ? 'High' : 'Medium',
                                owner: 'Unassigned',
                                dueDate: defaultDueDate(),
                                affectedProjects: n.affectedProjects,
                                affectedMW: n.affectedMW,
                                sourceInsightId: n.id,
                              });
                              setActionsOpen(true);
                            }}
                            disabled={tracked}
                            className="rounded-md bg-primary px-2 py-1 text-[10px] font-bold text-white transition-opacity hover:opacity-90 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                          >
                            {tracked ? 'Tracked' : 'Take action'}
                          </button>
                          <button
                            onClick={() => setInsightOpen(n)}
                            className="rounded-md border border-border px-2 py-1 text-[10px] font-bold text-fg-secondary transition-colors hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                          >
                            Review
                          </button>
                          {n.affectedProjects.length > 0 && (
                            <button
                              onClick={() => setDrill({
                                title: n.title,
                                subtitle: `${n.affectedProjects.length} projects affected`,
                                projects: projects.filter((p) => n.affectedProjects.includes(p.project_name)),
                              })}
                              className="rounded-md border border-border px-2 py-1 text-[10px] font-bold text-fg-secondary transition-colors hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                            >
                              Projects
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
              </div>
            </motion.section>
          </div>
        </>
      )}

      {/* ── Drawers ── */}
      <InsightDrawer
        insight={insightOpen}
        open={!!insightOpen}
        onClose={() => setInsightOpen(null)}
        projectIdByName={projectIdByName}
        onViewProjects={(names, title) => {
          setInsightOpen(null);
          setDrill({ title, subtitle: `${names.length} projects affected`, projects: projects.filter((p) => names.includes(p.project_name)) });
        }}
      />
      <ProjectDrilldown
        open={!!drill}
        onClose={() => setDrill(null)}
        title={drill?.title || ''}
        subtitle={drill?.subtitle}
        projects={drill?.projects || []}
      />
      <AskAiPanel open={askOpen} onClose={() => setAskOpen(false)} filters={filters} totals={totals} insights={insights} />
      <ActionsDrawer open={actionsOpen} onClose={() => setActionsOpen(false)} />
    </motion.div>
  );
}
