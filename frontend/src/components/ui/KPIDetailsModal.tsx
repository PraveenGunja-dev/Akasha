import React, { useEffect, useMemo } from 'react';
import ReactDOM from 'react-dom';
import { X, Layers, BarChart2, Target, AlertTriangle, Activity, Briefcase, CheckCircle2, ChevronRight, Hash } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import { useNavigate } from 'react-router-dom';

interface KPIDetailsModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeKpi: string | null;
  projects: any[];
}

const kpiConfig: Record<string, { icon: React.ElementType, gradient: string, glow: string, bg: string }> = {
  'Total Projects': { icon: Briefcase, gradient: 'from-blue-500 to-indigo-500', glow: 'shadow-blue-500/20', bg: 'bg-blue-500/10 text-blue-500' },
  'Portfolio Capacity': { icon: Activity, gradient: 'from-cyan-400 to-blue-500', glow: 'shadow-cyan-500/20', bg: 'bg-cyan-500/10 text-cyan-500' },
  'Delayed Projects': { icon: AlertTriangle, gradient: 'from-rose-500 to-red-600', glow: 'shadow-red-500/20', bg: 'bg-red-500/10 text-red-500' },
  'Average Progress': { icon: Target, gradient: 'from-emerald-400 to-teal-500', glow: 'shadow-emerald-500/20', bg: 'bg-emerald-500/10 text-emerald-500' },
  'Total PO Value': { icon: Hash, gradient: 'from-violet-500 to-purple-600', glow: 'shadow-purple-500/20', bg: 'bg-purple-500/10 text-purple-500' },
  'Completed Projects': { icon: CheckCircle2, gradient: 'from-green-400 to-emerald-500', glow: 'shadow-green-500/20', bg: 'bg-green-500/10 text-green-500' },
  'Remaining PO Value': { icon: Layers, gradient: 'from-orange-400 to-rose-500', glow: 'shadow-orange-500/20', bg: 'bg-orange-500/10 text-orange-500' },
};

