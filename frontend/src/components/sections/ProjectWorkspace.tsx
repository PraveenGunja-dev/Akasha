import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import {
  ArrowLeft, Sparkles, Activity, Clock, Shield, Target,
  Package, TrendingUp, AlertTriangle, CheckCircle2,
  Calendar, BarChart3, Truck, Brain, ChevronRight, Loader2,
  Users, DollarSign, Layers, MapPin, Database, FileText,
  Box, Network, Zap
} from 'lucide-react';

/* ── Circular Gauge ── */
const Gauge = ({ value, label, color, size = 72, stroke = 5 }: any) => {
  const radius = (size - stroke) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (Math.min(value, 100) / 100) * circumference;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} className="transform -rotate-90">
        <circle className="progress-ring-track" cx={size/2} cy={size/2} r={radius} strokeWidth={stroke} />
        <circle className="progress-ring-fill" cx={size/2} cy={size/2} r={radius} strokeWidth={stroke}
          stroke={color} strokeDasharray={circumference} strokeDashoffset={offset} />
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle"
          className="transform rotate-90 origin-center"
          style={{ fontSize: '14px', fontWeight: 700, fontFamily: 'monospace', fill: 'rgba(255,255,255,0.9)' }}>
          {Math.round(value)}
        </text>
      </svg>
      <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground/50">{label}</span>
    </div>
  );
};

/* ── Hero Metric Card ── */
const HeroMetric = ({ label, value, unit, color, icon: Icon }: any) => (
  <div className="intelligence-card p-5 flex flex-col gap-3">
    <div className="flex items-center justify-between">
      <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50">{label}</span>
      <Icon className={`w-4 h-4 ${color}`} />
    </div>
    <div className="flex items-baseline gap-1.5">
      <span className={`text-2xl font-light tracking-tight ${color}`}>{value}</span>
      {unit && <span className="text-xs text-muted-foreground/50">{unit}</span>}
    </div>
  </div>
);

/* ── Tab Button ── */
const TabBtn = ({ active, label, icon: Icon, onClick }: any) => (
  <button onClick={onClick}
    className={`flex items-center gap-2 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider rounded-lg transition-all ${
      active
        ? 'bg-primary/10 text-primary border border-primary/20'
        : 'text-muted-foreground/60 hover:text-foreground/80 hover:bg-white/[0.03] border border-transparent'
    }`}>
    <Icon className="w-3.5 h-3.5" /> {label}
  </button>
);

/* ── Format helpers ── */
const fmtCost = (v: number | null | undefined): string => {
  if (v == null) return '—';
  const abs = Math.abs(v);
  if (abs >= 10000000) return `₹${(v / 10000000).toFixed(2)} Cr`;
  if (abs >= 100000) return `₹${(v / 100000).toFixed(2)} L`;
  if (abs >= 1000) return `₹${(v / 1000).toFixed(1)}K`;
  return `₹${v.toFixed(0)}`;
};

const fmtMW = (v: number | null | undefined): string => {
  if (v == null) return '—';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(v);
};

const fmtHrs = (v: number | null | undefined): string => {
  if (v == null) return '—';
  return `${Math.round(v)} hrs`;
};

const fmtDays = (v: number | null | undefined): string => {
  if (v == null) return '—';
  return `${Math.round(v)} days`;
};

