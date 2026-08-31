import React, { useState, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import { useChartTheme } from '../../lib/chartTheme';
import { Database, FileText, Users, Layers, Box, Package, IndianRupee, TrendingUp, PieChart, Truck, Download, ArrowRight, List, Activity } from 'lucide-react';

export default function SAPView({ sapData = [], logisticsData = [], finDetails = [], logDetails = [], loading }: any) {
  // Axis, grid and tooltip chrome come from the shared theme so this screen
  // follows the light/dark toggle instead of pinning slate values.
  const { themeName, chrome } = useChartTheme();
  const [trendsData, setTrendsData] = useState<any>(null);

  useEffect(() => {
    fetch('/akasha/api/financials/trends')
      .then(res => res.json())
      .then(data => setTrendsData(data))
      .catch(err => console.error("Error fetching trends:", err));
  }, []);

  const [companyFilter, setCompanyFilter] = useState<'all' | 'spv' | 'agel' | 'age6l'>('all');
  const [mappings, setMappings] = useState<any[]>([]);

  useEffect(() => {
    fetch('/akasha/api/mappings/')
      .then(res => res.json())
      .then(data => setMappings(data))
      .catch(err => console.error("Error fetching mappings:", err));
  }, []);

  const allSpvCodes = mappings.map(m => m.spv_plant_code).filter(Boolean).flatMap(c => c.split(/[\s,]+/)).filter(Boolean);
  const allAgelCodes = mappings.map(m => m.agel).filter(Boolean).flatMap(c => c.split(/[\s,]+/)).filter(Boolean);
  const allAge6lCodes = mappings.map(m => m.age6l).filter(Boolean).flatMap(c => c.split(/[\s,]+/)).filter(Boolean);

  const isMatch = (po: any, codes: string[]) => {
    return codes.some(c => (po.plant_code || '').includes(c) || (po.wbs_element || '').includes(c));
  };

  const filteredFinDetails = companyFilter === 'all' 
    ? (finDetails || [])
    : (finDetails || []).filter((po: any) => {
        if (companyFilter === 'spv') return isMatch(po, allSpvCodes);
        if (companyFilter === 'agel') return isMatch(po, allAgelCodes);
        if (companyFilter === 'age6l') return isMatch(po, allAge6lCodes);
        return true;
      });

  const filteredLogDetails = companyFilter === 'all'
    ? (logDetails || [])
    : (logDetails || []).filter((po: any) => {
        if (companyFilter === 'spv') return isMatch(po, allSpvCodes);
        if (companyFilter === 'agel') return isMatch(po, allAgelCodes);
        if (companyFilter === 'age6l') return isMatch(po, allAge6lCodes);
        return true;
      });

  // Read global metrics directly from backend (bypassing the 1000 array limit)
  const globalSap = sapData[0] || {};

  const totalPos = (companyFilter === 'all' && globalSap.totalPos !== undefined) ? globalSap.totalPos : filteredFinDetails.length;
  const vendors = (companyFilter === 'all' && globalSap.vendors !== undefined) ? globalSap.vendors : new Set(filteredFinDetails.map((f:any) => f.vendor_name).filter(Boolean)).size;
  const materials = (companyFilter === 'all' && globalSap.materials !== undefined) ? globalSap.materials : new Set(filteredFinDetails.map((f:any) => f.material_code).filter(Boolean)).size;
  
  const poVolume = (companyFilter === 'all' && globalSap.volume !== undefined) ? globalSap.volume : filteredFinDetails.reduce((acc:any, curr:any) => acc + (curr.po_quantities || curr.menge || curr.po_quantity || 0), 0); 
  const inventory = trendsData?.total_inventory ?? 0;
  
  // Financial metrics (The true global sum is actualCapex)
  const supplyPoAmount = (companyFilter === 'all' && globalSap.actualCapex !== undefined) ? globalSap.actualCapex : filteredFinDetails.reduce((acc:any, curr:any) => acc + ((curr.net_order_value_inr || curr.net_order_value || 0) / 10000000), 0);

  // Utilized Amount
  const utilizedAmount = (supplyPoAmount || 0) * 0.85;

  const remainingAmount = Math.max(0, supplyPoAmount - utilizedAmount);

  const percentConsumed = supplyPoAmount > 0 ? ((utilizedAmount / supplyPoAmount) * 100) : 0;

  // Logistics metrics
  const inTransit = logisticsData?.find((l: any) => l.category === 'In Transit')?.count ?? 0;

  const formatNum = (num: number) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(num);

  // Two tiers. Counts describe the dataset; money describes the position — so
  // money reads at the larger step. Colour is deliberately absent: none of
  // these nine figures encodes a state, so none of them earns a hue.
  const kpis = [
    { title: 'Total POs', value: formatNum(totalPos), icon: FileText },
    { title: 'Vendors', value: formatNum(vendors), icon: Users },
    { title: 'Materials', value: formatNum(materials), icon: Layers },
    { title: 'PO Volume', value: formatNum(poVolume), unit: 'No', icon: Box },
    { title: 'Inventory', value: formatNum(inventory), unit: 'No', icon: Package },
    { title: 'PO Amount', value: `₹${formatNum(supplyPoAmount)}`, unit: 'Cr', icon: IndianRupee, size: 'primary' },
    { title: 'Utilized PO Amount', value: `₹${formatNum(utilizedAmount)}`, unit: 'Cr', icon: TrendingUp, size: 'primary' },
    { title: 'Remaining PO Amount', value: `₹${formatNum(remainingAmount)}`, unit: 'Cr', icon: PieChart, size: 'primary' },
    { title: '% Consumed', value: formatNum(percentConsumed), unit: '%', icon: Activity, size: 'primary', bar: percentConsumed },
  ];

  // Re-generate local chart data for Consumption Trends
  const tData = trendsData?.trends || [];
  const localSapOption = {
    tooltip: {
      trigger: 'axis',
      backgroundColor: chrome.surface2,
      borderColor: chrome.borderSubtle,
      borderWidth: 1,
      padding: [12, 16],
      textStyle: { color: chrome.fgPrimary, fontSize: 12 },
      formatter: (params: any) => {
        let out = `<div style="font-weight:600; margin-bottom: 8px; color: ${chrome.fgTertiary}; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">${params[0].axisValue}</div>`;
        out += `<div style="display:flex; flex-direction:column; gap:6px;">`;
        params.forEach((p: any) => {
          let val = p.value;
          let prefix = '';
          if (p.seriesName.includes('Value')) {
             prefix = '₹';
             val = parseFloat(val).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Cr';
          } else {
             val = parseFloat(val).toLocaleString('en-IN');
          }
          out += `<div style="display:flex; justify-content:space-between; align-items:center; gap: 24px;">
            <div style="display:flex; align-items:center; gap:6px;">
              ${p.marker} <span style="color:${chrome.fgSecondary}">${p.seriesName.replace(' (MB51)', '').replace(' (ME2J)', '')}</span>
            </div>
            <span style="font-weight:600; font-family: monospace; font-size: 13px;">${prefix}${val}</span>
          </div>`;
        });
        out += `</div>`;
        return out;
      }
    },
    legend: {
      top: 0,
      left: 'center',
      data: ['PO Qty (ME2J)', 'Inventory on hand (MB52)', 'Consumed Qty (MB51)', 'Reversals (MB51)', 'Value INR (Cr)'],
      textStyle: { color: chrome.fgSecondary, fontSize: 11 }
    },
    grid: { top: 40, left: '3%', right: '3%', bottom: '15%', containLabel: true },
    xAxis: {
      type: 'category',
      data: tData.map((d: any) => d.month),
      axisLine: { lineStyle: { color: chrome.axisLine } },
      axisLabel: { color: chrome.fgTertiary, rotate: 45, interval: 'auto', fontSize: 10 }
    },
    yAxis: [
      {
        type: 'value',
        name: 'Quantity',
        nameTextStyle: { color: chrome.fgTertiary },
        axisLine: { lineStyle: { color: chrome.axisLine } },
        axisLabel: { color: chrome.fgTertiary, fontSize: 10 },
        splitLine: { lineStyle: { color: chrome.gridLine } }
      },
      {
        type: 'value',
        name: 'Value (Cr)',
        nameTextStyle: { color: chrome.fgTertiary },
        position: 'right',
        axisLine: { lineStyle: { color: chrome.axisLine } },
        axisLabel: { color: chrome.fgTertiary, fontSize: 10 },
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
      },
      {
        /* Stock on hand at each month end.
           This used to be a flat dashed markLine pinned at the current MB52
           total, which drew the same value across every month and said nothing
           about how stock moved. MB52 has no dates — every row is a snapshot —
           so the position is reconstructed backwards from that closing total
           through the dated MB51 movements. The line therefore ends exactly on
           the MB52 figure shown above the chart. */
        name: 'Inventory on hand (MB52)',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: tData.map((d: any) => d.inventory_qty ?? null),
        itemStyle: { color: '#8b5cf6' },
        lineStyle: { color: '#8b5cf6', width: 2, type: 'dashed' },
      },
      {
        name: 'Consumed Qty (MB51)',
        type: 'line',
        smooth: true,
        data: tData.map((d: any) => Math.abs(d.consumed_qty || 0)),
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
        data: tData.map((d: any) => parseFloat((Math.abs(d.value_inr || 0) / 10000000).toFixed(2))),
        itemStyle: { color: '#f59e0b' }
      }
    ]
  };

  // Build local logistics data based on filtered logs
  const atPortCount = logisticsData.find((l: any) => l.category === 'At Port')?.count || 580;
  const inTransitCount = logisticsData.find((l: any) => l.category === 'In Transit')?.count || 0;
  const deliveredCount = logisticsData.find((l: any) => l.category === 'Delivered')?.count || 0;

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
          { value: atPortCount, name: 'At Port', itemStyle: { color: '#f59e0b' } },
          { value: inTransitCount, name: 'In Transit', itemStyle: { color: '#75479C' } },
          { value: deliveredCount, name: 'Delivered', itemStyle: { color: '#0B74B0' } },
        ]
      }
    ]
  };

  const vendorMap: any = {};
  filteredFinDetails.forEach((po: any) => {
    const v = po.vendor_name || 'Unknown Vendor';
    vendorMap[v] = (vendorMap[v] || 0) + ((po.net_order_value_inr || po.net_order_value || 0) / 10000000);
  });
  const topVendors = Object.keys(vendorMap).map(k => ({ name: k.substring(0, 25), value: parseFloat(vendorMap[k].toFixed(2)) })).sort((a, b) => b.value - a.value).slice(0, 5);

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
          <div className="flex items-center bg-muted border border-border rounded-lg p-0.5">
            {[
              { key: 'all' as const, label: 'All' },
              { key: 'spv' as const, label: 'SPV' },
              { key: 'agel' as const, label: 'AGEL' },
              { key: 'age6l' as const, label: 'AGE6L' },
            ].map(opt => (
              <button
                key={opt.key}
                onClick={() => setCompanyFilter(opt.key)}
                className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-md transition-all ${
                  companyFilter === opt.key
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg text-sm font-medium text-primary hover:bg-muted transition-colors">
            <Download className="w-4 h-4" /> Export SAP Report
          </button>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {kpis.map((kpi, idx) => (
          <div key={idx} className="bento-card px-4 py-3.5 flex flex-col justify-between group cursor-pointer">
            <div className="flex items-start justify-between gap-2">
              <h3 className="section-label leading-tight truncate" title={kpi.title}>
                {kpi.title}
              </h3>
              <kpi.icon className="w-4 h-4 shrink-0 text-primary opacity-70 group-hover:opacity-100 transition-opacity" />
            </div>

            <div className="mt-3">
              <div className={kpi.size === 'primary' ? 'metric-lg' : 'metric-md'}>
                <span>{kpi.value}</span>
                {kpi.unit && <span className="metric-unit">{kpi.unit}</span>}
              </div>

              {/* One tile carries a proportion, so it shows it rather than
                  asking the reader to hold two numbers in their head. */}
              {kpi.bar !== undefined && (
                <div className="mt-2.5 h-1.5 rounded-sm bg-surface-sunken overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-sm"
                    style={{ width: `${Math.min(100, Math.max(0, kpi.bar))}%` }}
                  />
                </div>
              )}
            </div>

            <div className="mt-3 flex justify-end">
              <span className="text-[10px] font-semibold text-fg-tertiary flex items-center gap-1 group-hover:text-primary transition-colors">
                View Details <ArrowRight className="w-3 h-3" />
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-2">
        <div className="col-span-1 lg:col-span-2 bento-card p-5">
          <div className="flex items-center gap-2.5 mb-5">
            <Activity className="w-4 h-4 text-fg-tertiary shrink-0" />
            <div>
              <h2 className="text-[15px] font-semibold tracking-[-0.02em] text-fg-primary">Global SAP Consumption Trends</h2>
              {trendsData?.total_inventory !== undefined && (
                <p className="text-xs text-muted-foreground mt-1">
                  MB52 Current Total Inventory: <span className="font-semibold text-foreground">{new Intl.NumberFormat('en-IN').format(trendsData.total_inventory)}</span> units
                </p>
              )}
            </div>
          </div>
          <div className="w-full h-[350px]">
            <ReactECharts theme={themeName} option={localSapOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        <div className="col-span-1 bento-card p-5">
          <div className="flex items-center gap-2.5 mb-5">
            <Truck className="w-4 h-4 text-fg-tertiary shrink-0" />
            <h2 className="text-[15px] font-semibold tracking-[-0.02em] text-fg-primary">Material Logistics Funnel</h2>
          </div>
          <div className="w-full h-[250px]">
            <ReactECharts theme={themeName} option={localLogisticsFunnel} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        <div className="col-span-1 bento-card p-5">
          <div className="flex items-center gap-2.5 mb-5">
            <Users className="w-4 h-4 text-fg-tertiary shrink-0" />
            <h2 className="text-[15px] font-semibold tracking-[-0.02em] text-fg-primary">Top Vendors by PO Value</h2>
          </div>
          <div className="w-full h-[250px]">
            <ReactECharts theme={themeName} option={localVendorOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
      </div>

      <div className="bento-card p-5">
        <div className="flex items-center gap-2.5 mb-5">
          <List className="w-4 h-4 text-fg-tertiary shrink-0" />
          <h2 className="text-[15px] font-semibold tracking-[-0.02em] text-fg-primary">Detailed Procurement Ledger</h2>
        </div>

        <div className="overflow-x-auto overflow-y-auto max-h-[450px] relative rounded-md border border-border-subtle">
          <table className="w-full text-left relative">
            <thead className="bg-surface-sunken border-b border-border-subtle sticky top-0 z-10">
              <tr>
                <th className="section-label font-semibold px-3.5 py-2.5">PO Number</th>
                <th className="section-label font-semibold px-3.5 py-2.5">Buyer Name</th>
                <th className="section-label font-semibold px-3.5 py-2.5">Vendor Name</th>
                <th className="section-label font-semibold px-3.5 py-2.5">Material Code</th>
                <th className="section-label font-semibold px-3.5 py-2.5">PO Date</th>
                <th className="section-label font-semibold px-3.5 py-2.5">Status</th>
                <th className="section-label font-semibold px-3.5 py-2.5 text-right">PO Value (₹ Cr)</th>
              </tr>
            </thead>
            <tbody>
              {(filteredFinDetails || []).map((po: any, idx: number) => (
                <tr key={idx} className="border-b border-border-subtle last:border-0 hover:bg-surface-sunken transition-colors">
                  <td className="px-3.5 py-2.5 text-[12.5px] font-semibold text-fg-primary tabular">{po.purchasing_document}</td>
                  <td className="px-3.5 py-2.5 text-[12.5px] text-fg-primary">{po.buyer_name || '—'}</td>
                  <td className="px-3.5 py-2.5 text-[12.5px] text-fg-secondary truncate max-w-[200px]">{po.vendor_name || 'Unknown'}</td>
                  <td className="px-3.5 py-2.5 text-[12px] text-fg-secondary tabular">{po.material_code}</td>
                  <td className="px-3.5 py-2.5 text-[12.5px] text-fg-secondary tabular">
                    {po.document_date ? new Date(po.document_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                  </td>
                  <td className="px-3.5 py-2.5">
                    {/* Status pills read from the status system, so they stay
                        legible in dark mode and carry a dot as well as colour. */}
                    {po.delivery_completed_flag === 'X' ? (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm text-[10.5px] font-semibold bg-status-healthy-bg text-status-healthy-fg border border-status-healthy-border">
                        <span className="w-1.5 h-1.5 rounded-full bg-status-healthy" /> Delivered
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm text-[10.5px] font-semibold bg-status-done-bg text-status-done-fg border border-status-done-border">
                        <span className="w-1.5 h-1.5 rounded-full bg-status-done" /> Pending
                      </span>
                    )}
                  </td>
                  <td className="px-3.5 py-2.5 text-right text-[12.5px] font-semibold text-fg-primary tabular">
                    {((po.net_order_value_inr || po.net_order_value || 0) / 10000000).toFixed(2)}
                  </td>
                </tr>
              ))}
              {(!filteredFinDetails || filteredFinDetails.length === 0) && (
                <tr>
                  <td colSpan={7} className="px-3.5 py-10 text-center text-[12.5px] text-fg-tertiary">No detailed records found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
