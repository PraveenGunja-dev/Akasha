import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, Sparkles, ChevronRight, AlertTriangle, Shield,
  Clock, Package, CheckCircle2, XCircle, Eye,
  Zap, Target, Layers, Info,
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
  All: { color: 'text-gray-900', bgColor: 'bg-gray-100', borderColor: 'border-gray-200', dotClass: '', icon: Layers, label: 'All' },
  Critical: { color: 'text-red-600', bgColor: 'bg-red-50', borderColor: 'border-red-100', dotClass: 'status-dot-critical', icon: XCircle, label: 'Critical' },
  'High Risk': { color: 'text-orange-600', bgColor: 'bg-orange-50', borderColor: 'border-orange-100', dotClass: 'status-dot-warning', icon: AlertTriangle, label: 'High Risk' },
  Watchlist: { color: 'text-amber-600', bgColor: 'bg-amber-50', borderColor: 'border-amber-100', dotClass: 'status-dot-warning', icon: Eye, label: 'Watchlist' },
  Healthy: { color: 'text-emerald-600', bgColor: 'bg-emerald-50', borderColor: 'border-emerald-100', dotClass: 'status-dot-healthy', icon: Shield, label: 'Healthy' },
  Completed: { color: 'text-blue-600', bgColor: 'bg-blue-50', borderColor: 'border-blue-100', dotClass: 'status-dot-healthy', icon: CheckCircle2, label: 'Completed' },
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
      className={`relative flex items-center gap-3 px-5 py-3.5 rounded-2xl border transition-all duration-300 cursor-pointer overflow-hidden group ${active
          ? `${cfg.bgColor} ${cfg.borderColor} shadow-sm ring-1 ring-primary/20 -translate-y-1`
          : `bg-white border-gray-200 hover:border-primary/30 hover:shadow-sm hover:-translate-y-1`
        }`}>
      <div className={`absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none ${!active ? cfg.bgColor : ''}`} />
      {cfg.dotClass && <div className={`${cfg.dotClass} relative z-10`}></div>}
      <div className="text-left relative z-10">
        <div className={`text-xl font-semibold tracking-tight transition-colors ${active ? cfg.color : 'text-foreground group-hover:text-primary'}`}>{count}</div>
        <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{tier}</div>
      </div>
    </button>
  );
};

/* ═══════════════════════════════════════════════════════════
   METRIC BREAKDOWN MODAL
   ═══════════════════════════════════════════════════════════ */
