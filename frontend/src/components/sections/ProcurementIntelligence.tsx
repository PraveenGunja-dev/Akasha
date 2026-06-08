import React from 'react';
import ReactECharts from 'echarts-for-react';
import { ShoppingCart, ShieldAlert, List } from 'lucide-react';

export default function ProcurementIntelligence({ finDetails }: any) {
  
  // Aggregate vendor performance from actual POs
  const vendorMap: any = {};
  (finDetails || []).forEach((po: any) => {
      const v = po.vendor_name || 'Unknown Vendor';
      vendorMap[v] = (vendorMap[v] || 0) + po.po_quantities_mw;
  });
  
  const vendorList = Object.keys(vendorMap)
    .map(k => ({name: k.substring(0,30), value: vendorMap[k]}))
    .sort((a,b) => b.value - a.value);
    
  const topVendors = vendorList.slice(0, 8);

  const vendorScorecardOption = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' }, splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.2 } } },
    yAxis: { type: 'category', data: topVendors.map(v => v.name).reverse(), axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)', width: 120, overflow: 'truncate' } },
    series: [
      { name: 'Total Order Volume (MW)', type: 'bar', data: topVendors.map(v => v.value).reverse(), itemStyle: { color: '#3B82F6', borderRadius: [0, 4, 4, 0] } }
    ]
  };

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-10">
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Total Active POs</h3>
           <p className="text-4xl font-light text-foreground">{finDetails?.length || 0}</p>
         </div>
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Total Unique Vendors</h3>
           <p className="text-4xl font-light text-primary">{vendorList.length}</p>
         </div>
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Vendor Concentration Risk</h3>
           <p className="text-4xl font-light text-amber-500">
             {vendorList.length > 0 ? Math.round((vendorList[0]?.value / vendorList.reduce((acc, v) => acc + v.value, 0)) * 100) : 0}%
           </p>
         </div>
      </div>

      <div className="bg-card border border-border rounded-2xl p-6 min-h-[400px] shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-primary/10 rounded-lg"><ShieldAlert className="w-5 h-5 text-primary" /></div>
          <h2 className="text-lg font-medium tracking-wide text-foreground">Vendor Performance Scorecard</h2>
        </div>
        <div className="w-full h-[350px]">
          <ReactECharts option={vendorScorecardOption} style={{ height: '100%', width: '100%' }} />
        </div>
      </div>

      {/* Detailed PO Pipeline */}
      <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-emerald-500/10 rounded-lg"><ShoppingCart className="w-5 h-5 text-emerald-500" /></div>
          <h2 className="text-lg font-medium tracking-wide text-foreground">Active Procurement Pipeline</h2>
        </div>
        
        <div className="overflow-x-auto h-[400px] custom-scrollbar">
          <table className="w-full text-sm text-left text-foreground/90">
            <thead className="text-xs uppercase bg-muted text-muted-foreground/70 border-b border-border sticky top-0 z-10">
              <tr>
                <th className="px-4 py-3">PO Number</th>
                <th className="px-4 py-3">Vendor Name</th>
                <th className="px-4 py-3">Material Code</th>
                <th className="px-4 py-3 text-right">Volume Ordered (MW)</th>
              </tr>
            </thead>
            <tbody>
              {(finDetails || []).map((po: any, idx: number) => (
                <tr key={idx} className="border-b border-border hover:bg-accent transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-primary">{po.purchasing_document}</td>
                  <td className="px-4 py-3 text-muted-foreground">{po.vendor_name || 'Unknown'}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{po.material_code}</td>
                  <td className="px-4 py-3 text-right font-medium">{po.po_quantities_mw?.toFixed(2)}</td>
                </tr>
              ))}
              {(!finDetails || finDetails.length === 0) && (
                  <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground/70">No active POs in pipeline.</td>
                  </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
