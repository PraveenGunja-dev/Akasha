import React, { useState, useEffect, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  Shield, AlertTriangle, CheckCircle2, Clock, Users, DollarSign,
  RefreshCw, ChevronDown, ChevronRight, XCircle, Activity,
  TrendingUp, Package, MapPin, Filter, Search, ArrowUpRight,
  ClipboardCheck, RotateCcw
} from 'lucide-react';

/* ── Status config ── */
const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  raised: { label: 'Raised', color: 'text-destructive', bg: 'bg-destructive/10', border: 'border-destructive/20' },
  submitted: { label: 'In Review (EE)', color: 'text-amber-500', bg: 'bg-amber-500/10', border: 'border-amber-500/20' },
  approved: { label: 'In Review (QI)', color: 'text-blue-500', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
  completed: { label: 'Approved', color: 'text-success', bg: 'bg-success/10', border: 'border-success/20' },
  rejected: { label: 'Rejected', color: 'text-orange-500', bg: 'bg-orange-500/10', border: 'border-orange-500/20' },
};

const HANDLER_CONFIG: Record<string, { label: string; color: string }> = {
  contractor: { label: 'Contractor', color: 'text-destructive' },
  execution_engineer: { label: 'Execution Engineer', color: 'text-amber-500' },
  quality_inspector: { label: 'Quality Inspector', color: 'text-blue-500' },
};

/* ── KPI Card ── */
const KPI = ({ label, value, sub, icon: Icon, color, alert }: any) => (
  <div className={`bg-card border rounded-2xl p-5 flex flex-col gap-2 group hover:shadow-card-hover transition-all relative overflow-hidden ${alert ? 'border-destructive/30' : 'border-border'}`}>
    <div className="flex items-center justify-between">
      <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-muted-foreground">{label}</span>
      <div className={`p-1.5 rounded-lg ${alert ? 'bg-destructive/10' : 'bg-muted'}`}>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
    </div>
    <div className={`text-2xl md:text-3xl font-light tracking-tight ${color}`}>{value}</div>
    {sub && <div className="text-[10px] font-semibold text-muted-foreground/70">{sub}</div>}
    {alert && <div className="absolute top-0 right-0 w-2 h-2 rounded-full bg-destructive animate-pulse m-2"></div>}
  </div>
);

