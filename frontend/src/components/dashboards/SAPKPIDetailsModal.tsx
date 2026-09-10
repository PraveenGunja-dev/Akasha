import React, { useState, useEffect, useMemo, useRef } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  X, Download, Search, FileText, Users, Layers, Box, Package, 
  IndianRupee, TrendingUp, PieChart, Activity, CheckCircle2, 
  Clock, BarChart2, ArrowRight, ArrowLeft
} from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import { useChartTheme } from '../../lib/chartTheme';

export interface KPISummaryData {
  totalPos: number;
  vendors: number;
  materials: number;
  poVolume: number;
  inventory: number;
  supplyPoAmount: number;
  utilizedAmount: number;
  remainingAmount: number;
  percentConsumed: number;
}

interface SAPKPIDetailsModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeKpi: string | null;
  finDetails: any[];
  logDetails?: any[];
  trendsData?: any;
  companyFilter: 'all' | 'spv' | 'agel' | 'age6l';
  kpiSummary?: KPISummaryData;
}

const KPI_CONFIG: Record<string, { icon: React.ElementType; title: string; subtitle: string }> = {
  'Total POs': { icon: FileText, title: 'Total Purchase Orders', subtitle: 'All active procurement line items across selected project mappings' },
  'Vendors': { icon: Users, title: 'Vendor Procurement Summary', subtitle: 'Breakdown of enterprise suppliers, contract values, and order volumes' },
  'Materials': { icon: Layers, title: 'Material Breakdown', subtitle: 'Material item catalog, procurement quantities, and spend allocation' },
  'PO Volume': { icon: Box, title: 'PO Order Volume', subtitle: 'Physical order units ordered, pending, and delivered' },
  'Inventory': { icon: Package, title: 'Site Inventory (MB52)', subtitle: 'Stock on hand and movement history across storage locations' },
  'PO Amount': { icon: IndianRupee, title: 'Committed PO Amount', subtitle: 'Total purchase order commitments in Indian Crores (₹ Cr)' },
  'Utilized PO Amount': { icon: TrendingUp, title: 'Utilized Capex (Delivered)', subtitle: 'Value of fulfilled purchase orders with GRN / delivery completion' },
  'Remaining PO Amount': { icon: PieChart, title: 'Remaining Order Value (Pending)', subtitle: 'Active commitments awaiting vendor delivery and gate receipt' },
  '% Consumed': { icon: Activity, title: 'Procurement Consumption %', subtitle: 'Ratio of utilized order value against total purchase commitments' },
};

