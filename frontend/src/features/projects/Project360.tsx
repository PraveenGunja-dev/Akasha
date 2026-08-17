import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Search, Sparkles, ChevronRight, AlertTriangle, Shield,
  Clock, Package, CheckCircle2, XCircle, Eye,
  Zap, Target, Layers, Info,
  Brain, Truck, DollarSign, Users,
  CalendarClock, Factory, SlidersHorizontal, X, Bell
} from 'lucide-react';

/* ═══════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════ */
const fmtNum = (n: number): string => {
  if (n == null || isNaN(n)) return '0';
  if (n >= 10000000) return `${(n / 10000000).toFixed(1).replace(/\.0$/, '')} Cr`;
  if (n >= 100000) return `${(n / 100000).toFixed(1).replace(/\.0$/, '')} L`;
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}K`;
  return Number.isInteger(n) ? n.toString() : n.toFixed(1);
};

const fmtMW = (n: number): string => {
  if (n == null || isNaN(n)) return '0 MW';
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')} GW`;
  return `${n.toFixed(1).replace(/\.0$/, '')} MW`;
};

/* ═══════════════════════════════════════════════════════════
   STATUS TIER CONFIGURATION
   ═══════════════════════════════════════════════════════════ */
const STATUS_CONFIG: Record<string, { color: string; bgColor: string; borderColor: string; dotClass: string; icon: any; label: string }> = {
  All: { color: 'text-foreground', bgColor: 'bg-muted', borderColor: 'border-border', dotClass: '', icon: Layers, label: 'All' },
  Critical: { color: 'text-destructive', bgColor: 'bg-destructive/10', borderColor: 'border-destructive/20', dotClass: 'status-dot-critical', icon: XCircle, label: 'Critical' },
  'High Risk': { color: 'text-warning', bgColor: 'bg-warning/10', borderColor: 'border-warning/20', dotClass: 'status-dot-warning', icon: AlertTriangle, label: 'High Risk' },
  Watchlist: { color: 'text-warning', bgColor: 'bg-warning/10', borderColor: 'border-warning/20', dotClass: 'status-dot-warning', icon: Eye, label: 'Watchlist' },
  Healthy: { color: 'text-success', bgColor: 'bg-success/10', borderColor: 'border-success/20', dotClass: 'status-dot-healthy', icon: Shield, label: 'Healthy' },
  Completed: { color: 'text-primary', bgColor: 'bg-primary/10', borderColor: 'border-primary/20', dotClass: 'status-dot-healthy', icon: CheckCircle2, label: 'Completed' },
};

