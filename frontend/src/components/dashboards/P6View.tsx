import React from 'react';
import ReactECharts from 'echarts-for-react';
import { Calendar, AlertTriangle, List } from 'lucide-react';

export default function P6View({ p6Data, loading }: any) {
  // P6 specific data mapping
  const sortedByDelay = [...(p6Data || [])].sort((a, b) => a.finishDateVariance - b.finishDateVariance);
  const delayedProjects = sortedByDelay.filter(p => (p.finishDateVariance || 0) < 0);
  
  const scheduleOption = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    legend: { data: ['Planned Duration', 'Actual Duration'], textStyle: { color: 'var(--foreground)' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { 
      type: 'value', 
      name: 'Days',
      axisLine: { lineStyle: { color: 'var(--border)' } }, 
      axisLabel: { color: 'var(--foreground)' }, 
      splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.2 } } 
    },
    yAxis: { 
      type: 'category', 
      data: p6Data.map((p: any) => p.name).slice(0, 8), 
      axisLine: { lineStyle: { color: 'var(--border)' } }, 
      axisLabel: { color: 'var(--foreground)', width: 120, overflow: 'truncate' } 
    },
    series: [
      { name: 'Planned Duration', type: 'bar', data: p6Data.map((p: any) => p.plannedDuration).slice(0, 8), itemStyle: { color: '#0B74B0', borderRadius: [0, 4, 4, 0] } },
      { name: 'Actual Duration', type: 'bar', data: p6Data.map((p: any) => p.actualDuration).slice(0, 8), itemStyle: { color: '#f59e0b', borderRadius: [0, 4, 4, 0] } }
    ]
  };

  const delayOption = {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    xAxis: { 
      type: 'category', 
      data: delayedProjects.map(p => p.name).slice(0, 10),
      axisLine: { lineStyle: { color: 'var(--border)' } }, 
      axisLabel: { color: 'var(--foreground)', interval: 0, rotate: 30 } 
    },
    yAxis: { 
      type: 'value', 
      name: 'Variance (Days)',
      axisLine: { lineStyle: { color: 'var(--border)' } }, 
      axisLabel: { color: 'var(--foreground)' },
      splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.2 } } 
    },
    series: [
      { 
        data: delayedProjects.map(p => p.finishDateVariance).slice(0, 10), 
        type: 'line', 
        areaStyle: { color: 'rgba(189, 56, 97, 0.2)' },
        itemStyle: { color: '#BD3861' },
        smooth: true 
      }
    ]
  };

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-10">
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Total Scheduled Projects</h3>
           <p className="text-4xl font-light text-foreground">{p6Data.length}</p>
         </div>
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Projects Delayed {">"} 30 Days</h3>
           <p className="text-4xl font-light text-red-500">{delayedProjects.filter(p => (p.finishDateVariance || 0) < -30).length}</p>
         </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="col-span-1 bg-card border border-border rounded-2xl p-6 min-h-[400px] shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-blue-500/10 rounded-lg"><Calendar className="w-5 h-5 text-blue-500" /></div>
              <h2 className="text-lg font-medium tracking-wide text-foreground">Schedule Progress</h2>
            </div>
            <div className="w-full h-[350px]">
              <ReactECharts option={scheduleOption} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>

          <div className="col-span-1 bg-card border border-border rounded-2xl p-6 min-h-[400px] shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-rose-500/10 rounded-lg"><AlertTriangle className="w-5 h-5 text-rose-500" /></div>
              <h2 className="text-lg font-medium tracking-wide text-foreground">Top Delays (Variance)</h2>
            </div>
            <div className="w-full h-[350px]">
              <ReactECharts option={delayOption} style={{ height: '100%', width: '100%' }} />
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
                <th className="px-4 py-3 text-right">Float</th>
                <th className="px-4 py-3 text-right">Variance (Days)</th>
                <th className="px-4 py-3 text-center">Status</th>
              </tr>
            </thead>
            <tbody>
              {(p6Data || []).map((p: any, idx: number) => (
                <tr key={idx} className="border-b border-border hover:bg-accent transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-primary">{p.project_id}</td>
                  <td className="px-4 py-3 font-medium truncate max-w-[200px] text-foreground">{p.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{p.start_date ? new Date(p.start_date).toLocaleDateString() : 'N/A'}</td>
                  <td className="px-4 py-3 text-muted-foreground">{p.finish_date ? new Date(p.finish_date).toLocaleDateString() : 'N/A'}</td>
                  <td className="px-4 py-3 text-right font-medium">{p.total_float ?? '0'}</td>
                  <td className={`px-4 py-3 text-right font-medium ${(p.finishDateVariance || 0) < 0 ? 'text-red-500' : 'text-emerald-500'}`}>
                      {p.finishDateVariance ?? '0'}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-2 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider ${p.status === 'Active' ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-muted text-muted-foreground border border-border'}`}>
                        {p.status}
                    </span>
                  </td>
                </tr>
              ))}
              {(!p6Data || p6Data.length === 0) && (
                  <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground/70">No detailed records found.</td>
                  </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
