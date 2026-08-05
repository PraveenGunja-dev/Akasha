import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import { 
  FileText, Activity, AlertCircle, CheckCircle2, TrendingUp, 
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

  const topVendors = [...(distributions.byVendor || [])].sort((a: any, b: any) => b.value - a.value).slice(0, 10);
  const vendorOption = {
    tooltip: { trigger: 'item', formatter: '{b}: ₹{c} L ({d}%)', backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#334155', textStyle: { color: '#f8fafc' } },
    legend: { type: 'scroll', orient: 'vertical', right: 0, top: 20, bottom: 20, textStyle: { color: '#94a3b8', fontSize: 10, width: 100, overflow: 'truncate' } },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['35%', '50%'],
        itemStyle: { borderRadius: 4, borderWidth: 0 },
        label: { show: false },
        data: topVendors.map((item: any) => ({
          name: item.name || 'Unknown',
          value: Number((item.value / 100000).toFixed(2))
        }))
      }
    ]
  };

  const statusOption = {
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
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: '{b}<br/><b>₹{c} L</b>', backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: '#334155', textStyle: { color: '#f8fafc' } },
    grid: { left: '2%', right: '12%', bottom: '2%', top: '2%', containLabel: true },
    xAxis: { type: 'value', show: false },
    yAxis: { 
      type: 'category', 
      data: topLocations.map((v: any) => v.name || 'Unknown'),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#94a3b8', width: 100, overflow: 'truncate', fontSize: 10, fontFamily: 'monospace' }
    },
    series: [
      {
        type: 'bar',
        data: topLocations.map((v: any) => Number((v.value / 100000).toFixed(2))),
        itemStyle: { color: '#10b981', borderRadius: [0, 4, 4, 0] },
        barWidth: '40%',
        label: { show: true, position: 'right', color: '#94a3b8', formatter: '₹{c} L', fontSize: 10, fontFamily: 'monospace' }
      }
    ]
  };

  const scatterDataRaw = (data.invoices || []).map((inv: any) => {
    const invDateStr = inv.invoiceDate;
    if (invDateStr && invDateStr.includes('/Date(')) {
      const match = /\/Date\((\d+)/.exec(invDateStr);
      if (match) {
        const ms = parseInt(match[1], 10);
        const date = new Date(ms);
        const dateStr = date.toISOString().split('T')[0];
        const amt = parseFloat(inv.invoiceAmount) || 0;
        const status = (inv.statusDesc || 'Pending').trim();
        return [dateStr, Number((amt / 100000).toFixed(2)), inv.invoiceNo, inv.vendorName || 'Unknown', status];
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
    tooltip: { 
      trigger: 'item',
      formatter: (params: any) => {
        const p = params.value;
        return `<div class="text-xs"><b>${p[0]}</b><br/>Status: <b>${p[4]}</b><br/>Vendor: ${p[3]}<br/>Invoice: ${p[2]}<br/>Amount: ₹${p[1]} L</div>`;
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

        {/* Top Vendors */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-bold text-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            Top 10 Vendors
          </h3>
          <div className="h-[250px] w-full">
            <ReactECharts option={vendorOption} style={{ height: '100%', width: '100%' }} />
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
