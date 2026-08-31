import React, { useEffect, useMemo } from 'react';
import ReactDOM from 'react-dom';
import { X, Layers, BarChart2, Target, AlertTriangle, Activity, Briefcase, CheckCircle2, ChevronRight, Hash, Shield } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import { useNavigate } from 'react-router-dom';

interface KPIDetailsModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeKpi: string | null;
  projects: any[];
  summary?: any;
}

const kpiConfig: Record<string, { icon: React.ElementType, gradient: string, glow: string, bg: string }> = {
  'Total Projects': { icon: Briefcase, gradient: 'from-blue-500 to-indigo-500', glow: 'shadow-blue-500/20', bg: 'bg-primary/10 text-primary' },
  'Portfolio Capacity': { icon: Activity, gradient: 'from-cyan-400 to-blue-500', glow: 'shadow-cyan-500/20', bg: 'bg-cyan-500/10 text-cyan-500' },
  'Delayed Projects': { icon: AlertTriangle, gradient: 'from-rose-500 to-red-600', glow: 'shadow-red-500/20', bg: 'bg-destructive/10 text-destructive' },
  'Average Progress': { icon: Target, gradient: 'from-emerald-400 to-teal-500', glow: 'shadow-emerald-500/20', bg: 'bg-success/10 text-success' },
  'Total PO Value': { icon: Hash, gradient: 'from-violet-500 to-purple-600', glow: 'shadow-purple-500/20', bg: 'bg-purple-500/10 text-purple-500' },
  'Completed Projects': { icon: CheckCircle2, gradient: 'from-green-400 to-emerald-500', glow: 'shadow-green-500/20', bg: 'bg-green-500/10 text-green-500' },
  'Remaining PO Value': { icon: Layers, gradient: 'from-orange-400 to-rose-500', glow: 'shadow-orange-500/20', bg: 'bg-warning/10 text-warning' },
  'Quality (Pulse)': { icon: Shield, gradient: 'from-amber-400 to-orange-500', glow: 'shadow-orange-500/20', bg: 'bg-warning/10 text-warning' },
};