const ISSUE_CONFIG: Record<string, { icon: any; color: string; bg: string }> = {
  'Material Bottleneck': { icon: Package, color: 'text-destructive', bg: '' },
  'Vendor Delay': { icon: Truck, color: 'text-purple-500', bg: '' },
  'Schedule Slippage': { icon: Clock, color: 'text-warning', bg: '' },
  'Cost Overrun': { icon: DollarSign, color: 'text-pink-500', bg: '' },
  'Procurement Gap': { icon: Factory, color: 'text-warning', bg: '' },
  'Resource Shortage': { icon: Users, color: 'text-cyan-500', bg: '' },
  'Engineering Delay': { icon: CalendarClock, color: 'text-yellow-500', bg: '' },
  'On Track': { icon: CheckCircle2, color: 'text-success', bg: '' },
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
      className={`relative flex items-center gap-3 px-6 py-4 rounded-2xl border transition-all duration-300 cursor-pointer overflow-hidden group ${active
          ? `${cfg.bgColor} ${cfg.borderColor} shadow-card ring-2 ring-primary/20 -translate-y-1 scale-[1.02]`
          : `bg-card border-border hover:border-primary/30 hover:shadow-card-hover hover:-translate-y-1`
        }`}>
      <div className={`absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none ${!active ? cfg.bgColor : ''}`} />
      {cfg.dotClass && <div className={`${cfg.dotClass} relative z-10`}></div>}
      <div className="text-left relative z-10">
        <div className={`text-2xl font-bold tracking-tight transition-colors ${active ? cfg.color : 'text-foreground group-hover:text-primary'}`}>{count}</div>
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
    if (type === 'transmission') return (b.tcEdgesCount || 0) - (a.tcEdgesCount || 0);
    if (type === 'critical') return (b.delayedActivities || 0) - (a.delayedActivities || 0);
    return 0;
  });

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-5xl bg-card border border-border shadow-2xl rounded-2xl overflow-hidden flex flex-col max-h-[85vh]">
        
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border bg-muted">
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
        <div className="flex-1 min-h-0 overflow-auto p-0 custom-scrollbar">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-muted sticky top-0 z-10 border-b border-border text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-6 py-3 font-semibold w-full">Project</th>
                {type === 'schedule' && (
                  <>
                    <th className="px-6 py-3 font-semibold text-right">Progress</th>
                    <th className="px-6 py-3 font-semibold text-right">NCs</th>
                    <th className="px-6 py-3 font-semibold text-right">RFIs</th>
                    <th className="px-6 py-3 font-semibold text-right">Delay Impact</th>
                  </>
                )}

                {type === 'activity' && (
                  <>
                    <th className="px-6 py-3 font-semibold text-right">Lines Charged</th>
                    <th className="px-6 py-3 font-semibold text-right">Foundation</th>
                    <th className="px-6 py-3 font-semibold text-right">Delayed</th>
                  </>
                )}

                {type === 'supply' && (
                  <>
                    <th className="px-6 py-3 font-semibold text-right">Availability</th>
                    <th className="px-6 py-3 font-semibold text-right">Ordered</th>
                    <th className="px-6 py-3 font-semibold text-right">Inventory</th>
                  </>
                )}
                {type === 'transmission' && (
                  <>
                    <th className="px-6 py-3 font-semibold text-right">Total Lines</th>
                    <th className="px-6 py-3 font-semibold text-right">Charged</th>
                    <th className="px-6 py-3 font-semibold text-right">Delayed</th>
                  </>
                )}
                {type === 'critical' && (
                  <>
                    <th className="px-6 py-3 font-semibold text-right">Critical Activities</th>
                    <th className="px-6 py-3 font-semibold text-right">Completing This Mo.</th>
                    <th className="px-6 py-3 font-semibold text-right">Delayed</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sorted.map((p) => (
                <tr key={p.projectId} className="hover:bg-muted transition-colors">
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
                      <td className={`px-6 py-3 font-mono text-xs text-right ${(p.ncCount || 0) > 0 ? 'text-warning font-bold' : 'text-success'}`}>{p.ncCount || 0}</td>
                      <td className={`px-6 py-3 font-mono text-xs text-right ${(p.rfiCount || 0) > 0 ? 'text-primary font-bold' : 'text-muted-foreground'}`}>{p.rfiCount || 0}</td>
                      <td className={`px-6 py-3 font-mono text-xs text-right ${p.delayDays > 0 ? 'text-destructive font-bold' : 'text-success'}`}>{p.delayDays || 0}d</td>
                    </>
                  )}

                  {type === 'activity' && (
                    <>
                      <td className="px-6 py-3 font-mono text-xs text-right">
                        <span className="text-primary font-bold">{p.tcData?.progress?.linesCharged?.count || 0}</span>
                        <span className="text-muted-foreground"> / {p.tcData?.progress?.linesCharged?.total || 0}</span>
                      </td>
                      <td className="px-6 py-3 font-mono text-xs text-right">
                        <span className="text-warning font-bold">{p.tcData?.progress?.foundation?.percent || 0}%</span>
                      </td>
                      <td className={`px-6 py-3 font-mono text-xs text-right ${p.tcData?.progress?.delayed?.count > 0 ? 'text-destructive font-bold' : 'text-success'}`}>
                        {p.tcData?.progress?.delayed?.count || 0}
                      </td>
                    </>
                  )}

                  {type === 'supply' && (
                    <>
                      <td className={`px-6 py-3 font-mono text-xs text-right ${p.materialAvailability < 80 ? 'text-warning font-bold' : 'text-success'}`}>{Math.round(p.materialAvailability || 0)}%</td>
                      <td className="px-6 py-3 font-mono text-xs text-right">{fmtNum(p.orderedQty || 0)}</td>
                      <td className="px-6 py-3 font-mono text-xs text-right text-success">{fmtNum(p.inventoryQty || 0)}</td>
                    </>
                  )}
                  {type === 'transmission' && (
                    <>
                      <td className="px-6 py-3 font-mono text-xs text-right">{p.tcEdgesCount || 0}</td>
                      <td className="px-6 py-3 font-mono text-xs text-right text-success font-bold">{p.tcData?.progress?.linesCharged?.count || 0}</td>
                      <td className={`px-6 py-3 font-mono text-xs text-right ${(p.tcData?.progress?.delayed?.count || 0) > 0 ? 'text-destructive font-bold' : 'text-success'}`}>{p.tcData?.progress?.delayed?.count || 0}</td>
                    </>
                  )}
                  {type === 'critical' && (
                    <>
                      <td className="px-6 py-3 font-mono text-xs text-right">{p.criticalActivityCount || 0}</td>
                      <td className="px-6 py-3 font-mono text-xs text-right text-primary font-bold">{p.activitiesCompletingThisMonth || 0}</td>
                      <td className={`px-6 py-3 font-mono text-xs text-right ${(p.delayedActivities || 0) > 0 ? 'text-destructive font-bold' : 'text-success'}`}>{p.delayedActivities || 0}</td>
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

  // ── P6 Schedule Metrics ──
  const totalCapacity = data.reduce((s, d) => s + d.capacityMW, 0);
  const avgProgress = Math.round((data.reduce((s, d) => s + (d.progress || 0), 0) / data.length) * 100);
  const delayedProjects = data.filter(d => d.delayDays > 0);
  const avgDelayDays = delayedProjects.length > 0 ? Math.round(delayedProjects.reduce((s, d) => s + d.delayDays, 0) / delayedProjects.length) : 0;
  const totalInProgressAct = data.reduce((s, d) => s + (d.inProgressActivities || 0), 0);
  const completedProjects = data.filter(d => { const p = d.progress || 0; return (p >= 0.99) || (p >= 99); }).length;
  const totalNCs = data.reduce((s, d) => s + (d.ncCount || 0), 0);
  const totalRFIs = data.reduce((s, d) => s + (d.rfiCount || 0), 0);
  
  // ── Monthly Completion Forecast ──
  const now = new Date();
  const thisMonth = now.getMonth();
  const thisYear = now.getFullYear();
  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const completingThisMonth = data.reduce((s, d) => s + (d.activitiesCompletingThisMonth || 0), 0);
  const nextMonthIdx = (thisMonth + 1) % 12;
  const completingNextMonth = data.reduce((s, d) => s + (d.activitiesCompletingNextMonth || 0), 0);
  const completingLater = data.reduce((s, d) => s + (d.activitiesCompletingLater || 0), 0);
  
  const completedCriticalActivities = data.reduce((s, d) => s + (d.completedCriticalActivities || 0), 0);
  const delayedActivities = data.reduce((s, d) => s + (d.delayedActivities || 0), 0);
  const totalActivities = data.reduce((s, d) => s + (d.criticalActivityCount || 0), 0) || 1; // fallback to 1 to prevent division by zero

  // ── SAP Material Metrics ──
  const avgMaterial = Math.round(data.reduce((s, d) => s + d.materialAvailability, 0) / data.length);
  const totalOrdered = data.reduce((s, d) => s + d.orderedQty, 0);
  const totalInTransit = data.reduce((s, d) => s + d.inTransitQty, 0);
  const totalInventory = data.reduce((s, d) => s + d.inventoryQty, 0);
  const totalConsumed = data.reduce((s, d) => s + Math.abs(d.consumedQty || 0), 0);
  const totalPending = data.reduce((s, d) => s + (d.pendingDispatchQty || 0), 0);


  // ── Transmission Metrics ──
  const uniqueLinesMap = new Map();
  data.forEach(d => {
    if (d.tcData && d.tcData.lines) {
      d.tcData.lines.forEach((line: any) => {
        if (line.id && !uniqueLinesMap.has(line.id)) {
          uniqueLinesMap.set(line.id, line);
        }
      });
    }
  });
  
  const uniqueLines = Array.from(uniqueLinesMap.values());
  // Fallback to simple sum if unique lines aren't fully populated yet
  const totalTCLines = uniqueLines.length > 0 ? uniqueLines.length : data.reduce((s, d) => s + (d.tcEdgesCount || 0), 0);
  const totalCharged = uniqueLines.length > 0 ? uniqueLines.filter(l => l.status === 'Charged').length : data.reduce((s, d) => s + (d.tcData?.progress?.linesCharged?.count || 0), 0);
  const totalTCDelayed = uniqueLines.length > 0 ? uniqueLines.filter(l => l.is_delayed).length : data.reduce((s, d) => s + (d.tcData?.progress?.delayed?.count || 0), 0);
  const totalInProgressTC = Math.max(0, totalTCLines - totalCharged - totalTCDelayed);
  const chargedPct = totalTCLines > 0 ? Math.round((totalCharged / totalTCLines) * 100) : 0;

  return (
    <>
      <MetricBreakdownModal 
        isOpen={activeModal !== null} 
        onClose={() => setActiveModal(null)}
        type={activeModal || 'schedule'}
        data={data}
        title={
          activeModal === 'schedule' ? 'Schedule & Quality Breakdown' :
          activeModal === 'supply' ? 'Material & Supply Chain Breakdown' :
          activeModal === 'transmission' ? 'Transmission Lines Breakdown' :
          'Critical Activities Breakdown'
        }
        description={
          activeModal === 'schedule' ? 'Calculated by aggregating Primavera P6 schedule variances along with Quality (NCs) and Documentation (RFIs) data.' :
          activeModal === 'supply' ? 'Aggregated from SAP logistics data (ZSPS Ordered vs In-Transit vs MB52 Inventory).' :
          activeModal === 'transmission' ? 'Transmission line connectivity data showing charged, in-progress, and delayed lines per project.' :
          'Breakdown of critical path activities, forecasting upcoming completions and current delays from P6.'
        }
      />
      <div className="bento-card relative overflow-hidden group transition-all duration-300 mb-8 p-0">
      <div className="relative z-10">
        {/* Header Bar */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-muted dark:border-border">
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-primary to-purple-600 flex items-center justify-center shadow-md shadow-primary/20 transition-transform duration-300 group-hover:scale-105 group-hover:-rotate-3">
              <Target className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2 tracking-tight">
                Portfolio Briefing
                <span className="text-[10px] bg-success/10 text-success dark:text-success px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider border border-success/20 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-success/100 animate-pulse"></span> Live
                </span>
              </h3>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground bg-muted px-3 py-1.5 rounded-full border border-border">
              <span>{data.length} Projects</span>
              <span className="text-primary font-bold">·</span>
              <span className="font-mono font-bold text-success">{completedProjects} Done</span>
            </div>
          </div>
        </div>

        {/* 3-Column Performance Matrix */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-0 md:divide-x divide-y md:divide-y-0 xl:divide-y-0 divide-border/30">
          
          {/* Column 1: Schedule & Progress */}
          <div className="p-6 space-y-6 relative hover:bg-muted/30 transition-colors">
            <div className="flex items-center justify-between">
              <div className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-primary" /> P6 Schedule
              </div>
              <button onClick={() => setActiveModal('schedule')} className="text-muted-foreground hover:text-primary transition-colors">
                <Info className="w-4 h-4" />
              </button>
            </div>
            
            <div className="grid grid-cols-3 gap-2">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1.5">Avg Progress</div>
                <div className="text-2xl tracking-tight text-primary">{avgProgress}%</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1.5">Total NCs</div>
                <div className="text-2xl tracking-tight text-warning">{fmtNum(totalNCs)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1.5">Total RFIs</div>
                <div className="text-2xl tracking-tight text-primary">{fmtNum(totalRFIs)}</div>
              </div>
            </div>
            <div className="pt-6 border-t border-border/50 flex justify-between items-end">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">In-Progress Activities</span>
              <span className="text-lg font-medium text-foreground">{fmtNum(totalInProgressAct)}</span>
            </div>
          </div>

          {/* Column 2: Material & Supply Chain */}
          <div className="p-6 space-y-6 relative hover:bg-muted/30 transition-colors">
            <div className="flex items-center justify-between">
              <div className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-warning" /> SAP Pipeline
              </div>
              <button onClick={() => setActiveModal('supply')} className="text-muted-foreground hover:text-primary transition-colors">
                <Info className="w-4 h-4" />
              </button>
            </div>
            
            <div className="grid grid-cols-3 gap-x-2 gap-y-6">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Ordered</div>
                <div className="text-[17px] text-foreground/80">{fmtNum(totalOrdered)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Consumed</div>
                <div className="text-[17px] text-success">{fmtNum(totalConsumed)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Inventory</div>
                <div className="text-[17px] text-primary">{fmtNum(totalInventory)}</div>
              </div>
              
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Transit</div>
                <div className="text-[17px] text-warning">{fmtNum(totalInTransit)}</div>
              </div>
              <div className="col-span-2">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Pending</div>
                <div className="text-[17px] text-destructive">{fmtNum(totalPending)}</div>
              </div>
            </div>
          </div>

          {/* Column 3: Transmission Lines */}
          <div className="p-6 space-y-6 relative hover:bg-muted/30 transition-colors">
            <div className="flex items-center justify-between">
              <div className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-success" /> Transmission
              </div>
              <button onClick={() => setActiveModal('transmission')} className="text-muted-foreground hover:text-primary transition-colors">
                <Info className="w-4 h-4" />
              </button>
            </div>
            
            <div className="grid grid-cols-3 gap-2">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Charged</div>
                <div className="text-[22px] text-success tracking-tight">{fmtNum(totalCharged)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">In Prog.</div>
                <div className="text-[22px] text-warning tracking-tight">{fmtNum(totalInProgressTC)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Delayed</div>
                <div className={`text-[22px] tracking-tight ${totalTCDelayed > 0 ? 'text-destructive' : 'text-success'}`}>{fmtNum(totalTCDelayed)}</div>
              </div>
            </div>
            
            <div className="pt-6 border-t border-border/50 flex justify-between items-end">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">Total Lines</span>
              <span className="text-lg font-medium text-foreground">{fmtNum(totalTCLines)}</span>
            </div>
          </div>

          {/* Column 4: Completion Forecast */}
          <div className="p-6 space-y-6 relative hover:bg-muted/30 transition-colors">
            <div className="flex items-center justify-between">
              <div className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-purple-500" /> Critical Activities
              </div>
              <button onClick={() => setActiveModal('critical')} className="text-muted-foreground hover:text-primary transition-colors">
                <Info className="w-4 h-4" />
              </button>
            </div>
            
            <div className="space-y-4">
              {[
                { label: monthNames[thisMonth], count: completingThisMonth, color: 'text-primary', bg: 'bg-primary' },
                { label: monthNames[nextMonthIdx], count: completingNextMonth, color: 'text-warning', bg: 'bg-warning' },
                { label: 'Later', count: completingLater, color: 'text-purple-500', bg: 'bg-purple-500' },
              ].map((item, i) => (
                <div key={i} className="flex items-center gap-4">
                  <span className="text-[11px] uppercase tracking-widest text-muted-foreground w-12 shrink-0">{item.label}</span>
                  <div className="flex-1 h-1 bg-muted rounded-full relative">
                    <div className={`absolute left-0 top-0 bottom-0 ${item.bg} rounded-full`} style={{ width: `${Math.max(2, (item.count / totalActivities) * 100)}%` }}>
                      <div className={`absolute right-0 top-1/2 -translate-y-1/2 w-2 h-2 ${item.bg} rounded-full translate-x-1 shadow-sm border border-card`} />
                    </div>
                  </div>
                  <span className={`text-[15px] ${item.color} w-10 text-right`}>{fmtNum(item.count)}</span>
                </div>
              ))}
            </div>
            
            <div className="pt-6 border-t border-border/50 grid grid-cols-2 gap-4">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Completed</div>
                <div className="text-[22px] text-success">{fmtNum(completedCriticalActivities)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">Delayed</div>
                <div className={`text-[22px] ${delayedActivities > 0 ? 'text-destructive' : 'text-success'}`}>{fmtNum(delayedActivities)}</div>
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

  const progressRaw = project.progress || 0;
  // If progress is between 0 and 1 (exclusive of 0), assume it's a decimal (e.g. 0.81 = 81%)
  // Otherwise, assume it's already a percentage (e.g. 3.9 = 3.9%)
  const progressPct = progressRaw > 0 && progressRaw <= 1 ? progressRaw * 100 : progressRaw;

  const isCommissioned = Boolean(project.isCommissioned);

  const accentColor =
    project.statusTier === 'Critical' ? '#EF4444' :
      project.statusTier === 'High Risk' ? '#F97316' :
        project.statusTier === 'Watchlist' ? '#F59E0B' :
          project.statusTier === 'Completed' ? '#3B82F6' : '#10B981';

  return (
    <div
      onClick={() => onOpen(project.projectId)}
      className="group relative flex items-center justify-between px-6 py-5 bg-card hover:bg-muted border-b border-border cursor-pointer transition-all duration-300"
    >
      <div className="absolute inset-0 opacity-0 group-hover:opacity-5 transition-opacity duration-300 pointer-events-none" style={{ backgroundColor: accentColor }} />
      <div className="absolute left-0 top-0 bottom-0 w-[3px] opacity-0 group-hover:opacity-100 transition-opacity" style={{ backgroundColor: accentColor }}></div>

      {/* 1. Project Details (30%) */}
      <div className="flex flex-col gap-1.5 w-[30%] min-w-[200px] pr-4">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-semibold text-foreground/90 group-hover:text-primary transition-colors truncate">
            {project.projectName}
          </h3>
          <div className={`w-2 h-2 rounded-full shrink-0 ${statusCfg.bgColor}`} style={{ backgroundColor: accentColor, boxShadow: `0 0 6px ${accentColor}80` }}></div>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground mt-1">
           {project.capacityMW > 0 && (
             <span className="bg-muted px-1.5 py-0.5 rounded text-foreground/80 font-semibold">{project.capacityMW} MW</span>
           )}
           <span className={`opacity-80 flex items-center gap-1 ${project.capacityMW > 0 ? 'border-l border-border pl-2' : ''}`}>
             P6: {project.projectId}
           </span>
        </div>
      </div>

      {/* 2. Schedule Performance (20%) */}
      <div className="w-[20%] min-w-[130px] flex flex-col justify-center gap-1.5 border-l border-border pl-4 pr-4">
        <div className="flex flex-col gap-1 w-full max-w-[120px]">
          <div className="flex justify-between text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">
            <span>Progress</span>
            <span className="text-foreground">{Math.round(progressPct)}%</span>
          </div>
          <div className="h-1.5 w-full bg-border rounded-full overflow-hidden">
            <div className="h-full bg-primary" style={{ width: `${Math.min(100, Math.round(progressPct))}%` }}></div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[9px] mt-0.5 text-muted-foreground font-mono">
           <span>P:{Math.round((project.plannedDuration || 0) / 8)}d</span>
           <span>A:{Math.round((project.actualDuration || 0) / 8)}d</span>
           <span>R:{Math.round((project.remainingDuration || 0) / 8)}d</span>
        </div>
      </div>

      {/* 3. Supply Funnel (20%) */}
      <div className="w-[20%] min-w-[150px] flex flex-col justify-center border-l border-border pl-4 pr-4 py-0.5">
        <div className="flex justify-between items-center text-[10px] mb-0.5">
          <span className="text-muted-foreground uppercase tracking-widest font-semibold">Ordered</span>
          <span className="font-mono font-semibold text-foreground/80">{fmtNum(project.orderedQty)}</span>
        </div>
        <div className="flex justify-between items-center text-[10px] mb-0.5">
          <span className="text-muted-foreground uppercase tracking-widest font-semibold">Consumed</span>
          <span className="font-mono font-semibold text-success">{fmtNum(project.consumedQty)}</span>
        </div>
        <div className="flex justify-between items-center text-[10px]">
          <span className="text-muted-foreground uppercase tracking-widest font-semibold">Pending</span>
          <span className="font-mono font-semibold text-warning">{fmtNum(project.pendingDispatchQty)}</span>
        </div>
      </div>

      {/* 4. Timeline Forecast (15%) */}
      <div className="w-[15%] min-w-[120px] flex items-center justify-between border-l border-border pl-4 pr-4">
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold w-8">Base</span>
            <span className="text-[11px] font-mono font-semibold text-foreground/60">{project.baselineMonth || 'N/A'}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[9px] uppercase tracking-widest font-semibold w-8 ${project.codAtRisk ? 'text-destructive/70' : 'text-primary/70'}`}>Fcst</span>
            <span className={`text-[13px] font-mono font-bold ${project.codAtRisk ? 'text-destructive' : 'text-foreground/90'}`}>{project.forecastMonth}</span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-0.5 ml-1">
          <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Lines</span>
          <span className="text-[13px] font-mono font-bold text-primary">{project.tcEdgesCount || 0}</span>
        </div>
      </div>

      {/* 5. Quality & Docs (15%) */}
      <div className="w-[15%] min-w-[150px] flex flex-col justify-center border-l border-border pl-4 pr-6">
        <div className="flex justify-between items-center text-[10px] mb-0.5">
          <span className="text-muted-foreground uppercase tracking-widest font-semibold">Invoices</span>
          <span className="font-mono font-semibold text-foreground/80">{project.invoiceCount || 0}</span>
        </div>
        <div className="flex justify-between items-center text-[10px] mb-0.5">
          <span className="text-muted-foreground uppercase tracking-widest font-semibold">NCs</span>
          <span className="font-mono font-semibold text-warning">{project.ncCount || 0}</span>
        </div>
        <div className="flex justify-between items-center text-[10px]">
          <span className="text-muted-foreground uppercase tracking-widest font-semibold">RFIs</span>
          <span className="font-mono font-semibold text-primary">{project.rfiCount || 0}</span>
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
  <div className="flex items-stretch border-b border-muted dark:border-border bg-white/40 animate-pulse">
    <div className="w-[30%] min-w-[200px] p-4 flex items-start gap-3">
      <div className="flex-1 mt-1">
        <div className="w-3/4 h-5 bg-gray-200 dark:bg-card rounded mb-2"></div>
        <div className="w-1/2 h-4 bg-gray-200 dark:bg-card rounded"></div>
      </div>
    </div>
    <div className="w-[20%] min-w-[130px] border-l border-border p-4 flex flex-col justify-center">
      <div className="w-full h-2 bg-gray-200 dark:bg-card rounded-full mb-3"></div>
      <div className="w-20 h-3 bg-gray-200 dark:bg-card rounded"></div>
    </div>
    <div className="w-[20%] min-w-[150px] border-l border-border p-4 flex flex-col justify-center gap-2">
      <div className="w-full h-3 bg-gray-200 dark:bg-card rounded"></div>
      <div className="w-full h-3 bg-gray-200 dark:bg-card rounded"></div>
      <div className="w-full h-3 bg-gray-200 dark:bg-card rounded"></div>
    </div>
    <div className="w-[15%] min-w-[120px] flex items-center justify-between border-l border-border pl-4 pr-4">
      <div className="flex flex-col gap-2">
        <div className="w-16 h-3 bg-gray-200 dark:bg-card rounded"></div>
        <div className="w-16 h-4 bg-gray-200 dark:bg-card rounded"></div>
      </div>
    </div>
    <div className="w-[15%] min-w-[150px] flex flex-col justify-center gap-2 border-l border-border pl-4 pr-6">
      <div className="w-full h-3 bg-gray-200 dark:bg-card rounded"></div>
      <div className="w-full h-3 bg-gray-200 dark:bg-card rounded"></div>
      <div className="w-full h-3 bg-gray-200 dark:bg-card rounded"></div>
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
  const [searchParams] = useSearchParams();
  const rawPortfolio = searchParams.get('portfolio');
  const portfolio = rawPortfolio ? rawPortfolio.replace(/\+/g, ' ') : null;
  const phaseFilter = searchParams.get('phase') || 'Ongoing';

  useEffect(() => {
    setLoading(true);
    const url = portfolio ? `/akasha/api/project-360?portfolio=${encodeURIComponent(portfolio)}&nocache=true` : '/akasha/api/project-360?nocache=true';
    fetch(url)
      .then(res => res.json())
      .then(json => setData(json))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [portfolio]);

  // ── Filtering ──
  const filtered = data
    .filter(d => {
      const searchLower = searchTerm.toLowerCase();
      const matchesSearch =
        (d.projectName?.toLowerCase().includes(searchLower) ?? false) ||
        (d.projectId?.toLowerCase().includes(searchLower) ?? false) ||
        (d.sapPlantCode?.toLowerCase().includes(searchLower) ?? false) ||
        (d.primaryIssue?.toLowerCase().includes(searchLower) ?? false);
      const matchesStatus = statusFilter === 'All' || d.statusTier === statusFilter;
      const isCommissioned = Boolean(d.isCommissioned);
      const matchesPhase = phaseFilter === 'ALL' ? true : phaseFilter === 'Commissioned' ? isCommissioned : !isCommissioned;
      const matchesRisk = riskFilters.length === 0 || riskFilters.every(rf => d.riskCategories?.includes(rf));
      return matchesSearch && matchesStatus && matchesPhase && matchesRisk;
    })
    .sort((a, b) => {
      switch (sortBy) {
        case 'integration': return b.integrationCount - a.integrationCount;
        case 'impact': return (b.delayDays || 0) - (a.delayDays || 0);
        case 'delay': return b.delayDays - a.delayDays;
        case 'cost': return a.costVariance - b.costVariance;
        case 'supply': return a.materialAvailability - b.materialAvailability;
        case 'vendor': return (b.inTransitQty === 0 && b.orderedQty > 0 ? 1 : 0) - (a.inTransitQty === 0 && a.orderedQty > 0 ? 1 : 0);
        case 'cod': return (b.codAtRisk ? 1 : 0) - (a.codAtRisk ? 1 : 0);
        case 'critical': return (b.delayDays || 0) - (a.delayDays || 0);
        default: return b.integrationCount - a.integrationCount;
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
      </div>

      {/* ── Executive Briefing ── */}
      {!loading && data.length > 0 && <PortfolioBriefingCard data={data} />}


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
                    : 'text-muted-foreground border-border hover:bg-muted hover:text-foreground'
                  }`}>
                {rf}
              </button>
            ))}
            {riskFilters.length > 0 && (
              <button onClick={() => setRiskFilters([])} className="text-[11px] text-destructive hover:text-red-300 transition-colors ml-2 self-center font-medium">
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
          <div className="flex items-center px-6 py-3 bg-muted dark:bg-gray-900/50 border-b border-border dark:border-border text-[11px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
            <div className="w-[30%] min-w-[200px] pr-4">Project Details</div>
            <div className="w-[20%] min-w-[130px] pl-4">Schedule</div>
            <div className="w-[20%] min-w-[150px] pl-4">Supply Chain</div>
            <div className="w-[15%] min-w-[120px] pl-4">Timeline</div>
            <div className="w-[15%] min-w-[150px] pl-4">Quality</div>
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
        <div className="bento-card overflow-hidden mb-8 p-0 flex flex-col max-h-[700px]">
          <div className="flex items-center px-6 py-3 bg-muted dark:bg-gray-900/50 border-b border-border dark:border-border text-[11px] font-bold uppercase tracking-[0.08em] text-muted-foreground shrink-0 z-10">
            <div className="w-[30%] min-w-[200px] pr-4">Project Details</div>
            <div className="w-[20%] min-w-[130px] pl-4">Schedule</div>
            <div className="w-[20%] min-w-[150px] pl-4">Supply Chain</div>
            <div className="w-[15%] min-w-[120px] pl-4">Timeline</div>
            <div className="w-[15%] min-w-[150px] pl-4">Quality</div>
          </div>
          <div className="flex flex-col overflow-y-auto custom-scrollbar flex-1 relative">
            {filtered.map((project, index) => (
              <div key={`${project.projectId}-${index}`} className="animate-in fade-in" style={{ animationDelay: `${index * 30}ms` }}>
                <ProjectRow project={project} onOpen={handleOpenProject} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
