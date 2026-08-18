import React, { useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Calendar, AlertTriangle, List, Layers, Box, Bell, ChevronRight, X, Activity } from 'lucide-react';

export default function P6View({ p6Data, loading }: any) {
  const [trackingMode, setTrackingMode] = useState<'activities' | 'materials'>('activities');
  const [viewNotifsProject, setViewNotifsProject] = useState<any>(null);

  // P6 specific data mapping
  const sortedByDelay = [...(p6Data || [])].sort((a, b) => a.finishDateVariance - b.finishDateVariance);
  const delayedProjects = sortedByDelay.filter(p => (p.finishDateVariance || 0) < 0);
  
  // Generate S-Curve Data
  // Generate S-Curve Data for Activities Completion
  const generateSCurveData = () => {
    if (!p6Data || p6Data.length === 0) return { months: [], baseline: [], actual: [], forecast: [] };

    let minT = Infinity;
    let maxT = -Infinity;
    const today = new Date();
    
    p6Data.forEach((p: any) => {
      const d1 = p.baseline_start_date ? new Date(p.baseline_start_date).getTime() : null;
      const d2 = p.baseline_finish_date ? new Date(p.baseline_finish_date).getTime() : null;
      const d3 = p.start_date ? new Date(p.start_date).getTime() : null;
      const d4 = p.scheduled_finish_date ? new Date(p.scheduled_finish_date).getTime() : null;
      const d5 = p.finish_date ? new Date(p.finish_date).getTime() : null;
      
      [d1, d2, d3, d4, d5, today.getTime()].forEach(d => {
        if (d && !isNaN(d)) {
          if (d < minT) minT = d;
          if (d > maxT) maxT = d;
        }
      });
    });

    if (minT === Infinity) return { months: [], baseline: [], actual: [], forecast: [] };

    const minDate = new Date(minT);
    const maxDate = new Date(maxT);

    const months: string[] = [];
    let current = new Date(minDate.getFullYear(), minDate.getMonth(), 1);
    const end = new Date(maxDate.getFullYear(), maxDate.getMonth(), 1);

    while (current <= end) {
      months.push(`${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, '0')}`);
      current.setMonth(current.getMonth() + 1);
    }

    const currentMonthStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;

    const baselineData: number[] = [];
    const actualData: (number | null)[] = [];
    const forecastData: number[] = [];

    // Helper to get linear interpolated value
    const getInterpolatedValue = (evalDateT: number, startT: number, endT: number, totalVal: number, startVal = 0) => {
        if (evalDateT < startT) return startVal;
        if (evalDateT >= endT || startT === endT) return totalVal;
        const progress = (evalDateT - startT) / (endT - startT);
        return startVal + (totalVal - startVal) * progress;
    };

    months.forEach(monthStr => {
      const [year, month] = monthStr.split('-');
      const monthEndDate = new Date(parseInt(year), parseInt(month), 0, 23, 59, 59);
      const evalT = monthEndDate.getTime();
      const todayT = today.getTime();

      let bSum = 0;
      let aSum = 0;
      let fSum = 0;

      p6Data.forEach((p: any) => {
          let totalAct = p.activity_count || 0;
          let compAct = p.completed_activity_count || 0;
          
          if (trackingMode === 'materials') {
            compAct = p.actual_non_labor_units || 0;
            // Estimate total material from percent complete if total is not available
            totalAct = compAct > 0 && p.duration_percent_complete ? compAct / p.duration_percent_complete : compAct;
            if (totalAct < compAct) totalAct = compAct;
          }
          
          // Baseline
          const bStart = p.baseline_start_date ? new Date(p.baseline_start_date).getTime() : null;
          const bEnd = p.baseline_finish_date ? new Date(p.baseline_finish_date).getTime() : null;
          if (bStart && bEnd) {
             bSum += getInterpolatedValue(evalT, bStart, bEnd, totalAct);
          } else if (bEnd && evalT >= bEnd) {
             bSum += totalAct;
          }

          // Actual (up to today)
          const aStart = p.start_date ? new Date(p.start_date).getTime() : null;
          if (aStart) {
             const actualEndT = Math.min(evalT, todayT);
             aSum += getInterpolatedValue(actualEndT, aStart, todayT, compAct);
          } else if (compAct > 0) {
             aSum += compAct;
          }

          // Forecast
          let fEnd = p.finish_date ? new Date(p.finish_date).getTime() : (p.scheduled_finish_date ? new Date(p.scheduled_finish_date).getTime() : null);
          
          if (fEnd !== null && fEnd <= todayT && compAct < totalAct) {
             // Project is delayed past its finish date but not complete.
             // Smooth the curve by estimating a new finish date based on historical run rate.
             if (compAct > 0 && aStart && todayT > aStart) {
                 const msPerAct = (todayT - aStart) / compAct;
                 fEnd = todayT + (totalAct - compAct) * msPerAct;
             } else {
                 fEnd = todayT + 180 * 24 * 60 * 60 * 1000; // 6 months buffer
             }
          }

          if (evalT <= todayT) {
              if (aStart) fSum += getInterpolatedValue(evalT, aStart, todayT, compAct);
              else if (compAct > 0) fSum += compAct;
          } else {
              if (fEnd && fEnd > todayT) fSum += getInterpolatedValue(evalT, todayT, fEnd, totalAct, compAct);
              else fSum += totalAct;
          }
      });

      baselineData.push(Math.round(bSum));
      forecastData.push(Math.round(fSum));
      
      if (monthStr <= currentMonthStr) {
        actualData.push(Math.round(aSum));
      } else {
        actualData.push(null);
      }
    });

    const monthLabels = months.map(m => {
      const [y, mo] = m.split('-');
      const date = new Date(parseInt(y), parseInt(mo) - 1, 1);
      return date.toLocaleDateString('default', { month: 'short', year: 'numeric' });
    });

    return { months: monthLabels, baseline: baselineData, actual: actualData, forecast: forecastData };
  };

  const sCurve = generateSCurveData();

  const scheduleOption = {
    tooltip: { 
      trigger: 'axis', 
      backgroundColor: 'rgba(0,0,0,0.8)', 
      textStyle: { color: '#fff' },
      valueFormatter: (value: any) => value != null ? new Intl.NumberFormat('en-US').format(value as number) : '-'
    },
    legend: { data: ['Baseline', 'Actual', 'Forecast'], textStyle: { color: '#9ca3af' }, bottom: 0, icon: 'circle' },
    grid: { left: '3%', right: '5%', bottom: '15%', top: '15%', containLabel: true },
    xAxis: { 
      type: 'category', 
      boundaryGap: false,
      data: sCurve.months,
      axisLine: { lineStyle: { color: '#4b5563' } }, 
      axisLabel: { color: '#9ca3af', rotate: 45, margin: 12 }, 
      splitLine: { show: false } 
    },
    yAxis: { 
      type: 'value', 
      name: trackingMode === 'activities' ? 'Cumulative Activities' : 'Cumulative Material Units',
      nameTextStyle: { color: '#9ca3af', padding: [0, 0, 10, 0] },
      axisLine: { lineStyle: { color: '#4b5563' } }, 
      axisLabel: { color: '#9ca3af', formatter: (value: number) => new Intl.NumberFormat('en-US', { notation: "compact", compactDisplay: "short" }).format(value) },
      splitLine: { lineStyle: { color: '#4b5563', opacity: 0.2 } } 
    },
    series: [
      { 
        name: 'Baseline', 
        type: 'line', 
        data: sCurve.baseline, 
        itemStyle: { color: '#0ea5e9' }, 
        lineStyle: { width: 3 }, 
        areaStyle: { color: 'rgba(14, 165, 233, 0.1)' },
        symbol: 'circle',
        symbolSize: 6,
        showSymbol: false,
        smooth: 0.4 
      },
      { 
        name: 'Actual', 
        type: 'line', 
        data: sCurve.actual, 
        itemStyle: { color: '#10b981' }, 
        lineStyle: { width: 3 }, 
        areaStyle: { color: 'rgba(16, 185, 129, 0.2)' },
        symbol: 'circle',
        symbolSize: 6,
        showSymbol: false,
        smooth: 0.4 
      },
      { 
        name: 'Forecast', 
        type: 'line', 
        data: sCurve.forecast, 
        itemStyle: { color: '#f59e0b' }, 
        lineStyle: { width: 3, type: 'dashed' }, 
        symbol: 'none',
        smooth: 0.4 
      }
    ]
  };



  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-10">
      
      <div className="flex flex-wrap gap-4">
         <div className="bg-card border border-border rounded-xl px-5 py-4 min-w-[220px] shadow-sm">
           <h3 className="text-muted-foreground text-[11px] font-medium mb-1 uppercase tracking-wider">Total Scheduled Projects</h3>
           <p className="text-3xl font-light text-foreground">{p6Data.length}</p>
         </div>
         <div className="bg-card border border-border rounded-xl px-5 py-4 min-w-[220px] shadow-sm">
           <h3 className="text-muted-foreground text-[11px] font-medium mb-1 uppercase tracking-wider">Projects Delayed {">"} 30 Days</h3>
           <p className="text-3xl font-light text-destructive">{delayedProjects.filter(p => (p.finishDateVariance || 0) < -30).length}</p>
         </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="col-span-1 lg:col-span-2 bg-card border border-border rounded-2xl p-6 min-h-[450px] shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-primary/10 rounded-lg"><Calendar className="w-5 h-5 text-primary" /></div>
                <h2 className="text-lg font-medium tracking-wide text-foreground">Schedule Progress</h2>
              </div>
              <div className="flex items-center p-1 bg-muted rounded-lg border border-border/50">
                <button 
                  onClick={() => setTrackingMode('activities')}
                  className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-all ${trackingMode === 'activities' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
                >
                  <Layers className="w-4 h-4" />
                  Construction Activities
                </button>
                <button 
                  onClick={() => setTrackingMode('materials')}
                  className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-all ${trackingMode === 'materials' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
                >
                  <Box className="w-4 h-4" />
                  Material Resources
                </button>
              </div>
            </div>
            <div className="w-full h-[350px]">
              <ReactECharts option={scheduleOption} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>


      </div>

      {/* Detailed Data Grid */}
      <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-primary/10 rounded-lg"><List className="w-5 h-5 text-primary" /></div>
          <h2 className="text-lg font-medium tracking-wide text-foreground">Detailed P6 Schedule Tracker</h2>
        </div>
        
        <div className="overflow-x-auto h-[400px] custom-scrollbar">
          <table className="w-full text-sm text-left relative text-foreground/90">
            <thead className="text-xs uppercase bg-muted text-muted-foreground/70 border-b border-border sticky top-0 z-10">
              <tr>
                <th className="px-4 py-3">Project ID</th>
                <th className="px-4 py-3">Project Name</th>
                <th className="px-4 py-3">Start Date</th>
                <th className="px-4 py-3">Finish Date</th>
                <th className="px-4 py-3 text-center">Alerts</th>
                <th className="px-4 py-3 text-right">Critical</th>
                <th className="px-4 py-3 text-right">Eng.</th>
                <th className="px-4 py-3 text-right">Ordering</th>
                <th className="px-4 py-3 text-right">Delivery</th>
                <th className="px-4 py-3 text-right">Variance (Days)</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {(p6Data || []).map((p: any, idx: number) => (
                <tr key={idx} className="border-b border-border hover:bg-accent transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-primary">{p.project_id}</td>
                  <td className="px-4 py-3 font-medium truncate max-w-[200px] text-foreground">{p.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{p.start_date ? new Date(p.start_date).toLocaleDateString() : 'N/A'}</td>
                  <td className="px-4 py-3 text-muted-foreground">{p.finish_date ? new Date(p.finish_date).toLocaleDateString() : 'N/A'}</td>
                  <td className="px-4 py-3 text-center">
                    {p.notifications > 0 ? (
                      <span className="inline-flex items-center justify-center gap-1 text-[11px] font-medium text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded-full">
                        <Bell className="w-3 h-3" /> {p.notifications}
                      </span>
                    ) : (
                      <span className="text-muted-foreground/50">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right text-muted-foreground">{p.critical_count || 0}</td>
                  <td className="px-4 py-3 text-right text-muted-foreground">{p.eng_count || 0}</td>
                  <td className="px-4 py-3 text-right text-muted-foreground">{p.ord_count || 0}</td>
                  <td className="px-4 py-3 text-right text-muted-foreground">{p.deliv_count || 0}</td>
                  <td className={`px-4 py-3 text-right font-medium ${(p.finishDateVariance || 0) < 0 ? 'text-destructive' : 'text-success'}`}>
                      {p.finishDateVariance ?? '0'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button 
                      onClick={() => setViewNotifsProject(p)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary text-xs font-medium rounded-lg transition-colors"
                    >
                      View <ChevronRight className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
              {(!p6Data || p6Data.length === 0) && (
                  <tr>
                      <td colSpan={10} className="px-4 py-8 text-center text-muted-foreground/70">No detailed records found.</td>
                  </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Project Notifications Modal */}
      {viewNotifsProject && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 md:p-8 animate-in fade-in duration-200">
          <div className="bg-card w-full h-full max-w-[1400px] max-h-[90vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col relative border border-border">
            <button 
              onClick={() => setViewNotifsProject(null)}
              className="absolute top-4 right-4 z-[110] p-2 bg-muted dark:bg-card hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors text-muted-foreground"
            >
              <X className="w-5 h-5" />
            </button>
            
            <div className="flex-1 overflow-y-auto flex flex-col items-center justify-center">
              <div className="w-20 h-20 bg-amber-100 dark:bg-amber-500/20 text-amber-500 rounded-full flex items-center justify-center mb-6 shadow-inner">
                <Bell className="w-10 h-10" />
              </div>
              
              <h2 className="text-2xl font-bold text-foreground dark:text-white mb-1">
                Project Alerts & Notifications
              </h2>
              <p className="text-sm font-mono text-primary bg-primary/10 px-2 py-0.5 rounded mb-4">
                {viewNotifsProject.project_id}
              </p>
              
              <p className="text-muted-foreground max-w-md text-[15px] leading-relaxed text-center mb-8">
                The granular notification feed for individual projects is currently under development.<br/>This feature will be available in an upcoming release.
              </p>
              
              <div className="w-full max-w-md border border-border rounded-xl p-5 bg-card">
                <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-4 text-center">Upcoming Integrations</h3>
                <ul className="space-y-3">
                  {[
                    "Real-time AI Suggestions & Risk Mitigations",
                    "Critical path delay warnings & float exhaustion alerts",
                    "Engineering milestone approvals & document status",
                    "Procurement and material delivery tracking"
                  ].map((item, i) => (
                    <li key={i} className="flex items-center gap-3 text-[14px] text-foreground/80">
                      <div className="w-1.5 h-1.5 rounded-full bg-amber-500/60"></div>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