export default function KPIDetailsModal({ isOpen, onClose, activeKpi, projects, summary }: KPIDetailsModalProps) {
  const [filterCategory, setFilterCategory] = React.useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      document.documentElement.style.overflow = 'hidden';
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose();
      };
      window.addEventListener('keydown', handleKeyDown);
      return () => {
        document.body.style.overflow = 'unset';
        document.documentElement.style.overflow = 'unset';
        window.removeEventListener('keydown', handleKeyDown);
      };
    } else {
      setFilterCategory(null);
    }
  }, [isOpen]);

  const getDelayDays = (p: any) => {
    if (!p.p6?.baseline_finish_date) return 0;
    const finishStr = p.p6?.scheduled_finish_date || p.p6?.finish_date;
    if (!finishStr) return 0;

    const finish = new Date(finishStr);
    const baseline = new Date(p.p6.baseline_finish_date);

    if (isNaN(finish.getTime()) || isNaN(baseline.getTime())) return 0;

    const diffTime = finish.getTime() - baseline.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays > 0 ? diffDays : 0;
  };

  const chartData = useMemo(() => {
    if (!projects || projects.length === 0 || !activeKpi) return null;

    if (activeKpi === 'Total Projects' || activeKpi === 'Portfolio Capacity') {
      const epsCounts: Record<string, number> = {};
      projects.forEach(p => {
        const eps = p.p6?.parent_eps_name || 'Unmapped';
        epsCounts[eps] = (epsCounts[eps] || 0) + (activeKpi === 'Total Projects' ? 1 : (p.capacity_mwac || 0));
      });
      return {
        title: activeKpi === 'Total Projects' ? 'Projects by EPS Node' : 'Capacity (MW) by EPS Node',
        type: activeKpi === 'Total Projects' ? 'pie' : 'bar',
        data: Object.entries(epsCounts).map(([name, value]) => ({ name, value: Math.round(value) })).sort((a, b) => b.value - a.value)
      };
    }

    if (activeKpi === 'Delayed Projects') {
      const delayed = projects.filter(p => p.p6?.health === 'Delayed')
        .sort((a, b) => getDelayDays(b) - getDelayDays(a))
        .slice(0, 15);
      return {
        title: 'Most Delayed Projects (Variance Days)',
        type: 'barh',
        data: delayed.map(p => ({
          name: (p.p6_project_name || p.project_name || '').substring(0, 20) + '...',
          value: getDelayDays(p)
        })).reverse()
      };
    }

    if (activeKpi === 'Average Progress') {
      const topProgress = [...projects].filter(p => p.p6?.progress > 0).sort((a, b) => b.p6.progress - a.p6.progress).slice(0, 15);
      return {
        title: 'Top Projects by Progress (%)',
        type: 'bar',
        data: topProgress.map(p => ({
          name: p.p6_project_name?.substring(0, 20) + '...',
          value: Math.round(p.p6.progress)
        }))
      };
    }

    if (activeKpi === 'Total PO Value') {
      const topPO = [...projects].filter(p => p.sap?.po_value > 0).sort((a, b) => b.sap.po_value - a.sap.po_value).slice(0, 15);
      return {
        title: 'Top Projects by PO Value (Cr)',
        type: 'bar',
        data: topPO.map(p => ({
          name: p.project_name?.substring(0, 20) + '...',
          value: parseFloat((p.sap.po_value / 10000000).toFixed(2))
        }))
      };
    }

    if (activeKpi === 'Completed Projects') {
      const completed = [...projects].filter(p => {
        const rawProg = p.p6?.progress;
        let prog = 0;
        if (typeof rawProg === 'string' && rawProg.includes('%')) {
          prog = parseFloat(rawProg.replace('%', ''));
        } else {
          prog = Number(rawProg) || 0;
        }
        return prog >= 99.9;
      });

      const epsCounts: Record<string, number> = {};
      completed.forEach(p => {
        const eps = p.p6?.parent_eps_name?.replace('EPS Node: ', '').trim() || 'Unmapped';
        epsCounts[eps] = (epsCounts[eps] || 0) + 1;
      });

      const data = Object.entries(epsCounts).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);

      return {
        title: 'Completed Projects by Portfolio',
        type: 'pie',
        data: data.length > 0 ? data : [{ name: 'No Completed Projects', value: 0 }]
      };
    }

    if (activeKpi === 'Remaining PO Value') {
      const topRemaining = [...projects].map(p => {
        const poValCr = (p.sap?.po_value || 0) / 10000000;
        const deliveredCr = p.sap?.po_delivered_cr || 0;
        const remaining = poValCr - deliveredCr;
        return { name: p.project_name || p.p6_project_name || 'Unknown', value: parseFloat(remaining.toFixed(1)) };
      }).filter(p => p.value > 0).sort((a, b) => b.value - a.value).slice(0, 15);

      return {
        title: 'Largest Open PO Values (Pending Delivery)',
        type: 'barh',
        data: topRemaining // removed .reverse() so the largest is at index 0 and rendered at top using inverse: true
      };
    }

    if (activeKpi === 'Quality (Pulse)') {
      const topContractors = summary?.quality?.top_contractors || [];
      return {
        title: 'Top Contractors by Open NCs',
        type: 'barh',
        data: topContractors
      };
    }

    return null;
  }, [projects, activeKpi, summary]);

  const filteredProjectsList = useMemo(() => {
    if (!projects || !activeKpi) return [];

    let list = [...projects];

    const mapItem = (p: any, value: string, sub: string) => {
      const codDateStr = p.p6?.planned_finish_date || p.p6?.scheduled_finish_date || p.p6?.finish_date;
      const cod = codDateStr ? new Date(codDateStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A';
      let progress = 0;
      if (typeof p.p6?.progress === 'string' && p.p6.progress.includes('%')) {
        progress = parseFloat(p.p6.progress.replace('%', ''));
      } else {
        progress = Number(p.p6?.progress) || 0;
      }

      let status = 'On Track';
      let statusColor = 'bg-primary/10 text-primary border-primary/20 dark:bg-primary/10';

      let codMw = p.cod_mw || 0;
      let trMw = p.tr_mw || 0;
      const capacityMw = p.capacity_mwac || 0;
      const isFullyDone = (codMw > 0 && codMw >= capacityMw * 0.99);
      const isPartiallyDone = !isFullyDone && codMw > 0;
      const hasTR = trMw > 0;
      
      let isCrossedTimeline = false;
      if (codDateStr) {
        const codDate = new Date(codDateStr);
        if (!isNaN(codDate.getTime()) && codDate.getTime() < Date.now()) {
          isCrossedTimeline = true;
        }
      }
      
      const isDelayed = p.p6?.health === 'Delayed';

      if (isFullyDone) {
        status = 'COD Done';
        statusColor = 'bg-success/10 text-success border-success/20 dark:bg-success/10';
      } else if (isPartiallyDone) {
        status = `COD Partial (${codMw} MW)`;
        statusColor = 'bg-success/10 text-success border-success/20 dark:bg-success/10';
        if (hasTR) {
          status += ` + TR (${trMw} MW)`;
        }
      } else if (hasTR) {
        status = `Trial Run (${trMw} MW)`;
        statusColor = 'bg-blue-500/10 text-blue-500 border-blue-500/20 dark:bg-blue-500/10';
      } else if (isCrossedTimeline) {
        status = 'Crossed Timeline (COD Not Done)';
        statusColor = 'bg-destructive/10 text-destructive border-destructive/20 dark:bg-destructive/10';
      } else if (isDelayed) {
        status = 'Lagging (COD Not Done)';
        statusColor = 'bg-warning/10 text-warning-foreground border-warning/30 dark:bg-warning/10 dark:text-orange-400';
      }

      const baselineStr = p.p6?.baseline_finish_date;
      const baseline = baselineStr ? new Date(baselineStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A';

      return {
        id: p.p6?.id || p.project_name,
        name: p.p6_project_name || p.project_name || 'Unknown Project',
        value,
        sub,
        cod,
        baseline,
        forecast: cod,
        progress: Math.round(progress),
        capacity: p.capacity_mwac || 0,
        status,
        statusColor
      };
    };

    if (activeKpi === 'Total Projects' || activeKpi === 'Portfolio Capacity') {
      let list = [...projects];
      if (filterCategory) {
        list = list.filter(p => (p.p6?.parent_eps_name || 'Unmapped') === filterCategory);
      }
      return list.map(p => mapItem(p, activeKpi === 'Total Projects' ? `${Math.round(p.p6?.progress || 0)}%` : `${p.capacity_mwac || 0}`, activeKpi === 'Total Projects' ? 'Complete' : 'MW'));
    }

    if (activeKpi === 'Delayed Projects') {
      list = list.filter(p => p.p6?.health === 'Delayed');
      if (filterCategory) list = list.filter(p => ((p.p6_project_name || p.project_name || '').substring(0, 20) + '...') === filterCategory);
      return list.map(p => mapItem(p, `${getDelayDays(p)}d`, 'Delayed')).sort((a: any, b: any) => parseInt(b.value) - parseInt(a.value));
    }

    if (activeKpi === 'Average Progress') {
      list = list.filter(p => p.p6?.progress > 0).sort((a, b) => b.p6.progress - a.p6.progress);
      if (filterCategory) list = list.filter(p => (p.p6_project_name?.substring(0, 20) + '...') === filterCategory || (p.project_name?.substring(0, 20) + '...') === filterCategory);
      return list.map(p => mapItem(p, `${Math.round(p.p6.progress)}%`, 'Progress'));
    }

    if (activeKpi === 'Total PO Value') {
      list = list.filter(p => p.sap?.po_value > 0).sort((a, b) => b.sap.po_value - a.sap.po_value);
      if (filterCategory) list = list.filter(p => (p.p6_project_name?.substring(0, 20) + '...') === filterCategory || (p.project_name?.substring(0, 20) + '...') === filterCategory);
      return list.map(p => mapItem(p, `₹${(p.sap.po_value / 10000000).toFixed(1)}`, 'Cr'));
    }

    if (activeKpi === 'Completed Projects') {
      list = list.filter(p => {
        let prog = typeof p.p6?.progress === 'string' && p.p6.progress.includes('%') ? parseFloat(p.p6.progress.replace('%', '')) : (Number(p.p6?.progress) || 0);
        return prog >= 99.9;
      });
      if (filterCategory) list = list.filter(p => (p.p6?.parent_eps_name?.replace('EPS Node: ', '').trim() || 'Unmapped') === filterCategory);
      return list.map(p => mapItem(p, `100%`, 'Done'));
    }

    if (activeKpi === 'Remaining PO Value') {
      list = list.filter(p => {
        const poValCr = (p.sap?.po_value || 0) / 10000000;
        const deliveredCr = p.sap?.po_delivered_cr || 0;
        return (poValCr - deliveredCr) > 0;
      }).sort((a, b) => {
        const aVal = ((a.sap?.po_value || 0) / 10000000) - (a.sap?.po_delivered_cr || 0);
        const bVal = ((b.sap?.po_value || 0) / 10000000) - (b.sap?.po_delivered_cr || 0);
        return bVal - aVal;
      });
      if (filterCategory) list = list.filter(p => (p.p6_project_name?.substring(0, 20) + '...') === filterCategory || (p.project_name?.substring(0, 20) + '...') === filterCategory);
      return list.map(p => {
        const poValCr = (p.sap?.po_value || 0) / 10000000;
        const deliveredCr = p.sap?.po_delivered_cr || 0;
        const remaining = poValCr - deliveredCr;
        return mapItem(p, `₹${remaining.toFixed(1)}`, 'Cr Open');
      });
    }

    if (activeKpi === 'Quality (Pulse)') {
      const topContractors = summary?.quality?.top_contractors || [];
      const contractorsToShow = filterCategory 
        ? topContractors.filter((c: any) => c.name === filterCategory)
        : topContractors;

      const pulseItems: any[] = [];
      contractorsToShow.forEach((c: any) => {
        if (c.projects) {
          c.projects.forEach((p: any) => {
            pulseItems.push({
              id: p.p6_id || p.mapping_id || '', 
              name: p.p6_name || p.project_name,
              value: `${p.open_ncs}`,
              sub: 'Open NCs',
              status: 'Quality Issue',
              statusColor: 'bg-warning/10 text-warning border-warning/30',
              isPulseData: true
            });
          });
        }
      });
      return pulseItems.sort((a, b) => parseInt(b.value) - parseInt(a.value));
    }

    return [];
  }, [projects, activeKpi, filterCategory]);

  const onChartClick = (params: any) => {
    if (activeKpi === 'Portfolio Capacity' || activeKpi === 'Total Projects') {
      setFilterCategory(params.name);
    } else {
      setFilterCategory(params.name);
    }
  };

  const renderChart = () => {
    if (!chartData || !activeKpi) return null;
    const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
    const axisLabelColor = isDark ? '#94a3b8' : '#64748b';
    const textMainColor = isDark ? '#f1f5f9' : '#1e293b';
    const textSubColor = isDark ? '#cbd5e1' : '#475569';
    const splitLineColor = isDark ? '#334155' : '#e2e8f0';
    const tooltipBgColor = isDark ? 'rgba(30, 41, 59, 0.95)' : 'rgba(255, 255, 255, 0.95)';
    const tooltipTextColor = isDark ? '#f8fafc' : '#0f172a';
    const tooltipBorderColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';

    let options: any = {
      color: [
        '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
        '#06b6d4', '#ec4899', '#f97316', '#14b8a6', '#6366f1',
        '#84cc16', '#a855f7', '#0ea5e9', '#f43f5e', '#10b981'
      ],
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'Adani, sans-serif' },
      tooltip: { 
        trigger: 'item', 
        axisPointer: { type: 'shadow' },
        backgroundColor: tooltipBgColor,
        borderColor: tooltipBorderColor,
        textStyle: { color: tooltipTextColor }
      },
      legend: { 
        type: 'scroll', 
        textStyle: { color: axisLabelColor, fontFamily: 'Adani' }, 
        top: 0, 
        right: 10,
        pageIconColor: '#3b82f6',
        pageTextStyle: { color: axisLabelColor }
      },
    };

    if (chartData.type === 'pie') {
      options = {
        ...options,
        tooltip: { trigger: 'item' },
        series: [{
          type: 'pie',
          radius: ['45%', '70%'],
          center: ['50%', '55%'],
          data: chartData.data,
          itemStyle: {
            borderColor: isDark ? '#020817' : '#ffffff',
            borderWidth: 2
          },
          label: { color: textMainColor, fontFamily: 'Adani', fontWeight: 'bold' }
        }]
      };

    } else if (chartData.type === 'barh') {
      let barColor = '#10B981';
      if (activeKpi === 'Delayed Projects') barColor = '#ef4444';
      else if (activeKpi === 'Quality (Pulse)') barColor = '#f59e0b';
      else if (activeKpi === 'Remaining PO Value') barColor = '#3b82f6';

      options = {
        ...options,
        grid: { left: '1%', right: '10%', bottom: '2%', top: '5%', containLabel: true },
        xAxis: { type: 'value', axisLabel: { color: axisLabelColor, fontFamily: 'Adani' }, splitLine: { lineStyle: { color: splitLineColor, type: 'dashed', opacity: 0.6 } } },
        yAxis: { type: 'category', inverse: true, data: (chartData.data || []).map((d: any) => d.name), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: textMainColor, fontFamily: 'Adani', fontWeight: 'bold', width: 140, overflow: 'truncate' } },
        series: [{ 
          type: 'bar', 
          data: (chartData.data || []).map((d: any) => d.value), 
          itemStyle: { color: barColor, borderRadius: [0, 6, 6, 0] },
          label: { show: true, position: 'right', fontFamily: 'Adani', fontWeight: 'bold', color: textMainColor },
          barMaxWidth: 30
        }]
      };
    } else if (chartData.type === 'bar') {
      let barColor = '#3b82f6';
      if (activeKpi === 'Total PO Value') barColor = '#8b5cf6';
      else if (activeKpi === 'Average Progress') barColor = '#10b981';

      options = {
        ...options,
        grid: { left: '1%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
        xAxis: { type: 'category', data: (chartData.data || []).map((d: any) => d.name), axisLabel: { color: textSubColor, fontFamily: 'Adani', rotate: 30, interval: 0, width: 100, overflow: 'truncate' } },
        yAxis: { type: 'value', axisLabel: { color: axisLabelColor, fontFamily: 'Adani' }, splitLine: { lineStyle: { color: splitLineColor, type: 'dashed', opacity: 0.6 } } },
        series: [{ 
          type: 'bar', 
          data: (chartData.data || []).map((d: any) => d.value), 
          itemStyle: { color: barColor, borderRadius: [6, 6, 0, 0] },
          label: { show: true, position: 'top', fontFamily: 'Adani', fontWeight: 'bold', color: textMainColor },
          barMaxWidth: 40
        }]
      };
    }

    return (
      <div className="w-full h-full min-h-[400px]">
        <ReactECharts option={options} style={{ height: '100%', width: '100%' }} onEvents={{ click: onChartClick }} />
      </div>
    );
  };

  const currentConfig = activeKpi ? kpiConfig[activeKpi] || kpiConfig['Total Projects'] : kpiConfig['Total Projects'];
  const HeaderIcon = currentConfig.icon;

  return typeof document !== 'undefined' ? ReactDOM.createPortal(
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.2 } }}
            onClick={onClose}
            className="fixed inset-0 z-[100] bg-white/40 backdrop-blur-md pointer-events-auto"
           
          />
          
          <div className="fixed inset-0 z-[100] flex items-center justify-center pointer-events-none p-4 sm:p-6 lg:p-8">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0, transition: { type: "spring", damping: 25, stiffness: 300 } }}
              exit={{ opacity: 0, scale: 0.95, y: 20, transition: { duration: 0.2 } }}
              className={`w-full max-w-[90vw] 2xl:max-w-[85vw] bg-white/95 dark:bg-slate-950/95 backdrop-blur-xl border border-white dark:border-border shadow-2xl dark:shadow-black/50 ${currentConfig.glow} rounded-[2rem] overflow-hidden flex flex-col max-h-[90vh] pointer-events-auto ring-1 ring-black/5`}
            >
              <div className="relative px-8 py-6 border-b border-border/60 dark:border-border/60 bg-gradient-to-r from-slate-50/50 to-white/50 dark:from-slate-900/50 dark:to-slate-950/50 shrink-0">
                <div className="flex items-center justify-between relative z-10">
                  <div className="flex items-center gap-5">
                    <div className={`w-14 h-14 rounded-2xl ${currentConfig.bg} flex items-center justify-center shadow-inner`}>
                      <HeaderIcon className="w-7 h-7" />
                    </div>
                    <div>
                      <h2 className={`text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r ${currentConfig.gradient} leading-tight tracking-tight`}>
                        {activeKpi} Analysis
                      </h2>
                      <p className="text-sm text-muted-foreground dark:text-muted-foreground font-medium mt-1">Performance Breakdown & Contributing Assets</p>
                    </div>
                  </div>
                  <button onClick={onClose} className="p-3 bg-muted hover:bg-slate-200 dark:bg-card dark:hover:bg-slate-700 rounded-full transition-all text-muted-foreground hover:text-foreground dark:text-muted-foreground dark:hover:text-muted-foreground hover:rotate-90">
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
            
              <div className="flex-1 flex flex-col lg:flex-row overflow-hidden bg-white dark:bg-slate-950">
                <div className="w-full lg:w-[50%] p-8 border-b lg:border-b-0 lg:border-r border-border/60 dark:border-border/60 flex flex-col relative bg-muted dark:bg-gray-900/30">
                   {activeKpi === 'Remaining PO Value' ? (
                     <div className="flex flex-col gap-1 w-full shrink-0 mb-8">
                       <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground dark:text-muted-foreground mb-2">Largest Open PO Values (SAP PO)</h3>
                       <p className="text-xs text-muted-foreground dark:text-muted-foreground font-medium">Select any segment below to dynamically filter the asset list.</p>
                     </div>
                   ) : (
                     <div className="mb-8 shrink-0 flex justify-between items-end">
                       <div>
                         <h3 className="text-lg font-bold text-foreground dark:text-slate-100 mb-1">{chartData?.title}</h3>
                         <p className="text-sm text-muted-foreground dark:text-muted-foreground font-medium">Select any segment below to dynamically filter the asset list.</p>
                       </div>
                     </div>
                   )}
                   <div className="flex-1 w-full min-h-[350px]">
                      {renderChart()}
                   </div>
                </div>
                
                <div className="w-full lg:w-[50%] flex flex-col overflow-hidden bg-white dark:bg-slate-950 relative">
                  <div className="px-8 py-6 flex items-center justify-between border-b border-border/60 dark:border-border/60 shrink-0 sticky top-0 bg-white/80 dark:bg-slate-950/80 backdrop-blur-md z-10">
                    <div className="flex items-center gap-3">
                      <h3 className="text-sm font-bold text-foreground dark:text-slate-100 uppercase tracking-wider flex items-center gap-2">
                        <Layers className="w-4 h-4 text-primary dark:text-primary" />
                        {filterCategory ? `Filtered: ${filterCategory.replace('|', ' - ')}` : 'Contributing Assets'}
                      </h3>
                      <div className="flex items-center gap-1.5 bg-muted dark:bg-card px-2.5 py-1 rounded-md border border-border/50">
                        <span className="text-[11px] font-bold text-foreground dark:text-slate-200">{filteredProjectsList.length} items</span>
                        {(activeKpi === 'Portfolio Capacity' || activeKpi === 'Total Projects') && (
                          <>
                            <span className="text-[10px] text-muted-foreground">•</span>
                            <span className="text-[11px] font-bold text-primary dark:text-primary">
                              {Math.round(filteredProjectsList.reduce((acc: number, curr: any) => acc + (curr.capacity || 0), 0))} MW Total
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    {filterCategory && (
                      <motion.button 
                        initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                        onClick={() => setFilterCategory(null)} 
                        className="text-xs bg-muted dark:bg-card text-foreground dark:text-muted-foreground px-3 py-1.5 rounded-full hover:bg-slate-200 dark:hover:bg-slate-700 font-bold transition-colors"
                      >
                        Clear Filter
                      </motion.button>
                    )}
                  </div>
                  
                  <div className="flex-1 overflow-y-auto custom-scrollbar p-6 overscroll-contain" onWheel={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
                    <div className="space-y-3">
                      {filteredProjectsList.slice(0, 50).map((item: any, idx: number) => {
                        const isAlert = item.value.includes('Delay') || item.value.includes('-') || (item.value.includes('+') && activeKpi === 'Remaining PO Value');
                        const isDone = item.value.includes('100%') || item.progress === 100;
                        
                        return (
                          <motion.div 
                            initial={{ opacity: 0, x: 20 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: idx * 0.03, type: "spring", stiffness: 300, damping: 24 }}
                            key={idx} 
                            onClick={() => {
                              if (item.id) {
                                onClose();
                                navigate(`/ceo-dashboard/project/${encodeURIComponent(item.id)}${activeKpi === 'Remaining PO Value' || activeKpi === 'Total PO Value' ? '?tab=sap' : ''}`);
                              }
                            }}
                            className={`group flex justify-between items-center px-5 py-4 rounded-2xl transition-all duration-300 ${item.id ? 'cursor-pointer hover:bg-muted dark:hover:bg-white/5 hover:shadow-md hover:scale-[1.02] border border-muted dark:border-border' : 'cursor-default border border-transparent'}`}
                          >
                            <div className="flex items-center gap-4 overflow-hidden pr-4 flex-1">
                               <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 font-bold text-sm ${isAlert ? 'bg-destructive/10 dark:bg-destructive/10 text-destructive dark:text-destructive' : isDone ? 'bg-success/10 dark:bg-success/10 text-success dark:text-success' : 'bg-primary/10 dark:bg-primary/10 text-primary dark:text-primary'}`}>
                                 {item.name.substring(0, 1).toUpperCase()}
                               </div>
                               <div className="flex flex-col gap-1 min-w-0">
                                 <span className="text-sm font-semibold text-foreground dark:text-muted-foreground truncate group-hover:text-primary dark:group-hover:text-primary transition-colors" title={item.name}>{item.name}</span>
                                 <div className="flex items-center gap-2 flex-wrap">
                                   {item.status && activeKpi !== 'Delayed Projects' && (
                                     <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${item.statusColor}`}>
                                       {item.status}
                                     </span>
                                   )}
                                   {item.isPulseData ? (
                                      <span className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><span className="text-foreground/70 dark:text-slate-400">Source:</span> SAP Pulse (Quality)</span>
                                   ) : activeKpi === 'Delayed Projects' ? (
                                      <>
                                        <span className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><span className="text-foreground/70 dark:text-slate-400">Baseline:</span> {item.baseline}</span>
                                        <span className="text-muted-foreground/40">•</span>
                                        <span className="flex items-center gap-1 text-[11px] font-medium text-destructive"><span className="text-destructive">Forecast:</span> {item.forecast}</span>
                                      </>
                                   ) : (
                                      <>
                                        {item.cod && item.cod !== 'N/A' && <span className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><span className="text-foreground/70 dark:text-slate-400">COD:</span> {item.cod}</span>}
                                        {item.cod && item.cod !== 'N/A' && <span className="text-muted-foreground/40">•</span>}
                                        {item.capacity > 0 && activeKpi !== 'Portfolio Capacity' && <span className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><span className="text-foreground/70 dark:text-slate-400">Cap:</span> {item.capacity} MW</span>}
                                      </>
                                   )}
                                   {!item.isPulseData && activeKpi !== 'Portfolio Capacity' && <span className="text-muted-foreground/40">•</span>}
                                   {!item.isPulseData && <span className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground"><span className="text-foreground/70 dark:text-slate-400">Prog:</span> {item.progress}%</span>}
                                 </div>
                               </div>
                            </div>
                            <div className="shrink-0 flex items-center gap-3">
                              <div className={`flex items-baseline gap-1.5`}>
                                <span className={`text-lg font-bold ${isAlert ? 'text-destructive' : isDone ? 'text-success' : 'text-foreground dark:text-slate-100'}`}>
                                  {item.value}
                                </span>
                                {item.sub && (
                                  <span className="text-[10px] font-bold text-muted-foreground dark:text-muted-foreground uppercase tracking-wider">{item.sub}</span>
                                )}
                              </div>
                              <ChevronRight className={`w-4 h-4 ${isAlert ? 'text-red-300 dark:text-destructive/50' : isDone ? 'text-emerald-300 dark:text-success/50' : 'text-muted-foreground dark:text-foreground'} group-hover:translate-x-1 transition-transform`} />
                            </div>
                          </motion.div>
                        );
                      })}
                      {filteredProjectsList.length === 0 && (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center h-48 text-muted-foreground">
                          <Layers className="w-12 h-12 mb-4 opacity-20" />
                          <span className="text-sm font-medium">No assets found for this segment.</span>
                        </motion.div>
                      )}
                    </div>
                    {filteredProjectsList.length > 50 && (
                      <div className="text-xs text-center py-6 text-muted-foreground font-bold uppercase tracking-widest mt-4">
                        Showing Top 50 of {filteredProjectsList.length}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  , document.body) : null;
}
