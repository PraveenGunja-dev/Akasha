import React, { useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { TrendingUp, Cpu } from 'lucide-react';
import { getCachedDashboardJson } from '../../services/dashboardQueryCache';

type PredictiveMetric = {
  value: {
    current: number;
    '30_days': number;
    '60_days': number;
    '90_days': number;
  };
  components: {
    active_project_count: number;
    confidence_pct: number;
  };
};

type ProjectRiskSource = { project_id?: string; projectId?: string };

const PredictiveAnalytics: React.FC<{
  p6Data?: ProjectRiskSource[];
  selectedProjectId?: string;
}> = ({ p6Data = [], selectedProjectId }) => {
  const [metric, setMetric] = useState<PredictiveMetric | null>(null);
  const portfolio = new URLSearchParams(window.location.search).get('portfolio');
  const projectId = selectedProjectId || (
    p6Data.length === 1 ? (p6Data[0].project_id || p6Data[0].projectId) : undefined
  );

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams();
    if (portfolio) params.set('portfolio', portfolio);
    if (projectId) params.set('project_id', projectId);
    const query = params.size ? `?${params.toString()}` : '';
    getCachedDashboardJson<any>(`/akasha/api/risk/predictive${query}`)
      .then(data => {
        if (active) setMetric(data.metrics?.['predictive.portfolio_slippage'] || null);
      })
      .catch(console.error);
    return () => { active = false; };
  }, [portfolio, projectId]);

  const forecast = metric?.value || { current: 0, '30_days': 0, '60_days': 0, '90_days': 0 };
  const activeProjects = metric?.components.active_project_count || 0;
  const avgVariance = forecast.current;

  // Forecast points: Current (0 days), +30 Days, +60 Days, +90 Days
  const forecastData = [
    { name: 'Current', actual: avgVariance, forecast: avgVariance },
    { name: '+30 Days', actual: null, forecast: forecast['30_days'] },
    { name: '+60 Days', actual: null, forecast: forecast['60_days'] },
    { name: '+90 Days', actual: null, forecast: forecast['90_days'] },
  ];

  const predictiveOption = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    legend: { textStyle: { color: 'var(--foreground)' }, bottom: '0%' },
    grid: { left: '3%', right: '4%', bottom: '10%', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: forecastData.map(d => d.name), axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' } },
    yAxis: { type: 'value', name: 'Avg Schedule Delay (Days)', axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' }, splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.2 } } },
    series: [
      {
        name: 'Actual Delay Trend',
        type: 'line',
        data: forecastData.map(d => d.actual),
        itemStyle: { color: '#3B82F6' },
        lineStyle: { width: 3 },
        symbolSize: 8
      },
      {
        name: 'Heuristic Forecasted Delay',
        type: 'line',
        data: forecastData.map(d => d.forecast),
        itemStyle: { color: '#F59E0B' },
        lineStyle: { type: 'dashed', width: 3 },
        symbolSize: 8,
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: 'rgba(245, 158, 11, 0.3)' }, { offset: 1, color: 'rgba(245, 158, 11, 0)' }]
          }
        }
      }
    ]
  };

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-10">
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Current Avg Delay</h3>
           <p className="text-4xl font-light text-foreground">{Math.round(avgVariance)} Days</p>
         </div>
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">90-Day Forecast</h3>
           <p className="text-4xl font-light text-destructive">{Math.round(forecast['90_days'])} Days</p>
         </div>
         <div className="bg-card border border-success/20 rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider flex items-center gap-2">
             <Cpu className="w-4 h-4 text-success" /> Fixed Confidence Label
           </h3>
           <p className="text-4xl font-light text-success">{metric?.components.confidence_pct ?? 87}%</p>
         </div>
      </div>

      <div className="bg-card border border-border rounded-2xl p-6 min-h-[400px] shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-warning/100/10 rounded-lg"><TrendingUp className="w-5 h-5 text-warning" /></div>
          <h2 className="text-lg font-medium tracking-wide text-foreground">Schedule Slippage Forecast (90 Days)</h2>
        </div>
        <p className="text-sm text-muted-foreground mb-4 border-l-2 border-amber-500 pl-3">
          This presentation heuristic applies fixed multipliers to the current average delay across {activeProjects} active P6 projects; it is not a statistically calibrated prediction.
        </p>
        <div className="w-full h-[350px]">
          <ReactECharts option={predictiveOption} style={{ height: '100%', width: '100%' }} />
        </div>
      </div>

    </div>
  );
};

export default PredictiveAnalytics;
