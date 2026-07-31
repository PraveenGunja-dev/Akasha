import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import {
  ArrowLeft, Activity, Calendar, Clock, BarChart3, TrendingUp, AlertTriangle, CheckCircle, Database, FileText, X,
  Layers, ChevronDown, ChevronUp, RefreshCcw, DollarSign, Target, Truck, Shield, Box, LayoutDashboard, Cpu, Network, Check,
  Loader2, Brain, CheckCircle2, BrainCircuit, Flag, CalendarClock, Download, Users, Package, Zap, MapPin, ChevronRight, ExternalLink, Play, Maximize2
} from 'lucide-react';
import { ProjectWBS } from './ProjectWBS';
import QualityProjectTab from '../quality/QualityProjectTab';
import { getCachedDashboardJson } from '../../services/dashboardQueryCache';

/* ── Circular Gauge ── */
const Gauge = ({ value, label, color, size = 72, stroke = 5 }: any) => {
  const radius = (size - stroke) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (Math.min(value, 100) / 100) * circumference;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} className="transform -rotate-90">
        <circle className="progress-ring-track" cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} />
        <circle className="progress-ring-fill" cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke}
          stroke={color} strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" />
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle"
          className="transform rotate-90 origin-center fill-foreground"
          style={{ fontSize: '14px', fontWeight: 700, fontFamily: 'monospace' }}>
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
    className={`bg-card hover:bg-muted transition-all duration-300 border rounded-2xl p-5 flex flex-col gap-3 group relative overflow-hidden shadow-card hover:shadow-card-hover ${active ? 'border-primary/60 ring-2 ring-primary/20 bg-primary/5' : 'border-border hover:border-primary/30'
      } ${hasBreakdown ? 'cursor-pointer' : ''}`}
  >
    <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"></div>
    <div className="flex items-center justify-between">
      <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/80 group-hover:text-foreground transition-colors truncate pr-2">{label}</span>
      <div className={`p-2 rounded-xl bg-muted group-hover:bg-primary/10 transition-colors`}>
        <Icon className={`w-4 h-4 shrink-0 ${color} transition-transform duration-300 group-hover:scale-110`} />
      </div>
    </div>
    <div className="flex items-baseline gap-1.5 relative z-10 w-full overflow-hidden mt-1">
      <span title={typeof value === 'string' ? value : undefined} className={`text-2xl md:text-3xl font-light tracking-tight truncate ${color}`}>{value}</span>
      {unit && <span className="text-xs font-semibold text-muted-foreground/60 shrink-0">{unit}</span>}
    </div>
    {hasBreakdown && (
      <div className={`absolute bottom-2 right-3 text-[10px] font-bold transition-colors ${active ? 'text-primary' : 'text-muted-foreground/40 group-hover:text-primary/70'}`}>View Details &rarr;</div>
    )}
  </div>
);

/* ── Tab Button ── */
const TabBtn = ({ active, label, icon: Icon, onClick }: any) => (
  <button onClick={onClick}
    className={`relative flex items-center gap-2 px-6 py-4 text-[13px] font-bold uppercase tracking-wider transition-all ${active
      ? 'text-primary bg-primary/5'
      : 'text-muted-foreground hover:text-foreground hover:bg-muted'
      }`}>
    <Icon className={`w-4 h-4 ${active ? 'text-primary' : 'text-muted-foreground/70'}`} />
    {label}
    {active && (
      <div className="absolute bottom-0 left-0 right-0 h-[3px] bg-primary rounded-t-full shadow-[0_-2px_12px_rgba(59,130,246,0.5)]" />
    )}
  </button>
);

const ECODCell = ({ edge }: { edge: any }) => {
  const scod = edge.scd;
  const ecod = edge.expectedDate;
  const status = (edge.normalizedStatus || edge.status || '').toLowerCase();
  const inProgress = status === 'in_progress' || status === 'in progress';
  
  let delayMonths = 0;
  if (inProgress && scod && ecod && scod !== '—' && ecod !== '—' && scod !== 'TBD' && ecod !== 'TBD') {
    const parse = (s: string) => {
      const parts = s.split('-');
      if (parts.length !== 2) return null;
      const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'].indexOf(parts[0]);
      if (m === -1) return null;
      let y = parseInt(parts[1]);
      if (y < 100) y += 2000;
      return new Date(y, m, 1);
    };
    const d1 = parse(scod);
    const d2 = parse(ecod);
    if (d1 && d2) {
      delayMonths = (d2.getFullYear() - d1.getFullYear()) * 12 + (d2.getMonth() - d1.getMonth());
    }
  }
  
  const isDelayed = delayMonths > 0 && inProgress;
  
  return (
    <td className="text-xs font-mono whitespace-nowrap">
      {isDelayed && <AlertTriangle className="w-3 h-3 text-destructive inline mr-1" />}
      <span className={isDelayed ? "text-destructive font-semibold" : ""}>
        {ecod || '—'} 
        {isDelayed && <span className="text-[10px] ml-1 bg-destructive/100/10 px-1.5 py-0.5 rounded-sm border border-destructive/20 text-destructive font-bold">+{delayMonths}m</span>}
      </span>
    </td>
  );
};

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

