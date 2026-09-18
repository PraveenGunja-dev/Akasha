import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import { AlertTriangle, HardHat, CheckCircle2, CalendarClock, IndianRupee, ListChecks } from 'lucide-react';
import { KPITile, ChartFrame, Card, CardHeader } from '../../components/ui/primitives';
import { NotAvailable } from '../sap-intelligence/components/Drawer';
import { useChartTheme } from '../../lib/chartTheme';
import { formatProjectName } from '../../lib/projectName';
import { useProjectLink } from '../capacity/useProjectLink';
import PlannerHeader from './PlannerHeader';
import PlannerGrid from './PlannerGrid';
import { DEFAULT_FILTERS, monthLabel, monthRange, shiftMonth, fyMonths } from './types';
import type { PlannerData, PlannerFilters, PlannerProject } from './types';

/* Portfolio-wide module installation, laid out the way a planner works:
   what's due each month, what got done, who is behind. Scope (portfolio,
   phase) comes from the top bar exactly as the other dashboards read it.
   Everything shown is a direct read of P6 activity status/dates and ZSPS
   POrd value — see the endpoint docstring for the 'behind' definition. */

const container = { hidden: { opacity: 0 }, show: { opacity: 1, transition: { staggerChildren: 0.06 } } };
const item = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } };

const useResize = (ref: React.RefObject<any>) => {
  useEffect(() => {
    const el = ref.current?.ele as HTMLElement | undefined;
    if (!el?.parentElement) return;
    const ro = new ResizeObserver(() => ref.current?.getEchartsInstance()?.resize());
    ro.observe(el.parentElement);
    return () => ro.disconnect();
  }, [ref]);
};

