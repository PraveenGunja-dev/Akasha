import React, { useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { ShieldAlert, AlertTriangle, List, Activity } from 'lucide-react';
import { getCachedDashboardJson } from '../../services/dashboardQueryCache';

type Metric<TValue, TEvidence> = {
  value: TValue;
  evidence: TEvidence[];
};

type ScheduleRisk = {
  name?: string;
  finish_date_variance: number;
};

type FinancialRisk = {
  vendor_name?: string;
  purchasing_document?: string;
  po_quantities_mw: number;
};

type HeatmapPoint = {
  probability: number;
  impact: number;
  name?: string;
};

type RiskResponse = {
  metrics: {
    'command_center.schedule_risk_count'?: Metric<number, ScheduleRisk>;
    'command_center.financial_risk_count'?: Metric<number, FinancialRisk>;
    'command_center.overall_risk_score'?: Metric<number, never>;
    'command_center.risk_heatmap'?: Metric<HeatmapPoint[], HeatmapPoint>;
  };
};

type ProjectRiskSource = { project_id?: string; projectId?: string };
type Props = {
  p6Data?: ProjectRiskSource[];
  finDetails?: unknown[];
  selectedProjectId?: string;
};

const RiskCommandCenter: React.FC<Props> = ({ p6Data = [], selectedProjectId }) => {
  const [metrics, setMetrics] = useState<RiskResponse['metrics']>({});
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
    getCachedDashboardJson<RiskResponse>(`/akasha/api/risk/command-center${query}`)
      .then(data => { if (active) setMetrics(data.metrics || {}); })
      .catch(console.error);
    return () => { active = false; };
  }, [portfolio, projectId]);

  const scheduleMetric = metrics['command_center.schedule_risk_count'];
  const financialMetric = metrics['command_center.financial_risk_count'];
  const overallMetric = metrics['command_center.overall_risk_score'];
  const heatmapMetric = metrics['command_center.risk_heatmap'];
  const scheduleRisks = scheduleMetric?.evidence || [];
  const financialRisks = financialMetric?.evidence || [];
  const matrixData = (heatmapMetric?.value || []).map((point) => [
    point.probability,
    point.impact,
    point.name,
  ]);

  const matrixOption = {
    tooltip: { 
      formatter: function(params: { value: [number, number, string] }) {
        return `<b>${params.value[2]}</b><br/>Prob: ${params.value[0]}, Impact: ${params.value[1]}`;
      },
      backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' }
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { name: 'Probability (1-5)', min: 1, max: 5, splitNumber: 4, axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' }, splitLine: { show: true, lineStyle: { color: 'var(--border)', opacity: 0.2 } } },
    yAxis: { name: 'Impact (1-5)', min: 1, max: 5, splitNumber: 4, axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' }, splitLine: { show: true, lineStyle: { color: 'var(--border)', opacity: 0.2 } } },
    series: [{
      type: 'scatter',
      symbolSize: 20,
      itemStyle: { color: '#EF4444', shadowBlur: 10, shadowColor: 'rgba(239, 68, 68, 0.5)' },
      data: matrixData
    }]
  };

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-10">
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
         <div className="bg-card border border-red-500/50 rounded-2xl p-6 relative shadow-[0_0_15px_theme(colors.red.500/0.1)]">
           <h3 className="text-destructive text-xs font-semibold mb-2 uppercase tracking-wider flex items-center gap-2">
             <AlertTriangle className="w-4 h-4" /> Schedule Risks
           </h3>
           <p className="text-4xl font-light text-foreground">{scheduleMetric?.value ?? 0}</p>
         </div>
         <div className="bg-card border border-amber-500/50 rounded-2xl p-6 relative shadow-[0_0_15px_theme(colors.amber.500/0.1)]">
           <h3 className="text-warning text-xs font-semibold mb-2 uppercase tracking-wider flex items-center gap-2">
             <Activity className="w-4 h-4" /> High-Volume POs
           </h3>
           <p className="text-4xl font-light text-foreground">{financialMetric?.value ?? 0}</p>
         </div>
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Overall Risk Score</h3>
           <p className="text-4xl font-light text-destructive">
             {overallMetric?.value ?? 0}
           </p>
         </div>
      </div>

      <div className="bg-card border border-border rounded-2xl p-6 min-h-[400px] shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-destructive/100/10 rounded-lg"><ShieldAlert className="w-5 h-5 text-destructive" /></div>
          <h2 className="text-lg font-medium tracking-wide text-foreground">Risk Heatmap (Heuristic Probability vs Impact)</h2>
        </div>
        <div className="w-full h-[350px]">
          <ReactECharts option={matrixOption} style={{ height: '100%', width: '100%' }} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Schedule Risk Register */}
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-destructive/100/10 rounded-lg"><List className="w-5 h-5 text-destructive" /></div>
            <h2 className="text-lg font-medium tracking-wide text-foreground">Top Schedule Risks</h2>
          </div>
          
          <div className="overflow-x-auto h-[300px] custom-scrollbar">
            <table className="w-full text-sm text-left text-foreground/90">
              <thead className="text-xs uppercase bg-muted text-muted-foreground/70 border-b border-border sticky top-0 z-10">
                <tr>
                  <th className="px-4 py-3">Project</th>
                  <th className="px-4 py-3 text-right">Variance (Days)</th>
                </tr>
              </thead>
              <tbody>
                {scheduleRisks.map((p, idx: number) => (
                  <tr key={idx} className="border-b border-border hover:bg-accent transition-colors">
                    <td className="px-4 py-3 font-medium text-foreground">{p.name}</td>
                    <td className="px-4 py-3 text-right font-bold text-destructive">+{p.finish_date_variance}</td>
                  </tr>
                ))}
                {scheduleRisks.length === 0 && (
                    <tr><td colSpan={2} className="px-4 py-8 text-center text-muted-foreground/70">No major schedule delays detected.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Financial Risk Register */}
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-warning/100/10 rounded-lg"><List className="w-5 h-5 text-warning" /></div>
            <h2 className="text-lg font-medium tracking-wide text-foreground">High-Volume PO Register</h2>
          </div>
          
          <div className="overflow-x-auto h-[300px] custom-scrollbar">
            <table className="w-full text-sm text-left text-foreground/90">
              <thead className="text-xs uppercase bg-muted text-muted-foreground/70 border-b border-border sticky top-0 z-10">
                <tr>
                  <th className="px-4 py-3">Vendor</th>
                  <th className="px-4 py-3">PO Number</th>
                  <th className="px-4 py-3 text-right">Volume (MW)</th>
                </tr>
              </thead>
              <tbody>
                {financialRisks.map((po, idx: number) => (
                  <tr key={idx} className="border-b border-border hover:bg-accent transition-colors">
                    <td className="px-4 py-3 text-foreground truncate max-w-[150px]">{po.vendor_name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-primary">{po.purchasing_document}</td>
                    <td className="px-4 py-3 text-right font-medium text-warning">{po.po_quantities_mw?.toFixed(2)}</td>
                  </tr>
                ))}
                {financialRisks.length === 0 && (
                    <tr><td colSpan={3} className="px-4 py-8 text-center text-muted-foreground/70">No high-volume POs detected.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RiskCommandCenter;
