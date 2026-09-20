import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import {
  Package, Sun, Truck, CheckCircle2, Clock, Search, Filter,
  AlertTriangle, ChevronDown, ChevronRight, Download, RefreshCw,
  Layers, BarChart3,
} from 'lucide-react';
import type { ModuleDeliveriesSummary, ModuleProject } from './types';
import { useChartTheme } from '../../lib/chartTheme';
import { FORECAST_MONTHS, exportModuleDeliveriesXLSX, moduleExportName } from './export';
import { InfoTip } from '../../components/ui/primitives/InfoTip';

/* ═══════════════════════════════════════════════════════════════════════════
   MODULE DELIVERIES & FORECAST
   CEO-grade view replicating the PDF tracker with live SAP/P6/TC data.
   ═══════════════════════════════════════════════════════════════════════════ */

const API = import.meta.env.VITE_API_BASE || '';

const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Column index where each logical section starts — drives the divider rules. */
const SECTION_EDGE = 'border-l border-border';

/** '07-Mar-27' -> '2027-03-07' for an <input type="date"> value */
function scodToInputValue(scod: string): string {
  const m = scod.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{2})$/);
  if (!m) return '';
  const monIdx = MONTH_ABBR.findIndex(a => a.toLowerCase() === m[2].toLowerCase());
  if (monIdx === -1) return '';
  return `20${m[3]}-${String(monIdx + 1).padStart(2, '0')}-${m[1].padStart(2, '0')}`;
}

function isApproachingOrOverdue(dateStr: string): boolean {
  if (!dateStr) return false;
  const matches = dateStr.match(/\d{2}-[a-zA-Z]{3}-\d{2}/g);
  if (!matches) return false;
  
  const now = new Date();
  for (const m of matches) {
    const parts = m.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{2})$/);
    if (!parts) continue;
    const monIdx = MONTH_ABBR.findIndex(a => a.toLowerCase() === parts[2].toLowerCase());
    const dt = new Date(2000 + parseInt(parts[3], 10), monIdx, parseInt(parts[1], 10));
    
    const diffDays = (dt.getTime() - now.getTime()) / (1000 * 3600 * 24);
    if (diffDays <= 14) {
      return true;
    }
  }
  return false;
}

const container = { hidden: { opacity: 0 }, show: { opacity: 1, transition: { staggerChildren: 0.04 } } };
const item = { hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0, transition: { duration: 0.25 } } };

const MW = (n: number) => n.toLocaleString('en-IN', { maximumFractionDigits: 1 });
const sum = <T,>(rows: T[], pick: (r: T) => number) => rows.reduce((s, r) => s + (pick(r) || 0), 0);

/* ── Status Badge ────────────────────────────────────────────────────────── */
function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { cls: string; label: string; icon: React.ReactNode }> = {
    delivered: { cls: 'status-pill-healthy', label: 'Delivered', icon: <CheckCircle2 className="w-3 h-3" /> },
    in_progress: { cls: 'status-pill-risk', label: 'In Progress', icon: <Truck className="w-3 h-3" /> },
    ordered: { cls: 'status-pill-done', label: 'Ordered', icon: <Clock className="w-3 h-3" /> },
    pending: { cls: 'status-pill', label: 'Pending', icon: <Clock className="w-3 h-3" /> },
  };
  const c = cfg[status] || cfg.pending;
  return <span className={`${c.cls} inline-flex items-center gap-1`}>{c.icon}{c.label}</span>;
}

/* ── Progress Ring ───────────────────────────────────────────────────────── */
function ProgressRing({ pct, size = 36, stroke = 3, color = 'var(--primary-600)' }: { pct: number; size?: number; stroke?: number; color?: string }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - Math.min(pct, 1));
  return (
    <svg width={size} height={size} className="shrink-0 -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border-subtle)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
        className="transition-all duration-700"
      />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central"
        className="fill-[var(--fg-primary)] text-[8px] font-bold rotate-90" style={{ transformOrigin: 'center' }}>
        {Math.round(pct * 100)}%
      </text>
    </svg>
  );
}

/* ── KPI Card ────────────────────────────────────────────────────────────── */
function KpiCard({ title, value, unit, sub, icon: Icon, tint, pct }: {
  title: string; value: number; unit: string; sub?: string;
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>; tint: string; pct?: number;
}) {
  return (
    <motion.div variants={item}
      className="kpi-card group flex flex-col rounded-xl border border-border bg-card p-3 transition-all hover:-translate-y-0.5"
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: tint }} />
        <span className="section-label truncate text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</span>
      </div>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-light tabular-nums text-foreground leading-none">{MW(value)}</p>
          <p className="mt-0.5 text-[10px] text-muted-foreground">{unit}</p>
          {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
        </div>
        {pct !== undefined && <ProgressRing pct={pct} color={tint} />}
      </div>
    </motion.div>
  );
}

