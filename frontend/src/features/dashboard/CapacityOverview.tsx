import React, { useEffect, useState, useMemo } from "react";
import { createPortal } from "react-dom";
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import {
  Activity, Zap, Sun, Wind, Calendar, RefreshCw, TrendingUp,
  TrendingDown, Layers, AlertTriangle, CheckCircle2, ArrowUpRight,
  Lightbulb, Sparkles, ChevronRight, Target, Clock, Shield,
  BarChart3, PieChart, Milestone, MessageSquare
} from "lucide-react";
import { motion, AnimatePresence } from 'framer-motion';
import { formatProjectName } from '../../lib/projectName';
import { useChartTheme } from '../../lib/chartTheme';

/* ═══════════════════════════════════════════════════════════════════════════
   CAPACITY OVERVIEW — premium dashboard
   Matches the reference design: 4 KPI cards + AI sidebar, trajectory chart,
   and a 4-panel analytics row at the bottom.
   ═══════════════════════════════════════════════════════════════════════════ */

const containerVariants: any = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.08 } }
};
const itemVariants: any = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } }
};

/* ── Interfaces ────────────────────────────────────────────────────────── */

interface FYData {
  name: string;
  solar_cod: number;
  solar_tr: number;
  wind_cod: number;
  wind_tr: number;
}

interface BlockMilestone {
  project: string;
  block: string;
  type: string;
  capacity: number;
  status: 'COD' | 'Trial Run' | 'Pending';
  tr_start: string | null;
  tr_finish: string | null;
  cod_start: string | null;
  cod_finish: string | null;
  tr_duration: number | null;
  cod_duration: number | null;
  gap_days: number | null;
}

interface ProjectBreakdown {
  project_id: string;
  project_name: string;
  type: string;
  total_capacity: number;
  total_blocks: number;
  tr_blocks: number;
  tr_mw: number;
  cod_blocks: number;
  cod_mw: number;
  remaining_capacity: number;
  remaining_blocks: number;
}

interface CapacityData {
  financial_years: FYData[];
  recent_milestones: BlockMilestone[];
  totals: { solar_cod: number; solar_tr: number; wind_cod: number; wind_tr: number };
  projects: ProjectBreakdown[];
  monthly_trends?: any[];
}

/* ── KPI Card (Section 1) ──────────────────────────────────────────────── */

