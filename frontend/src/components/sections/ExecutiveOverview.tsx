import React, { useMemo, useState } from 'react';
import { 
  TrendingUp, Activity, DollarSign, 
  AlertTriangle, Zap, Clock, Layers, MapPin, Package, RefreshCw, AlertCircle, Bot
} from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import KPIDetailsModal from '../ui/KPIDetailsModal';

const KPICard = ({ title, value, subtext, trend, trendValue, trendLabel, icon: Icon, color, onClick, hideBorderRight = false, hideBorderBottom = false }: any) => {
  const isRed = color === 'red';
  const isEmerald = color === 'emerald';
  const isAmber = color === 'amber';
  const colorClass = isRed ? 'text-red-500' : isEmerald ? 'text-emerald-500' : isAmber ? 'text-amber-500' : 'text-primary';
  
  return (
    <div 
      onClick={onClick}
      className={`bg-card rounded-sm border border-border p-5 hover:bg-muted/50 transition-all cursor-pointer relative flex flex-col justify-between shadow-sm`}
    >
      <div className="flex justify-between items-start mb-3">
        <h4 className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest leading-tight w-2/3">{title}</h4>
        <div className={`flex items-center justify-center p-2 border ${isRed ? 'bg-red-500/10 border-red-500/20' : isEmerald ? 'bg-emerald-500/10 border-emerald-500/20' : isAmber ? 'bg-amber-500/10 border-amber-500/20' : 'bg-primary/10 border-primary/20'}`}>
           <Icon className={`w-4 h-4 ${colorClass}`} />
        </div>
      </div>
      <div>
        <div className={`text-3xl font-bold tracking-tight mb-1 ${colorClass}`}>{value}</div>
        {subtext && <div className="text-[11px] text-muted-foreground mb-2">{subtext}</div>}
        
        {trend && (
          <div className="flex items-center gap-1.5 text-[11px] font-semibold mt-3">
            <span className={`flex items-center gap-0.5 ${trend === 'up' ? 'text-emerald-500' : trend === 'down' ? 'text-red-500' : 'text-primary'}`}>
              {trend === 'up' ? '▲' : trend === 'down' ? '▼' : '▬'} {trendValue}
            </span>
            <span className="text-muted-foreground">{trendLabel}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default function ExecutiveOverview({ dashboardData, briefing, briefingLoading, briefingError }: any) {
  const [activeKpiModal, setActiveKpiModal] = useState<string | null>(null);
  const [activeListTab, setActiveListTab] = useState<'top'|'low'|'delayed'>('top');
  const summary = dashboardData?.summary || {};
  const projects = dashboardData?.projects || [];
  
  // Helper to extract capacity from name if missing
  const getProjectCapacity = (p: any) => {
    if (p.capacity_mwac && p.capacity_mwac > 0) return p.capacity_mwac;
    const name = p.p6_project_name || p.project_name || '';
    const match = name.match(/(\d+(?:\.\d+)?)\s*MW/i);
    if (match) return parseFloat(match[1]);
    return 0; // Default to 0 if not found
  };
  
  const totalProjects = summary.total_projects || 0;
  const delayedProjects = summary.delayed_projects || 0;
  const onTrackProjects = summary.on_track_projects || 0;
  const totalMW = summary.total_mw || 0;
  const totalInventoryMW = summary.total_inventory_mw || 0;
  const totalPOMW = summary.total_po_mw || 0;

  // Calculate Aggregations from Projects
  const { totalPlannedCost, totalCurrentBudget } = useMemo(() => {
    let planned = 0;
    let current = 0;
    projects.forEach((p: any) => {
      planned += (p.p6?.planned_cost || 0);
      current += (p.p6?.current_budget || 0);
    });
    return { totalPlannedCost: planned, totalCurrentBudget: current };
  }, [projects]);

  const costVariance = totalCurrentBudget - totalPlannedCost;
  
  // Projects by Progress Stage
  const progressStages = useMemo(() => {
    let stages = { initiation: 0, early: 0, mid: 0, late: 0, completed: 0 };
    projects.forEach((p: any) => {
      const prog = (p.p6?.progress || 0) * 100;
      if (prog >= 100) stages.completed++;
      else if (prog >= 75) stages.late++;
      else if (prog >= 50) stages.mid++;
      else if (prog >= 25) stages.early++;
      else stages.initiation++;
    });
    return stages;
  }, [projects]);

  const epsPortfolio = useMemo(() => {
    const map = new Map<string, any>();
    
    projects.forEach((p: any) => {
      const rawEps = p.p6?.parent_eps_name || 'Unmapped Portfolio';
      const eps = rawEps.replace('EPS Node: ', '').trim();
      const capMatch = p.project_name?.match(/(\d+(?:\.\d+)?)\s*MW/i) || p.p6_project_name?.match(/(\d+(?:\.\d+)?)\s*MW/i);
      const cap = capMatch ? parseFloat(capMatch[1]) : 0;
      const isDelayed = p.p6?.health === 'Delayed' || (p.p6?.finish_date_variance || 0) < 0;
      const progress = p.p6?.progress || 0;
      
      if (!map.has(eps)) {
        map.set(eps, { eps, count: 0, capacity: 0, delayed: 0, totalProgress: 0 });
      }
      const data = map.get(eps);
      data.count += 1;
      data.capacity += cap;
      data.totalProgress += progress;
      if (isDelayed) data.delayed += 1;
    });

    return Array.from(map.values())
      .map(d => ({
        ...d,
        avgProgress: d.count > 0 ? d.totalProgress / d.count : 0
      }))
      .sort((a, b) => b.capacity - a.capacity || b.count - a.count)
      .slice(0, 6);
  }, [projects]);

  // Tabbed Project List
  const listProjects = useMemo(() => {
    if (activeListTab === 'delayed') {
      return [...projects].filter((p:any) => p.p6?.health === 'Delayed');
    }
    if (activeListTab === 'low') {
      return [...projects].filter((p:any) => ((p.p6?.progress || 0) * 100) < 50);
    }
    return projects;
  }, [projects, activeListTab]);

  // Delayed Projects List
  const delayedProjectList = useMemo(() => {
    return projects.filter((p: any) => p.p6?.health === 'Delayed').slice(0, 4);
  }, [projects]);

  // Top Projects by SAP Material Tracking (for ECharts)
  const topSapProjects = useMemo(() => {
    return [...projects]
      .filter((p: any) => (p.sap?.req_mw || p.sap?.po_mw || p.sap?.inventory_mw) > 0)
      .sort((a, b) => (b.sap?.req_mw || b.sap?.po_mw || 0) - (a.sap?.req_mw || a.sap?.po_mw || 0))
      .slice(0, 5);
  }, [projects]);

  const costChartOptions = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { textStyle: { color: 'var(--foreground)', fontFamily: 'Adani' }, top: 0, right: 0 },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true },
    xAxis: { 
      type: 'value', 
      axisLabel: { color: 'var(--muted-foreground)', fontFamily: 'Adani' },
      splitLine: { lineStyle: { color: 'var(--border)' } }
    },
    yAxis: { 
      type: 'category', 
      data: topSapProjects.map(p => p.project_name?.substring(0, 15) + '...'),
      axisLabel: { color: 'var(--foreground)', fontFamily: 'Adani', fontWeight: 'bold' }
    },
    series: [
      {
        name: 'Requirement',
        type: 'bar',
        stack: 'sap',
        data: topSapProjects.map(p => p.sap?.req_mw || 0),
        itemStyle: { color: 'hsl(210, 100%, 80%)' }
      },
      {
        name: 'PO Raised',
        type: 'bar',
        stack: 'sap',
        data: topSapProjects.map(p => p.sap?.po_mw || 0),
        itemStyle: { color: 'hsl(210, 100%, 60%)' }
      },
      {
        name: 'In-Transit',
        type: 'bar',
        stack: 'sap',
        data: topSapProjects.map(p => p.sap?.it_mw || 0),
        itemStyle: { color: '#F59E0B' } // Amber
      },
      {
        name: 'Inventory/GRN',
        type: 'bar',
        stack: 'sap',
        data: topSapProjects.map(p => p.sap?.inventory_mw || 0),
        itemStyle: { color: '#10B981' } // Emerald
      }
    ]
  };

  const originalScatterOptions = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { 
      trigger: 'item',
      formatter: function (params: any) {
        return `<div style="font-family: Adani"><strong>${params.data[2]}</strong><br/>Progress: ${params.data[0]}%<br/>Capacity: ${params.data[1]} MW</div>`;
      }
    },
    legend: { show: false },
    grid: { left: '3%', right: '7%', bottom: '3%', top: '15%', containLabel: true },
    xAxis: { 
      type: 'value', name: 'Progress (%)', 
      nameTextStyle: { color: 'var(--foreground)', fontFamily: 'Adani', fontWeight: 'bold' },
      axisLabel: { color: 'var(--muted-foreground)', fontFamily: 'Adani' },
      splitLine: { lineStyle: { color: 'var(--border)' } }
    },
    yAxis: { 
      type: 'value', name: 'Capacity (MW)', 
      nameTextStyle: { color: 'var(--foreground)', fontFamily: 'Adani', fontWeight: 'bold' },
      axisLabel: { color: 'var(--muted-foreground)', fontFamily: 'Adani' },
      splitLine: { lineStyle: { color: 'var(--border)' } }
    },
    series: [{
      name: 'Projects',
      type: 'scatter',
      symbolSize: function (data: any) { return Math.max(10, Math.min(data[1] / 10, 40)); },
      itemStyle: { color: '#F59E0B', opacity: 0.7 },
      data: projects
        .map((p: any) => ({ ...p, extractedCap: getProjectCapacity(p) }))
        .filter((p:any) => p.extractedCap > 0)
        .map((p: any) => [
          Math.round((p.p6?.progress || 0) * 100),
          p.extractedCap,
          p.p6_project_name || p.project_name
      ])
    }]
  };

  const queueScatterOptions = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { 
      trigger: 'item',
      formatter: function (params: any) {
        return `<div style="font-family: Adani"><strong>${params.data[2]}</strong><br/>Progress: ${params.data[0]}%<br/>Capacity: ${params.data[1]} MW<br/>Status: ${params.data[3]}</div>`;
      }
    },
    grid: { left: '3%', right: '4%', bottom: '5%', top: '10%', containLabel: true },
    xAxis: { 
      type: 'value', name: 'Progress (%)', 
      nameTextStyle: { color: 'var(--foreground)', fontFamily: 'Adani', fontWeight: 'bold' },
      axisLabel: { color: 'var(--muted-foreground)', fontFamily: 'Adani' },
      splitLine: { lineStyle: { color: 'var(--border)' } }
    },
    yAxis: { 
      type: 'value', name: 'Capacity (MW)', 
      nameTextStyle: { color: 'var(--foreground)', fontFamily: 'Adani', fontWeight: 'bold' },
      axisLabel: { color: 'var(--muted-foreground)', fontFamily: 'Adani' },
      splitLine: { lineStyle: { color: 'var(--border)' } }
    },
    series: [{
      name: 'Projects',
      type: 'scatter',
      symbolSize: function (data: any) { return Math.max(8, Math.min(data[1] / 8, 45)); },
      itemStyle: { 
        color: function(params: any) {
          if (params.data[3] === 'Delayed') return '#EF4444'; 
          if (params.data[0] >= 90) return '#10B981'; 
          return '#3B82F6'; 
        },
        opacity: 0.8,
        borderColor: '#ffffff',
        borderWidth: 1
      },
      data: listProjects
        .map((p: any) => ({ ...p, extractedCap: getProjectCapacity(p) }))
        .filter((p:any) => p.extractedCap > 0)
        .map((p: any) => [
          Math.round((p.p6?.progress || 0) * 100),
          p.extractedCap,
          p.p6_project_name || p.project_name,
          p.p6?.health || 'On Track'
      ])
    }]
  };

  return (
    <div className="flex flex-col gap-4 max-w-[1800px] mx-auto animate-in fade-in duration-500 p-4">
      
      {/* ROW 1: KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-4">
        <KPICard title="Total Projects" value={totalProjects} trend="up" trendValue={onTrackProjects} trendLabel="On Track" icon={Activity} color="blue" onClick={() => setActiveKpiModal('Total Projects')} />
        <KPICard title="Portfolio Capacity" value={`${Math.round(totalMW)} MW`} icon={Zap} color="emerald" onClick={() => setActiveKpiModal('Portfolio Capacity')} />
        <KPICard title="Delayed Projects" value={delayedProjects} icon={AlertTriangle} color="red" onClick={() => setActiveKpiModal('Delayed Projects')} />
        <KPICard title="SAP Inventory" value={`${Math.round(totalInventoryMW)} MW`} icon={Package} color="amber" onClick={() => setActiveKpiModal('SAP Inventory')} />
        <KPICard title="SAP PO Quantity" value={`${Math.round(totalPOMW)} MW`} icon={Layers} color="blue" onClick={() => setActiveKpiModal('SAP PO Quantity')} />
        <KPICard title="Cost Variance" value={`₹${Math.abs(costVariance / 10000000).toFixed(1)} Cr`} subtext={costVariance > 0 ? "Over Budget" : costVariance < 0 ? "Under Budget" : "On Budget"} icon={DollarSign} color={costVariance > 0 ? "red" : "emerald"} onClick={() => setActiveKpiModal('Cost Variance')} />
      </div>

      {/* ROW 2: Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        
        {/* Left Col (Span 2) */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          
          {/* SECTION 2: AI EXECUTIVE BRIEF */}
          <div className="bg-card rounded-sm border border-border p-6 shadow-sm">
            {/* Header */}
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-2 text-primary">
                <Bot className="w-4 h-4" />
                <h3 className="text-sm font-bold text-foreground">Executive Intelligence Brief</h3>
              </div>
              <div className="text-[11px] font-bold text-emerald-500 bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/20 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Confidence {briefing?.confidenceScore || 87}%
              </div>
            </div>

            {/* Inner Container */}
            <div className="bg-blue-50/50 dark:bg-blue-900/10 border border-blue-100 dark:border-blue-800/30 rounded-lg p-5">
              <div className="flex justify-between items-center mb-3">
                 <div className="flex items-center gap-1.5 text-[11px] font-bold text-blue-500 bg-blue-100 dark:bg-blue-900/30 px-2 py-0.5 rounded-sm uppercase tracking-wide">
                   <Zap className="w-3 h-3" /> AI-GENERATED SUMMARY
                 </div>
                 <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest">
                   Generated Live
                 </div>
              </div>
              
              <div className="mt-2">
                {briefingLoading ? (
                   <div className="flex items-center gap-3 py-4 text-primary text-sm font-medium">
                     <RefreshCw className="w-4 h-4 animate-spin" /> Analyzing live SAP & P6 data...
                   </div>
                ) : briefingError ? (
                   <div className="text-sm text-red-500 font-medium py-2 flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" /> {briefingError}
                   </div>
                ) : (
                  <>
                    <p className="text-[13px] text-foreground/80 leading-relaxed font-medium">
                      {briefing?.toplineSummary || "Insufficient data to generate portfolio summary."}
                    </p>
                    <div className="flex items-center gap-3 mt-5 flex-wrap">
                       {briefing?.keyActions?.map((a:any, i:number) => {
                          const isRed = a.title.toLowerCase().includes('risk') || a.color === 'red';
                          const isAmber = a.title.toLowerCase().includes('cost') || a.color === 'amber' || a.title.toLowerCase().includes('monitor');
                          const colorTheme = isRed ? 'text-red-500 bg-red-500/10 border-red-500/20' : 
                                             isAmber ? 'text-amber-500 bg-amber-500/10 border-amber-500/20' : 
                                             'text-emerald-500 bg-emerald-500/10 border-emerald-500/20';
                          
                          return (
                            <span key={i} className={`text-[11px] px-3 py-1 flex items-center gap-1.5 border rounded-full font-semibold ${colorTheme}`}>
                              <AlertCircle className="w-3.5 h-3.5" /> {a.title}
                            </span>
                          );
                       })}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="bg-card rounded-sm border border-border p-6 flex-1 flex flex-col min-h-[400px]">
            <div className="flex justify-between items-center mb-6">
               <h4 className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                 <Activity className="w-4 h-4 text-primary" /> Project Execution Queue
               </h4>
               <div className="flex bg-muted/30 p-1 border rounded-md text-[10px] font-bold uppercase tracking-widest">
                 <button onClick={() => setActiveListTab('top')} className={`px-3 py-1.5 rounded-sm transition-colors ${activeListTab === 'top' ? 'bg-background text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>All</button>
                 <button onClick={() => setActiveListTab('low')} className={`px-3 py-1.5 rounded-sm transition-colors ${activeListTab === 'low' ? 'bg-background text-amber-500 shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>&lt; 50%</button>
                 <button onClick={() => setActiveListTab('delayed')} className={`px-3 py-1.5 rounded-sm transition-colors ${activeListTab === 'delayed' ? 'bg-background text-red-500 shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Delayed</button>
               </div>
            </div>
            <div className="flex-1 w-full min-h-[350px]">
              <ReactECharts option={queueScatterOptions} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>
        </div>

        {/* Right Col */}
        <div className="flex flex-col gap-4">
          <div className="bg-card rounded-sm border border-border p-6 flex-none">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><Layers className="w-4 h-4 text-primary"/> Projects by Progress Stage</h3>
              <div className="text-[10px] font-bold text-muted-foreground uppercase">{totalProjects} total</div>
            </div>
            <div className="space-y-4 text-xs font-medium">
              {[
                { phase: 'Initiation (0-25%)', count: progressStages.initiation, color: 'bg-blue-500' },
                { phase: 'Early (26-50%)', count: progressStages.early, color: 'bg-indigo-500' },
                { phase: 'Mid (51-75%)', count: progressStages.mid, color: 'bg-amber-500' },
                { phase: 'Late (76-99%)', count: progressStages.late, color: 'bg-emerald-500' },
                { phase: 'Completed (100%)', count: progressStages.completed, color: 'bg-green-600' }
              ].map((p, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="w-32 text-muted-foreground">{p.phase}</div>
                  <div className="flex-1 h-2 bg-muted rounded-full mx-4 overflow-hidden"><div className={`h-full ${p.color}`} style={{ width: `${(p.count/Math.max(1, totalProjects))*100}%` }}></div></div>
                  <div className="w-6 text-right text-foreground">{p.count}</div>
                </div>
              ))}
            </div>
          </div>
          
          <div className="bg-card rounded-sm border border-border p-6 flex-1 overflow-hidden flex flex-col">
            <h3 className="text-sm font-bold text-foreground flex items-center justify-between mb-4 shrink-0">
              <span className="flex items-center gap-2"><MapPin className="w-4 h-4 text-primary"/> EPS Portfolio</span>
            </h3>
            <div className="space-y-1 overflow-y-auto custom-scrollbar pr-1 flex-1">
              {epsPortfolio.map((node, i) => (
                <div key={i} className="flex justify-between items-center py-3 border-b border-border/30 last:border-0 text-xs">
                  <div className="flex items-center gap-2 text-foreground font-medium flex-1 pr-2">
                    <MapPin className={`w-3.5 h-3.5 text-primary shrink-0`}/> 
                    <span className="line-clamp-1" title={node.eps}>{node.eps}</span>
                  </div>
                  <div className="font-mono text-muted-foreground shrink-0">{node.count} projects</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ROW 3: Alerts, Timeline */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        
        {/* Risk Alerts */}
        <div className="bg-card rounded-sm border border-border p-6 overflow-hidden">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-red-500"/> Delayed Projects Watchlist</h3>
            <div className="px-2 py-0.5 border border-red-500/20 text-red-600 dark:text-red-400 text-[10px] font-bold uppercase">{delayedProjects} Projects</div>
          </div>
          <div className="space-y-5">
            {delayedProjectList.length > 0 ? delayedProjectList.slice(0, 5).map((p: any, i: number) => (
              <div key={i} className="flex items-start gap-3">
                <div className="w-2 h-2 mt-1.5 rounded-full shrink-0 bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]"></div>
                <div className="flex-1">
                  <div className="flex justify-between items-start mb-1">
                     <div className="text-[13px] font-bold text-foreground leading-snug w-[70%]">{p.p6_project_name || p.project_name}</div>
                     <div className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{Math.round((p.p6?.progress || 0) * 100)}%</div>
                  </div>
                  <div className="text-[10px] text-muted-foreground flex justify-between items-center">
                    <span><span className="font-semibold text-foreground">Planned:</span> {(p.p6?.planned_finish_date || p.p6?.scheduled_finish_date) ? new Date(p.p6.planned_finish_date || p.p6.scheduled_finish_date).toLocaleDateString() : 'N/A'}</span>
                    <span className="text-red-500"><span className="font-semibold text-foreground">Current:</span> {p.p6?.finish_date ? new Date(p.p6.finish_date).toLocaleDateString() : 'N/A'}</span>
                  </div>
                </div>
              </div>
            )) : (
              <div className="text-sm text-muted-foreground">No delayed projects found in current data.</div>
            )}
          </div>
        </div>

        {/* Upcoming Deadlines / Timeline */}
        <div className="bg-card rounded-sm border border-border p-6">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><Clock className="w-4 h-4 text-primary"/> Upcoming Finish Dates</h3>
          </div>
          <div className="space-y-4">
            {[...projects].filter((p:any) => p.p6?.finish_date && new Date(p.p6.finish_date).getTime() > Date.now()).sort((a,b) => new Date(a.p6.finish_date).getTime() - new Date(b.p6.finish_date).getTime()).slice(0, 5).map((p: any, i: number) => (
              <div key={i} className="flex gap-4">
                <div className="w-16 text-[10px] text-muted-foreground font-mono pt-0.5 shrink-0">
                  {new Date(p.p6.finish_date).toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: '2-digit'})}
                </div>
                <div className="relative border-l border-border pl-4 pb-1 flex-1">
                  <div className={`absolute -left-1 top-1.5 w-2 h-2 rounded-full ${(p.p6?.progress || 0) * 100 > 90 ? 'bg-emerald-500' : 'bg-primary'}`}></div>
                  <div className="text-[13px] text-foreground font-semibold leading-tight pt-0.5 mb-1">{p.p6_project_name || p.project_name}</div>
                  <div className="text-[10px] text-muted-foreground">
                    Capacity: <span className="text-foreground">{p.capacity_mwac || 0} MW</span> | Progress: <span className="text-foreground">{Math.round((p.p6?.progress || 0) * 100)}%</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ROW 3: ECharts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pb-10">
        <div className="bg-card rounded-sm border border-border p-6 flex flex-col h-[350px]">
           <div className="flex justify-between items-center mb-2">
             <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><Package className="w-4 h-4 text-primary"/> SAP Material Pipeline (MW): Top 5 Projects</h3>
           </div>
           <div className="flex-1 w-full">
             <ReactECharts option={costChartOptions} style={{ height: '100%', width: '100%' }} />
           </div>
        </div>

        <div className="bg-card rounded-sm border border-border p-6 flex flex-col h-[350px]">
           <h3 className="text-sm font-bold text-foreground flex items-center gap-2 mb-2"><Activity className="w-4 h-4 text-primary"/> Progress vs Capacity Distribution</h3>
           <div className="flex-1 w-full">
             <ReactECharts option={originalScatterOptions} style={{ height: '100%', width: '100%' }} />
           </div>
        </div>
      </div>
      
      <KPIDetailsModal 
        isOpen={!!activeKpiModal} 
        onClose={() => setActiveKpiModal(null)} 
        activeKpi={activeKpiModal} 
        projects={projects} 
      />
    </div>
  );
}