const MetricBreakdownModal = ({ 
  isOpen, onClose, title, description, data, type 
}: { 
  isOpen: boolean; onClose: () => void; title: string; description: React.ReactNode; data: any[]; type: string; 
}) => {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen) return null;
  
  const sorted = [...data].sort((a, b) => {
    if (type === 'schedule') return (b.delayDays || 0) - (a.delayDays || 0);
    if (type === 'activity') return (b.integrationCount || 0) - (a.integrationCount || 0);
    if (type === 'supply') return (a.materialAvailability || 0) - (b.materialAvailability || 0);
    if (type === 'risk') return (b.riskScore || 0) - (a.riskScore || 0);
    return 0;
  });

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-4xl bg-card border border-border shadow-2xl rounded-2xl overflow-hidden flex flex-col max-h-[85vh]">
        
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border bg-muted/30">
          <div>
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <Info className="w-5 h-5 text-primary" />
              {title}
            </h3>
            <p className="text-xs text-muted-foreground mt-1">{description}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-full transition-colors">
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Table Content */}
        <div className="flex-1 min-h-0 overflow-auto p-0 custom-scrollbar" data-lenis-prevent="true">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-muted/50 sticky top-0 z-10 border-b border-border text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-6 py-3 font-semibold w-full">Project</th>
                {type === 'schedule' && (
                  <>
                    <th className="px-6 py-3 font-semibold text-right">Progress</th>
                    <th className="px-6 py-3 font-semibold text-right">SPI</th>
                    <th className="px-6 py-3 font-semibold text-right">Delay Impact</th>
                  </>
                )}

                {type === 'supply' && (
                  <>
                    <th className="px-6 py-3 font-semibold text-right">Availability</th>
                    <th className="px-6 py-3 font-semibold text-right">Ordered</th>
                    <th className="px-6 py-3 font-semibold text-right">Inventory</th>
                  </>
                )}
                {type === 'risk' && (
                  <>
                    <th className="px-6 py-3 font-semibold text-right">Risk Score</th>
                    <th className="px-6 py-3 font-semibold text-right">Confidence</th>
                    <th className="px-6 py-3 font-semibold text-right">Primary Issue</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sorted.map((p) => (
                <tr key={p.projectId} className="hover:bg-muted/30 transition-colors">
                  <td className="px-6 py-3 w-full max-w-[250px] sm:max-w-xs md:max-w-md">
                    <div className="font-semibold text-foreground truncate">{p.projectName}</div>
                    <div className="text-[10px] text-muted-foreground font-mono mt-0.5">{p.projectId}</div>
                  </td>
                  {type === 'schedule' && (
                    <>
                      <td className="px-6 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                           <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden shrink-0">
                             <div className="h-full bg-primary" style={{ width: `${Math.round((p.progress || 0) * 100)}%` }} />
                           </div>
                           <span className="font-mono text-xs">{Math.round((p.progress || 0) * 100)}%</span>
                        </div>
                      </td>
                      <td className={`px-6 py-3 font-mono text-xs text-right ${p.spi < 0.95 ? 'text-amber-500 font-bold' : 'text-emerald-500'}`}>{(p.spi || 0).toFixed(2)}</td>
                      <td className={`px-6 py-3 font-mono text-xs text-right ${p.delayDays > 0 ? 'text-red-500 font-bold' : 'text-emerald-500'}`}>{p.delayDays || 0}d</td>
                    </>
                  )}

                  {type === 'supply' && (
                    <>
                      <td className={`px-6 py-3 font-mono text-xs text-right ${p.materialAvailability < 80 ? 'text-amber-500 font-bold' : 'text-emerald-500'}`}>{Math.round(p.materialAvailability || 0)}%</td>
                      <td className="px-6 py-3 font-mono text-xs text-right">{fmtNum(p.orderedQty || 0)}</td>
                      <td className="px-6 py-3 font-mono text-xs text-right text-emerald-500">{fmtNum(p.inventoryQty || 0)}</td>
                    </>
                  )}
                  {type === 'risk' && (
                    <>
                      <td className={`px-6 py-3 font-mono text-xs text-right ${p.riskScore > 70 ? 'text-red-500 font-bold' : p.riskScore > 40 ? 'text-amber-500' : 'text-emerald-500'}`}>{Math.round(p.riskScore || 0)}/100</td>
                      <td className="px-6 py-3 font-mono text-xs text-right text-primary">{Math.round(p.confidence || 0)}%</td>
                      <td className="px-6 py-3 text-right"><span className="bg-muted px-2 py-1 rounded text-[10px] font-semibold text-foreground">{p.primaryIssue || 'On Track'}</span></td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════
   PORTFOLIO BRIEFING CARD
   ═══════════════════════════════════════════════════════════ */
const PortfolioBriefingCard = ({ data }: { data: any[] }) => {
  const [activeModal, setActiveModal] = useState<string | null>(null);

  if (!data || data.length === 0) return null;

  // Exact Metrics without fallbacks
  const totalCapacity = data.reduce((s, d) => s + d.capacityMW, 0);
  const avgSPI = (data.reduce((s, d) => s + d.spi, 0) / data.length).toFixed(2);
  const avgCPI = (data.reduce((s, d) => s + d.cpi, 0) / data.length).toFixed(2);
  const totalCostVariance = data.reduce((s, d) => s + d.costVariance, 0);
  const totalInProgress = data.reduce((s, d) => s + (d.inProgressActivities || 0), 0);
  
  const avgMaterial = Math.round(data.reduce((s, d) => s + d.materialAvailability, 0) / data.length);
  const totalOrdered = data.reduce((s, d) => s + d.orderedQty, 0);
  const totalInTransit = data.reduce((s, d) => s + d.inTransitQty, 0);
  const totalInventory = data.reduce((s, d) => s + d.inventoryQty, 0);

  const avgRisk = Math.round(data.reduce((s, d) => s + d.riskScore, 0) / data.length);
  const totalIntegration = data.reduce((s, d) => s + (d.integrationCount || d.tcEdgesCount), 0);
  const avgConfidence = Math.round(data.reduce((s, d) => s + d.confidence, 0) / data.length);

  const avgProgress = Math.round((data.reduce((s, d) => s + (d.progress || 0), 0) / data.length) * 100);
  const delayedProjects = data.filter(d => d.delayDays > 0);
  const totalDelayDays = delayedProjects.reduce((s, d) => s + d.delayDays, 0);
  const codAtRiskCount = data.filter(d => d.codAtRisk).length;

  return (
    <>
      <MetricBreakdownModal 
        isOpen={activeModal !== null} 
        onClose={() => setActiveModal(null)}
        type={activeModal || 'schedule'}
        data={data}
        title={
          activeModal === 'schedule' ? 'Schedule & Progress Breakdown' :
          activeModal === 'activity' ? 'Activity & Transmission Breakdown' :
          activeModal === 'supply' ? 'Material & Supply Chain Breakdown' :
          'Risk & Complexity Breakdown'
        }
        description={
          activeModal === 'schedule' ? 'Calculated by aggregating Primavera P6 baseline vs actual schedule variances.' :
          activeModal === 'activity' ? 'Aggregated Transmission lines, delayed projects, and in-progress activities.' :
          activeModal === 'supply' ? 'Aggregated from SAP logistics data (PO Ordered vs Transit vs Site Inventory).' :
          'Calculated via Akasha AI Risk Engine based on schedule, cost, and historical supplier performance.'
        }
      />
      <div className="bento-card relative overflow-hidden group transition-all duration-300 mb-8 p-0">
      <div className="relative z-10">
        {/* Header Bar */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-gray-100 dark:border-gray-800">
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-primary to-purple-600 flex items-center justify-center shadow-md shadow-primary/20 transition-transform duration-300 group-hover:scale-105 group-hover:-rotate-3">
              <Target className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2 tracking-tight">
                Portfolio Briefing
                <span className="text-[10px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider border border-emerald-500/20 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> Live
                </span>
              </h3>
              <p className="text-[10px] text-muted-foreground mt-0.5">Powered by Akasha Platform · {fmtMW(totalCapacity)} Total Portfolio</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground bg-muted/50 px-3 py-1.5 rounded-full border border-border">
              <span>Confidence:</span>
              <span className="font-mono font-bold text-primary">{avgConfidence}%</span>
            </div>
          </div>
        </div>

        {/* 3-Column Performance Matrix */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-0 md:divide-x divide-y md:divide-y-0 xl:divide-y-0 divide-border/30">
          
          {/* Column 1: Schedule & Progress */}
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Schedule & Progress</div>
              <button onClick={() => setActiveModal('schedule')} className="text-muted-foreground hover:text-primary transition-colors bg-muted/50 hover:bg-primary/10 rounded-md p-1 border border-transparent hover:border-primary/20">
                <Info className="w-3.5 h-3.5" />
              </button>
            </div>
            
            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 border border-gray-100 dark:border-gray-800 space-y-4">
              {/* Overall Progress */}
              <div className="flex flex-col gap-1.5">
                <div className="flex justify-between text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                  <span>Overall Progress</span>
                  <span className="text-foreground">{avgProgress}%</span>
                </div>
                <div className="h-2 w-full bg-border/50 rounded-full overflow-hidden">
                  <div className="h-full bg-primary" style={{ width: `${avgProgress}%` }}></div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2 border-t border-gray-200 dark:border-gray-700">
                <div>
                  <div className="text-[9px] font-bold uppercase tracking-widest text-gray-500 mb-1">Avg SPI</div>
                  <div className={`text-xl font-mono font-bold ${parseFloat(avgSPI) < 0.95 ? 'text-amber-500' : 'text-emerald-500'}`}>{avgSPI}</div>
                </div>
                <div>
                  <div className="text-[9px] font-bold uppercase tracking-widest text-gray-500 mb-1">Delay Impact</div>
                  <div className={`text-xl font-mono font-bold ${totalDelayDays > 0 ? 'text-red-500' : 'text-emerald-500'}`}>{totalDelayDays}d</div>
                </div>
              </div>
            </div>
          </div>



          {/* Column 3: Material & Supply Chain */}
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Material & Supply Chain</div>
              <button onClick={() => setActiveModal('supply')} className="text-muted-foreground hover:text-primary transition-colors bg-muted/50 hover:bg-primary/10 rounded-md p-1 border border-transparent hover:border-primary/20">
                <Info className="w-3.5 h-3.5" />
              </button>
            </div>
            
            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 border border-gray-100 dark:border-gray-800 space-y-4">
              <div className="flex flex-col gap-1.5">
                <div className="flex justify-between text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                  <span>Material Availability</span>
                  <span className="text-foreground">{avgMaterial}%</span>
                </div>
                <div className="h-2 w-full bg-border/50 rounded-full overflow-hidden">
                  <div className={`h-full ${avgMaterial < 80 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${avgMaterial}%` }}></div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Ordered</span>
                  <span className="text-sm font-mono font-semibold text-foreground/80">{fmtNum(totalOrdered)}</span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Transit</span>
                  <span className="text-sm font-mono font-semibold text-amber-500">{fmtNum(totalInTransit)}</span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Inventory</span>
                  <span className="text-sm font-mono font-semibold text-emerald-500">{fmtNum(totalInventory)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Column 4: Risk & Complexity */}
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Risk & Complexity</div>
              <button onClick={() => setActiveModal('risk')} className="text-muted-foreground hover:text-primary transition-colors bg-muted/50 hover:bg-primary/10 rounded-md p-1 border border-transparent hover:border-primary/20">
                <Info className="w-3.5 h-3.5" />
              </button>
            </div>
            
            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 border border-gray-100 dark:border-gray-800 space-y-4">
              <div className="flex flex-col gap-1.5">
                <div className="text-[9px] font-bold uppercase tracking-widest text-gray-500 mb-1">Avg Risk Score</div>
                <div className={`text-2xl font-mono font-bold tracking-tight ${avgRisk > 70 ? 'text-red-500' : avgRisk > 40 ? 'text-amber-500' : 'text-emerald-500'}`}>
                  {avgRisk}/100
                </div>
                <div className="text-[10px] text-muted-foreground">Aggregated portfolio risk</div>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2 border-t border-gray-200 dark:border-gray-700">
                <div>
                  <div className="text-[9px] font-bold uppercase tracking-widest text-gray-500 mb-1">Integrations</div>
                  <div className="text-xl font-mono font-bold text-purple-500">{fmtNum(totalIntegration)}</div>
                </div>
                <div>
                  <div className="text-[9px] font-bold uppercase tracking-widest text-gray-500 mb-1">Confidence</div>
                  <div className="text-xl font-mono font-bold text-primary">{avgConfidence}%</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      </div>
    </>
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

  return (
    <div
      onClick={() => onOpen(project.projectId)}
      className="group relative flex items-center justify-between px-6 py-4 bg-white dark:bg-gray-900 hover:bg-gray-50/80 dark:hover:bg-gray-800/80 border-b border-gray-100 dark:border-gray-800 cursor-pointer transition-colors duration-200"
    >
      <div className="absolute inset-0 opacity-0 group-hover:opacity-5 transition-opacity duration-300 pointer-events-none" style={{ backgroundColor: accentColor }} />
      <div className="absolute left-0 top-0 bottom-0 w-[3px] opacity-0 group-hover:opacity-100 transition-opacity" style={{ backgroundColor: accentColor }}></div>

      {/* 1. Project Details (35%) */}
      <div className="flex flex-col gap-1.5 w-[35%] min-w-[250px] pr-4">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-semibold text-foreground/90 group-hover:text-primary transition-colors truncate">
            {project.projectName}
          </h3>
          <div className={`w-2 h-2 rounded-full shrink-0 ${statusCfg.bgColor}`} style={{ backgroundColor: accentColor, boxShadow: `0 0 6px ${accentColor}80` }}></div>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
           <span className="bg-muted px-1.5 py-0.5 rounded text-foreground/80 font-semibold">{project.capacityMW} MW</span>
           <span className="opacity-80 border-l border-border pl-2">SPV: {project.sapPlantCode}</span>
           <span className="opacity-80 border-l border-border pl-2">P6: {project.projectId}</span>
        </div>
      </div>



      {/* 2. Schedule Performance (25%) */}
      <div className="w-[25%] min-w-[150px] flex flex-col gap-1.5 border-l border-border pl-4 pr-4">
        <div className="flex flex-col gap-1 w-full max-w-[120px]">
          <div className="flex justify-between text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">
            <span>Progress</span>
            <span className="text-foreground">{Math.round((project.progress || 0) * 100)}%</span>
          </div>
          <div className="h-1.5 w-full bg-border rounded-full overflow-hidden">
            <div className="h-full bg-primary" style={{ width: `${Math.round((project.progress || 0) * 100)}%` }}></div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[9px] mt-0.5 text-muted-foreground font-mono">
           <span>P:{Math.round((project.plannedDuration || 0) / 8)}d</span>
           <span>A:{Math.round((project.actualDuration || 0) / 8)}d</span>
           <span>R:{Math.round((project.remainingDuration || 0) / 8)}d</span>
        </div>
      </div>

      {/* 3. Supply Funnel (25%) */}
      <div className="w-[25%] min-w-[180px] flex flex-col justify-center border-l border-border pl-4 pr-4 py-0.5">
        <div className="flex justify-between items-center text-[10px] mb-0.5">
          <span className="text-muted-foreground uppercase tracking-widest font-semibold">Ordered</span>
          <span className="font-mono font-semibold text-foreground/80">{fmtNum(project.orderedQty)}</span>
        </div>
        <div className="flex justify-between items-center text-[10px] mb-0.5">
          <span className="text-muted-foreground uppercase tracking-widest font-semibold">Consumed</span>
          <span className="font-mono font-semibold text-emerald-500">{fmtNum(project.consumedQty)}</span>
        </div>
        <div className="flex justify-between items-center text-[10px]">
          <span className="text-muted-foreground uppercase tracking-widest font-semibold">Pending</span>
          <span className="font-mono font-semibold text-amber-500">{fmtNum(project.pendingDispatchQty)}</span>
        </div>
      </div>

      {/* 5. Timeline Forecast (15%) */}
      <div className="w-[15%] min-w-[150px] flex items-center justify-between border-l border-border pl-4 pr-6">
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold w-12">Base</span>
            <span className="text-[11px] font-mono font-semibold text-foreground/60">{project.baselineMonth || 'N/A'}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[9px] uppercase tracking-widest font-semibold w-12 ${project.codAtRisk ? 'text-red-500/70' : 'text-primary/70'}`}>Fcst</span>
            <span className={`text-[13px] font-mono font-bold ${project.codAtRisk ? 'text-red-500' : 'text-foreground/90'}`}>{project.forecastMonth}</span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-0.5 ml-2">
          <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Conf</span>
          <span className="text-[13px] font-mono font-bold text-primary">{project.confidence}%</span>
        </div>
      </div>

      <ChevronRight className="w-5 h-5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity absolute right-4" />
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════
   SKELETON LOADER
   ═══════════════════════════════════════════════════════════ */
const SkeletonRow = () => (
  <div className="flex items-stretch border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900/40 animate-pulse">
    <div className="w-[30%] min-w-[250px] p-4 flex items-start gap-3">
      <div className="flex-1 mt-1">
        <div className="w-3/4 h-5 bg-gray-200 dark:bg-gray-800 rounded mb-2"></div>
        <div className="w-1/2 h-4 bg-gray-200 dark:bg-gray-800 rounded"></div>
      </div>
    </div>
    <div className="w-[20%] min-w-[180px] border-l border-border p-4 flex flex-col justify-center gap-2">
      <div className="w-full h-3 bg-gray-200 dark:bg-gray-800 rounded"></div>
      <div className="w-full h-3 bg-gray-200 dark:bg-gray-800 rounded"></div>
      <div className="w-full h-3 bg-gray-200 dark:bg-gray-800 rounded"></div>
    </div>
    <div className="w-[15%] min-w-[150px] border-l border-border p-4 flex flex-col justify-center">
      <div className="w-full h-2 bg-gray-200 dark:bg-gray-800 rounded-full mb-3"></div>
      <div className="w-20 h-3 bg-gray-200 dark:bg-gray-800 rounded"></div>
    </div>
    <div className="w-[20%] min-w-[180px] border-l border-border p-4 flex flex-col justify-center gap-2">
      <div className="w-full h-3 bg-gray-200 dark:bg-gray-800 rounded"></div>
      <div className="w-full h-3 bg-gray-200 dark:bg-gray-800 rounded"></div>
      <div className="w-full h-3 bg-gray-200 dark:bg-gray-800 rounded"></div>
    </div>
    <div className="w-[15%] min-w-[150px] flex items-center justify-between border-l border-border pl-4 pr-6">
      <div className="flex flex-col gap-2">
        <div className="w-16 h-3 bg-gray-200 dark:bg-gray-800 rounded"></div>
        <div className="w-16 h-4 bg-gray-200 dark:bg-gray-800 rounded"></div>
      </div>
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
  const [sortBy, setSortBy] = useState<string>('integration');
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
        d.sapPlantCode.toLowerCase().includes(searchTerm.toLowerCase()) ||
        d.primaryIssue.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesStatus = statusFilter === 'All' || d.statusTier === statusFilter;
      const matchesRisk = riskFilters.length === 0 || riskFilters.some(rf => d.riskCategories.includes(rf));
      return matchesSearch && matchesStatus && matchesRisk;
    })
    .sort((a, b) => {
      switch (sortBy) {
        case 'integration': return b.integrationCount - a.integrationCount || b.riskScore - a.riskScore;
        case 'impact': return b.riskScore - a.riskScore;
        case 'delay': return b.delayDays - a.delayDays;
        case 'cost': return a.costVariance - b.costVariance;
        case 'supply': return a.materialAvailability - b.materialAvailability;
        case 'vendor': return (b.inTransitQty === 0 && b.orderedQty > 0 ? 1 : 0) - (a.inTransitQty === 0 && a.orderedQty > 0 ? 1 : 0);
        case 'cod': return (b.codAtRisk ? 1 : 0) - (a.codAtRisk ? 1 : 0);
        case 'critical': return b.riskScore - a.riskScore;
        default: return b.integrationCount - a.integrationCount || b.riskScore - a.riskScore;
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
          <div className="section-label mb-1">PORTFOLIO INTELLIGENCE</div>
          <h2 className="text-2xl font-light text-foreground tracking-wide flex items-center gap-3">
            <Target className="w-6 h-6 text-primary" />
            Project Intelligence
          </h2>
        </div>
        <span className="text-[11px] font-mono text-muted-foreground">
          {data.length} projects · Live Data
        </span>
      </div>

      {/* ── Executive Briefing ── */}
      {!loading && data.length > 0 && <PortfolioBriefingCard data={data} />}

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
              <option value="integration">Most Integrated</option>
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
        <div className="bento-card overflow-hidden mb-8 p-0">
          <div className="flex items-center px-6 py-3 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-800 text-[11px] font-bold uppercase tracking-[0.08em] text-gray-500">
            <div className="w-[30%] min-w-[250px] pr-4">Project Details</div>
            <div className="w-[20%] min-w-[180px] pl-4">Activity & Trans.</div>
            <div className="w-[15%] min-w-[150px] pl-4">Schedule</div>
            <div className="w-[20%] min-w-[180px] pl-4">Supply Chain</div>
            <div className="w-[15%] min-w-[150px] pl-4">Timeline Forecast</div>
          </div>
          <div className="flex flex-col">
            {[...Array(6)].map((_, i) => <SkeletonRow key={i} />)}
          </div>
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
        <div className="bento-card overflow-hidden mb-8 p-0">
          <div className="flex items-center px-6 py-3 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-800 text-[11px] font-bold uppercase tracking-[0.08em] text-gray-500">
            <div className="w-[30%] min-w-[250px] pr-4">Project Details</div>
            <div className="w-[20%] min-w-[180px] pl-4">Activity & Trans.</div>
            <div className="w-[15%] min-w-[150px] pl-4">Schedule</div>
            <div className="w-[20%] min-w-[180px] pl-4">Supply Chain</div>
            <div className="w-[15%] min-w-[150px] pl-4">Timeline Forecast</div>
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
