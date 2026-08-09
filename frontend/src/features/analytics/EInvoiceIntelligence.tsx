import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import { 
  FileText, Activity, AlertCircle, CheckCircle2, TrendingUp, TrendingDown,
  MapPin, Box, Filter, Search, ChevronDown, ChevronUp, Calendar, PieChart
} from 'lucide-react';

export default function EInvoiceIntelligence() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Filtering state
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [vendorViewMode, setVendorViewMode] = useState<'Top Billed' | 'Lowest Execution'>('Top Billed');

  useEffect(() => {
    fetch('/akasha/api/einvoice/global')
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch E-Invoice data');
        return res.json();
      })
      .then(json => {
        setData(json);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[500px] text-muted-foreground">
        <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin mb-4" />
        <p>Loading E-Invoice Intelligence...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[500px] text-destructive">
        <AlertCircle className="w-12 h-12 mb-4 opacity-50" />
        <p>{error}</p>
      </div>
    );
  }

  const formatLacs = (val: number) => `₹${(val / 100000).toLocaleString('en-IN', { maximumFractionDigits: 2 })} L`;

  const { metrics, distributions, invoices } = data;

  // Filter invoices for the table
  const filteredInvoices = invoices.filter((inv: any) => {
    const matchesSearch = 
      (inv.invoiceNo || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (inv.workOrderNo || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (inv.vendorName || '').toLowerCase().includes(searchTerm.toLowerCase());
      
    const matchesType = typeFilter === 'All' || (inv.projectType || '') === typeFilter;
    const matchesStatus = statusFilter === 'All' || (inv.statusDesc || 'Pending') === statusFilter;
    
    return matchesSearch && matchesType && matchesStatus;
  });

  const projectTypeOption = {
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { trigger: 'item', formatter: '{b}: ₹{c} L ({d}%)', backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#334155', textStyle: { color: '#f8fafc' } },
    legend: { bottom: '0%', left: 'center', textStyle: { color: '#94a3b8', fontSize: 11 }, icon: 'circle' },
    series: [
      {
        type: 'pie',
        radius: ['50%', '75%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 4, borderWidth: 0 },
        label: { show: false },
        data: distributions.byProjectType.map((item: any) => ({
          name: item.name || 'Unknown',
          value: Number((item.value / 100000).toFixed(2))
        }))
      }
    ]
  };

  let activeVendors = [];
  if (vendorViewMode === 'Top Billed') {
    activeVendors = [...(distributions.byVendor || [])].sort((a: any, b: any) => b.invoice - a.invoice).slice(0, 10);
  } else {
    activeVendors = [...(distributions.byVendor || [])]
      .filter((v: any) => v.so > 0)
      .map((v: any) => ({ ...v, execPercent: (v.invoice / v.so) * 100 }))
      .sort((a: any, b: any) => a.execPercent - b.execPercent)
      .slice(0, 10);
  }

  const vendorOption = {
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: function(params: any) {
      let tooltip = `<div class="font-bold text-sm mb-1">${params[0].name}</div>`;
      params.forEach((p: any) => {
        let valStr = p.seriesName === 'Execution %' ? p.value + '%' : '₹' + p.value + ' L';
        tooltip += `<div><span style="display:inline-block;margin-right:4px;border-radius:10px;width:10px;height:10px;background-color:${p.color};"></span>${p.seriesName}: <b>${valStr}</b></div>`;
      });
      return tooltip;
    }, backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#334155', textStyle: { color: '#f8fafc' } },
    legend: { top: 0, right: 0, textStyle: { color: '#94a3b8', fontSize: 10 } },
    grid: { left: '2%', right: '2%', bottom: '2%', top: '15%', containLabel: true },
    xAxis: { 
      type: 'category', 
      data: activeVendors.map((v: any) => v.name || 'Unknown'),
      axisLabel: { color: '#94a3b8', fontSize: 9, width: 60, overflow: 'truncate', interval: 0, rotate: 30 }
    },
    yAxis: [
      { type: 'value', splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } }, axisLabel: { color: '#94a3b8', fontSize: 9 } },
      { type: 'value', min: 0, max: 100, splitLine: { show: false }, axisLabel: { formatter: '{value}%', color: vendorViewMode === 'Lowest Execution' ? '#ef4444' : '#10b981', fontSize: 9 } }
    ],
    series: [
      {
        name: 'Billed',
        type: 'bar',
        barGap: 0,
        data: activeVendors.map((item: any) => Number((item.invoice / 100000).toFixed(2))),
        itemStyle: { color: '#3b82f6', borderRadius: [2, 2, 0, 0] }
      },
      {
        name: 'SO Value',
        type: 'bar',
        data: activeVendors.map((item: any) => Number((item.so / 100000).toFixed(2))),
        itemStyle: { color: '#64748b', borderRadius: [2, 2, 0, 0] }
      },
      {
        name: 'Execution %',
        type: 'line',
        yAxisIndex: 1,
        data: activeVendors.map((item: any) => {
          if (vendorViewMode === 'Lowest Execution') return Number(item.execPercent.toFixed(1));
          return item.so > 0 ? Number(((item.invoice / item.so) * 100).toFixed(1)) : 0;
        }),
        itemStyle: { color: vendorViewMode === 'Lowest Execution' ? '#ef4444' : '#10b981' },
        lineStyle: { width: 2, type: 'dashed' },
        symbol: 'circle',
        symbolSize: 6
      }
    ]
  };

  const statusOption = {
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { trigger: 'item', formatter: '{b}: ₹{c} L ({d}%)', backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#334155', textStyle: { color: '#f8fafc' } },
    legend: { bottom: '0%', left: 'center', textStyle: { color: '#94a3b8', fontSize: 11 }, icon: 'circle' },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '45%'],
        itemStyle: { borderRadius: 4, borderWidth: 0 },
        label: { show: false },
        data: (distributions.byStatusValue || []).map((item: any) => ({
          name: item.name || 'Unknown',
          value: Number((item.value / 100000).toFixed(2))
        }))
      }
    ]
  };

  const monthData = distributions.byMonth || [];
  const monthOption = {
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#334155', textStyle: { color: '#f8fafc' } },
    grid: { left: '3%', right: '4%', bottom: '10%', top: '10%', containLabel: true },
    xAxis: { 
      type: 'category', 
      boundaryGap: false, 
      data: monthData.map((d: any) => d.name),
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel: { color: '#94a3b8', fontSize: 10 }
    },
    yAxis: { 
      type: 'value',
      splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      axisLabel: { color: '#94a3b8', fontSize: 10 }
    },
    series: [
      {
        name: 'Invoice Value',
        type: 'line',
        smooth: true,
        data: monthData.map((d: any) => Number((d.value / 100000).toFixed(2))),
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: 'rgba(59,130,246,0.5)' }, { offset: 1, color: 'rgba(59,130,246,0.0)' }]
          }
        },
        itemStyle: { color: '#3b82f6' },
        lineStyle: { width: 3 }
      }
    ]
  };

  const topLocations = [...(distributions.byLocation || [])].sort((a: any, b: any) => b.value - a.value).slice(0, 5).reverse();
  const locationOption = {
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: '{b}<br/><b>₹{c} L</b>', backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#334155', textStyle: { color: '#f8fafc' } },
    grid: { left: '2%', right: '12%', bottom: '2%', top: '2%', containLabel: true },
    xAxis: { type: 'value', show: false },
    yAxis: { 
      type: 'category', 
      data: topLocations.map((v: any) => v.name || 'Unknown'),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#94a3b8', width: 100, overflow: 'truncate', fontSize: 10, fontFamily: 'Adani' }
    },
    series: [
      {
        type: 'bar',
        data: topLocations.map((v: any) => Number((v.value / 100000).toFixed(2))),
        itemStyle: { color: '#10b981', borderRadius: [0, 4, 4, 0] },
        barWidth: '40%',
        label: { show: true, position: 'right', color: '#94a3b8', formatter: '₹{c} L', fontSize: 10, fontFamily: 'Adani' }
      }
    ]
  };

  const funnelData = distributions.byStage || [];
  const funnelOption = {
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { trigger: 'item', formatter: '{b} : {c}', backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#334155', textStyle: { color: '#f8fafc' } },
    color: ['#3b82f6', '#8b5cf6', '#f59e0b', '#ef4444', '#10b981'],
    series: [
      {
        name: 'Workflow Stage',
        type: 'funnel',
        left: '15%', right: '25%', top: 20, bottom: 20,
        min: 0, max: Math.max(...funnelData.map((d: any) => d.value), 1),
        minSize: '15%', maxSize: '90%',
        sort: 'descending',
        gap: 3,
        label: { show: true, position: 'right', formatter: '{b}: {c}', color: '#64748b', fontSize: 12, fontWeight: 'bold' },
        labelLine: { length: 15, lineStyle: { width: 1, type: 'solid', color: '#cbd5e1' } },
        itemStyle: { borderColor: '#ffffff', borderWidth: 2, borderRadius: 4 },
        data: funnelData
      }
    ]
  };

  const approverData = (distributions.byApprover || []).slice(0, 10).reverse();
  const approverOption = {
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: '{b}<br/>Count: {c} pending', backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#334155', textStyle: { color: '#f8fafc' } },
    grid: { left: '5%', right: '12%', bottom: '5%', top: '5%', containLabel: true },
    xAxis: { type: 'value', show: false },
    yAxis: { 
      type: 'category', 
      data: approverData.map((v: any) => v.name),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { 
        color: '#ef4444', 
        fontWeight: 'bold', 
        fontSize: 11,
        formatter: function (value: string) {
            return value.length > 25 ? value.substring(0, 25) + '...' : value;
        }
      }
    },
    series: [
      {
        name: 'Pending Invoices',
        type: 'bar',
        data: approverData.map((v: any) => v.count),
        itemStyle: { color: '#ef4444', borderRadius: [0, 4, 4, 0] },
        barWidth: '50%',
        label: { show: true, position: 'right', color: '#ef4444', fontWeight: 'bold' }
      }
    ]
  };

  const scatterDataRaw = (data.invoices || []).map((inv: any) => {
    const invDateStr = inv.invoiceDate;
    if (invDateStr) {
      let date: Date | null = null;
      if (invDateStr.includes('/Date(')) {
        const match = /\/Date\((\d+)/.exec(invDateStr);
        if (match) {
          date = new Date(parseInt(match[1], 10));
        }
      } else {
        date = new Date(invDateStr);
      }
      
      if (date && !isNaN(date.getTime())) {
        const dateStr = date.toISOString().split('T')[0];
        const amt = parseFloat(inv.invoiceAmount) || 0;
        const soAmt = parseFloat(inv.SOAmount) || 0;
        const status = (inv.statusDesc || 'Pending').trim();
        return [
          dateStr, 
          Number((amt / 100000).toFixed(2)), 
          inv.invoiceNo, 
          inv.vendorName || 'Unknown', 
          status,
          inv.packageName || 'N/A',
          inv.projectType || 'N/A',
          inv.workLocation || 'N/A',
          inv.workOrderNo || 'N/A',
          inv.workDescription || 'N/A',
          inv.p6ProjectName || 'Unknown Project',
          Number((soAmt / 100000).toFixed(2))
        ];
      }
    }
    return null;
  }).filter(Boolean);

  const statuses = Array.from(new Set(scatterDataRaw.map((d: any) => d[4])));
  const scatterSeries = statuses.map(status => ({
    name: status,
    type: 'scatter',
    symbolSize: (data: any) => Math.min(Math.max(data[1] / 10, 8), 45),
    itemStyle: { opacity: 0.7 },
    data: scatterDataRaw.filter((d: any) => d[4] === status)
  }));

  const scatterOption = {
    textStyle: { fontFamily: 'Adani, sans-serif' },
    tooltip: { 
      trigger: 'item',
      formatter: (params: any) => {
        const p = params.value;
        return `
          <div class="text-xs space-y-2" style="max-width: 300px; white-space: normal;">
            <div class="flex justify-between items-center border-b border-slate-600 pb-1 mb-1">
              <span class="font-bold text-sm text-slate-100">Invoice Details</span>
              <span class="text-slate-400 font-mono">${p[0]}</span>
            </div>
            
            <div class="space-y-1">
              <div class="font-semibold text-slate-400 mb-1 uppercase text-[10px] tracking-wider">Project Details</div>
              <div><span class="text-slate-400">Name:</span> <span class="text-sky-300 font-bold">${p[10]}</span></div>
              <div><span class="text-slate-400">Type:</span> ${p[6]}</div>
              <div><span class="text-slate-400">Package:</span> ${p[5]}</div>
              <div><span class="text-slate-400">Location:</span> ${p[7]}</div>
              <div><span class="text-slate-400">Desc:</span> ${p[9]}</div>
            </div>

            <div class="border-t border-slate-600 my-1"></div>

            <div class="space-y-1">
              <div class="font-semibold text-slate-400 mb-1 uppercase text-[10px] tracking-wider">Vendor Details</div>
              <div><span class="text-slate-400">Vendor:</span> <span class="text-slate-200 font-medium">${p[3]}</span></div>
              <div><span class="text-slate-400">Invoice:</span> ${p[2]}</div>
              <div><span class="text-slate-400">WO:</span> ${p[8]}</div>
            </div>

            <div class="border-t border-slate-600 my-1"></div>

            <div class="flex justify-between items-center bg-slate-800/50 p-2 rounded border border-slate-700">
              <div>
                <div class="text-slate-400 text-[10px] uppercase">Status</div>
                <div class="font-bold ${(p[4] || '').toLowerCase() === 'completed' ? 'text-emerald-400' : 'text-warning'}">${p[4]}</div>
              </div>
              <div class="text-right">
                <div class="text-slate-400 text-[10px] uppercase">SO Amount</div>
                <div class="font-bold text-slate-300 text-sm mb-1">₹${p[11]} L</div>
                
                <div class="text-slate-400 text-[10px] uppercase border-t border-slate-600 pt-1 mt-1">Invoice Amount</div>
                <div class="font-bold text-sky-400 text-sm">₹${p[1]} L</div>
              </div>
            </div>
          </div>
        `;
      },
      backgroundColor: 'rgba(15, 23, 42, 0.95)', 
      borderColor: '#334155', 
      textStyle: { color: '#f8fafc' } 
    },
    legend: { top: 5, left: 'center', textStyle: { color: '#94a3b8', fontSize: 11 }, icon: 'circle' },
    grid: { left: '3%', right: '4%', bottom: '15%', top: '15%', containLabel: true },
    xAxis: { 
      type: 'time',
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel: { color: '#94a3b8', fontSize: 10 }
    },
    yAxis: { 
      type: 'value',
      name: 'Amount (Lacs)',
      nameTextStyle: { color: '#94a3b8', fontSize: 10 },
      splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
      axisLabel: { color: '#94a3b8', fontSize: 10 }
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'filter' },
      { type: 'slider', xAxisIndex: 0, filterMode: 'empty', height: 24, bottom: 5, borderColor: 'transparent', backgroundColor: '#e2e8f0', fillerColor: 'rgba(59,130,246,0.2)' }
    ],
    series: scatterSeries
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
            E-Invoice Intelligence
          </h2>
          <p className="text-sm text-muted-foreground mt-1">Global aggregation of all electronic invoices</p>
        </div>
      </div>

      {/* Top Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <FileText className="w-4 h-4 text-primary" />
            </div>
            <h3 className="text-sm font-medium text-muted-foreground">Total Invoices</h3>
          </div>
          <div className="text-3xl font-bold font-mono text-foreground">{metrics.totalInvoices}</div>
        </div>
        
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-blue-500" />
            </div>
            <h3 className="text-sm font-medium text-muted-foreground">Total Value</h3>
          </div>
          <div className="text-3xl font-bold font-mono text-blue-500">{formatLacs(metrics.totalAmount)}</div>
        </div>
        
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-success/10 flex items-center justify-center">
              <CheckCircle2 className="w-4 h-4 text-success" />
            </div>
            <h3 className="text-sm font-medium text-muted-foreground">Completed Value</h3>
          </div>
          <div className="text-3xl font-bold font-mono text-success">{formatLacs(metrics.completedAmount)}</div>
        </div>
        
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-warning/10 flex items-center justify-center">
              <Activity className="w-4 h-4 text-warning" />
            </div>
            <h3 className="text-sm font-medium text-muted-foreground">Pending Value</h3>
          </div>
          <div className="text-3xl font-bold font-mono text-warning">{formatLacs(metrics.pendingAmount)}</div>
        </div>
      </div>

      {/* Extended Analytics Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        
        {/* Project Type */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-bold text-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
            <Box className="w-4 h-4 text-primary" />
            Spend By Project Type
          </h3>
          <div className="h-[250px] w-full">
            <ReactECharts option={projectTypeOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        {/* Workflow Funnel */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-bold text-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
            <Filter className="w-4 h-4 text-primary" />
            Workflow Pipeline
          </h3>
          <div className="h-[250px] w-full">
            <ReactECharts option={funnelOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        {/* Approver Bottlenecks */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-bold text-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-destructive" />
            Approver Bottlenecks
          </h3>
          <div className="h-[250px] w-full">
            <ReactECharts option={approverOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        {/* Vendor Dual Axis */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm col-span-1 lg:col-span-2 xl:col-span-2">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-sm font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
              {vendorViewMode === 'Top Billed' ? <Activity className="w-4 h-4 text-primary" /> : <TrendingDown className="w-4 h-4 text-destructive" />}
              Vendor Performance Analytics
            </h3>
            <div className="flex bg-muted/50 p-1 rounded-lg border border-border">
              <button 
                onClick={() => setVendorViewMode('Top Billed')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${vendorViewMode === 'Top Billed' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
              >
                Top Billed
              </button>
              <button 
                onClick={() => setVendorViewMode('Lowest Execution')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${vendorViewMode === 'Lowest Execution' ? 'bg-destructive text-destructive-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
              >
                Lagging
              </button>
            </div>
          </div>
          <div className="h-[250px] w-full">
            <ReactECharts option={vendorOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
        
        {/* Invoice Status */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-bold text-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
            <PieChart className="w-4 h-4 text-primary" />
            Spend By Status
          </h3>
          <div className="h-[250px] w-full">
            <ReactECharts option={statusOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        {/* Scatter Chart (Outliers) */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm col-span-1 lg:col-span-2 xl:col-span-3">
          <h3 className="text-sm font-bold text-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-primary" />
            Invoice Outliers & Timeline (Scatter)
          </h3>
          <div className="h-[450px] w-full">
            <ReactECharts option={scatterOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

      </div>

      {/* Global Master Table */}
      <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden flex flex-col">
        <div className="p-4 border-b border-border bg-muted/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">Global Invoice Master</h3>
          <div className="flex items-center gap-3">
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input 
                type="text" 
                placeholder="Search invoice, WO, or vendor..." 
                className="w-full pl-9 pr-4 py-2 text-sm bg-background/50 border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 font-medium transition-all"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
              />
            </div>
            
            <div className="relative">
              <select
                className="appearance-none bg-background/50 border border-border rounded-xl pl-4 pr-10 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all cursor-pointer hover:bg-muted/50"
                value={typeFilter}
                onChange={e => setTypeFilter(e.target.value)}
              >
                <option value="All">All Types</option>
                {distributions.byProjectType.map((pt: any) => (
                  <option key={pt.name} value={pt.name}>{pt.name}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground pointer-events-none" />
            </div>

            <div className="relative">
              <select
                className="appearance-none bg-background/50 border border-border rounded-xl pl-4 pr-10 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all cursor-pointer hover:bg-muted/50"
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
              >
                <option value="All">All Statuses</option>
                <option value="Pending">Pending</option>
                <option value="Completed">Completed</option>
                <option value="Pending for Info Required">Info Required</option>
                <option value="Pending for Approval">Pending Approval</option>
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground pointer-events-none" />
            </div>
          </div>
        </div>
        
        <div className="overflow-x-auto overflow-y-auto max-h-[600px] custom-scrollbar">
          <table className="w-full text-xs relative">
            <thead className="sticky top-0 z-10">
              <tr className="bg-muted border-b border-border shadow-sm">
                <th className="text-left font-medium text-muted-foreground py-3 px-4">INVOICE NO</th>
                <th className="text-left font-medium text-muted-foreground py-3 px-4">WORK ORDER</th>
                <th className="text-left font-medium text-muted-foreground py-3 px-4">LOCATION</th>
                <th className="text-left font-medium text-muted-foreground py-3 px-4">PACKAGE</th>
                <th className="text-left font-medium text-muted-foreground py-3 px-4">STATUS</th>
                <th className="text-left font-medium text-muted-foreground py-3 px-4">VENDOR</th>
                <th className="text-right font-medium text-muted-foreground py-3 px-4">SO AMOUNT</th>
                <th className="text-right font-medium text-muted-foreground py-3 px-4">INVOICE AMOUNT</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {filteredInvoices.length > 0 ? (
                filteredInvoices.map((inv: any, idx: number) => (
                  <tr key={idx} className="hover:bg-muted/20 transition-colors">
                    <td className="text-left font-mono font-medium text-primary py-2.5 px-4">{inv.invoiceNo}</td>
                    <td className="text-left font-mono text-muted-foreground py-2.5 px-4">{inv.workOrderNo}</td>
                    <td className="text-left text-foreground/80 py-2.5 px-4 max-w-[150px] truncate" title={inv.workLocation}>{inv.workLocation || '—'}</td>
                    <td className="text-left text-foreground/80 py-2.5 px-4 max-w-[150px] truncate" title={inv.packageName}>{inv.packageName || '—'}</td>
                    <td className="text-left py-2.5 px-4">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${(inv.statusDesc || '').toLowerCase() === 'completed' ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'}`}>
                        {inv.statusDesc || 'Pending'}
                      </span>
                    </td>
                    <td className="text-left text-foreground/80 py-2.5 px-4 max-w-[200px] truncate" title={inv.vendorName}>{inv.vendorName || '—'}</td>
                    <td className="text-right font-mono text-muted-foreground py-2.5 px-4">{inv.SOAmount ? `₹${Number(inv.SOAmount).toLocaleString('en-IN')}` : '—'}</td>
                    <td className="text-right font-mono font-semibold text-foreground py-2.5 px-4">{inv.invoiceAmount ? `₹${Number(inv.invoiceAmount).toLocaleString('en-IN')}` : '—'}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8} className="text-center text-muted-foreground py-8">
                    No invoices match your search filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
