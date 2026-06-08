import React from 'react';
import ReactECharts from 'echarts-for-react';
import { Truck, Map, List, PackageSearch } from 'lucide-react';

export default function MaterialIntelligence({ logDetails, logisticsData }: any) {
  
  // Material Transit Status (Mocked geo data for supply chain map feel, backed by real volumes)
  const inTransitVolume = logDetails?.reduce((acc: number, val: any) => acc + val.quantity_mw, 0) || 0;
  
  // Aggregate by plant code to see which plants have the most incoming material
  const plantMap: any = {};
  (logDetails || []).forEach((item: any) => {
      const p = item.plant_code || 'Unknown';
      plantMap[p] = (plantMap[p] || 0) + item.quantity_mw;
  });
  
  const plantList = Object.keys(plantMap).map(k => ({name: `Plant ${k}`, value: plantMap[k]}));

  const supplyChainOption = {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    legend: { textStyle: { color: 'var(--foreground)' } },
    series: [
      {
        name: 'Incoming Material Volume (MW)',
        type: 'pie',
        radius: ['50%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 10, borderColor: 'var(--background)', borderWidth: 2 },
        label: { show: true, color: 'var(--foreground)', formatter: '{b}: {c}MW' },
        data: plantList.length > 0 ? plantList : [{ name: 'No Transit Data', value: 0 }]
      }
    ]
  };

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-10">
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Total Material In-Transit (MW)</h3>
           <p className="text-4xl font-light text-foreground">{inTransitVolume.toFixed(2)}</p>
         </div>
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Active Shipments</h3>
           <p className="text-4xl font-light text-amber-500">{logDetails?.length || 0}</p>
         </div>
         <div className="bg-card border border-border rounded-2xl p-6 relative shadow-sm">
           <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Total Delivered (Historical)</h3>
           <p className="text-4xl font-light text-emerald-500">{logisticsData.find((l:any) => l.category === 'Delivered')?.count || 0}</p>
         </div>
      </div>

      <div className="bg-card border border-border rounded-2xl p-6 min-h-[400px] shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-amber-500/10 rounded-lg"><Map className="w-5 h-5 text-amber-500" /></div>
          <h2 className="text-lg font-medium tracking-wide text-foreground">Supply Chain Distribution (In-Transit to Plants)</h2>
        </div>
        <div className="w-full h-[350px]">
          <ReactECharts option={supplyChainOption} style={{ height: '100%', width: '100%' }} />
        </div>
      </div>

      {/* Detailed Material Transit Ledger */}
      <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-emerald-500/10 rounded-lg"><PackageSearch className="w-5 h-5 text-emerald-500" /></div>
          <h2 className="text-lg font-medium tracking-wide text-foreground">Live In-Transit Ledger</h2>
        </div>
        
        <div className="overflow-x-auto h-[400px] custom-scrollbar">
          <table className="w-full text-sm text-left text-foreground/90">
            <thead className="text-xs uppercase bg-muted text-muted-foreground/70 border-b border-border sticky top-0 z-10">
              <tr>
                <th className="px-4 py-3">PO Number</th>
                <th className="px-4 py-3">Plant Destination</th>
                <th className="px-4 py-3">Material Code</th>
                <th className="px-4 py-3 text-right">In-Transit Volume (MW)</th>
              </tr>
            </thead>
            <tbody>
              {(logDetails || []).map((item: any, idx: number) => (
                <tr key={idx} className="border-b border-border hover:bg-accent transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-primary">{item.po_number || 'N/A'}</td>
                  <td className="px-4 py-3 text-muted-foreground font-medium">Plant {item.plant_code}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{item.material_code}</td>
                  <td className="px-4 py-3 text-right font-medium text-amber-500">{item.quantity_mw?.toFixed(2)}</td>
                </tr>
              ))}
              {(!logDetails || logDetails.length === 0) && (
                  <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground/70">No active materials in transit.</td>
                  </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
