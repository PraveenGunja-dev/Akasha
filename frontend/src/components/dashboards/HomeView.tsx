import React from 'react';
import ReactECharts from 'echarts-for-react';
import { RefreshCw, Activity, Box, BarChart3 } from 'lucide-react';

export default function HomeView({ p6Data, logisticsData, sapData, loading }: any) {
  const totalActiveProjects = p6Data.length || 0;
  const criticalDelays = p6Data.filter((p: any) => p.status === 'Critical').length || 0;
  const totalCapex = sapData.reduce((acc: number, curr: any) => acc + (curr.actualCapex || 0), 0);
  const formattedCapex = totalCapex > 1000 ? `$${(totalCapex / 1000).toFixed(1)}B` : `$${totalCapex.toFixed(1)}M`;

  const p6Option = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    legend: { data: ['Planned Progress', 'Actual Progress'], textStyle: { color: 'var(--foreground)' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { 
      type: 'category', 
      data: p6Data.map((p: any) => p.name).slice(0, 5), 
      axisLine: { lineStyle: { color: 'var(--border)' } }, 
      axisLabel: { color: 'var(--foreground)', interval: 0, rotate: 15 } 
    },
    yAxis: { 
      type: 'value', 
      axisLine: { lineStyle: { color: 'var(--border)' } }, 
      axisLabel: { color: 'var(--foreground)' }, 
      splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.2 } } 
    },
    series: [
      { name: 'Planned Progress', type: 'bar', data: p6Data.map((p: any) => p.plannedProgress).slice(0, 5), itemStyle: { color: '#0B74B0', borderRadius: [4, 4, 0, 0] } },
      { name: 'Actual Progress', type: 'bar', data: p6Data.map((p: any) => p.actualProgress).slice(0, 5), itemStyle: { color: '#BD3861', borderRadius: [4, 4, 0, 0] } }
    ]
  };

  const logisticsOption = {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    legend: { top: '5%', left: 'center', textStyle: { color: 'var(--foreground)' } },
    series: [
      {
        name: 'Material Readiness',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 10, borderColor: 'var(--background)', borderWidth: 2 },
        label: { show: false, position: 'center' },
        emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' } },
        labelLine: { show: false },
        data: logisticsData.map((l: any) => ({ value: l.count, name: l.category, itemStyle: { color: l.color } }))
      }
    ]
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-7xl mx-auto pb-10">
      <div className="col-span-1 md:col-span-2 lg:col-span-3 grid grid-cols-3 gap-6">
        <div className="bg-card text-card-foreground border border-border rounded-2xl p-6 shadow-sm relative overflow-hidden">
          {loading && <div className="absolute inset-0 bg-background/50 flex items-center justify-center backdrop-blur-sm z-10"><RefreshCw className="w-5 h-5 animate-spin text-[#0B74B0]" /></div>}
          <h3 className="text-muted-foreground text-sm font-medium mb-2 uppercase tracking-wider">Total Active Projects</h3>
          <p className="text-4xl font-light">{totalActiveProjects}</p>
        </div>
        <div className="bg-card text-card-foreground border border-border rounded-2xl p-6 shadow-sm relative overflow-hidden">
          {loading && <div className="absolute inset-0 bg-background/50 flex items-center justify-center backdrop-blur-sm z-10"><RefreshCw className="w-5 h-5 animate-spin text-[#75479C]" /></div>}
          <h3 className="text-muted-foreground text-sm font-medium mb-2 uppercase tracking-wider">Total SAP PO / CAPEX</h3>
          <p className="text-4xl font-light">{formattedCapex}</p>
        </div>
        <div className="bg-card text-card-foreground border border-border rounded-2xl p-6 shadow-sm relative overflow-hidden">
          {loading && <div className="absolute inset-0 bg-background/50 flex items-center justify-center backdrop-blur-sm z-10"><RefreshCw className="w-5 h-5 animate-spin text-[#BD3861]" /></div>}
          <h3 className="text-muted-foreground text-sm font-medium mb-2 uppercase tracking-wider">Critical Path Delays</h3>
          <p className="text-4xl font-light text-[#BD3861]">{criticalDelays}</p>
        </div>
      </div>

      <div className="col-span-1 lg:col-span-2 bg-card text-card-foreground border border-border rounded-2xl p-6 min-h-[400px] shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-[#0B74B0]/10 rounded-lg"><BarChart3 className="w-5 h-5 text-[#0B74B0]" /></div>
          <h2 className="text-xl font-medium tracking-wide">Top 5 Projects Progress (P6)</h2>
        </div>
        <div className="w-full h-[350px]">
          <ReactECharts option={p6Option} style={{ height: '100%', width: '100%' }} />
        </div>
      </div>

      <div className="col-span-1 bg-card text-card-foreground border border-border rounded-2xl p-6 min-h-[400px] shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-[#75479C]/10 rounded-lg"><Box className="w-5 h-5 text-[#75479C]" /></div>
          <h2 className="text-xl font-medium tracking-wide">Overall Logistics (SAP)</h2>
        </div>
        <div className="w-full h-[350px]">
           <ReactECharts option={logisticsOption} style={{ height: '100%', width: '100%' }} />
        </div>
      </div>
    </div>
  );
}
