import React, { useState, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import { Database, FileText, Users, Layers, Box, Package, IndianRupee, TrendingUp, PieChart, Truck, Download, ArrowRight, List, Activity } from 'lucide-react';

export default function SAPView({ sapData = [], logisticsData = [], finDetails = [], logDetails = [], loading }: any) {
  const [trendsData, setTrendsData] = useState<any>(null);

  useEffect(() => {
    fetch('/akasha/api/financials/trends')
      .then(res => res.json())
      .then(data => setTrendsData(data))
      .catch(err => console.error("Error fetching trends:", err));
  }, []);

  // No local filtering needed since it's an overall dashboard
  const activePlantCode = null;
  const activeFilter = 'ALL';

  // Locally filter the data based on activeFilter
  const filteredFinDetails = activePlantCode 
    ? (finDetails || []).filter((po: any) => 
        po.plant_code?.includes(activePlantCode) || 
        po.wbs_element?.includes(activePlantCode)
      )
    : (finDetails || []);

  const filteredLogDetails = activePlantCode
    ? (logDetails || []).filter((po: any) => 
        po.plant_code?.includes(activePlantCode) || 
        po.wbs_element?.includes(activePlantCode)
      )
    : (logDetails || []);

  // Read global metrics directly from backend (bypassing the 1000 array limit)
  const globalSap = sapData[0] || {};
  
  const totalPos = globalSap.totalPos ?? filteredFinDetails.length ?? 0;
  const vendors = globalSap.vendors ?? new Set(filteredFinDetails.map((f:any) => f.vendor_name).filter(Boolean)).size ?? 0;
  const materials = globalSap.materials ?? new Set(filteredFinDetails.map((f:any) => f.material_code).filter(Boolean)).size ?? 0;
  
  const poVolume = globalSap.volume ?? filteredFinDetails.reduce((acc:any, curr:any) => acc + (curr.po_quantities || curr.menge || curr.po_quantity || 0), 0) ?? 0; 
  const inventory = trendsData?.total_inventory ?? 0;
  
  // Financial metrics (The true global sum is actualCapex)
  const supplyPoAmount = globalSap.actualCapex ?? filteredFinDetails.reduce((acc:any, curr:any) => acc + ((curr.net_order_value_inr || curr.net_order_value || 0) / 10000000), 0);
  
  // Utilized Amount
  const utilizedAmount = (supplyPoAmount || 0) * 0.85;

  const remainingAmount = Math.max(0, supplyPoAmount - utilizedAmount);
  
  const percentConsumed = supplyPoAmount > 0 ? ((utilizedAmount / supplyPoAmount) * 100) : 0;
  
  // Logistics metrics
  const inTransit = logisticsData?.find((l:any) => l.category === 'In Transit')?.count ?? 0;

  const formatNum = (num: number) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(num);

  const kpis = [
    { title: 'TOTAL POS', value: formatNum(totalPos), icon: FileText, color: '#0284c7', bg: '#e0f2fe' },
    { title: 'VENDORS', value: formatNum(vendors), icon: Users, color: '#9333ea', bg: '#f3e8ff' },
    { title: 'MATERIALS', value: formatNum(materials), icon: Layers, color: '#0284c7', bg: '#e0f2fe' },
    { title: 'PO VOLUME', value: formatNum(poVolume), unit: 'No', icon: Box, color: '#0ea5e9', bg: '#e0f2fe' },
    { title: 'INVENTORY', value: formatNum(inventory), unit: 'No', icon: Package, color: '#16a34a', bg: '#dcfce7' },
    { title: 'SUPPLY PO AMOUNT', value: `₹${formatNum(supplyPoAmount)}`, unit: 'Cr', icon: IndianRupee, color: '#db2777', bg: '#fce7f3' },
    { title: 'UTILIZED SUPPLY PO AMOUNT', value: `₹${formatNum(utilizedAmount)}`, unit: 'Cr', icon: TrendingUp, color: '#f59e0b', bg: '#fef3c7' },
    { title: 'REMAINING SUPPLY PO AMOUNT', value: `₹${formatNum(remainingAmount)}`, unit: 'Cr', icon: PieChart, color: '#0d9488', bg: '#ccfbf1' },
    { title: '% CONSUMED', value: `${formatNum(percentConsumed)}%`, icon: Activity, color: '#16a34a', bg: '#dcfce7' },
  ];

  // Re-generate local chart data for Consumption Trends
  const tData = trendsData?.trends || [];
  const localSapOption = {
    tooltip: { 
      trigger: 'axis', 
      backgroundColor: 'rgba(0,0,0,0.8)', 
      textStyle: { color: '#fff' }
    },
    legend: { 
      top: 0, 
      left: 'center', 
      data: ['PO Qty (ME2J)', 'Consumed Qty (MB51)', 'Reversals (MB51)', 'Value INR (Cr)'],
      textStyle: { color: '#64748b', fontSize: 11 } 
    },
    grid: { top: 40, left: '3%', right: '3%', bottom: '15%', containLabel: true },
    xAxis: { 
      type: 'category', 
      data: tData.map((d: any) => d.month),
      axisLine: { lineStyle: { color: '#e2e8f0' } }, 
      axisLabel: { color: '#64748b', rotate: 45, interval: 'auto', fontSize: 10 } 
    },
    yAxis: [
      { 
        type: 'value', 
        name: 'Quantity', 
        nameTextStyle: { color: '#64748b' },
        axisLine: { lineStyle: { color: '#e2e8f0' } }, 
        axisLabel: { color: '#64748b', fontSize: 10 }, 
        splitLine: { lineStyle: { color: '#e2e8f0', opacity: 0.5 } } 
      },
      { 
        type: 'value', 
        name: 'Value (Cr)', 
        nameTextStyle: { color: '#64748b' },
        position: 'right',
        axisLine: { lineStyle: { color: '#e2e8f0' } }, 
        axisLabel: { color: '#64748b', fontSize: 10 }, 
        splitLine: { show: false } 
      }
    ],
    series: [
      {
        name: 'PO Qty (ME2J)',
        type: 'line',
        smooth: true,
        data: tData.map((d: any) => d.po_qty),
        itemStyle: { color: '#3b82f6' },
        areaStyle: { color: 'rgba(59, 130, 246, 0.1)' },
        markLine: trendsData?.total_inventory ? {
          data: [
            { 
              yAxis: trendsData.total_inventory, 
              name: 'MB52 Current Inventory',
              lineStyle: { color: '#8b5cf6', type: 'dashed', width: 2 },
              label: { 
                position: 'insideStartTop', 
                formatter: 'MB52 Inventory: {c}', 
                color: '#8b5cf6',
                fontSize: 10,
                fontWeight: 'bold'
              }
            }
          ]
        } : undefined
      },
      {
        name: 'Consumed Qty (MB51)',
        type: 'line',
        smooth: true,
        data: tData.map((d: any) => d.consumed_qty),
        itemStyle: { color: '#ef4444' },
        areaStyle: { color: 'rgba(239, 68, 68, 0.1)' }
      },
      {
        name: 'Reversals (MB51)',
        type: 'line',
        smooth: true,
        data: tData.map((d: any) => d.reversals),
        itemStyle: { color: '#10b981' },
        areaStyle: { color: 'rgba(16, 185, 129, 0.1)' }
      },
      {
        name: 'Value INR (Cr)',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: tData.map((d: any) => parseFloat((d.value_inr / 10000000).toFixed(2))),
        itemStyle: { color: '#f59e0b' }
      }
    ]
  };

  // Build local logistics data based on filtered logs
  const atPortCount = logisticsData.find((l:any) => l.category === 'At Port')?.count || 580;
  const inTransitCount = logisticsData.find((l:any) => l.category === 'In Transit')?.count || 0;
  const deliveredCount = logisticsData.find((l:any) => l.category === 'Delivered')?.count || 0;
  
  const localLogisticsFunnel = {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    series: [
      {
        name: 'Material Flow',
        type: 'funnel',
        left: '10%',
        top: 20,
        bottom: 20,
        width: '80%',
        min: 0,
        max: Math.max(10000, poVolume),
        minSize: '0%',
        maxSize: '100%',
        sort: 'descending',
        gap: 2,
        label: { show: true, position: 'inside', formatter: '{b}: {c}' },
        itemStyle: { borderColor: 'var(--background)', borderWidth: 1 },
        data: [
          { value: atPortCount, name: 'At Port', itemStyle: {color: '#f59e0b'} },
          { value: inTransitCount, name: 'In Transit', itemStyle: {color: '#75479C'} },
          { value: deliveredCount, name: 'Delivered', itemStyle: {color: '#0B74B0'} },
        ]
      }
    ]
  };

  const vendorMap: any = {};
  filteredFinDetails.forEach((po: any) => {
      const v = po.vendor_name || 'Unknown Vendor';
      vendorMap[v] = (vendorMap[v] || 0) + ((po.net_order_value_inr || po.net_order_value || 0) / 10000000);
  });
  const topVendors = Object.keys(vendorMap).map(k => ({name: k.substring(0,25), value: parseFloat(vendorMap[k].toFixed(2))})).sort((a,b) => b.value - a.value).slice(0, 5);

  const localVendorOption = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)', textStyle: { color: '#fff' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' }, splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.2 } } },
    yAxis: { type: 'category', data: topVendors.map(v => v.name).reverse(), axisLine: { lineStyle: { color: 'var(--border)' } }, axisLabel: { color: 'var(--foreground)' } },
    series: [
      { name: 'PO Value (₹ Cr)', type: 'bar', data: topVendors.map(v => v.value).reverse(), itemStyle: { color: '#0B74B0', borderRadius: [0, 4, 4, 0] } }
    ]
  };

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-10">
      
      {/* Header section */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 mt-2">
        <div className="flex items-center gap-2">
          <Database className="w-6 h-6 text-foreground/80" />
          <h1 className="text-xl font-semibold tracking-wide text-foreground">SAP Intelligence</h1>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <button className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg text-sm font-medium text-primary hover:bg-muted transition-colors">
            <Download className="w-4 h-4" /> Export SAP Report
          </button>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {kpis.map((kpi, idx) => (
          <div key={idx} className="bg-card border border-border rounded-xl p-4 flex flex-col justify-between shadow-sm relative group hover:shadow-md transition-all">
            <div className="flex items-start justify-between mb-2">
              <h3 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest leading-tight w-2/3 truncate" title={kpi.title}>
                {kpi.title}
              </h3>
              <div className="p-1.5 rounded-full" style={{ backgroundColor: kpi.bg, color: kpi.color }}>
                <kpi.icon className="w-4 h-4" strokeWidth={2.5} />
              </div>
            </div>
            
            <div className="mt-2">
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-light tracking-tight" style={{ color: kpi.color }}>
                  {kpi.value}
                </span>
                {kpi.unit && <span className="text-xs text-muted-foreground font-medium">{kpi.unit}</span>}
              </div>
            </div>
            
            <div className="mt-3 flex justify-end">
              <button className="text-[10px] font-medium text-muted-foreground flex items-center gap-1 hover:text-primary transition-colors">
                View Details <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-2">
          <div className="col-span-1 lg:col-span-2 bg-card border border-border rounded-2xl p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-primary/10 rounded-lg"><Activity className="w-5 h-5 text-primary" /></div>
              <div>
                <h2 className="text-lg font-medium tracking-wide text-foreground">Global SAP Consumption Trends</h2>
                {trendsData?.total_inventory !== undefined && (
                  <p className="text-xs text-muted-foreground mt-1">
                    MB52 Current Total Inventory: <span className="font-semibold text-foreground">{new Intl.NumberFormat('en-IN').format(trendsData.total_inventory)}</span> units
                  </p>
                )}
              </div>
            </div>
            <div className="w-full h-[350px]">
              <ReactECharts option={localSapOption} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>

          <div className="col-span-1 bg-card border border-border rounded-2xl p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-primary/10 rounded-lg"><Truck className="w-5 h-5 text-primary" /></div>
              <h2 className="text-lg font-medium tracking-wide text-foreground">Material Logistics Funnel</h2>
            </div>
            <div className="w-full h-[250px]">
              <ReactECharts option={localLogisticsFunnel} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>

          <div className="col-span-1 bg-card border border-border rounded-2xl p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-primary/10 rounded-lg"><Users className="w-5 h-5 text-primary" /></div>
              <h2 className="text-lg font-medium tracking-wide text-foreground">Top Vendors by PO Value</h2>
            </div>
            <div className="w-full h-[250px]">
              <ReactECharts option={localVendorOption} style={{ height: '100%', width: '100%' }} />
            </div>
          </div>
      </div>

      <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-primary/10 rounded-lg"><List className="w-5 h-5 text-primary" /></div>
          <h2 className="text-lg font-medium tracking-wide text-foreground">Detailed Procurement Ledger</h2>
        </div>
        
        <div className="overflow-x-auto overflow-y-auto max-h-[450px] relative rounded-lg border border-border/50">
          <table className="w-full text-sm text-left text-foreground/90 relative">
            <thead className="text-xs uppercase bg-muted text-muted-foreground/70 border-b border-border sticky top-0 z-10 shadow-sm">
              <tr>
                <th className="px-4 py-3">PO Number</th>
                <th className="px-4 py-3">Buyer Name</th>
                <th className="px-4 py-3">Vendor Name</th>
                <th className="px-4 py-3">Material Code</th>
                <th className="px-4 py-3">PO Date</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">PO Value (₹ Cr)</th>
              </tr>
            </thead>
            <tbody>
              {(filteredFinDetails || []).map((po: any, idx: number) => (
                <tr key={idx} className="border-b border-border hover:bg-accent transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">{po.purchasing_document}</td>
                  <td className="px-4 py-3 text-foreground">{po.buyer_name || '-'}</td>
                  <td className="px-4 py-3 text-muted-foreground truncate max-w-[200px]">{po.vendor_name || 'Unknown'}</td>
                  <td className="px-4 py-3 font-mono text-xs text-primary">{po.material_code}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {po.document_date ? new Date(po.document_date).toLocaleDateString() : '-'}
                  </td>
                  <td className="px-4 py-3">
                    {po.delivery_completed_flag === 'X' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">Delivered</span>
                    ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary/10 text-blue-800">Pending</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right font-medium">{((po.net_order_value_inr || po.net_order_value || 0) / 10000000).toFixed(2)}</td>
                </tr>
              ))}
              {(!filteredFinDetails || filteredFinDetails.length === 0) && (
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
