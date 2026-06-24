import React, { useState } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  Activity, TrendingUp, AlertTriangle, Layers, Wifi, Bell,
  CheckCircle2, Clock, Calendar, XCircle, ArrowUpRight, ArrowDownRight, Minus, Shield, LayoutDashboard, ChevronDown, ChevronRight
} from 'lucide-react';

export default function PMAGOverview({
  summary,
  filteredProjects,
  sv_chart,
  critical_path,
  dpr_tracker,
  connectivity,
  alerts,
  theme
}: any) {
  const isDark = theme === 'dark';

  const [expandedGroups, setExpandedGroups] = useState<string[]>([]);

  const toggleGroup = (eps: string) => {
    setExpandedGroups(prev => 
      prev.includes(eps) ? prev.filter(g => g !== eps) : [...prev, eps]
    );
  };

  const groupedProjects = React.useMemo(() => {
    const groups: Record<string, any> = {};
    filteredProjects.forEach((p: any) => {
      const eps = p.eps || 'Unknown EPS';
      if (!groups[eps]) {
        groups[eps] = {
          eps,
          projects: [],
          total: 0,
          total_pct: 0,
          on_track: 0,
          at_risk: 0,
          delayed: 0
        };
      }
      groups[eps].projects.push(p);
      groups[eps].total += 1;
      groups[eps].total_pct += (p.pct_complete || 0);
      
      if (p.rag === 'green') groups[eps].on_track += 1;
      else if (p.rag === 'amber') groups[eps].at_risk += 1;
      else groups[eps].delayed += 1;
    });

    return Object.values(groups).map((g: any) => ({
      ...g,
      avg_pct: g.total > 0 ? (g.total_pct / g.total).toFixed(1) : 0
    })).sort((a: any, b: any) => b.total - a.total);
  }, [filteredProjects]);

  const svChartOption = {
    tooltip: { trigger: 'axis', backgroundColor: isDark ? 'rgba(17,24,39,0.95)' : 'rgba(255,255,255,0.95)', borderColor: isDark ? '#374151' : '#e5e7eb', textStyle: { color: isDark ? '#f1f5f9' : '#374151', fontSize: 11 }, borderRadius: 8, extraCssText: 'box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);' },
    legend: { bottom: 0, textStyle: { color: '#6b7280', fontSize: 11, fontWeight: 600 }, icon: 'circle' },
    grid: { top: 20, left: 10, right: 20, bottom: 40, containLabel: true },
    xAxis: { type: 'category', data: sv_chart.map((d: any) => d.name.substring(0, 20)), axisLabel: { color: '#9ca3af', fontSize: 9, rotate: 35 }, axisLine: { lineStyle: { color: isDark ? '#374151' : '#e5e7eb' } } },
    yAxis: { type: 'value', name: '% Complete', axisLabel: { color: '#9ca3af' }, splitLine: { lineStyle: { type: 'dashed', color: isDark ? '#1f2937' : '#f3f4f6' } } },
    series: [
      { name: 'Planned', type: 'bar', data: sv_chart.map(() => 100), barWidth: 10, itemStyle: { color: isDark ? '#1f2937' : '#e5e7eb', borderRadius: [3, 3, 0, 0] } },
      {
        name: 'Actual', type: 'bar', barWidth: 10,
        data: sv_chart.map((d: any) => ({
          value: d.actual,
          itemStyle: { color: d.rag === 'red' ? '#ef4444' : d.rag === 'amber' ? '#f59e0b' : '#10b981', borderRadius: [3, 3, 0, 0] }
        })),
      },
    ],
  };

  const ragBadge = (rag: string) => {
    const cls: Record<string, string> = {
      green: 'risk-badge-low', amber: 'risk-badge-medium', red: 'risk-badge-high', grey: 'text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700',
    };
    const labels: Record<string, string> = { green: 'On Track', amber: 'At Risk', red: 'Delayed', grey: 'N/A' };
    return <span className={cls[rag] || cls.grey}>{labels[rag] || 'N/A'}</span>;
  };

  return (
    <div className="space-y-4">
      {/* ─── 1. Portfolio Summary KPIs ─── */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {[
          { label: 'Total Projects', value: summary.total_projects, icon: LayoutDashboard, accent: 'text-[#0b74b1]', bg: 'bg-[#0b74b1]/10' },
          { label: 'On Track', value: summary.on_track, icon: CheckCircle2, accent: 'text-emerald-600', bg: 'bg-emerald-500/10' },
          { label: 'At Risk', value: summary.at_risk, icon: AlertTriangle, accent: 'text-amber-600', bg: 'bg-amber-500/10' },
          { label: 'Delayed', value: summary.delayed, icon: XCircle, accent: 'text-red-600', bg: 'bg-red-500/10' },
          { label: 'Avg Completion', value: `${summary.avg_completion}%`, icon: TrendingUp, accent: 'text-violet-600', bg: 'bg-violet-500/10' },
          { label: 'Due This Week', value: summary.milestones_due_this_week, icon: Calendar, accent: 'text-[#75479c]', bg: 'bg-[#75479c]/10' },
          { label: 'Overdue', value: summary.milestones_overdue, icon: Clock, accent: 'text-[#bc3860]', bg: 'bg-[#bc3860]/10' },
        ].map((kpi, i) => (
          <div key={i} className="bento-card p-4 group">
            <div className="flex items-center justify-between mb-2.5">
              <div className={`w-8 h-8 rounded-lg ${kpi.bg} flex items-center justify-center`}>
                <kpi.icon className={`w-4 h-4 ${kpi.accent}`} />
              </div>
            </div>
            <p className={`text-2xl font-black ${kpi.accent} leading-none mb-1`}>{kpi.value}</p>
            <p className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">{kpi.label}</p>
          </div>
        ))}
      </div>

      {/* ─── 2. Project Health Table ─── */}
      <div className="bento-card overflow-hidden">
        <div className="px-5 py-3.5 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#0b74b1]" />
            <h3 className="section-label !text-[12px] !text-gray-900 dark:!text-white">Project Health Table</h3>
          </div>
          <span className="text-[11px] font-bold text-gray-400">{filteredProjects.length} Projects</span>
        </div>
        <div className="overflow-x-auto max-h-[600px] overflow-y-auto custom-scrollbar">
          <table className="intel-table relative w-full">
            <thead className="sticky top-0 z-10 bg-card shadow-sm">
              <tr>
                <th className="w-8"></th>
                <th>Project Name / EPS</th>
                <th>Type</th>
                <th>% Complete</th>
                <th>Baseline Finish</th>
                <th>Actual Finish</th>
                <th>SV (Days)</th>
                <th>SPI</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {groupedProjects.map((group: any) => {
                const isExpanded = expandedGroups.includes(group.eps);
                return (
                  <React.Fragment key={`group-${group.eps}`}>
                    {/* Parent Row */}
                    <tr 
                      className="cursor-pointer bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors border-y border-gray-200 dark:border-gray-700 font-bold"
                      onClick={() => toggleGroup(group.eps)}
                    >
                      <td className="text-center w-8 text-gray-500">
                        {isExpanded ? <ChevronDown className="w-4 h-4 inline" /> : <ChevronRight className="w-4 h-4 inline" />}
                      </td>
                      <td colSpan={2} className="py-3">
                        <div className="flex items-center gap-2">
                          <span className="text-gray-900 dark:text-white uppercase tracking-wider text-[11px]">{group.eps}</span>
                          <span className="text-[10px] bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 px-1.5 py-0.5 rounded text-gray-500">{group.total} Projects</span>
                        </div>
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="w-14 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div className="h-full rounded-full bg-[#0b74b1]" style={{ width: `${Math.min(group.avg_pct, 100)}%` }} />
                          </div>
                          <span className="text-[11px] font-bold text-gray-600 dark:text-gray-300">{group.avg_pct}%</span>
                        </div>
                      </td>
                      <td colSpan={4}></td>
                      <td>
                        <div className="flex gap-1">
                          {group.on_track > 0 && <span className="risk-badge-low !px-1.5" title="On Track">{group.on_track}</span>}
                          {group.at_risk > 0 && <span className="risk-badge-medium !px-1.5" title="At Risk">{group.at_risk}</span>}
                          {group.delayed > 0 && <span className="risk-badge-high !px-1.5" title="Delayed">{group.delayed}</span>}
                        </div>
                      </td>
                    </tr>
                    
                    {/* Child Rows */}
                    {isExpanded && group.projects.map((p: any, i: number) => (
                      <tr key={`child-${group.eps}-${i}`} className="cursor-pointer hover:bg-gray-50/50 dark:hover:bg-gray-800/30">
                        <td></td>
                        <td className="pl-6"><span className="font-semibold text-gray-700 dark:text-gray-300 truncate max-w-[200px] block" title={p.name}>{p.name}</span></td>
                        <td className="font-medium text-gray-500">{p.type}</td>
                        <td>
                          <div className="flex items-center gap-2">
                            <div className="w-14 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                              <div className={`h-full rounded-full ${p.rag === 'green' ? 'bg-emerald-500' : p.rag === 'amber' ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${Math.min(p.pct_complete, 100)}%` }} />
                            </div>
                            <span className="text-[11px] font-bold text-gray-600 dark:text-gray-300">{p.pct_complete}%</span>
                          </div>
                        </td>
                        <td className="text-gray-500">{p.baseline_finish || '-'}</td>
                        <td className="text-gray-500">{p.actual_finish || '-'}</td>
                        <td>
                          <span className={`font-bold flex items-center gap-1 ${p.sv_days === null ? 'text-gray-400' : p.sv_days >= 0 ? 'text-emerald-600' : p.sv_days >= -7 ? 'text-amber-600' : 'text-red-600'}`}>
                            {p.sv_days === null ? <Minus className="w-3 h-3" /> : p.sv_days >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                            {p.sv_days !== null ? `${p.sv_days > 0 ? '+' : ''}${p.sv_days}d` : '-'}
                          </span>
                        </td>
                        <td className="font-bold text-gray-600 dark:text-gray-300">{p.spi || '-'}</td>
                        <td>{ragBadge(p.rag)}</td>
                      </tr>
                    ))}
                  </React.Fragment>
                );
              })}
              {groupedProjects.length === 0 && (
                <tr>
                  <td colSpan={9} className="text-center py-6 text-gray-500">No projects found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── Row: Schedule Variance + Critical Path ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 3. Schedule Variance Chart */}
        <div className="bento-card p-5 flex flex-col h-[400px]">
          <h3 className="section-label !text-[12px] !text-gray-900 dark:!text-white mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-[#0b74b1]" /> Schedule Variance
          </h3>
          <div className="flex-1 min-h-0">
            <ReactECharts option={svChartOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        {/* 4. Critical Path Panel */}
        <div className="bento-card p-5 flex flex-col h-[400px]">
          <div className="flex items-center justify-between mb-3">
            <h3 className="section-label !text-[12px] !text-gray-900 dark:!text-white flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" /> Critical Path Activities
            </h3>
            <span className="text-[10px] font-bold text-gray-400">{critical_path.length} items</span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-2 custom-scrollbar">
            {critical_path.length === 0 ? (
              <div className="flex items-center justify-center h-full text-sm text-gray-400">No critical path items</div>
            ) : critical_path.map((cp: any, i: number) => (
              <div key={i} className="p-3 rounded-lg bg-gray-50 dark:bg-slate-800/50 border border-gray-100 dark:border-slate-700/40 hover:border-amber-200 dark:hover:border-amber-500/30 transition-colors">
                <div className="flex items-start justify-between mb-1">
                  <p className="text-[12px] font-bold text-gray-900 dark:text-white truncate max-w-[70%]">{cp.project}</p>
                  <span className={cp.impact === 'High' ? 'risk-badge-high' : cp.impact === 'Medium' ? 'risk-badge-medium' : 'risk-badge-low'}>{cp.impact}</span>
                </div>
                <p className="text-[11px] text-gray-500 mb-1">{cp.activity}</p>
                <div className="flex items-center gap-4 text-[10px] text-gray-400 font-medium">
                  <span>Planned: {cp.planned_date}</span>
                  <span className="text-red-500 font-bold">Delay: {cp.delay_days}d</span>
                  {cp.cascades_to_milestone && (
                    <span className="text-red-600 flex items-center gap-1"><Shield className="w-3 h-3" /> Cascades</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── Row: DPR Tracker + Connectivity ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 5. DPR Submission Tracker */}
        <div className="bento-card p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="section-label !text-[12px] !text-gray-900 dark:!text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-violet-500" /> DPR Submission Tracker
            </h3>
            <span className="text-[10px] font-bold text-gray-400">Last 7 Days</span>
          </div>
          <div className="overflow-x-auto">
            <table className="intel-table">
              <thead>
                <tr>
                  <th>Site</th>
                  {dpr_tracker[0]?.days.map((d: any, i: number) => (
                    <th key={i} className="text-center">{d.day}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dpr_tracker.map((site: any, i: number) => (
                  <tr key={i}>
                    <td className="font-bold truncate max-w-[150px]">{site.project}</td>
                    {site.days.map((d: any, j: number) => (
                      <td key={j} className="text-center">
                        <div className={`w-5 h-5 rounded-md mx-auto ${d.status === 'submitted' ? 'bg-emerald-500' : d.status === 'pending' ? 'bg-amber-400' : 'bg-red-400'}`} title={`${d.date}: ${d.status}`} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 6. Connectivity Readiness */}
        <div className="bento-card p-5">
          <h3 className="section-label !text-[12px] !text-gray-900 dark:!text-white mb-3 flex items-center gap-2">
            <Wifi className="w-4 h-4 text-[#0b74b1]" /> Connectivity Readiness
          </h3>
          <div className="overflow-x-auto max-h-[280px] overflow-y-auto custom-scrollbar">
            <table className="intel-table">
              <thead className="sticky top-0 z-10">
                <tr>
                  {['Project', 'MW', 'SCD Status', 'ECOD', 'Risk'].map(h => <th key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {connectivity.map((c: any, i: number) => (
                  <tr key={i}>
                    <td className="font-bold truncate max-w-[140px]">{c.project}</td>
                    <td>{c.mw}</td>
                    <td>
                      <span className={c.scd_status?.toLowerCase().includes('completed') || c.scd_status?.toLowerCase().includes('commissioned') ? 'risk-badge-low' : 'risk-badge-medium'}>
                        {c.scd_status}
                      </span>
                    </td>
                    <td className="text-gray-500">{c.ecod_projection}</td>
                    <td>
                      {c.delay_risk ? <AlertTriangle className="w-4 h-4 text-amber-500" /> : <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ─── 7. Alerts & Notifications ─── */}
      <div className="bento-card p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="section-label !text-[12px] !text-gray-900 dark:!text-white flex items-center gap-2">
            <Bell className="w-4 h-4 text-[#bc3860]" /> Alerts & Notifications
          </h3>
          <span className="text-[10px] font-bold text-gray-400">{alerts.length} alerts</span>
        </div>
        <div className="space-y-2 max-h-[300px] overflow-y-auto custom-scrollbar">
          {alerts.length === 0 ? (
            <p className="text-center text-sm text-gray-400 py-8">No active alerts</p>
          ) : alerts.map((a: any, i: number) => (
            <div key={i} className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${a.severity === 'high' ? 'bg-red-50/50 border-red-100 dark:bg-red-500/5 dark:border-red-500/20' : 'bg-amber-50/50 border-amber-100 dark:bg-amber-500/5 dark:border-amber-500/20'}`}>
              <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${a.severity === 'high' ? 'bg-red-500' : 'bg-amber-500'}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[12px] font-bold text-gray-900 dark:text-white truncate">{a.project}</span>
                  <span className={a.severity === 'high' ? 'risk-badge-high' : 'risk-badge-medium'}>{a.type}</span>
                </div>
                <p className="text-[11px] text-gray-500">{a.message}</p>
              </div>
              <span className="text-[9px] text-gray-400 font-medium whitespace-nowrap">{a.timestamp}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