export default function ProjectWorkspace({ projectId: propProjectId, onBack }: { projectId?: string, onBack?: () => void }) {
  const params = useParams();
  const projectId = propProjectId || params.projectId;
  const navigate = useNavigate();
  const [project, setProject] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [diagnostic, setDiagnostic] = useState<string>('');
  const [diagLoading, setDiagLoading] = useState(false);

  useEffect(() => {
    const fetchProject = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/project-360");
        const json = await res.json();
        const found = json.find((p: any) => p.projectId === projectId);
        if (found) {
          setProject(found);
          // Auto-fetch AI diagnostic
          setDiagLoading(true);
          fetch("http://localhost:8000/api/project-diagnostic", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(found)
          })
          .then(res => res.json())
          .then(data => setDiagnostic(data.diagnostic || "Diagnostic unavailable."))
          .catch(() => setDiagnostic("Failed to generate diagnostic."))
          .finally(() => setDiagLoading(false));
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    const fetchDetail = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/project-360/${encodeURIComponent(projectId || '')}/detail`);
        if (res.ok) {
          const json = await res.json();
          setDetail(json);
        }
      } catch (err) {
        console.error('Detail fetch error:', err);
      } finally {
        setDetailLoading(false);
      }
    };

    fetchProject();
    fetchDetail();
  }, [projectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
          <span className="text-sm text-muted-foreground/60 font-medium tracking-wider uppercase">Loading Intelligence...</span>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-amber-500/50 mx-auto mb-4" />
          <p className="text-muted-foreground">Project not found.</p>
          <button onClick={() => navigate('/dashboard')} className="mt-4 text-primary text-sm hover:underline">
            ← Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const p = project;
  const progressPct = p.progress < 1 ? p.progress * 100 : p.progress;
  const tier = p.statusTier || p.health;
  const healthColor = tier === 'Critical' ? 'text-red-400' : (tier === 'High Risk' || tier === 'Watchlist') ? 'text-amber-400' : 'text-emerald-400';
  const dotClass = tier === 'Critical' ? 'status-dot-critical' : (tier === 'High Risk' || tier === 'Watchlist') ? 'status-dot-warning' : 'status-dot-healthy';

  // Activity completion chart
  const activityOption = {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.85)', borderColor: 'rgba(255,255,255,0.06)', textStyle: { color: '#fff', fontSize: 12 } },
    series: [{
      type: 'pie', radius: ['55%', '78%'], avoidLabelOverlap: false, center: ['50%', '50%'],
      itemStyle: { borderRadius: 6, borderColor: '#060A14', borderWidth: 3 },
      label: { show: false },
      data: [
        { value: p.completedActivities, name: 'Completed', itemStyle: { color: '#10B981' } },
        { value: p.inProgressActivities, name: 'In Progress', itemStyle: { color: '#3B82F6' } },
        { value: p.notStartedActivities, name: 'Not Started', itemStyle: { color: 'rgba(255,255,255,0.08)' } },
      ]
    }]
  };

  // Supply chain pipeline
  const supplyData = [
    { name: 'PO Volume', value: p.poVolumeMW, color: '#3B82F6' },
    { name: 'In Transit', value: p.inTransitMW, color: '#F59E0B' },
    { name: 'Inventory', value: p.inventoryMW, color: '#10B981' },
  ];
  const supplyOption = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.85)', borderColor: 'rgba(255,255,255,0.06)', textStyle: { color: '#fff' } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
    xAxis: { type: 'category', data: supplyData.map(s => s.name), axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } }, axisLabel: { color: 'rgba(255,255,255,0.5)', fontSize: 10 } },
    yAxis: { type: 'value', name: 'MW', axisLine: { show: false }, axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } } },
    series: [{ type: 'bar', data: supplyData.map(s => ({ value: s.value, itemStyle: { color: s.color, borderRadius: [6, 6, 0, 0] } })), barWidth: '40%' }]
  };

  // SAP vendor chart (from detail)
  const vendorChartOption = detail?.sap?.vendorBreakdown?.length > 0 ? {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.85)', borderColor: 'rgba(255,255,255,0.06)', textStyle: { color: '#fff' } },
    grid: { left: '3%', right: '8%', bottom: '3%', top: '8%', containLabel: true },
    xAxis: { type: 'value', name: 'MW', axisLine: { show: false }, axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } } },
    yAxis: {
      type: 'category',
      data: (detail.sap.vendorBreakdown.slice(0, 8)).map((v: any) => v.vendorName?.substring(0, 22) || 'Unknown').reverse(),
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: { color: 'rgba(255,255,255,0.5)', fontSize: 10 }
    },
    series: [{
      type: 'bar',
      data: (detail.sap.vendorBreakdown.slice(0, 8)).map((v: any) => v.totalMW).reverse(),
      itemStyle: { color: '#3B82F6', borderRadius: [0, 6, 6, 0] },
      barWidth: '50%'
    }]
  } : null;

  // Material type pie chart
  const materialTypeOption = detail?.sap?.materialBreakdown?.length > 0 ? {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.85)', borderColor: 'rgba(255,255,255,0.06)', textStyle: { color: '#fff', fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['45%', '72%'], center: ['50%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 4, borderColor: '#060A14', borderWidth: 2 },
      label: { show: false },
      data: detail.sap.materialBreakdown.map((m: any, i: number) => ({
        value: m.totalMW,
        name: m.type,
        itemStyle: { color: ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EF4444', '#EC4899'][i % 6] }
      }))
    }]
  } : null;

  // P6 detail data
  const p6 = detail?.p6;
  const mapping = detail?.mapping;
  const sap = detail?.sap;
  const tc = detail?.tc;

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ── Top Bar ── */}
      <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-xl border-b border-white/[0.06] px-6 py-3">
        <div className="max-w-[1600px] mx-auto flex items-center gap-4">
          <button onClick={() => onBack ? onBack() : navigate('/dashboard')}
            className="flex items-center gap-2 text-sm text-muted-foreground/70 hover:text-foreground transition-colors group">
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
            Back to Portfolio
          </button>
          <div className="h-5 w-px bg-white/[0.06]"></div>
          <div className="flex items-center gap-2">
            <div className={dotClass}></div>
            <span className="text-sm font-semibold text-foreground truncate max-w-[400px]">{p.projectName}</span>
          </div>
          <span className="text-[10px] font-mono text-muted-foreground/40 ml-auto">{p.projectId}</span>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">
        {/* ── Hero Section ── */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <HeroMetric label="Progress" value={`${Math.round(progressPct)}%`} icon={Activity} color={healthColor} />
          <HeroMetric label="Health Score" value={p.healthScore} unit="/100" icon={Shield} color={p.healthScore > 70 ? 'text-emerald-400' : p.healthScore > 40 ? 'text-amber-400' : 'text-red-400'} />
          <HeroMetric label="SPI" value={p.spi.toFixed(2)} icon={TrendingUp} color={p.spi >= 0.95 ? 'text-emerald-400' : 'text-red-400'} />
          <HeroMetric label="Schedule Variance" value={`${p.scheduleVariance > 0 ? '+' : ''}${p.scheduleVariance}`} unit="days" icon={Clock} color={p.scheduleVariance < -10 ? 'text-red-400' : 'text-foreground/80'} />
          <HeroMetric label="Forecast COD" value={p.forecastMonth} icon={Calendar} color="text-primary" />
          <HeroMetric label="Risk Score" value={p.riskScore} unit="/100" icon={AlertTriangle} color={p.riskScore > 50 ? 'text-red-400' : p.riskScore > 25 ? 'text-amber-400' : 'text-emerald-400'} />
        </div>

        {/* ── AI Project Summary ── */}
        <div className="intelligence-card p-6 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-72 h-72 bg-primary/[0.03] blur-[100px] rounded-full pointer-events-none"></div>
          
          <div className="flex items-start gap-4 mb-4 relative z-10">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary/20 to-purple-600/20 flex items-center justify-center shrink-0 border border-primary/10">
              <Brain className="w-5 h-5 text-primary/80" />
            </div>
            <div className="flex-1">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                AI Project Intelligence
                <span className="text-[9px] bg-primary/10 text-primary px-2 py-0.5 rounded-full font-bold uppercase tracking-wider border border-primary/20">
                  Live Analysis
                </span>
              </h3>
              <p className="text-[10px] text-muted-foreground/50 mt-0.5">Powered by AKASHA AI Engine</p>
            </div>
          </div>

          <div className="relative z-10 grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: AI Diagnostic */}
            <div>
              <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50 mb-3">Diagnostic Analysis</h4>
              <div className="border-l-2 border-primary/30 pl-4 min-h-[80px]">
                {diagLoading ? (
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin"></div>
                    <span className="text-sm text-muted-foreground/60 animate-pulse">Analyzing project intelligence...</span>
                  </div>
                ) : (
                  <p className="text-sm text-foreground/80 leading-relaxed">{diagnostic}</p>
                )}
              </div>
            </div>

            {/* Right: Key Metrics + Action */}
            <div className="space-y-4">
              <div>
                <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50 mb-2">Key Issue</h4>
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-lg ${
                    p.keyIssue === 'On Track' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'
                  }`}>
                    {p.keyIssue === 'On Track' ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                    {p.keyIssue}
                  </span>
                </div>
              </div>
              <div>
                <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50 mb-2">Recommended Action</h4>
                <p className="text-sm text-primary/80 leading-relaxed bg-primary/[0.04] border border-primary/10 rounded-lg px-4 py-3">
                  {p.recommendedAction}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* ── Tab Navigation ── */}
        <div className="flex items-center gap-2 border-b border-white/[0.06] pb-0 overflow-x-auto scrollbar-hide">
          <TabBtn active={activeTab === 'overview'} label="Overview" icon={BarChart3} onClick={() => setActiveTab('overview')} />
          <TabBtn active={activeTab === 'schedule'} label="Schedule" icon={Calendar} onClick={() => setActiveTab('schedule')} />
          <TabBtn active={activeTab === 'supply'} label="Supply Chain" icon={Truck} onClick={() => setActiveTab('supply')} />
          <TabBtn active={activeTab === 'risk'} label="Risk" icon={Shield} onClick={() => setActiveTab('risk')} />
          <TabBtn active={activeTab === 'sap'} label="SAP Intelligence" icon={Database} onClick={() => setActiveTab('sap')} />
          <TabBtn active={activeTab === 'p6'} label="P6 Deep Dive" icon={Layers} onClick={() => setActiveTab('p6')} />
          <TabBtn active={activeTab === 'transmission'} label="Transmission" icon={Network} onClick={() => setActiveTab('transmission')} />
        </div>

        {/* ── Tab Content ── */}
        <div className="animate-in fade-in duration-300">

          {/* ════════ OVERVIEW TAB ════════ */}
          {activeTab === 'overview' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Activity Breakdown */}
              <div className="intelligence-card p-6">
                <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-primary/70" />
                  Activity Completion
                </h3>
                <div className="flex items-center gap-6">
                  <div className="w-[160px] h-[160px]">
                    <ReactECharts option={activityOption} style={{ height: '100%', width: '100%' }} />
                  </div>
                  <div className="flex-1 space-y-3">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2"><div className="w-2.5 h-2.5 rounded bg-emerald-500"></div> Completed</div>
                      <span className="font-mono font-semibold text-foreground/90">{p.completedActivities}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2"><div className="w-2.5 h-2.5 rounded bg-blue-500"></div> In Progress</div>
                      <span className="font-mono font-semibold text-foreground/90">{p.inProgressActivities}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2"><div className="w-2.5 h-2.5 rounded bg-white/10"></div> Not Started</div>
                      <span className="font-mono font-semibold text-foreground/90">{p.notStartedActivities}</span>
                    </div>
                    <div className="border-t border-white/[0.06] pt-2 flex items-center justify-between text-sm">
                      <span className="text-muted-foreground/60">Total</span>
                      <span className="font-mono font-bold text-foreground">{p.activityCount}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Project Details */}
              <div className="intelligence-card p-6">
                <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                  <Target className="w-4 h-4 text-primary/70" />
                  Project Details
                </h3>
                <div className="space-y-1">
                  {[
                    ['Status', p.status],
                    ['Plant Code', p.sapPlantCode || '—'],
                    ['SPV Code', p.agelCode || '—'],
                    ['Capacity', p.capacityMW ? `${p.capacityMW} MW` : '—'],
                    ['Location', p6?.locationName || '—'],
                    ['Start Date', p.startDate || '—'],
                    ['Forecast Finish', p.forecastFinish],
                    ['Baseline Finish', p.baselineFinishDate || '—'],
                    ['Planned Duration', p.plannedDuration ? `${Math.round(p.plannedDuration)} hrs` : '—'],
                    ['Actual Duration', p.actualDuration ? `${Math.round(p.actualDuration)} hrs` : '—'],
                    ['Parent EPS', p.parentEPS || '—'],
                  ].map(([label, val]) => (
                    <div key={label} className="detail-row">
                      <span className="detail-row-label">{label}</span>
                      <span className="detail-row-value text-right max-w-[60%] truncate">{val}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ════════ SCHEDULE TAB ════════ */}
          {activeTab === 'schedule' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="intelligence-card p-6 flex flex-col items-center justify-center">
                <Gauge value={p.spi * 100} label="SPI" color={p.spi >= 0.95 ? '#10B981' : '#EF4444'} size={100} stroke={6} />
                <p className="text-xs text-muted-foreground/50 mt-3 text-center">
                  {p.spi >= 1.0 ? 'Ahead of schedule' : p.spi >= 0.95 ? 'Marginally on track' : 'Behind schedule'}
                </p>
              </div>
              <div className="intelligence-card p-6 flex flex-col items-center justify-center">
                <Gauge value={p.cpi * 100} label="CPI" color={p.cpi >= 0.95 ? '#10B981' : '#F59E0B'} size={100} stroke={6} />
                <p className="text-xs text-muted-foreground/50 mt-3 text-center">
                  {p.cpi >= 1.0 ? 'Under budget' : p.cpi >= 0.95 ? 'On budget' : 'Over budget'}
                </p>
              </div>
              <div className="intelligence-card p-6">
                <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50 mb-4">Schedule Timeline</h4>
                <div className="space-y-3">
                  {[
                    { dot: 'bg-blue-500', label: 'Start Date', value: p.startDate || '—' },
                    { dot: 'bg-cyan-500', label: 'Data Date', value: p6?.dataDate || '—' },
                    { dot: 'bg-amber-500', label: 'Baseline Finish', value: p.baselineFinishDate || '—' },
                    { dot: 'bg-red-500', label: 'Forecast Finish', value: p.forecastFinish },
                    { dot: 'bg-purple-500', label: 'Must Finish By', value: p6?.mustFinishByDate || '—' },
                  ].map(item => (
                    <div key={item.label} className="flex items-center gap-3">
                      <div className={`w-2 h-2 rounded-full ${item.dot}`}></div>
                      <span className="text-xs text-muted-foreground/60 w-28">{item.label}</span>
                      <span className="text-sm font-mono text-foreground/80">{item.value}</span>
                    </div>
                  ))}
                  <div className="flex items-center gap-3 pt-2 border-t border-white/[0.04]">
                    <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                    <span className="text-xs text-muted-foreground/60 w-28">Variance</span>
                    <span className={`text-sm font-mono font-semibold ${p.scheduleVariance < -10 ? 'text-red-400' : 'text-foreground/80'}`}>
                      {p.scheduleVariance} days
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ════════ SUPPLY CHAIN TAB ════════ */}
          {activeTab === 'supply' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="intelligence-card p-6">
                <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                  <Package className="w-4 h-4 text-primary/70" /> Supply Chain Pipeline
                </h3>
                <div className="h-[250px]">
                  <ReactECharts option={supplyOption} style={{ height: '100%', width: '100%' }} />
                </div>
              </div>
              <div className="intelligence-card p-6">
                <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                  <Truck className="w-4 h-4 text-primary/70" /> Material Status
                </h3>
                <div className="space-y-4">
                  {[
                    { label: 'PO Volume', value: `${p.poVolumeMW} MW`, color: 'text-blue-400' },
                    { label: 'In Transit', value: `${p.inTransitMW} MW`, color: 'text-amber-400' },
                    { label: 'Inventory (Received)', value: `${p.inventoryMW} MW`, color: 'text-emerald-400' },
                    { label: 'Material Availability', value: `${p.materialAvailability}%`, color: p.materialAvailability < 50 ? 'text-red-400' : 'text-emerald-400' },
                  ].map(item => (
                    <div key={item.label} className="flex items-center justify-between border-b border-white/[0.04] pb-3 last:border-0">
                      <span className="text-sm text-muted-foreground/60">{item.label}</span>
                      <span className={`text-lg font-mono font-semibold ${item.color}`}>{item.value}</span>
                    </div>
                  ))}
                  {/* Material Availability Bar */}
                  <div className="mt-2">
                    <div className="w-full h-2 rounded-full bg-white/[0.04] overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-1000"
                        style={{ width: `${Math.min(p.materialAvailability, 100)}%`, background: p.materialAvailability >= 80 ? '#10B981' : p.materialAvailability >= 50 ? '#F59E0B' : '#EF4444' }}>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ════════ RISK TAB ════════ */}
          {activeTab === 'risk' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="intelligence-card p-6 flex flex-col items-center">
                <Gauge value={p.riskScore} label="Risk Score" color={p.riskScore > 50 ? '#EF4444' : p.riskScore > 25 ? '#F59E0B' : '#10B981'} size={120} stroke={8} />
                <p className="text-sm text-muted-foreground/60 mt-4 text-center max-w-[280px]">
                  {p.riskScore > 50 ? 'High risk — immediate intervention required' : p.riskScore > 25 ? 'Moderate risk — close monitoring needed' : 'Low risk — continue standard monitoring'}
                </p>
              </div>
              <div className="intelligence-card p-6">
                <h3 className="text-sm font-semibold text-foreground mb-4">Risk Factors</h3>
                <div className="space-y-3">
                  {[
                    { factor: 'Schedule Delay', score: Math.min(40, Math.abs(p.scheduleVariance < 0 ? p.scheduleVariance : 0)), max: 40 },
                    { factor: 'SPI Below Target', score: Math.round(p.spi < 1 ? (1 - p.spi) * 100 : 0), max: 100 },
                    { factor: 'Material Shortage', score: Math.round(p.materialAvailability < 100 ? (100 - p.materialAvailability) * 0.5 : 0), max: 50 },
                  ].map(rf => (
                    <div key={rf.factor}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-muted-foreground/60">{rf.factor}</span>
                        <span className="text-xs font-mono text-foreground/70">{rf.score}/{rf.max}</span>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-white/[0.04]">
                        <div className="h-full rounded-full transition-all duration-700"
                          style={{ width: `${(rf.score / rf.max) * 100}%`, background: rf.score > rf.max * 0.6 ? '#EF4444' : rf.score > rf.max * 0.3 ? '#F59E0B' : '#10B981' }}></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ════════ SAP INTELLIGENCE TAB (NEW) ════════ */}
          {activeTab === 'sap' && (
            <div className="space-y-6">
              {detailLoading ? (
                <div className="flex items-center justify-center h-[300px]">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-5 h-5 text-primary animate-spin" />
                    <span className="text-sm text-muted-foreground/60">Loading SAP data...</span>
                  </div>
                </div>
              ) : !sap || sap.summary.totalPOs === 0 ? (
                <div className="intelligence-card p-12 flex flex-col items-center justify-center text-center">
                  <Database className="w-10 h-10 text-muted-foreground/20 mb-3" />
                  <p className="text-muted-foreground/60 text-sm">No SAP procurement data found for this project.</p>
                  <p className="text-muted-foreground/40 text-xs mt-1">Plant code: {mapping?.sapPlantCode || '—'} · SPV: {mapping?.agelCode || '—'}</p>
                </div>
              ) : (
                <>
                  {/* SAP Summary Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                    <HeroMetric label="Total POs" value={sap.summary.totalPOs} icon={FileText} color="text-blue-400" />
                    <HeroMetric label="Vendors" value={sap.summary.totalVendors} icon={Users} color="text-purple-400" />
                    <HeroMetric label="PO Volume" value={fmtMW(sap.summary.totalPOMW)} unit="MW" icon={Package} color="text-blue-400" />
                    <HeroMetric label="In Transit" value={fmtMW(sap.summary.totalInTransitMW)} unit="MW" icon={Truck} color="text-amber-400" />
                    <HeroMetric label="Inventory" value={fmtMW(sap.summary.totalInventoryMW)} unit="MW" icon={Box} color="text-emerald-400" />
                    <HeroMetric label="Net Value" value={fmtCost(sap.summary.totalNetValue)} icon={DollarSign} color="text-pink-400" />
                  </div>

                  {/* Allocation Context */}
                  {sap.allocation && (
                    <div className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-primary/[0.04] border border-primary/[0.08] text-[11px] text-muted-foreground/60">
                      <Database className="w-3.5 h-3.5 text-primary/50 shrink-0" />
                      <span>
                        Data allocated to this project: <span className="font-semibold text-foreground/70">{sap.allocation.projectCapacityMW} MW</span> of{' '}
                        <span className="font-medium text-foreground/60">{sap.allocation.totalPlantCapacityMW} MW</span> total plant capacity
                        <span className="text-muted-foreground/40"> · </span>
                        Ratio: <span className="font-mono font-semibold text-primary/70">{(sap.allocation.allocationRatio * 100).toFixed(1)}%</span>
                        {sap.allocation.wbsFilter && (
                          <>
                            <span className="text-muted-foreground/40"> · </span>
                            WBS: <span className="font-mono text-foreground/60">{sap.allocation.wbsFilter}</span>
                          </>
                        )}
                      </span>
                    </div>
                  )}

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Vendor Breakdown Chart */}
                    {vendorChartOption && (
                      <div className="intelligence-card p-6">
                        <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                          <Users className="w-4 h-4 text-primary/70" /> Top Vendors by Volume (MW)
                        </h3>
                        <div className="h-[280px]">
                          <ReactECharts option={vendorChartOption} style={{ height: '100%', width: '100%' }} />
                        </div>
                      </div>
                    )}

                    {/* Material Type Distribution */}
                    {materialTypeOption && (
                      <div className="intelligence-card p-6">
                        <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                          <Box className="w-4 h-4 text-primary/70" /> Material Type Distribution
                        </h3>
                        <div className="flex items-center gap-6">
                          <div className="w-[200px] h-[200px]">
                            <ReactECharts option={materialTypeOption} style={{ height: '100%', width: '100%' }} />
                          </div>
                          <div className="flex-1 space-y-2">
                            {detail.sap.materialBreakdown.map((m: any, i: number) => (
                              <div key={m.type} className="flex items-center justify-between text-xs">
                                <div className="flex items-center gap-2">
                                  <div className="w-2.5 h-2.5 rounded" style={{ background: ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EF4444', '#EC4899'][i % 6] }}></div>
                                  <span className="text-muted-foreground/70 truncate max-w-[120px]">{m.type}</span>
                                </div>
                                <span className="font-mono text-foreground/80">{fmtMW(m.totalMW)} MW</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Vendor Breakdown Table */}
                  <div className="intelligence-card p-6">
                    <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                      <Users className="w-4 h-4 text-primary/70" /> Vendor Summary
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="intel-table">
                        <thead>
                          <tr>
                            <th>Vendor Name</th>
                            <th>Vendor Code</th>
                            <th className="text-right">POs</th>
                            <th className="text-right">Materials</th>
                            <th className="text-right">Volume (MW)</th>
                            <th className="text-right">Net Value</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sap.vendorBreakdown.map((v: any, i: number) => (
                            <tr key={i}>
                              <td className="font-medium text-foreground/90 max-w-[200px] truncate">{v.vendorName}</td>
                              <td className="font-mono text-xs text-muted-foreground/60">{v.vendorCode || '—'}</td>
                              <td className="text-right font-mono">{v.poCount}</td>
                              <td className="text-right font-mono">{v.materialCount}</td>
                              <td className="text-right font-mono font-semibold text-blue-400">{fmtMW(v.totalMW)}</td>
                              <td className="text-right font-mono text-foreground/70">{fmtCost(v.totalValue)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Purchase Order Detail Table */}
                  <div className="intelligence-card p-6">
                    <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-primary/70" /> Purchase Orders (ME2M)
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="intel-table">
                        <thead>
                          <tr>
                            <th>PO Number</th>
                            <th>Vendor Name</th>
                            <th>Material Code</th>
                            <th>Material Type</th>
                            <th className="text-right">Qty (MW)</th>
                            <th className="text-right">Net Value</th>
                            <th>Plant</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sap.purchaseOrders.slice(0, 50).map((po: any, i: number) => (
                            <tr key={i}>
                              <td className="font-mono text-xs font-medium text-primary/80">{po.poNumber}</td>
                              <td className="max-w-[180px] truncate">{po.vendorName}</td>
                              <td className="font-mono text-xs text-muted-foreground/60">{po.materialCode}</td>
                              <td className="text-muted-foreground/70">{po.materialType || '—'}</td>
                              <td className="text-right font-mono font-semibold">{fmtMW(po.poQuantityMW)}</td>
                              <td className="text-right font-mono text-foreground/70">{fmtCost(po.netOrderValue)}</td>
                              <td className="font-mono text-xs text-muted-foreground/50">{po.plantCode}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {sap.purchaseOrders.length > 50 && (
                        <p className="text-[10px] text-muted-foreground/40 mt-2 text-center">Showing first 50 of {sap.purchaseOrders.length} records</p>
                      )}
                    </div>
                  </div>

                  {/* In-Transit Table */}
                  {sap.inTransit.length > 0 && (
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Truck className="w-4 h-4 text-primary/70" /> In-Transit Shipments (MIGO)
                      </h3>
                      <div className="overflow-x-auto">
                        <table className="intel-table">
                          <thead>
                            <tr>
                              <th>PO Number</th>
                              <th>Vendor Name</th>
                              <th>Material Code</th>
                              <th className="text-right">Qty (MW)</th>
                              <th>GR Date</th>
                              <th>WBS Element</th>
                              <th>Plant</th>
                            </tr>
                          </thead>
                          <tbody>
                            {sap.inTransit.slice(0, 50).map((t: any, i: number) => (
                              <tr key={i}>
                                <td className="font-mono text-xs font-medium text-primary/80">{t.poNumber || '—'}</td>
                                <td className="max-w-[180px] truncate">{t.vendorName || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/60">{t.materialCode}</td>
                                <td className="text-right font-mono font-semibold text-amber-400">{fmtMW(t.quantityMW)}</td>
                                <td className="font-mono text-xs">{t.grPostingDate || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/50 max-w-[120px] truncate">{t.wbsElement || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/50">{t.plantCode}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Inventory Table */}
                  {sap.inventory.length > 0 && (
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Box className="w-4 h-4 text-primary/70" /> Inventory Records (MB52)
                      </h3>
                      <div className="overflow-x-auto">
                        <table className="intel-table">
                          <thead>
                            <tr>
                              <th>Purchase Order</th>
                              <th>Material Code</th>
                              <th>Vendor Code</th>
                              <th className="text-right">Qty (MW)</th>
                              <th>Posting Date</th>
                              <th>WBS Element</th>
                              <th>Storage Loc</th>
                            </tr>
                          </thead>
                          <tbody>
                            {sap.inventory.slice(0, 50).map((inv: any, i: number) => (
                              <tr key={i}>
                                <td className="font-mono text-xs font-medium text-primary/80">{inv.purchaseOrder || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/60">{inv.materialCode}</td>
                                <td className="font-mono text-xs text-muted-foreground/60">{inv.vendorCode || '—'}</td>
                                <td className="text-right font-mono font-semibold text-emerald-400">{fmtMW(inv.quantityMW)}</td>
                                <td className="font-mono text-xs">{inv.postingDate || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/50 max-w-[120px] truncate">{inv.wbsElement || '—'}</td>
                                <td className="text-muted-foreground/60 text-xs">{inv.storageLocation || '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ════════ P6 DEEP DIVE TAB (NEW) ════════ */}
          {activeTab === 'p6' && (
            <div className="space-y-6">
              {detailLoading ? (
                <div className="flex items-center justify-center h-[300px]">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-5 h-5 text-primary animate-spin" />
                    <span className="text-sm text-muted-foreground/60">Loading P6 data...</span>
                  </div>
                </div>
              ) : !p6 ? (
                <div className="intelligence-card p-12 flex flex-col items-center justify-center text-center">
                  <Layers className="w-10 h-10 text-muted-foreground/20 mb-3" />
                  <p className="text-muted-foreground/60 text-sm">No enriched P6 data available.</p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                    {/* Full Project Timeline */}
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-primary/70" /> Complete Project Timeline
                      </h3>
                      <div className="space-y-1">
                        {[
                          ['Project ID', p6.projectId],
                          ['Status', p6.status],
                          ['Location', p6.locationName || '—'],
                          ['Parent EPS', p6.parentEPSName || '—'],
                          ['Start Date', p6.startDate || '—'],
                          ['Planned Start', p6.plannedStartDate || '—'],
                          ['Finish Date', p6.finishDate || '—'],
                          ['Scheduled Finish', p6.scheduledFinishDate || '—'],
                          ['Data Date', p6.dataDate || '—'],
                          ['Must Finish By', p6.mustFinishByDate || '—'],
                          ['Baseline Start', p6.baselineStartDate || '—'],
                          ['Baseline Finish', p6.baselineFinishDate || '—'],
                          ['Last Synced', p6.lastSyncedAt || '—'],
                        ].map(([label, val]) => (
                          <div key={label as string} className="detail-row">
                            <span className="detail-row-label">{label}</span>
                            <span className="detail-row-value">{val}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Cost Analysis */}
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <DollarSign className="w-4 h-4 text-primary/70" /> Cost Analysis
                      </h3>
                      <div className="space-y-1">
                        {[
                          ['Actual Total Cost', fmtCost(p6.actualTotalCost)],
                          ['Planned Cost', fmtCost(p6.plannedCost)],
                          ['Current Budget', fmtCost(p6.currentBudget)],
                          ['Cost Variance', fmtCost(p6.totalCostVariance)],
                          ['Baseline Total Cost', fmtCost(p6.baselineTotalCost)],
                          ['CPI', p6.cpi != null ? p6.cpi.toFixed(3) : '—'],
                          ['SPI', p6.spi != null ? p6.spi.toFixed(3) : '—'],
                        ].map(([label, val]) => (
                          <div key={label as string} className="detail-row">
                            <span className="detail-row-label">{label}</span>
                            <span className={`detail-row-value ${
                              label === 'Cost Variance' && p6.totalCostVariance && p6.totalCostVariance < 0 ? 'text-red-400' :
                              label === 'CPI' && p6.cpi && p6.cpi < 0.95 ? 'text-amber-400' :
                              label === 'SPI' && p6.spi && p6.spi < 0.95 ? 'text-red-400' : ''
                            }`}>{val}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Float Analysis */}
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Clock className="w-4 h-4 text-primary/70" /> Float & Variance
                      </h3>
                      <div className="space-y-1">
                        {[
                          ['Total Float', p6.totalFloat != null ? `${Math.round(p6.totalFloat)} hrs` : '—'],
                          ['Finish Date Variance', fmtDays(p6.finishDateVariance)],
                          ['Start Date Variance', fmtDays(p6.startDateVariance)],
                          ['Duration Variance', p6.durationVariance != null ? `${Math.round(p6.durationVariance)} hrs` : '—'],
                        ].map(([label, val]) => (
                          <div key={label as string} className="detail-row">
                            <span className="detail-row-label">{label}</span>
                            <span className={`detail-row-value ${
                              (label === 'Total Float' && p6.totalFloat != null && p6.totalFloat <= 0) ? 'text-red-400 font-semibold' :
                              (label === 'Finish Date Variance' && p6.finishDateVariance != null && p6.finishDateVariance < -10) ? 'text-red-400' : ''
                            }`}>{val}</span>
                          </div>
                        ))}
                        {p6.totalFloat != null && (
                          <div className="mt-3 p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                            <p className="text-[11px] text-muted-foreground/60 leading-relaxed">
                              {p6.totalFloat <= 0
                                ? '⚠️ Critical path — zero or negative float. Any delay directly impacts the project finish date.'
                                : p6.totalFloat < 80
                                ? '⚡ Low float — limited buffer remaining. Monitor closely for potential delays.'
                                : '✅ Adequate float — schedule has sufficient buffer.'}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Duration Analysis */}
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Clock className="w-4 h-4 text-primary/70" /> Duration Analysis
                      </h3>
                      <div className="space-y-1">
                        {[
                          ['Planned Duration', fmtHrs(p6.plannedDuration)],
                          ['Actual Duration', fmtHrs(p6.actualDuration)],
                          ['Remaining Duration', fmtHrs(p6.remainingDuration)],
                          ['Baseline Duration', fmtHrs(p6.baselineDuration)],
                          ['% Complete', p6.durationPercentComplete != null ? `${(p6.durationPercentComplete < 1 ? p6.durationPercentComplete * 100 : p6.durationPercentComplete).toFixed(1)}%` : '—'],
                        ].map(([label, val]) => (
                          <div key={label as string} className="detail-row">
                            <span className="detail-row-label">{label}</span>
                            <span className="detail-row-value">{val}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Activity Baseline Comparison */}
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <BarChart3 className="w-4 h-4 text-primary/70" /> Baseline vs Current
                      </h3>
                      <div className="space-y-3">
                        {[
                          { label: 'Completed', current: p6.completedActivities, baseline: p6.baselineCompletedActivities, color: '#10B981' },
                          { label: 'In Progress', current: p6.inProgressActivities, baseline: p6.baselineInProgressActivities, color: '#3B82F6' },
                          { label: 'Not Started', current: p6.notStartedActivities, baseline: p6.baselineNotStartedActivities, color: 'rgba(255,255,255,0.15)' },
                        ].map(item => (
                          <div key={item.label}>
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs text-muted-foreground/60">{item.label}</span>
                              <div className="flex items-center gap-3 text-xs font-mono">
                                <span className="text-foreground/80">{item.current ?? '—'}</span>
                                <span className="text-muted-foreground/30">vs</span>
                                <span className="text-muted-foreground/50">{item.baseline ?? '—'}</span>
                              </div>
                            </div>
                            {item.current != null && (
                              <div className="flex gap-1 h-1.5">
                                <div className="rounded-full" style={{ width: `${Math.max(5, (item.current / Math.max(p6.activityCount || 1, 1)) * 100)}%`, background: item.color }}></div>
                                {item.baseline != null && (
                                  <div className="rounded-full opacity-30" style={{ width: `${Math.max(5, (item.baseline / Math.max(p6.activityCount || 1, 1)) * 100)}%`, background: item.color }}></div>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Mapping Info */}
                  {mapping && (
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-primary/70" /> Project Mapping
                      </h3>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        {[
                          ['P6 Project Name', mapping.p6ProjectName],
                          ['SAP Plant Code', mapping.sapPlantCode || '—'],
                          ['AGEL Code', mapping.agelCode || '—'],
                          ['Module WBS', mapping.moduleWBS || '—'],
                          ['Capacity', mapping.capacityMW ? `${mapping.capacityMW} MW` : '—'],
                        ].map(([label, val]) => (
                          <div key={label as string}>
                            <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/40 mb-1">{label}</div>
                            <div className="text-sm font-mono text-foreground/80 truncate">{val}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ════════ TRANSMISSION TAB ════════ */}
          {activeTab === 'transmission' && (
            <div className="space-y-6">
              {detailLoading ? (
                <div className="flex items-center justify-center h-[300px]">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-5 h-5 text-primary animate-spin" />
                    <span className="text-sm text-muted-foreground/60">Loading Transmission data...</span>
                  </div>
                </div>
              ) : !tc || !tc.summary.hasData ? (
                <div className="intelligence-card p-12 flex flex-col items-center justify-center text-center">
                  <Network className="w-10 h-10 text-muted-foreground/20 mb-3" />
                  <p className="text-muted-foreground/60 text-sm">No Transmission data linked to this project.</p>
                  <p className="text-muted-foreground/40 text-xs mt-1">TC Project: {mapping?.tcProjectName || '—'}</p>
                </div>
              ) : (
                <>
                  {/* TC Summary Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <HeroMetric label="Khavda Edges" value={tc.summary.totalKhavdaEdges} icon={Zap} color="text-purple-400" />
                    <HeroMetric label="Rajasthan Edges" value={tc.summary.totalRajasthanEdges} icon={Network} color="text-blue-400" />
                    <HeroMetric label="Total Mapped MW" value={tc.summary.totalMW ? `${tc.summary.totalMW}` : '—'} unit="MW" icon={Target} color="text-emerald-400" />
                    <HeroMetric label="TC Project" value={mapping?.tcProjectName || '—'} icon={MapPin} color="text-amber-400" />
                  </div>

                  {/* Khavda Transmission Lines Table */}
                  {tc.khavdaEdges.length > 0 && (
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Zap className="w-4 h-4 text-purple-400" /> Khavda Transmission Lines
                      </h3>
                      <div className="overflow-x-auto">
                        <table className="intel-table">
                          <thead>
                            <tr>
                              <th>Project / Phase</th>
                              <th>From</th>
                              <th>To</th>
                              <th>Voltage</th>
                              <th>Length</th>
                              <th>Contractor</th>
                              <th>Status</th>
                              <th>Erection</th>
                              <th>Foundation</th>
                              <th>Stringing</th>
                              <th>Expected Date</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tc.khavdaEdges.map((edge: any, i: number) => (
                              <tr key={i}>
                                <td className="font-bold text-purple-400 font-mono text-[10px] uppercase tracking-wider truncate max-w-[200px]" title={`${edge.project} (${edge.phase})`}>
                                  {edge.project} <span className="text-muted-foreground ml-1 font-normal lowercase tracking-normal">({edge.phase})</span>
                                </td>
                                <td className="font-medium text-foreground/90 max-w-[150px] truncate" title={edge.fromLabel || edge.fromNode}>{edge.fromLabel || edge.fromNode}</td>
                                <td className="font-medium text-foreground/90 max-w-[150px] truncate" title={edge.toLabel || edge.toNode}>{edge.toLabel || edge.toNode}</td>
                                <td className="font-mono text-xs">{edge.voltage || '—'}</td>
                                <td className="font-mono text-xs">{edge.length || '—'}</td>
                                <td className="text-muted-foreground/70 text-xs">{edge.contractor || '—'}</td>
                                <td>
                                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                                    edge.normalizedStatus === 'charged' ? 'bg-emerald-500/10 text-emerald-400' :
                                    edge.normalizedStatus === 'in_progress' ? 'bg-amber-500/10 text-amber-400' :
                                    'bg-muted text-muted-foreground'
                                  }`}>
                                    {edge.status || '—'}
                                  </span>
                                </td>
                                <td className="text-xs text-muted-foreground/80">{edge.erection || '—'}</td>
                                <td className="text-xs text-muted-foreground/80">{edge.foundation || '—'}</td>
                                <td className="text-xs text-muted-foreground/80">{edge.stringing || '—'}</td>
                                <td className="text-xs font-mono">{edge.expectedDate || '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Rajasthan Transmission Lines Table */}
                  {tc.rajasthanEdges.length > 0 && (
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Network className="w-4 h-4 text-blue-400" /> Rajasthan Transmission Lines
                      </h3>
                      <div className="overflow-x-auto">
                        <table className="intel-table">
                          <thead>
                            <tr>
                              <th>Project / Phase</th>
                              <th>From</th>
                              <th>To</th>
                              <th>Voltage</th>
                              <th>Length</th>
                              <th>Contractor</th>
                              <th>Status</th>
                              <th>Erection</th>
                              <th>Foundation</th>
                              <th>Stringing</th>
                              <th>Expected Date</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tc.rajasthanEdges.map((edge: any, i: number) => (
                              <tr key={i}>
                                <td className="font-bold text-purple-400 font-mono text-[10px] uppercase tracking-wider truncate max-w-[200px]" title={`${edge.project} (${edge.phase})`}>
                                  {edge.project} <span className="text-muted-foreground ml-1 font-normal lowercase tracking-normal">({edge.phase})</span>
                                </td>
                                <td className="font-medium text-foreground/90 max-w-[150px] truncate" title={edge.fromLabel || edge.fromNode}>{edge.fromLabel || edge.fromNode}</td>
                                <td className="font-medium text-foreground/90 max-w-[150px] truncate" title={edge.toLabel || edge.toNode}>{edge.toLabel || edge.toNode}</td>
                                <td className="font-mono text-xs">{edge.voltage || '—'}</td>
                                <td className="font-mono text-xs">{edge.length || '—'}</td>
                                <td className="text-muted-foreground/70 text-xs max-w-[120px] truncate">{edge.contractor || '—'}</td>
                                <td>
                                  <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                                    edge.normalizedStatus === 'Completed' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                                    edge.normalizedStatus === 'In Progress' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                                    'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                                  }`}>
                                    {edge.normalizedStatus || edge.status || '—'}
                                  </span>
                                </td>
                                <td className="font-mono text-xs text-muted-foreground/70">{edge.erection || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/70">{edge.foundation || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/70">{edge.stringing || '—'}</td>
                                <td className="font-mono text-xs">{edge.expectedDate || '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