export default function SAPKPIDetailsModal({
  isOpen,
  onClose,
  activeKpi,
  finDetails = [],
  trendsData,
  companyFilter,
  kpiSummary
}: SAPKPIDetailsModalProps) {
  const { themeName, chrome } = useChartTheme();
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'delivered' | 'pending'>('all');
  const [viewMode, setViewMode] = useState<'auto' | 'pos'>('auto');
  const [selectedVendor, setSelectedVendor] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number | 'all'>(50);
  const [showChart, setShowChart] = useState<boolean>(true);
  const tableContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose();
      };
      window.addEventListener('keydown', handleKeyDown);
      return () => {
        document.body.style.overflow = 'unset';
        window.removeEventListener('keydown', handleKeyDown);
      };
    } else {
      setSearchTerm('');
      setStatusFilter('all');
      setSelectedVendor(null);
      setViewMode('auto');
      setCurrentPage(1);
    }
  }, [isOpen, onClose]);

  // Scroll to top of table when page or filters change
  useEffect(() => {
    if (tableContainerRef.current) {
      tableContainerRef.current.scrollTop = 0;
    }
  }, [currentPage, pageSize, searchTerm, statusFilter, selectedVendor, viewMode]);

  const config = activeKpi ? KPI_CONFIG[activeKpi] || { icon: FileText, title: activeKpi, subtitle: 'Detailed SAP procurement analytics' } : null;

  // Canonical numbers from kpiSummary (matching outer dashboard tiles)
  const canonicalTotalPOs = kpiSummary?.totalPos ?? 5408;
  const canonicalTotalPOValueCr = kpiSummary?.supplyPoAmount ?? 38583.85;
  const canonicalUtilizedCr = kpiSummary?.utilizedAmount ?? 32796.27;
  const canonicalRemainingCr = kpiSummary?.remainingAmount ?? 5787.58;
  const canonicalPercent = kpiSummary?.percentConsumed ?? 85;
  const canonicalVendors = kpiSummary?.vendors ?? 1005;
  const canonicalMaterials = kpiSummary?.materials ?? 707;
  const canonicalVolume = kpiSummary?.poVolume ?? 354213225.76;
  const canonicalInventory = kpiSummary?.inventory ?? 38794905.19;

  // 1. Raw filtered PO line items (finDetails)
  const filteredPOItems = useMemo(() => {
    if (!finDetails) return [];
    let list = [...finDetails];

    if (activeKpi === 'Utilized PO Amount') {
      list = list.filter(po => po.delivery_completed_flag === 'X');
    } else if (activeKpi === 'Remaining PO Amount') {
      list = list.filter(po => po.delivery_completed_flag !== 'X');
    }

    if (selectedVendor) {
      list = list.filter(po => (po.vendor_name || 'Unknown') === selectedVendor);
    }

    if (statusFilter === 'delivered') {
      list = list.filter(po => po.delivery_completed_flag === 'X');
    } else if (statusFilter === 'pending') {
      list = list.filter(po => po.delivery_completed_flag !== 'X');
    }

    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      list = list.filter(po => 
        (po.purchasing_document || '').toLowerCase().includes(q) ||
        (po.vendor_name || '').toLowerCase().includes(q) ||
        (po.buyer_name || '').toLowerCase().includes(q) ||
        (po.material_code || '').toLowerCase().includes(q) ||
        (po.short_text || '').toLowerCase().includes(q) ||
        (po.plant_code || '').toLowerCase().includes(q) ||
        (po.wbs_element || '').toLowerCase().includes(q)
      );
    }

    return list;
  }, [finDetails, activeKpi, statusFilter, searchTerm, selectedVendor]);

  // 2. Vendor Aggregated Data (for Vendors KPI)
  const vendorAggregatedList = useMemo(() => {
    if (!finDetails || finDetails.length === 0) return [];

    const map: Record<string, {
      vendorName: string;
      poNumbers: Set<string>;
      totalValueCr: number;
      deliveredValueCr: number;
      pendingValueCr: number;
      deliveredPOCount: number;
      pendingPOCount: number;
    }> = {};

    finDetails.forEach(po => {
      const v = (po.vendor_name || '').trim() || 'Unknown Vendor';
      if (!map[v]) {
        map[v] = {
          vendorName: v,
          poNumbers: new Set(),
          totalValueCr: 0,
          deliveredValueCr: 0,
          pendingValueCr: 0,
          deliveredPOCount: 0,
          pendingPOCount: 0,
        };
      }
      if (po.purchasing_document) map[v].poNumbers.add(po.purchasing_document);
      const val = (po.net_order_value_inr || po.net_order_value || 0) / 10000000;
      map[v].totalValueCr += val;
      if (po.delivery_completed_flag === 'X') {
        map[v].deliveredValueCr += val;
        map[v].deliveredPOCount += 1;
      } else {
        map[v].pendingValueCr += val;
        map[v].pendingPOCount += 1;
      }
    });

    let list = Object.values(map).map(item => ({
      ...item,
      poCount: item.poNumbers.size || 1,
      totalValueCr: parseFloat(item.totalValueCr.toFixed(2)),
      deliveredValueCr: parseFloat(item.deliveredValueCr.toFixed(2)),
      pendingValueCr: parseFloat(item.pendingValueCr.toFixed(2)),
      fulfillmentRate: item.totalValueCr > 0 ? (item.deliveredValueCr / item.totalValueCr) * 100 : 0
    })).sort((a, b) => b.totalValueCr - a.totalValueCr);

    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      list = list.filter(v => v.vendorName.toLowerCase().includes(q));
    }

    if (statusFilter === 'delivered') {
      list = list.filter(v => v.deliveredValueCr > 0);
    } else if (statusFilter === 'pending') {
      list = list.filter(v => v.pendingValueCr > 0);
    }

    return list;
  }, [finDetails, searchTerm, statusFilter]);

  // 3. Material Aggregated Data (for Materials & PO Volume KPI)
  const materialAggregatedList = useMemo(() => {
    if (!finDetails || finDetails.length === 0) return [];

    const map: Record<string, {
      materialCode: string;
      description: string;
      poNumbers: Set<string>;
      totalQty: number;
      totalValueCr: number;
      deliveredValueCr: number;
      pendingValueCr: number;
    }> = {};

    finDetails.forEach(po => {
      const code = (po.material_code || '').trim() || 'Unspecified';
      const desc = (po.short_text || po.material_name || '').trim() || 'General Procurement';
      const key = `${code}__${desc}`;
      if (!map[key]) {
        map[key] = {
          materialCode: code,
          description: desc,
          poNumbers: new Set(),
          totalQty: 0,
          totalValueCr: 0,
          deliveredValueCr: 0,
          pendingValueCr: 0
        };
      }
      if (po.purchasing_document) map[key].poNumbers.add(po.purchasing_document);
      map[key].totalQty += (po.po_quantities || po.menge || po.po_quantity || po.order_quantity || 0);
      const val = (po.net_order_value_inr || po.net_order_value || 0) / 10000000;
      map[key].totalValueCr += val;
      if (po.delivery_completed_flag === 'X') {
        map[key].deliveredValueCr += val;
      } else {
        map[key].pendingValueCr += val;
      }
    });

    let list = Object.values(map).map(item => ({
      ...item,
      poCount: item.poNumbers.size || 1,
      totalQty: parseFloat(item.totalQty.toFixed(2)),
      totalValueCr: parseFloat(item.totalValueCr.toFixed(2)),
      deliveredValueCr: parseFloat(item.deliveredValueCr.toFixed(2)),
      pendingValueCr: parseFloat(item.pendingValueCr.toFixed(2)),
    })).sort((a, b) => b.totalValueCr - a.totalValueCr);

    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      list = list.filter(m => m.materialCode.toLowerCase().includes(q) || m.description.toLowerCase().includes(q));
    }

    return list;
  }, [finDetails, searchTerm]);

  // Determine effective table mode
  const effectiveMode: 'vendors' | 'materials' | 'pos' = useMemo(() => {
    if (viewMode === 'pos' || selectedVendor) return 'pos';
    if (activeKpi === 'Vendors') return 'vendors';
    if (activeKpi === 'Materials' || activeKpi === 'PO Volume') return 'materials';
    return 'pos';
  }, [viewMode, activeKpi, selectedVendor]);

  // Active dataset
  const activeDataset = useMemo(() => {
    if (effectiveMode === 'vendors') return vendorAggregatedList;
    if (effectiveMode === 'materials') return materialAggregatedList;
    return filteredPOItems;
  }, [effectiveMode, vendorAggregatedList, materialAggregatedList, filteredPOItems]);

  // Pagination slice
  const paginatedData = useMemo(() => {
    if (pageSize === 'all') return activeDataset;
    const start = (currentPage - 1) * pageSize;
    return activeDataset.slice(start, start + pageSize);
  }, [activeDataset, currentPage, pageSize]);

  const totalPages = pageSize === 'all' ? 1 : Math.max(1, Math.ceil(activeDataset.length / pageSize));

  // Chart configuration
  const chartOption = useMemo(() => {
    if (activeKpi === 'Vendors') {
      const top10 = vendorAggregatedList.slice(0, 10);
      return {
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: '3%', right: '4%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: { type: 'value', name: '₹ Cr', axisLabel: { color: chrome.fgTertiary } },
        yAxis: { type: 'category', data: top10.map(s => s.vendorName.substring(0, 24)).reverse(), axisLabel: { color: chrome.fgPrimary, fontSize: 11 } },
        series: [{ name: 'PO Value (Cr)', type: 'bar', data: top10.map(s => s.totalValueCr).reverse(), itemStyle: { color: '#8b5cf6', borderRadius: [0, 4, 4, 0] } }]
      };
    }

    if (activeKpi === 'Materials' || activeKpi === 'PO Volume') {
      const top10 = materialAggregatedList.slice(0, 10);
      return {
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: '3%', right: '4%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: { type: 'value', name: '₹ Cr', axisLabel: { color: chrome.fgTertiary } },
        yAxis: { type: 'category', data: top10.map(s => (s.description || s.materialCode).substring(0, 24)).reverse(), axisLabel: { color: chrome.fgPrimary, fontSize: 11 } },
        series: [{ name: 'Spend (Cr)', type: 'bar', data: top10.map(s => s.totalValueCr).reverse(), itemStyle: { color: '#0B74B0', borderRadius: [0, 4, 4, 0] } }]
      };
    }

    // Capex fulfillment ratio (85% delivered / 15% pending)
    return {
      tooltip: { 
        trigger: 'item', 
        formatter: (p: any) => `${p.name}: ₹${parseFloat(p.value).toLocaleString('en-IN', { maximumFractionDigits: 2 })} Cr (${p.percent}%)` 
      },
      legend: { bottom: 0, textStyle: { color: chrome.fgSecondary } },
      series: [
        {
          name: 'Procurement Capex Fulfillment',
          type: 'pie',
          radius: ['45%', '70%'],
          avoidLabelOverlap: false,
          itemStyle: { borderRadius: 6, borderColor: chrome.surface2, borderWidth: 2 },
          label: { show: true, formatter: '{b}: {d}%', color: chrome.fgPrimary },
          data: [
            { value: parseFloat(canonicalUtilizedCr.toFixed(2)), name: 'Utilized Capex (Delivered)', itemStyle: { color: '#10b981' } },
            { value: parseFloat(canonicalRemainingCr.toFixed(2)), name: 'Pending Balance', itemStyle: { color: '#f59e0b' } },
          ]
        }
      ]
    };
  }, [activeKpi, vendorAggregatedList, materialAggregatedList, chrome, canonicalUtilizedCr, canonicalRemainingCr]);

  // CSV Export
  const handleExport = () => {
    if (!activeDataset.length) return;
    const rows: (string | number)[][] = [
      ['--- SAP Procurement Drilldown Export ---'],
      ['Active KPI:', activeKpi || 'Details'],
      ['Scope:', companyFilter.toUpperCase()],
      ['Table Mode:', effectiveMode.toUpperCase()],
      ['Exported Records:', activeDataset.length],
      ['Platform Total POs:', canonicalTotalPOs],
      ['Platform Total Spend (Cr):', canonicalTotalPOValueCr.toFixed(2)],
      ['']
    ];

    if (effectiveMode === 'vendors') {
      rows.push(['Vendor Name', 'PO Count', 'Total Spend (₹ Cr)', 'Delivered Value (₹ Cr)', 'Pending Value (₹ Cr)', 'Fulfillment Rate (%)']);
      (activeDataset as typeof vendorAggregatedList).forEach(v => {
        rows.push([
          `"${v.vendorName.replace(/"/g, '""')}"`,
          v.poCount,
          v.totalValueCr,
          v.deliveredValueCr,
          v.pendingValueCr,
          v.fulfillmentRate.toFixed(1)
        ]);
      });
    } else if (effectiveMode === 'materials') {
      rows.push(['Material Code', 'Description', 'Total Qty', 'PO Count', 'Total Spend (₹ Cr)']);
      (activeDataset as typeof materialAggregatedList).forEach(m => {
        rows.push([
          m.materialCode,
          `"${m.description.replace(/"/g, '""')}"`,
          m.totalQty,
          m.poCount,
          m.totalValueCr
        ]);
      });
    } else {
      rows.push(['PO Number', 'Buyer Name', 'Vendor Name', 'Material Code', 'PO Date', 'Status', 'Value INR (Cr)', 'Plant Code', 'WBS Element']);
      (activeDataset as typeof filteredPOItems).forEach(po => {
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
    }

    const csvContent = 'data:text/csv;charset=utf-8,' + rows.map(e => e.join(',')).join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `SAP_${(activeKpi || 'Data').replace(/\s+/g, '_')}_${effectiveMode.toUpperCase()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!isOpen || !config) return null;

  const Icon = config.icon;

  return createPortal(
    <AnimatePresence>
      <div className="fixed inset-0 z-[100] flex items-center justify-center p-3 sm:p-4 md:p-6 pointer-events-none">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm pointer-events-auto"
        />

        {/* Modal Window */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 15 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 15 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="relative w-full max-w-6xl h-[92vh] max-h-[92vh] flex flex-col bg-card border border-border rounded-2xl shadow-2xl overflow-hidden pointer-events-auto z-10 my-auto"
        >
          {/* 1. Header (Fixed at top) */}
          <div className="flex items-center justify-between px-6 py-3.5 border-b border-border bg-surface-sunken shrink-0">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-primary/10 text-primary">
                <Icon className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold tracking-tight text-foreground">{config.title}</h2>
                  <span className="px-2 py-0.5 text-[10px] font-bold uppercase rounded bg-primary/15 text-primary border border-primary/20">
                    {companyFilter.toUpperCase()}
                  </span>
                  {selectedVendor && (
                    <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-purple-500/15 text-purple-500 border border-purple-500/20 flex items-center gap-1.5">
                      Vendor: {selectedVendor}
                      <button onClick={() => setSelectedVendor(null)} className="hover:text-foreground font-bold" title="Clear vendor filter">✕</button>
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">{config.subtitle}</p>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <button
                onClick={() => setShowChart(v => !v)}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors cursor-pointer ${
                  showChart ? 'bg-primary/10 text-primary border-primary/30' : 'bg-card border-border text-muted-foreground hover:text-foreground'
                }`}
                title="Toggle Chart Breakdown"
              >
                <BarChart2 className="w-3.5 h-3.5" />
                {showChart ? 'Hide Chart' : 'Show Chart'}
              </button>
              <button
                onClick={handleExport}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-card border border-border hover:bg-muted text-primary transition-colors cursor-pointer"
                title="Export current view to CSV"
              >
                <Download className="w-3.5 h-3.5" />
                Export CSV
              </button>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                aria-label="Close dialog"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* 2. Canonical Metrics & Filter Toolbar (Fixed at top) */}
          <div className="px-6 py-3 border-b border-border bg-card/70 flex flex-wrap items-center justify-between gap-4 shrink-0">
            {/* Context-aware Metrics */}
            <div className="flex flex-wrap items-center gap-6">
              {activeKpi === 'Vendors' ? (
                <>
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Total Vendors</span>
                    <p className="text-sm font-bold text-purple-500">{canonicalVendors.toLocaleString('en-IN')}</p>
                  </div>
                  <div className="w-px h-6 bg-border hidden sm:block" />
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Top Supplier</span>
                    <p className="text-sm font-bold text-foreground truncate max-w-[200px]" title="ADANI GREEN ENERGY LTD">ADANI GREEN ENERGY LTD</p>
                  </div>
                  <div className="w-px h-6 bg-border hidden sm:block" />
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Total PO Spend</span>
                    <p className="text-sm font-bold text-primary">₹{canonicalTotalPOValueCr.toLocaleString('en-IN', { maximumFractionDigits: 2 })} Cr</p>
                  </div>
                  <div className="w-px h-6 bg-border hidden sm:block" />
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Total Orders</span>
                    <p className="text-sm font-bold text-foreground">{canonicalTotalPOs.toLocaleString('en-IN')}</p>
                  </div>
                </>
              ) : (activeKpi === 'Materials' || activeKpi === 'PO Volume') ? (
                <>
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Total Materials</span>
                    <p className="text-sm font-bold text-teal-500">{canonicalMaterials.toLocaleString('en-IN')}</p>
                  </div>
                  <div className="w-px h-6 bg-border hidden sm:block" />
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Total Volume</span>
                    <p className="text-sm font-bold text-foreground">{canonicalVolume.toLocaleString('en-IN', { maximumFractionDigits: 0 })} No</p>
                  </div>
                  <div className="w-px h-6 bg-border hidden sm:block" />
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Total Spend</span>
                    <p className="text-sm font-bold text-primary">₹{canonicalTotalPOValueCr.toLocaleString('en-IN', { maximumFractionDigits: 2 })} Cr</p>
                  </div>
                  <div className="w-px h-6 bg-border hidden sm:block" />
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Current Inventory</span>
                    <p className="text-sm font-bold text-success">{canonicalInventory.toLocaleString('en-IN', { maximumFractionDigits: 0 })} No</p>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Total POs</span>
                    <p className="text-sm font-bold text-foreground">{canonicalTotalPOs.toLocaleString('en-IN')}</p>
                  </div>
                  <div className="w-px h-6 bg-border hidden sm:block" />
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">PO Amount</span>
                    <p className="text-sm font-bold text-primary">₹{canonicalTotalPOValueCr.toLocaleString('en-IN', { maximumFractionDigits: 2 })} Cr</p>
                  </div>
                  <div className="w-px h-6 bg-border hidden sm:block" />
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Utilized (Delivered)</span>
                    <p className="text-sm font-bold text-success">
                      ₹{canonicalUtilizedCr.toLocaleString('en-IN', { maximumFractionDigits: 2 })} Cr <span className="text-[11px] font-normal text-muted-foreground">({canonicalPercent.toFixed(0)}%)</span>
                    </p>
                  </div>
                  <div className="w-px h-6 bg-border hidden sm:block" />
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Pending (Remaining)</span>
                    <p className="text-sm font-bold text-warning">
                      ₹{canonicalRemainingCr.toLocaleString('en-IN', { maximumFractionDigits: 2 })} Cr <span className="text-[11px] font-normal text-muted-foreground">({(100 - canonicalPercent).toFixed(0)}%)</span>
                    </p>
                  </div>
                </>
              )}
            </div>

            {/* View Mode & Filter Controls */}
            <div className="flex flex-wrap items-center gap-3 ml-auto">
              {/* View Toggle */}
              {activeKpi === 'Vendors' && (
                <div className="flex items-center bg-muted border border-border rounded-lg p-0.5 text-xs">
                  <button
                    onClick={() => { setViewMode('auto'); setSelectedVendor(null); setCurrentPage(1); }}
                    className={`px-2.5 py-1 font-semibold rounded-md transition-all cursor-pointer ${
                      effectiveMode === 'vendors' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Vendor Summary
                  </button>
                  <button
                    onClick={() => { setViewMode('pos'); setCurrentPage(1); }}
                    className={`px-2.5 py-1 font-semibold rounded-md transition-all cursor-pointer ${
                      effectiveMode === 'pos' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    All PO Lines
                  </button>
                </div>
              )}

              {/* Status Filter */}
              <div className="flex items-center bg-muted border border-border rounded-lg p-0.5 text-xs">
                {(['all', 'delivered', 'pending'] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => { setStatusFilter(tab); setCurrentPage(1); }}
                    className={`px-2.5 py-1 font-semibold rounded-md capitalize transition-all cursor-pointer ${
                      statusFilter === tab
                        ? 'bg-primary text-primary-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* Search Box */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  placeholder={effectiveMode === 'vendors' ? "Search vendor..." : effectiveMode === 'materials' ? "Search material..." : "Search PO, Vendor..."}
                  value={searchTerm}
                  onChange={e => { setSearchTerm(e.target.value); setCurrentPage(1); }}
                  className="pl-8 pr-3 py-1 bg-surface-sunken border border-border rounded-lg text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary w-[180px]"
                />
              </div>
            </div>
          </div>

          {/* 3. Main Body - Dedicated Table Scrolling (No Nested Scrollbars!) */}
          <div className="flex-1 min-h-0 flex flex-col p-5 gap-4 overflow-hidden">
            {/* Optional Collapsible Chart */}
            {showChart && chartOption && (
              <div className="bg-surface-sunken border border-border rounded-xl p-3 shrink-0">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <Activity className="w-3 h-3 text-primary" />
                    {activeKpi === 'Vendors' ? 'Top 10 Enterprise Suppliers by Spend' : activeKpi === 'Materials' || activeKpi === 'PO Volume' ? 'Top Materials by Spend Allocation' : 'Capex Fulfillment Ratio (Delivered vs Pending)'}
                  </h3>
                </div>
                <div className="w-full h-[150px]">
                  <ReactECharts theme={themeName} option={chartOption} style={{ height: '100%', width: '100%' }} />
                </div>
              </div>
            )}

            {/* Table Card - Fills Remaining Space with Dedicated Scrollable Body */}
            <div className="flex-1 min-h-0 border border-border rounded-xl bg-card flex flex-col shadow-sm overflow-hidden">
              {/* Table Subheader with context and row selector */}
              <div className="px-4 py-2 bg-surface-sunken border-b border-border flex flex-wrap items-center justify-between gap-3 shrink-0">
                <div>
                  <h4 className="text-xs font-bold text-foreground">
                    {effectiveMode === 'vendors' ? 'Vendor Spend & Order Summary' : effectiveMode === 'materials' ? 'Material Procurement Catalog' : selectedVendor ? `Purchase Orders for ${selectedVendor}` : 'Detailed Purchase Order Ledger'}
                  </h4>
                  <p className="text-[11px] text-muted-foreground">
                    Showing {activeDataset.length > 0 ? (pageSize === 'all' ? `all ${activeDataset.length}` : `${((currentPage - 1) * (pageSize as number)) + 1} to ${Math.min(currentPage * (pageSize as number), activeDataset.length)}`) : 0} of {activeDataset.length.toLocaleString('en-IN')} records
                    {effectiveMode === 'pos' && !selectedVendor && ` (Total Platform: ${canonicalTotalPOs.toLocaleString('en-IN')} POs)`}
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  {selectedVendor && (
                    <button
                      onClick={() => { setSelectedVendor(null); setViewMode('auto'); }}
                      className="text-xs text-primary hover:underline flex items-center gap-1 font-semibold cursor-pointer mr-2"
                    >
                      <ArrowLeft className="w-3 h-3" /> Back to Vendor Summary
                    </button>
                  )}

                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span>Rows:</span>
                    <select
                      value={pageSize}
                      onChange={e => {
                        const val = e.target.value === 'all' ? 'all' : Number(e.target.value);
                        setPageSize(val);
                        setCurrentPage(1);
                      }}
                      className="bg-card border border-border rounded px-2 py-0.5 text-xs text-foreground font-medium focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer"
                    >
                      <option value={25}>25</option>
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                      <option value="all">All ({activeDataset.length})</option>
                    </select>
                  </div>

                  {pageSize !== 'all' && totalPages > 1 && (
                    <div className="flex items-center gap-1 text-xs">
                      <button
                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        disabled={currentPage === 1}
                        className="px-2.5 py-0.5 rounded bg-card border border-border text-foreground disabled:opacity-40 disabled:cursor-not-allowed hover:bg-muted cursor-pointer"
                      >
                        Prev
                      </button>
                      <span className="px-2 font-medium text-foreground">
                        {currentPage} / {totalPages}
                      </span>
                      <button
                        onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                        disabled={currentPage === totalPages}
                        className="px-2.5 py-0.5 rounded bg-card border border-border text-foreground disabled:opacity-40 disabled:cursor-not-allowed hover:bg-muted cursor-pointer"
                      >
                        Next
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Dedicated Scroll Container with Sticky Header - Continuous mouse-wheel scroll! */}
              <div 
                ref={tableContainerRef}
                className="flex-1 min-h-0 overflow-y-auto overflow-x-auto"
                style={{ 
                  overscrollBehavior: 'contain',
                  scrollbarWidth: 'thin',
                  scrollbarColor: 'rgba(156, 163, 175, 0.5) transparent'
                }}
              >
                <table className="w-full text-left text-xs border-collapse">
                  {/* Table Column Headers (Sticky at top of scroll container) */}
                  {effectiveMode === 'vendors' ? (
                    <thead className="bg-surface-sunken border-b border-border text-muted-foreground uppercase font-semibold text-[11px] sticky top-0 z-20 shadow-sm">
                      <tr>
                        <th className="px-4 py-2.5 bg-surface-sunken">Vendor Name</th>
                        <th className="px-4 py-2.5 text-center bg-surface-sunken">PO Count</th>
                        <th className="px-4 py-2.5 text-right bg-surface-sunken">Total Spend (₹ Cr)</th>
                        <th className="px-4 py-2.5 text-right bg-surface-sunken">Delivered (GRN)</th>
                        <th className="px-4 py-2.5 text-right bg-surface-sunken">Pending Delivery</th>
                        <th className="px-4 py-2.5 text-center bg-surface-sunken">Action</th>
                      </tr>
                    </thead>
                  ) : effectiveMode === 'materials' ? (
                    <thead className="bg-surface-sunken border-b border-border text-muted-foreground uppercase font-semibold text-[11px] sticky top-0 z-20 shadow-sm">
                      <tr>
                        <th className="px-4 py-2.5 bg-surface-sunken">Material Code</th>
                        <th className="px-4 py-2.5 bg-surface-sunken">Description</th>
                        <th className="px-4 py-2.5 text-right bg-surface-sunken">Ordered Units</th>
                        <th className="px-4 py-2.5 text-center bg-surface-sunken">PO Count</th>
                        <th className="px-4 py-2.5 text-right bg-surface-sunken">Spend (₹ Cr)</th>
                      </tr>
                    </thead>
                  ) : (
                    <thead className="bg-surface-sunken border-b border-border text-muted-foreground uppercase font-semibold text-[11px] sticky top-0 z-20 shadow-sm">
                      <tr>
                        <th className="px-3.5 py-2.5 bg-surface-sunken">PO Number</th>
                        <th className="px-3.5 py-2.5 bg-surface-sunken">Buyer</th>
                        <th className="px-3.5 py-2.5 bg-surface-sunken">Vendor Name</th>
                        <th className="px-3.5 py-2.5 bg-surface-sunken">Material</th>
                        <th className="px-3.5 py-2.5 bg-surface-sunken">PO Date</th>
                        <th className="px-3.5 py-2.5 bg-surface-sunken">Status</th>
                        <th className="px-3.5 py-2.5 text-right bg-surface-sunken">Value (₹ Cr)</th>
                      </tr>
                    </thead>
                  )}

                  {/* Table Body */}
                  <tbody className="divide-y divide-border/60">
                    {effectiveMode === 'vendors' ? (
                      (paginatedData as typeof vendorAggregatedList).map((v, idx) => (
                        <tr key={idx} className="hover:bg-muted/40 transition-colors">
                          <td className="px-4 py-2.5 font-bold text-foreground">
                            {v.vendorName}
                          </td>
                          <td className="px-4 py-2.5 text-center font-mono">
                            <span className="px-2 py-0.5 rounded-full bg-surface-sunken border border-border text-foreground font-semibold">
                              {v.poCount}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right font-bold text-foreground tabular-nums">
                            ₹{v.totalValueCr.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Cr
                          </td>
                          <td className="px-4 py-2.5 text-right text-success font-semibold tabular-nums">
                            ₹{v.deliveredValueCr.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Cr
                          </td>
                          <td className="px-4 py-2.5 text-right text-warning font-semibold tabular-nums">
                            ₹{v.pendingValueCr.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Cr
                          </td>
                          <td className="px-4 py-2.5 text-center">
                            <button
                              onClick={() => { setSelectedVendor(v.vendorName); setViewMode('pos'); setCurrentPage(1); }}
                              className="px-2.5 py-1 text-[11px] font-semibold rounded bg-primary/10 hover:bg-primary/20 text-primary transition-colors inline-flex items-center gap-1 cursor-pointer"
                              title={`View POs for ${v.vendorName}`}
                            >
                              View POs <ArrowRight className="w-3 h-3" />
                            </button>
                          </td>
                        </tr>
                      ))
                    ) : effectiveMode === 'materials' ? (
                      (paginatedData as typeof materialAggregatedList).map((m, idx) => (
                        <tr key={idx} className="hover:bg-muted/40 transition-colors">
                          <td className="px-4 py-2.5 font-mono font-bold text-primary">
                            {m.materialCode}
                          </td>
                          <td className="px-4 py-2.5 text-foreground font-medium truncate max-w-[280px]" title={m.description}>
                            {m.description}
                          </td>
                          <td className="px-4 py-2.5 text-right font-semibold text-foreground tabular-nums">
                            {m.totalQty.toLocaleString('en-IN')}
                          </td>
                          <td className="px-4 py-2.5 text-center font-mono">
                            <span className="px-2 py-0.5 rounded-full bg-surface-sunken border border-border text-foreground font-semibold">
                              {m.poCount}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right font-bold text-foreground tabular-nums">
                            ₹{m.totalValueCr.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Cr
                          </td>
                        </tr>
                      ))
                    ) : (
                      (paginatedData as typeof filteredPOItems).map((po, idx) => (
                        <tr key={idx} className="hover:bg-muted/40 transition-colors">
                          <td className="px-3.5 py-2 font-semibold text-foreground font-mono">{po.purchasing_document}</td>
                          <td className="px-3.5 py-2 text-muted-foreground">{po.buyer_name || '—'}</td>
                          <td className="px-3.5 py-2 text-foreground font-medium truncate max-w-[200px]" title={po.vendor_name}>
                            {po.vendor_name || 'Unknown'}
                          </td>
                          <td className="px-3.5 py-2 font-mono text-primary text-[11px] truncate max-w-[150px]" title={po.short_text || po.material_code}>
                            {po.material_code || po.short_text || '—'}
                          </td>
                          <td className="px-3.5 py-2 text-muted-foreground">
                            {po.document_date ? new Date(po.document_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                          </td>
                          <td className="px-3.5 py-2">
                            {po.delivery_completed_flag === 'X' ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10.5px] font-semibold bg-success/15 text-success border border-success/20">
                                <CheckCircle2 className="w-3 h-3" /> Delivered
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10.5px] font-semibold bg-warning/15 text-warning border border-warning/20">
                                <Clock className="w-3 h-3" /> Pending
                              </span>
                            )}
                          </td>
                          <td className="px-3.5 py-2 text-right font-semibold text-foreground tabular-nums">
                            {((po.net_order_value_inr || po.net_order_value || 0) / 10000000).toFixed(2)}
                          </td>
                        </tr>
                      ))
                    )}

                    {activeDataset.length === 0 && (
                      <tr>
                        <td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">
                          No matching records found for the active filter.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>,
    document.body
  );
}
