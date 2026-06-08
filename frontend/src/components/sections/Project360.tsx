import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, Sparkles, ChevronRight, AlertTriangle, Shield,
  Clock, Package, CheckCircle2, XCircle, Eye,
  Zap, Target, Layers,
  Brain, Truck, DollarSign, Users,
  CalendarClock, Factory, SlidersHorizontal, X
} from 'lucide-react';

/* ═══════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════ */
const fmtNum = (n: number): string => {
  if (n >= 10000000) return `${(n / 10000000).toFixed(1)} Cr`;
  if (n >= 100000) return `${(n / 100000).toFixed(1)} L`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toFixed(1);
};

const fmtMW = (n: number): string => {
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)} GW`;
  return `${n.toFixed(1)} MW`;
};

/* ═══════════════════════════════════════════════════════════
   STATUS TIER CONFIGURATION
   ═══════════════════════════════════════════════════════════ */
const STATUS_CONFIG: Record<string, { color: string; bgColor: string; borderColor: string; dotClass: string; icon: any; label: string }> = {
  All: { color: 'text-foreground', bgColor: 'bg-muted/30', borderColor: 'border-border', dotClass: '', icon: Layers, label: 'All' },
  Critical: { color: 'text-red-400', bgColor: 'bg-red-500/10', borderColor: 'border-red-500/20', dotClass: 'status-dot-critical', icon: XCircle, label: 'Critical' },
  'High Risk': { color: 'text-orange-400', bgColor: 'bg-orange-500/10', borderColor: 'border-orange-500/15', dotClass: 'status-dot-warning', icon: AlertTriangle, label: 'High Risk' },
  Watchlist: { color: 'text-amber-400', bgColor: 'bg-amber-500/10', borderColor: 'border-amber-500/12', dotClass: 'status-dot-warning', icon: Eye, label: 'Watchlist' },
  Healthy: { color: 'text-emerald-400', bgColor: 'bg-emerald-500/10', borderColor: 'border-emerald-500/10', dotClass: 'status-dot-healthy', icon: Shield, label: 'Healthy' },
  Completed: { color: 'text-blue-400', bgColor: 'bg-blue-500/10', borderColor: 'border-blue-500/10', dotClass: 'status-dot-healthy', icon: CheckCircle2, label: 'Completed' },
};

const ISSUE_CONFIG: Record<string, { icon: any; color: string; bg: string }> = {
  'Material Bottleneck': { icon: Package, color: 'text-red-500', bg: '' },
  'Vendor Delay': { icon: Truck, color: 'text-purple-500', bg: '' },
  'Schedule Slippage': { icon: Clock, color: 'text-amber-500', bg: '' },
  'Cost Overrun': { icon: DollarSign, color: 'text-pink-500', bg: '' },
  'Procurement Gap': { icon: Factory, color: 'text-orange-500', bg: '' },
  'Resource Shortage': { icon: Users, color: 'text-cyan-500', bg: '' },
  'Engineering Delay': { icon: CalendarClock, color: 'text-yellow-500', bg: '' },
  'On Track': { icon: CheckCircle2, color: 'text-emerald-500', bg: '' },
};

const RISK_FILTER_OPTIONS = [
  'Material Risk', 'Schedule Risk', 'Vendor Risk', 'Financial Risk',
  'Procurement Risk', 'COD Risk', 'Resource Risk'
];

/* ═══════════════════════════════════════════════════════════
   STATUS SUMMARY PILL
   ═══════════════════════════════════════════════════════════ */
const StatusPill = ({ tier, count, active, onClick }: { tier: string; count: number; active: boolean; onClick: () => void }) => {
  const cfg = STATUS_CONFIG[tier] || STATUS_CONFIG['Healthy'];
  return (
    <button onClick={onClick}
      className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-all duration-200 cursor-pointer ${active
          ? `${cfg.bgColor} ${cfg.borderColor} shadow-sm`
          : 'bg-card border-border hover:bg-muted/20'
        }`}>
      {cfg.dotClass && <div className={cfg.dotClass}></div>}
      <div className="text-left">
        <div className={`text-xl font-semibold tracking-tight ${active ? cfg.color : 'text-foreground'}`}>{count}</div>
        <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{tier}</div>
      </div>
    </button>
  );
};