export default function KPIDetailsModal({ isOpen, onClose, activeKpi, projects }: KPIDetailsModalProps) {
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
      const epsSolar: Record<string, number> = {};
      const epsWind: Record<string, number> = {};
      const allEps = new Set<string>();

      projects.forEach(p => {
        const eps = p.p6?.parent_eps_name || 'Unmapped';
        allEps.add(eps);
        
        const nameUpper = (p.p6_project_name || p.project_name || '').toUpperCase();
        const isWind = nameUpper.includes('WIND') || nameUpper.includes('WTG');
        const value = activeKpi === 'Total Projects' ? 1 : (p.capacity_mwac || 0);

        if (isWind) {
          epsWind[eps] = (epsWind[eps] || 0) + value;
        } else {
          epsSolar[eps] = (epsSolar[eps] || 0) + value;
        }
      });
      
      const epsList = Array.from(allEps).sort((a, b) => {
        const totalA = (epsSolar[a] || 0) + (epsWind[a] || 0);
        const totalB = (epsSolar[b] || 0) + (epsWind[b] || 0);
        return totalB - totalA; // Sort by total descending
      });
      
      if (activeKpi === 'Total Projects') {
        const pieData = epsList.map(eps => ({
          name: eps,
          value: (epsSolar[eps] || 0) + (epsWind[eps] || 0)
        })).filter(d => d.value > 0);

        return {
          title: 'Projects by Region',
          type: 'pie',
          data: pieData
        };
      }

      const solarData = epsList.map(eps => Math.round(epsSolar[eps] || 0));
      const windData = epsList.map(eps => Math.round(epsWind[eps] || 0));

      return {
        title: activeKpi === 'Total Projects' ? 'Projects by Region (Solar vs Wind)' : 'Capacity (MW) by Region (Solar vs Wind)',
        type: 'stacked-bar',
        xAxisData: epsList,
        seriesData: [
          { name: 'Solar', data: solarData },
          { name: 'Wind', data: windData }
        ]
      };
    }

    if (activeKpi === 'Delayed Projects') {
      const delayed = projects.filter(p => p.p6?.health === 'Delayed')
        .sort((a, b) => getDelayDays(b) - getDelayDays(a)) // sort largest delay to top
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
        return { name: p.project_name?.substring(0, 20) + '...', value: parseFloat(remaining.toFixed(1)) };
      }).filter(p => p.value > 0).sort((a, b) => b.value - a.value).slice(0, 15);

      return {
        title: 'Largest Open PO Values (Pending Delivery)',
        type: 'barh',
        data: topRemaining.reverse()
      };
    }

    return null;
  }, [projects, activeKpi]);

  const filteredProjectsList = useMemo(() => {
    if (!projects || !activeKpi) return [];

    let list = [...projects];

    if (activeKpi === 'Total Projects' || activeKpi === 'Portfolio Capacity') {
      if (filterCategory) {
        if (activeKpi === 'Portfolio Capacity' && filterCategory.includes('|')) {
          const [region, tech] = filterCategory.split('|');
          list = list.filter(p => {
            const eps = p.p6?.parent_eps_name || 'Unmapped';
            const nameUpper = (p.p6_project_name || p.project_name || '').toUpperCase();
            const isWind = nameUpper.includes('WIND') || nameUpper.includes('WTG');
            const pTech = isWind ? 'Wind' : 'Solar';
            return eps === region && pTech === tech;
          });
        } else {
          list = list.filter(p => (p.p6?.parent_eps_name || 'Unmapped') === filterCategory);
        }
      }
      return list.map(p => ({ 
        id: p.p6?.id || p.project_name, 
        name: p.p6_project_name || p.project_name || 'Unknown Project', 
        value: activeKpi === 'Total Projects' ? `${Math.round(p.p6?.progress || 0)}%` : `${p.capacity_mwac || 0}`, 
        sub: activeKpi === 'Total Projects' ? 'Complete' : 'MW' 
      }));
    }

    if (activeKpi === 'Delayed Projects') {
      list = list.filter(p => p.p6?.health === 'Delayed');
      if (filterCategory) list = list.filter(p => ((p.p6_project_name || p.project_name || '').substring(0, 20) + '...') === filterCategory);
      return list.map(p => ({ id: p.p6?.id || p.project_name, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `${getDelayDays(p)}d`, sub: 'Delayed' })).sort((a: any, b: any) => parseInt(b.value) - parseInt(a.value));
    }

    if (activeKpi === 'Average Progress') {
      list = list.filter(p => p.p6?.progress > 0).sort((a, b) => b.p6.progress - a.p6.progress);
      if (filterCategory) list = list.filter(p => (p.p6_project_name?.substring(0, 20) + '...') === filterCategory || (p.project_name?.substring(0, 20) + '...') === filterCategory);
      return list.map(p => ({ id: p.p6?.id || p.project_name, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `${Math.round(p.p6.progress)}%`, sub: 'Progress' }));
    }

    if (activeKpi === 'Total PO Value') {
      list = list.filter(p => p.sap?.po_value > 0).sort((a, b) => b.sap.po_value - a.sap.po_value);
      if (filterCategory) list = list.filter(p => (p.p6_project_name?.substring(0, 20) + '...') === filterCategory || (p.project_name?.substring(0, 20) + '...') === filterCategory);
      return list.map(p => ({ id: p.p6?.id || p.project_name, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `₹${(p.sap.po_value / 10000000).toFixed(1)}`, sub: 'Cr' }));
    }

    if (activeKpi === 'Completed Projects') {
      list = list.filter(p => {
        const rawProg = p.p6?.progress;
        let prog = 0;
        if (typeof rawProg === 'string' && rawProg.includes('%')) {
          prog = parseFloat(rawProg.replace('%', ''));
        } else {
          prog = Number(rawProg) || 0;
        }
        return prog >= 99.9;
      });
      if (filterCategory) list = list.filter(p => (p.p6?.parent_eps_name?.replace('EPS Node: ', '').trim() || 'Unmapped') === filterCategory);
      return list.map(p => ({ id: p.p6?.id || p.project_name, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `100%`, sub: 'Done' }));
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
        return { id: p.p6?.id || p.project_name, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `₹${remaining.toFixed(1)}`, sub: 'Cr Open' };
      });
    }

    return [];
  }, [projects, activeKpi, filterCategory]);

  const onChartClick = (params: any) => {
    if (activeKpi === 'Portfolio Capacity') {
      setFilterCategory(`${params.name}|${params.seriesName}`);
    } else {
      setFilterCategory(params.name);
    }
  };

  const renderChart = () => {
    if (!chartData || !activeKpi) return null;
    const config = kpiConfig[activeKpi] || kpiConfig['Total Projects'];

    const barGradient = {
      type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
      colorStops: [{ offset: 0, color: '#38bdf8' }, { offset: 1, color: '#3b82f6' }]
    };
    
    const barhGradient = {
      type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
      colorStops: [{ offset: 0, color: '#f87171' }, { offset: 1, color: '#dc2626' }]
    };

    const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
    const axisLabelColor = isDark ? '#94a3b8' : '#64748b'; // slate-400 : slate-500
    const textMainColor = isDark ? '#f1f5f9' : '#1e293b'; // slate-100 : slate-800
    const textSubColor = isDark ? '#cbd5e1' : '#475569'; // slate-300 : slate-600
    const splitLineColor = isDark ? '#334155' : '#e2e8f0'; // slate-700 : slate-200
    const tooltipBgColor = isDark ? 'rgba(30, 41, 59, 0.95)' : 'rgba(255, 255, 255, 0.95)';
    const tooltipTextColor = isDark ? '#f8fafc' : '#0f172a';
    const tooltipBorderColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';

      let options: any = {
      color: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#0ea5e9', '#ef4444', '#6366f1', '#f97316', '#14b8a6', '#a855f7'],
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'Adani, sans-serif' },
      tooltip: { 
        trigger: 'axis', 
        axisPointer: { type: 'shadow' },
        backgroundColor: tooltipBgColor,
        borderColor: tooltipBorderColor,
        textStyle: { color: tooltipTextColor },
        borderRadius: 8,
        padding: [12, 16]
      },
      title: { show: false },
      legend: { textStyle: { color: axisLabelColor, fontFamily: 'Adani' }, top: 0, right: 0, type: 'scroll', orient: 'horizontal' },
    };

    if (chartData.type === 'pie') {
      options = {
        ...options,
        tooltip: { trigger: 'item', backgroundColor: tooltipBgColor, borderColor: tooltipBorderColor, textStyle: { color: tooltipTextColor } },
        series: [{
          type: 'pie',
          radius: ['45%', '70%'],
          center: ['50%', '55%'],
          itemStyle: { borderColor: isDark ? 'rgba(15,23,42,0.8)' : 'rgba(255,255,255,0.8)', borderWidth: 4, borderRadius: 8 },
          data: chartData.data,
          label: { color: textMainColor, fontFamily: 'Adani', fontWeight: 'bold' }
        }]
      };
    } else if (chartData.type === 'bar') {
      options = {
        ...options,
        grid: { left: '2%', right: '4%', bottom: '2%', top: '12%', containLabel: true },
        xAxis: { type: 'category', data: chartData.data.map((d: any) => d.name), axisLabel: { color: textSubColor, interval: 0, rotate: 25, fontFamily: 'Adani', fontWeight: 'bold' }, axisLine: { lineStyle: { color: splitLineColor } }, axisTick: { show: false } },
        yAxis: { type: 'value', axisLabel: { color: axisLabelColor, fontFamily: 'Adani' }, splitLine: { lineStyle: { color: splitLineColor, type: 'dashed', opacity: 0.6 } } },
        series: [{ type: 'bar', data: chartData.data.map((d: any) => d.value), itemStyle: { color: barGradient, borderRadius: [6, 6, 0, 0] }, barMaxWidth: 40 }]
      };
    } else if (chartData.type === 'stacked-bar') {
      options = {
        ...options,
        tooltip: { 
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          backgroundColor: tooltipBgColor,
          borderColor: tooltipBorderColor,
          textStyle: { color: tooltipTextColor }
        },
        grid: { left: '2%', right: '4%', bottom: '2%', top: '12%', containLabel: true },
        xAxis: { type: 'category', data: chartData.xAxisData, axisLabel: { color: textSubColor, interval: 0, rotate: 25, fontFamily: 'Adani', fontWeight: 'bold' }, axisLine: { lineStyle: { color: splitLineColor } }, axisTick: { show: false } },
        yAxis: { type: 'value', axisLabel: { color: axisLabelColor, fontFamily: 'Adani' }, splitLine: { lineStyle: { color: splitLineColor, type: 'dashed', opacity: 0.6 } } },
        series: chartData.seriesData.map((series: any) => ({
          name: series.name,
          type: 'bar',
          stack: 'total',
          data: series.data,
          barMaxWidth: 40,
          itemStyle: {
            color: series.name === 'Solar' ? { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#38bdf8' }, { offset: 1, color: '#0284c7' }] }
                 : { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#34d399' }, { offset: 1, color: '#059669' }] }
          }
        }))
      };
    } else if (chartData.type === 'barh') {
      options = {
        ...options,
        grid: { left: '1%', right: '10%', bottom: '2%', top: '5%', containLabel: true },
        xAxis: { type: 'value', axisLabel: { color: axisLabelColor, fontFamily: 'Adani' }, splitLine: { lineStyle: { color: splitLineColor, type: 'dashed', opacity: 0.6 } } },
        yAxis: { type: 'category', data: chartData.data.map((d: any) => d.name), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: textMainColor, fontFamily: 'Adani', fontWeight: 'bold', width: 140, overflow: 'truncate' } },
        series: [{ 
          type: 'bar', 
          data: chartData.data.map((d: any) => d.value), 
          itemStyle: { color: barhGradient, borderRadius: [0, 6, 6, 0] },
          label: { show: true, position: 'right', fontFamily: 'Adani', fontWeight: 'bold', color: textMainColor },
          barMaxWidth: 30
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
            className="fixed inset-0 z-[100] bg-slate-900/40 backdrop-blur-md pointer-events-auto"
            data-lenis-prevent="true"
          />
          
          <div className="fixed inset-0 z-[100] flex items-center justify-center pointer-events-none p-4 sm:p-6 lg:p-8" data-lenis-prevent="true">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0, transition: { type: "spring", damping: 25, stiffness: 300 } }}
              exit={{ opacity: 0, scale: 0.95, y: 20, transition: { duration: 0.2 } }}
              className={`w-full max-w-[90vw] 2xl:max-w-[85vw] bg-white/95 dark:bg-slate-950/95 backdrop-blur-xl border border-white dark:border-slate-800 shadow-2xl dark:shadow-black/50 ${currentConfig.glow} rounded-[2rem] overflow-hidden flex flex-col max-h-[90vh] pointer-events-auto ring-1 ring-black/5`}
            >
              <div className="relative px-8 py-6 border-b border-slate-200/60 dark:border-slate-800/60 bg-gradient-to-r from-slate-50/50 to-white/50 dark:from-slate-900/50 dark:to-slate-950/50 shrink-0">
                <div className="flex items-center justify-between relative z-10">
                  <div className="flex items-center gap-5">
                    <div className={`w-14 h-14 rounded-2xl ${currentConfig.bg} flex items-center justify-center shadow-inner`}>
                      <HeaderIcon className="w-7 h-7" />
                    </div>
                    <div>
                      <h2 className={`text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r ${currentConfig.gradient} leading-tight tracking-tight`}>
                        {activeKpi} Analysis
                      </h2>
                      <p className="text-sm text-slate-500 dark:text-slate-400 font-medium mt-1">Performance Breakdown & Contributing Assets</p>
                    </div>
                  </div>
                  <button onClick={onClose} className="p-3 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 rounded-full transition-all text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 hover:rotate-90">
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
            
              <div className="flex-1 flex flex-col lg:flex-row overflow-hidden bg-white dark:bg-slate-950">
                <div className="w-full lg:w-[50%] p-8 border-b lg:border-b-0 lg:border-r border-slate-200/60 dark:border-slate-800/60 flex flex-col relative bg-slate-50/30 dark:bg-slate-900/30">
                   {activeKpi === 'Remaining PO Value' ? (
                     <div className="flex flex-col gap-1 w-full h-full pb-8">
                       <h3 className="text-[11px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Largest Open PO Values (SAP PO)</h3>
                       <p className="text-xs text-slate-400 dark:text-slate-500 mb-6 font-medium">Select any segment below to dynamically filter the asset list.</p>
                     </div>
                   ) : (
                     <div className="mb-8 shrink-0 flex justify-between items-end">
                       <div>
                         <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 mb-1">{chartData?.title}</h3>
                         <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Select any segment below to dynamically filter the asset list.</p>
                       </div>
                     </div>
                   )}
                   <div className="flex-1 w-full min-h-[350px]">
                      {renderChart()}
                   </div>
                </div>
                
                <div className="w-full lg:w-[50%] flex flex-col overflow-hidden bg-white dark:bg-slate-950 relative">
                  <div className="px-8 py-6 flex items-center justify-between border-b border-slate-200/60 dark:border-slate-800/60 shrink-0 sticky top-0 bg-white/80 dark:bg-slate-950/80 backdrop-blur-md z-10">
                    <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 uppercase tracking-wider flex items-center gap-2">
                      <Layers className="w-4 h-4 text-indigo-500 dark:text-indigo-400" />
                      {filterCategory ? `Filtered: ${filterCategory.replace('|', ' - ')}` : 'Contributing Assets'}
                    </h3>
                    {filterCategory && (
                      <motion.button 
                        initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                        onClick={() => setFilterCategory(null)} 
                        className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-3 py-1.5 rounded-full hover:bg-slate-200 dark:hover:bg-slate-700 font-bold transition-colors"
                      >
                        Clear Filter
                      </motion.button>
                    )}
                  </div>
                  
                  <div className="flex-1 overflow-y-auto custom-scrollbar p-6 overscroll-contain" data-lenis-prevent="true" onWheel={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
                    <div className="space-y-3">
                      {filteredProjectsList.slice(0, 50).map((item: any, idx: number) => {
                        const isAlert = item.value.includes('Delay') || item.value.includes('-') || (item.value.includes('+') && activeKpi === 'Remaining PO Value');
                        const isDone = item.value.includes('100%');
                        
                        return (
                          <motion.div 
                            initial={{ opacity: 0, x: 20 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: idx * 0.03, type: "spring", stiffness: 300, damping: 24 }}
                            key={idx} 
                            onClick={() => {
                              if (item.id) {
                                onClose();
                                navigate(`/dashboard/project/${encodeURIComponent(item.id)}${activeKpi === 'Remaining PO Value' || activeKpi === 'Total PO Value' ? '?tab=sap' : ''}`);
                              }
                            }}
                            className={`group flex justify-between items-center px-5 py-4 rounded-2xl transition-all duration-300 ${item.id ? 'cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 hover:shadow-md hover:scale-[1.02] border border-slate-100 dark:border-slate-800' : 'cursor-default border border-transparent'}`}
                          >
                            <div className="flex items-center gap-4 overflow-hidden pr-4 flex-1">
                               <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 font-bold text-sm ${isAlert ? 'bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400' : isDone ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400'}`}>
                                 {item.name.substring(0, 1).toUpperCase()}
                               </div>
                               <span className="text-sm font-semibold text-slate-700 dark:text-slate-200 truncate group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors" title={item.name}>{item.name}</span>
                            </div>
                            <div className="shrink-0 flex items-center gap-3">
                              <div className={`flex items-baseline gap-1.5`}>
                                <span className={`text-base font-bold ${isAlert ? 'text-red-500' : isDone ? 'text-emerald-500' : 'text-slate-800 dark:text-slate-100'}`}>
                                  {item.value}
                                </span>
                                {item.sub && (
                                  <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">{item.sub}</span>
                                )}
                              </div>
                              <ChevronRight className={`w-4 h-4 ${isAlert ? 'text-red-300 dark:text-red-400/50' : isDone ? 'text-emerald-300 dark:text-emerald-400/50' : 'text-slate-300 dark:text-slate-600'} group-hover:translate-x-1 transition-transform`} />
                            </div>
                          </motion.div>
                        );
                      })}
                      {filteredProjectsList.length === 0 && (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center h-48 text-slate-400">
                          <Layers className="w-12 h-12 mb-4 opacity-20" />
                          <span className="text-sm font-medium">No assets found for this segment.</span>
                        </motion.div>
                      )}
                    </div>
                    {filteredProjectsList.length > 50 && (
                      <div className="text-xs text-center py-6 text-slate-400 font-bold uppercase tracking-widest mt-4">
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
