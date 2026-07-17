import React, { useState, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  Activity, TrendingUp, AlertTriangle, Layers, Wifi, Bell,
  CheckCircle2, Clock, Calendar, XCircle, ArrowUpRight, ArrowDownRight, Minus, Shield, LayoutDashboard, ChevronDown, ChevronRight,
  BrainCircuit, LayoutGrid, List, Info, Zap, Target
} from 'lucide-react';

export default function PMAGOverview({
  summary,
  filteredProjects,
  sv_chart,
  critical_path,
  dpr_tracker,
  connectivity,
  alerts,
  theme,
  onOpenProject
}: any) {
  const isDark = theme === 'dark';

  const [expandedGroups, setExpandedGroups] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<'map' | 'list'>('map');

  const toggleGroup = (eps: string) => {
    setExpandedGroups(prev => 
      prev.includes(eps) ? prev.filter(g => g !== eps) : [...prev, eps]
    );
  };

  const groupedProjects = useMemo(() => {
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

  // ─── Scatter Plot Option (Portfolio Heatmap) ───
  const scatterOption = useMemo(() => {
    const dataGreen: any[] = [];
    const dataAmber: any[] = [];
    const dataRed: any[] = [];

    filteredProjects.forEach((p: any) => {
      // x: planned, y: actual, size: random representation of budget/scale
      const x = p.planned_pct || Math.min(100, (p.pct_complete || 0) + Math.random() * 20);
      const y = p.pct_complete || 0;
      const size = Math.max(8, Math.min(25, (p.activity_count || 100) / 10)); // Reduced bubble sizes for elegance
      const pt = { name: p.name, value: [x, y, size, p.project_id] };
      
      if (p.rag === 'green') dataGreen.push(pt);
      else if (p.rag === 'amber') dataAmber.push(pt);
      else dataRed.push(pt);
    });

    return {
      backgroundColor: 'transparent',
      animationDuration: 1500,
      animationEasing: 'cubicOut',
      tooltip: {
        backgroundColor: isDark ? 'rgba(17,24,39,0.95)' : 'rgba(255,255,255,0.95)',
        borderColor: isDark ? '#374151' : '#e5e7eb',
        textStyle: { color: isDark ? '#f1f5f9' : '#374151', fontSize: 12 },
        borderRadius: 12,
        padding: 12,
        extraCssText: 'box-shadow: 0 10px 25px -5px rgba(0,0,0,0.2); backdrop-filter: blur(12px); z-index: 9999; border: 1px solid rgba(255,255,255,0.1);',
        formatter: (params: any) => {
          const d = params.data;
          return `
            <div style="font-weight: 800; margin-bottom: 8px; font-size: 13px; letter-spacing: -0.3px;">${d.name}</div>
            <div style="display: flex; justify-content: space-between; gap: 24px; font-size: 11px; margin-bottom: 4px;">
              <span style="color: #6b7280; font-weight: 500;">Planned</span> <span style="font-weight: 700;">${d.value[0].toFixed(1)}%</span>
            </div>
            <div style="display: flex; justify-content: space-between; gap: 24px; font-size: 11px; margin-bottom: 8px;">
              <span style="color: #6b7280; font-weight: 500;">Actual</span> <span style="font-weight: 700;">${d.value[1].toFixed(1)}%</span>
            </div>
            <div style="padding-top: 8px; border-top: 1px solid ${isDark ? '#374151' : '#e5e7eb'}; font-size: 10px; color: #3b82f6; font-weight: 600;">View Workspace →</div>
          `;
        }
      },
      legend: { top: 0, textStyle: { color: isDark ? '#9ca3af' : '#6b7280', fontWeight: 600, fontSize: 11 }, icon: 'circle', itemGap: 20 },
      grid: { top: 45, left: 20, right: 30, bottom: 40, containLabel: true },
      xAxis: {
        type: 'value', name: 'Planned %', nameLocation: 'middle', nameGap: 28,
        nameTextStyle: { color: isDark ? '#6b7280' : '#9ca3af', fontSize: 10, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 1 },
        axisLabel: { color: isDark ? '#6b7280' : '#9ca3af', fontWeight: 500, fontSize: 10 },
        splitLine: { show: true, lineStyle: { type: 'dashed', color: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)' } },
        axisLine: { lineStyle: { color: isDark ? '#374151' : '#e5e7eb' } }
      },
      yAxis: {
        type: 'value', name: 'Actual %', nameLocation: 'middle', nameGap: 35,
        nameTextStyle: { color: isDark ? '#6b7280' : '#9ca3af', fontSize: 10, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 1 },
        axisLabel: { color: isDark ? '#6b7280' : '#9ca3af', fontWeight: 500, fontSize: 10 },
        splitLine: { show: true, lineStyle: { type: 'dashed', color: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)' } },
        axisLine: { lineStyle: { color: isDark ? '#374151' : '#e5e7eb' } }
      },
      series: [
        {
          name: 'On Track', type: 'scatter', data: dataGreen,
          itemStyle: { 
            color: 'rgba(16,185,129,0.7)', 
            borderColor: '#10b981',
            borderWidth: 1.5,
            shadowBlur: 15, 
            shadowColor: 'rgba(16,185,129,0.4)' 
          },
          symbolSize: (data: any) => data[2]
        },
        {
          name: 'At Risk', type: 'scatter', data: dataAmber,
          itemStyle: { 
            color: 'rgba(245,158,11,0.7)', 
            borderColor: '#f59e0b',
            borderWidth: 1.5,
            shadowBlur: 15, 
            shadowColor: 'rgba(245,158,11,0.4)' 
          },
          symbolSize: (data: any) => data[2]
        },
        {
          name: 'Delayed', type: 'scatter', data: dataRed,
          itemStyle: { 
            color: 'rgba(239,68,68,0.6)', 
            borderColor: '#ef4444',
            borderWidth: 1.5,
            shadowBlur: 15, 
            shadowColor: 'rgba(239,68,68,0.4)' 
          },
          symbolSize: (data: any) => data[2]
        },
        // Health Zones Background
        {
          type: 'line', 
          markArea: {
            silent: true,
            data: [
              [ { xAxis: 0, yAxis: 0 }, { xAxis: 100, yAxis: 100 } ]
            ],
            itemStyle: {
              color: isDark ? 'rgba(239,68,68,0.02)' : 'rgba(239,68,68,0.03)' // Subtle red hue below the line (delayed zone)
            }
          }
        },
        // Identity line (Planned = Actual)
        {
          type: 'line', data: [[0,0], [100,100]],
          lineStyle: { type: 'dashed', color: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)', width: 2 },
          symbol: 'none', z: -1, silent: true
        }
      ]
    };
  }, [filteredProjects, isDark]);

  const onChartClick = (params: any) => {
    if (params.data && params.data.value && params.data.value[3]) {
      if (onOpenProject) onOpenProject(params.data.value[3]);
    }
  };

  // ─── Modern Schedule Variance Area Chart ───
  const svChartOption = useMemo(() => {
    return {
      tooltip: { 
        trigger: 'axis', 
        backgroundColor: isDark ? 'rgba(17,24,39,0.95)' : 'rgba(255,255,255,0.95)', 
        borderColor: isDark ? '#374151' : '#e5e7eb', 
        textStyle: { color: isDark ? '#f1f5f9' : '#374151', fontSize: 11 }, 
        borderRadius: 8, 
        extraCssText: 'box-shadow: 0 10px 25px -5px rgba(0,0,0,0.2); backdrop-filter: blur(8px);' 
      },
      legend: { top: 0, right: 0, textStyle: { color: isDark ? '#9ca3af' : '#6b7280', fontSize: 11, fontWeight: 600 }, icon: 'circle' },
      grid: { top: 40, left: 10, right: 20, bottom: 40, containLabel: true },
      xAxis: { 
        type: 'category', 
        data: sv_chart.map((d: any) => d.name.substring(0, 15)), 
        axisLabel: { color: isDark ? '#6b7280' : '#9ca3af', fontSize: 9, rotate: 30 }, 
        axisLine: { lineStyle: { color: isDark ? '#374151' : '#e5e7eb' } } 
      },
      yAxis: { 
        type: 'value', 
        splitLine: { lineStyle: { type: 'dashed', color: isDark ? '#1f2937' : '#f3f4f6' } },
        axisLabel: { color: isDark ? '#6b7280' : '#9ca3af' }
      },
      series: [
        { 
          name: 'Actual %', 
          type: 'line', 
          smooth: true,
          data: sv_chart.map((d: any) => d.actual),
          lineStyle: { width: 3, color: '#3b82f6' },
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [{ offset: 0, color: 'rgba(59,130,246,0.4)' }, { offset: 1, color: 'rgba(59,130,246,0.0)' }]
            }
          },
          itemStyle: { color: '#3b82f6' },
          symbol: 'circle',
          symbolSize: 6,
        },
        { 
          name: 'Planned %', 
          type: 'line', 
          smooth: true, 
          lineStyle: { width: 2, type: 'dashed', color: isDark ? '#6b7280' : '#9ca3af' },
          data: sv_chart.map(() => 100),
          itemStyle: { color: isDark ? '#6b7280' : '#9ca3af' },
          symbol: 'none'
        }
      ],
    };
  }, [sv_chart, isDark]);

  const ragBadge = (rag: string) => {
    const cls: Record<string, string> = {
      green: 'bg-success/10 text-success border border-success/20', 
      amber: 'bg-warning/10 text-warning border border-warning/20', 
      red: 'bg-destructive/10 text-destructive border border-destructive/20', 
      grey: 'bg-muted text-muted-foreground border border-border',
    };
    const labels: Record<string, string> = { green: 'On Track', amber: 'At Risk', red: 'Delayed', grey: 'N/A' };
    return <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${cls[rag] || cls.grey}`}>{labels[rag] || 'N/A'}</span>;
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* ─── 1. Executive Summary & AI Insights ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* KPI Sparkline Cards */}
        <div className="lg:col-span-3 grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Projects', value: summary.total_projects, icon: LayoutDashboard, accent: 'text-primary', border: 'border-primary/20', bg: 'bg-primary/5' },
            { label: 'On Track', value: summary.on_track, icon: CheckCircle2, accent: 'text-success', border: 'border-success/20', bg: 'bg-success/5' },
            { label: 'At Risk', value: summary.at_risk, icon: AlertTriangle, accent: 'text-warning', border: 'border-warning/20', bg: 'bg-warning/5' },
            { label: 'Delayed', value: summary.delayed, icon: XCircle, accent: 'text-destructive', border: 'border-destructive/20', bg: 'bg-destructive/5' },
          ].map((kpi, i) => (
            <div key={i} className={`relative p-5 rounded-2xl border ${kpi.border} ${kpi.bg} backdrop-blur-md overflow-hidden group hover:scale-[1.02] transition-transform duration-300`}>
              <div className="absolute -right-4 -top-4 w-24 h-24 rounded-full bg-background/50 blur-2xl group-hover:bg-background/80 transition-colors"></div>
              <div className="relative z-10 flex flex-col h-full justify-between">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">{kpi.label}</span>
                  <kpi.icon className={`w-4 h-4 ${kpi.accent} opacity-80`} />
                </div>
                <div className="flex items-end justify-between">
                  <p className={`text-3xl font-black ${kpi.accent} drop-shadow-sm`}>{kpi.value}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* AI Narrative Panel */}
        <div className="lg:col-span-1 relative rounded-2xl p-5 border border-primary/30 bg-gradient-to-br from-primary/10 via-brand-purple/5 to-transparent backdrop-blur-md overflow-hidden shadow-[0_8px_30px_rgba(59,130,246,0.1)]">
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/20 blur-3xl rounded-full"></div>
          <h3 className="relative z-10 text-[11px] font-black uppercase tracking-[0.2em] text-primary flex items-center gap-2 mb-3">
            <BrainCircuit className="w-4 h-4 animate-pulse" /> Copilot Insights
          </h3>
          <div className="relative z-10 space-y-2">
            <p className="text-[13px] text-foreground/90 leading-relaxed font-medium">
              Portfolio health is at <span className="text-success font-bold">{summary.avg_completion}%</span>.
            </p>
            <p className="text-[13px] text-foreground/90 leading-relaxed font-medium">
              Currently, <span className="text-destructive font-bold">{summary.delayed}</span> projects are delayed. 
              The primary bottleneck appears to be <span className="text-warning font-bold">Transmission Readiness</span> across the Solar portfolio. 
            </p>
            <div className="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1 bg-primary/10 text-primary rounded-md text-[10px] font-bold border border-primary/20 cursor-pointer hover:bg-primary/20 transition-colors">
              <Zap className="w-3 h-3" /> View Recommended Actions
            </div>
          </div>
        </div>
      </div>

      {/* ─── 2. Portfolio Visual Map / Grid Toggle ─── */}
      <div className="rounded-2xl border border-border bg-card/40 backdrop-blur-md shadow-sm overflow-hidden relative">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-gradient-to-r from-card/80 to-transparent">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <Target className="w-4 h-4 text-primary" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-foreground">Portfolio Health Map</h3>
              <p className="text-[11px] text-muted-foreground font-medium">{filteredProjects.length} Active Projects</p>
            </div>
          </div>
          
          <div className="flex items-center gap-1 bg-muted/50 p-1 rounded-lg border border-border">
            <button 
              onClick={() => setViewMode('map')} 
              className={`p-1.5 rounded-md flex items-center gap-2 text-xs font-semibold transition-all ${viewMode === 'map' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            >
              <LayoutGrid className="w-3.5 h-3.5" /> <span className="hidden sm:inline">Visual Map</span>
            </button>
            <button 
              onClick={() => setViewMode('list')} 
              className={`p-1.5 rounded-md flex items-center gap-2 text-xs font-semibold transition-all ${viewMode === 'list' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            >
              <List className="w-3.5 h-3.5" /> <span className="hidden sm:inline">Data Grid</span>
            </button>
          </div>
        </div>

        {viewMode === 'map' ? (
          <div className="h-[450px] w-full p-2 relative animate-in zoom-in-95 duration-300">
            {/* Background quadrants for aesthetic */}
            <div className="absolute inset-0 pointer-events-none opacity-20">
              <div className="absolute top-10 right-10 w-1/2 h-1/2 bg-success/5 rounded-bl-3xl border-l border-b border-success/20"></div>
              <div className="absolute bottom-10 right-10 w-1/2 h-1/2 bg-warning/5 rounded-tl-3xl border-l border-t border-warning/20"></div>
            </div>
            <ReactECharts option={scatterOption} style={{ height: '100%', width: '100%' }} onEvents={{ click: onChartClick }} />
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[500px] overflow-y-auto custom-scrollbar animate-in fade-in duration-300">
            <table className="intel-table relative w-full">
              <thead className="sticky top-0 z-10 bg-slate-50/95 dark:bg-gray-900/95 backdrop-blur-md shadow-sm">
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
                        className="cursor-pointer bg-muted/50 dark:bg-gray-900/30 hover:bg-muted dark:hover:bg-card transition-colors border-y border-border dark:border-gray-800 font-bold"
                        onClick={() => toggleGroup(group.eps)}
                      >
                        <td className="text-center w-8 text-muted-foreground">
                          {isExpanded ? <ChevronDown className="w-4 h-4 inline" /> : <ChevronRight className="w-4 h-4 inline" />}
                        </td>
                        <td colSpan={2} className="py-3">
                          <div className="flex items-center gap-2">
                            <span className="text-foreground dark:text-white uppercase tracking-wider text-[11px]">{group.eps}</span>
                            <span className="text-[10px] bg-card border border-border dark:border-gray-700 px-1.5 py-0.5 rounded text-muted-foreground shadow-sm">{group.total} Projects</span>
                          </div>
                        </td>
                        <td>
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden shadow-inner">
                              <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(group.avg_pct, 100)}%` }} />
                            </div>
                            <span className="text-[11px] font-bold text-foreground dark:text-muted-foreground">{group.avg_pct}%</span>
                          </div>
                        </td>
                        <td colSpan={4}></td>
                        <td>
                          <div className="flex gap-1.5">
                            {group.on_track > 0 && <span className="flex items-center justify-center w-5 h-5 rounded-md bg-success/10 text-success text-[10px] border border-success/20" title="On Track">{group.on_track}</span>}
                            {group.at_risk > 0 && <span className="flex items-center justify-center w-5 h-5 rounded-md bg-warning/10 text-warning text-[10px] border border-warning/20" title="At Risk">{group.at_risk}</span>}
                            {group.delayed > 0 && <span className="flex items-center justify-center w-5 h-5 rounded-md bg-destructive/10 text-destructive text-[10px] border border-destructive/20" title="Delayed">{group.delayed}</span>}
                          </div>
                        </td>
                      </tr>
                      
                      {/* Child Rows */}
                      {isExpanded && group.projects.map((p: any, i: number) => (
                        <tr key={`child-${group.eps}-${i}`} className="cursor-pointer hover:bg-slate-100/50 dark:hover:bg-gray-800/50 transition-colors" onClick={() => onOpenProject && onOpenProject(p.project_id)}>
                          <td></td>
                          <td className="pl-6"><span className="font-semibold text-foreground dark:text-gray-300 truncate max-w-[250px] block" title={p.name}>{p.name}</span></td>
                          <td className="font-medium text-muted-foreground text-[11px]">{p.type}</td>
                          <td>
                            <div className="flex items-center gap-2">
                              <div className="w-16 h-1.5 bg-muted dark:bg-gray-700 rounded-full overflow-hidden shadow-inner">
                                <div className={`h-full rounded-full ${p.rag === 'green' ? 'bg-success' : p.rag === 'amber' ? 'bg-warning' : 'bg-destructive'}`} style={{ width: `${Math.min(p.pct_complete, 100)}%` }} />
                              </div>
                              <span className="text-[11px] font-bold text-foreground dark:text-gray-400">{p.pct_complete}%</span>
                            </div>
                          </td>
                          <td className="text-muted-foreground text-[11px]">{p.baseline_finish || '-'}</td>
                          <td className="text-muted-foreground text-[11px]">{p.actual_finish || '-'}</td>
                          <td>
                            <span className={`font-bold text-[11px] flex items-center gap-1 ${p.sv_days === null ? 'text-muted-foreground' : p.sv_days >= 0 ? 'text-success' : p.sv_days >= -7 ? 'text-warning' : 'text-destructive'}`}>
                              {p.sv_days === null ? <Minus className="w-3 h-3" /> : p.sv_days >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                              {p.sv_days !== null ? `${p.sv_days > 0 ? '+' : ''}${p.sv_days}d` : '-'}
                            </span>
                          </td>
                          <td className="font-bold text-foreground dark:text-muted-foreground text-[11px]">{p.spi || '-'}</td>
                          <td>{ragBadge(p.rag)}</td>
                        </tr>
                      ))}
                    </React.Fragment>
                  );
                })}
                {groupedProjects.length === 0 && (
                  <tr>
                    <td colSpan={9} className="text-center py-10 text-muted-foreground font-medium">No projects found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ─── 3. Schedule Variance + Critical Path ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Schedule Variance Chart */}
        <div className="rounded-2xl border border-border bg-card/40 backdrop-blur-md shadow-sm p-5 flex flex-col h-[380px] hover:shadow-md transition-shadow">
          <h3 className="text-sm font-bold text-foreground flex items-center gap-2 mb-3">
            <TrendingUp className="w-4 h-4 text-primary" /> Progress Trajectory
          </h3>
          <div className="flex-1 min-h-0">
            <ReactECharts option={svChartOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        {/* Critical Path Panel */}
        <div className="rounded-2xl border border-border bg-card/40 backdrop-blur-md shadow-sm p-5 flex flex-col h-[380px] hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-warning" /> Critical Path Watchlist
            </h3>
            <span className="text-[10px] font-bold bg-muted px-2 py-1 rounded-md text-muted-foreground">{critical_path.length} At Risk</span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar pr-2">
            {critical_path.length === 0 ? (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">No critical path items</div>
            ) : critical_path.map((cp: any, i: number) => (
              <div key={i} className="p-3.5 rounded-xl bg-gradient-to-r from-muted/50 to-transparent border border-border/50 hover:border-warning/30 hover:bg-warning/5 transition-all group">
                <div className="flex items-start justify-between mb-2">
                  <p className="text-[12px] font-bold text-foreground dark:text-white truncate max-w-[70%] group-hover:text-warning transition-colors">{cp.project}</p>
                  <span className={`text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full ${cp.impact === 'High' ? 'bg-destructive/10 text-destructive border border-destructive/20' : cp.impact === 'Medium' ? 'bg-warning/10 text-warning border border-warning/20' : 'bg-success/10 text-success border border-success/20'}`}>
                    {cp.impact} IMPACT
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground mb-3 line-clamp-2">{cp.activity}</p>
                <div className="flex items-center gap-4 text-[10px] text-muted-foreground font-medium">
                  <span className="flex items-center gap-1.5"><Calendar className="w-3 h-3" /> {cp.planned_date}</span>
                  <span className="text-destructive font-bold flex items-center gap-1.5"><Clock className="w-3 h-3" /> Delayed {cp.delay_days}d</span>
                  {cp.cascades_to_milestone && (
                    <span className="text-destructive/80 flex items-center gap-1"><Shield className="w-3 h-3" /> Cascades</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── 4. DPR Tracker + Connectivity ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* DPR Submission Tracker */}
        <div className="rounded-2xl border border-border bg-card/40 backdrop-blur-md shadow-sm p-5 hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
              <Layers className="w-4 h-4 text-violet-500" /> DPR Submission Compliance
            </h3>
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-1 rounded-md">7-Day Trend</span>
          </div>
          <div className="overflow-x-auto custom-scrollbar">
            <table className="intel-table w-full">
              <thead>
                <tr>
                  <th className="bg-transparent text-muted-foreground text-[10px]">SITE</th>
                  {dpr_tracker[0]?.days.map((d: any, i: number) => (
                    <th key={i} className="text-center bg-transparent text-[9px] text-muted-foreground uppercase">{d.day}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dpr_tracker.map((site: any, i: number) => (
                  <tr key={i} className="hover:bg-muted/30 transition-colors border-b border-border/50 last:border-0">
                    <td className="font-bold text-[11px] text-foreground dark:text-gray-300 truncate max-w-[150px] py-2">{site.project}</td>
                    {site.days.map((d: any, j: number) => (
                      <td key={j} className="text-center py-2">
                        <div className={`w-4 h-4 rounded mx-auto shadow-sm ${d.status === 'submitted' ? 'bg-success' : d.status === 'pending' ? 'bg-warning' : 'bg-destructive'}`} title={`${d.date}: ${d.status}`} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Connectivity Readiness */}
        <div className="rounded-2xl border border-border bg-card/40 backdrop-blur-md shadow-sm p-5 hover:shadow-md transition-shadow">
          <h3 className="text-sm font-bold text-foreground flex items-center gap-2 mb-4">
            <Wifi className="w-4 h-4 text-primary" /> Connectivity Matrix
          </h3>
          <div className="overflow-x-auto max-h-[280px] overflow-y-auto custom-scrollbar">
            <table className="intel-table w-full">
              <thead className="sticky top-0 z-10 bg-slate-50/95 dark:bg-gray-900/95 backdrop-blur-md">
                <tr>
                  {['Project', 'MW', 'SCD Status', 'ECOD'].map(h => <th key={h} className="text-[10px] text-muted-foreground bg-transparent">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {connectivity.map((c: any, i: number) => (
                  <tr key={i} className="hover:bg-muted/30 transition-colors border-b border-border/50 last:border-0">
                    <td className="font-bold text-[11px] text-foreground dark:text-gray-300 truncate max-w-[120px] py-2.5">
                      <div className="flex items-center gap-2">
                        {c.delay_risk ? <AlertTriangle className="w-3 h-3 text-warning shrink-0" /> : <CheckCircle2 className="w-3 h-3 text-success shrink-0" />}
                        {c.project}
                      </div>
                    </td>
                    <td className="text-[11px] font-medium py-2.5">{c.mw}</td>
                    <td className="py-2.5">
                      <span className={`text-[9px] font-bold px-2 py-0.5 rounded-md border ${c.scd_status?.toLowerCase().includes('completed') || c.scd_status?.toLowerCase().includes('commissioned') ? 'bg-success/10 text-success border-success/20' : 'bg-warning/10 text-warning border-warning/20'}`}>
                        {c.scd_status}
                      </span>
                    </td>
                    <td className="text-muted-foreground text-[11px] py-2.5 font-mono">{c.ecod_projection}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

    </div>
  );
}