const KPICard = ({
  title, value, unit, icon: Icon, trend, trendLabel, sparkData, color, onClick, active,
}: {
  title: string; value: string; unit?: string; icon: any;
  trend?: { dir: string; val: string }; trendLabel?: string;
  sparkData?: number[]; color: string; onClick?: () => void; active?: boolean;
}) => {
  const colorMap: Record<string, { bg: string; border: string; iconBg: string; iconFg: string; spark: string }> = {
    blue:   { bg: 'bg-gradient-to-br from-blue-50 to-blue-100/50 dark:from-blue-950/40 dark:to-blue-900/20',
              border: active ? 'border-blue-500 ring-2 ring-blue-200 dark:ring-blue-800' : 'border-blue-200/60 dark:border-blue-800/30',
              iconBg: 'bg-blue-100 dark:bg-blue-900/40', iconFg: 'text-blue-600 dark:text-blue-400', spark: '#3b82f6' },
    green:  { bg: 'bg-gradient-to-br from-emerald-50 to-emerald-100/50 dark:from-emerald-950/40 dark:to-emerald-900/20',
              border: active ? 'border-emerald-500 ring-2 ring-emerald-200 dark:ring-emerald-800' : 'border-emerald-200/60 dark:border-emerald-800/30',
              iconBg: 'bg-emerald-100 dark:bg-emerald-900/40', iconFg: 'text-emerald-600 dark:text-emerald-400', spark: '#10b981' },
    amber:  { bg: 'bg-gradient-to-br from-amber-50 to-orange-100/50 dark:from-amber-950/40 dark:to-orange-900/20',
              border: active ? 'border-amber-500 ring-2 ring-amber-200 dark:ring-amber-800' : 'border-amber-200/60 dark:border-amber-800/30',
              iconBg: 'bg-amber-100 dark:bg-amber-900/40', iconFg: 'text-amber-600 dark:text-amber-400', spark: '#f59e0b' },
    purple: { bg: 'bg-gradient-to-br from-purple-50 to-violet-100/50 dark:from-purple-950/40 dark:to-violet-900/20',
              border: active ? 'border-purple-500 ring-2 ring-purple-200 dark:ring-purple-800' : 'border-purple-200/60 dark:border-purple-800/30',
              iconBg: 'bg-purple-100 dark:bg-purple-900/40', iconFg: 'text-purple-600 dark:text-purple-400', spark: '#a855f7' },
  };
  const c = colorMap[color] || colorMap.blue;

  /* Tiny ECharts sparkline inside the KPI card. */
  const sparkOption = sparkData && sparkData.length > 2 ? {
    grid: { top: 2, right: 0, bottom: 2, left: 0 },
    xAxis: { show: false, type: 'category' as const, data: sparkData.map((_, i) => i) },
    yAxis: { show: false, type: 'value' as const, min: Math.min(...sparkData) * 0.9 },
    series: [{
      type: 'line' as const, smooth: true, showSymbol: false,
      lineStyle: { width: 2, color: c.spark },
      areaStyle: { color: { type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: c.spark + '30' }, { offset: 1, color: c.spark + '05' }] } },
      data: sparkData,
    }],
  } : null;

  return (
    <motion.div variants={itemVariants} className="h-full">
      <div
        onClick={onClick}
        className={`relative h-full px-5 py-4 flex flex-col justify-between cursor-pointer rounded-2xl border shadow-sm transition-all duration-200 hover:shadow-md ${c.bg} ${c.border}`}
      >
        <div className="flex justify-between items-start mb-1">
          <div className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${c.iconBg}`}>
              <Icon className={`w-4 h-4 ${c.iconFg}`} />
            </div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-fg-secondary">{title}</span>
          </div>
          {trend && (
            <span className={`text-[11px] font-bold flex items-center gap-0.5 px-2 py-0.5 rounded-full ${
              trend.dir === 'up'
                ? 'text-emerald-700 bg-emerald-100 dark:text-emerald-400 dark:bg-emerald-900/30'
                : 'text-red-700 bg-red-100 dark:text-red-400 dark:bg-red-900/30'
            }`}>
              {trend.dir === 'up' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              {trend.val}
            </span>
          )}
        </div>

        <div className="flex items-end justify-between mt-auto">
          <div>
            <div className="flex items-baseline gap-1.5">
              <span className="text-3xl font-black tracking-tight text-foreground leading-none">{value}</span>
              {unit && <span className="text-[11px] font-bold uppercase tracking-wider text-fg-secondary">{unit}</span>}
            </div>
            {trendLabel && <span className="text-[10px] text-fg-tertiary mt-0.5">{trendLabel}</span>}
          </div>
          {sparkOption && (
            <div className="w-24 h-10 opacity-80">
              <ReactECharts option={sparkOption} style={{ height: '100%', width: '100%' }} opts={{ renderer: 'svg' }} />
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

/* ── KPI Breakdown Modal ───────────────────────────────────────────────── */

const KPIBreakdownModal = ({ isOpen, onClose, activeKpi, projects }: {
  isOpen: boolean; onClose: () => void; activeKpi: string | null; projects: ProjectBreakdown[];
}) => {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      const handleKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
      window.addEventListener('keydown', handleKeyDown);
      return () => { document.body.style.overflow = 'unset'; window.removeEventListener('keydown', handleKeyDown); };
    } else { document.body.style.overflow = 'unset'; }
  }, [isOpen, onClose]);

  if (!isOpen || !projects) return null;

  let filteredProjects = projects;
  if (activeKpi === "COD Done") filteredProjects = projects.filter(p => p.cod_mw > 0);
  else if (activeKpi === "Trial Run Only") filteredProjects = projects.filter(p => p.tr_mw > 0);
  else if (activeKpi === "Solar Portfolio") filteredProjects = projects.filter(p => p.type === 'Solar');
  else if (activeKpi === "Wind Portfolio") filteredProjects = projects.filter(p => p.type === 'Wind');

  const totalCap = filteredProjects.reduce((s, p) => s + p.total_capacity, 0);
  const totalCod = filteredProjects.reduce((s, p) => s + p.cod_mw, 0);
  const totalTr = filteredProjects.reduce((s, p) => s + p.tr_mw, 0);

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/40 backdrop-blur-md" onClick={onClose} />
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1, transition: { type: 'spring', bounce: 0, duration: 0.4 } }}
            exit={{ opacity: 0, y: 20, scale: 0.95, transition: { duration: 0.2 } }}
            className="bg-background/90 backdrop-blur-2xl w-full max-w-5xl rounded-3xl shadow-2xl relative z-10 overflow-hidden flex flex-col max-h-[85vh] border border-border"
          >
            <div className="px-6 py-5 border-b border-border/50 flex justify-between items-start bg-gradient-to-r from-gray-50/50 to-transparent dark:from-gray-800/20">
              <div>
                <h2 className="text-lg font-black text-primary flex items-center gap-2 mb-2">
                  <Layers className="w-5 h-5" /> {activeKpi}
                </h2>
                <div className="flex gap-2 flex-wrap">
                  <span className="text-[11px] font-bold text-fg-secondary bg-muted/50 px-3 py-1.5 rounded-full border border-border/50">Total: <span className="text-foreground ml-1">{totalCap.toFixed(1)} MW</span></span>
                  <span className="text-[11px] font-bold text-primary bg-primary/5 px-3 py-1.5 rounded-full border border-primary/20">COD: <span className="font-black ml-1">{totalCod.toFixed(1)} MW</span></span>
                  <span className="text-[11px] font-bold text-success bg-success/5 px-3 py-1.5 rounded-full border border-success/20">TR: <span className="font-black ml-1">{totalTr.toFixed(1)} MW</span></span>
                </div>
              </div>
              <button onClick={onClose} className="p-2 bg-muted hover:bg-muted-foreground/20 rounded-full transition-colors">
                <span className="sr-only">Close</span>
                <svg width="14" height="14" viewBox="0 0 15 15" fill="none"><path d="M11.7816 4.03157C12.0062 3.80702 12.0062 3.44295 11.7816 3.2184C11.5571 2.99385 11.193 2.99385 10.9685 3.2184L7.50005 6.68682L4.03164 3.2184C3.80708 2.99385 3.44301 2.99385 3.21846 3.2184C2.99391 3.44295 2.99391 3.80702 3.21846 4.03157L6.68688 7.49999L3.21846 10.9684C2.99391 11.193 2.99391 11.557 3.21846 11.7816C3.44301 12.0061 3.80708 12.0061 4.03164 11.7816L7.50005 8.31316L10.9685 11.7816C11.193 12.0061 11.5571 12.0061 11.7816 11.7816C12.0062 11.557 12.0062 11.193 11.7816 10.9684L8.31322 7.49999L11.7816 4.03157Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd" /></svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto min-h-0 custom-scrollbar">
              {filteredProjects.length === 0 ? (
                <div className="text-center py-16 text-fg-tertiary font-medium">No projects found.</div>
              ) : (
                <div className="px-6 pb-6 pt-2">
                  <table className="w-full text-left text-sm border-separate border-spacing-y-1.5">
                    <thead className="text-[10px] font-black text-fg-tertiary uppercase tracking-[0.1em] sticky top-0 bg-card/95 backdrop-blur-md z-10">
                      <tr>
                        <th className="py-3 pl-4 rounded-l-xl">Project</th>
                        <th className="py-3 text-center">Type</th>
                        <th className="py-3 text-center">Total Cap</th>
                        <th className="py-3 text-center">COD</th>
                        <th className="py-3 text-center">TR Only</th>
                        <th className="py-3 text-center rounded-r-xl">Progress</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredProjects.map((p, idx) => {
                        const pct = p.total_capacity > 0 ? ((p.cod_mw + p.tr_mw) / p.total_capacity * 100) : 0;
                        return (
                          <tr key={idx} className="bg-muted/30 hover:bg-muted/60 transition-all rounded-xl">
                            <td className="px-4 py-3 font-bold text-[12px] text-foreground max-w-[200px] truncate rounded-l-xl" title={formatProjectName(p.project_name)}>{formatProjectName(p.project_name)}</td>
                            <td className="px-2 py-3 text-center">
                              {p.type === 'Solar' ? <Sun size={14} className="mx-auto text-amber-500" /> : <Wind size={14} className="mx-auto text-blue-500" />}
                            </td>
                            <td className="px-2 py-3 text-center text-[12px] font-black text-foreground">{p.total_capacity.toFixed(1)}</td>
                            <td className="px-2 py-3 text-center">
                              {p.cod_mw > 0 ? <span className="text-[11px] font-black text-primary bg-primary/10 px-2 py-1 rounded-full">{p.cod_mw.toFixed(1)} MW</span> : <span className="text-fg-tertiary">-</span>}
                            </td>
                            <td className="px-2 py-3 text-center">
                              {p.tr_mw > 0 ? <span className="text-[11px] font-black text-success bg-success/10 px-2 py-1 rounded-full">{p.tr_mw.toFixed(1)} MW</span> : <span className="text-fg-tertiary">-</span>}
                            </td>
                            <td className="px-4 py-3 text-center rounded-r-xl">
                              <div className="flex flex-col gap-1">
                                <span className="text-[10px] font-bold text-fg-tertiary">{pct.toFixed(0)}%</span>
                                <div className="w-full h-1.5 bg-border/50 rounded-full overflow-hidden flex">
                                  {p.cod_mw > 0 && <div className="h-full bg-primary" style={{ width: `${Math.min((p.cod_mw / p.total_capacity) * 100, 100)}%` }} />}
                                  {p.tr_mw > 0 && <div className="h-full bg-success" style={{ width: `${Math.min((p.tr_mw / p.total_capacity) * 100, 100)}%` }} />}
                                </div>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
};

/* ── Main Component ────────────────────────────────────────────────────── */

export default function CapacityOverview() {
  const [data, setData] = useState<CapacityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeKpi, setActiveKpi] = useState<string | null>(null);
  const [chartFilter, setChartFilter] = useState<string>('All');
  const [viewMode, setViewMode] = useState<'Monthly' | 'Quarterly' | 'Yearly'>('Monthly');
  const [searchParams] = useSearchParams();
  const portfolio = searchParams.get('portfolio');
  const phase = searchParams.get('phase');
  const { themeName } = useChartTheme();

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (portfolio) params.append('portfolio', portfolio);
    if (phase) params.append('phase', phase);
    const qs = params.toString() ? `?${params.toString()}` : '';
    const url = `/akasha/api/dashboard/capacity-overview${qs}`;

    fetch(url)
      .then(res => res.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { console.error(e); setError("Failed to load Capacity Overview data."); setLoading(false); });
  }, [portfolio, phase]);

  /* ── Derived values ──────────────────────────────────────────────────── */

  const { totalCod, totalTr, totalSolar, totalWind, totalPortfolio } = useMemo(() => {
    if (!data) return { totalCod: 0, totalTr: 0, totalSolar: 0, totalWind: 0, totalPortfolio: 0 };
    const projects = data.projects || [];
    return {
      totalCod: projects.reduce((s, p) => s + p.cod_mw, 0),
      totalTr: projects.reduce((s, p) => s + p.tr_mw, 0),
      totalSolar: projects.filter(p => p.type === 'Solar').reduce((s, p) => s + p.total_capacity, 0),
      totalWind: projects.filter(p => p.type === 'Wind').reduce((s, p) => s + p.total_capacity, 0),
      totalPortfolio: projects.reduce((s, p) => s + p.total_capacity, 0),
    };
  }, [data]);

  /* Sparklines from the FY series. */
  const sparklines = useMemo(() => {
    if (!data) return { cod: [], tr: [], solar: [], wind: [] };
    const fys = [...(data.financial_years || [])].sort((a, b) => a.name.localeCompare(b.name));
    let rc = 0, rt = 0, rs = 0, rw = 0;
    const cod: number[] = [], tr: number[] = [], solar: number[] = [], wind: number[] = [];
    fys.forEach(fy => {
      rc += fy.solar_cod + fy.wind_cod; cod.push(rc);
      rt += fy.solar_tr + fy.wind_tr; tr.push(rt);
      rs += fy.solar_cod + fy.solar_tr; solar.push(rs);
      rw += fy.wind_cod + fy.wind_tr; wind.push(rw);
    });
    return { cod, tr, solar, wind };
  }, [data]);

  /* Trends vs previous FY. */
  const trends = useMemo(() => {
    if (!data || (data.financial_years || []).length < 2) return { cod: null, tr: null, solar: null, wind: null };
    const fys = [...data.financial_years].sort((a, b) => a.name.localeCompare(b.name));
    const cur = fys[fys.length - 1], prev = fys[fys.length - 2];
    const calc = (c: number, p: number) => {
      if (p === 0 && c > 0) return { dir: 'up', val: '+100%' };
      if (p === 0) return null;
      const pct = ((c - p) / p) * 100;
      return { dir: pct >= 0 ? 'up' : 'down', val: `${pct >= 0 ? '+' : ''}${pct.toFixed(0)}%` };
    };
    return {
      cod: calc(cur.solar_cod + cur.wind_cod, prev.solar_cod + prev.wind_cod),
      tr: calc(cur.solar_tr + cur.wind_tr, prev.solar_tr + prev.wind_tr),
      solar: calc(cur.solar_cod + cur.solar_tr, prev.solar_cod + prev.solar_tr),
      wind: calc(cur.wind_cod + cur.wind_tr, prev.wind_cod + prev.wind_tr),
    };
  }, [data]);

  /* AI Insights derived from the data. */
  const aiInsights = useMemo(() => {
    if (!data) return [];
    const projects = data.projects || [];
    const pctCod = totalPortfolio > 0 ? ((totalCod / totalPortfolio) * 100) : 0;
    const solarMW = projects.filter(p => p.type === 'Solar').reduce((s, p) => s + p.cod_mw + p.tr_mw, 0);
    const windRemaining = projects.filter(p => p.type === 'Wind').reduce((s, p) => s + p.remaining_capacity, 0);
    const delayedProjects = projects.filter(p => p.remaining_capacity > 0 && p.cod_mw === 0 && p.tr_mw === 0);

    return [
      {
        icon: CheckCircle2, color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-900/20',
        title: 'Capacity on track',
        desc: `Total capacity is ${pctCod.toFixed(0)}% commissioned with ${totalCod.toFixed(0)} MW at COD.`,
      },
      {
        icon: TrendingUp, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20',
        title: 'Solar growth acceleration',
        desc: `Solar capacity reached ${solarMW.toFixed(0)} MW across COD and trial run stages.`,
      },
      {
        icon: AlertTriangle, color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/20',
        title: 'Wind commissioning delay risk',
        desc: `${windRemaining.toFixed(0)} MW of wind capacity still pending commissioning.`,
      },
      {
        icon: Lightbulb, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/20',
        title: 'Optimal opportunity',
        desc: `${delayedProjects.length} project(s) with no milestones yet — early acceleration could improve annual targets.`,
      },
    ];
  }, [data, totalCod, totalPortfolio]);

  /* ── Chart config ────────────────────────────────────────────────────── */

  const formatMonthLabel = (label: string) => {
    if (!label || !label.includes('-')) return label;
    const [year, month] = label.split('-');
    const date = new Date(parseInt(year), parseInt(month) - 1);
    return date.toLocaleDateString('en-US', { month: 'short' }) + " '" + year.substring(2);
  };

  const allSeriesDef = [
    { key: "Solar COD", color: "#ea580c", name: "Solar COD", type: 'Solar', kpi: 'COD' },
    { key: "Solar Trial Run", color: "#eab308", name: "Solar TR", type: 'Solar', kpi: 'TR' },
    { key: "Wind COD", color: "#0284c7", name: "Wind COD", type: 'Wind', kpi: 'COD' },
    { key: "Wind Trial Run", color: "#38bdf8", name: "Wind TR", type: 'Wind', kpi: 'TR' },
  ];

  const visibleSeries = allSeriesDef.filter(s => {
    if (chartFilter === 'All') return true;
    if (chartFilter === 'COD') return s.kpi === 'COD';
    if (chartFilter === 'TR') return s.kpi === 'TR';
    if (chartFilter === 'SOLAR') return s.type === 'Solar';
    if (chartFilter === 'WIND') return s.type === 'Wind';
    return true;
  });

  const chartData = useMemo(() => data?.monthly_trends || [], [data]);

  const trajectoryOption = useMemo(() => {
    if (chartData.length === 0) return null;

    /* Find today's position in the data. */
    const today = new Date();
    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
    const todayIdx = chartData.findIndex((d: any) => d.name === todayStr);
    const labels = chartData.map((d: any) => formatMonthLabel(d.name));

    return {
      tooltip: {
        trigger: 'axis' as const,
        backgroundColor: 'rgba(255,255,255,0.95)',
        borderColor: '#e5e7eb',
        textStyle: { color: '#374151', fontSize: 12, fontWeight: 500 },
        padding: [12, 16],
        borderRadius: 12,
        extraCssText: 'backdrop-filter:blur(10px);box-shadow:0 10px 25px -5px rgba(0,0,0,0.1)',
        valueFormatter: (v: any) => Number(v).toFixed(1) + ' MW',
      },
      legend: {
        bottom: 0, itemWidth: 10, itemHeight: 10, icon: 'circle',
        textStyle: { color: '#6b7280', fontSize: 11, fontWeight: 600, fontFamily: 'inherit' },
      },
      grid: { top: 30, left: 10, right: 30, bottom: 50, containLabel: true },
      xAxis: {
        type: 'category' as const, boundaryGap: false, data: labels,
        axisLine: { lineStyle: { color: '#e5e7eb' } },
        axisLabel: { color: '#6b7280', fontWeight: 600, fontSize: 10, interval: 'auto' },
      },
      yAxis: {
        type: 'value' as const, name: 'Capacity (MW)', nameTextStyle: { color: '#9ca3af', fontSize: 10, padding: [0, 0, 0, 40] },
        splitLine: { lineStyle: { type: 'dashed' as const, color: '#f3f4f6' } },
        axisLabel: { color: '#9ca3af', fontSize: 11, fontWeight: 600 },
      },
      series: [
        /* "Today" marker line. */
        ...(todayIdx >= 0 ? [{
          type: 'line' as const, markLine: {
            silent: true, symbol: 'none',
            lineStyle: { type: 'solid' as const, color: '#3b82f6', width: 2 },
            label: { formatter: 'Today', position: 'start' as const, fontSize: 11, fontWeight: 700, color: '#3b82f6',
              backgroundColor: '#eff6ff', padding: [3, 8], borderRadius: 6 },
            data: [{ xAxis: todayIdx }],
          }, data: [],
        }] : []),
        /* Data series. */
        ...visibleSeries.map(s => ({
          name: s.name, type: 'line' as const, smooth: true, showSymbol: false,
          symbol: 'circle', symbolSize: 6,
          lineStyle: { width: 2.5, color: s.color },
          itemStyle: { color: s.color },
          areaStyle: {
            color: {
              type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [{ offset: 0, color: s.color + '20' }, { offset: 1, color: s.color + '02' }],
            },
          },
          data: chartData.map((d: any) => d[s.key]),
        })),
      ],
    };
  }, [chartData, visibleSeries]);

  /* ── Donut chart for Capacity by Segment ─────────────────────────────── */
  const donutOption = useMemo(() => {
    if (!data) return null;
    const projects = data.projects || [];
    const solarCod = projects.filter(p => p.type === 'Solar').reduce((s, p) => s + p.cod_mw, 0);
    const windCod = projects.filter(p => p.type === 'Wind').reduce((s, p) => s + p.cod_mw, 0);
    const codOthers = totalCod - solarCod - windCod;
    const segments = [
      { name: 'Solar', value: Math.round(projects.filter(p => p.type === 'Solar').reduce((s, p) => s + p.total_capacity, 0)), color: '#f59e0b' },
      { name: 'Wind', value: Math.round(projects.filter(p => p.type === 'Wind').reduce((s, p) => s + p.total_capacity, 0)), color: '#3b82f6' },
      { name: 'COD (Others)', value: Math.round(Math.max(0, codOthers)), color: '#a855f7' },
      { name: 'Trial Run', value: Math.round(totalTr), color: '#10b981' },
    ].filter(s => s.value > 0);

    return {
      tooltip: { trigger: 'item' as const, formatter: '{b}: {c} MW ({d}%)' },
      series: [{
        type: 'pie' as const, radius: ['55%', '80%'], center: ['35%', '50%'],
        avoidLabelOverlap: false,
        label: { show: false },
        emphasis: { label: { show: false } },
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        data: segments.map(s => ({ value: s.value, name: s.name, itemStyle: { color: s.color } })),
      }],
    };
  }, [data, totalCod, totalTr]);

  const donutSegments = useMemo(() => {
    if (!data) return [];
    const projects = data.projects || [];
    const total = totalPortfolio || 1;
    return [
      { label: 'Solar', value: projects.filter(p => p.type === 'Solar').reduce((s, p) => s + p.total_capacity, 0), color: '#f59e0b' },
      { label: 'Wind', value: projects.filter(p => p.type === 'Wind').reduce((s, p) => s + p.total_capacity, 0), color: '#3b82f6' },
      { label: 'COD (Others)', value: totalCod, color: '#a855f7' },
      { label: 'Trial Run', value: totalTr, color: '#10b981' },
    ].map(s => ({ ...s, pct: ((s.value / total) * 100).toFixed(1) }));
  }, [data, totalCod, totalTr, totalPortfolio]);

  /* ── Upcoming capacity (next 6 months) from milestones ──────────────── */
  const upcomingCapacity = useMemo(() => {
    if (!data) return [];
    const now = new Date();
    const sixMonths = new Date(now);
    sixMonths.setMonth(sixMonths.getMonth() + 6);
    const projects = data.projects || [];
    const solar = projects.filter(p => p.type === 'Solar').reduce((s, p) => s + p.remaining_capacity, 0);
    const wind = projects.filter(p => p.type === 'Wind').reduce((s, p) => s + p.remaining_capacity, 0);
    const total = solar + wind || 1;
    return [
      { label: 'Solar', value: Math.round(solar), pct: Math.round((solar / total) * 100), color: '#f59e0b' },
      { label: 'Wind', value: Math.round(wind), pct: Math.round((wind / total) * 100), color: '#3b82f6' },
    ];
  }, [data]);

  /* ── Key milestones (recent 4) ──────────────────────────────────────── */
  const keyMilestones = useMemo(() => {
    if (!data) return [];
    return (data.recent_milestones || [])
      .filter(m => m.status === 'COD' || m.status === 'Trial Run')
      .slice(0, 4)
      .map(m => {
        const dateStr = m.cod_finish || m.tr_finish || m.cod_start || m.tr_start || '';
        const d = dateStr ? new Date(dateStr) : null;
        const label = d ? d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '';
        return {
          date: label,
          desc: `${m.capacity.toFixed(1)} MW ${m.status === 'COD' ? 'expected COD' : 'under trial run'}`,
          project: formatProjectName(m.project),
        };
      });
  }, [data]);

  /* ── Risks derived from data ─────────────────────────────────────────── */
  const risks = useMemo(() => {
    if (!data) return [];
    const projects = data.projects || [];
    const windPending = projects.filter(p => p.type === 'Wind' && p.remaining_capacity > 0);
    const windPendingMW = windPending.reduce((s, p) => s + p.remaining_capacity, 0);
    const solarPending = projects.filter(p => p.type === 'Solar' && p.remaining_capacity > p.total_capacity * 0.5);
    const noMilestones = projects.filter(p => p.cod_mw === 0 && p.tr_mw === 0);

    const items = [];
    if (windPending.length > 0) {
      items.push({
        icon: Wind, color: 'text-amber-600', bg: 'bg-amber-50 dark:bg-amber-900/20',
        title: `${windPending.length} wind projects (${windPendingMW.toFixed(0)} MW)`,
        desc: 'at risk due to land & clearance delays.',
        action: 'Take Action',
      });
    }
    if (solarPending.length > 0) {
      items.push({
        icon: Sun, color: 'text-blue-600', bg: 'bg-blue-50 dark:bg-blue-900/20',
        title: `Solar TR to COD delay`,
        desc: `may impact Q2 target for ${solarPending.length} projects.`,
        action: 'Review',
      });
    }
    if (noMilestones.length > 0) {
      items.push({
        icon: AlertTriangle, color: 'text-red-600', bg: 'bg-red-50 dark:bg-red-900/20',
        title: `Grid evacuation pending`,
        desc: `for ${noMilestones.length} projects (${noMilestones.reduce((s, p) => s + p.total_capacity, 0).toFixed(0)} MW).`,
        action: 'Track',
      });
    }
    return items;
  }, [data]);

  /* ── Loading / error ─────────────────────────────────────────────────── */

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[500px] w-full">
        <RefreshCw className="w-8 h-8 text-primary animate-spin mb-4" />
        <p className="text-fg-tertiary font-medium">Analyzing Capacity Metrics…</p>
      </div>
    );
  }
  if (error || !data) return <div className="text-destructive flex justify-center items-center h-64 font-bold">{error || "No data available"}</div>;

  const { financial_years, monthly_trends, recent_milestones, totals, projects } = data;

  /* ════════════════════════════════════════════════════════════════════════
     RENDER
     ════════════════════════════════════════════════════════════════════════ */

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="show" className="flex flex-col gap-4 w-full pb-8">
      <KPIBreakdownModal isOpen={!!activeKpi} onClose={() => setActiveKpi(null)} activeKpi={activeKpi} projects={projects || []} />

      {/* ══════════════════════════════════════════════════════════════════
          SECTION 1 — KPI Band + AI Insights
          ══════════════════════════════════════════════════════════════════ */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        {/* 4 KPI Cards */}
        <div className="lg:col-span-8 grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KPICard title="COD Done" value={totalCod.toFixed(1)} unit="MW" icon={Zap} color="blue"
            trend={trends.cod || undefined} trendLabel="vs previous period"
            sparkData={sparklines.cod} active={activeKpi === 'COD Done'}
            onClick={() => setActiveKpi('COD Done')} />
          <KPICard title="Trial Run Only" value={totalTr.toFixed(1)} unit="MW" icon={Activity} color="green"
            trend={trends.tr || undefined} trendLabel="vs previous period"
            sparkData={sparklines.tr} active={activeKpi === 'Trial Run Only'}
            onClick={() => setActiveKpi('Trial Run Only')} />
          <KPICard title="Solar Portfolio" value={totalSolar.toFixed(1)} unit="MW" icon={Sun} color="amber"
            trend={trends.solar || undefined} trendLabel="vs previous period"
            sparkData={sparklines.solar} active={activeKpi === 'Solar Portfolio'}
            onClick={() => setActiveKpi('Solar Portfolio')} />
          <KPICard title="Wind Portfolio" value={totalWind.toFixed(1)} unit="MW" icon={Wind} color="purple"
            trend={trends.wind || undefined} trendLabel="vs previous period"
            sparkData={sparklines.wind} active={activeKpi === 'Wind Portfolio'}
            onClick={() => setActiveKpi('Wind Portfolio')} />
        </div>

        {/* AI Insights Panel */}
        <motion.div variants={itemVariants} className="lg:col-span-4">
          <div className="h-full rounded-2xl border border-border bg-card shadow-sm overflow-hidden flex flex-col">
            <div className="px-4 py-3 flex items-center justify-between border-b border-border/50">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-primary" />
                <span className="text-[12px] font-bold text-foreground">AI Insights</span>
                <span className="text-[9px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded-md uppercase tracking-wider">Beta</span>
              </div>
              <span className="text-[10px] text-primary font-semibold cursor-pointer hover:underline flex items-center gap-0.5">
                View All <ArrowUpRight className="w-3 h-3" />
              </span>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
              {aiInsights.map((insight, i) => (
                <div key={i} className="flex gap-2.5 p-2 rounded-xl hover:bg-muted/50 transition-colors cursor-pointer">
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${insight.bg}`}>
                    <insight.icon className={`w-3.5 h-3.5 ${insight.color}`} />
                  </div>
                  <div className="min-w-0">
                    <h4 className="text-[11px] font-bold text-foreground leading-tight">{insight.title}</h4>
                    <p className="text-[10px] text-fg-tertiary leading-snug mt-0.5">{insight.desc}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="px-3 py-2 border-t border-border/50">
              <div className="flex items-center gap-2 px-3 py-2 bg-muted/50 rounded-xl text-[11px] text-fg-tertiary">
                <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                Ask AI anything about capacity…
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* ══════════════════════════════════════════════════════════════════
          SECTION 2 — Capacity Trajectory Chart
          ══════════════════════════════════════════════════════════════════ */}
      <motion.div variants={itemVariants} className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
        <div className="flex flex-wrap justify-between items-center gap-3 px-5 pt-4 pb-2">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-primary" />
            <h3 className="text-[13px] font-bold text-foreground">Capacity Trajectory</h3>
            <span className="text-[10px] text-fg-tertiary hidden sm:inline">Actual, Planned and Forecasted capacity addition across segments</span>
          </div>

          <div className="flex items-center gap-2">
            {/* Filter pills */}
            <div className="flex bg-muted p-1 rounded-xl border border-border/50">
              {['All', 'COD', 'TR', 'SOLAR', 'WIND'].map(f => (
                <button
                  key={f}
                  onClick={() => setChartFilter(f)}
                  className={`px-3 py-1.5 text-[10px] font-bold uppercase rounded-lg transition-colors ${
                    chartFilter === f
                      ? 'bg-card text-primary shadow-sm'
                      : 'text-fg-tertiary hover:text-foreground'
                  }`}
                >{f}</button>
              ))}
            </div>

            {/* Period toggle */}
            <div className="flex bg-muted p-1 rounded-xl border border-border/50">
              {(['Monthly', 'Quarterly', 'Yearly'] as const).map(m => (
                <button
                  key={m}
                  onClick={() => setViewMode(m)}
                  className={`px-3 py-1.5 text-[10px] font-bold rounded-lg transition-colors ${
                    viewMode === m ? 'bg-card text-primary shadow-sm' : 'text-fg-tertiary hover:text-foreground'
                  }`}
                >{m}</button>
              ))}
            </div>
          </div>
        </div>

        {/* Legend row */}
        <div className="flex flex-wrap gap-4 px-5 pb-2">
          {allSeriesDef.map(s => (
            <span key={s.key} className="flex items-center gap-1.5 text-[10px] text-fg-secondary font-medium">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: s.color }} />
              {s.name}
            </span>
          ))}
          <span className="ml-auto flex items-center gap-3 text-[10px] text-fg-tertiary font-medium">
            <span className="flex items-center gap-1"><span className="w-4 h-0 border-t-2 border-foreground" /> Actual</span>
            <span className="flex items-center gap-1"><span className="w-4 h-0 border-t-2 border-dashed border-foreground" /> Planned</span>
          </span>
        </div>

        {/* Chart */}
        <div className="h-[340px] px-2 pb-4">
          {trajectoryOption ? (
            <ReactECharts theme={themeName} option={trajectoryOption} style={{ height: '100%', width: '100%' }} notMerge />
          ) : (
            <div className="flex items-center justify-center h-full text-fg-tertiary text-sm">No monthly trend data available</div>
          )}
        </div>
      </motion.div>

      {/* ══════════════════════════════════════════════════════════════════
          SECTION 3 — Bottom 4-Panel Row
          ══════════════════════════════════════════════════════════════════ */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">

        {/* Panel A — Capacity by Segment */}
        <motion.div variants={itemVariants} className="rounded-2xl border border-border bg-card shadow-sm p-4 flex flex-col min-h-[260px]">
          <div className="flex items-center gap-2 mb-3">
            <PieChart className="w-4 h-4 text-primary" />
            <h4 className="text-[12px] font-bold text-foreground">Capacity by Segment</h4>
          </div>
          <div className="flex-1 flex items-center gap-2">
            {/* Donut */}
            <div className="w-1/2 h-[160px] relative">
              {donutOption && <ReactECharts option={donutOption} style={{ height: '100%', width: '100%' }} opts={{ renderer: 'svg' }} />}
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none" style={{ left: '-15%' }}>
                <span className="text-xl font-black text-foreground leading-none">{totalPortfolio.toFixed(1)}</span>
                <span className="text-[9px] text-fg-tertiary font-medium">MW Total</span>
              </div>
            </div>
            {/* Breakdown */}
            <div className="w-1/2 flex flex-col gap-2">
              {donutSegments.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
                  <span className="font-semibold text-foreground flex-1 truncate">{s.label}</span>
                  <span className="font-black text-foreground tabular-nums">{s.value.toFixed(1)}</span>
                  <span className="text-fg-tertiary font-medium w-10 text-right tabular-nums">{s.pct}%</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* Panel B — Key Milestones */}
        <motion.div variants={itemVariants} className="rounded-2xl border border-border bg-card shadow-sm p-4 flex flex-col min-h-[260px]">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Milestone className="w-4 h-4 text-primary" />
              <h4 className="text-[12px] font-bold text-foreground">Key Milestones</h4>
            </div>
            <span className="text-[10px] text-primary font-semibold cursor-pointer hover:underline flex items-center gap-0.5">
              View Timeline <ArrowUpRight className="w-3 h-3" />
            </span>
          </div>
          <div className="flex-1 flex flex-col gap-3">
            {keyMilestones.length === 0 ? (
              <div className="flex-1 flex items-center justify-center text-fg-tertiary text-[11px]">No milestones found</div>
            ) : (
              keyMilestones.map((m, i) => (
                <div key={i} className="flex gap-3 items-start">
                  <div className="flex flex-col items-center shrink-0">
                    <div className="w-2.5 h-2.5 rounded-full bg-primary border-2 border-primary/20" />
                    {i < keyMilestones.length - 1 && <div className="w-px flex-1 bg-border mt-1" />}
                  </div>
                  <div className="min-w-0 pb-1">
                    <span className="text-[10px] font-bold text-primary">{m.date}</span>
                    <p className="text-[11px] text-foreground font-semibold truncate">{m.desc}</p>
                    <p className="text-[10px] text-fg-tertiary truncate">{m.project}</p>
                  </div>
                </div>
              ))
            )}
          </div>
        </motion.div>

        {/* Panel C — Upcoming Capacity */}
        <motion.div variants={itemVariants} className="rounded-2xl border border-border bg-card shadow-sm p-4 flex flex-col min-h-[260px]">
          <div className="flex items-center gap-2 mb-3">
            <Target className="w-4 h-4 text-primary" />
            <h4 className="text-[12px] font-bold text-foreground">Upcoming Capacity</h4>
          </div>
          <p className="text-[10px] text-fg-tertiary mb-3">Remaining capacity pending commissioning</p>
          <div className="flex-1 flex flex-col gap-3 justify-center">
            {upcomingCapacity.map((item, i) => (
              <div key={i} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {item.label === 'Solar' ? <Sun className="w-3.5 h-3.5 text-amber-500" /> : <Wind className="w-3.5 h-3.5 text-blue-500" />}
                    <span className="text-[11px] font-semibold text-foreground">{item.label}</span>
                  </div>
                  <span className="text-[11px] font-black text-foreground tabular-nums">{item.value.toLocaleString('en-IN')} MW</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }} animate={{ width: `${Math.min(item.pct, 100)}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                      className="h-full rounded-full" style={{ backgroundColor: item.color }}
                    />
                  </div>
                  <span className="text-[10px] font-bold text-fg-tertiary w-10 text-right tabular-nums">{item.pct}%</span>
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Panel D — Risks & Actions */}
        <motion.div variants={itemVariants} className="rounded-2xl border border-border bg-card shadow-sm p-4 flex flex-col min-h-[260px]">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              <h4 className="text-[12px] font-bold text-foreground">Risks & Actions</h4>
            </div>
            <span className="text-[10px] text-primary font-semibold cursor-pointer hover:underline flex items-center gap-0.5">
              View All <ArrowUpRight className="w-3 h-3" />
            </span>
          </div>
          <div className="flex-1 flex flex-col gap-2.5">
            {risks.length === 0 ? (
              <div className="flex-1 flex items-center justify-center text-fg-tertiary text-[11px]">No active risks detected</div>
            ) : (
              risks.map((r, i) => (
                <div key={i} className="flex gap-2.5 items-start p-2 rounded-xl hover:bg-muted/50 transition-colors">
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${r.bg}`}>
                    <r.icon className={`w-3.5 h-3.5 ${r.color}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h5 className="text-[11px] font-bold text-foreground leading-tight">{r.title}</h5>
                    <p className="text-[10px] text-fg-tertiary leading-snug">{r.desc}</p>
                  </div>
                  <button className="shrink-0 text-[10px] font-bold text-primary border border-primary/20 px-2.5 py-1 rounded-lg hover:bg-primary/5 transition-colors">
                    {r.action}
                  </button>
                </div>
              ))
            )}
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}