/* ── Table chrome, matching the printed tracker ───────────────────────────
   The header is a solid inverted band with stacked unit labels, and every
   cell carries a hairline grid, exactly as the PDF reads. The neutral scale
   flips between themes, so neutral-900 on neutral-50 stays a strong band in
   both light and dark rather than hardcoding black. */
const GRID_LINE = 'border-b border-r border-[var(--border-subtle)]';

/** Header label with its unit stacked underneath, as the tracker prints it. */
function ThLabel({ label, unit }: { label: string; unit?: string }) {
  return (
    <>
      {label}
      {unit && <><br /><span className="font-semibold opacity-80">{unit}</span></>}
    </>
  );
}

function Th({ children, className = '', stickyLeft, rowSpan, colSpan, title }: {
  children: React.ReactNode; className?: string; stickyLeft?: number; rowSpan?: number; colSpan?: number; title?: string;
}) {
  return (
    <th
      rowSpan={rowSpan} colSpan={colSpan} title={title}
      style={stickyLeft !== undefined ? { left: stickyLeft } : undefined}
      className={`px-1.5 py-1.5 align-middle text-center text-[9px] font-bold leading-[1.2] tracking-tight border-b border-r border-[var(--neutral-700)] bg-[var(--neutral-900)] text-[var(--neutral-50)] ${stickyLeft !== undefined ? 'sticky z-30' : ''} ${className}`}
    >
      {children}
    </th>
  );
}

/** Centre is the default — the tracker centres every short code, date and
    flag, and only the name and remarks columns run left. */
function Td({ children, className = '', stickyLeft, align = 'center', title, colSpan }: {
  children?: React.ReactNode; className?: string; stickyLeft?: number; align?: 'left' | 'center' | 'right'; title?: string; colSpan?: number;
}) {
  const alignCls = align === 'right' ? 'text-right' : align === 'left' ? 'text-left' : 'text-center';
  return (
    <td
      title={title} colSpan={colSpan}
      style={stickyLeft !== undefined ? { left: stickyLeft } : undefined}
      className={`px-1.5 py-[3px] text-[10px] leading-[1.35] tabular-nums whitespace-nowrap ${GRID_LINE} ${alignCls} ${stickyLeft !== undefined ? 'sticky z-20' : ''} ${className}`}
    >
      {children}
    </td>
  );
}