/* ── P6 Sync Editor Component ── */
const P6SyncEditor = ({ p6 }: { p6: any }) => {
  const [editMode, setEditMode] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [saveMsg, setSaveMsg] = React.useState<string | null>(null);
  const [editFields, setEditFields] = React.useState<Record<string, string>>({});

  const editableFields = [
    { key: 'start_date', label: 'Start Date', current: p6.startDate },
    { key: 'finish_date', label: 'Finish Date', current: p6.finishDate },
    { key: 'planned_start_date', label: 'Planned Start', current: p6.plannedStartDate },
    { key: 'scheduled_finish_date', label: 'Scheduled Finish', current: p6.scheduledFinishDate },
    { key: 'data_date', label: 'Data Date', current: p6.dataDate },
    { key: 'must_finish_by_date', label: 'Must Finish By', current: p6.mustFinishByDate },
    { key: 'baseline_start_date', label: 'Baseline Start', current: p6.baselineStartDate },
    { key: 'baseline_finish_date', label: 'Baseline Finish', current: p6.baselineFinishDate },
  ];

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const payload: Record<string, string> = {};
      for (const [k, v] of Object.entries(editFields)) {
        if (v && v.trim()) payload[k] = new Date(v).toISOString();
      }
      if (Object.keys(payload).length === 0) {
        setSaveMsg('No changes to save.');
        setSaving(false);
        return;
      }
      const res = await fetch(`/akasha/api/p6/projects/${encodeURIComponent(p6.projectId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await res.json();
      if (res.ok && result.success) {
        setSaveMsg('✓ Synced to P6 successfully');
        setEditMode(false);
        setEditFields({});
      } else {
        setSaveMsg(`⚠ ${result.detail || result.message || 'Sync failed'}`);
      }
    } catch (err) {
      setSaveMsg('⚠ Network error — could not reach P6.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="intelligence-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <RefreshCcw className="w-4 h-4 text-primary/70" /> 2-Way P6 Sync
          <span className="text-[9px] bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ml-2">Live</span>
        </h3>
        <div className="flex items-center gap-2">
          {saveMsg && (
            <span className={`text-xs font-medium ${saveMsg.startsWith('✓') ? 'text-success' : 'text-warning'}`}>{saveMsg}</span>
          )}
          {editMode ? (
            <>
              <button onClick={() => { setEditMode(false); setEditFields({}); setSaveMsg(null); }}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5 rounded-lg border border-border">Cancel</button>
              <button onClick={handleSave} disabled={saving}
                className="text-xs font-bold text-primary-foreground bg-primary hover:bg-primary/90 px-4 py-1.5 rounded-lg transition-all disabled:opacity-50 flex items-center gap-1.5">
                {saving && <Loader2 className="w-3 h-3 animate-spin" />}
                Push to P6
              </button>
            </>
          ) : (
            <button onClick={() => setEditMode(true)}
              className="text-xs font-bold text-primary bg-primary/10 hover:bg-primary/20 border border-primary/20 px-4 py-1.5 rounded-lg transition-all">
              Edit Dates
            </button>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {editableFields.map(f => (
          <div key={f.key} className="bg-muted border border-border rounded-lg p-3">
            <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground/50 mb-1.5">{f.label}</div>
            {editMode ? (
              <input type="date" defaultValue={f.current || ''}
                onChange={e => setEditFields(prev => ({ ...prev, [f.key]: e.target.value }))}
                className="w-full bg-background border border-border rounded px-2 py-1 text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary/40" />
            ) : (
              <div className="text-sm font-mono text-foreground/80">{f.current || '—'}</div>
            )}
          </div>
        ))}
      </div>
      <p className="text-[10px] text-muted-foreground/40 mt-3">Changes are pushed directly to Oracle Primavera P6 via the SOAP API.</p>
    </div>
  );
};

export default function ProjectWorkspace({ projectId: propProjectId, onBack }: { projectId?: string, onBack?: () => void }) {
  const params = useParams();
  const projectId = propProjectId || params.projectId;
  const navigate = useNavigate();
  const [project, setProject] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'schedule' | 'sap' | 'p6' | 'transmission' | 'quality'>('overview');
  const [diagnostic, setDiagnostic] = useState<any>(null);
  const [diagLoading, setDiagLoading] = useState(false);
  const [showDelayedModal, setShowDelayedModal] = useState(false);
  const [showCodModal, setShowCodModal] = useState<'done' | 'pending' | null>(null);
  const [sapFilter, setSapFilter] = useState<'all' | 'spv' | 'agel'>('all');
  const [inventoryFilter, setInventoryFilter] = useState<'ALL' | 'COMPANY' | 'PROJECT'>('ALL');
  const [expandedMaterial, setExpandedMaterial] = useState<string | null>(null);
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null);
  const [expandedTcMetric, setExpandedTcMetric] = useState<string | null>(null);
  const [actFilter, setActFilter] = useState<string>('All');
  const [expandedBlock, setExpandedBlock] = useState<string | null>(null);
  const [expandedCat, setExpandedCat] = useState<string | null>(null);
  const [showWorkflowModal, setShowWorkflowModal] = useState(false);
  const [syncingP6, setSyncingP6] = useState(false);

  useEffect(() => {
    setActiveTab('overview');
  }, [projectId]);

  useEffect(() => {
    const fetchProject = async () => {
      try {
        const json = await getCachedDashboardJson<any[]>("/akasha/api/project-360");
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
        const json = await getCachedDashboardJson<any>(`/akasha/api/project-360/${encodeURIComponent(projectId || '')}/detail`);
        setDetail(json);
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
          wbsElements: new Set<string>(),
          baseUnit: '—'
        };
      } else if (cleanDesc !== '—') {
        if (matMap[code].materialDescription === '—' || cleanDesc.length > matMap[code].materialDescription.length) {
          matMap[code].materialDescription = cleanDesc;
        }
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
      if (c.baseUnit && c.baseUnit !== 'nan') m.baseUnit = c.baseUnit;
      if (c.wbsElement && c.wbsElement.trim() && c.wbsElement !== 'nan') m.wbsElements.add(c.wbsElement);
      if (c.blockPlotName && c.blockPlotName.trim() && c.blockPlotName !== 'nan') m.wbsElements.add(c.blockPlotName);
    });

    // 3. Inventory
    (filteredSap.inventory || []).forEach((inv: any) => {
      if (inventoryFilter === 'COMPANY' && inv.storageLocation !== 'CS01') return;
      if (inventoryFilter === 'PROJECT' && inv.storageLocation !== 'PS01') return;
      const code = inv.materialCode;
      if (!code) return;
      initMat(code, inv.materialName || '—');
      const m = matMap[code];
      m.inventoryQty += Number(inv.inventoryQty || 0);
      m.inventoryValueINR += Number(inv.inventoryValueINR || 0);
      m.inventories.push(inv);
      if (inv.baseUnit && inv.baseUnit !== 'nan' && m.baseUnit === '—') m.baseUnit = inv.baseUnit;
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
      m.remainingBalanceINR = m.budgetINR - m.consumedAmountINR;
      m.wbsList = Array.from(m.wbsElements).filter(Boolean);
      return m;
    });

    return result.sort((a: any, b: any) => b.orderedQty - a.orderedQty);
  }, [filteredSap, inventoryFilter]);

  const unifiedMaterialsMap = useMemo(() => {
    const map: Record<string, any> = {};
    unifiedMaterials.forEach((m: any) => {
      map[m.materialCode] = m;
    });
    return map;
  }, [unifiedMaterials]);

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
          <AlertTriangle className="w-12 h-12 text-warning/50 mx-auto mb-4" />
          <p className="text-muted-foreground">Project not found.</p>
          <button onClick={() => navigate('/ceo-dashboard')} className="mt-4 text-primary text-sm hover:underline">
            ← Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const p = project;
  const progressPct = p.progress < 1 ? p.progress * 100 : p.progress;
  const tier = p.statusTier || p.health;
  const healthColor = tier === 'Critical' ? 'text-destructive' : (tier === 'High Risk' || tier === 'Watchlist') ? 'text-warning' : 'text-success';
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
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e2e8f0', textStyle: { color: '#0f172a', fontSize: 11 } },
    grid: { left: '3%', right: '4%', bottom: '5%', top: '8%', containLabel: true },
    xAxis: { type: 'category', data: supplyData.map(s => s.name), axisLine: { lineStyle: { color: '#e2e8f0' } }, axisLabel: { color: '#64748b', fontSize: 10, fontWeight: 'bold' } },
    yAxis: { type: 'value', name: 'No', nameTextStyle: { fontSize: 10, color: '#64748b', fontWeight: 'bold' }, axisLine: { show: false }, axisLabel: { color: '#64748b', fontSize: 10 }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    series: [{ type: 'bar', data: supplyData.map(s => ({ value: s.value, itemStyle: { color: s.color, borderRadius: [4, 4, 0, 0] } })), barWidth: '35%' }]
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
    legend: { data: ['PO Count', 'Net Value (INR)'], bottom: 0, textStyle: { fontSize: 10, color: '#64748b' } },
    grid: { left: '3%', right: '8%', bottom: '15%', top: '8%', containLabel: true },
    xAxis: {
      type: 'category',
      data: (sap.vendorBreakdown.slice(0, 8)).map((v: any) => v.vendorName?.substring(0, 22) || 'Unknown'),
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#64748b', fontSize: 10, rotate: 15 }
    },
    yAxis: [
      { type: 'value', name: 'No', axisLine: { show: false }, axisLabel: { color: '#64748b', fontSize: 10 }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
      { type: 'value', name: 'Value', position: 'right', axisLine: { show: false }, axisLabel: { color: '#64748b', fontSize: 10, formatter: (v: number) => `₹${(v / 100000).toFixed(0)}L` }, splitLine: { show: false } }
    ],
    series: [
      {
        name: 'PO Count',
        type: 'bar',
        data: (sap.vendorBreakdown.slice(0, 8)).map((v: any) => v.poCount),
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
          <button onClick={() => onBack ? onBack() : navigate('/ceo-dashboard')}
            className="flex items-center gap-2 text-sm text-muted-foreground/70 hover:text-foreground transition-colors group">
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
            Back to Portfolio
          </button>
          <div className="h-5 w-px bg-muted"></div>
          <div className="flex items-center gap-2">
            <div className={dotClass}></div>
            <span className="text-sm font-semibold text-foreground truncate max-w-[400px]">{p.projectName}</span>
          </div>
          <div className="ml-auto flex items-center gap-4">
            <span className="text-[10px] font-mono text-muted-foreground/40">{p.projectId}</span>
            {detail?.p6?.p6ObjectId && (
              <button
                onClick={async () => {
                  setSyncingP6(true);
                  try {
                    const p6Promise = fetch(`/akasha/api/p6/sync/${detail.p6.p6ObjectId}`, { method: 'POST' });
                    const tcPromise = fetch(`/akasha/api/tc/sync`, { method: 'POST' });
                    
                    const [p6Res, tcRes] = await Promise.all([p6Promise, tcPromise]);
                    
                    if (p6Res.ok || tcRes.ok) {
                      window.location.reload();
                    }
                  } catch (e) {
                    console.error(e);
                  } finally {
                    setSyncingP6(false);
                  }
                }}
                disabled={syncingP6}
                title="Pull latest data from P6 and Transmission Portal for this project"
                className="flex items-center gap-2 text-[11px] font-bold text-primary bg-primary/10 hover:bg-primary/20 border border-primary/20 px-3 py-1.5 rounded-lg transition-all disabled:opacity-50"
              >
                {syncingP6 ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCcw className="w-3 h-3" />}
                Sync P6 & TC
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">
        {/* ── Hero Section ── */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
          <HeroMetric label="Progress" value={`${Math.round(progressPct)}%`} icon={Activity} color={healthColor} />
          <HeroMetric label="Supply PO Amount" value={detail?.sap?.summary?.totalBudgetINR ? `₹${(detail.sap.summary.totalBudgetINR / 10000000).toFixed(1)}` : '₹0'} unit="Cr" icon={Database} color="text-primary" />
          
          <HeroMetric 
            label={`COD Done (${detail?.mapping?.unitType || 'Units'})`} 
            value={detail?.mapping?.codBlocksDone || 0} 
            icon={CheckCircle2} 
            color="text-success" 
            hasBreakdown={(detail?.mapping?.codBlocksDone || 0) > 0} 
            onClick={() => (detail?.mapping?.codBlocksDone || 0) > 0 && setShowCodModal('done')} 
            active={showCodModal === 'done'} 
          />
          <HeroMetric label="MW Generated" value={detail?.mapping?.mwGenerated || 0} unit="MW" icon={Zap} color="text-primary" />
          <HeroMetric 
            label="Pending COD" 
            value={detail?.mapping?.pendingCodBlocks || 0} 
            icon={AlertTriangle} 
            color="text-warning" 
            hasBreakdown={(detail?.mapping?.pendingCodBlocks || 0) > 0} 
            onClick={() => (detail?.mapping?.pendingCodBlocks || 0) > 0 && setShowCodModal('pending')} 
            active={showCodModal === 'pending'} 
          />
          
          <HeroMetric label="Schedule Variance" value={`${p.scheduleVariance > 0 ? '+' : ''}${p.scheduleVariance}`} unit="days" icon={Clock} color={p.scheduleVariance < -10 ? 'text-destructive' : 'text-foreground/80'} hasBreakdown={(detail?.p6?.delayedActivities?.length || 0) > 0} onClick={() => (detail?.p6?.delayedActivities?.length || 0) > 0 && setShowDelayedModal(true)} active={showDelayedModal} />
          <HeroMetric label="Forecast COD" value={p.forecastFinish || p.forecastMonth} icon={Calendar} color="text-primary" />
          {((detail?.tc?.summary?.totalKhavdaEdges || 0) + (detail?.tc?.summary?.totalRajasthanEdges || 0)) > 0 && (
            <HeroMetric label="Transmission Lines" value={(detail?.tc?.summary?.totalKhavdaEdges || 0) + (detail?.tc?.summary?.totalRajasthanEdges || 0)} icon={MapPin} color="text-primary" />
          )}
          {(detail?.tc?.summary?.totalNodes || 0) > 0 && (
            <HeroMetric label="Substations" value={detail?.tc?.summary?.totalNodes || 0} icon={Zap} color="text-warning" />
          )}
          <HeroMetric label="Baseline COD" value={p6?.baselineFinishDate || 'Not Set'} icon={CalendarClock} color="text-teal-500 dark:text-teal-400" />
        </div>

        {/* ── AI Project Summary ── */}
        <div className="intelligence-card p-6 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-72 h-72 bg-primary/[0.03] blur-[100px] rounded-full pointer-events-none"></div>

          <div className="flex items-start gap-4 mb-4 relative z-10">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary/20 to-purple-600/20 flex items-center justify-center shrink-0 border border-primary/10">
              <BarChart3 className="w-5 h-5 text-primary/80" />
            </div>
            <div className="flex-1">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                Project Insights
              </h3>
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
                    <span className="text-sm text-muted-foreground/60 animate-pulse">Analyzing project data...</span>
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
                  <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-lg ${p.keyIssue === 'On Track' ? 'bg-success/100/10 text-success border border-success/20' : 'bg-destructive/100/10 text-destructive border border-destructive/20'
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
                  <Activity className="w-4 h-4" />
                  Run Scenario Analysis
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ── Tab Navigation ── */}
        <div className="flex items-center gap-2 border-b border-border bg-slate-100/50 dark:bg-gray-900/50 backdrop-blur-sm px-4 overflow-x-auto scrollbar-hide">
          <TabBtn active={activeTab === 'overview'} label="Overview" icon={BarChart3} onClick={() => setActiveTab('overview')} />
          <TabBtn active={activeTab === 'schedule'} label="Schedule" icon={Calendar} onClick={() => setActiveTab('schedule')} />
          <TabBtn active={activeTab === 'sap'} label="SAP Intelligence" icon={Database} onClick={() => setActiveTab('sap')} />
          <TabBtn active={activeTab === 'p6'} label="P6 Deep Dive" icon={Layers} onClick={() => setActiveTab('p6')} />
          <TabBtn active={activeTab === 'transmission'} label="Transmission" icon={Network} onClick={() => setActiveTab('transmission')} />
          <TabBtn active={activeTab === 'quality'} label="Quality" icon={Shield} onClick={() => setActiveTab('quality')} />
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
                        <div className="w-3 h-3 rounded-sm bg-success/100 shadow-[0_0_8px_rgba(16,185,129,0.4)]"></div>
                        <span className="text-foreground/80 font-medium group-hover:text-foreground transition-colors">Completed</span>
                      </div>
                      <span className="font-mono font-bold text-foreground">{p.completedActivities}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm group">
                      <div className="flex items-center gap-3">
                        <div className="w-3 h-3 rounded-sm bg-primary/100 shadow-[0_0_8px_rgba(59,130,246,0.4)]"></div>
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
                    <div key={label} className="bg-muted border border-border rounded-lg p-3 hover:bg-muted transition-colors">
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
              {/* Right Column: Timeline & Variance */}
              <div className="lg:col-span-12 flex flex-col gap-6">
                <div className="intelligence-card p-6">
                  <h4 className="text-xs font-bold uppercase tracking-widest text-foreground mb-6 flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-primary" /> Schedule Timeline
                  </h4>

                  <div className="relative pl-4 border-l-2 border-border space-y-6">
                    {[
                      { icon: Flag, color: 'text-success', bg: 'bg-success/100/10', border: 'border-success/20', label: 'Project Start', value: p.startDate || '—', desc: 'Official commencement' },
                      { icon: Activity, color: 'text-primary', bg: 'bg-primary/100/10', border: 'border-primary/20', label: 'Data Date', value: p6?.dataDate || '—', desc: 'Latest schedule update' },
                      { icon: Target, color: 'text-warning', bg: 'bg-warning/100/10', border: 'border-warning/20', label: 'Baseline Finish', value: p.baselineFinishDate || '—', desc: 'Original target' },
                      { icon: CalendarClock, color: 'text-destructive', bg: 'bg-destructive/100/10', border: 'border-destructive/20', label: 'Forecast Finish', value: p.forecastFinish, desc: 'Current projection' },
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
                  <div className="intelligence-card p-4 flex items-center justify-between bg-muted">
                    <div>
                      <span className="block text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Schedule Variance</span>
                      <span className={`block text-xl font-bold mt-1 ${p.scheduleVariance < 0 ? 'text-destructive' : 'text-success'}`}>
                        {p.scheduleVariance} days
                      </span>
                    </div>
                    <AlertTriangle className={`w-8 h-8 opacity-20 ${p.scheduleVariance < 0 ? 'text-destructive' : 'text-success'}`} />
                  </div>
                  <div className="intelligence-card p-4 flex items-center justify-between bg-muted">
                    <div>
                      <span className="block text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Must Finish By</span>
                      <span className="block text-lg font-mono font-bold text-foreground mt-1">{p6?.mustFinishByDate || 'Not Set'}</span>
                    </div>
                    <Target className="w-8 h-8 text-primary opacity-20" />
                  </div>

                  {p6?.delayedActivities && p6.delayedActivities.length > 0 && (
                    <div
                      onClick={() => setShowDelayedModal(true)}
                      className="intelligence-card p-4 flex items-center justify-between bg-destructive/100/10 border-destructive/20 cursor-pointer hover:bg-destructive/100/20 transition-colors"
                    >
                      <div>
                        <span className="block text-[10px] font-bold uppercase tracking-wider text-destructive">Delayed Activities</span>
                        <span className="block text-2xl font-mono font-bold text-destructive mt-1">{p6.delayedActivities.length}</span>
                        <span className="block text-xs text-destructive/80 mt-1 underline decoration-red-500/30 underline-offset-2">View details</span>
                      </div>
                      <AlertTriangle className="w-10 h-10 text-destructive opacity-80" />
                    </div>
                  )}
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
                      <div className="flex items-center bg-muted border border-border rounded-lg p-0.5">
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
                            className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-md transition-all ${opt.disabled
                              ? 'opacity-40 cursor-not-allowed border border-dashed border-muted-foreground/30 text-muted-foreground'
                              : sapFilter === opt.key
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
                        <HeroMetric label="Total POs" value={sap.summary.totalPOs} icon={FileText} color="text-primary dark:text-primary" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'pos' ? null : 'pos')} active={expandedMetric === 'pos'} />
                        <HeroMetric label="Vendors" value={sap.summary.totalVendors} icon={Users} color="text-purple-500 dark:text-purple-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'vendors' ? null : 'vendors')} active={expandedMetric === 'vendors'} />
                        <HeroMetric label="Materials" value={unifiedMaterials.length} icon={Layers} color="text-primary dark:text-primary" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'materials' ? null : 'materials')} active={expandedMetric === 'materials'} />
                        <HeroMetric label="PO Volume" value={fmtMW(sap.summary.totalOrderedQty)} unit="No" icon={Package} color="text-primary dark:text-primary" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'volume' ? null : 'volume')} active={expandedMetric === 'volume'} />
                        <HeroMetric label="Inventory" value={fmtMW(sap.summary.totalInventoryQty)} unit="No" icon={Box} color="text-success dark:text-success" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'inventory' ? null : 'inventory')} active={expandedMetric === 'inventory'} />

                        <HeroMetric label="Supply PO Amount" value={fmtCost(sap.summary.totalBudgetINR)} icon={DollarSign} color="text-pink-500 dark:text-pink-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'budget' ? null : 'budget')} active={expandedMetric === 'budget'} />
                        <HeroMetric label="Utilized Supply PO Amount" value={fmtCost(sap.summary.totalExpenditureINR)} icon={Activity} color="text-warning dark:text-warning" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'utilized' ? null : 'utilized')} active={expandedMetric === 'utilized'} />
                        <HeroMetric label="Remaining Supply PO Amount" value={fmtCost((sap.summary.totalBudgetINR || 0) - (sap.summary.totalExpenditureINR || 0))} icon={Target} color="text-teal-500 dark:text-teal-400" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'remaining' ? null : 'remaining')} active={expandedMetric === 'remaining'} />
                        <HeroMetric label="% Consumed" value={`${sap.summary.totalBudgetINR ? ((sap.summary.totalExpenditureINR / sap.summary.totalBudgetINR) * 100).toFixed(1) : '0'}%`} icon={BarChart3} color={sap.summary.totalBudgetINR && (sap.summary.totalExpenditureINR / sap.summary.totalBudgetINR) > 0.9 ? 'text-destructive dark:text-destructive' : 'text-success dark:text-success'} />
                        <HeroMetric label="In Transit" value={fmtMW(sap.summary.totalInTransitQty)} unit="No" icon={Truck} color="text-warning dark:text-warning" hasBreakdown onClick={() => setExpandedMetric(expandedMetric === 'transit' ? null : 'transit')} active={expandedMetric === 'transit'} />
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
                            <button onClick={() => setExpandedMetric(null)} className="text-muted-foreground hover:text-foreground text-xs px-2 py-1 rounded hover:bg-muted transition-colors">✕ Close</button>
                          </div>
                          <div className="overflow-x-auto max-h-[350px] overflow-y-auto scrollbar-thin">
                            <table className="intel-table w-full text-xs">
                              <thead className="sticky top-0 bg-slate-50/95 dark:bg-gray-900/95 backdrop-blur-sm z-10 text-[10px] uppercase tracking-wider">
                                {/* ── PO Breakdown ── */}
                                {expandedMetric === 'pos' && (
                                  <tr>
                                    <th className="text-left">PO Number</th>
                                    <th className="text-left">Material Description</th>
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
                                    <th className="text-right">Supply PO Amount (INR)</th>
                                  </tr>
                                )}
                                {/* ── Material Type Breakdown ── */}
                                {expandedMetric === 'materials' && (
                                  <tr>
                                    <th className="text-left">Material Code</th>
                                    <th className="text-left">Material Description</th>
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
                                    <th className="text-left">Material Description</th>
                                    <th className="text-right">Ordered Qty</th>
                                    <th className="text-right">% of Total</th>
                                    <th className="text-left">Distribution</th>
                                  </tr>
                                )}
                                {/* ── Inventory Breakdown ── */}
                                {expandedMetric === 'inventory' && (
                                  <tr>
                                    <th className="text-left">Material Code</th>
                                    <th className="text-left">Material Description</th>
                                    <th className="text-right">Inventory Qty</th>
                                    <th className="text-right">Inventory Value (INR)</th>
                                    <th className="text-center">Storage Location</th>
                                  </tr>
                                )}
                                {/* ── Budget / Utilized / Remaining ── */}
                                {(expandedMetric === 'budget' || expandedMetric === 'utilized' || expandedMetric === 'remaining') && (
                                  <tr>
                                    <th className="text-left">Material Code</th>
                                    <th className="text-left">Material Description</th>
                                    <th className="text-right">Supply PO Amount</th>
                                    <th className="text-right">Consumed Amt</th>
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
                                  <tr key={i} className="hover:bg-muted transition-colors">
                                    <td className="text-left font-mono font-medium text-primary/80">{po.poNumber}</td>
                                    <td className="text-left text-foreground/70 max-w-[150px] truncate" title={po.materialName}>{po.materialName || po.materialCode}</td>
                                    <td className="text-left text-foreground/70 max-w-[150px] truncate" title={po.vendorName}>{po.vendorName || '—'}</td>
                                    <td className="text-right font-mono font-semibold text-primary">{Number(po.orderedQty || 0).toLocaleString('en-IN')} {unifiedMaterialsMap[po.materialCode]?.baseUnit && unifiedMaterialsMap[po.materialCode]?.baseUnit !== '—' && <span className="text-[10px] text-muted-foreground ml-1">{unifiedMaterialsMap[po.materialCode].baseUnit}</span>}</td>
                                    <td className="text-right font-mono text-foreground/70">{fmtCost(po.budgetINR)}</td>
                                    <td className="text-right font-mono text-success">{fmtCost(po.deliveredINR)}</td>
                                    <td className="text-center"><span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${po.storageLocation === 'CS01' ? 'bg-primary/100/10 text-primary' : 'bg-purple-500/10 text-purple-500'}`}>{po.storageLocation || '—'}</span></td>
                                  </tr>
                                ))}
                                {/* ── Vendor Rows ── */}
                                {expandedMetric === 'vendors' && (sap.vendorBreakdown || []).map((v: any, i: number) => (
                                  <tr key={i} className="hover:bg-muted transition-colors">
                                    <td className="text-left font-medium text-foreground/80 max-w-[200px] truncate" title={v.vendorName}>{v.vendorName}</td>
                                    <td className="text-center font-mono font-semibold text-primary">{v.poCount}</td>
                                    <td className="text-center font-mono text-purple-400">{v.materialCount}</td>
                                    <td className="text-right font-mono font-semibold text-foreground">{Number(v.totalOrderedQty || 0).toLocaleString('en-IN')}</td>
                                    <td className="text-right font-mono text-pink-400">{fmtCost(v.totalBudgetINR)}</td>
                                  </tr>
                                ))}
                                {/* ── Materials Rows ── */}
                                {expandedMetric === 'materials' && unifiedMaterials.slice(0, 50).map((mat: any, i: number) => (
                                  <tr key={i} className="hover:bg-muted transition-colors">
                                    <td className="text-left font-mono text-primary/80">{mat.materialCode}</td>
                                    <td className="text-left text-foreground/70 max-w-[180px] truncate" title={mat.materialDescription}>{mat.materialDescription}</td>
                                    <td className="text-right font-mono text-primary">{mat.orderedQty ? <>{Number(mat.orderedQty).toLocaleString('en-IN')} {mat.baseUnit !== '—' && <span className="text-[10px] text-muted-foreground ml-1">{mat.baseUnit}</span>}</> : '—'}</td>
                                    <td className="text-right font-mono text-success">{mat.consumedQty ? <>{Number(mat.consumedQty).toLocaleString('en-IN')} {mat.baseUnit !== '—' && <span className="text-[10px] text-muted-foreground ml-1">{mat.baseUnit}</span>}</> : '—'}</td>
                                    <td className="text-right font-mono text-purple-400">{mat.inventoryQty ? <>{Number(mat.inventoryQty).toLocaleString('en-IN')} {mat.baseUnit !== '—' && <span className="text-[10px] text-muted-foreground ml-1">{mat.baseUnit}</span>}</> : '—'}</td>
                                    <td className="text-right font-mono text-warning">{mat.inTransitQty ? <>{Number(mat.inTransitQty).toLocaleString('en-IN')} {mat.baseUnit !== '—' && <span className="text-[10px] text-muted-foreground ml-1">{mat.baseUnit}</span>}</> : '—'}</td>
                                  </tr>
                                ))}
                                {/* ── Volume Rows ── */}
                                {expandedMetric === 'volume' && unifiedMaterials.filter((m: any) => m.orderedQty > 0).slice(0, 30).map((mat: any, i: number) => {
                                  const pct = sap.summary.totalOrderedQty ? (mat.orderedQty / sap.summary.totalOrderedQty) * 100 : 0;
                                  return (
                                    <tr key={i} className="hover:bg-muted transition-colors">
                                      <td className="text-left font-mono text-primary/80">{mat.materialCode}</td>
                                      <td className="text-left text-foreground/70 max-w-[150px] truncate" title={mat.materialDescription}>{mat.materialDescription}</td>
                                      <td className="text-right font-mono font-semibold text-primary">{Number(mat.orderedQty).toLocaleString('en-IN')} {mat.baseUnit !== '—' && <span className="text-[10px] text-muted-foreground ml-1">{mat.baseUnit}</span>}</td>
                                      <td className="text-right font-mono text-foreground/60">{pct.toFixed(1)}%</td>
                                      <td className="text-left"><div className="w-full h-2 bg-muted rounded-full overflow-hidden"><div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400" style={{ width: `${Math.min(pct, 100)}%` }}></div></div></td>
                                    </tr>
                                  );
                                })}
                                {/* ── Inventory Rows ── */}
                                {expandedMetric === 'inventory' && (sap.inventory || []).filter((inv: any) => (inv.inventoryQty || 0) > 0).slice(0, 50).map((inv: any, i: number) => (
                                  <tr key={i} className="hover:bg-muted transition-colors">
                                    <td className="text-left font-mono text-primary/80">{inv.materialCode}</td>
                                    <td className="text-left text-foreground/70 max-w-[150px] truncate">{inv.materialName || '—'}</td>
                                    <td className="text-right font-mono font-semibold text-success">{Number(inv.inventoryQty || 0).toLocaleString('en-IN')} {inv.baseUnit && inv.baseUnit !== '—' ? <span className="text-[10px] text-muted-foreground ml-1">{inv.baseUnit}</span> : unifiedMaterialsMap[inv.materialCode]?.baseUnit && unifiedMaterialsMap[inv.materialCode]?.baseUnit !== '—' ? <span className="text-[10px] text-muted-foreground ml-1">{unifiedMaterialsMap[inv.materialCode].baseUnit}</span> : null}</td>
                                    <td className="text-right font-mono text-purple-400">{inv.inventoryValueINR ? `₹${Number(inv.inventoryValueINR).toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'}</td>
                                    <td className="text-center"><span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${inv.storageLocation === 'CS01' ? 'bg-primary/100/10 text-primary' : 'bg-purple-500/10 text-purple-500'}`}>{inv.storageLocation || '—'}</span></td>
                                  </tr>
                                ))}
                                {/* ── Budget / Utilized / Remaining Rows ── */}
                                {(expandedMetric === 'budget' || expandedMetric === 'utilized' || expandedMetric === 'remaining') && unifiedMaterials.filter((m: any) => expandedMetric === 'budget' ? m.budgetINR > 0 : expandedMetric === 'utilized' ? m.consumedAmountINR > 0 : m.remainingBalanceINR !== 0).sort((a: any, b: any) => {
                                  if (expandedMetric === 'utilized') return b.consumedAmountINR - a.consumedAmountINR;
                                  if (expandedMetric === 'remaining') return b.remainingBalanceINR - a.remainingBalanceINR;
                                  return b.budgetINR - a.budgetINR;
                                }).slice(0, 50).map((mat: any, i: number) => {
                                  const utilPct = mat.budgetINR ? (mat.consumedAmountINR / mat.budgetINR) * 100 : 0;
                                  return (
                                    <tr key={i} className="hover:bg-muted transition-colors">
                                      <td className="text-left font-mono text-primary/80">{mat.materialCode}</td>
                                      <td className="text-left text-foreground/70 max-w-[150px] truncate" title={mat.materialDescription}>{mat.materialDescription}</td>
                                      <td className="text-right font-mono text-pink-400">{fmtCost(mat.budgetINR)}</td>
                                      <td className="text-right font-mono text-warning">{fmtCost(mat.consumedAmountINR)}</td>
                                      <td className="text-right font-mono text-teal-400">{fmtCost(mat.remainingBalanceINR)}</td>
                                      <td className="text-left">
                                        <div className="flex items-center gap-2">
                                          <div className="w-16 h-2 bg-muted rounded-full overflow-hidden"><div className={`h-full rounded-full ${utilPct > 90 ? 'bg-destructive/100' : utilPct > 60 ? 'bg-warning/100' : 'bg-success/100'}`} style={{ width: `${Math.min(utilPct, 100)}%` }}></div></div>
                                          <span className={`text-[10px] font-mono font-bold ${utilPct > 90 ? 'text-destructive' : utilPct > 60 ? 'text-warning' : 'text-success'}`}>{utilPct.toFixed(0)}%</span>
                                        </div>
                                      </td>
                                    </tr>
                                  );
                                })}
                                {/* ── Transit Rows ── */}
                                {expandedMetric === 'transit' && (sap.inTransit || []).filter((t: any) => (t.inTransitQty || 0) > 0).slice(0, 50).map((t: any, i: number) => (
                                  <tr key={i} className="hover:bg-muted transition-colors">
                                    <td className="text-left font-mono text-primary/80">{t.materialCode}</td>
                                    <td className="text-left text-foreground/70 max-w-[150px] truncate" title={t.vendorName}>{t.vendorName || '—'}</td>
                                    <td className="text-right font-mono font-semibold text-warning">{Number(t.inTransitQty || 0).toLocaleString('en-IN')} {unifiedMaterialsMap[t.materialCode]?.baseUnit && unifiedMaterialsMap[t.materialCode]?.baseUnit !== '—' && <span className="text-[10px] text-muted-foreground ml-1">{unifiedMaterialsMap[t.materialCode].baseUnit}</span>}</td>
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
                              <span className="font-mono font-bold text-success">{fmtMW(sap.summary.totalInventoryQty)}</span>
                            </div>
                          )}
                          {expandedMetric === 'transit' && (
                            <div className="mt-3 pt-3 border-t border-border/30 flex items-center gap-6 text-xs">
                              <span className="text-muted-foreground">Total In-Transit Qty:</span>
                              <span className="font-mono font-bold text-warning">{fmtMW(sap.summary.totalInTransitQty)}</span>
                              <span className="text-muted-foreground ml-4">Unique Materials in Transit:</span>
                              <span className="font-mono font-bold text-warning">{new Set((sap.inTransit || []).map((t: any) => t.materialCode)).size}</span>
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
                              <div className="h-full w-full flex flex-col items-center justify-center border border-dashed border-border/40 rounded-xl bg-muted">
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
                            <div className="flex bg-muted p-1 rounded-md border border-border">
                              <button onClick={() => setInventoryFilter('ALL')} className={`px-3 py-1 text-xs font-medium rounded-sm transition-all ${inventoryFilter === 'ALL' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-muted'}`}>All Stock</button>
                              <button onClick={() => setInventoryFilter('COMPANY')} className={`px-3 py-1 text-xs font-medium rounded-sm transition-all ${inventoryFilter === 'COMPANY' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-muted'}`}>Company (CS01)</button>
                              <button onClick={() => setInventoryFilter('PROJECT')} className={`px-3 py-1 text-xs font-medium rounded-sm transition-all ${inventoryFilter === 'PROJECT' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-muted'}`}>Project (PS01)</button>
                            </div>
                          </div>

                          <div className="overflow-x-auto max-h-[600px] overflow-y-auto scrollbar-thin">
                            <table className="intel-table relative w-full text-xs">
                              <thead className="sticky top-0 bg-slate-50/95 dark:bg-gray-900/95 backdrop-blur-sm z-10 shadow-sm text-[10px] uppercase tracking-wider whitespace-nowrap">
                                <tr>
                                  <th className="w-8"></th>
                                  <th className="text-center">Material Code</th>
                                  <th className="text-left">Material Description</th>
                                  <th className="text-center">Base Unit</th>
                                  <th className="text-left">WBS Tracking</th>
                                  <th className="text-center">Ordered</th>
                                  <th className="text-center">Consumed</th>
                                  <th className="text-center">Remaining Qty</th>
                                  <th className="text-center">Inventory Qty</th>
                                  <th className="text-center">Inventory Value</th>
                                  <th className="text-center">In Transit</th>
                                  <th className="text-center">Supply PO Amount</th>
                                  <th className="text-center">Utilized Supply PO Amount</th>
                                  <th className="text-center">Remaining Supply PO Amount</th>
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
                                        <td className="text-center font-mono text-muted-foreground/80">{mat.baseUnit}</td>
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
                                        <td className="text-center font-mono font-semibold text-primary">{mat.orderedQty ? Number(mat.orderedQty).toLocaleString('en-IN') : '—'}</td>
                                        <td className="text-center font-mono font-semibold text-success">{mat.consumedQty ? Number(mat.consumedQty).toLocaleString('en-IN') : '—'}</td>
                                        <td className="text-center font-mono font-semibold text-warning">{mat.remainingQty ? Number(mat.remainingQty).toLocaleString('en-IN') : '—'}</td>
                                        <td className="text-center font-mono text-purple-400">{mat.inventoryQty ? Number(mat.inventoryQty).toLocaleString('en-IN') : '—'}</td>
                                        <td className="text-center font-mono text-purple-400/80">{mat.inventoryValueINR ? `₹${Number(mat.inventoryValueINR).toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'}</td>
                                        <td className="text-center font-mono text-warning">{mat.inTransitQty ? Number(mat.inTransitQty).toLocaleString('en-IN') : '—'}</td>
                                        <td className="text-center font-mono text-foreground/70">{mat.budgetINR ? `₹${Number(mat.budgetINR).toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'}</td>
                                        <td className="text-center font-mono text-success/80">{mat.deliveredINR ? `₹${Number(mat.deliveredINR).toLocaleString('en-IN')}` : '—'}</td>
                                        <td className="text-center font-mono text-warning/80">{mat.remainingBalanceINR ? `₹${Number(mat.remainingBalanceINR).toLocaleString('en-IN')}` : '—'}</td>
                                      </tr>

                                      {/* Drill-down Detail Row */}
                                      {isExpanded && (
                                        <tr className="bg-muted border-b border-border">
                                          <td colSpan={12} className="p-0">
                                            <div className="p-6 space-y-6">

                                              {/* PO Details */}
                                              {mat.pos.length > 0 && (
                                                <div>
                                                  <h4 className="text-xs uppercase text-muted-foreground mb-3 font-semibold tracking-wider flex items-center gap-2"><FileText className="w-3.5 h-3.5" /> Purchase Orders</h4>
                                                  <div className="rounded-md border border-border bg-background/50 overflow-hidden shadow-sm">
                                                    <table className="intel-table w-full text-xs">
                                                      <thead className="bg-muted text-[10px] text-muted-foreground uppercase tracking-wider">
                                                        <tr>
                                                          <th className="text-left font-semibold py-2 px-4">PO Number</th>
                                                          <th className="text-right font-semibold py-2 px-4">Ordered Qty</th>
                                                          <th className="text-center font-semibold py-2 px-4 w-32">Storage Location</th>
                                                        </tr>
                                                      </thead>
                                                      <tbody className="divide-y divide-border/30">
                                                        {mat.pos.map((po: any, j: number) => (
                                                          <tr key={j} className="hover:bg-muted transition-colors">
                                                            <td className="text-left font-mono font-medium text-foreground py-2 px-4">{po.poNumber}</td>
                                                            <td className="text-right font-mono font-semibold text-primary dark:text-primary py-2 px-4">{po.orderedQty} Unit</td>
                                                            <td className="text-center py-2 px-4">
                                                              <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${po.storageLocation === 'CS01' ? 'bg-primary/100/10 text-primary dark:text-primary' : 'bg-purple-500/10 text-purple-600 dark:text-purple-400'}`}>{po.storageLocation || '—'}</span>
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
                                                  <h4 className="text-xs uppercase text-muted-foreground mb-3 font-semibold tracking-wider flex items-center gap-2"><Activity className="w-3.5 h-3.5" /> Consumptions</h4>
                                                  <div className="rounded-md border border-border bg-background/50 overflow-hidden shadow-sm">
                                                    <table className="intel-table w-full text-xs">
                                                      <thead className="bg-muted text-[10px] text-muted-foreground uppercase tracking-wider">
                                                        <tr>
                                                          <th className="text-center font-semibold py-2 px-4 w-24">Movement</th>
                                                          <th className="text-left font-semibold py-2 px-4">WBS Element / Date</th>
                                                          <th className="text-right font-semibold py-2 px-4">Quantity</th>
                                                        </tr>
                                                      </thead>
                                                      <tbody className="divide-y divide-border/30">
                                                        {mat.consumptions.slice(0, 50).map((c: any, j: number) => (
                                                          <tr key={j} className="hover:bg-muted transition-colors">
                                                            <td className="text-center py-2 px-4">
                                                              <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${String(c.movementType) === '221' ? 'bg-success/100/10 text-success dark:text-success' : 'bg-destructive/100/10 text-destructive dark:text-destructive'}`}>{c.movementType}</span>
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
                                                  <h4 className="text-xs uppercase text-muted-foreground mb-3 font-semibold tracking-wider flex items-center gap-2"><Package className="w-3.5 h-3.5" /> Inventory Storage</h4>
                                                  <div className="rounded-md border border-border bg-background/50 overflow-hidden shadow-sm">
                                                    <table className="intel-table w-full text-xs">
                                                      <thead className="bg-muted text-[10px] text-muted-foreground uppercase tracking-wider">
                                                        <tr>
                                                          <th className="text-left font-semibold py-2 px-4">WBS Element</th>
                                                          <th className="text-right font-semibold py-2 px-4">Inventory Qty</th>
                                                          <th className="text-right font-semibold py-2 px-4">Value (INR)</th>
                                                          <th className="text-center font-semibold py-2 px-4 w-32">Storage Location</th>
                                                        </tr>
                                                      </thead>
                                                      <tbody className="divide-y divide-border/30">
                                                        {mat.inventories.map((inv: any, j: number) => (
                                                          <tr key={j} className="hover:bg-muted transition-colors">
                                                            <td className="text-left font-mono font-medium text-foreground py-2 px-4">{inv.wbsElement || 'Stock'}</td>
                                                            <td className="text-right font-mono font-semibold text-success dark:text-success py-2 px-4">{inv.inventoryQty}</td>
                                                            <td className="text-right font-mono font-semibold text-foreground py-2 px-4">{fmtCost(inv.inventoryValueINR)}</td>
                                                            <td className="text-center py-2 px-4">
                                                              <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${inv.storageLocation === 'CS01' ? 'bg-primary/100/10 text-primary dark:text-primary' : 'bg-purple-500/10 text-purple-600 dark:text-purple-400'}`}>{inv.storageLocation || '—'}</span>
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
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                          <Calendar className="w-4 h-4 text-primary/70" /> Complete Project Timeline
                        </h3>
                        <a href="https://digitalized-dpr.adani.com" target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-xs font-semibold bg-primary/10 hover:bg-primary/20 text-primary px-2.5 py-1.5 rounded-md transition-colors whitespace-nowrap">
                          <ExternalLink className="w-3.5 h-3.5" />
                          DPR Application
                        </a>
                      </div>
                      <div className="flex flex-col h-full">
                        {/* Header Info */}
                        <div className="flex items-center gap-3 mb-6 bg-muted p-3 rounded-lg border border-border/50">
                          <div className="flex-1">
                            <div className="text-[10px] uppercase font-bold text-muted-foreground mb-0.5">Project ID</div>
                            <div className="text-sm font-semibold text-foreground">{p6.projectId}</div>
                          </div>
                          <div className="w-px h-8 bg-border"></div>
                          <div className="flex-1">
                            <div className="text-[10px] uppercase font-bold text-muted-foreground mb-0.5">Parent EPS</div>
                            <div className="text-sm font-semibold text-foreground truncate">{p6.parentEPSName || '—'}</div>
                          </div>
                        </div>

                        {/* Phases Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                          {/* Start Phase */}
                          <div className="bg-card border border-border rounded-xl p-4 shadow-sm relative overflow-hidden">
                            <div className="absolute top-0 right-0 w-24 h-24 bg-primary/100/5 rounded-full blur-2xl pointer-events-none"></div>
                            <div className="flex items-center gap-2 mb-4 relative z-10">
                              <div className="w-7 h-7 rounded-lg bg-primary/100/10 flex items-center justify-center border border-primary/20">
                                <Activity className="w-3.5 h-3.5 text-primary" />
                              </div>
                              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Start Phase</span>
                            </div>
                            <div className="space-y-4 relative z-10">
                              <div className="flex justify-between items-center">
                                <span className="text-xs text-muted-foreground flex items-center gap-1.5"><CalendarClock className="w-3.5 h-3.5" /> Baseline</span>
                                <span className="text-sm font-medium">{p6.baselineStartDate || '—'}</span>
                              </div>
                              <div className="flex justify-between items-center">
                                <span className="text-xs text-muted-foreground flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" /> Planned</span>
                                <span className="text-sm font-medium">{p6.plannedStartDate || '—'}</span>
                              </div>
                              <div className="flex justify-between items-center bg-primary/100/5 -mx-2 px-2 py-1.5 rounded border border-blue-500/10">
                                <span className="text-xs text-primary dark:text-primary font-semibold flex items-center gap-1.5"><Play className="w-3.5 h-3.5" /> Actual</span>
                                <span className="text-sm font-bold text-blue-700 dark:text-blue-300">{p6.startDate || 'Pending'}</span>
                              </div>
                            </div>
                          </div>

                          {/* Finish Phase */}
                          <div className="bg-card border border-border rounded-xl p-4 shadow-sm relative overflow-hidden">
                            <div className="absolute top-0 right-0 w-24 h-24 bg-success/100/5 rounded-full blur-2xl pointer-events-none"></div>
                            <div className="flex items-center gap-2 mb-4 relative z-10">
                              <div className="w-7 h-7 rounded-lg bg-success/100/10 flex items-center justify-center border border-success/20">
                                <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                              </div>
                              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Finish Phase</span>
                            </div>
                            <div className="space-y-4 relative z-10">
                              <div className="flex justify-between items-center">
                                <span className="text-xs text-muted-foreground flex items-center gap-1.5"><CalendarClock className="w-3.5 h-3.5" /> Baseline</span>
                                <span className="text-sm font-medium">{p6.baselineFinishDate || '—'}</span>
                              </div>
                              <div className="flex justify-between items-center">
                                <span className="text-xs text-muted-foreground flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" /> Scheduled</span>
                                <span className="text-sm font-medium">{p6.scheduledFinishDate || p6.finishDate || '—'}</span>
                              </div>
                              <div className={`flex justify-between items-center -mx-2 px-2 py-1.5 rounded border ${p6.finishDate ? 'bg-success/100/5 border-emerald-500/10' : 'bg-warning/100/5 border-amber-500/10'}`}>
                                <span className={`text-xs font-semibold flex items-center gap-1.5 ${p6.finishDate ? 'text-success dark:text-success' : 'text-warning dark:text-warning'}`}>
                                  {p6.finishDate ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Clock className="w-3.5 h-3.5" />} 
                                  {p6.finishDate ? 'Actual Finish' : 'Must Finish By'}
                                </span>
                                <span className={`text-sm font-bold ${p6.finishDate ? 'text-success dark:text-emerald-300' : 'text-warning dark:text-amber-300'}`}>
                                  {p6.finishDate || p6.mustFinishByDate || '—'}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Footer */}
                        <div className="mt-auto pt-4 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground">
                          <div className="flex items-center gap-1.5"><Database className="w-3.5 h-3.5 opacity-70" /> Data Date: <span className="font-medium text-foreground/80">{p6.dataDate || '—'}</span></div>
                          <div className="flex items-center gap-1.5"><RefreshCcw className="w-3.5 h-3.5 opacity-70" /> Last Synced: <span className="font-medium text-foreground/80">{p6.lastSyncedAt || '—'}</span></div>
                        </div>
                      </div>
                    </div>

                    {/* Project Milestones */}
                    <div className="intelligence-card p-6 flex flex-col max-h-[400px]">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                          <Flag className="w-4 h-4 text-primary/70" /> Project Milestones
                        </h3>
                        <button onClick={() => setShowWorkflowModal(true)} className="p-1 hover:bg-primary/10 hover:text-primary rounded text-muted-foreground transition-colors">
                          <Maximize2 className="w-4 h-4" />
                        </button>
                      </div>
                      
                      <div className="flex-1 overflow-x-auto custom-scrollbar pr-2 py-6">
                        {p6.milestones && p6.milestones.length > 0 ? (
                          <div className="flex items-center px-6 min-w-max h-[240px]">
                            {p6.milestones.map((m: any, i: number) => {
                              const isLast = i === p6.milestones.length - 1;
                              const isEven = i % 2 === 0;
                              const isCompleted = m.status === 'Completed';
                              const isInProgress = m.status === 'In Progress';
                              const dateStr = isCompleted ? (m.actualFinishDate || m.actualStartDate || '—') : (m.plannedFinishDate || m.plannedStartDate || '—');

                              return (
                                <div key={i} className={`relative flex items-center shrink-0 w-[260px] mr-16 transition-transform duration-500 hover:z-50 ${isEven ? 'translate-y-[45px]' : '-translate-y-[45px]'}`}>
                                  
                                  {/* Input Port */}
                                  {i !== 0 && (
                                    <div className={`absolute -left-2 top-1/2 -translate-y-1/2 w-4 h-4 bg-background border-[3px] rounded-full z-20 transition-colors duration-300 ${
                                      isCompleted ? 'border-primary shadow-[0_0_10px_rgba(59,130,246,0.6)]' : 
                                      isInProgress ? 'border-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.6)] animate-pulse' : 
                                      'border-border shadow-inner'
                                    }`}></div>
                                  )}
                                  
                                  {/* Node Card */}
                                  <div className={`group w-full rounded-2xl flex flex-col z-10 border transition-all duration-300 hover:scale-[1.03] hover:-translate-y-1 ${
                                      isCompleted ? 'bg-white/40 dark:bg-gray-900/40 border-primary/40 shadow-[0_8px_30px_-4px_rgba(59,130,246,0.2)] hover:shadow-[0_12px_40px_-4px_rgba(59,130,246,0.4)] backdrop-blur-md' : 
                                      isInProgress ? 'bg-white/40 dark:bg-gray-900/40 border-amber-500/50 shadow-[0_8px_30px_-4px_rgba(245,158,11,0.2)] hover:shadow-[0_12px_40px_-4px_rgba(245,158,11,0.4)] backdrop-blur-md ring-1 ring-amber-500/20 ring-inset' : 
                                      'bg-card/40 dark:bg-card/40 border-border shadow-lg hover:shadow-xl backdrop-blur-sm hover:border-border/80'
                                  }`}>
                                    {/* Glass reflection overlay */}
                                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-tr from-white/0 via-white/5 to-white/0 dark:from-white/0 dark:via-white/5 dark:to-white/0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"></div>

                                    {/* Header */}
                                    <div className={`px-4 py-3 flex items-center gap-3 border-b ${
                                        isCompleted ? 'border-primary/20 text-primary' : 
                                        isInProgress ? 'border-amber-500/20 text-amber-500' : 
                                        'border-border text-muted-foreground group-hover:text-foreground transition-colors'
                                    }`}>
                                        <div className={`w-7 h-7 rounded-xl flex items-center justify-center shadow-inner text-[11px] font-black tracking-tighter ${
                                          isCompleted ? 'bg-gradient-to-br from-primary to-blue-700 text-white shadow-primary/40' : 
                                          isInProgress ? 'bg-gradient-to-br from-amber-400 to-orange-600 text-white shadow-amber-500/40 animate-pulse' : 
                                          'bg-muted border border-border text-muted-foreground group-hover:bg-muted/80 transition-colors'
                                        }`}>
                                          {isCompleted ? <Check className="w-4 h-4 text-white" /> : i + 1}
                                        </div>
                                        <h4 className="text-[12px] font-bold uppercase tracking-wide truncate flex-1 drop-shadow-sm" title={m.name}>
                                          {m.name}
                                        </h4>
                                    </div>

                                    {/* Body */}
                                    <div className="px-4 py-3 flex items-center justify-between relative overflow-hidden">
                                        <div className="flex items-center gap-2">
                                          {isCompleted ? (
                                            <div className="flex items-center gap-1.5 px-2 py-1 bg-primary/10 text-primary rounded-md text-[10px] font-semibold border border-primary/20">
                                              <CheckCircle2 className="w-3 h-3" /> Done
                                            </div>
                                          ) : isInProgress ? (
                                            <div className="flex items-center gap-1.5 px-2 py-1 bg-amber-500/10 text-amber-500 rounded-md text-[10px] font-semibold border border-amber-500/20">
                                              <Activity className="w-3 h-3 animate-pulse" /> Active
                                            </div>
                                          ) : (
                                            <div className="flex items-center gap-1.5 px-2 py-1 bg-muted text-muted-foreground rounded-md text-[10px] font-semibold border border-border">
                                              <Clock className="w-3 h-3" /> Pending
                                            </div>
                                          )}
                                        </div>
                                        <div className={`font-mono text-[10px] px-2 py-1 rounded-md border backdrop-blur-sm font-medium ${
                                          isCompleted ? 'bg-primary/5 text-primary border-primary/20' : 
                                          isInProgress ? 'bg-amber-500/5 text-amber-500 border-amber-500/20' : 
                                          'bg-card/50 text-muted-foreground border-border shadow-inner'
                                        }`}>
                                          {dateStr}
                                        </div>
                                    </div>
                                  </div>

                                  {/* Output Port */}
                                  {!isLast && (
                                    <div className={`absolute -right-2 top-1/2 -translate-y-1/2 w-4 h-4 bg-background border-[3px] rounded-full z-20 transition-colors duration-300 ${
                                      isCompleted ? 'border-primary shadow-[0_0_10px_rgba(59,130,246,0.6)]' : 
                                      'border-border shadow-inner'
                                    }`}></div>
                                  )}

                                  {/* Connection Wire (SVG Bezier Fix) */}
                                  {!isLast && (
                                    <svg width="64" height="90" className="absolute left-[calc(100%-2px)] pointer-events-none drop-shadow-md" style={{ top: isEven ? 'calc(50% - 90px)' : '50%', zIndex: 0 }}>
                                      <path 
                                        d={isEven ? "M 0 90 C 32 90, 32 0, 64 0" : "M 0 0 C 32 0, 32 90, 64 90"} 
                                        fill="none" 
                                        stroke="currentColor" 
                                        strokeWidth={isCompleted ? "3" : "2"} 
                                        strokeDasharray={isInProgress ? "4 4" : "0"}
                                        className={`transition-all duration-700 ${
                                          isCompleted ? 'text-primary' : 
                                          isInProgress ? 'text-amber-500 animate-[dash_2s_linear_infinite]' : 
                                          'text-border dark:text-gray-700'
                                        }`}
                                      />
                                    </svg>
                                  )}

                                </div>
                              )
                            })}
                          </div>
                        ) : (
                          <div className="text-xs text-muted-foreground italic py-8 text-center bg-muted rounded-xl border border-border">
                            No milestones tracked in P6 for this EPS
                          </div>
                        )}
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
                            <span className={`detail-row-value ${(label === 'Total Float' && p6.totalFloat != null && p6.totalFloat <= 0) ? 'text-destructive font-semibold' :
                              (label === 'Finish Date Variance' && p6.finishDateVariance != null && p6.finishDateVariance < -10) ? 'text-destructive' : ''
                              }`}>{val}</span>
                          </div>
                        ))}
                        {p6.totalFloat != null && (
                          <div className="mt-3 p-3 rounded-lg bg-muted border border-border">
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

                  {/* ═══ ALL ACTIVITIES HIERARCHY ═══ */}
                  <ProjectWBS p6Data={p6} />

                  {/* ═══ 2-WAY SYNC: EDIT PROJECT DATES ═══ */}
                  <P6SyncEditor p6={p6} />

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

                    <div className="flex items-center gap-2 mt-3 text-xs bg-success/100/10 border border-success/20 text-success dark:text-success px-3 py-1.5 rounded-md w-fit">
                      <div className="w-2 h-2 rounded-full bg-success/100 animate-pulse" />
                      <span><strong>Auto-Login Enabled:</strong> You will be securely authenticated automatically.</span>
                    </div>
                  </div>
                </div>

                <a
                  href={`https://adani.unada.in/transmission/v1/dashboard/${(detail?.mapping?.cluster || 'khavda').toLowerCase().includes('rajasthan') ? 'rajasthan' : 'khavda'}/commissioning-team?project=${encodeURIComponent(projectId || '')}&email=c7lj9OK6uzRLjiZLxS84y0QthSsZe7POcrGs-DIVaA0pmSPD9rlCGg2-Cg&pass=bFLZzcL7tsx1pZUJBqCXnMMkKQySqhmUDczHBCCX63aLNJ69`}
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
                  <div className="grid grid-cols-2 lg:grid-cols-5 gap-6">
                    <HeroMetric label="Charged" value={tc.summary.chargedLines} icon={Zap} color="text-success" hasBreakdown onClick={() => setExpandedTcMetric(expandedTcMetric === 'charged' ? null : 'charged')} active={expandedTcMetric === 'charged'} />
                    <HeroMetric label="In Progress" value={tc.summary.inProgressLines} icon={Activity} color="text-primary" hasBreakdown onClick={() => setExpandedTcMetric(expandedTcMetric === 'in_progress' ? null : 'in_progress')} active={expandedTcMetric === 'in_progress'} />
                    <HeroMetric label="Delayed" value={tc.summary.delayedLines} icon={AlertTriangle} color="text-destructive" hasBreakdown onClick={() => setExpandedTcMetric(expandedTcMetric === 'delayed' ? null : 'delayed')} active={expandedTcMetric === 'delayed'} />
                    
                    {(() => {
                      let mappedMW = tc.summary.totalMW;
                      if (!mappedMW) {
                        let sum = 0;
                        const KV_TO_MW: Record<string, number> = {
                          '800': 4000,
                          '765': 3000,
                          '400': 1000,
                          '220': 400,
                          '132': 150
                        };
                        const allEdges = [...(tc.khavdaEdges || []), ...(tc.rajasthanEdges || [])];
                        allEdges.forEach(edge => {
                          const match = String(edge.voltage || '').match(/(\d+)/);
                          if (match) {
                            const kv = match[1];
                            sum += KV_TO_MW[kv] || parseInt(kv, 10);
                          }
                        });
                        if (sum > 0) mappedMW = sum;
                      }
                      return <HeroMetric label="Mapped MW" value={mappedMW != null && mappedMW !== '' ? `${mappedMW}` : '—'} unit="MW" icon={Target} color="text-success" />
                    })()}

                    <HeroMetric label="TC Project" value={mapping?.tcProjectName || '—'} icon={MapPin} color="text-warning" />
                  </div>

                  {/* ── Interactive Breakdown Panel ── */}
                  {expandedTcMetric && (
                    <div className="intelligence-card p-5 animate-in slide-in-from-top-2 duration-300 border-primary/20 mt-4">
                      <div className="flex items-center justify-between mb-4">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-primary flex items-center gap-2">
                          <Network className="w-3.5 h-3.5" />
                          {expandedTcMetric === 'total' && 'All Transmission Lines'}
                          {expandedTcMetric === 'charged' && 'Charged Lines'}
                          {expandedTcMetric === 'in_progress' && 'Lines In Progress'}
                          {expandedTcMetric === 'delayed' && 'Delayed Lines'}
                        </h4>
                        <button onClick={() => setExpandedTcMetric(null)} className="text-muted-foreground hover:text-foreground text-xs px-2 py-1 rounded hover:bg-muted transition-colors">✕ Close</button>
                      </div>
                      <div className="overflow-x-auto max-h-[500px] overflow-y-auto scrollbar-thin">
                        <table className="intel-table relative w-full">
                          <thead className="sticky top-0 bg-slate-50/95 dark:bg-gray-900/95 backdrop-blur-sm z-10 text-[10px] uppercase tracking-wider">
                            <tr>
                              <th className="whitespace-nowrap">Project / Phase</th>
                              <th>From</th>
                              <th>To</th>
                              <th>Voltage</th>
                              <th>Length</th>
                              <th>Contractor</th>
                              <th>Status</th>
                              <th>Erection</th>
                              <th>Foundation</th>
                              <th>Stringing</th>
                              <th>SCOD</th>
                              <th className="whitespace-nowrap">ECOD</th>
                            </tr>
                          </thead>
                          <tbody>
                            {[...(tc.khavdaEdges || []), ...(tc.rajasthanEdges || [])]
                              .filter((edge: any) => {
                                if (expandedTcMetric === 'total') return true;
                                if (expandedTcMetric === 'charged') return edge.normalizedStatus === 'charged';
                                if (expandedTcMetric === 'in_progress') return edge.normalizedStatus === 'in_progress';
                                if (expandedTcMetric === 'delayed') return edge.isDelayed;
                                return true;
                              })
                              .map((edge: any, i: number) => (
                                <tr key={i} className="hover:bg-muted transition-colors">
                                  <td className="font-bold text-purple-400 font-mono text-[10px] uppercase tracking-wider truncate max-w-[200px]" title={`${edge.project} (${edge.phase})`}>
                                    {edge.project} <span className="text-muted-foreground ml-1 font-normal lowercase tracking-normal">({edge.phase})</span>
                                  </td>
                                  <td className="font-medium text-foreground/90 max-w-[150px] truncate" title={edge.fromLabel || edge.fromNode}>{edge.fromLabel || edge.fromNode}</td>
                                  <td className="font-medium text-foreground/90 max-w-[150px] truncate" title={edge.toLabel || edge.toNode}>{edge.toLabel || edge.toNode}</td>
                                  <td className="font-mono text-xs">{edge.voltage || '—'}</td>
                                  <td className="font-mono text-xs">{edge.length || '—'}</td>
                                  <td className="text-muted-foreground/70 text-xs">{edge.contractor || '—'}</td>
                                  <td>
                                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${edge.normalizedStatus === 'charged' ? 'bg-success/100/10 text-success border border-success/20' :
                                      edge.normalizedStatus === 'in_progress' ? 'bg-warning/100/10 text-warning border border-warning/20' :
                                        'bg-muted text-muted-foreground border border-border'
                                      }`}>
                                      {edge.status || '—'}
                                    </span>
                                  </td>
                                  <td className="text-xs text-muted-foreground/80">{edge.erection || '—'}</td>
                                  <td className="text-xs text-muted-foreground/80">{edge.foundation || '—'}</td>
                                  <td className="text-xs text-muted-foreground/80">{edge.stringing || '—'}</td>
                                  <td className="text-xs font-mono">{edge.scd || '—'}</td>
                                  <ECODCell edge={edge} />
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Khavda Transmission Lines Table */}
                  {tc.khavdaEdges.length > 0 && (
                    <div className="intelligence-card p-6">
                      <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                        <Zap className="w-4 h-4 text-purple-400" /> Khavda Transmission Lines
                      </h3>
                      <div className="overflow-auto max-h-[400px]">
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
                              <th>SCOD</th>
                              <th>ECOD</th>
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
                                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${(edge.normalizedStatus || edge.status || '').toLowerCase() === 'charged' || (edge.normalizedStatus || edge.status || '').toLowerCase() === 'completed' ? 'bg-green-500/10 text-green-500 border border-green-500/20' :
                                    (edge.normalizedStatus || edge.status || '').toLowerCase() === 'in_progress' || (edge.normalizedStatus || edge.status || '').toLowerCase() === 'in progress' ? 'bg-blue-500/10 text-blue-500 border border-blue-500/20' :
                                    (edge.normalizedStatus || edge.status || '').toLowerCase() === 'under_bidding' ? 'bg-orange-500/10 text-orange-500 border border-orange-500/20' :
                                      'bg-slate-500/10 text-slate-500 border border-slate-500/20'
                                    }`}>
                                    {edge.status || '—'}
                                  </span>
                                </td>
                                <td className="text-xs text-muted-foreground/80">{edge.erection || '—'}</td>
                                <td className="text-xs text-muted-foreground/80">{edge.foundation || '—'}</td>
                                <td className="text-xs text-muted-foreground/80">{edge.stringing || '—'}</td>
                                <td className="text-xs font-mono">{edge.scd || '—'}</td>
                                <ECODCell edge={edge} />
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
                        <Network className="w-4 h-4 text-primary" /> Rajasthan Transmission Lines
                      </h3>
                      <div className="overflow-auto max-h-[400px]">
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
                              <th>SCOD</th>
                              <th>ECOD</th>
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
                                  <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${(edge.normalizedStatus || edge.status || '').toLowerCase() === 'charged' || (edge.normalizedStatus || edge.status || '').toLowerCase() === 'completed' ? 'bg-green-500/10 text-green-500 border border-green-500/20' :
                                    (edge.normalizedStatus || edge.status || '').toLowerCase() === 'in_progress' || (edge.normalizedStatus || edge.status || '').toLowerCase() === 'in progress' ? 'bg-blue-500/10 text-blue-500 border border-blue-500/20' :
                                    (edge.normalizedStatus || edge.status || '').toLowerCase() === 'under_bidding' ? 'bg-orange-500/10 text-orange-500 border border-orange-500/20' :
                                      'bg-slate-500/10 text-slate-500 border border-slate-500/20'
                                    }`}>
                                    {edge.normalizedStatus || edge.status || '—'}
                                  </span>
                                </td>
                                <td className="font-mono text-xs text-muted-foreground/70">{edge.erection || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/70">{edge.foundation || '—'}</td>
                                <td className="font-mono text-xs text-muted-foreground/70">{edge.stringing || '—'}</td>
                                <td className="font-mono text-xs">{edge.scd || '—'}</td>
                                <ECODCell edge={edge} />
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
                        <MapPin className="w-4 h-4 text-success" /> Transmission Substations & Nodes
                      </h3>
                      <div className="overflow-x-auto max-h-[300px] overflow-y-auto scrollbar-thin">
                        <table className="intel-table relative w-full">
                          <thead className="sticky top-0 bg-slate-50/95 dark:bg-gray-900/95 backdrop-blur-sm z-10 shadow-sm">
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
                                  <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${(n.status || '').toLowerCase() === 'charged' || (n.status || '').toLowerCase() === 'completed' ? 'bg-green-500/10 text-green-500 border border-green-500/20' :
                                    (n.status || '').toLowerCase() === 'in_progress' || (n.status || '').toLowerCase() === 'in progress' ? 'bg-blue-500/10 text-blue-500 border border-blue-500/20' :
                                    (n.status || '').toLowerCase() === 'under_bidding' ? 'bg-orange-500/10 text-orange-500 border border-orange-500/20' :
                                      'bg-slate-500/10 text-slate-500 border border-slate-500/20'
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
          
          {/* ════════ QUALITY TAB (NEW) ════════ */}
          {activeTab === 'quality' && (
            <div className="intelligence-card p-6 min-h-[500px]">
              <div className="mb-6">
                <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <Shield className="w-5 h-5 text-primary" /> Pulse Quality Data
                </h2>
                <p className="text-sm text-muted-foreground mt-1">Non-conformances and inspections synced from SAP Pulse for {p.projectName}</p>
              </div>
              <QualityProjectTab projectName={p.projectName} />
            </div>
          )}

        </div>
      </main>

      {/* ── Modals ── */}
      {/* COD Blocks Modal */}
      {showCodModal && detail?.mapping?.blocksStatus && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setShowCodModal(null)}>
          <div className="bg-card w-full max-w-4xl max-h-[85vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-border" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-border bg-muted/30">
              <div>
                <h2 className="text-xl font-bold flex items-center gap-2">
                  {showCodModal === 'done' ? (
                    <><CheckCircle2 className="w-5 h-5 text-success" /> COD Completed {detail.mapping.unitType || 'Blocks'}</>
                  ) : (
                    <><AlertTriangle className="w-5 h-5 text-warning" /> Pending COD {detail.mapping.unitType || 'Blocks'}</>
                  )}
                </h2>
                <p className="text-sm text-muted-foreground mt-1">
                  {showCodModal === 'done' ? 'Units that have achieved Commercial Operation Date' : 'Units waiting for Commercial Operation Date'}
                </p>
              </div>
              <button onClick={() => setShowCodModal(null)} className="p-2 rounded-lg hover:bg-accent text-muted-foreground transition-colors"><X className="w-5 h-5" /></button>
            </div>
            
            <div className="p-6 overflow-y-auto custom-scrollbar flex-1">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {Object.entries(detail.mapping.blocksStatus)
                  .filter(([_, status]: any) => showCodModal === 'done' ? status.cod === 'Completed' : status.cod !== 'Completed')
                  .sort(([a], [b]) => a.localeCompare(b, undefined, {numeric: true}))
                  .map(([bName, status]: any) => (
                  <div key={bName} className="p-4 rounded-xl border border-border bg-background shadow-sm space-y-3">
                    <div className="flex justify-between items-center pb-2 border-b border-border/50">
                      <span className="font-bold text-sm truncate pr-2">{bName}</span>
                      <span className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded font-bold shrink-0 ${status.cod === 'Completed' ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'}`}>
                        {status.cod === 'Completed' ? 'COD Done' : 'Pending'}
                      </span>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <div className="text-muted-foreground mb-1 text-[10px] uppercase">COD</div>
                        {status.cod === 'Completed' ? (
                          <div className="font-semibold text-success flex items-center gap-1 truncate text-[11px]">
                            <CheckCircle2 className="w-3 h-3 shrink-0" /> {status.cod_actual_date || 'Done'}
                          </div>
                        ) : (
                          <div className="font-semibold text-blue-500 flex items-center gap-1 truncate text-[11px]">
                            <Clock className="w-3 h-3 shrink-0" /> {status.cod_forecast_date || 'TBD'}
                          </div>
                        )}
                      </div>
                      
                      <div>
                        <div className="text-muted-foreground mb-1 text-[10px] uppercase">Trial Run</div>
                        {status.tr === 'Completed' ? (
                          <div className="font-semibold text-success flex items-center gap-1 truncate text-[11px]">
                            <CheckCircle2 className="w-3 h-3 shrink-0" /> {status.tr_actual_date || 'Done'}
                          </div>
                        ) : (
                          <div className="font-semibold text-blue-500 flex items-center gap-1 truncate text-[11px]">
                            <Clock className="w-3 h-3 shrink-0" /> Pending
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {showDelayedModal && detail?.p6?.delayedActivities && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setShowDelayedModal(false)}>
          <div className="bg-card border border-border rounded-2xl w-full max-w-5xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden ring-1 ring-black/5 dark:ring-white/10" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-border bg-muted">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-destructive/10 dark:bg-destructive/100/10 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-destructive dark:text-destructive" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-card-foreground tracking-tight">Delayed Construction Activities</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">Live from Primavera P6 • Auto-filtered to Construction Scope</p>
                </div>
              </div>
              <button onClick={() => setShowDelayedModal(false)} className="p-2 rounded-lg hover:bg-accent text-muted-foreground transition-colors"><X className="w-5 h-5" /></button>
            </div>

            <div className="flex-1 overflow-auto p-6 space-y-6">
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-muted border border-border rounded-xl p-4 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Total Delayed</div>
                    <div className="text-3xl font-light text-card-foreground">{detail.p6.delayedActivities.length}</div>
                  </div>
                  <AlertTriangle className="w-8 h-8 text-destructive/20" />
                </div>
                <div className="bg-muted border border-border rounded-xl p-4 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Impacted Capacity</div>
                    <div className="text-3xl font-light text-card-foreground">
                      {(() => {
                        const uniqueBlocks = new Set();
                        return detail.p6.delayedActivities.reduce((acc: number, cur: any) => {
                          if (cur.mwCapacity > 0) {
                            if (cur.wbsName) {
                              if (!uniqueBlocks.has(cur.wbsName)) {
                                uniqueBlocks.add(cur.wbsName);
                                return acc + cur.mwCapacity;
                              }
                            } else {
                              return acc + cur.mwCapacity;
                            }
                          }
                          return acc;
                        }, 0).toFixed(1);
                      })()} <span className="text-sm">MW</span>
                    </div>
                  </div>
                  <Zap className="w-8 h-8 text-warning/20" />
                </div>
                <div className="bg-muted border border-border rounded-xl p-4 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Critical Delays (&gt;30d)</div>
                    <div className="text-3xl font-light text-destructive">{detail.p6.delayedActivities.filter((a: any) => a.delayDays > 30).length}</div>
                  </div>
                  <Clock className="w-8 h-8 text-destructive/20" />
                </div>
              </div>

              <div className="border border-border rounded-xl overflow-hidden bg-background">
                <table className="w-full text-sm text-left whitespace-nowrap">
                  <thead className="bg-muted text-[10px] uppercase font-bold tracking-widest text-muted-foreground border-b border-border">
                    <tr>
                      <th className="px-4 py-3">Activity ID & Name</th>
                      <th className="px-4 py-3">WBS</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Planned Date</th>
                      <th className="px-4 py-3">Delay</th>
                      <th className="px-4 py-3">MW Impact</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {(() => {
                      const renderedBlocks = new Set();
                      return detail.p6.delayedActivities.map((act: any, i: number) => {
                        let showMW = false;
                        if (act.mwCapacity > 0) {
                          if (act.wbsName) {
                            if (!renderedBlocks.has(act.wbsName)) {
                              renderedBlocks.add(act.wbsName);
                              showMW = true;
                            }
                          } else {
                            showMW = true;
                          }
                        }
                        return (
                          <tr key={i} className="hover:bg-muted transition-colors">
                            <td className="px-4 py-3">
                              <div className="text-xs font-mono text-muted-foreground mb-0.5">{act.activityId}</div>
                              <div className="font-medium text-card-foreground max-w-[300px] truncate" title={act.name}>{act.name}</div>
                            </td>
                            <td className="px-4 py-3 text-muted-foreground text-xs max-w-[200px] truncate" title={act.wbsName}>{act.wbsName || '—'}</td>
                            <td className="px-4 py-3">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${(act.status || '').toLowerCase() === 'completed' ? 'bg-green-500/10 text-green-500 border border-green-500/20' :
                                    (act.status || '').toLowerCase() === 'in progress' ? 'bg-blue-500/10 text-blue-500 border border-blue-500/20' :
                                      'bg-red-500/10 text-red-500 border border-red-500/20'
                                    }`}>
                                {act.status}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-muted-foreground">
                              {act.status === 'In Progress' ? act.plannedFinishDate : act.plannedStartDate}
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-1.5 text-destructive font-medium">
                                <ArrowLeft className="w-3 h-3 text-destructive/50" />
                                {act.delayDays} days
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              {showMW ? <span className="text-warning font-medium">{act.mwCapacity.toFixed(1)} MW</span> : <span className="text-muted-foreground/40 italic text-[10px]">grouped</span>}
                            </td>
                          </tr>
                        );
                      });
                    })()}
                  </tbody>
                </table>
              </div>
              {/* Workflow Modal */}
      {showWorkflowModal && (
        <div className="fixed inset-0 z-[100] bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card w-[95vw] h-[90vh] rounded-2xl shadow-2xl border border-border flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="flex items-center justify-between p-4 border-b bg-card z-20">
              <h2 className="text-lg font-bold flex items-center gap-2 text-foreground">
                <Network className="w-5 h-5 text-primary" /> Full Project Workflow
              </h2>
              <button onClick={() => setShowWorkflowModal(false)} className="p-2 hover:bg-muted rounded-full text-muted-foreground hover:text-foreground transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-auto bg-muted p-12 custom-scrollbar">
              <div className="flex items-center gap-24 min-w-max h-[400px] px-12 py-12">
                {p6?.milestones?.map((m: any, i: number) => {
                  const isLast = i === p6.milestones.length - 1;
                  const isEven = i % 2 === 0;
                  const isCompleted = m.status === 'Completed';
                  const isInProgress = m.status === 'In Progress';
                  const dateStr = isCompleted ? (m.actualFinishDate || m.actualStartDate || '—') : (m.plannedFinishDate || m.plannedStartDate || '—');

                  return (
                    <div key={i} className={`relative flex items-center shrink-0 w-[280px] ${isEven ? 'translate-y-[80px]' : '-translate-y-[80px]'}`}>
                      
                      {/* Input Port */}
                      {i !== 0 && (
                        <div className={`absolute -left-2 top-1/2 -translate-y-1/2 w-4 h-4 bg-background border-[3px] rounded-full z-20 ${
                          isCompleted || isInProgress ? 'border-primary shadow-[0_0_10px_rgba(59,130,246,0.5)]' : 'border-muted-foreground/50'
                        }`}></div>
                      )}
                      
                      {/* Node Card */}
                      <div className={`w-full bg-card rounded-2xl shadow-lg flex flex-col z-10 border-2 ${
                          isCompleted ? 'border-primary shadow-primary/20' : 
                          isInProgress ? 'border-amber-500 shadow-amber-500/20' : 
                          'border-border shadow-black/5'
                      }`}>
                        <div className={`px-4 py-3 flex items-center gap-3 border-b ${
                            isCompleted ? 'bg-primary/5 border-primary/20 text-primary' : 
                            isInProgress ? 'bg-warning/100/5 border-warning/20 text-warning' : 
                            'bg-muted border-border text-muted-foreground'
                        } rounded-t-2xl`}>
                            <div className={`w-7 h-7 rounded-lg flex items-center justify-center shadow-md text-xs font-bold ${
                              isCompleted ? 'bg-primary text-primary-foreground' : 
                              isInProgress ? 'bg-warning/100 text-white' : 
                              'bg-background border border-border text-foreground'
                            }`}>
                              {i + 1}
                            </div>
                            <h4 className="text-[13px] font-bold uppercase tracking-tight line-clamp-2 leading-tight flex-1" title={m.name}>
                              {m.name}
                            </h4>
                        </div>

                        <div className="px-4 py-3.5 flex items-center justify-between bg-card rounded-b-2xl">
                            <div className="flex items-center gap-2">
                              <div className={`w-2.5 h-2.5 rounded-full shadow-sm ${isCompleted ? 'bg-primary' : isInProgress ? 'bg-warning/100 animate-pulse' : 'bg-muted-foreground/30'}`}></div>
                            </div>
                            <span className="font-mono text-[10px] text-foreground bg-muted px-2 py-1 rounded-md border border-border">{dateStr}</span>
                        </div>
                      </div>

                      {/* Output Port */}
                      {!isLast && (
                        <div className={`absolute -right-2 top-1/2 -translate-y-1/2 w-4 h-4 bg-background border-[3px] rounded-full z-20 ${
                          isCompleted ? 'border-primary shadow-[0_0_10px_rgba(59,130,246,0.5)]' : 'border-muted-foreground/50'
                        }`}></div>
                      )}

                      {/* Connection Wire */}
                      {!isLast && (
                        <svg className="absolute left-[calc(100%-1.5px)] pointer-events-none" style={{ width: '6rem', height: '160px', top: isEven ? 'calc(50% - 160px)' : '50%', zIndex: -10 }}>
                          <path 
                            d={isEven ? "M 0 160 C 48 160, 48 0, 96 0" : "M 0 0 C 48 0, 48 160, 96 160"} 
                            fill="none" 
                            stroke="currentColor" 
                            strokeWidth="3" 
                            className={isCompleted ? 'text-primary' : 'text-primary/20'}
                          />
                        </svg>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
          </div>
        </div>
      )}
    </div>
  );
}
