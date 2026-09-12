import React, { useState, useEffect, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import { useChartTheme } from '../../lib/chartTheme';
import { Database, FileText, Users, Layers, Box, Package, IndianRupee, TrendingUp, PieChart, Truck, Download, ArrowRight, List, Activity } from 'lucide-react';
import SAPKPIDetailsModal from './SAPKPIDetailsModal';
import TransmissionMiniMap from '../../features/dashboard/TransmissionMiniMap';
import { ChartFrame, SourceTag } from '../ui/primitives';

export default function SAPView({ sapData = [], logisticsData = [], finDetails = [], logDetails = [], loading }: any) {
  // Axis, grid and tooltip chrome come from the shared theme so this screen
  // follows the light/dark toggle instead of pinning slate values.
  const { themeName, chrome, categorical, sequential } = useChartTheme();
  const [trendsData, setTrendsData] = useState<any>(null);
  const [activeKpiModal, setActiveKpiModal] = useState<string | null>(null);

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

  /* Supply position by vendor — delivered vs still-to-deliver, in ₹ Cr, from
     the whole of ZSPS. Replaces two panels:

       · a "logistics funnel" of Delivered 38.8M vs In Transit 380.9M — raw
         quantity columns that mix units of measure and do not reconcile
         (CLAUDE.md: chart value, not quantity), drawn as a funnel, which
         implies stages narrowing when these are two parts of one whole;
       · "top vendors by PO value" rolled up client-side from finDetails,
         which the backend caps at 1,000 of 87,899 lines — so the ranking
         was of a sample and presented as the population.

     /financials/material-breakdown?by=supplier does the honest version in
     SQL: value, partitioned, full table, filterable to the company toggle. */
  const [vendorPosition, setVendorPosition] = useState<{ groups: any[]; group_count: number } | null>(null);
  useEffect(() => {
    const codes = companyFilter === 'spv' ? allSpvCodes : companyFilter === 'agel' ? allAgelCodes : companyFilter === 'age6l' ? allAge6lCodes : [];
    if (companyFilter !== 'all' && codes.length === 0) return; // mappings not loaded yet
    const qs = new URLSearchParams({ by: 'supplier', limit: '8' });
    if (codes.length) qs.set('codes', codes.join(','));
    let cancelled = false;
    fetch(`/akasha/api/financials/material-breakdown?${qs}`)
      .then(r => (r.ok ? r.json() : null))
      .then(j => { if (!cancelled && j) setVendorPosition(j); })
      .catch(() => { /* frame shows its empty state */ });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyFilter, mappings.length]);

  /* echarts-for-react measures once at mount and then only on window resize;
     inside a grid the card can change width without the window doing so. */
  const vendorChartRef = useRef<ReactECharts>(null);
  const vendorHostRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = vendorHostRef.current;
    if (!host) return;
    const ro = new ResizeObserver(() => vendorChartRef.current?.getEchartsInstance().resize());
    ro.observe(host);
    return () => ro.disconnect();
  }, []);

  const isMatch = (po: any, codes: string[]) => {
    const poPlant = (po.plant_code || '').trim();
    const poWbs = (po.wbs_element || '').trim();
    return codes.some(c => {
      const cleanC = c.replace(/^H-/, '').trim();
      return (poPlant && (poPlant.includes(c) || poPlant.includes(cleanC))) ||
             (poWbs && (poWbs.includes(c) || poWbs.includes(cleanC)));
    });
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

  // Utilized Amount - the delivered value ZSPS actually records. This was
  // supplyPoAmount * 0.85, i.e. a flat 85% assumption presented as measured data.
  const utilizedAmount = (companyFilter === 'all' && globalSap.deliveredCapex !== undefined)
    ? globalSap.deliveredCapex
    : filteredFinDetails.reduce((acc: any, curr: any) => acc + (curr.delivered_value_inr_cr || 0), 0);

  const remainingAmount = Math.max(0, supplyPoAmount - utilizedAmount);

  const percentConsumed = supplyPoAmount > 0 ? ((utilizedAmount / supplyPoAmount) * 100) : 0;

  // Logistics metrics
  const inTransit = logisticsData?.find((l: any) => l.category === 'In Transit')?.count ?? 0;

  const formatNum = (num: number) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(num);

  const downloadSAPReport = () => {
    const rows: (string | number)[][] = [
      ['--- SAP Intelligence Global Report ---'],
      ['Scope:', companyFilter.toUpperCase()],
      ['Generated Date:', new Date().toLocaleString('en-IN')],
      ['Total POs:', totalPos],
      ['Vendors:', vendors],
      ['Materials:', materials],
      ['PO Volume:', poVolume],
      ['Inventory:', inventory],
      ['PO Amount (Cr):', typeof supplyPoAmount === 'number' ? supplyPoAmount.toFixed(2) : supplyPoAmount],
      ['Utilized PO Amount (Cr):', typeof utilizedAmount === 'number' ? utilizedAmount.toFixed(2) : utilizedAmount],
      ['Remaining PO Amount (Cr):', typeof remainingAmount === 'number' ? remainingAmount.toFixed(2) : remainingAmount],
      ['% Consumed:', typeof percentConsumed === 'number' ? `${percentConsumed.toFixed(1)}%` : `${percentConsumed}%`],
      [''],
      ['--- Detailed Procurement Ledger ---'],
      ['PO Number', 'Buyer Name', 'Vendor Name', 'Material Code', 'PO Date', 'Status', 'PO Value (₹ Cr)', 'Plant Code', 'WBS Element']
    ];

    (filteredFinDetails || []).forEach((po: any) => {
      rows.push([
        po.purchasing_document || '',
        `"${(po.buyer_name || '').replace(/"/g, '""')}"`,
        `"${(po.vendor_name || '').replace(/"/g, '""')}"`,
        po.material_code || '',
        po.document_date ? new Date(po.document_date).toLocaleDateString('en-IN') : '',
        po.delivery_completed_flag === 'X' ? 'Delivered' : 'Pending',
        ((po.net_order_value_inr || po.net_order_value || 0) / 10000000).toFixed(2),
        po.plant_code || '',
        po.wbs_element || ''
      ]);
    });

    const csvContent = "data:text/csv;charset=utf-8," + rows.map(e => e.join(",")).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `SAP_Intelligence_Report_${companyFilter.toUpperCase()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

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

  const vendorRows = (vendorPosition?.groups || []).slice().reverse(); // echarts draws category[0] at the bottom
  const fmtCr = (v: number) => `₹${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(v)} Cr`;
  const vendorMax = Math.max(0, ...vendorRows.map((g: any) => g.ordered_cr));
  /* Round axis max + interval, or ticks land at 24,112 / 20,000 / 15,000. */
  const vendorStep = vendorMax > 20000 ? 5000 : vendorMax > 8000 ? 2000 : vendorMax > 3000 ? 1000 : vendorMax > 1000 ? 500 : 100;
  const vendorAxisMax = Math.ceil((vendorMax * 1.12) / vendorStep) * vendorStep;

  const localVendorOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: chrome.surface2,
      borderColor: chrome.borderSubtle,
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: chrome.fgPrimary, fontSize: 12 },
      formatter: (params: any) => {
        const g = vendorRows[params[0].dataIndex];
        if (!g) return '';
        const row = (label: string, v: string, strong = false) =>
          `<div style="display:flex;justify-content:space-between;gap:24px;${strong ? 'font-weight:600' : ''}"><span style="color:${chrome.fgSecondary}">${label}</span><span style="font-variant-numeric:tabular-nums">${v}</span></div>`;
        return `<div style="font-weight:600;margin-bottom:6px">${g.name}</div>`
          + row('Ordered', fmtCr(g.ordered_cr), true)
          + row('Delivered', fmtCr(g.delivered_cr))
          + row('Still to deliver', fmtCr(g.in_transit_cr))
          + row('Purchase orders', String(g.pos))
          + `<div style="margin-top:6px;padding-top:6px;border-top:1px solid ${chrome.borderSubtle};color:${chrome.fgSecondary}">${g.delivered_pct}% delivered by value</div>`;
      },
    },
    legend: {
      top: 0, right: 0, itemWidth: 10, itemHeight: 10, itemGap: 16,
      textStyle: { color: chrome.fgSecondary, fontSize: 12 },
    },
    grid: { left: 0, right: 56, top: 28, bottom: 0, containLabel: true },
    xAxis: {
      type: 'value',
      max: vendorAxisMax,
      interval: vendorStep,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: chrome.fgTertiary, fontSize: 11, formatter: (v: number) => (v === 0 ? '0' : `${(v / 1000).toFixed(v % 1000 ? 1 : 0)}k`) },
      splitLine: { lineStyle: { color: chrome.gridLine } },
    },
    yAxis: {
      type: 'category',
      data: vendorRows.map((g: any) => g.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: chrome.fgPrimary, fontSize: 12, width: 190, overflow: 'truncate' },
    },
    series: [
      {
        name: 'Delivered',
        type: 'bar',
        stack: 'value',
        barWidth: 18,
        data: vendorRows.map((g: any) => g.delivered_cr),
        itemStyle: { color: categorical[0] },
      },
      {
        /* Same hue, lighter step — one quantity in two parts, not two
           categories. The status palette is not used: "still to deliver" is
           a stage, not a problem. */
        name: 'Still to deliver',
        type: 'bar',
        stack: 'value',
        barWidth: 18,
        data: vendorRows.map((g: any) => g.in_transit_cr),
        itemStyle: { color: themeName.includes('dark') ? sequential[4] : sequential[2] },
        label: {
          show: true,
          position: 'right',
          distance: 8,
          color: chrome.fgSecondary,
          fontSize: 11,
          formatter: (p: any) => `${vendorRows[p.dataIndex]?.delivered_pct ?? 0}%`,
        },
      },
    ],
  };

  return (
    <div className="flex w-full flex-col gap-6 animate-in fade-in duration-500 pb-10">

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
          <button 
            onClick={downloadSAPReport}
            className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg text-sm font-medium text-primary hover:bg-muted transition-colors cursor-pointer"
            title="Download SAP report as CSV"
          >
            <Download className="w-4 h-4" /> Export SAP Report
          </button>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {kpis.map((kpi, idx) => (
          <div 
            key={idx} 
            onClick={() => setActiveKpiModal(kpi.title)}
            className="kpi-card bento-card px-4 py-3.5 flex flex-col justify-between group cursor-pointer hover:border-primary/50 transition-all shadow-sm hover:shadow-md"
          >
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
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setActiveKpiModal(kpi.title);
                }}
                className="text-[10px] font-semibold text-fg-tertiary flex items-center gap-1 group-hover:text-primary transition-colors focus:outline-none cursor-pointer"
              >
                View Details <ArrowRight className="w-3 h-3" />
              </button>
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

        <ChartFrame
          className="col-span-1 lg:col-span-2"
          icon={Truck}
          eyebrow="Supply position"
          title="Where the outstanding PO value sits, by vendor"
          right={
            <>
              {vendorPosition && (
                <span className="text-[12px] text-fg-tertiary">
                  top {vendorPosition.groups.length} of {new Intl.NumberFormat('en-IN').format(vendorPosition.group_count)} vendors · ₹ Cr
                </span>
              )}
              <SourceTag system="SAP" stamp="ZSPS" />
            </>
          }
          height={Math.max(220, 28 + vendorRows.length * 34)}
        >
          <div ref={vendorHostRef} className="h-full w-full">
            {vendorRows.length > 0 ? (
              <ReactECharts ref={vendorChartRef} theme={themeName} option={localVendorOption} notMerge style={{ height: '100%', width: '100%' }} />
            ) : (
              <div className="flex h-full items-center justify-center text-[13px] text-fg-tertiary">
                {vendorPosition ? 'No purchase orders in this scope.' : 'Loading vendor positions…'}
              </div>
            )}
          </div>
        </ChartFrame>

        {/* Transmission Mini Map / Network Overview */}
        <div className="col-span-1 lg:col-span-2 bento-card p-0 flex flex-col relative h-[450px] overflow-hidden">
          <TransmissionMiniMap />
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

      {/* SAP KPI Details Drill-Down Modal */}
      <SAPKPIDetailsModal
        isOpen={!!activeKpiModal}
        onClose={() => setActiveKpiModal(null)}
        activeKpi={activeKpiModal}
        finDetails={filteredFinDetails}
        logDetails={filteredLogDetails}
        trendsData={trendsData}
        companyFilter={companyFilter}
        kpiSummary={{
          totalPos,
          vendors,
          materials,
          poVolume,
          inventory,
          supplyPoAmount,
          utilizedAmount,
          remainingAmount,
          percentConsumed,
        }}
      />
    </div>
  );
}