/* ── MW Cell with conditional coloring ───────────────────────────────────── */
function MwCell({ value, cap, className = '' }: { value: number; cap: number; className?: string }) {
  const pct = cap > 0 ? value / cap : 0;
  const color = value === 0 ? 'text-muted-foreground' : pct >= 0.95 ? 'text-emerald-600 dark:text-emerald-400 font-medium' : pct >= 0.5 ? 'text-foreground' : 'text-amber-600 dark:text-amber-400';
  return <Td align="right" className={`${color} ${className}`}>{value > 0 ? MW(value) : '-'}</Td>;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN PAGE COMPONENT
   ═══════════════════════════════════════════════════════════════════════════ */

export default function ModuleDeliveriesPage() {
  const [data, setData] = useState<ModuleDeliveriesSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [groupBy, setGroupBy] = useState<'epc' | 'category' | 'type' | 'none'>('epc');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [editingScodId, setEditingScodId] = useState<number | null>(null);
  const [savingScodId, setSavingScodId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  // The printed tracker covers Khavda projects not yet commissioned (33 rows).
  // Default to that so the figures reconcile with it; 'all' reveals the wider
  // portfolio (Rajasthan, commissioned, and Khavda projects the PDF omits).
  const [scope, setScope] = useState<'tracker' | 'all'>('tracker');
  const chartTheme = useChartTheme();

  const loadData = React.useCallback(() => {
    setLoading(true);
    return fetch(`${API}/akasha/api/module-deliveries/summary`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const saveScod = async (id: number, isoDateOrNull: string | null) => {
    setSavingScodId(id);
    try {
      await fetch(`${API}/akasha/api/mappings/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manual_scod: isoDateOrNull }),
      });
      await loadData();
    } finally {
      setSavingScodId(null);
      setEditingScodId(null);
    }
  };

  // Filtered projects
  const filtered = useMemo(() => {
    if (!data) return [];
    return data.projects.filter(p => {
      if (scope === 'tracker' && (p.cluster !== 'Solar Khavda' || p.is_commissioned)) return false;
      if (statusFilter !== 'all') {
        if (statusFilter === 'needs_ordering') {
          if (p.balance_ordering_mwp <= 0 || !isApproachingOrOverdue(p.module_date)) return false;
        } else if (p.status !== statusFilter) {
          return false;
        }
      }
      if (search) {
        const q = search.toLowerCase();
        return (
          p.project_name.toLowerCase().includes(q) ||
          p.spv.toLowerCase().includes(q) ||
          p.plot.toLowerCase().includes(q) ||
          p.epc.toLowerCase().includes(q) ||
          p.p6_name.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [data, search, statusFilter, scope]);

  const needsOrderingProjects = useMemo(() => {
    if (!data) return [];
    return data.projects.filter(p => p.balance_ordering_mwp > 0 && isApproachingOrOverdue(p.module_date));
  }, [data]);

  // Totals are summed from the rows actually on screen. Using the server's
  // all-projects totals under a filtered table would put a 49-project figure
  // above 33 rows — a number that looks right and is not.
  const totals = useMemo(() => ({
    total_mwac: sum(filtered, p => p.capacity_mwac),
    total_mwp: sum(filtered, p => p.capacity_mwp),
    ordered_mwp: sum(filtered, p => p.ordered_mwp),
    balance_ordering_mwp: sum(filtered, p => p.balance_ordering_mwp),
    received_mwp: sum(filtered, p => p.total_receipt_mwp),
    erection_mwp: sum(filtered, p => p.erection_done_mwp),
    inventory_mwp: sum(filtered, p => p.module_inventory_mwp),
    under_transit_mwp: sum(filtered, p => p.under_transit_mwp),
    balance_dispatch_mwp: sum(filtered, p => p.balance_dispatch_mwp),
  }), [filtered]);

  // Grouped projects
  const grouped = useMemo(() => {
    if (groupBy === 'none') return { 'All Projects': filtered };
    const groups: Record<string, ModuleProject[]> = {};
    filtered.forEach(p => {
      const key = groupBy === 'epc' ? (p.epc || 'AGEL (Direct)')
        : groupBy === 'category' ? (p.category || 'Unknown')
          : (p.type || 'Unknown');
      (groups[key] = groups[key] || []).push(p);
    });
    return groups;
  }, [filtered, groupBy]);

  const toggleGroup = (g: string) => {
    setCollapsed(prev => {
      const next = new Set(prev);
      next.has(g) ? next.delete(g) : next.add(g);
      return next;
    });
  };

  // Exports exactly what is on screen — current search, status filter and grouping.
  const handleExport = async () => {
    if (!data) return;
    setExporting(true);
    try {
      await exportModuleDeliveriesXLSX(grouped, data.totals, data, moduleExportName('xlsx'));
    } finally {
      setExporting(false);
    }
  };

  // Pipeline chart — reads the same filtered totals as the KPIs and the table
  const pipelineChart = useMemo(() => {
    if (!data) return {};
    const t = totals;
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${MW(v)} MWp` },
      grid: { left: 20, right: 20, top: 30, bottom: 30, containLabel: true },
      xAxis: {
        type: 'category',
        data: ['Total\nCapacity', 'Ordered', 'Received', 'Erected', 'Inventory', 'In Transit', 'Balance\nOrdering'],
        axisLabel: { fontSize: 10, color: chartTheme.chrome.fgTertiary },
        axisLine: { show: false }, axisTick: { show: false },
      },
      yAxis: {
        type: 'value', name: 'MWp',
        nameTextStyle: { fontSize: 10, color: chartTheme.chrome.fgTertiary },
        axisLabel: { fontSize: 10, color: chartTheme.chrome.fgTertiary },
        splitLine: { lineStyle: { color: chartTheme.chrome.gridLine, type: 'dashed' } },
      },
      series: [{
        type: 'bar', barMaxWidth: 48,
        // One measure across pipeline stages — one colour. The trailing bar is a
        // shortfall, which is a state, so it takes the reserved status colour.
        data: [t.total_mwp, t.ordered_mwp, t.received_mwp, t.erection_mwp, t.inventory_mwp, t.under_transit_mwp, t.balance_ordering_mwp]
          .map((value, i) => ({
            value,
            itemStyle: {
              color: i === 6 ? chartTheme.status.critical : chartTheme.categorical[0],
              borderRadius: [3, 3, 0, 0],
            },
          })),
        label: { show: true, position: 'top', fontSize: 10, fontWeight: 600, color: chartTheme.chrome.fgSecondary, formatter: (p: any) => MW(p.value) },
      }],
      animationDuration: 600,
    };
  }, [data, chartTheme, totals]);

  // Type breakdown chart (horizontal stacked bar).
  // Source type is categorical, so it takes the categorical ramp — status
  // colours are reserved for state and must never encode a series here.
  const typeChart = useMemo(() => {
    if (!data || !data.type_breakdowns) return {};
    const types = Object.keys(data.type_breakdowns);
    const colors: Record<string, string> = Object.fromEntries(
      types.map((t, i) => [t, t === 'Unknown' ? chartTheme.status.neutral : chartTheme.categorical[i % chartTheme.categorical.length]])
    );
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${MW(v)} MWp` },
      grid: { left: 10, right: 20, top: 30, bottom: 10, containLabel: true },
      xAxis: { type: 'value', axisLabel: { fontSize: 10, color: chartTheme.chrome.fgTertiary }, splitLine: { lineStyle: { color: chartTheme.chrome.gridLine, type: 'dashed' } } },
      yAxis: { type: 'category', data: ['Capacity', 'Ordered', 'Received'], axisLabel: { fontSize: 10, color: chartTheme.chrome.fgTertiary } },
      legend: { top: 0, textStyle: { fontSize: 10, color: chartTheme.chrome.fgSecondary } },
      series: types.map(t => ({
        name: t, type: 'bar', stack: 'total', barMaxWidth: 30,
        itemStyle: { color: colors[t], borderRadius: [0, 2, 2, 0] },
        data: [
          data.type_breakdowns[t].mwp,
          data.type_breakdowns[t].ordered,
          data.type_breakdowns[t].received,
        ],
      })),
      animationDuration: 600,
    };
  }, [data, chartTheme]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px] gap-3">
        <RefreshCw className="w-5 h-5 animate-spin text-primary" />
        <span className="text-muted-foreground text-sm">Loading module deliveries data...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center min-h-[400px] gap-3 text-destructive">
        <AlertTriangle className="w-5 h-5" />
        <span className="text-sm">{error || 'Failed to load data'}</span>
      </div>
    );
  }

  const t = totals;
  const pct = (a: number, b: number) => (b > 0 ? Math.round((a / b) * 100) : 0);
  const orderedPct = pct(t.ordered_mwp, t.total_mwp);
  const receivedPct = pct(t.received_mwp, t.ordered_mwp);

  return (
    <div className="flex w-full flex-col gap-5 animate-in fade-in duration-500 pb-10">

      {/* ── HEADER ────────────────────────────────────────────────────────── */}
      <motion.div variants={item} initial="hidden" animate="show" className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="rounded-lg border border-border bg-[var(--surface-sunken)] p-1.5">
              <Package className="w-4 h-4 text-primary" />
            </div>
            <h1 className="text-xl font-semibold text-foreground tracking-tight">Module Deliveries &amp; Forecast</h1>
          </div>
          <p className="text-xs text-muted-foreground">
            Khavda FY 26-27 Solar Projects · Live data from SAP, P6 &amp; Transmission · Updated {new Date(data.generated_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {data.data_coverage.with_sap_data}/{data.data_coverage.total_projects} with SAP data
          </span>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-primary disabled:opacity-60"
          >
            {exporting
              ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Preparing…</>
              : <><Download className="w-3.5 h-3.5" /> Export</>}
          </button>
        </div>
      </motion.div>

      {/* ── KPI CARDS ─────────────────────────────────────────────────────── */}
      <motion.div variants={container} initial="hidden" animate="show"
        className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3"
      >
        <KpiCard title="Total Capacity" value={t.total_mwp} unit="MWp" icon={Sun} tint="var(--primary-500)" />
        <KpiCard title="Ordered" value={t.ordered_mwp} unit="MWp" icon={Package} tint="var(--secondary-500)"
          pct={t.total_mwp > 0 ? t.ordered_mwp / t.total_mwp : 0}
          sub={`${orderedPct}% of capacity`} />
        <KpiCard title="Received" value={t.received_mwp} unit="MWp" icon={CheckCircle2} tint="#10b981"
          pct={t.ordered_mwp > 0 ? t.received_mwp / t.ordered_mwp : 0}
          sub={`${receivedPct}% of ordered`} />
        <KpiCard title="Erected" value={t.erection_mwp} unit="MWp" icon={Layers} tint="#3b82f6"
          pct={t.received_mwp > 0 ? t.erection_mwp / t.received_mwp : 0} />
        <KpiCard title="Inventory" value={t.inventory_mwp} unit="MWp" icon={BarChart3} tint="#f59e0b" />
        <KpiCard title="In Transit" value={t.under_transit_mwp} unit="MWp" icon={Truck} tint="#8b5cf6" />
        <KpiCard title="Balance to Order" value={t.balance_ordering_mwp} unit="MWp" icon={AlertTriangle}
          tint={t.balance_ordering_mwp > 0 ? '#ef4444' : '#10b981'} />
      </motion.div>

      {/* ── PIPELINE CHART + TYPE BREAKDOWN ───────────────────────────────── */}
      <motion.div variants={item} initial="hidden" animate="show" className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="bento-card lg:col-span-3 p-4">
          <div className="flex items-baseline justify-between gap-2 mb-3">
            <h2 className="text-sm font-semibold text-foreground">Module Pipeline</h2>
            <span className="section-label">MWp by stage</span>
          </div>
          <div className="h-[220px]">
            <ReactECharts notMerge theme={chartTheme.themeName} option={pipelineChart} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
        <div className="bento-card lg:col-span-2 p-4">
          <div className="flex items-baseline justify-between gap-2 mb-3">
            <h2 className="text-sm font-semibold text-foreground">Source Type Breakdown</h2>
            <span className="section-label">MWp</span>
          </div>
          <div className="h-[220px]">
            <ReactECharts notMerge theme={chartTheme.themeName} option={typeChart} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
      </motion.div>

      {/* ── Notification Banner ────────────────────────────────────────────────── */}
      {needsOrderingProjects.length > 0 && (
        <motion.div variants={item} className="flex items-center justify-between gap-4 rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-600 dark:text-amber-400">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 shrink-0" />
            <div>
              <p className="font-semibold">Module Ordering Action Required</p>
              <p className="opacity-90 text-[13px]">{needsOrderingProjects.length} project(s) have Module Dates approaching within 14 days or are already overdue, and still require module procurement (Balance Ordering &gt; 0).</p>
            </div>
          </div>
          {statusFilter !== 'needs_ordering' && (
            <button
              onClick={() => setStatusFilter('needs_ordering')}
              className="shrink-0 rounded-md bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900 transition-colors"
            >
              Review Projects
            </button>
          )}
        </motion.div>
      )}

      {/* ── TOOLBAR ───────────────────────────────────────────────────────── */}
      <motion.div variants={item} initial="hidden" animate="show" className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="text" placeholder="Search project, SPV, plot..."
            value={search} onChange={e => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-[11px] rounded-lg border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="flex items-center gap-1 text-[10px]">
          <Filter className="w-3 h-3 text-muted-foreground" />
          <span className="section-label mr-0.5">Group</span>
          <div className="inline-flex overflow-hidden rounded-md border border-border">
            {(['epc', 'category', 'type', 'none'] as const).map(g => (
              <button key={g} onClick={() => setGroupBy(g)}
                aria-pressed={groupBy === g}
                className={`px-2 py-1 transition-colors ${groupBy === g ? 'bg-primary text-white' : 'bg-card text-muted-foreground hover:bg-muted hover:text-foreground'}`}>
                {g === 'none' ? 'None' : g.charAt(0).toUpperCase() + g.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1 text-[10px]">
          <span className="section-label mr-0.5">Status</span>
          <div className="inline-flex overflow-hidden rounded-md border border-border">
            {['all', 'delivered', 'in_progress', 'ordered', 'pending', 'needs_ordering'].map(s => (
              <button key={s} onClick={() => setStatusFilter(s)}
                aria-pressed={statusFilter === s}
                className={`px-2 py-1 transition-colors ${statusFilter === s ? 'bg-primary text-white' : 'bg-card text-muted-foreground hover:bg-muted hover:text-foreground'}`}>
                {s === 'all' ? 'All' : s === 'needs_ordering' ? 'Needs Ordering' : s.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1 text-[10px]">
          <span className="section-label mr-0.5">Scope</span>
          <div className="inline-flex overflow-hidden rounded-md border border-border">
            {([
              ['tracker', 'Khavda tracker', 'Khavda projects not yet commissioned — the scope of the printed tracker'],
              ['all', 'All projects', 'Everything mapped: also Rajasthan, commissioned projects, and Khavda projects the printed tracker omits'],
            ] as const).map(([v, label, tip]) => (
              <button key={v} onClick={() => setScope(v)} aria-pressed={scope === v} title={tip}
                className={`px-2 py-1 transition-colors ${scope === v ? 'bg-primary text-white' : 'bg-card text-muted-foreground hover:bg-muted hover:text-foreground'}`}>
                {label}
              </button>
            ))}
          </div>
        </div>
        <span className="ml-auto text-[10px] tabular-nums text-muted-foreground">{filtered.length} of {data.projects.length} projects</span>
      </motion.div>

      {/* ── MAIN DATA TABLE ───────────────────────────────────────────────── */}
      <motion.div variants={item} initial="hidden" animate="show" className="bento-card overflow-hidden">
        <div className="max-h-[72vh] overflow-auto custom-scrollbar">
          {/* min-w-full, not w-full: with 40 columns the natural content width
              always exceeds the container. w-full would force the browser's
              auto layout to shrink every column below its declared width to
              fit, which desyncs the frozen Sr/Project columns' hardcoded
              sticky `left` offsets from their real rendered width and makes
              adjacent column text visually overlap. min-w-full lets the table
              grow past the container (the wrapper already scrolls) while
              still filling it when there's little content. */}
          <table className="min-w-full text-left border-separate border-spacing-0">
            <thead className="sticky top-0 z-40">
              <tr>
                <Th stickyLeft={0} rowSpan={2} className="w-[34px] min-w-[34px]">Sr</Th>
                <Th stickyLeft={34} rowSpan={2} className="min-w-[188px] text-left">Project</Th>
                <Th rowSpan={2} className="min-w-[178px] text-left">P6 Name</Th>
                <Th rowSpan={2} className="min-w-[62px]">SPV</Th>
                <Th rowSpan={2} className="min-w-[46px]">Plot</Th>
                <Th rowSpan={2} className="min-w-[62px]">Category</Th>
                <Th rowSpan={2} className="min-w-[52px]">Type</Th>
                <Th rowSpan={2} className="min-w-[46px]"><ThLabel label="MMS" unit="Type" /></Th>
                <Th rowSpan={2} className="min-w-[124px] text-left">AGEL / EPC</Th>
                <Th rowSpan={2} className={`min-w-[38px] ${SECTION_EDGE}`}>OL</Th>
                <Th rowSpan={2} className="min-w-[58px]"><ThLabel label="Capacity" unit="(MWac)" /></Th>
                <Th rowSpan={2} className="min-w-[58px]"><ThLabel label="Capacity" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="FTC Completed" unit="(MWp)" /></Th>
                <Th rowSpan={2} className={`min-w-[74px] ${SECTION_EDGE}`}><ThLabel label="Connectivity" unit="Phase" /></Th>
                <Th rowSpan={2} className="min-w-[62px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    LTA
                    <InfoTip info="Long Term Access date (pulled from ECOD in master sheets)" align="center" />
                  </div>
                </Th>
                <Th rowSpan={2} className="min-w-[80px]">SCOD</Th>
                <Th rowSpan={2} className="min-w-[66px]"><ThLabel label="AOP" unit="(Plan)" /></Th>
                <Th rowSpan={2} className="min-w-[76px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="FTC" unit="Date" />
                    <InfoTip info="First Time Charging. Base date mapped for the project." align="center" />
                  </div>
                </Th>
                <Th rowSpan={2} className="min-w-[76px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="TC" unit="Date" />
                    <InfoTip info={<span>Trial Commissioning.<br/><b>Calculation:</b> FTC Date - 45 days.</span>} align="center" />
                  </div>
                </Th>
                <Th rowSpan={2} className="min-w-[76px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="Module" unit="Date" />
                    <InfoTip info={<span>Target delivery date at site.<br/><b>Calculation:</b> TC Date - Lead Time (98 or 136 days based on origin).</span>} align="center" />
                  </div>
                </Th>
                <Th rowSpan={2} className={`min-w-[64px] ${SECTION_EDGE}`}><ThLabel label="Ordered" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Balance Ordering" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Total Receipt" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Erection done" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Module Inventory" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Under Transit" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Balance Dispatch" unit="(MWp)" /></Th>
                <Th rowSpan={2} className={`min-w-[78px] ${SECTION_EDGE}`}>Status</Th>
                <Th colSpan={FORECAST_MONTHS.length + 1} className={SECTION_EDGE} title="From the CEO PDF tracker's manual monthly plan — no live data source yet, so these are intentionally blank">
                  Month wise Module Requirement at Site (MWp)
                </Th>
                <Th rowSpan={2} className={`min-w-[210px] text-left ${SECTION_EDGE}`}>Remarks</Th>
              </tr>
              <tr>
                {FORECAST_MONTHS.map((mo, i) => (
                  <Th key={mo} className={`min-w-[48px] font-semibold ${i === 0 ? SECTION_EDGE : ''}`}>{mo}</Th>
                ))}
                <Th className="min-w-[52px]">Total</Th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(grouped).map(([group, projects]) => (
                <React.Fragment key={group}>
                  {/* Group Header */}
                  {groupBy !== 'none' && (
                    <tr className="cursor-pointer" onClick={() => toggleGroup(group)}>
                      <td colSpan={40} className="border-y border-[var(--border-default)] bg-[var(--neutral-200)] px-1.5 py-1">
                        <div className="sticky left-2 flex w-fit items-center gap-1.5">
                          {collapsed.has(group)
                            ? <ChevronRight className="h-3 w-3 text-muted-foreground" />
                            : <ChevronDown className="h-3 w-3 text-muted-foreground" />
                          }
                          <span className="text-[10px] font-bold uppercase tracking-wide text-foreground">{group}</span>
                          <span className="text-[10px] tabular-nums text-muted-foreground">
                            {projects.length} project{projects.length !== 1 ? 's' : ''} · {MW(projects.reduce((s, p) => s + p.capacity_mwp, 0))} MWp
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                  {/* Rows. The frozen Sr/Project cells hover to a SOLID colour,
                      never a translucent one — they sit above the scrolling
                      columns, so any alpha lets that content bleed through. */}
                  {!collapsed.has(group) && projects.map((p, idx) => (
                    <tr key={p.id} className="group hover:bg-[var(--surface-sunken)]">
                      <Td stickyLeft={0} className="bg-card group-hover:bg-[var(--surface-sunken)] text-muted-foreground font-mono">{idx + 1}</Td>
                      <Td stickyLeft={34} align="left" className="bg-card group-hover:bg-[var(--surface-sunken)] font-medium text-foreground shadow-[1px_0_0_0_var(--border-default)]">{p.project_name || p.p6_name}</Td>
                      <Td align="left" className="text-muted-foreground">{p.p6_name || '-'}</Td>
                      <Td className="font-mono">{p.spv}</Td>
                      <Td className="font-mono">{p.plot}</Td>
                      <Td>{p.category || '-'}</Td>
                      <Td>{p.type}</Td>
                      <Td className="font-mono">{p.mms_type || '-'}</Td>
                      <Td align="left" className="font-medium">{p.epc || '-'}</Td>
                      <Td align="right" className={SECTION_EDGE}>{p.ol > 0 ? p.ol.toFixed(2) : '-'}</Td>
                      <Td align="right">{MW(p.capacity_mwac)}</Td>
                      <Td align="right" className="font-semibold text-foreground">{MW(p.capacity_mwp)}</Td>
                      <Td align="right" className="font-semibold text-[var(--status-watch-fg)]">{p.completed_ftc_mwp > 0 ? MW(p.completed_ftc_mwp) : '-'}</Td>
                      <Td className={SECTION_EDGE}>{p.connectivity_phase || <span className="text-muted-foreground/50">-</span>}</Td>
                      <Td>{p.lta || '-'}</Td>
                      <td className={`px-1.5 py-[3px] text-center text-[10px] leading-[1.35] whitespace-nowrap ${GRID_LINE}`}>
                        {editingScodId === p.id ? (
                          <input
                            type="date"
                            autoFocus
                            defaultValue={scodToInputValue(p.scod)}
                            disabled={savingScodId === p.id}
                            className="w-[112px] rounded border border-border bg-background px-1 py-0 text-[10px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
                            onBlur={e => {
                              const v = e.target.value;
                              if (v === scodToInputValue(p.scod)) { setEditingScodId(null); return; }
                              saveScod(p.id, v || null);
                            }}
                            onKeyDown={e => {
                              if (e.key === 'Escape') setEditingScodId(null);
                              if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                            }}
                          />
                        ) : savingScodId === p.id ? (
                          <RefreshCw className="w-3 h-3 animate-spin text-muted-foreground" />
                        ) : (
                          <button
                            type="button"
                            onClick={() => setEditingScodId(p.id)}
                            className={`inline-flex items-center gap-1 rounded px-1 -mx-1 py-px text-[10px] decoration-dotted underline-offset-2 hover:bg-primary/5 hover:text-primary hover:underline focus:outline-none focus-visible:ring-1 focus-visible:ring-primary ${p.scod_lta_diff_days != null ? 'text-amber-500 font-semibold' : 'text-foreground'}`}
                            title={`${p.scod_source === 'manual' ? 'Manually entered' : `Derived from ${p.scod_source ?? 'no source'}`} ${p.scod_lta_diff_days != null ? `\n(LTA ${p.scod_lta_diff_days >= 0 ? '+' : ''}${p.scod_lta_diff_days} days)` : ''} — click to override`}
                          >
                            <span>{p.scod || '-'}</span>
                            {p.scod_source === 'manual' && <span className="h-1 w-1 shrink-0 rounded-full bg-primary" title="Manually entered" />}
                          </button>
                        )}
                      </td>
                      <Td>{p.aop_plan || '-'}</Td>
                      <Td>{p.ftc_date || '-'}</Td>
                      <Td>{p.tc_date || '-'}</Td>
                      <Td>{p.module_date || '-'}</Td>
                      {/* An apportioned figure is derived, not measured — mark it. */}
                      <Td align="right" className={`${SECTION_EDGE} ${p.ordered_mwp === 0 ? 'text-muted-foreground' : ''}`}
                        title={p.po_apportioned ? `Apportioned: ${p.po_share_pct}% of a PO on WBS ${p.p6_name ? '' : ''}shared with other projects` : undefined}>
                        {p.ordered_mwp > 0 ? MW(p.ordered_mwp) : '-'}
                        {p.po_apportioned && <span className="ml-0.5 text-[8px] align-super text-[var(--status-watch-fg)]">~</span>}
                      </Td>
                      <Td align="right" className={p.balance_ordering_mwp > 0 ? 'text-[var(--status-critical-fg)]' : 'text-muted-foreground'}>
                        {p.balance_ordering_mwp > 0 ? MW(p.balance_ordering_mwp) : '-'}
                      </Td>
                      <MwCell value={p.total_receipt_mwp} cap={p.ordered_mwp} />
                      <Td align="right" className="text-muted-foreground/50" title="No source — needs MB51 movement types">-</Td>
                      <Td align="right">{p.module_inventory_mwp > 0 ? MW(p.module_inventory_mwp) : '-'}</Td>
                      <Td align="right">{p.under_transit_mwp > 0 ? MW(p.under_transit_mwp) : '-'}</Td>
                      <Td align="right" className={p.balance_dispatch_mwp > 0 ? 'text-[var(--status-risk-fg)]' : 'text-muted-foreground'}>
                        {p.balance_dispatch_mwp > 0 ? MW(p.balance_dispatch_mwp) : '-'}
                      </Td>
                      <Td className={SECTION_EDGE}><StatusBadge status={p.status} /></Td>
                      {FORECAST_MONTHS.map((mo, i) => (
                        <Td key={mo} align="right" className={`text-muted-foreground/40 ${i === 0 ? SECTION_EDGE : ''}`}>-</Td>
                      ))}
                      <Td align="right" className="text-muted-foreground/40">-</Td>
                      <Td align="left" className={`max-w-[240px] truncate text-muted-foreground ${SECTION_EDGE}`} title={p.remarks || undefined}>{p.remarks || '-'}</Td>
                    </tr>
                  ))}
                </React.Fragment>
              ))}

              {/* ── TOTALS ROW ──────────────────────────────────────────────── */}
              <tr className="border-t-2 border-[var(--neutral-700)] bg-[var(--neutral-200)] font-bold">
                {/* One cell per visible column — no colSpan arithmetic to drift
                    out of step when the view changes. */}
                <Td stickyLeft={0} className="bg-[var(--neutral-200)] text-muted-foreground">Σ</Td>
                <Td stickyLeft={34} align="left" className="bg-[var(--neutral-200)] text-foreground shadow-[1px_0_0_0_var(--border-default)]">Total ({filtered.length} projects)</Td>
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td className={SECTION_EDGE} />
                <Td align="right" className={`text-foreground tabular-nums `}>{MW(t.total_mwac)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.total_mwp)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.completed_ftc_mwp)}</Td>
                <Td className={SECTION_EDGE} />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td align="right" className={`text-foreground tabular-nums ${SECTION_EDGE}`}>{MW(t.ordered_mwp)}</Td>
                <Td align="right" className="text-[var(--status-critical-fg)] tabular-nums">{MW(t.balance_ordering_mwp)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.received_mwp)}</Td>
                <Td align="right" className="tabular-nums text-muted-foreground/50">—</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.inventory_mwp)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.under_transit_mwp)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.balance_dispatch_mwp)}</Td>
                <Td className={SECTION_EDGE} />
                {FORECAST_MONTHS.map(mo => <Td key={mo} />)}
                <Td />
                <Td className={SECTION_EDGE} />
              </tr>
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  );
}
