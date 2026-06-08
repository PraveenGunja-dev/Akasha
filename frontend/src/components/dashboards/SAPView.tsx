import React from 'react';
import ReactECharts from 'echarts-for-react';
import { DollarSign, Truck, Activity, List, Users } from 'lucide-react';

export default function SAPView({ sapData, logisticsData, finDetails, logDetails, loading }: any) {
  
  const sapOption = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    legend: { data: ['Planned CAPEX', 'Actual CAPEX', 'Cash Flow Variance'], textStyle: { color: 'var(--foreground)' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { 
      type: 'category', 
      data: sapData.map((s: any) => s.quarter), 
      axisLine: { lineStyle: { color: 'var(--border)' } }, 
      axisLabel: { color: 'var(--foreground)' } 
    },
    yAxis: [
      { type: 'value', name: 'Millions ($)', axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' }, splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.2 } } },
      { type: 'value', name: 'Variance (%)', axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' }, splitLine: { show: false } }
    ],
    series: [
      { name: 'Planned CAPEX', type: 'bar', data: sapData.map((s: any) => s.plannedCapex), itemStyle: { color: '#0B74B0', borderRadius: [4, 4, 0, 0] } },
      { name: 'Actual CAPEX', type: 'bar', data: sapData.map((s: any) => s.actualCapex), itemStyle: { color: '#75479C', borderRadius: [4, 4, 0, 0] } },
      { name: 'Cash Flow Variance', type: 'line', yAxisIndex: 1, data: sapData.map((s: any) => s.cashFlowVariancePercent), itemStyle: { color: '#BD3861' }, smooth: true, symbolSize: 8 }
    ]
  };

  const logisticsFunnel = {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    series: [
      {
        name: 'Material Flow',
        type: 'funnel',
        left: '10%',
        top: 60,
        bottom: 60,
        width: '80%',
        min: 0,
        max: 10000,
        minSize: '0%',
        maxSize: '100%',
        sort: 'descending',
        gap: 2,
        label: { show: true, position: 'inside', formatter: '{b}: {c}' },
        itemStyle: { borderColor: 'var(--background)', borderWidth: 1 },
        data: [
          { value: logisticsData.find((l:any) => l.category === 'At Port')?.count || 580, name: 'At Port', itemStyle: {color: '#f59e0b'} },
          { value: logisticsData.find((l:any) => l.category === 'In Transit')?.count || 0, name: 'In Transit', itemStyle: {color: '#75479C'} },
          { value: logisticsData.find((l:any) => l.category === 'Delivered')?.count || 0, name: 'Delivered', itemStyle: {color: '#0B74B0'} },
        ]
      }
    ]
  };

  // Process finDetails for Top Vendors
  const vendorMap: any = {};
  (finDetails || []).forEach((po: any) => {
      const v = po.vendor_name || 'Unknown Vendor';
      vendorMap[v] = (vendorMap[v] || 0) + po.po_quantities_mw;
  });
  const topVendors = Object.keys(vendorMap).map(k => ({name: k.substring(0,25), value: vendorMap[k]})).sort((a,b) => b.value - a.value).slice(0, 5);

  const vendorOption = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' }, splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.2 } } },
    yAxis: { type: 'category', data: topVendors.map(v => v.name).reverse(), axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' } },
    series: [
      { name: 'Order Volume (MW)', type: 'bar', data: topVendors.map(v => v.value).reverse(), itemStyle: { color: '#0B74B0', borderRadius: [0, 4, 4, 0] } }
    ]
  };

  const totalCapex = sapData.reduce((acc: number, curr: any) => acc + (curr.actualCapex || 0), 0);

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-10">
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Actual CAPEX (YTD)</h3>
           <p className="text-4xl font-light text-foreground">${totalCapex > 1000 ? (totalCapex/1000).toFixed(2) + 'B' : totalCapex.toFixed(1) + 'M'}</p>
         </div>
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Total Deliveries Completed</h3>
           <p className="text-4xl font-light text-foreground">{logisticsData.find((l:any)=>l.category === 'Delivered')?.count || 0}</p>
         </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="col-span-1 lg:col-span-2 bg-card border border-border rounded-2xl p-6 min-h-[400px] shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-rose-500/10 rounded-lg"><Activity className="w-5 h-5 text-rose-500" /></div>
              <h2 className="text-lg font-medium tracking-wide text-foreground">CAPEX & Cash Flow (SAP)</h2>
            </div>
            <div className="w-full h-[350px]">
              <ReactECharts option={sapOption} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>

          <div className="col-span-1 bg-card border border-border rounded-2xl p-6 min-h-[350px] shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-blue-500/10 rounded-lg"><Truck className="w-5 h-5 text-blue-500" /></div>
              <h2 className="text-lg font-medium tracking-wide text-foreground">Material Logistics Funnel</h2>
            </div>
            <div className="w-full h-[250px]">
              <ReactECharts option={logisticsFunnel} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>

          <div className="col-span-1 bg-card border border-border rounded-2xl p-6 min-h-[350px] shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-purple-500/10 rounded-lg"><Users className="w-5 h-5 text-purple-500" /></div>
              <h2 className="text-lg font-medium tracking-wide text-foreground">Top Vendors by Volume</h2>
            </div>
            <div className="w-full h-[250px]">
              <ReactECharts option={vendorOption} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>
      </div>

      {/* Detailed Data Grid */}
      <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-primary/10 rounded-lg"><List className="w-5 h-5 text-primary" /></div>
          <h2 className="text-lg font-medium tracking-wide text-foreground">Detailed Procurement Ledger</h2>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left text-foreground/90">
            <thead className="text-xs uppercase bg-muted text-muted-foreground/70 border-b border-border">
              <tr>
                <th className="px-4 py-3">PO Number</th>
                <th className="px-4 py-3">Vendor Name</th>
                <th className="px-4 py-3">Material Code</th>
                <th className="px-4 py-3 text-right">Quantity (MW)</th>
              </tr>
            </thead>
            <tbody>
              {(finDetails || []).map((po: any, idx: number) => (
                <tr key={idx} className="border-b border-border hover:bg-accent transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">{po.purchasing_document}</td>
                  <td className="px-4 py-3 text-muted-foreground truncate max-w-[200px]">{po.vendor_name || 'Unknown'}</td>
                  <td className="px-4 py-3 font-mono text-xs text-primary">{po.material_code}</td>
                  <td className="px-4 py-3 text-right font-medium">{po.po_quantities_mw?.toFixed(2)}</td>
                </tr>
              ))}
              {(!finDetails || finDetails.length === 0) && (
                  <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground/70">No detailed records found.</td>
                  </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
