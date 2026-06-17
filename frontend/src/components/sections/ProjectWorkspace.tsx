import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import {
  ArrowLeft, Sparkles, Activity, Clock, Shield, Target,
  Package, TrendingUp, AlertTriangle, CheckCircle2,
  Calendar, BarChart3, Truck, Brain, ChevronRight, ChevronDown, ChevronUp, Loader2,
  Users, DollarSign, Layers, MapPin, Database, FileText,
  Box, Network, Zap, BrainCircuit, Flag, CalendarClock, Download
} from 'lucide-react';

/* ── Circular Gauge ── */
const Gauge = ({ value, label, color, size = 72, stroke = 5 }: any) => {
  const radius = (size - stroke) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (Math.min(value, 100) / 100) * circumference;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} className="transform -rotate-90">
        <circle className="progress-ring-track" cx={size/2} cy={size/2} r={radius} strokeWidth={stroke} />
        <circle className="progress-ring-fill" cx={size/2} cy={size/2} r={radius} strokeWidth={stroke}
          stroke={color} strokeDasharray={circumference} strokeDashoffset={offset} />
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle"
          className="transform rotate-90 origin-center"
          style={{ fontSize: '14px', fontWeight: 700, fontFamily: 'monospace', fill: 'rgba(255,255,255,0.9)' }}>
          {Math.round(value)}
        </text>
      </svg>
      <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground/50">{label}</span>
    </div>
  );
};

/* ── Hero Metric Card ── */
const HeroMetric = ({ label, value, unit, color, icon: Icon, onClick, active, hasBreakdown }: any) => (
  <div 
    onClick={onClick} 
    className={`bg-muted/20 hover:bg-muted/40 transition-all duration-300 border rounded-xl p-5 flex flex-col gap-3 group relative overflow-hidden shadow-sm hover:shadow-md ${
      active ? 'border-primary/60 ring-1 ring-primary/30 bg-primary/5' : 'border-border/50 hover:border-primary/20'
    } ${hasBreakdown ? 'cursor-pointer' : ''}`}
  >
    <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"></div>
    <div className="flex items-center justify-between">
      <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70 group-hover:text-muted-foreground transition-colors">{label}</span>
      <Icon className={`w-4 h-4 ${color} transition-transform duration-300 group-hover:scale-110`} />
    </div>
    <div className="flex items-baseline gap-1.5 relative z-10">
      <span className={`text-2xl font-light tracking-tight ${color}`}>{value}</span>
      {unit && <span className="text-xs text-muted-foreground/50">{unit}</span>}
    </div>
    {hasBreakdown && (
      <div className={`absolute bottom-1.5 right-2 text-[9px] font-medium transition-colors ${active ? 'text-primary' : 'text-muted-foreground/30 group-hover:text-muted-foreground/50'}`}>▾ details</div>
    )}
  </div>
);

/* ── Tab Button ── */
const TabBtn = ({ active, label, icon: Icon, onClick }: any) => (
  <button onClick={onClick}
    className={`relative flex items-center gap-2 px-5 py-3.5 text-[12px] font-bold uppercase tracking-wider transition-all ${
      active
        ? 'text-primary'
        : 'text-muted-foreground hover:text-foreground hover:bg-muted/30'
    }`}>
    <Icon className={`w-4 h-4 ${active ? 'text-primary' : 'text-muted-foreground/70'}`} />
    {label}
    {active && (
      <div className="absolute bottom-0 left-0 right-0 h-[3px] bg-primary rounded-t-full shadow-[0_-2px_10px_rgba(59,130,246,0.3)]" />
    )}
  </button>
);

/* ── Format helpers ── */
const fmtCost = (v: number | null | undefined): string => {
  if (v == null) return '—';
  const abs = Math.abs(v);
  if (abs >= 10000000) return `₹${(v / 10000000).toFixed(2)} Cr`;
  if (abs >= 100000) return `₹${(v / 100000).toFixed(2)} L`;
  if (abs >= 1000) return `₹${(v / 1000).toFixed(1)}K`;
  return `₹${v.toFixed(0)}`;
};

const fmtMW = (v: number | null | undefined): string => {
  if (v == null) return '—';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(v);
};

const fmtHrs = (v: number | null | undefined): string => {
  if (v == null) return '—';
  return `${Math.round(v)} hrs`;
};

const fmtDays = (v: number | null | undefined): string => {
  if (v == null) return '—';
  return `${Math.round(v)} days`;
};