/* ═══════════════════════════════════════════════════════════
   AI EXECUTIVE BRIEFING CARD
   ═══════════════════════════════════════════════════════════ */
const AIBriefingCard = ({ data }: { data: any[] }) => {
  const critCount = data.filter(d => d.statusTier === 'Critical').length;
  const highRiskCount = data.filter(d => d.statusTier === 'High Risk').length;
  const watchlistCount = data.filter(d => d.statusTier === 'Watchlist').length;
  const needsAttention = critCount + highRiskCount + watchlistCount;

  // Aggregate drivers
  const issueBreakdown: Record<string, number> = {};
  data.forEach(d => {
    if (d.primaryIssue !== 'On Track') {
      issueBreakdown[d.primaryIssue] = (issueBreakdown[d.primaryIssue] || 0) + 1;
    }
  });
  const topDrivers = Object.entries(issueBreakdown).sort((a, b) => b[1] - a[1]).slice(0, 3);

  // Aggregate supply risk
  const totalSupplyGap = data.reduce((sum, d) => {
    const gap = (d.poVolumeMW || 0) - (d.inventoryMW || 0) - (d.inTransitMW || 0);
    return sum + (gap > 0 ? gap : 0);
  }, 0);

  // Average delay
  const delayedProjects = data.filter(d => d.delayDays > 0);
  const avgDelay = delayedProjects.length > 0 ? Math.round(delayedProjects.reduce((s, d) => s + d.delayDays, 0) / delayedProjects.length) : 0;
  const maxDelay = delayedProjects.length > 0 ? Math.max(...delayedProjects.map(d => d.delayDays)) : 0;

  // Avg confidence
  const avgConfidence = Math.round(data.reduce((s, d) => s + (d.confidence || 70), 0) / (data.length || 1));

  return (
    <div className="intelligence-card p-6 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-premium flex items-center justify-center shadow-lg shadow-primary/20">
            <Brain className="w-6 h-6 text-white" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-foreground flex items-center gap-2 tracking-tight">
              AI Portfolio Briefing
              <span className="text-[10px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider border border-emerald-500/20 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> Live
              </span>
            </h3>
            <p className="text-[10px] text-muted-foreground mt-0.5">Powered by AKASHA Intelligence Engine</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span>Confidence:</span>
          <span className="font-mono font-bold text-primary">{avgConfidence}%</span>
        </div>
      </div>

      {/* Briefing Body */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-8">
        {/* Left: Summary */}
        <div className="space-y-5">
          <p className="text-[15px] text-foreground leading-relaxed">
            <span className="font-semibold text-primary">{needsAttention} of {data.length} projects</span> require attention.
            {critCount > 0 && <span className="text-red-500 font-medium"> {critCount} are in critical status.</span>}
            {highRiskCount > 0 && <span className="text-amber-500 font-medium"> {highRiskCount} at high risk.</span>}
            {watchlistCount > 0 && <span className="text-purple-500 font-medium"> {watchlistCount} on watchlist.</span>}
          </p>

          {topDrivers.length > 0 && (
            <div>
              <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2.5">Primary Drivers</div>
              <div className="flex flex-wrap gap-2">
                {topDrivers.map(([issue, count]) => {
                  const cfg = ISSUE_CONFIG[issue] || ISSUE_CONFIG['On Track'];
                  const IssueIcon = cfg.icon;
                  return (
                    <span key={issue} className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-3 py-1.5 rounded-lg bg-muted/50 border border-border/50 ${cfg.color}`}>
                      <IssueIcon className="w-3.5 h-3.5" /> {issue} <span className="opacity-60">({count})</span>
                    </span>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Right: Impact Metrics */}
        <div className="space-y-4 lg:border-l lg:border-border/50 lg:pl-8 flex flex-col justify-center">
          <div className="bg-red-500/5 dark:bg-red-500/10 rounded-xl p-4 border border-red-500/10">
            <div className="text-[10px] font-bold uppercase tracking-widest text-red-500/70 mb-1">Supply Risk Exposure</div>
            <div className="text-2xl font-light text-red-500 tracking-tight">{fmtMW(totalSupplyGap)}</div>
            <div className="text-[11px] text-muted-foreground mt-1">Pending across portfolio</div>
          </div>
          <div className="bg-amber-500/5 dark:bg-amber-500/10 rounded-xl p-4 border border-amber-500/10">
            <div className="text-[10px] font-bold uppercase tracking-widest text-amber-500/70 mb-1">Schedule Slippage</div>
            <div className="text-2xl font-light text-amber-500 tracking-tight">{avgDelay} <span className="text-sm font-normal text-amber-500/70">days (avg)</span></div>
            <div className="text-[11px] text-muted-foreground mt-1">Max exposure: {maxDelay} days</div>
          </div>
        </div>
      </div>
    </div>
  );
};

const ProjectRow = ({ project, onOpen }: { project: any; onOpen: (id: string) => void }) => {
  const statusCfg = STATUS_CONFIG[project.statusTier] || STATUS_CONFIG['Healthy'];
  const issueCfg = ISSUE_CONFIG[project.primaryIssue] || ISSUE_CONFIG['On Track'];
  const IssueIcon = issueCfg.icon;

  const accentColor =
    project.statusTier === 'Critical' ? '#EF4444' :
      project.statusTier === 'High Risk' ? '#F97316' :
        project.statusTier === 'Watchlist' ? '#F59E0B' :
          project.statusTier === 'Completed' ? '#3B82F6' : '#10B981';

  const supplyGap = Math.max(0, (project.poVolumeMW || 0) - (project.inventoryMW || 0) - (project.inTransitMW || 0));

  return (
    <div
      onClick={() => onOpen(project.projectId)}
      className="group relative flex items-center justify-between px-6 py-4 bg-card hover:bg-muted/30 border-b border-border/50 cursor-pointer transition-colors"
    >
      {/* Left Accent Line on Hover */}
      <div className="absolute left-0 top-0 bottom-0 w-[2px] opacity-0 group-hover:opacity-100 transition-opacity" style={{ backgroundColor: accentColor }}></div>

      {/* 1. Status & Name */}
      <div className="flex flex-col gap-1 w-[30%] min-w-[250px]">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-semibold text-foreground/90 group-hover:text-primary transition-colors truncate">
            {project.projectName}
          </h3>
          <div className={`w-2 h-2 rounded-full shrink-0 ${statusCfg.bgColor}`} style={{ backgroundColor: accentColor, boxShadow: `0 0 6px ${accentColor}80` }}></div>
        </div>
        <div className="flex items-center gap-3 text-[10px] font-mono text-muted-foreground mt-1">
           {project.capacityMW > 0 && <span className="bg-muted px-1.5 py-0.5 rounded text-foreground/80">{project.capacityMW} MW</span>}
           {project.sapPlantCode && <span className="opacity-80 border-l border-border pl-3">SPV: {project.sapPlantCode}</span>}
           {project.projectId && <span className="opacity-80 border-l border-border pl-3">P6: {project.projectId}</span>}
        </div>
      </div>

      {/* 2. Project Health & AI Driver */}
      <div className="w-[25%] min-w-[200px] flex flex-col gap-2 pr-4">
        <div className={`flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider ${issueCfg.color}`}>
           <IssueIcon className="w-3.5 h-3.5" />
           {project.primaryIssue}
        </div>
        <div className="flex items-center gap-4 text-[10px] mt-0.5">
          {/* Progress Bar */}
          <div className="flex flex-col gap-1 w-full max-w-[90px]">
            <div className="flex justify-between text-muted-foreground font-semibold uppercase tracking-wider">
              <span>Progress</span>
              <span className="text-foreground">{project.durationPercentComplete || project.progress}%</span>
            </div>
            <div className="h-1.5 w-full bg-border rounded-full overflow-hidden">
              <div className="h-full bg-primary" style={{ width: `${project.durationPercentComplete || project.progress}%` }}></div>
            </div>
          </div>
          {/* SPI & CPI */}
          <div className="flex items-center gap-3 border-l border-border pl-3">
             <div className="flex flex-col">
               <span className="text-muted-foreground font-semibold uppercase tracking-wider">SPI</span>
               <span className={`font-mono font-bold text-[11px] ${project.spi < 0.95 ? 'text-amber-500' : 'text-emerald-500'}`}>{project.spi}</span>
             </div>
             <div className="flex flex-col">
               <span className="text-muted-foreground font-semibold uppercase tracking-wider">CPI</span>
               <span className={`font-mono font-bold text-[11px] ${project.cpi < 0.95 ? 'text-amber-500' : 'text-emerald-500'}`}>{project.cpi}</span>
             </div>
          </div>
        </div>
      </div>

      {/* 3. SAP Supply & Transmission Breakdown */}
      <div className="w-[30%] min-w-[250px] grid grid-cols-2 gap-x-4 gap-y-3 border-l border-border pl-5">
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">PO Volume</span>
          <span className="text-[13px] font-mono font-semibold text-foreground/80">
            {project.poVolumeMW > 0 ? `${project.poVolumeMW} MW` : '--'}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">In-Transit</span>
          <span className="text-[13px] font-mono font-semibold text-amber-500">
            {project.inTransitMW > 0 ? `${project.inTransitMW} MW` : '--'}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Inventory</span>
          <span className="text-[13px] font-mono font-semibold text-emerald-500">
            {project.inventoryMW > 0 ? `${project.inventoryMW} MW` : '--'}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Transmission</span>
          <span className="text-[13px] font-mono font-semibold text-purple-500">
            {project.tcEdgesCount > 0 ? `${project.tcEdgesCount} Assets` : 'N/A'}
          </span>
        </div>
      </div>

      {/* 4. Forecast COD & Confidence */}
      <div className="w-[15%] min-w-[150px] flex items-center justify-between border-l border-border pl-4 pr-6">
        <div className="flex flex-col gap-1">
          <span className={`text-[10px] uppercase tracking-widest font-semibold ${project.codAtRisk ? 'text-red-500/70' : 'text-muted-foreground'}`}>Forecast COD</span>
          <span className={`text-[15px] font-mono font-semibold ${project.codAtRisk ? 'text-red-500' : 'text-foreground/80'}`}>{project.forecastMonth}</span>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-semibold">AI Conf</span>
          <span className="text-[15px] font-mono font-bold text-primary">{project.confidence}%</span>
        </div>
      </div>

      {/* Action Chevron */}
      <ChevronRight className="w-5 h-5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity absolute right-4" />
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════
   SKELETON LOADER
   ═══════════════════════════════════════════════════════════ */
const SkeletonCard = () => (
  <div className="intelligence-card p-5">
    <div className="flex items-center justify-between mb-4">
      <div className="w-2/3 h-4 rounded shimmer"></div>
      <div className="w-16 h-6 rounded-lg shimmer"></div>
    </div>
    <div className="w-28 h-7 rounded-lg shimmer mb-4"></div>
    <div className="space-y-2 mb-4">
      <div className="w-3/4 h-4 rounded shimmer"></div>
      <div className="w-1/2 h-4 rounded shimmer"></div>
    </div>
    <div className="w-full h-12 rounded-lg shimmer mb-4"></div>
    <div className="flex justify-between pt-2 border-t border-border">
      <div className="w-1/3 h-3 rounded shimmer"></div>
      <div className="w-16 h-3 rounded shimmer"></div>
    </div>
  </div>
);

/* ═══════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════ */
export default function Project360({ onOpenProject }: { onOpenProject?: (id: string) => void }) {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('All');
  const [riskFilters, setRiskFilters] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<string>('impact');
  const [showFilters, setShowFilters] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetch('/akasha/api/project-360')
      .then(res => res.json())
      .then(json => setData(json))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  // ── Filtering ──
  const filtered = data
    .filter(d => {
      const matchesSearch =
        d.projectName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        d.projectId.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (d.sapPlantCode || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        (d.primaryIssue || '').toLowerCase().includes(searchTerm.toLowerCase());
      const matchesStatus = statusFilter === 'All' || d.statusTier === statusFilter;
      const matchesRisk = riskFilters.length === 0 || riskFilters.some(rf => (d.riskCategories || []).includes(rf));
      return matchesSearch && matchesStatus && matchesRisk;
    })
    .sort((a, b) => {
      switch (sortBy) {
        case 'impact': return b.riskScore - a.riskScore;
        case 'delay': return b.delayDays - a.delayDays;
        case 'cost': return a.costVariance - b.costVariance;
        case 'supply': return a.materialAvailability - b.materialAvailability;
        case 'vendor': return (b.inTransitMW === 0 && b.poVolumeMW > 0 ? 1 : 0) - (a.inTransitMW === 0 && a.poVolumeMW > 0 ? 1 : 0);
        case 'cod': return (b.codAtRisk ? 1 : 0) - (a.codAtRisk ? 1 : 0);
        case 'critical': return b.riskScore - a.riskScore;
        default: return b.riskScore - a.riskScore;
      }
    });

  // ── Status Counts ──
  const statusCounts: Record<string, number> = { Critical: 0, 'High Risk': 0, Watchlist: 0, Healthy: 0, Completed: 0 };
  data.forEach(d => { if (statusCounts[d.statusTier] !== undefined) statusCounts[d.statusTier]++; });

  const toggleRiskFilter = (rf: string) => {
    setRiskFilters(prev => prev.includes(rf) ? prev.filter(r => r !== rf) : [...prev, rf]);
  };

  const handleOpenProject = (projectId: string) => {
    if (onOpenProject) {
      onOpenProject(projectId);
    }
  };

  return (
    <div className="flex flex-col h-full w-full max-w-[1800px] mx-auto animate-in fade-in duration-500 pb-8">

      {/* ── Page Header ── */}
      <div className="flex items-end justify-between gap-4 mb-6">
        <div>
          <div className="section-label mb-1">AI-POWERED INTELLIGENCE</div>
          <h2 className="text-2xl font-light text-foreground tracking-wide flex items-center gap-3">
            <Target className="w-6 h-6 text-primary" />
            Project Intelligence
          </h2>
        </div>
        <span className="text-[11px] font-mono text-muted-foreground">
          {data.length} projects · Live Data
        </span>
      </div>

      {/* ── AI Executive Briefing ── */}
      {!loading && data.length > 0 && <AIBriefingCard data={data} />}

      {/* ── Status Tier Distribution ── */}
      <div className="flex flex-wrap gap-2.5 mb-5">
        <StatusPill tier="All" count={data.length} active={statusFilter === 'All'}
          onClick={() => setStatusFilter('All')} />
        {Object.entries(statusCounts).map(([tier, count]) => (
          <StatusPill key={tier} tier={tier} count={count} active={statusFilter === tier}
            onClick={() => setStatusFilter(statusFilter === tier ? 'All' : tier)} />
        ))}
      </div>

      {/* ── Search + Sort + Filters Bar ── */}
      <div className="flex flex-col gap-3 mb-5">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 group">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
            <input type="text" placeholder="Search by project, issue, or plant code..."
              value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
              className="w-full bg-card border border-border focus:border-primary/40 rounded-xl py-2.5 pl-10 pr-4 text-sm text-foreground placeholder-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/30 transition-all" />
          </div>

          {/* Sort */}
          <div className="flex items-center gap-2 bg-card border border-border rounded-xl px-3 py-1">
            <SlidersHorizontal className="w-3.5 h-3.5 text-muted-foreground" />
            <select value={sortBy} onChange={e => setSortBy(e.target.value)}
              className="bg-transparent text-[11px] font-semibold text-muted-foreground focus:outline-none cursor-pointer py-1.5">
              <option value="impact">Highest Impact</option>
              <option value="delay">Highest Delay Risk</option>
              <option value="cost">Highest Cost Risk</option>
              <option value="supply">Highest Supply Risk</option>
              <option value="vendor">Highest Vendor Risk</option>
              <option value="cod">Most Likely COD Miss</option>
              <option value="critical">Most Critical</option>
            </select>
          </div>

          {/* Filter Toggle */}
          <button onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-[11px] font-semibold uppercase tracking-wider border transition-all ${showFilters || riskFilters.length > 0
                ? 'bg-primary/10 text-primary border-primary/20'
                : 'bg-card text-muted-foreground border-border hover:text-foreground'
              }`}>
            <Zap className="w-3.5 h-3.5" />
            Smart Filters
            {riskFilters.length > 0 && (
              <span className="bg-primary/20 text-primary text-[9px] font-bold px-1.5 py-0.5 rounded-md">{riskFilters.length}</span>
            )}
          </button>
        </div>

        {/* ── Smart Risk Filters (Expandable) ── */}
        {showFilters && (
          <div className="flex flex-wrap gap-2 p-4 rounded-xl bg-card border border-border animate-in fade-in duration-200">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground self-center mr-2">Filter by:</span>
            {RISK_FILTER_OPTIONS.map(rf => (
              <button key={rf} onClick={() => toggleRiskFilter(rf)}
                className={`text-[11px] font-semibold px-3 py-1.5 rounded-lg border transition-all ${riskFilters.includes(rf)
                    ? 'bg-primary/15 text-primary border-primary/20'
                    : 'text-muted-foreground border-border hover:bg-muted/20 hover:text-foreground'
                  }`}>
                {rf}
              </button>
            ))}
            {riskFilters.length > 0 && (
              <button onClick={() => setRiskFilters([])} className="text-[11px] text-red-400 hover:text-red-300 transition-colors ml-2 self-center font-medium">
                Clear all
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── Results Summary ── */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] text-muted-foreground font-medium">
          Showing {filtered.length} of {data.length} projects
          {riskFilters.length > 0 && <span className="text-primary"> · {riskFilters.join(', ')}</span>}
        </span>
        {(searchTerm || riskFilters.length > 0 || statusFilter !== 'All') && (
          <button onClick={() => { setSearchTerm(''); setRiskFilters([]); setStatusFilter('All'); }}
            className="text-[11px] text-primary hover:text-primary/80 transition-colors flex items-center gap-1 font-medium">
            <X className="w-3 h-3" /> Reset all
          </button>
        )}
      </div>

      {/* ── Intelligence Card Grid ── */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-[400px] border border-dashed border-border rounded-2xl bg-card">
          <Search className="w-12 h-12 text-muted-foreground/30 mb-4" />
          <p className="text-muted-foreground text-sm">No projects match your criteria.</p>
          <button onClick={() => { setSearchTerm(''); setRiskFilters([]); setStatusFilter('All'); }}
            className="mt-3 text-xs text-primary hover:text-primary/80 transition-colors font-medium">
            Reset filters
          </button>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden mb-8">
          <div className="flex items-center px-6 py-4 bg-muted/20 border-b border-border/50 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            <div className="w-[30%] min-w-[250px]">Project Details</div>
            <div className="w-[25%] min-w-[200px]">Health & AI Driver</div>
            <div className="w-[30%] min-w-[250px] pl-5">SAP Supply & Transmission</div>
            <div className="w-[15%] min-w-[150px] pl-4">Forecast COD</div>
          </div>
          <div className="flex flex-col">
            {filtered.map((project, index) => (
              <div key={project.projectId} className="animate-in fade-in" style={{ animationDelay: `${index * 30}ms` }}>
                <ProjectRow project={project} onOpen={handleOpenProject} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
