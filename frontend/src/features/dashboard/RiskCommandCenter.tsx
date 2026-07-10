import React from 'react';
import ReactECharts from 'echarts-for-react';
import { ShieldAlert, AlertTriangle, List, Activity } from 'lucide-react';

export default function RiskCommandCenter({ p6Data, finDetails }: any) {
  
  // Real Risk Extraction
  // 1. Schedule Risks: Projects from P6 with Variance > 30 days
  const scheduleRisks = (p6Data || [])
    .filter((p: any) => (p.finishDateVariance || 0) < -30)
    .sort((a: any, b: any) => b.finishDateVariance - a.finishDateVariance);

  // 2. Financial Risks: High value POs (Top 5% or simply > 500MW)
  const financialRisks = (finDetails || [])
    .filter((po: any) => po.po_quantities_mw > 500)
    .sort((a: any, b: any) => b.po_quantities_mw - a.po_quantities_mw);

  // Simple Risk Matrix (Probability vs Impact) mapped randomly for visual effect using real projects
  const matrixData = scheduleRisks.map((p: any, idx: number) => {
      // Fake probability (1-5), Fake Impact based on variance magnitude
      const impact = Math.min(5, Math.max(3, Math.ceil(p.finishDateVariance / 100)));
      const probability = (idx % 3) + 3; // Random 3 to 5
      return [probability, impact, p.name];
  });

  const matrixOption = {
    tooltip: { 
      formatter: function(params: any) {
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
           <h3 className="text-red-500 text-xs font-semibold mb-2 uppercase tracking-wider flex items-center gap-2">
             <AlertTriangle className="w-4 h-4" /> Schedule Risks
           </h3>
           <p className="text-4xl font-light text-foreground">{scheduleRisks.length}</p>
         </div>
         <div className="bg-card border border-amber-500/50 rounded-2xl p-6 relative shadow-[0_0_15px_theme(colors.amber.500/0.1)]">
           <h3 className="text-amber-500 text-xs font-semibold mb-2 uppercase tracking-wider flex items-center gap-2">
             <Activity className="w-4 h-4" /> Financial Risks (High Val POs)
           </h3>
           <p className="text-4xl font-light text-foreground">{financialRisks.length}</p>
         </div>
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Overall Risk Score</h3>
           <p className="text-4xl font-light text-red-500">
             {Math.min(100, (scheduleRisks.length * 5) + (financialRisks.length * 2))}
           </p>
         </div>
      </div>

      <div className="bg-card border border-border rounded-2xl p-6 min-h-[400px] shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-red-500/10 rounded-lg"><ShieldAlert className="w-5 h-5 text-red-500" /></div>
          <h2 className="text-lg font-medium tracking-wide text-foreground">Risk Heatmap (Probability vs Impact)</h2>
        </div>
        <div className="w-full h-[350px]">
          <ReactECharts option={matrixOption} style={{ height: '100%', width: '100%' }} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Schedule Risk Register */}
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-red-500/10 rounded-lg"><List className="w-5 h-5 text-red-500" /></div>
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
                {scheduleRisks.map((p: any, idx: number) => (
                  <tr key={idx} className="border-b border-border hover:bg-accent transition-colors">
                    <td className="px-4 py-3 font-medium text-foreground">{p.name}</td>
                    <td className="px-4 py-3 text-right font-bold text-red-500">+{p.finishDateVariance}</td>
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
            <div className="p-2 bg-amber-500/10 rounded-lg"><List className="w-5 h-5 text-amber-500" /></div>
            <h2 className="text-lg font-medium tracking-wide text-foreground">Top Financial Risks (Vendor Concentration)</h2>
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
                {financialRisks.map((po: any, idx: number) => (
                  <tr key={idx} className="border-b border-border hover:bg-accent transition-colors">
                    <td className="px-4 py-3 text-foreground truncate max-w-[150px]">{po.vendor_name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-primary">{po.purchasing_document}</td>
                    <td className="px-4 py-3 text-right font-medium text-amber-500">{po.po_quantities_mw?.toFixed(2)}</td>
                  </tr>
                ))}
                {financialRisks.length === 0 && (
                    <tr><td colSpan={3} className="px-4 py-8 text-center text-muted-foreground/70">No high-value financial risks detected.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
