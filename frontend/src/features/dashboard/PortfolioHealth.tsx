import React from 'react';
import ReactECharts from 'echarts-for-react';
import { PieChart, Activity } from 'lucide-react';

export default function PortfolioHealth({ p6Data, logisticsData }: any) {
  
  // Schedule Progress Bar Chart
  const progressOption = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', max: 100, axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)', formatter: '{value}%' }, splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.2 } } },
    yAxis: { type: 'category', data: p6Data.map((p:any) => p.name).slice(0, 5), axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)', width: 120, overflow: 'truncate' } },
    series: [
      { name: 'Progress', type: 'bar', data: p6Data.map((p:any) => p.durationPercentComplete || 0).slice(0, 5), itemStyle: { color: '#3B82F6', borderRadius: [0, 4, 4, 0] } }
    ]
  };

  // Logistics Pie
  const logisticsOption = {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    legend: { bottom: '0%', left: 'center', textStyle: { color: 'var(--foreground)' } },
    series: [
      {
        name: 'Logistics', type: 'pie', radius: ['40%', '70%'], avoidLabelOverlap: false,
        itemStyle: { borderRadius: 10, borderColor: 'var(--background)', borderWidth: 2 },
        label: { show: false, position: 'center' },
        emphasis: { label: { show: true, fontSize: 18, fontWeight: 'bold' } },
        labelLine: { show: false },
        data: logisticsData.map((d: any) => ({ value: d.count, name: d.category, itemStyle: { color: d.color } }))
      }
    ]
  };

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500">
      <div className="flex items-center gap-2 mb-2">
        <PieChart className="w-5 h-5 text-primary" />
        <h2 className="text-lg font-semibold text-foreground tracking-wide">Portfolio Health Center</h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-card/40 backdrop-blur-md border border-border/60 hover:bg-card hover:border-primary/40 hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)] dark:hover:shadow-[0_8px_30px_rgba(59,130,246,0.1)] transition-all duration-300 rounded-3xl p-7 relative group overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 blur-[100px] rounded-full pointer-events-none transition-opacity duration-500 group-hover:opacity-100 opacity-0"></div>
          <div className="relative z-10">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2.5 bg-primary/10 rounded-xl transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-3 shadow-sm border border-primary/20"><Activity className="w-5 h-5 text-primary" /></div>
              <h3 className="text-[13px] font-semibold text-foreground tracking-widest uppercase transition-colors group-hover:text-primary">Top 5 Projects Progress</h3>
            </div>
            <div className="w-full h-[300px]">
              <ReactECharts option={progressOption} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>
        </div>

        <div className="bg-card/40 backdrop-blur-md border border-border/60 hover:bg-card hover:border-emerald-500/40 hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)] dark:hover:shadow-[0_8px_30px_rgba(16,185,129,0.1)] transition-all duration-300 rounded-3xl p-7 relative group overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/5 blur-[100px] rounded-full pointer-events-none transition-opacity duration-500 group-hover:opacity-100 opacity-0"></div>
          <div className="relative z-10">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2.5 bg-emerald-500/10 rounded-xl transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-3 shadow-sm border border-emerald-500/20"><PieChart className="w-5 h-5 text-emerald-500" /></div>
              <h3 className="text-[13px] font-semibold text-foreground tracking-widest uppercase transition-colors group-hover:text-emerald-500">Overall Logistics Status</h3>
            </div>
            <div className="w-full h-[300px]">
              <ReactECharts option={logisticsOption} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>
        </div>
      </div>
      
      {/* Portfolio Status Matrix Placeholder */}
      <div className="bg-card/40 backdrop-blur-md border border-border/60 rounded-3xl p-8 hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] transition-all duration-300 min-h-[300px] flex flex-col items-center justify-center text-center mt-2 group relative overflow-hidden">
         <div className="absolute inset-0 bg-gradient-to-br from-transparent to-muted/20 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"></div>
         <PieChart className="w-12 h-12 text-muted-foreground/50 mb-4 transition-transform duration-300 group-hover:scale-110" />
         <h3 className="text-lg font-medium text-foreground mb-2">Portfolio Health Matrix (Quadrant)</h3>
         <p className="text-sm text-muted-foreground/70 max-w-md">Schedule vs Cost Quadrant visualization will be populated when historical variance snapshots are available.</p>
      </div>
    </div>
  );
}