const cr = (v: number) => `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

export default function InstallationPlannerPage() {
  const [searchParams] = useSearchParams();
  const portfolio = searchParams.get('portfolio');
  const phase = searchParams.get('phase') || 'Ongoing';
  const { themeName, categorical, status, chrome } = useChartTheme();
  const { open } = useProjectLink();

  const [data, setData] = useState<PlannerData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [filters, setFilters] = useState<PlannerFilters>(DEFAULT_FILTERS);
  const patch = useCallback((p: Partial<PlannerFilters>) => setFilters(f => ({ ...f, ...p })), []);
  const chartRef = useRef<any>(null);
  useResize(chartRef);

  useEffect(() => {
    let live = true;
    setLoading(true);
    const qs = new URLSearchParams();
    if (portfolio) qs.set('portfolio', portfolio);
    if (phase && phase !== 'ALL') qs.set('phase', phase);
    fetch(`/akasha/api/dashboard/installation-planner${qs.toString() ? `?${qs}` : ''}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: PlannerData) => { if (live) { setData(d); setError(null); } })
      .catch(e => { if (live) setError(e.message || 'Failed to load'); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [portfolio, phase, reloadKey]);

  // Month window shown in the grid and the curve.
  const months = useMemo(() => {
    if (!data) return [];
    const all = data.months.length ? data.months : [data.today];
    if (filters.window === 'ALL') return monthRange(all[0], all[all.length - 1]);
    if (filters.window === 'FY') { const [a, b] = fyMonths(data.today); return monthRange(a, b); }
    return monthRange(shiftMonth(data.today, -2), shiftMonth(data.today, 6));
  }, [data, filters.window]);

  const visible = useMemo<PlannerProject[]>(() => {
    if (!data) return [];
    const q = filters.search.trim().toLowerCase();
    return data.projects.filter(p => {
      if (q && !(`${p.name} ${p.project_id} ${p.cluster ?? ''}`.toLowerCase().includes(q))) return false;
      if (filters.show === 'behind') return p.behind > 0;
      if (filters.show === 'notstarted') return !p.not_applicable && p.summary!.completed === 0;
      if (filters.show === 'done') return !p.not_applicable && p.summary!.pct_complete >= 100;
      return true;
    });
  }, [data, filters.search, filters.show]);

  // Cumulative S-curve over the window, for the projects in view.
  const curve = useMemo(() => {
    const rows = months.map(m => visible.reduce((a, p) => {
      const c = p.monthly[m]; if (!c) return a;
      return { planned: a.planned + c.planned, baseline: a.baseline + c.baseline, completed: a.completed + c.completed };
    }, { planned: 0, baseline: 0, completed: 0 }));
    // seed with everything before the window so cumulative lines start at the right height
    const before = visible.reduce((a, p) => {
      for (const [k, c] of Object.entries(p.monthly)) if (months.length && k < months[0]) { a.planned += c.planned; a.baseline += c.baseline; a.completed += c.completed; }
      return a;
    }, { planned: 0, baseline: 0, completed: 0 });
    let cp = before.planned, cb = before.baseline, cc = before.completed;
    return rows.map(r => ({ ...r, cp: cp += r.planned, cb: cb += r.baseline, cc: cc += r.completed }));
  }, [visible, months]);

  const curveOption = useMemo(() => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { top: 0, itemHeight: 8, itemWidth: 16, textStyle: { fontSize: 11, color: chrome.fgSecondary } },
    grid: { left: 8, right: 12, top: 34, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: months.map(monthLabel), axisLabel: { fontSize: 10, color: chrome.fgTertiary }, axisLine: { lineStyle: { color: chrome.axisLine } } },
    yAxis: { type: 'value', name: 'Blocks (cumulative)', minInterval: 1, nameTextStyle: { fontSize: 10, color: chrome.fgTertiary }, axisLabel: { fontSize: 10, color: chrome.fgTertiary }, splitLine: { lineStyle: { color: chrome.gridLine } } },
    series: [
      { name: 'Current plan', type: 'line', data: curve.map(r => r.cp), symbol: 'none', lineStyle: { width: 1.5, type: 'dashed', color: categorical[0] }, itemStyle: { color: categorical[0] } },
      { name: 'Baseline', type: 'line', data: curve.map(r => r.cb), symbol: 'none', lineStyle: { width: 1, type: 'dotted', color: chrome.fgTertiary }, itemStyle: { color: chrome.fgTertiary } },
      { name: 'Completed', type: 'line', data: curve.map(r => r.cc), symbol: 'circle', symbolSize: 4, lineStyle: { width: 2, color: status.healthy }, itemStyle: { color: status.healthy }, areaStyle: { color: status.healthy, opacity: 0.06 },
        markLine: data ? { symbol: 'none', silent: true, lineStyle: { color: chrome.fgTertiary, type: 'solid', width: 1 }, label: { formatter: 'today', fontSize: 9, color: chrome.fgTertiary }, data: [{ xAxis: monthLabel(data.today) }] } : undefined },
    ],
  }), [curve, months, data, chrome, categorical, status]);

  const behindList = useMemo(() => [...visible].filter(p => p.behind > 0).sort((a, b) => b.behind - a.behind).slice(0, 8), [visible]);
  const scopeLabel = `${portfolio ?? 'All portfolios'} · ${phase === 'ALL' ? 'All phases' : phase}`;

  if (loading && !data) {
    return (
      <div className="flex flex-col gap-3">
        <div className="h-14 animate-pulse rounded-xl bg-muted/60" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map(i => <div key={i} className="h-[104px] animate-pulse rounded-xl bg-muted/60" />)}</div>
        <div className="h-[420px] animate-pulse rounded-xl bg-muted/60" />
      </div>
    );
  }
  if (error && !data) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-border bg-card p-10 text-center">
        <AlertTriangle className="h-6 w-6 text-status-critical-fg" />
        <p className="text-[13px] text-fg-secondary">Could not load the installation planner: {error}</p>
        <button onClick={() => setReloadKey(k => k + 1)} className="rounded-lg border border-border bg-card px-3 py-1.5 text-[12px] font-semibold text-fg-secondary hover:text-foreground">Retry</button>
      </div>
    );
  }
  const T = data!.totals;
  const pct = T.planned ? Math.round((T.completed / T.planned) * 100) : 0;
  const empty = visible.length === 0;

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="flex flex-col gap-3">
      <motion.section variants={item}>
        <PlannerHeader filters={filters} onChange={patch} onRefresh={() => setReloadKey(k => k + 1)} refreshing={loading} scopeLabel={scopeLabel} />
      </motion.section>

      <motion.section variants={item} className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KPITile label="Blocks installed" value={T.completed.toLocaleString('en-IN')} denominator={`/ ${T.planned.toLocaleString('en-IN')} planned`} icon={HardHat} source="P6"
          proportion={{ pct, nowLabel: `${pct}%`, capLabel: `${T.in_progress} in progress · ${T.not_started} not started` }} />
        <KPITile label={`This month · ${monthLabel(data!.today)}`} value={T.this_month.completed} denominator={`/ ${T.this_month.planned} due`} icon={CalendarClock} source="P6"
          tone={T.this_month.planned > 0 && T.this_month.completed < T.this_month.planned ? 'watch' : 'neutral'}
          subtext={T.this_month.planned ? `${T.this_month.planned - T.this_month.completed} still to finish this month` : 'Nothing due this month'} />
        <KPITile label="Projects behind plan" value={T.behind_projects} icon={AlertTriangle} source="P6" tone={T.behind_projects > 0 ? 'critical' : 'healthy'}
          subtext="Cumulative plan to date minus completed, per project" />
        <KPITile label="Materials delivered" value={cr(T.delivered_cr)} unit="Cr" denominator={`/ ${cr(T.ordered_cr)} Cr ordered`} icon={IndianRupee} source="SAP"
          proportion={{ pct: T.ordered_cr ? Math.round((T.delivered_cr / T.ordered_cr) * 100) : 0 }} subtext="ZSPS PO value, POrd only — value, not quantity" />
      </motion.section>

      {empty ? (
        <motion.section variants={item} className="rounded-xl border border-dashed border-border p-10 text-center text-[13px] text-fg-tertiary">
          No projects match this filter.
          <button onClick={() => patch({ show: 'all', search: '' })} className="ml-2 font-semibold text-brand-blue hover:underline">Reset</button>
        </motion.section>
      ) : (
        <motion.section variants={item}>
          <Card pad="md">
            <CardHeader icon={HardHat} title="Monthly plan vs completed" eyebrow={`${visible.length} projects · ${months.length} months · basis: ${filters.basis === 'planned' ? 'current plan' : 'baseline'}`} />
            <PlannerGrid projects={visible} months={months} today={data!.today} basis={filters.basis} />
          </Card>
        </motion.section>
      )}

      <motion.section variants={item} className="grid grid-cols-1 gap-3 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <ChartFrame icon={CheckCircle2} title="Cumulative installation curve" eyebrow="Plan vs baseline vs completed · projects in view" height={280}>
            <ReactECharts ref={chartRef} theme={themeName} option={curveOption} notMerge style={{ height: '100%', width: '100%' }} />
          </ChartFrame>
        </div>
        <div className="lg:col-span-4">
          <Card pad="md" className="h-full">
            <CardHeader icon={ListChecks} title="Behind plan" eyebrow={behindList.length ? `Top ${behindList.length} by shortfall` : 'Nothing behind in view'} />
            {behindList.length === 0 ? (
              <p className="text-[12px] text-fg-tertiary">Every project in view has completed at least what was planned through this month.</p>
            ) : (
              <ul className="divide-y divide-border-subtle">
                {behindList.map(p => (
                  <li key={p.project_id} className="flex items-center justify-between gap-3 py-2">
                    <button onClick={() => open(p.project_id, 'installation')} className="min-w-0 text-left">
                      <div className="truncate text-[12.5px] font-medium text-fg-primary hover:text-brand-blue">{formatProjectName(p.name)}</div>
                      <div className="text-[10.5px] text-fg-tertiary">
                        {p.next_due ? `next due ${monthLabel(p.next_due)}` : 'no further blocks planned'}
                        {p.ecod.slip_days != null && p.ecod.slip_days > 0 && ` · ECOD ${p.ecod.slip_days}d late`}
                      </div>
                    </button>
                    <span className="shrink-0 rounded-md border border-status-critical-border bg-status-critical-bg px-2 py-0.5 text-[11px] font-semibold tabular-nums text-status-critical-fg">−{p.behind} blocks</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </motion.section>

      <motion.section variants={item}>
        <NotAvailable what="Materials received by month" why="ZSPS carries no delivery/GRN date, so delivery is a cumulative value only; installation months come from P6." />
      </motion.section>
    </motion.div>
  );
}
