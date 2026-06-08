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
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-primary/10 rounded-lg"><Activity className="w-5 h-5 text-primary" /></div>
            <h3 className="text-sm font-medium text-foreground tracking-wide uppercase">Top 5 Projects Progress</h3>
          </div>
          <div className="w-full h-[300px]">
            <ReactECharts option={progressOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-emerald-500/10 rounded-lg"><PieChart className="w-5 h-5 text-emerald-500" /></div>
            <h3 className="text-sm font-medium text-foreground tracking-wide uppercase">Overall Logistics Status</h3>
          </div>
          <div className="w-full h-[300px]">
            <ReactECharts option={logisticsOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
      </div>
      
      {/* Portfolio Status Matrix Placeholder */}
      <div className="bg-card border border-border rounded-2xl p-6 shadow-sm min-h-[300px] flex flex-col items-center justify-center text-center">
         <PieChart className="w-12 h-12 text-muted-foreground mb-4" />
         <h3 className="text-lg font-medium text-foreground mb-2">Portfolio Health Matrix (Quadrant)</h3>
         <p className="text-sm text-muted-foreground/70 max-w-md">Schedule vs Cost Quadrant visualization will be populated when historical variance snapshots are available.</p>
      </div>
    </div>
  );
}