/* ── Workflow Stage ── */
const WorkflowStage = ({ label, count, total, color, isLast }: any) => {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex-1 flex flex-col items-center gap-2 relative">
      <div className={`text-[10px] font-bold uppercase tracking-widest ${color}`}>{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{count}</div>
      <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700`}
          style={{ width: `${pct}%`, backgroundColor: color.includes('destructive') ? '#ef4444' : color.includes('amber') ? '#f59e0b' : color.includes('blue') ? '#3b82f6' : color.includes('success') ? '#22c55e' : color.includes('orange') ? '#f97316' : '#6b7280' }} />
      </div>
      {!isLast && <ChevronRight className="absolute -right-3 top-6 w-4 h-4 text-muted-foreground/30" />}
    </div>
  );
};

export default function QualityCommandCenter() {
  const [overview, setOverview] = useState<any>(null);
  const [contractors, setContractors] = useState<any[]>([]);
  const [ncList, setNcList] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [activeFilter, setActiveFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const loadData = async () => {
    setLoading(true);
    try {
      const [ovRes, conRes, ncRes] = await Promise.all([
        fetch('/akasha/api/quality/overview'),
        fetch('/akasha/api/quality/contractors'),
        fetch('/akasha/api/quality/ncs?page_size=100'),
      ]);
      setOverview(await ovRes.json());
      setContractors(await conRes.json());
      const ncData = await ncRes.json();
      setNcList(ncData.items || []);
    } catch (e) {
      console.error('Failed to load quality data:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      await fetch('/akasha/api/pulse/sync', { method: 'POST' });
      await loadData();
    } catch (e) {
      console.error('Pulse sync failed:', e);
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const ov = overview || {};
  const byStatus = ov.by_status || {};
  const rfiByStatus = ov.rfi_by_status || {};
  const rfiByHandler = ov.rfi_by_handler || {};
  const aging = ov.aging || {};
  const trend = ov.trend || [];
  const topDefects = ov.top_defects || [];

  /* ── Filtered NCs ── */
  const filteredNCs = useMemo(() => {
    let list = ncList;
    if (activeFilter !== 'all') list = list.filter(nc => nc.status === activeFilter);
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      list = list.filter(nc =>
        (nc.nc_label || '').toLowerCase().includes(q) ||
        (nc.project_name || '').toLowerCase().includes(q) ||
        (nc.defect_type || '').toLowerCase().includes(q) ||
        (nc.vendor_name || '').toLowerCase().includes(q)
      );
    }
    return list;
  }, [ncList, activeFilter, searchQuery]);

  const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
  const labelColor = isDark ? '#cbd5e1' : '#475569';
  const lineColor = isDark ? '#334155' : '#e2e8f0';

  /* ── ECharts: Aging ── */
  const agingOption = useMemo(() => ({
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.85)', textStyle: { color: '#fff', fontSize: 11, fontFamily: 'Adani' }, borderWidth: 0 },
    grid: { left: 0, right: 10, top: 10, bottom: 0, containLabel: true },
    xAxis: { type: 'category', data: ['0-3 days', '3-7 days', '7-14 days', '14-30 days', '30+ days'], axisLine: { lineStyle: { color: lineColor } }, axisLabel: { color: labelColor, fontSize: 10 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: lineColor, opacity: 0.5 } }, axisLabel: { color: labelColor, fontSize: 10 } },
    series: [{
      type: 'bar', barWidth: '60%', data: [
        { value: aging['0-3'] || 0, itemStyle: { color: '#22c55e', borderRadius: [4, 4, 0, 0] } },
        { value: aging['3-7'] || 0, itemStyle: { color: '#84cc16', borderRadius: [4, 4, 0, 0] } },
        { value: aging['7-14'] || 0, itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] } },
        { value: aging['14-30'] || 0, itemStyle: { color: '#f97316', borderRadius: [4, 4, 0, 0] } },
        { value: aging['30+'] || 0, itemStyle: { color: '#ef4444', borderRadius: [4, 4, 0, 0] } },
      ]
    }]
  }), [aging, labelColor, lineColor]);

  /* ── ECharts: Trend ── */
  const trendOption = useMemo(() => ({
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.85)', textStyle: { color: '#fff', fontSize: 11, fontFamily: 'Adani' }, borderWidth: 0 },
    grid: { left: 0, right: 10, top: 20, bottom: 0, containLabel: true },
    xAxis: { type: 'category', data: trend.map((t: any) => t.month), axisLine: { lineStyle: { color: lineColor } }, axisLabel: { color: labelColor, fontSize: 10 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: lineColor, opacity: 0.5 } }, axisLabel: { color: labelColor, fontSize: 10 } },
    series: [{
      name: 'NCs Created', type: 'line', smooth: true, symbol: 'circle', symbolSize: 8,
      data: trend.map((t: any) => t.count),
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(239,68,68,0.3)' }, { offset: 1, color: 'rgba(239,68,68,0.02)' }] } },
      lineStyle: { color: '#ef4444', width: 2 },
      itemStyle: { color: '#ef4444' }
    }]
  }), [trend, labelColor, lineColor]);

  /* ── ECharts: Defect Bar Chart ── */
  const defectBarOption = useMemo(() => {
    const items = [...topDefects].slice(0, 6).reverse(); // Reverse so largest is at the top
    return {
      textStyle: { fontFamily: 'Adani, sans-serif' },
      tooltip: { backgroundColor: 'rgba(0,0,0,0.85)', textStyle: { color: '#fff', fontSize: 11, fontFamily: 'Adani' }, borderWidth: 0, trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 0, right: 30, top: 10, bottom: 0, containLabel: true },
      xAxis: { type: 'value', splitLine: { show: false }, axisLabel: { show: false } },
      yAxis: { 
        type: 'category', 
        data: items.map((d: any) => d.type.length > 25 ? d.type.substring(0, 23) + '..' : d.type), 
        axisLine: { show: false }, 
        axisTick: { show: false },
        axisLabel: { color: labelColor, fontSize: 11, fontWeight: '500', fontFamily: 'Adani' }
      },
      series: [{
        name: 'Defects',
        type: 'bar',
        data: items.map((d: any) => d.count),
        itemStyle: { 
          color: {
            type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [{ offset: 0, color: '#f43f5e' }, { offset: 1, color: '#9f1239' }]
          },
          borderRadius: [0, 4, 4, 0] 
        },
        label: { show: true, position: 'right', color: labelColor, fontSize: 11, fontWeight: 'bold' },
        barMaxWidth: 20
      }]
    };
  }, [topDefects, labelColor]);

  /* ── ECharts: Package Donut ── */
  const packageOption = useMemo(() => {
    const byPkg = ov.by_package || {};
    const items = Object.entries(byPkg).sort((a: any, b: any) => b[1] - a[1]).slice(0, 5);
    const colors = ['#0B74B0', '#75479C', '#BD3861', '#f59e0b', '#22c55e'];
    return {
      textStyle: { fontFamily: 'Adani, sans-serif' },
      tooltip: { backgroundColor: 'rgba(0,0,0,0.85)', textStyle: { color: '#fff', fontSize: 11, fontFamily: 'Adani' }, borderWidth: 0 },
      series: [{
        type: 'pie', radius: ['55%', '80%'], center: ['50%', '50%'],
        label: { show: true, position: 'outside', color: labelColor, fontSize: 10, formatter: '{b}\n{c}', fontFamily: 'Adani' },
        labelLine: { lineStyle: { color: lineColor } },
        data: items.map(([name, count], i) => ({ name, value: count, itemStyle: { color: colors[i] } })),
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.2)' } }
      }]
    };
  }, [ov.by_package, labelColor, lineColor]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[500px]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 text-primary animate-spin" />
          <span className="text-sm text-muted-foreground">Loading Quality Data...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-10">

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Quality Command Center</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Non-Conformance & Inspection tracking from Pulse</p>
        </div>
        <button onClick={handleSync} disabled={syncing}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
          {syncing ? 'Syncing...' : 'Sync Pulse'}
        </button>
      </div>

      {/* ── KPI Row ── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KPI label="Total NCs" value={ov.total_ncs || 0} sub={`${ov.by_category?.['Critical'] || 0} Critical`} icon={Shield} color="text-foreground" />
        <KPI label="Open NCs" value={ov.open_ncs || 0} sub={`Pending action`} icon={AlertTriangle} color="text-destructive" alert={ov.open_ncs > 100} />
        <KPI label="Critical Open" value={ov.critical_open || 0} sub="Require immediate action" icon={XCircle} color="text-destructive" alert={ov.critical_open > 50} />
        <KPI label="Closure Rate" value={`${ov.closure_rate || 0}%`} sub={`${byStatus.completed || 0} closed`} icon={CheckCircle2} color={ov.closure_rate >= 70 ? 'text-success' : 'text-warning'} />
        <KPI label="Avg Resolution" value={ov.avg_resolution_days ? `${ov.avg_resolution_days}d` : '—'} sub="Days to close" icon={Clock} color={ov.avg_resolution_days <= 7 ? 'text-success' : 'text-warning'} />
        <KPI label="Penalties" value={ov.total_debit ? `₹${(ov.total_debit / 1000).toFixed(0)}K` : '₹0'} sub={`${ov.debit_count || 0} NCs debited`} icon={DollarSign} color="text-pink-500" />
      </div>

      {/* ── NC Workflow Pipeline ── */}
      <div className="bg-card border border-border rounded-2xl p-6">
        <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-5 flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" /> NC Workflow Pipeline
        </h3>
        <div className="flex gap-4">
          <WorkflowStage label="Raised" count={byStatus.raised || 0} total={ov.total_ncs} color="text-destructive" />
          <WorkflowStage label="In Review (EE)" count={byStatus.submitted || 0} total={ov.total_ncs} color="text-amber-500" />
          <WorkflowStage label="In Review (QI)" count={byStatus.approved || 0} total={ov.total_ncs} color="text-blue-500" />
          <WorkflowStage label="Approved" count={byStatus.completed || 0} total={ov.total_ncs} color="text-success" isLast />
        </div>
        {(byStatus.rejected || 0) > 0 && (
          <div className="mt-4 p-3 bg-orange-500/5 border border-orange-500/20 rounded-xl flex items-center gap-3">
            <XCircle className="w-4 h-4 text-orange-500 shrink-0" />
            <span className="text-sm"><strong className="text-orange-500">{byStatus.rejected}</strong> NCs rejected — sent back to contractor for re-work</span>
          </div>
        )}
      </div>

      {/* ── RFI Inspection Pipeline ── */}
      <div className="bg-card border border-border rounded-2xl p-6">
        <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-5 flex items-center gap-2">
          <ClipboardCheck className="w-4 h-4 text-primary" /> RFI Inspection Pipeline
          <span className="ml-auto normal-case tracking-normal text-xs font-semibold text-muted-foreground">
            {(ov.total_rfis || 0).toLocaleString()} inspections raised
          </span>
        </h3>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <KPI label="Pass Rate" value={`${ov.rfi_pass_rate || 0}%`} sub={`${(ov.rfis_completed || 0).toLocaleString()} passed`}
            icon={CheckCircle2} color={(ov.rfi_pass_rate || 0) >= 90 ? 'text-success' : 'text-warning'} />
          <KPI label="Rejected" value={(ov.rfis_rejected || 0).toLocaleString()} sub="Awaiting re-submission"
            icon={RotateCcw} color="text-orange-500" alert={(ov.rfis_rejected || 0) > 500} />
          <KPI label="In Flight" value={(ov.rfis_in_flight || 0).toLocaleString()} sub="Awaiting sign-off"
            icon={Clock} color="text-blue-500" />
          <KPI label="With Contractor" value={(rfiByHandler.contractor || 0).toLocaleString()} sub="Re-work outstanding"
            icon={Users} color="text-destructive" alert={(rfiByHandler.contractor || 0) > 500} />
        </div>

        <div className="flex gap-4">
          <WorkflowStage label="In Review (EE)" count={rfiByStatus.submitted || 0} total={ov.total_rfis} color="text-amber-500" />
          <WorkflowStage label="In Review (QI)" count={rfiByStatus.approved || 0} total={ov.total_rfis} color="text-blue-500" />
          <WorkflowStage label="Completed" count={rfiByStatus.completed || 0} total={ov.total_rfis} color="text-success" isLast />
        </div>

        {(ov.rfis_rejected || 0) > 0 && (
          <div className="mt-4 p-3 bg-orange-500/5 border border-orange-500/20 rounded-xl flex items-center gap-3">
            <XCircle className="w-4 h-4 text-orange-500 shrink-0" />
            <span className="text-sm">
              <strong className="text-orange-500">{(ov.rfis_rejected || 0).toLocaleString()}</strong> inspections rejected — work sent back to the contractor and not yet re-submitted
            </span>
          </div>
        )}

        {Object.keys(rfiByHandler).length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mr-1">Open with</span>
            {Object.entries(rfiByHandler)
              .sort((a: any, b: any) => b[1] - a[1])
              .map(([handler, count]: any) => (
                <span key={handler} className="px-2.5 py-1 rounded-lg bg-muted text-xs font-semibold">
                  <span className={HANDLER_CONFIG[handler]?.color || 'text-muted-foreground'}>
                    {HANDLER_CONFIG[handler]?.label || handler}
                  </span>
                  <span className="text-muted-foreground ml-1.5">{count.toLocaleString()}</span>
                </span>
              ))}
          </div>
        )}
      </div>

      {/* ── Charts Row ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Aging Analysis */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-1 flex items-center gap-2">
            <Clock className="w-4 h-4 text-warning" /> NC Aging (Open NCs)
          </h3>
          <p className="text-[10px] text-muted-foreground/60 mb-3">How long NCs have been open without resolution</p>
          {(aging['30+'] || 0) > 50 && (
            <div className="mb-3 p-2.5 bg-destructive/5 border border-destructive/20 rounded-lg text-xs text-destructive font-medium flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5" /> {aging['30+']} NCs are 30+ days old — escalation needed
            </div>
          )}
          <ReactECharts option={agingOption} style={{ height: 200 }} />
        </div>

        {/* Defect Pattern Radar */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-1 flex items-center gap-2">
            <Shield className="w-4 h-4 text-pink-500" /> Defect Pattern Analysis
          </h3>
          <p className="text-[10px] text-muted-foreground/60 mb-3">Top defect types — clustered patterns indicate systemic issues</p>
          <ReactECharts option={defectBarOption} style={{ height: 200 }} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* NC Trend */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-1 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-destructive" /> NC Trend (Monthly)
          </h3>
          <p className="text-[10px] text-muted-foreground/60 mb-3">NC creation rate over time — are interventions working?</p>
          <ReactECharts option={trendOption} style={{ height: 200 }} />
        </div>

        {/* Package Breakdown */}
        <div className="bg-card border border-border rounded-2xl p-6">
          <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-1 flex items-center gap-2">
            <Package className="w-4 h-4 text-primary" /> NCs by Package
          </h3>
          <p className="text-[10px] text-muted-foreground/60 mb-3">Which work packages have the most quality issues</p>
          <ReactECharts option={packageOption} style={{ height: 200 }} />
        </div>
      </div>

      {/* ── Contractor Scorecard ── */}
      <div className="bg-card border border-border rounded-2xl p-6">
        <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground mb-4 flex items-center gap-2">
          <Users className="w-4 h-4 text-purple-500" /> Contractor Quality Scorecard
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2.5 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Contractor</th>
                <th className="text-center py-2.5 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Total NCs</th>
                <th className="text-center py-2.5 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Critical</th>
                <th className="text-center py-2.5 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Open</th>
                <th className="text-center py-2.5 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Rejected</th>
                <th className="text-center py-2.5 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Closure %</th>
                <th className="text-center py-2.5 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Debit</th>
                <th className="text-center py-2.5 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Avg Days</th>
                <th className="text-center py-2.5 px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Score</th>
              </tr>
            </thead>
            <tbody>
              {contractors.slice(0, 15).map((c: any, i: number) => (
                <tr key={i} className="border-b border-border/50 hover:bg-muted/50 transition-colors">
                  <td className="py-2.5 px-3 font-medium truncate max-w-[250px]" title={c.name}>{c.name}</td>
                  <td className="text-center py-2.5 px-3 font-bold">{c.total_ncs}</td>
                  <td className="text-center py-2.5 px-3 text-destructive font-bold">{c.critical}</td>
                  <td className="text-center py-2.5 px-3">{c.open}</td>
                  <td className="text-center py-2.5 px-3 text-orange-500">{c.rejected}</td>
                  <td className="text-center py-2.5 px-3">{c.closure_rate}%</td>
                  <td className="text-center py-2.5 px-3">{c.debit_total > 0 ? `₹${(c.debit_total / 1000).toFixed(0)}K` : '—'}</td>
                  <td className="text-center py-2.5 px-3">{c.avg_resolution_days != null ? `${c.avg_resolution_days}d` : '—'}</td>
                  <td className="text-center py-2.5 px-3">
                    <span className={`inline-flex items-center justify-center w-10 h-6 rounded-md text-xs font-bold ${c.quality_score >= 70 ? 'bg-success/10 text-success' : c.quality_score >= 40 ? 'bg-warning/10 text-warning' : 'bg-destructive/10 text-destructive'}`}>
                      {c.quality_score}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── NC List ── */}
      <div className="bg-card border border-border rounded-2xl p-6">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <Shield className="w-4 h-4 text-primary" /> Non-Conformance Register
          </h3>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search NCs..."
                className="pl-8 pr-3 py-1.5 bg-muted border border-border rounded-lg text-xs w-[200px] focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>
            {['all', 'raised', 'submitted', 'approved', 'rejected', 'completed'].map(s => (
              <button key={s} onClick={() => setActiveFilter(s)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${activeFilter === s ? 'bg-primary text-white' : 'bg-muted text-muted-foreground hover:text-foreground'}`}>
                {s === 'all' ? 'All' : STATUS_CONFIG[s]?.label || s}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2 max-h-[500px] overflow-y-auto custom-scrollbar">
          {filteredNCs.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground text-sm">No NCs found. Try syncing data first.</div>
          ) : filteredNCs.map((nc: any, i: number) => {
            const sCfg = STATUS_CONFIG[nc.status] || { label: nc.status, color: 'text-muted-foreground', bg: 'bg-muted', border: 'border-border' };
            const hCfg = HANDLER_CONFIG[nc.current_handler] || { label: nc.current_handler, color: 'text-muted-foreground' };
            return (
              <div key={nc.id || i} className="border border-border/60 rounded-xl p-4 hover:border-primary/30 hover:shadow-sm transition-all group">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono font-bold text-sm text-foreground">{nc.nc_label}</span>
                      <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${nc.category === 'Critical' ? 'bg-destructive/10 text-destructive border border-destructive/20' : 'bg-blue-500/10 text-blue-500 border border-blue-500/20'}`}>
                        {nc.category}
                      </span>
                      <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${sCfg.bg} ${sCfg.color} border ${sCfg.border}`}>
                        {sCfg.label}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1 truncate">{nc.defect_type}</p>
                    <div className="flex items-center gap-3 mt-2 text-[10px] text-muted-foreground/70 flex-wrap">
                      <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{nc.project_name} — {nc.workarea_name || 'N/A'}</span>
                      <span className="flex items-center gap-1"><Package className="w-3 h-3" />{nc.package_name || 'N/A'}</span>
                      <span className="flex items-center gap-1"><Users className="w-3 h-3" />{nc.vendor_name || nc.contractor_name || 'N/A'}</span>
                      {nc.status !== 'completed' && <span className={`flex items-center gap-1 font-bold ${hCfg.color}`}>→ {hCfg.label}</span>}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className={`text-lg font-bold ${nc.age_days > 30 ? 'text-destructive' : nc.age_days > 14 ? 'text-warning' : nc.age_days > 7 ? 'text-amber-500' : 'text-muted-foreground'}`}>
                      {nc.age_days}d
                    </div>
                    <div className="text-[9px] text-muted-foreground/50 uppercase">Age</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
