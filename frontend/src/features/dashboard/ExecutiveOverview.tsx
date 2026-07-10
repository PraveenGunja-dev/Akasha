import React, { useMemo, useState } from 'react';
import {
  TrendingUp, Activity, DollarSign,
  AlertTriangle, Zap, Clock, Layers, MapPin, Package, RefreshCw, AlertCircle, Bot, CheckCircle2
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

  const iconColor = isRed ? 'text-red-500' : isEmerald ? 'text-emerald-500' : isAmber ? 'text-amber-500' : 'text-[#0b74b1]';

  return (
    <motion.div variants={itemVariants} className="h-full">
      <div
        onClick={onClick}
        className="bento-card h-full px-4 py-3.5 cursor-pointer flex flex-col justify-between group"
      >
        <div className="flex justify-between items-start mb-2">
          <h4 className="text-[10px] font-semibold text-gray-400 uppercase tracking-[0.08em] leading-tight">{title}</h4>
          <Icon className={`w-4 h-4 ${iconColor} opacity-60 group-hover:opacity-100 transition-opacity`} />
        </div>
        <div>
          <div className="text-xl font-bold tracking-tight text-gray-900 dark:text-white leading-none mb-1">{value}</div>
          {subtext && <div className="text-[10px] text-gray-400 font-medium">{subtext}</div>}

          {trend && (
            <div className="flex items-center gap-1.5 text-[10px] font-semibold mt-2">
              <span className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded ${trend === 'up' ? 'text-emerald-700 bg-emerald-50' : trend === 'down' ? 'text-red-700 bg-red-50' : 'text-[#0b74b1] bg-blue-50'}`}>
                {trend === 'up' ? '▲' : trend === 'down' ? '▼' : '●'} {trendValue}
              </span>
              <span className="text-gray-400">{trendLabel}</span>
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

  const delayedProjectList = useMemo(() => {
    return projects.filter((p: any) => p.p6?.health === 'Delayed').slice(0, 5);
  }, [projects]);

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
    tooltip: { trigger: 'item', formatter: (p: any) => `<strong>${p.data[2]}</strong><br/>Progress: ${p.data[0]}%<br/>Capacity: ${Number(p.data[1]).toFixed(1)} MW` },
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
      data: projects.map((p: any) => ({ ...p, extractedCap: getProjectCapacity(p) })).filter((p: any) => p.extractedCap > 0).map((p: any) => [Math.round(p.p6?.progress || 0), parseFloat(p.extractedCap.toFixed(1)), p.p6_project_name || p.project_name])
    }]
  };

  const queueScatterOptions = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'inherit' },
    tooltip: { trigger: 'item', formatter: (p: any) => `<strong>${p.data[2]}</strong><br/>Progress: ${Number(p.data[0]).toFixed(1)}%<br/>Capacity: ${Number(p.data[1]).toFixed(1)} MW<br/>Status: ${p.data[3]}${p.data[4] > 0 ? ` (${p.data[4]} days delayed)` : ''}` },
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
        return [p.p6?.progress || 0, parseFloat(p.extractedCap.toFixed(1)), p.p6_project_name || p.project_name, p.p6?.health || 'On Track', delayDays];
      })
    }]
  };

  return (
    <div className="flex flex-col gap-4 w-full pb-8">

      {/* ROW 1: All 6 KPIs in a single row on desktop */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-3"
      >
        <KPICard title="Total Projects" value={totalProjects} trend="up" trendValue={onTrackProjects} trendLabel="On Track" icon={Activity} color="blue" onClick={() => setActiveKpiModal('Total Projects')} />
        <KPICard title="Portfolio Capacity" value={`${Math.round(totalMW)} MW`} icon={Zap} color="emerald" onClick={() => setActiveKpiModal('Portfolio Capacity')} />
        <KPICard title="Delayed Projects" value={delayedProjects} icon={AlertTriangle} color="red" onClick={() => setActiveKpiModal('Delayed Projects')} />
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
                <Bot className="w-4 h-4 text-[#0b74b1]" />
                <h3 className="text-[14px] font-bold text-gray-900 dark:text-white">Executive Intelligence Brief</h3>
              </div>
              <div className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> {briefing?.confidenceScore || 87}%
              </div>
            </div>

            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4 border border-gray-100 dark:border-gray-800">
              <div className="flex justify-between items-center mb-3">
                <div className="flex items-center gap-1.5 text-[10px] font-bold text-gray-400 uppercase tracking-[0.08em]">
                  <Zap className="w-3 h-3 text-[#0b74b1]" /> AI-GENERATED SUMMARY
                </div>
                <div className="text-[9px] font-medium text-gray-400 uppercase tracking-[0.08em]">
                  Generated Live
                </div>
              </div>

              <div className="mt-2">
                {briefingLoading ? (
                  <div className="flex items-center gap-3 py-6 text-primary text-sm font-medium justify-center">
                    <RefreshCw className="w-5 h-5 animate-spin" /> Analyzing live SAP & P6 data...
                  </div>
                ) : briefingError ? (
                  <div className="text-sm text-red-500 font-medium py-4 flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" /> {briefingError}
                  </div>
                ) : (
                  <>
                    <p className="text-[13px] text-gray-700 dark:text-gray-300 leading-relaxed">
                      {briefing?.toplineSummary || "Insufficient data to generate portfolio summary."}
                    </p>
                    <div className="flex items-center gap-2 mt-4 flex-wrap">
                      {briefing?.keyActions?.map((a: any, i: number) => {
                        const isRed = a.title.toLowerCase().includes('risk') || a.color === 'red';
                        const isAmber = a.title.toLowerCase().includes('cost') || a.color === 'amber' || a.title.toLowerCase().includes('monitor');
                        const colorTheme = isRed ? 'text-red-700 bg-red-50 border-red-100 dark:text-red-400 dark:bg-red-500/10 dark:border-red-500/20' :
                          isAmber ? 'text-amber-700 bg-amber-50 border-amber-100 dark:text-amber-400 dark:bg-amber-500/10 dark:border-amber-500/20' :
                            'text-emerald-700 bg-emerald-50 border-emerald-100 dark:text-emerald-400 dark:bg-emerald-500/10 dark:border-emerald-500/20';

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

          <motion.div variants={itemVariants} initial="hidden" animate="show" className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm p-6 flex-1 flex flex-col min-h-[450px]">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-6">
              <h4 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-primary" /> Project Execution Queue
              </h4>
              <div className="flex bg-gray-100 dark:bg-gray-800 p-1 border border-gray-200 dark:border-gray-700 rounded-lg text-xs font-semibold">
                <button onClick={() => setActiveListTab('top')} className={`px-4 py-1.5 rounded-md transition-all ${activeListTab === 'top' ? 'bg-white dark:bg-gray-700 text-primary shadow-sm' : 'text-gray-500 hover:text-gray-900 dark:hover:text-white'}`}>All</button>
                <button onClick={() => setActiveListTab('low')} className={`px-4 py-1.5 rounded-md transition-all ${activeListTab === 'low' ? 'bg-white dark:bg-gray-700 text-amber-500 shadow-sm' : 'text-gray-500 hover:text-gray-900 dark:hover:text-white'}`}>&lt; 50%</button>
                <button onClick={() => setActiveListTab('delayed')} className={`px-4 py-1.5 rounded-md transition-all ${activeListTab === 'delayed' ? 'bg-white dark:bg-gray-700 text-red-500 shadow-sm' : 'text-gray-500 hover:text-gray-900 dark:hover:text-white'}`}>Delayed</button>
              </div>
            </div>
            <div className="flex justify-end items-center gap-5 px-2 mb-2 text-xs font-medium text-gray-600 dark:text-gray-400">
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
              <h3 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-2"><Layers className="w-5 h-5 text-primary" /> Progress Stage</h3>
              <div className="text-[11px] font-bold text-gray-500 uppercase bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded-md">{totalProjects} total</div>
            </div>
            <div className="space-y-5 text-xs font-semibold">
              {[
                { phase: 'Initiation (0-25%)', count: progressStages.initiation, color: 'bg-gray-400' },
                { phase: 'Early (26-50%)', count: progressStages.early, color: 'bg-blue-400' },
                { phase: 'Mid (51-75%)', count: progressStages.mid, color: 'bg-amber-400' },
                { phase: 'Late (76-99%)', count: progressStages.late, color: 'bg-primary' },
                { phase: 'Completed (100%)', count: progressStages.completed, color: 'bg-emerald-500' }
              ].map((p, i) => (
                <div key={i} className="flex items-center justify-between group">
                  <div className="w-32 text-gray-500 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">{p.phase}</div>
                  <div className="flex-1 h-2.5 bg-gray-100 dark:bg-gray-800 rounded-full mx-4 overflow-hidden"><div className={`h-full ${p.color}`} style={{ width: `${(p.count / Math.max(1, totalProjects)) * 100}%` }}></div></div>
                  <div className="w-6 text-right text-gray-900 dark:text-white">{p.count}</div>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div variants={itemVariants} initial="hidden" animate="show" className="bento-card p-6 flex-1 overflow-hidden flex flex-col">
            <h3 className="text-sm font-bold text-gray-900 dark:text-white flex items-center justify-between mb-4 shrink-0">
              <span className="flex items-center gap-2"><Activity className="w-5 h-5 text-primary" /> Transmission Network</span>
            </h3>
            <div className="space-y-1 overflow-y-auto custom-scrollbar pr-2 flex-1">
              {transmissionOverview.map((node, i) => (
                <div key={i} className="flex justify-between items-center py-3 border-b border-gray-100 dark:border-gray-800 last:border-0 text-sm">
                  <div className="flex items-center gap-2.5 text-gray-700 dark:text-gray-300 font-semibold flex-1 pr-2">
                    <Zap className={`w-4 h-4 text-emerald-500 shrink-0`} />
                    <span className="line-clamp-1" title={node.key}>{node.key}</span>
                  </div>
                  <div className="text-[11px] font-bold text-gray-500 bg-gray-50 dark:bg-gray-800/50 px-2.5 py-1 rounded-md shrink-0 border border-gray-200 dark:border-gray-700">{node.count} Nodes</div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>

      {/* ROW 4: Alerts, Timeline */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* Risk Alerts */}
        <motion.div variants={itemVariants} initial="hidden" animate="show" className="bento-card p-6 overflow-hidden">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-2"><AlertTriangle className="w-5 h-5 text-red-500" /> Delayed Projects</h3>
            <div className="px-2.5 py-1 rounded-md bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400 text-[10px] font-bold uppercase border border-red-100 dark:border-red-500/20">{delayedProjects} Active</div>
          </div>
          <div className="space-y-4">
            {delayedProjectList.length > 0 ? delayedProjectList.map((p: any, i: number) => (
              <div key={i} className="flex items-start gap-4 p-3 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group border border-transparent hover:border-gray-200 dark:hover:border-gray-700">
                <div className="w-2.5 h-2.5 mt-1.5 rounded-full shrink-0 bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]"></div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-start mb-1.5 gap-2">
                    <div className="text-[13px] font-bold text-gray-900 dark:text-white leading-snug group-hover:text-primary transition-colors line-clamp-2 break-all" title={p.p6_project_name || p.project_name}>
                      {p.p6_project_name || p.project_name}
                    </div>
                    <div className="text-[10px] font-bold text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700 shrink-0">
                      {Math.round((p.p6?.progress || 0) * 100)}%
                    </div>
                  </div>
                  <div className="text-[11px] text-gray-500 flex justify-between items-center bg-gray-50 dark:bg-gray-800/30 px-3 py-2 rounded-lg border border-gray-100 dark:border-gray-800">
                    <span className="truncate pr-2"><span className="font-semibold text-gray-700 dark:text-gray-300">Plan:</span> {(p.p6?.planned_finish_date || p.p6?.scheduled_finish_date) ? new Date(p.p6.planned_finish_date || p.p6.scheduled_finish_date).toLocaleDateString() : 'N/A'}</span>
                    <span className="text-red-600 dark:text-red-400 font-medium flex items-center gap-1 shrink-0"><Clock className="w-3 h-3" /> <span className="font-semibold">Cur:</span> {p.p6?.finish_date ? new Date(p.p6.finish_date).toLocaleDateString() : 'N/A'}</span>
                  </div>
                </div>
              </div>
            )) : (
              <div className="text-sm text-gray-500 flex items-center justify-center h-32 bg-gray-50 dark:bg-gray-800/30 rounded-xl border border-dashed border-gray-200 dark:border-gray-700">No delayed projects found in current data.</div>
            )}
          </div>
        </motion.div>

        {/* Upcoming Deadlines / Timeline */}
        <motion.div variants={itemVariants} initial="hidden" animate="show" className="bento-card p-6">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-2"><Clock className="w-5 h-5 text-primary" /> Upcoming Finish Dates</h3>
          </div>
          <div className="space-y-4">
            {[...projects].filter((p: any) => p.p6?.finish_date && new Date(p.p6.finish_date).getTime() > Date.now()).sort((a, b) => new Date(a.p6.finish_date).getTime() - new Date(b.p6.finish_date).getTime()).slice(0, 5).map((p: any, i: number) => (
              <div key={i} className="flex gap-4 p-2 hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-lg transition-colors group">
                <div className="w-16 text-[10px] text-gray-500 font-bold pt-1 shrink-0 uppercase tracking-[0.08em] text-right">
                  {new Date(p.p6.finish_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                </div>
                <div className="relative border-l-2 border-gray-200 dark:border-gray-700 pl-4 pb-2 flex-1 min-w-0">
                  <div className={`absolute -left-[5px] top-2 w-2 h-2 rounded-full ${(p.p6?.progress || 0) * 100 > 90 ? 'bg-emerald-500' : 'bg-primary'} ring-4 ring-white dark:ring-gray-900 group-hover:scale-150 transition-transform`}></div>
                  <div className="text-[13px] text-gray-900 dark:text-white font-bold leading-tight pt-0.5 mb-1.5 group-hover:text-primary transition-colors line-clamp-2 break-all" title={p.p6_project_name || p.project_name}>
                    {p.p6_project_name || p.project_name}
                  </div>
                  <div className="text-[11px] text-gray-500 flex items-center gap-3">
                    <span className="flex items-center gap-1"><Zap className="w-3 h-3 text-gray-400" /> <span className="text-gray-700 dark:text-gray-300 font-semibold">{p.capacity_mwac || 0} MW</span></span>
                    <span className="flex items-center gap-1"><Activity className="w-3 h-3 text-gray-400" /> <span className="text-gray-700 dark:text-gray-300 font-semibold">{Math.round((p.p6?.progress || 0) * 100)}%</span></span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* ROW 4: ECharts */}
      <motion.div variants={itemVariants} initial="hidden" animate="show" className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bento-card p-4 flex flex-col h-[350px]">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-2"><Package className="w-5 h-5 text-primary" /> SAP Material Pipeline (Qty)</h3>
          </div>
          <div className="flex-1 w-full">
            <ReactECharts option={costChartOptions} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        <div className="bento-card p-4 flex flex-col h-[350px]">
          <h3 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-2 mb-4"><Activity className="w-5 h-5 text-primary" /> Progress vs Capacity Distribution</h3>
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
      />
    </div>
  );
}
