import React, { useMemo, useState } from 'react';
import {
  TrendingUp, Activity, DollarSign,
  AlertTriangle, Zap, Clock, Layers, MapPin, Package, RefreshCw, AlertCircle, Bot, CheckCircle2, Shield
} from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import { motion } from 'framer-motion';
import KPIDetailsModal from '../../components/ui/KPIDetailsModal';

const containerVariants: any = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.04 }
  }
};

const itemVariants: any = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } }
};

const KPICard = ({ title, value, subtext, trend, trendValue, trendLabel, icon: Icon, color, onClick }: any) => {
  const isRed = color === 'red';
  const isEmerald = color === 'emerald';
  const isAmber = color === 'amber';

  const iconColor = isRed ? 'text-destructive' : isEmerald ? 'text-success' : isAmber ? 'text-warning' : 'text-primary';

  return (
    <motion.div variants={itemVariants} className="h-full">
      <div
        onClick={onClick}
        className="bento-card h-full px-4 py-3.5 cursor-pointer flex flex-col justify-between group"
      >
        <div className="flex justify-between items-start mb-2">
          <h4 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.08em] leading-tight">{title}</h4>
          <Icon className={`w-4 h-4 ${iconColor} opacity-60 group-hover:opacity-100 transition-opacity`} />
        </div>
        <div>
          <div className="text-xl font-bold tracking-tight text-foreground dark:text-white leading-none mb-1">{value}</div>
          {subtext && <div className="text-[10px] text-muted-foreground font-medium">{subtext}</div>}

          {trend && (
            <div className="flex items-center gap-1.5 text-[10px] font-semibold mt-2">
              <span className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded ${trend === 'up' ? 'text-success bg-success/10' : trend === 'down' ? 'text-destructive bg-destructive/10' : 'text-primary bg-primary/10'}`}>
                {trend === 'up' ? '▲' : trend === 'down' ? '▼' : '●'} {trendValue}
              </span>
              <span className="text-muted-foreground">{trendLabel}</span>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default function ExecutiveOverview({ dashboardData, briefing, briefingLoading, briefingError }: any) {
  const [activeKpiModal, setActiveKpiModal] = useState<string | null>(null);
  const [activeListTab, setActiveListTab] = useState<'top' | 'low' | 'delayed'>('top');
  const summary = dashboardData?.summary || {};
  const projects = dashboardData?.projects || [];

  const getProjectCapacity = (p: any) => {
    if (p.capacity_mwac && p.capacity_mwac > 0) return p.capacity_mwac;
    const name = p.p6_project_name || p.project_name || '';
    const match = name.match(/(\d+(?:\.\d+)?)\s*MW/i);
    if (match) return parseFloat(match[1]);
    return 0;
  };

  const totalProjects = summary.total_projects || 0;
  const delayedProjects = summary.delayed_projects || 0;
  const onTrackProjects = summary.on_track_projects || 0;
  const totalMW = summary.total_mw || 0;
  
  const { codMW, trMW } = useMemo(() => {
    return projects.reduce((acc: any, p: any) => {
      acc.codMW += (p.cod_mw || 0);
      acc.trMW += (p.tr_mw || 0);
      return acc;
    }, { codMW: 0, trMW: 0 });
  }, [projects]);

  const { totalPOValue, avgProgress, poDeliveredCr } = useMemo(() => {
    let poVal = 0;
    let progSum = 0;
    let validProg = 0;
    let deliveredCr = 0;
    projects.forEach((p: any) => {
      poVal += (p.sap?.po_value || 0);
      deliveredCr += (p.sap?.po_delivered_cr || 0);
      
      let prog = 0;
      const rawProg = p.p6?.progress;
      if (typeof rawProg === 'string' && rawProg.includes('%')) {
        prog = parseFloat(rawProg.replace('%', ''));
      } else {
        prog = Number(rawProg) || 0;
      }

      if (prog > 0) {
        progSum += prog;
        validProg++;
      }
    });
    return {
      totalPOValue: poVal,
      avgProgress: validProg ? (progSum / validProg) : 0,
      poDeliveredCr: deliveredCr
    };
  }, [projects]);

  const remainingPOValue = (totalPOValue / 10000000) - poDeliveredCr;

  const progressStages = useMemo(() => {
    let stages = { initiation: 0, early: 0, mid: 0, late: 0, completed: 0 };
    projects.forEach((p: any) => {
      const rawProg = p.p6?.progress;
      let prog = 0;
      if (typeof rawProg === 'string' && rawProg.includes('%')) {
        prog = parseFloat(rawProg.replace('%', ''));
      } else {
        prog = Number(rawProg) || 0;
      }
      
      if (prog >= 99.9) stages.completed++;
      else if (prog >= 75) stages.late++;
      else if (prog >= 50) stages.mid++;
      else if (prog >= 25) stages.early++;
      else stages.initiation++;
    });
    return stages;
  }, [projects]);

  const transmissionOverview = useMemo(() => {
    const map = new Map<string, number>();
    projects.forEach((p: any) => {
      const tc = p.tc?.data || {};
      ['khavda', 'rajasthan'].forEach(loc => {
        (tc[loc] || []).forEach((item: any) => {
          if (item.phase && item.voltage) {
            const key = `${item.phase} - ${item.voltage}`;
            map.set(key, (map.get(key) || 0) + 1);
          }
        });
      });
    });
    return Array.from(map.entries())
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
  }, [projects]);

  const listProjects = useMemo(() => {
    if (activeListTab === 'delayed') return [...projects].filter((p: any) => p.p6?.health === 'Delayed');
    if (activeListTab === 'low') return [...projects].filter((p: any) => ((p.p6?.progress || 0) * 100) < 50);
    return projects;
  }, [projects, activeListTab]);

  const topSapProjects = useMemo(() => {
    return [...projects]
      .filter((p: any) => (p.sap?.req_qty || p.sap?.po_qty || p.sap?.inventory_qty) > 0)
      .sort((a, b) => (b.sap?.req_qty || b.sap?.po_qty || 0) - (a.sap?.req_qty || a.sap?.po_qty || 0))
      .slice(0, 5);
  }, [projects]);

  const costChartOptions = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'inherit' },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { textStyle: { color: '#94a3b8', fontSize: 11 }, top: 0, right: 0 },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true },
    xAxis: {
      type: 'value',
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(150, 150, 150, 0.2)', type: 'dashed' } }
    },
    yAxis: {
      type: 'category',
      data: topSapProjects.map(p => p.project_name?.substring(0, 15) + '...'),
      axisLabel: { color: '#94a3b8', fontWeight: '600', fontSize: 11 }
    },
    series: [
      { name: 'Requirement', type: 'bar', stack: 'sap', data: topSapProjects.map(p => p.sap?.req_qty || 0), itemStyle: { color: '#bfdbfe' } },
      { name: 'PO Raised', type: 'bar', stack: 'sap', data: topSapProjects.map(p => p.sap?.po_qty || 0), itemStyle: { color: '#60a5fa' } },
      { name: 'In-Transit', type: 'bar', stack: 'sap', data: topSapProjects.map(p => p.sap?.in_transit_qty || 0), itemStyle: { color: '#fbbf24' } },
      { name: 'Inventory/GRN', type: 'bar', stack: 'sap', data: topSapProjects.map(p => p.sap?.inventory_qty || 0), itemStyle: { color: '#34d399' } }
    ]
  };

  const originalScatterOptions = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'inherit' },
    tooltip: { trigger: 'item', formatter: (p: any) => `<strong>${p.data[2]}</strong><br/>Progress: ${p.data[0]}%<br/>Capacity: ${Number(p.data[1]).toFixed(1)} MW<br/>COD: ${p.data[3]}` },
    grid: { left: '3%', right: '7%', bottom: '3%', top: '15%', containLabel: true },
    xAxis: {
      type: 'value', name: 'Progress (%)',
      nameTextStyle: { color: '#94a3b8', fontWeight: '600', padding: [0, 0, 10, 0] },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(150, 150, 150, 0.2)', type: 'dashed' } }
    },
    yAxis: {
      type: 'value', name: 'Capacity (MW)',
      nameTextStyle: { color: '#94a3b8', fontWeight: '600' },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(150, 150, 150, 0.2)', type: 'dashed' } }
    },
    series: [{
      name: 'Projects', type: 'scatter',
      symbolSize: (data: any) => Math.max(10, Math.min(data[1] / 10, 40)),
      itemStyle: { color: '#3b82f6', opacity: 0.6, borderColor: '#ffffff', borderWidth: 1 },
      data: projects.map((p: any) => ({ ...p, extractedCap: getProjectCapacity(p) })).filter((p: any) => p.extractedCap > 0).map((p: any) => {
        const codDateStr = p.p6?.planned_finish_date || p.p6?.scheduled_finish_date || p.p6?.finish_date;
        const cod = codDateStr ? new Date(codDateStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A';
        return [Math.round(p.p6?.progress || 0), parseFloat(p.extractedCap.toFixed(1)), p.p6_project_name || p.project_name, cod];
      })
    }]
  };

  const queueScatterOptions = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'inherit' },
    tooltip: { trigger: 'item', formatter: (p: any) => `<strong>${p.data[2]}</strong><br/>Progress: ${Number(p.data[0]).toFixed(1)}%<br/>Capacity: ${Number(p.data[1]).toFixed(1)} MW<br/>COD: ${p.data[5]}<br/>Status: ${p.data[3]}${p.data[4] > 0 ? ' (' + p.data[4] + ' days delayed)' : ''}` },
    grid: { left: '3%', right: '4%', bottom: '5%', top: '10%', containLabel: true },
    xAxis: {
      type: 'value', name: 'Progress (%)',
      nameTextStyle: { color: '#94a3b8', fontWeight: '600' },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(150, 150, 150, 0.2)', type: 'dashed' } }
    },
    yAxis: {
      type: 'value', name: 'Capacity (MW)',
      nameTextStyle: { color: '#94a3b8', fontWeight: '600' },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(150, 150, 150, 0.2)', type: 'dashed' } }
    },
    series: [{
      name: 'Projects', type: 'scatter',
      symbolSize: (data: any) => Math.max(8, Math.min(data[1] / 15, 30)),
      itemStyle: {
        color: (params: any) => params.data[0] >= 90 ? '#34d399' : params.data[3] === 'Delayed' ? '#f87171' : '#60a5fa',
        opacity: 0.8, borderColor: '#ffffff', borderWidth: 1
      },
      data: listProjects.map((p: any) => ({ ...p, extractedCap: getProjectCapacity(p) })).filter((p: any) => p.extractedCap > 0).map((p: any) => {
        let delayDays = 0;
        const codDateStr = p.p6?.planned_finish_date || p.p6?.scheduled_finish_date || p.p6?.finish_date;
        const cod = codDateStr ? new Date(codDateStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A';
        if (p.p6?.baseline_finish_date) {
          const finishStr = p.p6?.scheduled_finish_date || p.p6?.finish_date;
          if (finishStr) {
            const finish = new Date(finishStr);
            const baseline = new Date(p.p6.baseline_finish_date);
            if (!isNaN(finish.getTime()) && !isNaN(baseline.getTime())) {
              delayDays = Math.max(0, Math.ceil((finish.getTime() - baseline.getTime()) / (1000 * 60 * 60 * 24)));
            }
          }
        }
        return [p.p6?.progress || 0, parseFloat(p.extractedCap.toFixed(1)), p.p6_project_name || p.project_name, p.p6?.health || 'On Track', delayDays, cod];
      })
    }]
  };

  return (
    <div className="flex flex-col gap-4 w-full pb-8">

      {/* ROW 1: All KPIs in a single row on desktop */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-3"
      >
        <KPICard title="Total Projects" value={totalProjects} trend="up" trendValue={onTrackProjects} trendLabel="On Track" icon={Activity} color="blue" onClick={() => setActiveKpiModal('Total Projects')} />
        <KPICard title="Portfolio Capacity" value={`COD: ${Math.round(codMW)} MW`} subtext={`Trial Run: ${Math.round(trMW)} MW | Total: ${Math.round(totalMW)} MW`} icon={Zap} color="emerald" onClick={() => setActiveKpiModal('Portfolio Capacity')} />
        <KPICard title="Delayed Projects" value={delayedProjects} icon={AlertTriangle} color="red" onClick={() => setActiveKpiModal('Delayed Projects')} />
        
        {/* Quality Pulse KPI */}
        <KPICard 
          title="Quality (Pulse)" 
          value={`${summary?.quality?.open_ncs || 0} Open NCs`} 
          subtext={`${summary?.quality?.closure_rate || 0}% Closure Rate`} 
          icon={Shield} 
          color="amber" 
          onClick={() => setActiveKpiModal('Quality (Pulse)')} 
        />

        <KPICard title="Remaining PO Value" value={`₹${Math.max(0, remainingPOValue).toFixed(1)} Cr`} subtext="Pending Delivery" icon={DollarSign} color="amber" onClick={() => setActiveKpiModal('Remaining PO Value')} />
        <KPICard title="Total PO Value" value={`₹${(totalPOValue / 10000000).toFixed(1)} Cr`} icon={DollarSign} color="emerald" onClick={() => setActiveKpiModal('Total PO Value')} />
        <KPICard title="Completed Projects" value={progressStages.completed} icon={CheckCircle2} color="emerald" onClick={() => setActiveKpiModal('Completed Projects')} />
      </motion.div>

      {/* ROW 2: Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Left Col (Span 2) */}
        <div className="lg:col-span-2 flex flex-col gap-4">

          {/* SECTION: AI EXECUTIVE BRIEF */}
          <motion.div variants={itemVariants} initial="hidden" animate="show" className="bento-card p-4">
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-2">
                <Bot className="w-4 h-4 text-primary" />
                <h3 className="text-[14px] font-bold text-foreground dark:text-white">Executive Intelligence Brief</h3>
              </div>
              <div className="text-[10px] font-bold text-success bg-success/10 px-2.5 py-0.5 rounded-full flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-success/100 animate-pulse"></span> {briefing?.confidenceScore || 87}%
              </div>
            </div>

            <div className="bg-muted dark:bg-gray-900/50 rounded-lg p-4 border border-muted dark:border-border">
              <div className="flex justify-between items-center mb-3">
                <div className="flex items-center gap-1.5 text-[10px] font-bold text-muted-foreground uppercase tracking-[0.08em]">
                  <Zap className="w-3 h-3 text-primary" /> AI-GENERATED SUMMARY
                </div>
                <div className="text-[9px] font-medium text-muted-foreground uppercase tracking-[0.08em]">
                  Generated Live
                </div>
              </div>

              <div className="mt-2">
                {briefingLoading ? (
                  <div className="flex items-center gap-3 py-6 text-primary text-sm font-medium justify-center">
                    <RefreshCw className="w-5 h-5 animate-spin" /> Analyzing live SAP & P6 data...
                  </div>
                ) : briefingError ? (
                  <div className="text-sm text-destructive font-medium py-4 flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" /> {briefingError}
                  </div>
                ) : (
                  <>
                    <p className="text-[13px] text-foreground dark:text-muted-foreground leading-relaxed">
                      {briefing?.toplineSummary || "Insufficient data to generate portfolio summary."}
                    </p>
                    <div className="flex items-center gap-2 mt-4 flex-wrap">
                      {briefing?.keyActions?.map((a: any, i: number) => {
                        const isRed = a.title.toLowerCase().includes('risk') || a.color === 'red';
                        const isAmber = a.title.toLowerCase().includes('cost') || a.color === 'amber' || a.title.toLowerCase().includes('monitor');
                        const colorTheme = isRed ? 'text-destructive bg-destructive/10 border-destructive/20 dark:text-destructive dark:bg-destructive/100/10 dark:border-destructive/20' :
                          isAmber ? 'text-warning bg-warning/10 border-warning/20 dark:text-warning dark:bg-warning/100/10 dark:border-warning/20' :
                            'text-success bg-success/10 border-success/20 dark:text-success dark:bg-success/100/10 dark:border-success/20';

                        return (
                          <span key={i} className={`text-[11px] px-3 py-1.5 flex items-center gap-1.5 border rounded-full font-semibold shadow-sm ${colorTheme}`}>
                            <AlertCircle className="w-3.5 h-3.5" /> {a.title}
                          </span>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            </div>
          </motion.div>

          <motion.div variants={itemVariants} initial="hidden" animate="show" className="bg-card border border-border dark:border-border rounded-xl shadow-sm p-6 flex-1 flex flex-col min-h-[450px]">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-6">
              <h4 className="text-sm font-bold text-foreground dark:text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-primary" /> Project Execution Queue
              </h4>
              <div className="flex bg-muted dark:bg-card p-1 border border-border dark:border-gray-700 rounded-lg text-xs font-semibold">
                <button onClick={() => setActiveListTab('top')} className={`px-4 py-1.5 rounded-md transition-all ${activeListTab === 'top' ? 'bg-white dark:bg-gray-700 text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground dark:hover:text-white'}`}>All</button>
                <button onClick={() => setActiveListTab('low')} className={`px-4 py-1.5 rounded-md transition-all ${activeListTab === 'low' ? 'bg-white dark:bg-gray-700 text-warning shadow-sm' : 'text-muted-foreground hover:text-foreground dark:hover:text-white'}`}>&lt; 50%</button>
                <button onClick={() => setActiveListTab('delayed')} className={`px-4 py-1.5 rounded-md transition-all ${activeListTab === 'delayed' ? 'bg-white dark:bg-gray-700 text-destructive shadow-sm' : 'text-muted-foreground hover:text-foreground dark:hover:text-white'}`}>Delayed</button>
              </div>
            </div>
            <div className="flex justify-end items-center gap-5 px-2 mb-2 text-xs font-medium text-foreground dark:text-muted-foreground">
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#3b82f6] shadow-sm ring-1 ring-white/10"></div> On Track (&lt; 90%)</div>
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#10b981] shadow-sm ring-1 ring-white/10"></div> Near Completion (&ge; 90%)</div>
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#ef4444] shadow-sm ring-1 ring-white/10"></div> Delayed</div>
            </div>
            <div className="flex-1 w-full min-h-[350px]">
              <ReactECharts option={queueScatterOptions} style={{ height: '100%', width: '100%' }} />
            </div>
          </motion.div>
        </div>

        {/* Right Col */}
        <div className="flex flex-col gap-4">
          <motion.div variants={itemVariants} initial="hidden" animate="show" className="bento-card p-6 flex-none">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-sm font-bold text-foreground dark:text-white flex items-center gap-2"><Layers className="w-5 h-5 text-primary" /> Progress Stage</h3>
              <div className="text-[11px] font-bold text-muted-foreground uppercase bg-muted dark:bg-card px-2 py-1 rounded-md">{totalProjects} total</div>
            </div>
            <div className="space-y-5 text-xs font-semibold">
              {[
                { phase: 'Initiation (0-25%)', count: progressStages.initiation, color: 'bg-gray-400' },
                { phase: 'Early (26-50%)', count: progressStages.early, color: 'bg-blue-400' },
                { phase: 'Mid (51-75%)', count: progressStages.mid, color: 'bg-amber-400' },
                { phase: 'Late (76-99%)', count: progressStages.late, color: 'bg-primary' },
                { phase: 'Completed (100%)', count: progressStages.completed, color: 'bg-success/100' }
              ].map((p, i) => (
                <div key={i} className="flex items-center justify-between group">
                  <div className="w-32 text-muted-foreground group-hover:text-foreground dark:group-hover:text-white transition-colors">{p.phase}</div>
                  <div className="flex-1 h-2.5 bg-muted dark:bg-card rounded-full mx-4 overflow-hidden"><div className={`h-full ${p.color}`} style={{ width: `${(p.count / Math.max(1, totalProjects)) * 100}%` }}></div></div>
                  <div className="w-6 text-right text-foreground dark:text-white">{p.count}</div>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div variants={itemVariants} initial="hidden" animate="show" className="bento-card p-6 flex-1 overflow-hidden flex flex-col">
            <h3 className="text-sm font-bold text-foreground dark:text-white flex items-center justify-between mb-4 shrink-0">
              <span className="flex items-center gap-2"><Activity className="w-5 h-5 text-primary" /> Transmission Network</span>
            </h3>
            <div className="space-y-1 overflow-y-auto custom-scrollbar pr-2 flex-1">
              {transmissionOverview.map((node, i) => (
                <div key={i} className="flex justify-between items-center py-3 border-b border-muted dark:border-border last:border-0 text-sm">
                  <div className="flex items-center gap-2.5 text-foreground dark:text-muted-foreground font-semibold flex-1 pr-2">
                    <Zap className={`w-4 h-4 text-success shrink-0`} />
                    <span className="line-clamp-1" title={node.key}>{node.key}</span>
                  </div>
                  <div className="text-[11px] font-bold text-muted-foreground bg-muted dark:bg-gray-900/50 px-2.5 py-1 rounded-md shrink-0 border border-border dark:border-gray-700">{node.count} Nodes</div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>

      {/* ROW 3: ECharts */}
      <motion.div variants={itemVariants} initial="hidden" animate="show" className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bento-card p-4 flex flex-col h-[350px]">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-sm font-bold text-foreground dark:text-white flex items-center gap-2"><Package className="w-5 h-5 text-primary" /> SAP Material Pipeline (Qty)</h3>
          </div>
          <div className="flex-1 w-full">
            <ReactECharts option={costChartOptions} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        <div className="bento-card p-4 flex flex-col h-[350px]">
          <h3 className="text-sm font-bold text-foreground dark:text-white flex items-center gap-2 mb-4"><Activity className="w-5 h-5 text-primary" /> Progress vs Capacity Distribution</h3>
          <div className="flex-1 w-full">
            <ReactECharts option={originalScatterOptions} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
      </motion.div>

      <KPIDetailsModal
        isOpen={!!activeKpiModal}
        onClose={() => setActiveKpiModal(null)}
        activeKpi={activeKpiModal}
        projects={projects}
        summary={summary}
      />
    </div>
  );
}