export default function ProjectWorkspace({ projectId: propProjectId, onBack }: { projectId?: string, onBack?: () => void }) {
  const params = useParams();
  const projectId = propProjectId || params.projectId;
  const navigate = useNavigate();
  const [project, setProject] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [diagnostic, setDiagnostic] = useState<any>(null);
  const [diagLoading, setDiagLoading] = useState(false);
  const [sapFilter, setSapFilter] = useState<'all' | 'spv' | 'agel'>('all');
  const [inventoryFilter, setInventoryFilter] = useState<'ALL' | 'COMPANY' | 'PROJECT'>('ALL');
  const [expandedMaterial, setExpandedMaterial] = useState<string | null>(null);
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null);

  useEffect(() => {
    setActiveTab('overview');
  }, [projectId]);

  useEffect(() => {
    const fetchProject = async () => {
      try {
        const res = await fetch("/akasha/api/project-360");
        const json = await res.json();
        const found = json.find((p: any) => p.projectId === projectId);
        if (found) {
          setProject(found);
          // Auto-fetch AI diagnostic
          setDiagLoading(true);
          fetch("/akasha/api/project-diagnostic", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(found)
          })
          .then(res => res.json())
          .then(data => setDiagnostic(data || null))
          .catch(() => setDiagnostic(null))
          .finally(() => setDiagLoading(false));
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    const fetchDetail = async () => {
      try {
        const res = await fetch(`/akasha/api/project-360/${encodeURIComponent(projectId || '')}/detail`);
        if (res.ok) {
          const json = await res.json();
          setDetail(json);
        }
      } catch (err) {
        console.error('Detail fetch error:', err);
      } finally {
        setDetailLoading(false);
      }
    };

    fetchProject();
    fetchDetail();
  }, [projectId]);

  // ── SAP filtering (must be before early returns — Rules of Hooks) ──
  const sapRaw = detail?.sap;
  const filteredSap = useMemo(() => {
    if (!sapRaw) return null;
    if (sapFilter === 'all') return sapRaw;

    const targetCode = sapFilter === 'spv' ? project?.sapPlantCode : project?.agelCode;
    if (!targetCode) return sapRaw;

    const filteredPOs = (sapRaw.purchaseOrders || []).filter((po: any) => po.plantCode === targetCode);
    const filteredInTransit = (sapRaw.inTransit || []).filter((t: any) => t.plantCode === targetCode);
    const filteredInventory = (sapRaw.inventory || []).filter((inv: any) => inv.plantCode === targetCode);
    const filteredConsumption = (sapRaw.consumption || []).filter((c: any) => c.plantCode === targetCode);

    const vendorMap: Record<string, any> = {};
    for (const po of filteredPOs) {
      const vName = po.vendorName || 'Unknown';
      if (!vendorMap[vName]) {
        vendorMap[vName] = { vendorName: vName, vendorCode: po.vendorCode || '', totalOrderedQty: 0, totalBudgetINR: 0, poCount: 0, materials: new Set() };
      }
      vendorMap[vName].totalOrderedQty += po.orderedQty || 0;
      vendorMap[vName].totalBudgetINR += po.budgetINR || 0;
      vendorMap[vName].poCount += 1;
      if (po.materialCode) vendorMap[vName].materials.add(po.materialCode);
    }
    const filteredVendorBreakdown = Object.values(vendorMap)
      .map((v: any) => ({ ...v, materialCount: v.materials.size }))
      .sort((a: any, b: any) => b.totalOrderedQty - a.totalOrderedQty);

    const matMap: Record<string, any> = {};
    for (const po of filteredPOs) {
      const mt = po.materialType || 'Unknown';
      if (!matMap[mt]) matMap[mt] = { type: mt, totalQty: 0, count: 0 };
      matMap[mt].totalQty += po.orderedQty || 0;
      matMap[mt].count += 1;
    }
    const filteredMaterialBreakdown = Object.values(matMap).sort((a: any, b: any) => b.totalQty - a.totalQty);

    const filteredSummary = {
      totalPOs: filteredPOs.length,
      totalVendors: filteredVendorBreakdown.length,
      totalOrderedQty: filteredPOs.reduce((sum: number, po: any) => sum + (po.orderedQty || 0), 0),
      totalInTransitQty: filteredInTransit.reduce((sum: number, t: any) => sum + (t.inTransitQty || 0), 0),
      totalInventoryQty: filteredInventory.reduce((sum: number, inv: any) => sum + (inv.inventoryQty || 0), 0),
      totalInventoryValueINR: filteredInventory.reduce((sum: number, inv: any) => sum + (inv.inventoryValueINR || 0), 0),
      totalBudgetINR: filteredPOs.reduce((sum: number, po: any) => sum + (po.budgetINR || 0), 0),
      totalDeliveredINR: filteredPOs.reduce((sum: number, po: any) => sum + (po.deliveredINR || 0), 0),
      totalConsumedQty: filteredConsumption.reduce((sum: number, c: any) => sum - (c.quantity || 0), 0),
      totalExpenditureINR: filteredConsumption.reduce((sum: number, c: any) => sum - (c.amountINR || 0), 0),
    };

    return {
      ...sapRaw,
      purchaseOrders: filteredPOs,
      inTransit: filteredInTransit,
      inventory: filteredInventory,
      consumption: filteredConsumption,
      vendorBreakdown: filteredVendorBreakdown,
      materialBreakdown: filteredMaterialBreakdown,
      summary: filteredSummary,
    };
  }, [sapRaw, sapFilter, project?.sapPlantCode, project?.agelCode]);

  const unifiedMaterials = useMemo(() => {
    if (!filteredSap) return [];
    const matMap: Record<string, any> = {};

    const initMat = (code: string, desc: string) => {
      const cleanDesc = desc === 'nan' || !desc ? '—' : desc;
      if (!matMap[code]) {
        matMap[code] = {
          materialCode: code,
          materialDescription: cleanDesc,
          orderedQty: 0,
          consumedQty: 0,
          budgetINR: 0,
          deliveredINR: 0,
          consumedAmountINR: 0,
          inventoryQty: 0,
          inventoryValueINR: 0,
          inTransitQty: 0,
          pos: [],
          consumptions: [],
          inventories: [],
          inTransits: [],
          wbsElements: new Set<string>()
        };
      } else if (cleanDesc !== '—' && matMap[code].materialDescription === '—') {
        matMap[code].materialDescription = cleanDesc;
      }
    };

    // 1. POs
    (filteredSap.purchaseOrders || []).forEach((po: any) => {
      if (inventoryFilter === 'COMPANY' && po.storageLocation !== 'CS01') return;
      if (inventoryFilter === 'PROJECT' && po.storageLocation !== 'PS01') return;
      const code = po.materialCode;
      if (!code) return;
      initMat(code, po.materialName || po.materialType);
      const m = matMap[code];
      m.orderedQty += Number(po.orderedQty || 0);
      m.budgetINR += Number(po.budgetINR || 0);
      m.deliveredINR += Number(po.deliveredINR || 0);
      m.pos.push(po);
    });

    // 2. Consumption
    (filteredSap.consumption || []).forEach((c: any) => {
      const code = c.materialCode;
      if (!code) return;
      initMat(code, c.materialDescription || '—');
      const m = matMap[code];
      const qty = Number(c.quantity || 0);
      const amt = Number(c.amountINR || 0);
      m.consumedQty -= qty;
      m.consumedAmountINR -= amt;
      m.consumptions.push(c);
      if (c.wbsElement && c.wbsElement.trim() && c.wbsElement !== 'nan') m.wbsElements.add(c.wbsElement);
      if (c.blockPlotName && c.blockPlotName.trim() && c.blockPlotName !== 'nan') m.wbsElements.add(c.blockPlotName);
    });

    // 3. Inventory
    (filteredSap.inventory || []).forEach((inv: any) => {
      if (inventoryFilter === 'COMPANY' && inv.storageLocation !== 'CS01') return;
      if (inventoryFilter === 'PROJECT' && inv.storageLocation !== 'PS01') return;
      const code = inv.materialCode;
      if (!code) return;
      initMat(code, '—');
      const m = matMap[code];
      m.inventoryQty += Number(inv.inventoryQty || 0);
      m.inventoryValueINR += Number(inv.inventoryValueINR || 0);
      m.inventories.push(inv);
      if (inv.wbsElement && inv.wbsElement.trim() && inv.wbsElement !== 'nan') m.wbsElements.add(inv.wbsElement);
    });

    // 4. InTransit
    (filteredSap.inTransit || []).forEach((t: any) => {
      const code = t.materialCode;
      if (!code) return;
      initMat(code, '—');
      const m = matMap[code];
      m.inTransitQty += Number(t.inTransitQty || 0);
      m.inTransits.push(t);
      if (t.wbsElement && t.wbsElement.trim() && t.wbsElement !== 'nan') m.wbsElements.add(t.wbsElement);
    });

    const result = Object.values(matMap).map((m: any) => {
      m.remainingQty = m.orderedQty - m.consumedQty;
      m.remainingBalanceINR = m.budgetINR - m.deliveredINR;
      m.wbsList = Array.from(m.wbsElements).filter(Boolean);
      return m;
    });

    return result.sort((a: any, b: any) => b.orderedQty - a.orderedQty);
  }, [filteredSap, inventoryFilter]);

  if (loading) {
    return (
      <div className="flex items-center justify-center w-full h-full min-h-[500px] bg-background">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
          <span className="text-sm text-muted-foreground/60 font-medium tracking-wider uppercase">Loading Intelligence...</span>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex items-center justify-center w-full h-full min-h-[500px] bg-background">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-amber-500/50 mx-auto mb-4" />
          <p className="text-muted-foreground">Project not found.</p>
          <button onClick={() => navigate('/dashboard')} className="mt-4 text-primary text-sm hover:underline">
            ← Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const p = project;
  const progressPct = p.progress < 1 ? p.progress * 100 : p.progress;
  const tier = p.statusTier || p.health;
  const healthColor = tier === 'Critical' ? 'text-red-400' : (tier === 'High Risk' || tier === 'Watchlist') ? 'text-amber-400' : 'text-emerald-400';
  const dotClass = tier === 'Critical' ? 'status-dot-critical' : (tier === 'High Risk' || tier === 'Watchlist') ? 'status-dot-warning' : 'status-dot-healthy';

  // Activity completion chart
  const activityOption = {
    tooltip: { trigger: 'item', backgroundColor: '#fff', borderColor: '#e2e8f0', textStyle: { color: '#0f172a', fontSize: 12 } },
    series: [{
      type: 'pie', radius: ['55%', '78%'], avoidLabelOverlap: false, center: ['50%', '50%'],
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 3 },
      label: { show: false },
      data: [
        { value: p.completedActivities, name: 'Completed', itemStyle: { color: '#10B981' } },
        { value: p.inProgressActivities, name: 'In Progress', itemStyle: { color: '#3B82F6' } },
        { value: p.notStartedActivities, name: 'Not Started', itemStyle: { color: '#e2e8f0' } },
      ]
    }]
  };

  // Supply chain pipeline
  const supplyData = [
    { name: 'Ordered Qty', value: p.orderedQty, color: '#3B82F6' },
    { name: 'In Transit Qty', value: p.inTransitQty, color: '#F59E0B' },
    { name: 'Inventory Qty', value: p.inventoryQty, color: '#10B981' },
  ];
  const supplyOption = {
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e2e8f0', textStyle: { color: '#0f172a' } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
    xAxis: { type: 'category', data: supplyData.map(s => s.name), axisLine: { lineStyle: { color: '#e2e8f0' } }, axisLabel: { color: '#64748b', fontSize: 10 } },
    yAxis: { type: 'value', name: 'Units', axisLine: { show: false }, axisLabel: { color: '#64748b', fontSize: 10 }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
    series: [{ type: 'bar', data: supplyData.map(s => ({ value: s.value, itemStyle: { color: s.color, borderRadius: [6, 6, 0, 0] } })), barWidth: '40%' }]
  };

  // SAP vendor chart and material chart are defined after sap filtering below


  // P6 detail data
  const p6 = detail?.p6;
  const mapping = detail?.mapping;
  const sap = filteredSap;
  const tc = detail?.tc;

  // SAP vendor chart (reactive to toggle filter)
  const vendorChartOption = sap?.vendorBreakdown?.length > 0 ? {
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e2e8f0', textStyle: { color: '#0f172a' } },
    legend: { data: ['Ordered Qty', 'Net Value (INR)'], bottom: 0, textStyle: { fontSize: 10, color: '#64748b' } },
    grid: { left: '3%', right: '8%', bottom: '15%', top: '8%', containLabel: true },
    xAxis: {
      type: 'category',
      data: (sap.vendorBreakdown.slice(0, 8)).map((v: any) => v.vendorName?.substring(0, 22) || 'Unknown'),
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#64748b', fontSize: 10, rotate: 15 }
    },
    yAxis: [
      { type: 'value', name: 'Units', axisLine: { show: false }, axisLabel: { color: '#64748b', fontSize: 10 }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
      { type: 'value', name: 'Value', position: 'right', axisLine: { show: false }, axisLabel: { color: '#64748b', fontSize: 10, formatter: (v: number) => `₹${(v/100000).toFixed(0)}L` }, splitLine: { show: false } }
    ],
    series: [
      {
        name: 'Ordered Qty',
        type: 'bar',
        data: (sap.vendorBreakdown.slice(0, 8)).map((v: any) => v.totalOrderedQty),
        itemStyle: { color: '#3B82F6', borderRadius: [6, 6, 0, 0] },
        barWidth: '40%'
      },
      {
        name: 'Net Value (INR)',
        type: 'line',
        yAxisIndex: 1,
        data: (sap.vendorBreakdown.slice(0, 8)).map((v: any) => v.totalBudgetINR),
        itemStyle: { color: '#10B981' },
        lineStyle: { width: 3 },
        symbol: 'circle',
        symbolSize: 8
      }
    ]
  } : null;

  // Material type pie chart (reactive to toggle filter)
  const materialTypeOption = sap?.materialBreakdown?.length > 0 ? {
    tooltip: { trigger: 'item', backgroundColor: '#fff', borderColor: '#e2e8f0', textStyle: { color: '#0f172a', fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['45%', '72%'], center: ['50%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      data: sap.materialBreakdown.map((m: any, i: number) => ({
        value: m.totalQty,
        name: m.type,
        itemStyle: { color: ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EF4444', '#EC4899'][i % 6] }
      }))
    }]
  } : null;

  const downloadSAPReport = () => {
    if (!sap) return;
    
    const rows = [];
    rows.push(['--- SAP Intelligence Report ---']);
    rows.push(['Project:', p.projectName]);
    rows.push(['Capacity (MW):', mapping?.capacityMW || '']);
    rows.push(['']);
    
    rows.push(['--- Vendor Summary ---']);
    rows.push(['Vendor Name', 'Vendor Code', 'POs', 'Materials', 'Ordered Qty', 'Budget INR']);
    sap.vendorBreakdown?.forEach((v: any) => {
      rows.push([
        `"${v.vendorName?.replace(/"/g, '""') || ''}"`, 
        v.vendorCode || '', 
        v.poCount, 
        v.materialCount, 
        v.totalQty, 
        v.totalValue
      ]);
    });
    rows.push(['']);
    
    // Purchase Orders
    rows.push(['--- Purchase Orders (ME2M) ---']);
    rows.push(['PO Number', 'Vendor Name', 'Material Code', 'Material Name', 'Material Type', 'Ordered Qty', 'Budget INR', 'Plant Code']);
    sap.purchaseOrders?.forEach((po: any) => {
      rows.push([
        po.poNumber, 
        `"${po.vendorName?.replace(/"/g, '""') || ''}"`, 
        po.materialCode, 
        `"${po.materialName?.replace(/"/g, '""') || ''}"`, 
        `"${po.materialType || ''}"`, 
        po.orderedQty,
        po.budgetINR, 
        po.plantCode
      ]);
    });
    rows.push(['']);
    
    // In Transit
    if (sap.inTransit?.length > 0) {
      rows.push(['--- In-Transit Shipments (MIGO) ---']);
      rows.push(['PO Number', 'Vendor Name', 'Material Code', 'In Transit Qty']);
      sap.inTransit.forEach((t: any) => {
        rows.push([
          t.poNumber, 
          `"${t.vendorName?.replace(/"/g, '""') || ''}"`, 
          t.materialCode, 
          t.inTransitQty
        ]);
      });
      rows.push(['']);
    }

    // Inventory
    if (sap.inventory?.length > 0) {
      rows.push(['--- Site Inventory (MB52) ---']);
      rows.push(['Material Code', 'Storage Location', 'Inventory Qty', 'Inventory Value']);
      sap.inventory.forEach((inv: any) => {
        rows.push([
          inv.materialCode, 
          `"${inv.storageLocation || ''}"`, 
          inv.inventoryQty,
          inv.inventoryValueINR
        ]);
      });
    }

    const csvContent = "data:text/csv;charset=utf-8," + rows.map(e => e.join(",")).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `SAP_Intelligence_${p.projectId}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="w-full min-h-full bg-background text-foreground pb-12">
      {/* ── Top Bar ── */}
      <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-xl border-b border-border px-6 py-3">
        <div className="max-w-[1600px] mx-auto flex items-center gap-4">
          <button onClick={() => onBack ? onBack() : navigate('/dashboard')}
            className="flex items-center gap-2 text-sm text-muted-foreground/70 hover:text-foreground transition-colors group">
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
            Back to Portfolio
          </button>
          <div className="h-5 w-px bg-muted/50"></div>
          <div className="flex items-center gap-2">
            <div className={dotClass}></div>
            <span className="text-sm font-semibold text-foreground truncate max-w-[400px]">{p.projectName}</span>
          </div>
          <span className="text-[10px] font-mono text-muted-foreground/40 ml-auto">{p.projectId}</span>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">
        {/* ── Hero Section ── */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <HeroMetric label="Progress" value={`${Math.round(progressPct)}%`} icon={Activity} color={healthColor} />
          <HeroMetric label="Health Score" value={p.healthScore} unit="/100" icon={Shield} color={p.healthScore > 70 ? 'text-emerald-400' : p.healthScore > 40 ? 'text-amber-400' : 'text-red-400'} />
          <HeroMetric label="SPI" value={p.spi.toFixed(2)} icon={TrendingUp} color={p.spi >= 0.95 ? 'text-emerald-400' : 'text-red-400'} />
          <HeroMetric label="Schedule Variance" value={`${p.scheduleVariance > 0 ? '+' : ''}${p.scheduleVariance}`} unit="days" icon={Clock} color={p.scheduleVariance < -10 ? 'text-red-400' : 'text-foreground/80'} />
          <HeroMetric label="Forecast COD" value={p.forecastMonth} icon={Calendar} color="text-primary" />
          <HeroMetric label="Risk Score" value={p.riskScore} unit="/100" icon={AlertTriangle} color={p.riskScore > 50 ? 'text-red-400' : p.riskScore > 25 ? 'text-amber-400' : 'text-emerald-400'} />
        </div>

        {/* ── AI Project Summary ── */}
        <div className="intelligence-card p-6 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-72 h-72 bg-primary/[0.03] blur-[100px] rounded-full pointer-events-none"></div>
          
          <div className="flex items-start gap-4 mb-4 relative z-10">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary/20 to-purple-600/20 flex items-center justify-center shrink-0 border border-primary/10">
              <Brain className="w-5 h-5 text-primary/80" />
            </div>
            <div className="flex-1">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                AI Project Intelligence
                <span className="text-[9px] bg-primary/10 text-primary px-2 py-0.5 rounded-full font-bold uppercase tracking-wider border border-primary/20">
                  Live Analysis
                </span>
              </h3>
              <p className="text-[10px] text-muted-foreground/50 mt-0.5">Powered by AKASHA AI Engine</p>
            </div>
          </div>

          <div className="relative z-10 grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Left: AI Diagnostic */}
            <div className="lg:col-span-8">
              <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50 mb-3">Diagnostic Analysis</h4>
              <div className="border-l-2 border-primary/30 pl-4 min-h-[80px]">
                {diagLoading ? (
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin"></div>
                    <span className="text-sm text-muted-foreground/60 animate-pulse">Analyzing project intelligence...</span>
                  </div>
                ) : diagnostic ? (
                  <div className="columns-1 md:columns-2 gap-8 prose prose-sm max-w-none text-foreground/80">
                    {diagnostic.executiveSummary && (
                      <div className="break-inside-avoid mb-6">
                        <h4 className="text-sm font-bold text-foreground mb-1">Executive Summary</h4>
                        <p>{diagnostic.executiveSummary}</p>
                      </div>
                    )}
                    {diagnostic.keyFindings && diagnostic.keyFindings.length > 0 && (
                      <div className="break-inside-avoid mb-6">
                        <h4 className="text-sm font-bold text-foreground mb-1">Key Findings</h4>
                        <ul className="list-disc pl-4 space-y-1">
                          {diagnostic.keyFindings.map((f: string, i: number) => <li key={i}>{f}</li>)}
                        </ul>
                      </div>
                    )}
                    {diagnostic.riskAssessment && (
                      <div className="break-inside-avoid mb-6">
                        <h4 className="text-sm font-bold text-foreground mb-1">Risk Assessment</h4>
                        <p>{diagnostic.riskAssessment}</p>
                      </div>
                    )}
                    {diagnostic.rootCauseAnalysis && (
                      <div className="break-inside-avoid mb-6">
                        <h4 className="text-sm font-bold text-foreground mb-1">Root Cause Analysis</h4>
                        <p>{diagnostic.rootCauseAnalysis}</p>
                      </div>
                    )}
                    {diagnostic.recommendedActions && diagnostic.recommendedActions.length > 0 && (
                      <div className="break-inside-avoid mb-6">
                        <h4 className="text-sm font-bold text-foreground mb-1">Recommended Actions</h4>
                        <ul className="list-disc pl-4 space-y-1">
                          {diagnostic.recommendedActions.map((f: string, i: number) => <li key={i}>{f}</li>)}
                        </ul>
                      </div>
                    )}
                    {diagnostic.expectedOutcome && (
                      <div className="break-inside-avoid mb-6">
                        <h4 className="text-sm font-bold text-foreground mb-1">Expected Outcome</h4>
                        <p>{diagnostic.expectedOutcome}</p>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-foreground/80 leading-relaxed">Diagnostic unavailable.</p>
                )}
              </div>
            </div>

            {/* Right: Key Metrics + Action */}
            <div className="space-y-4 lg:col-span-4">
              <div>
                <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50 mb-2">Key Issue</h4>
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-lg ${
                    p.keyIssue === 'On Track' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'
                  }`}>
                    {p.keyIssue === 'On Track' ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                    {p.keyIssue}
                  </span>
                </div>
              </div>
              <div>
                <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50 mb-2">Recommended Action</h4>
                <p className="text-sm text-primary/80 leading-relaxed bg-primary/[0.04] border border-primary/10 rounded-lg px-4 py-3">
                  {p.recommendedAction}
                </p>
              </div>

              <div className="mt-6 pt-4 border-t border-border">
                <button
                  onClick={() => window.dispatchEvent(new CustomEvent('open-simulation-lab', { detail: { projectId } }))}
                  className="w-full flex items-center justify-center gap-2 bg-primary/20 hover:bg-primary/30 text-primary border border-primary/30 transition-colors rounded-lg px-4 py-2.5 text-sm font-semibold"
                >
                  <BrainCircuit className="w-4 h-4" />
                  Run AI Simulation
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ── Tab Navigation ── */}
        <div className="flex items-center gap-2 border-b border-border bg-card/50 backdrop-blur-sm px-4 overflow-x-auto scrollbar-hide">
          <TabBtn active={activeTab === 'overview'} label="Overview" icon={BarChart3} onClick={() => setActiveTab('overview')} />
          <TabBtn active={activeTab === 'schedule'} label="Schedule" icon={Calendar} onClick={() => setActiveTab('schedule')} />
          <TabBtn active={activeTab === 'supply'} label="Supply Chain" icon={Truck} onClick={() => setActiveTab('supply')} />
          <TabBtn active={activeTab === 'risk'} label="Risk" icon={Shield} onClick={() => setActiveTab('risk')} />
          <TabBtn active={activeTab === 'sap'} label="SAP Intelligence" icon={Database} onClick={() => setActiveTab('sap')} />
          <TabBtn active={activeTab === 'p6'} label="P6 Deep Dive" icon={Layers} onClick={() => setActiveTab('p6')} />
          <TabBtn active={activeTab === 'transmission'} label="Transmission" icon={Network} onClick={() => setActiveTab('transmission')} />
        </div>

        {/* ── Tab Content ── */}
        <div className="animate-in fade-in duration-300">

          {/* ════════ OVERVIEW TAB ════════ */}
          {activeTab === 'overview' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Activity Breakdown */}
              <div className="intelligence-card p-6 flex flex-col">
                <h3 className="text-sm font-semibold text-foreground mb-6 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-primary" />
                  Activity Completion
                </h3>
                <div className="flex-1 flex flex-col md:flex-row items-center gap-8 justify-center">
                  <div className="w-[180px] h-[180px] relative">
                    <ReactECharts option={activityOption} style={{ height: '100%', width: '100%' }} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                      <span className="text-2xl font-light text-foreground">{Math.round((p.completedActivities / (p.activityCount || 1)) * 100)}%</span>
                      <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Done</span>
                    </div>
                  </div>
                  <div className="flex-1 w-full max-w-[240px] space-y-4">
                    <div className="flex items-center justify-between text-sm group">
                      <div className="flex items-center gap-3">
                        <div className="w-3 h-3 rounded-sm bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]"></div> 
                        <span className="text-foreground/80 font-medium group-hover:text-foreground transition-colors">Completed</span>
                      </div>
                      <span className="font-mono font-bold text-foreground">{p.completedActivities}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm group">
                      <div className="flex items-center gap-3">
                        <div className="w-3 h-3 rounded-sm bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.4)]"></div> 
                        <span className="text-foreground/80 font-medium group-hover:text-foreground transition-colors">In Progress</span>
                      </div>
                      <span className="font-mono font-bold text-foreground">{p.inProgressActivities}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm group">
                      <div className="flex items-center gap-3">
                        <div className="w-3 h-3 rounded-sm bg-slate-200"></div> 
                        <span className="text-foreground/80 font-medium group-hover:text-foreground transition-colors">Not Started</span>
                      </div>
                      <span className="font-mono font-bold text-foreground">{p.notStartedActivities}</span>
                    </div>
                    <div className="border-t border-border mt-4 pt-4 flex items-center justify-between text-sm">
                      <span className="text-muted-foreground font-bold uppercase tracking-wider text-[11px]">Total Activities</span>
                      <span className="font-mono font-bold text-lg text-primary">{p.activityCount}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Project Details */}
              <div className="intelligence-card p-6 flex flex-col">
                <h3 className="text-sm font-semibold text-foreground mb-6 flex items-center gap-2">
                  <Target className="w-4 h-4 text-primary" />
                  Project Details
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 flex-1 content-start">
                  {[
                    ['Status', p.status],
                    ['Plant Code', p.sapPlantCode || '—'],
                    ['SPV Code', p.agelCode || '—'],
                    ['Capacity', p.capacityMW ? `${p.capacityMW} MW` : '—'],
                    ['Location', p6?.locationName || '—'],
                    ['Start Date', p.startDate || '—'],
                    ['Forecast Finish', p.forecastFinish],
                    ['Baseline Finish', p.baselineFinishDate || '—'],
                    ['Planned Duration', p.plannedDuration ? `${Math.round(p.plannedDuration)} hrs` : '—'],
                    ['Actual Duration', p.actualDuration ? `${Math.round(p.actualDuration)} hrs` : '—'],
                    ['Parent EPS', p.parentEPS || '—'],
                  ].map(([label, val]) => (
                    <div key={label} className="bg-muted/30 border border-border/50 rounded-lg p-3 hover:bg-muted/50 transition-colors">
                      <span className="block text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1">{label}</span>
                      <span className="block text-sm font-semibold text-foreground truncate" title={val as string}>{val}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ════════ SCHEDULE TAB ════════ */}
          {activeTab === 'schedule' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Key Indices */}
              <div className="lg:col-span-4 flex flex-col gap-6">
                <div className="intelligence-card p-6 flex-1 flex flex-col justify-center items-center relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-emerald-400 to-emerald-600" />
                  <Gauge value={p.spi * 100} label="SPI" color={p.spi >= 0.95 ? '#10B981' : '#EF4444'} size={120} stroke={8} />
                  <div className="mt-4 text-center">
                    <span className="block text-sm font-bold text-foreground">Schedule Performance Index</span>
                    <span className="block text-[11px] text-muted-foreground mt-1">
                      {p.spi >= 1.0 ? 'Ahead of schedule' : p.spi >= 0.95 ? 'Marginally on track' : 'Behind schedule'}
                    </span>
                  </div>
                </div>
                <div className="intelligence-card p-6 flex-1 flex flex-col justify-center items-center relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-400 to-blue-600" />
                  <Gauge value={p.cpi * 100} label="CPI" color={p.cpi >= 0.95 ? '#3B82F6' : '#F59E0B'} size={120} stroke={8} />
                  <div className="mt-4 text-center">
                    <span className="block text-sm font-bold text-foreground">Cost Performance Index</span>
                    <span className="block text-[11px] text-muted-foreground mt-1">
                      {p.cpi >= 1.0 ? 'Under budget' : p.cpi >= 0.95 ? 'On budget' : 'Over budget'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Right Column: Timeline & Variance */}
              <div className="lg:col-span-8 flex flex-col gap-6">
                <div className="intelligence-card p-6">
                  <h4 className="text-xs font-bold uppercase tracking-widest text-foreground mb-6 flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-primary" /> Schedule Timeline
                  </h4>
                  
                  <div className="relative pl-4 border-l-2 border-border space-y-6">
                    {[
                      { icon: Flag, color: 'text-emerald-500', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', label: 'Project Start', value: p.startDate || '—', desc: 'Official commencement' },
                      { icon: Activity, color: 'text-blue-500', bg: 'bg-blue-500/10', border: 'border-blue-500/20', label: 'Data Date', value: p6?.dataDate || '—', desc: 'Latest schedule update' },
                      { icon: Target, color: 'text-amber-500', bg: 'bg-amber-500/10', border: 'border-amber-500/20', label: 'Baseline Finish', value: p.baselineFinishDate || '—', desc: 'Original target' },
                      { icon: CalendarClock, color: 'text-red-500', bg: 'bg-red-500/10', border: 'border-red-500/20', label: 'Forecast Finish', value: p.forecastFinish, desc: 'Current projection' },
                    ].map((item, idx) => (
                      <div key={idx} className="relative">
                        <div className={`absolute -left-[23px] top-1 w-3 h-3 rounded-full border-2 border-background ${item.bg.replace('/10', '')}`} />
                        <div className={`p-4 rounded-xl border ${item.border} ${item.bg} flex items-center justify-between`}>
                          <div className="flex items-center gap-4">
                            <item.icon className={`w-5 h-5 ${item.color}`} />
                            <div>
                              <span className="block font-semibold text-foreground text-sm">{item.label}</span>
                              <span className="block text-xs text-muted-foreground mt-0.5">{item.desc}</span>
                            </div>
                          </div>
                          <span className="font-mono font-bold text-foreground bg-background/50 px-3 py-1 rounded-md">{item.value}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="intelligence-card p-4 flex items-center justify-between bg-muted/20">
                    <div>
                      <span className="block text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Schedule Variance</span>
                      <span className={`block text-xl font-bold mt-1 ${p.scheduleVariance < 0 ? 'text-red-500' : 'text-emerald-500'}`}>
                        {p.scheduleVariance} days
                      </span>
                    </div>
                    <AlertTriangle className={`w-8 h-8 opacity-20 ${p.scheduleVariance < 0 ? 'text-red-500' : 'text-emerald-500'}`} />
                  </div>
                  <div className="intelligence-card p-4 flex items-center justify-between bg-muted/20">
                    <div>
                      <span className="block text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Must Finish By</span>
                      <span className="block text-lg font-mono font-bold text-foreground mt-1">{p6?.mustFinishByDate || 'Not Set'}</span>
                    </div>
                    <Target className="w-8 h-8 text-primary opacity-20" />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ════════ SUPPLY CHAIN TAB ════════ */}
          {activeTab === 'supply' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Visual Pipeline */}
              <div className="lg:col-span-8 flex flex-col gap-6">
                <div className="intelligence-card p-6 flex flex-col">
                  <h3 className="text-sm font-semibold text-foreground mb-6 flex items-center gap-2">
                    <Package className="w-4 h-4 text-primary" /> Supply Chain Pipeline
                  </h3>
                  <div className="h-[280px] w-full">
                    <ReactECharts option={supplyOption} style={{ height: '100%', width: '100%' }} />
                  </div>
                </div>
                
                {/* Metrics Grid */}
                <div className="grid grid-cols-3 gap-4">
                  {[
                    { label: 'Ordered Qty', value: p.orderedQty ? Math.round(p.orderedQty).toLocaleString() : '0', color: 'text-blue-500', bg: 'bg-blue-500/10' },
                    { label: 'In Transit Qty', value: p.inTransitQty ? Math.round(p.inTransitQty).toLocaleString() : '0', color: 'text-amber-500', bg: 'bg-amber-500/10' },
                    { label: 'Inventory Qty', value: p.inventoryQty ? Math.round(p.inventoryQty).toLocaleString() : '0', color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
                  ].map(m => (
                    <div key={m.label} className="intelligence-card p-4 flex flex-col items-center text-center justify-center">
                      <div className={`w-10 h-10 rounded-full ${m.bg} flex items-center justify-center mb-3`}>
                        <Truck className={`w-5 h-5 ${m.color}`} />
                      </div>
                      <span className="block text-2xl font-bold text-foreground">{m.value}</span>
                      <span className="block text-[11px] font-bold uppercase tracking-wider text-muted-foreground mt-1">{m.label}</span>
                    </div>
                  ))}
                </div>
              </div>
              
              {/* Right Column: Material Status */}
              <div className="lg:col-span-4 flex flex-col gap-6">
                <div className="intelligence-card p-6 flex-1 flex flex-col">
                  <h3 className="text-sm font-semibold text-foreground mb-6 flex items-center gap-2">
                    <Database className="w-4 h-4 text-primary" /> Material Availability
                  </h3>
                  
                  <div className="flex flex-col items-center justify-center flex-1 py-8">
                    <div className="relative w-40 h-40">
                      <svg className="w-full h-full transform -rotate-90">
                        <circle cx="80" cy="80" r="70" stroke="currentColor" strokeWidth="12" fill="transparent" className="text-muted/30" />
                        <circle cx="80" cy="80" r="70" stroke="currentColor" strokeWidth="12" fill="transparent"
                          strokeDasharray={440} strokeDashoffset={440 - (p.materialAvailability / 100) * 440}
                          className={p.materialAvailability >= 80 ? 'text-emerald-500' : p.materialAvailability >= 50 ? 'text-amber-500' : 'text-red-500'} />
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-3xl font-bold text-foreground">{Math.round(p.materialAvailability)}%</span>
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mt-1">Ready</span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-auto space-y-3">
                    <div className="flex items-center justify-between p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                      <span className="text-sm font-medium text-emerald-700 dark:text-emerald-400">Inventory</span>
                      <span className="font-bold text-emerald-700 dark:text-emerald-400">{p.inventoryQty?.toLocaleString()}</span>
                    </div>
                    <div className="flex items-center justify-between p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                      <span className="text-sm font-medium text-red-700 dark:text-red-400">Shortage</span>
                      <span className="font-bold text-red-700 dark:text-red-400">{Math.max(0, p.orderedQty - p.inventoryQty).toLocaleString()}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ════════ RISK TAB ════════ */}
          {activeTab === 'risk' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 intelligence-card p-8 flex flex-col items-center justify-center text-center">
                <div className="w-full h-2 bg-gradient-to-r from-red-500 to-amber-500 absolute top-0 left-0" />
                <AlertTriangle className={`w-16 h-16 mb-4 ${p.riskScore > 50 ? 'text-red-500' : p.riskScore > 25 ? 'text-amber-500' : 'text-emerald-500'}`} />
                <span className="text-6xl font-bold tracking-tight text-foreground">{p.riskScore}</span>
                <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground mt-2">Overall Risk Score</span>
                
                <div className={`mt-6 px-4 py-2 rounded-full border ${p.riskScore > 50 ? 'bg-red-500/10 border-red-500/20 text-red-600 dark:text-red-400' : p.riskScore > 25 ? 'bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400' : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400'}`}>
                  <span className="text-sm font-semibold">
                    {p.riskScore > 50 ? 'Immediate Intervention Required' : p.riskScore > 25 ? 'Close Monitoring Needed' : 'Standard Monitoring'}
                  </span>
                </div>
              </div>

              <div className="lg:col-span-8 intelligence-card p-6">
                <h3 className="text-sm font-semibold text-foreground mb-6 flex items-center gap-2">
                  <Shield className="w-4 h-4 text-primary" /> Risk Breakdown
                </h3>
                <div className="space-y-6">
                  {[
                    { factor: 'Schedule Delay', score: Math.min(40, Math.abs(p.scheduleVariance < 0 ? p.scheduleVariance : 0)), max: 40, icon: CalendarClock },
                    { factor: 'Cost Overrun (SPI/CPI)', score: Math.round(p.spi < 1 ? (1 - p.spi) * 100 : 0), max: 100, icon: Target },
                    { factor: 'Material Availability', score: Math.round(p.materialAvailability < 100 ? (100 - p.materialAvailability) * 0.5 : 0), max: 50, icon: Package },
                  ].map(rf => (
                    <div key={rf.factor} className="bg-muted/20 p-4 rounded-xl border border-border/50 hover:bg-muted/40 transition-colors">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <rf.icon className="w-4 h-4 text-muted-foreground" />
                          <span className="font-semibold text-foreground text-sm">{rf.factor}</span>
                        </div>
                        <span className="text-sm font-bold text-foreground">
                          {rf.score} <span className="text-muted-foreground font-normal">/ {rf.max} impact</span>
                        </span>
                      </div>
                      <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                        <div className="h-full rounded-full transition-all duration-1000"
                          style={{ width: `${(rf.score / rf.max) * 100}%`, background: rf.score > rf.max * 0.6 ? '#EF4444' : rf.score > rf.max * 0.3 ? '#F59E0B' : '#10B981' }}></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ════════ SAP INTELLIGENCE TAB (NEW) ════════ */}
          {activeTab === 'sap' && (
            <div className="space-y-6">
              {detailLoading ? (
                <div className="flex items-center justify-center h-[300px]">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-5 h-5 text-primary animate-spin" />
                    <span className="text-sm text-muted-foreground/60">Loading SAP data...</span>
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  {/* SAP Summary Header */}
                  <div className="flex items-center justify-between mb-2">
                    <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                      <Database className="w-5 h-5 text-primary/70" /> SAP Intelligence
                    </h2>
                    <div className="flex items-center gap-3">
                      <div className="flex items-center bg-muted/40 border border-border rounded-lg p-0.5">
                        {[
                          { key: 'all' as const, label: 'All', disabled: false },
                          { 
                            key: 'spv' as const, 
                            label: `SPV (${project?.sapPlantCode || '—'})`, 
                            disabled: project?.sapPlantCode ? ![(sapRaw?.purchaseOrders || []), (sapRaw?.inventory || []), (sapRaw?.consumption || [])].some(arr => arr.some((x: any) => x.plantCode === project.sapPlantCode)) : true 
                          },
                          { 
                            key: 'agel' as const, 
                            label: `AGEL (${project?.agelCode || '—'})`, 
                            disabled: project?.agelCode ? ![(sapRaw?.purchaseOrders || []), (sapRaw?.inventory || []), (sapRaw?.consumption || [])].some(arr => arr.some((x: any) => x.plantCode === project.agelCode)) : true 
                          },
                        ].map(opt => (
                          <button
                            key={opt.key}
                            onClick={() => !opt.disabled && setSapFilter(opt.key)}
                            disabled={opt.disabled}
                            title={opt.disabled ? 'No procurement data found for this plant code' : ''}
                            className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-md transition-all ${
                              opt.disabled 
                                ? 'opacity-40 cursor-not-allowed border border-dashed border-muted-foreground/30 text-muted-foreground'
                                : sapFilter === opt.key
                                  ? 'bg-primary text-primary-foreground shadow-sm'
                                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
                            }`}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                      <button
                        onClick={downloadSAPReport}
                        className="flex items-center gap-2 bg-primary/20 hover:bg-primary/30 text-primary border border-primary/30 transition-colors rounded-lg px-4 py-2 text-sm font-semibold"
                      >
                        <Download className="w-4 h-4" />
                        Export SAP Report
                      </button>
                    </div>
                  </div>

                  {!sap || sap.summary.totalPOs === 0 ? (
                    <div className="intelligence-card p-12 flex flex-col items-center justify-center text-center">
                      <Database className="w-10 h-10 text-muted-foreground/20 mb-3" />
                      <p className="text-muted-foreground/60 text-sm">No SAP procurement data found for this plant code.</p>
                      <p className="text-muted-foreground/40 text-xs mt-1">Plant code: {sapFilter === 'spv' ? project?.sapPlantCode : sapFilter === 'agel' ? project?.agelCode : '—'}</p>
                    </div>
                  ) : (
                    <>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                    <HeroMetric label="Total POs" value={sap.summary.totalPOs} icon={FileText} color="text-blue-500 dark:text-blue-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'pos' ? null : 'pos')} active={expandedMetric === 'pos'} />
                    <HeroMetric label="Vendors" value={sap.summary.totalVendors} icon={Users} color="text-purple-500 dark:text-purple-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'vendors' ? null : 'vendors')} active={expandedMetric === 'vendors'} />
                    <HeroMetric label="Materials" value={unifiedMaterials.length} icon={Layers} color="text-indigo-500 dark:text-indigo-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'materials' ? null : 'materials')} active={expandedMetric === 'materials'} />
                    <HeroMetric label="PO Volume" value={fmtMW(sap.summary.totalOrderedQty)} unit="" icon={Package} color="text-blue-500 dark:text-blue-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'volume' ? null : 'volume')} active={expandedMetric === 'volume'} />
                    <HeroMetric label="Inventory" value={fmtMW(sap.summary.totalInventoryQty)} unit="" icon={Box} color="text-emerald-500 dark:text-emerald-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'inventory' ? null : 'inventory')} active={expandedMetric === 'inventory'} />
                    
                    <HeroMetric label="Total Budget" value={fmtCost(sap.summary.totalBudgetINR)} icon={DollarSign} color="text-pink-500 dark:text-pink-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'budget' ? null : 'budget')} active={expandedMetric === 'budget'} />
                    <HeroMetric label="Utilized Amt" value={fmtCost(sap.summary.totalDeliveredINR)} icon={Activity} color="text-orange-500 dark:text-orange-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'utilized' ? null : 'utilized')} active={expandedMetric === 'utilized'} />
                    <HeroMetric label="Remaining Bal" value={fmtCost((sap.summary.totalBudgetINR || 0) - (sap.summary.totalDeliveredINR || 0))} icon={Target} color="text-teal-500 dark:text-teal-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'remaining' ? null : 'remaining')} active={expandedMetric === 'remaining'} />
                    <HeroMetric label="% Consumed" value={`${sap.summary.totalBudgetINR ? ((sap.summary.totalDeliveredINR / sap.summary.totalBudgetINR) * 100).toFixed(1) : '0'}%`} icon={BarChart3} color={sap.summary.totalBudgetINR && (sap.summary.totalDeliveredINR / sap.summary.totalBudgetINR) > 0.9 ? 'text-red-500 dark:text-red-400' : 'text-emerald-500 dark:text-emerald-400'} />
                    <HeroMetric label="In Transit" value={fmtMW(sap.summary.totalInTransitQty)} unit="" icon={Truck} color="text-amber-500 dark:text-amber-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'transit' ? null : 'transit')} active={expandedMetric === 'transit'} />
                  </div>

                  {/* ── Interactive Breakdown Panel ── */}
                  {expandedMetric && (
                    <div className="intelligence-card p-5 animate-in slide-in-from-top-2 duration-300 border-primary/20">
                      <div className="flex items-center justify-between mb-4">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-primary flex items-center gap-2">
                          <Zap className="w-3.5 h-3.5" />
                          {expandedMetric === 'pos' && 'Purchase Order Breakdown'}
                          {expandedMetric === 'vendors' && 'Vendor Breakdown'}
                          {expandedMetric === 'materials' && 'Material Type Breakdown'}
                          {expandedMetric === 'volume' && 'PO Volume by Material'}
                          {expandedMetric === 'inventory' && 'Inventory Breakdown (Qty & Value)'}
                          {expandedMetric === 'budget' && 'Budget Allocation by Material'}
                          {expandedMetric === 'utilized' && 'Utilization by Material'}
                          {expandedMetric === 'remaining' && 'Remaining Balance by Material'}
                          {expandedMetric === 'transit' && 'In-Transit Breakdown'}
                        </h4>
                        <button onClick={() => setExpandedMetric(null)} className="text-muted-foreground hover:text-foreground text-xs px-2 py-1 rounded hover:bg-muted/50 transition-colors">✕ Close</button>
                      </div>
                      <div className="overflow-x-auto max-h-[350px] overflow-y-auto scrollbar-thin">
                        <table className="intel-table w-full text-xs">
                          <thead className="sticky top-0 bg-card/95 backdrop-blur-sm z-10 text-[10px] uppercase tracking-wider">
                            {/* ── PO Breakdown ── */}
                            {expandedMetric === 'pos' && (
                              <tr>
                                <th className="text-left">PO Number</th>
                                <th className="text-left">Material</th>
                                <th className="text-left">Vendor</th>
                                <th className="text-right">Ordered Qty</th>
                                <th className="text-right">Budget (INR)</th>
                                <th className="text-right">Delivered Value</th>
                                <th className="text-center">Storage</th>
                              </tr>
                            )}
                            {/* ── Vendor Breakdown ── */}
                            {expandedMetric === 'vendors' && (
                              <tr>
                                <th className="text-left">Vendor Name</th>
                                <th className="text-center">PO Count</th>
                                <th className="text-center">Materials</th>
                                <th className="text-right">Total Ordered Qty</th>
                                <th className="text-right">Total Budget (INR)</th>
                              </tr>
                            )}
                            {/* ── Material Type Breakdown ── */}
                            {expandedMetric === 'materials' && (
                              <tr>
                                <th className="text-left">Material Code</th>
                                <th className="text-left">Description</th>
                                <th className="text-right">Ordered</th>
                                <th className="text-right">Consumed</th>
                                <th className="text-right">Inventory</th>
                                <th className="text-right">In Transit</th>
                              </tr>
                            )}
                            {/* ── Volume Breakdown ── */}
                            {expandedMetric === 'volume' && (
                              <tr>
                                <th className="text-left">Material Code</th>
                                <th className="text-left">Description</th>
                                <th className="text-right">Ordered Qty</th>
                                <th className="text-right">% of Total</th>
                                <th className="text-left">Distribution</th>
                              </tr>
                            )}
                            {/* ── Inventory Breakdown ── */}
                            {expandedMetric === 'inventory' && (
                              <tr>
                                <th className="text-left">Material Code</th>
                                <th className="text-left">Description</th>
                                <th className="text-right">Inventory Qty</th>
                                <th className="text-right">Inventory Value (INR)</th>
                                <th className="text-center">Storage Location</th>
                              </tr>
                            )}
                            {/* ── Budget / Utilized / Remaining ── */}
                            {(expandedMetric === 'budget' || expandedMetric === 'utilized' || expandedMetric === 'remaining') && (
                              <tr>
                                <th className="text-left">Material Code</th>
                                <th className="text-left">Description</th>
                                <th className="text-right">Total Budget</th>
                                <th className="text-right">Delivered Amt</th>
                                <th className="text-right">Remaining</th>
                                <th className="text-left">Utilization</th>
                              </tr>
                            )}
                            {/* ── Transit Breakdown ── */}
                            {expandedMetric === 'transit' && (
                              <tr>
                                <th className="text-left">Material Code</th>
                                <th className="text-left">Vendor</th>
                                <th className="text-right">In-Transit Qty</th>
                                <th className="text-left">WBS Element</th>
                              </tr>
                            )}
                          </thead>
                          <tbody className="divide-y divide-border/30">
                            {/* ── PO Rows ── */}
                            {expandedMetric === 'pos' && (sap.purchaseOrders || []).slice(0, 50).map((po: any, i: number) => (
                              <tr key={i} className="hover:bg-muted/30 transition-colors">
                                <td className="text-left font-mono font-medium text-primary/80">{po.poNumber}</td>
                                <td className="text-left text-foreground/70 max-w-[150px] truncate" title={po.materialName}>{po.materialName || po.materialCode}</td>
                                <td className="text-left text-foreground/70 max-w-[150px] truncate" title={po.vendorName}>{po.vendorName || '—'}</td>
                                <td className="text-right font-mono font-semibold text-blue-400">{Number(po.orderedQty || 0).toLocaleString('en-IN')}</td>
                                <td className="text-right font-mono text-foreground/70">{fmtCost(po.budgetINR)}</td>
                                <td className="text-right font-mono text-emerald-500">{fmtCost(po.deliveredINR)}</td>
                                <td className="text-center"><span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${po.storageLocation === 'CS01' ? 'bg-blue-500/10 text-blue-500' : 'bg-purple-500/10 text-purple-500'}`}>{po.storageLocation || '—'}</span></td>
                              </tr>
                            ))}
                            {/* ── Vendor Rows ── */}
                            {expandedMetric === 'vendors' && (sap.vendorBreakdown || []).map((v: any, i: number) => (
                              <tr key={i} className="hover:bg-muted/30 transition-colors">
                                <td className="text-left font-medium text-foreground/80 max-w-[200px] truncate" title={v.vendorName}>{v.vendorName}</td>
                                <td className="text-center font-mono font-semibold text-blue-400">{v.poCount}</td>
                                <td className="text-center font-mono text-purple-400">{v.materialCount}</td>
                                <td className="text-right font-mono font-semibold text-foreground">{Number(v.totalOrderedQty || 0).toLocaleString('en-IN')}</td>
                                <td className="text-right font-mono text-pink-400">{fmtCost(v.totalBudgetINR)}</td>
                              </tr>
                            ))}
                            {/* ── Materials Rows ── */}
                            {expandedMetric === 'materials' && unifiedMaterials.slice(0, 50).map((mat: any, i: number) => (
                              <tr key={i} className="hover:bg-muted/30 transition-colors">
                                <td className="text-left font-mono text-primary/80">{mat.materialCode}</td>
                                <td className="text-left text-foreground/70 max-w-[180px] truncate" title={mat.materialDescription}>{mat.materialDescription}</td>
                                <td className="text-right font-mono text-blue-400">{mat.orderedQty ? Number(mat.orderedQty).toLocaleString('en-IN') : '—'}</td>
                                <td className="text-right font-mono text-emerald-500">{mat.consumedQty ? Number(mat.consumedQty).toLocaleString('en-IN') : '—'}</td>
                                <td className="text-right font-mono text-purple-400">{mat.inventoryQty ? Number(mat.inventoryQty).toLocaleString('en-IN') : '—'}</td>
                                <td className="text-right font-mono text-amber-400">{mat.inTransitQty ? Number(mat.inTransitQty).toLocaleString('en-IN') : '—'}</td>
                              </tr>
                            ))}
                            {/* ── Volume Rows ── */}
                            {expandedMetric === 'volume' && unifiedMaterials.filter((m: any) => m.orderedQty > 0).slice(0, 30).map((mat: any, i: number) => {
                              const pct = sap.summary.totalOrderedQty ? (mat.orderedQty / sap.summary.totalOrderedQty) * 100 : 0;
                              return (
                                <tr key={i} className="hover:bg-muted/30 transition-colors">
                                  <td className="text-left font-mono text-primary/80">{mat.materialCode}</td>
                                  <td className="text-left text-foreground/70 max-w-[150px] truncate" title={mat.materialDescription}>{mat.materialDescription}</td>
                                  <td className="text-right font-mono font-semibold text-blue-400">{Number(mat.orderedQty).toLocaleString('en-IN')}</td>
                                  <td className="text-right font-mono text-foreground/60">{pct.toFixed(1)}%</td>
                                  <td className="text-left"><div className="w-full h-2 bg-muted rounded-full overflow-hidden"><div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400" style={{ width: `${Math.min(pct, 100)}%` }}></div></div></td>
                                </tr>
                              );
                            })}
                            {/* ── Inventory Rows ── */}
                            {expandedMetric === 'inventory' && (sap.inventory || []).filter((inv: any) => (inv.inventoryQty || 0) > 0).slice(0, 50).map((inv: any, i: number) => (
                              <tr key={i} className="hover:bg-muted/30 transition-colors">
                                <td className="text-left font-mono text-primary/80">{inv.materialCode}</td>
                                <td className="text-left text-foreground/70 max-w-[150px] truncate">{inv.materialName || '—'}</td>
                                <td className="text-right font-mono font-semibold text-emerald-400">{Number(inv.inventoryQty || 0).toLocaleString('en-IN')}</td>
                                <td className="text-right font-mono text-purple-400">{inv.inventoryValueINR ? `₹${Number(inv.inventoryValueINR).toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'}</td>
                                <td className="text-center"><span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${inv.storageLocation === 'CS01' ? 'bg-blue-500/10 text-blue-500' : 'bg-purple-500/10 text-purple-500'}`}>{inv.storageLocation || '—'}</span></td>
                              </tr>
                            ))}
                            {/* ── Budget / Utilized / Remaining Rows ── */}
                            {(expandedMetric === 'budget' || expandedMetric === 'utilized' || expandedMetric === 'remaining') && unifiedMaterials.filter((m: any) => m.budgetINR > 0).slice(0, 50).map((mat: any, i: number) => {
                              const utilPct = mat.budgetINR ? (mat.deliveredINR / mat.budgetINR) * 100 : 0;
                              return (
                                <tr key={i} className="hover:bg-muted/30 transition-colors">
                                  <td className="text-left font-mono text-primary/80">{mat.materialCode}</td>
                                  <td className="text-left text-foreground/70 max-w-[150px] truncate" title={mat.materialDescription}>{mat.materialDescription}</td>
                                  <td className="text-right font-mono text-pink-400">{fmtCost(mat.budgetINR)}</td>
                                  <td className="text-right font-mono text-orange-400">{fmtCost(mat.deliveredINR)}</td>
                                  <td className="text-right font-mono text-teal-400">{fmtCost(mat.remainingBalanceINR)}</td>
                                  <td className="text-left">
                                    <div className="flex items-center gap-2">
                                      <div className="w-16 h-2 bg-muted rounded-full overflow-hidden"><div className={`h-full rounded-full ${utilPct > 90 ? 'bg-red-500' : utilPct > 60 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${Math.min(utilPct, 100)}%` }}></div></div>
                                      <span className={`text-[10px] font-mono font-bold ${utilPct > 90 ? 'text-red-400' : utilPct > 60 ? 'text-amber-400' : 'text-emerald-400'}`}>{utilPct.toFixed(0)}%</span>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                            {/* ── Transit Rows ── */}
                            {expandedMetric === 'transit' && (sap.inTransit || []).filter((t: any) => (t.inTransitQty || 0) > 0).slice(0, 50).map((t: any, i: number) => (
                              <tr key={i} className="hover:bg-muted/30 transition-colors">
                                <td className="text-left font-mono text-primary/80">{t.materialCode}</td>
                                <td className="text-left text-foreground/70 max-w-[150px] truncate" title={t.vendorName}>{t.vendorName || '—'}</td>
                                <td className="text-right font-mono font-semibold text-amber-400">{Number(t.inTransitQty || 0).toLocaleString('en-IN')}</td>
                                <td className="text-left font-mono text-foreground/50 text-[10px]">{t.wbsElement || '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {/* Summary footer */}
                      {expandedMetric === 'inventory' && (
                        <div className="mt-3 pt-3 border-t border-border/30 flex items-center gap-6 text-xs">
                          <span className="text-muted-foreground">Total Inventory Value:</span>
                          <span className="font-mono font-bold text-purple-400">{fmtCost(sap.summary.totalInventoryValueINR)}</span>
                          <span className="text-muted-foreground ml-4">Total Inventory Qty:</span>
                          <span className="font-mono font-bold text-emerald-400">{fmtMW(sap.summary.totalInventoryQty)}</span>
                        </div>
                      )}
                      {expandedMetric === 'transit' && (
                        <div className="mt-3 pt-3 border-t border-border/30 flex items-center gap-6 text-xs">
                          <span className="text-muted-foreground">Total In-Transit Qty:</span>
                          <span className="font-mono font-bold text-amber-400">{fmtMW(sap.summary.totalInTransitQty)}</span>
                          <span className="text-muted-foreground ml-4">Unique Materials in Transit:</span>
                          <span className="font-mono font-bold text-amber-400">{new Set((sap.inTransit || []).map((t: any) => t.materialCode)).size}</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Allocation Context */}
                  {sap.allocation && (
                    <div className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-primary/[0.04] border border-primary/[0.08] text-[11px] text-muted-foreground/60">
                      <Database className="w-3.5 h-3.5 text-primary/50 shrink-0" />
                      <span>
                        Data allocated to this project: <span className="font-semibold text-foreground/70">{sap.allocation.projectCapacityMW} MW</span> of{' '}
                        <span className="font-medium text-foreground/60">{sap.allocation.totalPlantCapacityMW} MW</span> total plant capacity
                        <span className="text-muted-foreground/40"> · </span>
                        Ratio: <span className="font-mono font-semibold text-primary/70">{(sap.allocation.allocationRatio * 100).toFixed(1)}%</span>
                        {sap.allocation.wbsFilter && (
                          <>
                            <span className="text-muted-foreground/40"> · </span>
                            WBS: <span className="font-mono text-foreground/60">{sap.allocation.wbsFilter}</span>
                          </>
                        )}
                      </span>
                    </div>
                  )}

                  {/* Unified Material Tracking & Chart */}
                  <div className="space-y-6">

                    {/* Analytics Line Chart */}
                    <div className="intelligence-card p-6 flex flex-col h-[400px]">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <BarChart3 className="w-4 h-4 text-primary/70" /> Consumption Trends
                      </h3>
                      <div className="flex-1">
                        {!sap.consumption || sap.consumption.length === 0 ? (
                          <div className="h-full w-full flex flex-col items-center justify-center border border-dashed border-border/40 rounded-xl bg-muted/5">
                            <BarChart3 className="w-8 h-8 text-muted-foreground/20 mb-3" />
                            <p className="text-sm font-medium text-muted-foreground/70">No Consumption Data</p>
                            <p className="text-xs text-muted-foreground/40 mt-1 max-w-[250px] text-center">There are no MB51 material consumption records for this selection.</p>
                          </div>
                        ) : (
                          <ReactECharts
                            option={{
                              tooltip: { trigger: 'axis', backgroundColor: 'rgba(9,9,11,0.9)', borderColor: '#27272a', textStyle: { color: '#e4e4e7' } },
                              legend: { data: ['Consumed Qty', 'Reversals', 'Value INR'], textStyle: { color: '#a1a1aa' }, top: 0, right: 0 },
                              grid: { top: 30, right: 10, bottom: 40, left: 40 },
                              xAxis: { type: 'category', data: sap.consumption.map((c: any) => c.postingDate ? new Date(c.postingDate).toLocaleDateString() : (c.wbsElement || 'Unknown')).slice(0, 40), axisLabel: { color: '#71717a', fontSize: 10, rotate: 45, interval: 0 } },
                              yAxis: [
                                { type: 'value', axisLabel: { color: '#71717a', fontSize: 10 }, splitLine: { lineStyle: { color: '#27272a' } } },
                                { type: 'value', axisLabel: { color: '#71717a', fontSize: 10 }, splitLine: { show: false }, position: 'right' }
                              ],
                              series: [
                                { name: 'Consumed Qty', type: 'line', smooth: true, data: sap.consumption.map((c: any) => String(c.movementType) === '221' ? -c.quantity : 0).slice(0, 40), itemStyle: { color: '#10b981' }, areaStyle: { color: 'rgba(16, 185, 129, 0.1)' } },
                                { name: 'Reversals', type: 'line', smooth: true, data: sap.consumption.map((c: any) => String(c.movementType) === '222' ? c.quantity : 0).slice(0, 40), itemStyle: { color: '#ef4444' }, areaStyle: { color: 'rgba(239, 68, 68, 0.1)' } },
                                { name: 'Value INR', type: 'line', smooth: true, yAxisIndex: 1, data: sap.consumption.map((c: any) => -c.amountINR).slice(0, 40), itemStyle: { color: '#3b82f6' } }
                              ]
                            }}
                            style={{ height: '100%', width: '100%' }}
                          />
                        )}
                      </div>
                    </div>
                    
                    {/* Unified Table */}
                    <div className="intelligence-card p-6">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                          <Box className="w-4 h-4 text-primary/70" /> Material Lifecycle & Tracking
                        </h3>
                        <div className="flex bg-muted/40 p-1 rounded-md border border-border/50">
                          <button onClick={() => setInventoryFilter('ALL')} className={`px-3 py-1 text-xs font-medium rounded-sm transition-all ${inventoryFilter === 'ALL' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}>All Stock</button>
                          <button onClick={() => setInventoryFilter('COMPANY')} className={`px-3 py-1 text-xs font-medium rounded-sm transition-all ${inventoryFilter === 'COMPANY' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}>Company (CS01)</button>
                          <button onClick={() => setInventoryFilter('PROJECT')} className={`px-3 py-1 text-xs font-medium rounded-sm transition-all ${inventoryFilter === 'PROJECT' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}>Project (PS01)</button>
                        </div>
                      </div>
                      
                      <div className="overflow-x-auto max-h-[600px] overflow-y-auto scrollbar-thin">
                        <table className="intel-table relative w-full text-xs">
                          <thead className="sticky top-0 bg-card/95 backdrop-blur-sm z-10 shadow-sm text-[10px] uppercase tracking-wider whitespace-nowrap">
                            <tr>
                              <th className="w-8"></th>
                              <th className="text-center">Material Code</th>
                              <th className="text-left">Material Description</th>
                              <th className="text-left">WBS Tracking</th>
                              <th className="text-center">Ordered</th>
                              <th className="text-center">Consumed</th>
                              <th className="text-center">Remaining Qty</th>
                              <th className="text-center">Inventory Qty</th>
                              <th className="text-center">Inventory Value</th>
                              <th className="text-center">In Transit</th>
                              <th className="text-center">Total Budget</th>
                              <th className="text-center">Delivered Amt</th>
                              <th className="text-center">Remaining Bal</th>
                            </tr>
                          </thead>
                          <tbody>
                            {unifiedMaterials.map((mat: any, i: number) => {
                              const isExpanded = expandedMaterial === mat.materialCode;
                              return (
                                <React.Fragment key={i}>
                                  {/* Master Row */}
                                  <tr className={`cursor-pointer transition-colors ${isExpanded ? 'bg-primary/5' : 'hover:bg-primary/5'}`} onClick={() => setExpandedMaterial(isExpanded ? null : mat.materialCode)}>
                                    <td className="text-center text-muted-foreground">
                                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                    </td>
                                    <td className="text-center font-mono font-medium text-primary/90">{mat.materialCode}</td>
                                    <td className="text-left font-medium text-foreground/80 max-w-[200px] truncate" title={mat.materialDescription}>{mat.materialDescription}</td>
                                    <td className="text-left">
                                      {mat.wbsList && mat.wbsList.length > 0 ? (
                                        <div className="flex items-center gap-1 flex-wrap max-w-[150px]">
                                          <span className="px-1.5 py-0.5 bg-primary/10 text-primary border border-primary/20 rounded text-[9px] font-mono whitespace-nowrap truncate max-w-[100px]" title={mat.wbsList[0]}>{mat.wbsList[0]}</span>
                                          {mat.wbsList.length > 1 && (
                                            <span className="text-[9px] text-muted-foreground font-medium" title={mat.wbsList.slice(1).join(', ')}>+{mat.wbsList.length - 1}</span>
                                          )}
                                        </div>
                                      ) : <span className="text-muted-foreground/40">—</span>}
                                    </td>
                                    <td className="text-center font-mono font-semibold text-blue-400">{mat.orderedQty ? Number(mat.orderedQty).toLocaleString('en-IN') : '—'}</td>
                                    <td className="text-center font-mono font-semibold text-emerald-500">{mat.consumedQty ? Number(mat.consumedQty).toLocaleString('en-IN') : '—'}</td>
                                    <td className="text-center font-mono font-semibold text-amber-500">{mat.remainingQty ? Number(mat.remainingQty).toLocaleString('en-IN') : '—'}</td>
                                    <td className="text-center font-mono text-purple-400">{mat.inventoryQty ? Number(mat.inventoryQty).toLocaleString('en-IN') : '—'}</td>
                                    <td className="text-center font-mono text-purple-400/80">{mat.inventoryValueINR ? `₹${Number(mat.inventoryValueINR).toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'}</td>
                                    <td className="text-center font-mono text-orange-400">{mat.inTransitQty ? Number(mat.inTransitQty).toLocaleString('en-IN') : '—'}</td>
                                    <td className="text-center font-mono text-foreground/70">{mat.budgetINR ? `₹${Number(mat.budgetINR).toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'}</td>
                                    <td className="text-center font-mono text-emerald-500/80">{mat.deliveredINR ? `₹${Number(mat.deliveredINR).toLocaleString('en-IN')}` : '—'}</td>
                                    <td className="text-center font-mono text-amber-500/80">{mat.remainingBalanceINR ? `₹${Number(mat.remainingBalanceINR).toLocaleString('en-IN')}` : '—'}</td>
                                  </tr>
                                  
                                  {/* Drill-down Detail Row */}
                                  {isExpanded && (
                                    <tr className="bg-muted/30 border-b border-border/50">
                                      <td colSpan={12} className="p-0">
                                        <div className="p-6 space-y-6">
                                          
                                          {/* PO Details */}
                                          {mat.pos.length > 0 && (
                                            <div>
                                              <h4 className="text-xs uppercase text-muted-foreground mb-3 font-semibold tracking-wider flex items-center gap-2"><FileText className="w-3.5 h-3.5"/> Purchase Orders</h4>
                                              <div className="rounded-md border border-border/50 bg-background/50 overflow-hidden shadow-sm">
                                                <table className="intel-table w-full text-xs">
                                                  <thead className="bg-muted/50 text-[10px] text-muted-foreground uppercase tracking-wider">
                                                    <tr>
                                                      <th className="text-left font-semibold py-2 px-4">PO Number</th>
                                                      <th className="text-right font-semibold py-2 px-4">Ordered Qty</th>
                                                      <th className="text-center font-semibold py-2 px-4 w-32">Storage Location</th>
                                                    </tr>
                                                  </thead>
                                                  <tbody className="divide-y divide-border/30">
                                                    {mat.pos.map((po: any, j: number) => (
                                                      <tr key={j} className="hover:bg-muted/50 transition-colors">
                                                        <td className="text-left font-mono font-medium text-foreground py-2 px-4">{po.poNumber}</td>
                                                        <td className="text-right font-mono font-semibold text-blue-500 dark:text-blue-400 py-2 px-4">{po.orderedQty} Unit</td>
                                                        <td className="text-center py-2 px-4">
                                                          <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${po.storageLocation === 'CS01' ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400' : 'bg-purple-500/10 text-purple-600 dark:text-purple-400'}`}>{po.storageLocation || '—'}</span>
                                                        </td>
                                                      </tr>
                                                    ))}
                                                  </tbody>
                                                </table>
                                              </div>
                                            </div>
                                          )}

                                          {/* Consumption Details */}
                                          {mat.consumptions.length > 0 && (
                                            <div>
                                              <h4 className="text-xs uppercase text-muted-foreground mb-3 font-semibold tracking-wider flex items-center gap-2"><Activity className="w-3.5 h-3.5"/> Consumptions</h4>
                                              <div className="rounded-md border border-border/50 bg-background/50 overflow-hidden shadow-sm">
                                                <table className="intel-table w-full text-xs">
                                                  <thead className="bg-muted/50 text-[10px] text-muted-foreground uppercase tracking-wider">
                                                    <tr>
                                                      <th className="text-center font-semibold py-2 px-4 w-24">Movement</th>
                                                      <th className="text-left font-semibold py-2 px-4">WBS Element / Date</th>
                                                      <th className="text-right font-semibold py-2 px-4">Quantity</th>
                                                    </tr>
                                                  </thead>
                                                  <tbody className="divide-y divide-border/30">
                                                    {mat.consumptions.slice(0, 50).map((c: any, j: number) => (
                                                      <tr key={j} className="hover:bg-muted/50 transition-colors">
                                                        <td className="text-center py-2 px-4">
                                                          <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${String(c.movementType) === '221' ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-red-500/10 text-red-600 dark:text-red-400'}`}>{c.movementType}</span>
                                                        </td>
                                                        <td className="text-left text-foreground/80 font-medium py-2 px-4">{c.wbsElement || c.postingDate}</td>
                                                        <td className="text-right font-mono font-semibold text-foreground py-2 px-4">{c.quantity}</td>
                                                      </tr>
                                                    ))}
                                                  </tbody>
                                                </table>
                                              </div>
                                            </div>
                                          )}

                                          {/* Inventory Details */}
                                          {mat.inventories.length > 0 && (
                                            <div>
                                              <h4 className="text-xs uppercase text-muted-foreground mb-3 font-semibold tracking-wider flex items-center gap-2"><Package className="w-3.5 h-3.5"/> Inventory Storage</h4>
                                              <div className="rounded-md border border-border/50 bg-background/50 overflow-hidden shadow-sm">
                                                <table className="intel-table w-full text-xs">
                                                  <thead className="bg-muted/50 text-[10px] text-muted-foreground uppercase tracking-wider">
                                                    <tr>
                                                      <th className="text-left font-semibold py-2 px-4">WBS Element</th>
                                                      <th className="text-right font-semibold py-2 px-4">Inventory Qty</th>
                                                      <th className="text-right font-semibold py-2 px-4">Value (INR)</th>
                                                      <th className="text-center font-semibold py-2 px-4 w-32">Storage Location</th>
                                                    </tr>
                                                  </thead>
                                                  <tbody className="divide-y divide-border/30">
                                                    {mat.inventories.map((inv: any, j: number) => (
                                                      <tr key={j} className="hover:bg-muted/50 transition-colors">
                                                        <td className="text-left font-mono font-medium text-foreground py-2 px-4">{inv.wbsElement || 'Stock'}</td>
                                                        <td className="text-right font-mono font-semibold text-emerald-600 dark:text-emerald-400 py-2 px-4">{inv.inventoryQty}</td>
                                                        <td className="text-right font-mono font-semibold text-foreground py-2 px-4">{fmtCost(inv.inventoryValueINR)}</td>
                                                        <td className="text-center py-2 px-4">
                                                          <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${inv.storageLocation === 'CS01' ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400' : 'bg-purple-500/10 text-purple-600 dark:text-purple-400'}`}>{inv.storageLocation || '—'}</span>
                                                        </td>
                                                      </tr>
                                                    ))}
                                                  </tbody>
                                                </table>
                                              </div>
                                            </div>
                                          )}

                                        </div>
                                      </td>
                                    </tr>
                                  )}
                                </React.Fragment>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

          {/* ════════ P6 DEEP DIVE TAB (NEW) ════════ */}
          {activeTab === 'p6' && (
            <div className="space-y-6">
              {detailLoading ? (
                <div className="flex items-center justify-center h-[300px]">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-5 h-5 text-primary animate-spin" />
                    <span className="text-sm text-muted-foreground/60">Loading P6 data...</span>
                  </div>
                </div>
              ) : !p6 ? (
                <div className="intelligence-card p-12 flex flex-col items-center justify-center text-center">
                  <Layers className="w-10 h-10 text-muted-foreground/20 mb-3" />
                  <p className="text-muted-foreground/60 text-sm">No enriched P6 data available.</p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                    {/* Full Project Timeline */}
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-primary/70" /> Complete Project Timeline
                      </h3>
                      <div className="space-y-1">
                        {[
                          ['Project ID', p6.projectId],
                          ['Status', p6.status],
                          ['Location', p6.locationName || '—'],
                          ['Parent EPS', p6.parentEPSName || '—'],
                          ['Start Date', p6.startDate || '—'],
                          ['Planned Start', p6.plannedStartDate || '—'],
                          ['Finish Date', p6.finishDate || '—'],
                          ['Scheduled Finish', p6.scheduledFinishDate || '—'],
                          ['Data Date', p6.dataDate || '—'],
                          ['Must Finish By', p6.mustFinishByDate || '—'],
                          ['Baseline Start', p6.baselineStartDate || '—'],
                          ['Baseline Finish', p6.baselineFinishDate || '—'],
                          ['Last Synced', p6.lastSyncedAt || '—'],
                        ].map(([label, val]) => (
                          <div key={label as string} className="detail-row">
                            <span className="detail-row-label">{label}</span>
                            <span className="detail-row-value">{val}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Cost Analysis */}
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <DollarSign className="w-4 h-4 text-primary/70" /> Cost Analysis
                      </h3>
                      <div className="space-y-1">
                        {[
                          ['Actual Total Cost', fmtCost(p6.actualTotalCost)],
                          ['Planned Cost', fmtCost(p6.plannedCost)],
                          ['Current Budget', fmtCost(p6.currentBudget)],
                          ['Cost Variance', fmtCost(p6.totalCostVariance)],
                          ['Baseline Total Cost', fmtCost(p6.baselineTotalCost)],
                          ['CPI', p6.cpi != null ? p6.cpi.toFixed(3) : '—'],
                          ['SPI', p6.spi != null ? p6.spi.toFixed(3) : '—'],
                        ].map(([label, val]) => (
                          <div key={label as string} className="detail-row">
                            <span className="detail-row-label">{label}</span>
                            <span className={`detail-row-value ${
                              label === 'Cost Variance' && p6.totalCostVariance && p6.totalCostVariance < 0 ? 'text-red-400' :
                              label === 'CPI' && p6.cpi && p6.cpi < 0.95 ? 'text-amber-400' :
                              label === 'SPI' && p6.spi && p6.spi < 0.95 ? 'text-red-400' : ''
                            }`}>{val}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Float Analysis */}
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Clock className="w-4 h-4 text-primary/70" /> Float & Variance
                      </h3>
                      <div className="space-y-1">
                        {[
                          ['Total Float', p6.totalFloat != null ? `${Math.round(p6.totalFloat)} hrs` : '—'],
                          ['Finish Date Variance', fmtDays(p6.finishDateVariance)],
                          ['Start Date Variance', fmtDays(p6.startDateVariance)],
                          ['Duration Variance', p6.durationVariance != null ? `${Math.round(p6.durationVariance)} hrs` : '—'],
                        ].map(([label, val]) => (
                          <div key={label as string} className="detail-row">
                            <span className="detail-row-label">{label}</span>
                            <span className={`detail-row-value ${
                              (label === 'Total Float' && p6.totalFloat != null && p6.totalFloat <= 0) ? 'text-red-400 font-semibold' :
                              (label === 'Finish Date Variance' && p6.finishDateVariance != null && p6.finishDateVariance < -10) ? 'text-red-400' : ''
                            }`}>{val}</span>
                          </div>
                        ))}
                        {p6.totalFloat != null && (
                          <div className="mt-3 p-3 rounded-lg bg-muted/50 border border-border">
                            <p className="text-[11px] text-muted-foreground/60 leading-relaxed">
                              {p6.totalFloat <= 0
                                ? '⚠️ Critical path — zero or negative float. Any delay directly impacts the project finish date.'
                                : p6.totalFloat < 80
                                ? '⚡ Low float — limited buffer remaining. Monitor closely for potential delays.'
                                : '✅ Adequate float — schedule has sufficient buffer.'}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Duration Analysis */}
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Clock className="w-4 h-4 text-primary/70" /> Duration Analysis
                      </h3>
                      <div className="space-y-1">
                        {[
                          ['Planned Duration', fmtHrs(p6.plannedDuration)],
                          ['Actual Duration', fmtHrs(p6.actualDuration)],
                          ['Remaining Duration', fmtHrs(p6.remainingDuration)],
                          ['Baseline Duration', fmtHrs(p6.baselineDuration)],
                          ['% Complete', p6.durationPercentComplete != null ? `${(p6.durationPercentComplete < 1 ? p6.durationPercentComplete * 100 : p6.durationPercentComplete).toFixed(1)}%` : '—'],
                        ].map(([label, val]) => (
                          <div key={label as string} className="detail-row">
                            <span className="detail-row-label">{label}</span>
                            <span className="detail-row-value">{val}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Activity Baseline Comparison */}
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <BarChart3 className="w-4 h-4 text-primary/70" /> Baseline vs Current
                      </h3>
                      <div className="space-y-3">
                        {[
                          { label: 'Completed', current: p6.completedActivities, baseline: p6.baselineCompletedActivities, color: '#10B981' },
                          { label: 'In Progress', current: p6.inProgressActivities, baseline: p6.baselineInProgressActivities, color: '#3B82F6' },
                          { label: 'Not Started', current: p6.notStartedActivities, baseline: p6.baselineNotStartedActivities, color: 'rgba(255,255,255,0.15)' },
                        ].map(item => (
                          <div key={item.label}>
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs text-muted-foreground/60">{item.label}</span>
                              <div className="flex items-center gap-3 text-xs font-mono">
                                <span className="text-foreground/80">{item.current ?? '—'}</span>
                                <span className="text-muted-foreground/30">vs</span>
                                <span className="text-muted-foreground/50">{item.baseline ?? '—'}</span>
                              </div>
                            </div>
                            {item.current != null && (
                              <div className="flex gap-1 h-1.5">
                                <div className="rounded-full" style={{ width: `${Math.max(5, (item.current / Math.max(p6.activityCount || 1, 1)) * 100)}%`, background: item.color }}></div>
                                {item.baseline != null && (
                                  <div className="rounded-full opacity-30" style={{ width: `${Math.max(5, (item.baseline / Math.max(p6.activityCount || 1, 1)) * 100)}%`, background: item.color }}></div>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Mapping Info */}
                  {mapping && (
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-primary/70" /> Project Mapping
                      </h3>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        {[
                          ['P6 Project Name', mapping.p6ProjectName],
                          ['SAP Plant Code', mapping.sapPlantCode || '—'],
                          ['AGEL Code', mapping.agelCode || '—'],
                          ['Module WBS', mapping.moduleWBS || '—'],
                          ['Capacity', mapping.capacityMW ? `${mapping.capacityMW} MW` : '—'],
                        ].map(([label, val]) => (
                          <div key={label as string}>
                            <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/40 mb-1">{label}</div>
                            <div className="text-sm font-mono text-foreground/80 truncate">{val}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ════════ TRANSMISSION TAB ════════ */}
          {activeTab === 'transmission' && (
            <div className="space-y-6">
              {/* Transmission Portal Link Banner */}
              <div className="intelligence-card p-6 flex flex-col md:flex-row items-center justify-between gap-6 border-primary/20 bg-primary/[0.02]">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                    <Network className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-foreground">Live Transmission Commissioning Portal</h3>
                    <p className="text-sm text-muted-foreground mt-1">Access the live Adani Transmission dashboard for deep-dive real-time metrics.</p>
                    
                    <div className="flex items-center gap-2 mt-3 text-xs bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-400 px-3 py-1.5 rounded-md w-fit">
                      <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                      <span><strong>Auto-Login Enabled:</strong> You will be securely authenticated automatically.</span>
                    </div>
                  </div>
                </div>
                
                <a 
                  href={`https://adani.unada.in/transmission/v1/dashboard/khavda/commissioning-team?project=${projectId}&email=c7lj9OK6uzRLjiZLxS84y0QthSsZe7POcrGs-DIVaA0pmSPD9rlCGg2-Cg&pass=bFLZzcL7tsx1pZUJBqCXnMMkKQySqhmUDczHBCCX63aLNJ69`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-6 py-3 rounded-xl font-bold shadow-sm hover:shadow-md transition-all whitespace-nowrap shrink-0 group"
                >
                  Open Portal <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </a>
              </div>

              {detailLoading ? (
                <div className="flex items-center justify-center h-[300px]">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-5 h-5 text-primary animate-spin" />
                    <span className="text-sm text-muted-foreground/60">Loading Transmission data...</span>
                  </div>
                </div>
              ) : !tc || !tc.summary.hasData ? (
                <div className="intelligence-card p-12 flex flex-col items-center justify-center text-center">
                  <Network className="w-10 h-10 text-muted-foreground/20 mb-3" />
                  <p className="text-muted-foreground/60 text-sm">No synchronized Transmission data linked to this project internally.</p>
                  <p className="text-muted-foreground/40 text-xs mt-1">TC Project: {mapping?.tcProjectName || '—'}</p>
                </div>
              ) : (
                <>
                  {/* TC Summary Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <HeroMetric label="Khavda Edges" value={tc.summary.totalKhavdaEdges} icon={Zap} color="text-purple-400" />
                    <HeroMetric label="Rajasthan Edges" value={tc.summary.totalRajasthanEdges} icon={Network} color="text-blue-400" />
                    <HeroMetric label="Total Mapped MW" value={tc.summary.totalMW ? `${tc.summary.totalMW}` : '—'} unit="MW" icon={Target} color="text-emerald-400" />
                    <HeroMetric label="TC Project" value={mapping?.tcProjectName || '—'} icon={MapPin} color="text-amber-400" />
                  </div>

                  {/* Khavda Transmission Lines Table */}
                  {tc.khavdaEdges.length > 0 && (
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Zap className="w-4 h-4 text-purple-400" /> Khavda Transmission Lines
                      </h3>
                      <div className="overflow-x-auto">
                        <table className="intel-table">
                          <thead>
                            <tr>
                              <th>Project / Phase</th>
                              <th>From</th>
                              <th>To</th>
                              <th>Voltage</th>
                              <th>Length</th>
                              <th>Contractor</th>
                              <th>Status</th>
                              <th>Erection</th>
                              <th>Foundation</th>
                              <th>Stringing</th>
                              <th>Expected Date</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tc.khavdaEdges.map((edge: any, i: number) => (
                              <tr key={i}>
                                <td className="font-bold text-purple-400 font-mono text-[10px] uppercase tracking-wider truncate max-w-[200px]" title={`${edge.project} (${edge.phase})`}>
                                  {edge.project} <span className="text-muted-foreground ml-1 font-normal lowercase tracking-normal">({edge.phase})</span>
                                </td>
                                <td className="font-medium text-foreground/90 max-w-[150px] truncate" title={edge.fromLabel || edge.fromNode}>{edge.fromLabel || edge.fromNode}</td>
                                <td className="font-medium text-foreground/90 max-w-[150px] truncate" title={edge.toLabel || edge.toNode}>{edge.toLabel || edge.toNode}</td>
                                <td className="font-mono text-xs">{edge.voltage || '—'}</td>
                                <td className="font-mono text-xs">{edge.length || '—'}</td>
                                <td className="text-muted-foreground/70 text-xs">{edge.contractor || '—'}</td>
                                <td>
                                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                                    edge.normalizedStatus === 'charged' ? 'bg-emerald-500/10 text-emerald-400' :
                                    edge.normalizedStatus === 'in_progress' ? 'bg-amber-500/10 text-amber-400' :
                                    'bg-muted text-muted-foreground'
                                  }`}>
                                    {edge.status || '—'}
                                  </span>
                                </td>
                                <td className="text-xs text-muted-foreground/80">{edge.erection || '—'}</td>
                                <td className="text-xs text-muted-foreground/80">{edge.foundation || '—'}</td>
                                <td className="text-xs text-muted-foreground/80">{edge.stringing || '—'}</td>
                                <td className="text-xs font-mono">{edge.expectedDate || '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Rajasthan Transmission Lines Table */}
                  {tc.rajasthanEdges.length > 0 && (
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Network className="w-4 h-4 text-blue-400" /> Rajasthan Transmission Lines
                      </h3>
                      <div className="overflow-x-auto">
                        <table className="intel-table">
                          <thead>
                            <tr>
                              <th>Project / Phase</th>
                              <th>From</th>
                              <th>To</th>
                              <th>Voltage</th>
                              <th>Length</th>
                              <th>Contractor</th>
                              <th>Status</th>
                              <th>Erection</th>
                              <th>Foundation</th>
                              <th>Stringing</th>
                              <th>Expected Date</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tc.rajasthanEdges.map((edge: any, i: number) => (
                              <tr key={i}>
                                <td className="font-bold text-purple-400 font-mono text-[10px] uppercase tracking-wider truncate max-w-[200px]" title={`${edge.project} (${edge.phase})`}>
                                  {edge.project} <span className="text-muted-foreground ml-1 font-normal lowercase tracking-normal">({edge.phase})</span>
                                </td>
                                <td className="font-medium text-foreground/90 max-w-[150px] truncate" title={edge.fromLabel || edge.fromNode}>{edge.fromLabel || edge.fromNode}</td>
                                <td className="font-medium text-foreground/90 max-w-[150px] truncate" title={edge.toLabel || edge.toNode}>{edge.toLabel || edge.toNode}</td>
                                <td className="font-mono text-xs">{edge.voltage || '—'}</td>
                                <td className="font-mono text-xs">{edge.length || '—'}</td>
                                <td className="text-muted-foreground/70 text-xs max-w-[120px] truncate">{edge.contractor || '—'}</td>
                                <td>
                                  <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                                    edge.normalizedStatus === 'Completed' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                                    edge.normalizedStatus === 'In Progress' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                                    'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                                  }`}>
                                    {edge.normalizedStatus || edge.status || '—'}
                                  </span>
                                </td>
                                <td className="font-mono text-xs text-muted-foreground/70">{edge.erection || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/70">{edge.foundation || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/70">{edge.stringing || '—'}</td>
                                <td className="font-mono text-xs">{edge.expectedDate || '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Transmission Substations & Nodes Table */}
                  {tc.nodes && tc.nodes.length > 0 && (
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-emerald-400" /> Transmission Substations & Nodes
                      </h3>
                      <div className="overflow-x-auto max-h-[300px] overflow-y-auto scrollbar-thin">
                        <table className="intel-table relative w-full">
                          <thead className="sticky top-0 bg-card/95 backdrop-blur-sm z-10 shadow-sm">
                            <tr>
                              <th>Node ID</th>
                              <th>Label</th>
                              <th>Type</th>
                              <th>Region</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tc.nodes.map((n: any, i: number) => (
                              <tr key={i}>
                                <td className="font-mono text-xs text-muted-foreground/80">{n.nodeId}</td>
                                <td className="font-bold text-foreground/90">{n.label || '—'}</td>
                                <td>
                                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-primary/10 text-primary border border-primary/20">
                                    {n.type || 'Unknown'}
                                  </span>
                                </td>
                                <td className="text-muted-foreground/70 text-xs">{n.region || '—'}</td>
                                <td>
                                  <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                                    n.status === 'Completed' || n.status === 'charged' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                                    n.status === 'In Progress' || n.status === 'in_progress' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                                    'bg-muted/50 text-muted-foreground border border-border'
                                  }`}>
                                    {n.status || '—'}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
