import React, { useEffect, useMemo } from 'react';
import ReactDOM from 'react-dom';
import { X, Layers, BarChart2 } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import { useNavigate } from 'react-router-dom';

interface KPIDetailsModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeKpi: string | null;
  projects: any[];
}

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
      const epsCounts: Record<string, number> = {};
      projects.forEach(p => {
        const eps = p.p6?.parent_eps_name || 'Unmapped';
        epsCounts[eps] = (epsCounts[eps] || 0) + (activeKpi === 'Total Projects' ? 1 : (p.capacity_mwac || 0));
      });
      return {
        title: activeKpi === 'Total Projects' ? 'Projects by Region' : 'Capacity (MW) by Region',
        type: activeKpi === 'Total Projects' ? 'pie' : 'bar',
        data: Object.entries(epsCounts).map(([name, value]) => ({ name, value: Math.round(value) })).sort((a, b) => b.value - a.value)
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
        })).reverse() // reverse for barh so largest is on top
      };
    }

    if (activeKpi === 'Average Progress') {
      const topProgress = [...projects].filter(p => p.p6?.progress > 0).sort((a, b) => b.p6.progress - a.p6.progress).slice(0, 15);
      return {
        title: 'Top Projects by Progress (%)',
        type: 'bar',
        data: topProgress.map(p => ({
          name: p.p6_project_name?.substring(0, 20) + '...',
          value: Math.round(p.p6.progress * 100)
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
      const completed = [...projects].filter(p => p.p6?.progress >= 1);
      const epsCounts: Record<string, number> = {};
      completed.forEach(p => {
        const eps = p.p6?.parent_eps_name || 'Unmapped';
        epsCounts[eps] = (epsCounts[eps] || 0) + 1;
      });
      return {
        title: 'Completed Projects by Region',
        type: 'pie',
        data: Object.entries(epsCounts).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value)
      };
    }

    if (activeKpi === 'Cost Variance') {
      const topVariance = [...projects].map(p => {
        const poValCr = (p.sap?.po_value || 0) / 10000000;
        const deliveredCr = p.sap?.po_delivered_cr || 0;
        const variance = deliveredCr - poValCr;
        return { name: p.project_name?.substring(0, 20) + '...', value: variance };
      }).sort((a, b) => Math.abs(b.value) - Math.abs(a.value)).slice(0, 15);

      return {
        title: 'Largest Cost Variances (SAP PO)',
        type: 'barh',
        data: topVariance.reverse()
      };
    }

    return null;
  }, [projects, activeKpi]);

  const filteredProjectsList = useMemo(() => {
    if (!projects || !activeKpi) return [];

    let list = [...projects];

    if (activeKpi === 'Total Projects' || activeKpi === 'Portfolio Capacity') {
      if (filterCategory) {
        list = list.filter(p => (p.p6?.parent_eps_name || 'Unmapped') === filterCategory);
      }
      return list.map(p => ({ id: p.project_id, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `${Math.round((p.p6?.progress || 0) * 100)}% Complete` }));
    }

    if (activeKpi === 'Delayed Projects') {
      list = list.filter(p => p.p6?.health === 'Delayed');
      if (filterCategory) list = list.filter(p => ((p.p6_project_name || p.project_name || '').substring(0, 20) + '...') === filterCategory);
      return list.map(p => ({ id: p.project_id, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `${getDelayDays(p)} Days Delayed` })).sort((a: any, b: any) => parseInt(b.value) - parseInt(a.value));
    }

    if (activeKpi === 'Average Progress') {
      list = list.filter(p => p.p6?.progress > 0).sort((a, b) => b.p6.progress - a.p6.progress);
      if (filterCategory) list = list.filter(p => (p.p6_project_name?.substring(0, 20) + '...') === filterCategory || (p.project_name?.substring(0, 20) + '...') === filterCategory);
      return list.map(p => ({ id: p.project_id, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `${Math.round(p.p6.progress * 100)}%` }));
    }

    if (activeKpi === 'Total PO Value') {
      list = list.filter(p => p.sap?.po_value > 0).sort((a, b) => b.sap.po_value - a.sap.po_value);
      if (filterCategory) list = list.filter(p => (p.p6_project_name?.substring(0, 20) + '...') === filterCategory || (p.project_name?.substring(0, 20) + '...') === filterCategory);
      return list.map(p => ({ id: p.project_id, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `₹${(p.sap.po_value / 10000000).toFixed(2)} Cr` }));
    }

    if (activeKpi === 'Completed Projects') {
      list = list.filter(p => p.p6?.progress >= 1);
      if (filterCategory) list = list.filter(p => (p.p6?.parent_eps_name || 'Unmapped') === filterCategory);
      return list.map(p => ({ id: p.project_id, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `100% Complete` }));
    }

    if (activeKpi === 'Cost Variance') {
      list = list.filter(p => {
        const poValCr = (p.sap?.po_value || 0) / 10000000;
        const deliveredCr = p.sap?.po_delivered_cr || 0;
        return (deliveredCr - poValCr) !== 0;
      });
      if (filterCategory) list = list.filter(p => (p.p6_project_name?.substring(0, 20) + '...') === filterCategory || (p.project_name?.substring(0, 20) + '...') === filterCategory);
      return list.map(p => {
        const poValCr = (p.sap?.po_value || 0) / 10000000;
        const deliveredCr = p.sap?.po_delivered_cr || 0;
        const variance = deliveredCr - poValCr;
        return { id: p.project_id, name: p.p6_project_name || p.project_name || 'Unknown Project', value: `₹${variance.toFixed(1)} Cr` };
      });
    }

    return [];
  }, [projects, activeKpi, filterCategory]);

  const onChartClick = (params: any) => {
    setFilterCategory(params.name);
  };

  const renderChart = () => {
    if (!chartData) return null;

    let options: any = {
      color: ['#2563eb', '#059669', '#d97706', '#7c3aed', '#0284c7', '#dc2626', '#4f46e5', '#ea580c', '#0d9488', '#9333ea'],
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'Adani, sans-serif' },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      title: { show: false },
      legend: { textStyle: { color: '#64748b', fontFamily: 'Adani' }, top: 0, right: 0, type: 'scroll', orient: 'horizontal' },
    };

    if (chartData.type === 'pie') {
      options = {
        ...options,
        tooltip: { trigger: 'item' },
        series: [{
          type: 'pie',
          radius: ['35%', '55%'],
          center: ['50%', '55%'],
          itemStyle: { borderColor: '#ffffff', borderWidth: 3, borderRadius: 4 },
          data: chartData.data,
          label: { color: '#0f172a', fontFamily: 'Adani', fontWeight: 'bold' }
        }]
      };
    } else if (chartData.type === 'bar') {
      options = {
        ...options,
        grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
        xAxis: { type: 'category', data: chartData.data.map((d: any) => d.name), axisLabel: { color: '#0f172a', interval: 0, rotate: 30, fontFamily: 'Adani', fontWeight: 'bold' } },
        yAxis: { type: 'value', axisLabel: { color: '#64748b', fontFamily: 'Adani' }, splitLine: { lineStyle: { color: '#e2e8f0' } } },
        series: [{ type: 'bar', data: chartData.data.map((d: any) => d.value), itemStyle: { color: '#2563eb' } }]
      };
    } else if (chartData.type === 'barh') {
      options = {
        ...options,
        grid: { left: '1%', right: '8%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: { type: 'value', axisLabel: { color: '#64748b', fontFamily: 'Adani' }, splitLine: { lineStyle: { color: '#e2e8f0' } } },
        yAxis: { type: 'category', data: chartData.data.map((d: any) => d.name), axisLabel: { color: '#0f172a', fontFamily: 'Adani', fontWeight: 'bold', width: 150, overflow: 'truncate' } },
        series: [{ 
          type: 'bar', 
          data: chartData.data.map((d: any) => d.value), 
          itemStyle: { color: '#ef4444', borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: 'right', fontFamily: 'Adani', fontWeight: 'bold', color: '#0f172a' }
        }]
      };
      if (activeKpi === 'Cost Variance') {
        options.series[0].itemStyle.color = (params: any) => params.value > 0 ? '#ef4444' : '#10b981';
      }
    } else if (chartData.type === 'pie' && activeKpi === 'Completed Projects') {
        options = {
          ...options,
          tooltip: { trigger: 'item' },
          series: [{
            type: 'pie',
            radius: ['35%', '55%'],
            center: ['50%', '55%'],
            itemStyle: { borderColor: '#ffffff', borderWidth: 3, borderRadius: 4 },
            data: chartData.data,
            label: { color: '#0f172a', fontFamily: 'Adani', fontWeight: 'bold' }
          }]
        };
    }

    return (
      <div className="w-full h-full min-h-[400px]">
        <ReactECharts option={options} style={{ height: '100%', width: '100%' }} onEvents={{ click: onChartClick }} />
      </div>
    );
  };

  const modalContent = (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-[100] bg-black/70 pointer-events-auto"
            data-lenis-prevent="true"
          />
          <div className="fixed inset-0 z-[100] flex items-center justify-center pointer-events-none p-4 sm:p-6" data-lenis-prevent="true">
            <motion.div
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              className="w-full max-w-7xl bg-card border border-border/60 shadow-2xl rounded-2xl overflow-hidden flex flex-col max-h-[90vh] pointer-events-auto"
            >
              {/* Premium Header */}
              <div className="flex items-center justify-between px-6 py-5 border-b border-border/40 bg-card/80 backdrop-blur-sm shrink-0">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                    <BarChart2 className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h2 className="text-lg font-bold text-foreground leading-tight tracking-tight">{activeKpi} Analysis</h2>
                    <p className="text-xs text-muted-foreground mt-0.5">Performance Breakdown & Contributing Assets</p>
                  </div>
                </div>
                <button onClick={onClose} className="p-2.5 bg-muted/50 hover:bg-muted rounded-full transition-colors text-muted-foreground">
                  <X className="w-5 h-5" />
                </button>
              </div>
            
              <div className="flex-1 flex flex-col lg:flex-row overflow-hidden bg-background">
                {/* Left Column - Chart */}
                <div className="w-full lg:w-[50%] p-8 border-b lg:border-b-0 lg:border-r border-border/40 flex flex-col bg-card/30 relative">
                   <div className="mb-6 shrink-0">
                     <h3 className="text-base font-bold text-foreground mb-1">{chartData?.title}</h3>
                     <p className="text-sm text-muted-foreground">Select any segment to filter the data list.</p>
                   </div>
                   <div className="flex-1 w-full min-h-[350px]">
                      {renderChart()}
                   </div>
                </div>
                
                {/* Right Column - Data List */}
                <div className="w-full lg:w-[50%] flex flex-col overflow-hidden bg-card/50">
                  <div className="px-6 py-5 flex items-center justify-between border-b border-border/40 shrink-0 bg-card/80 backdrop-blur-sm">
                    <h3 className="text-sm font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
                      <Layers className="w-4 h-4 text-primary" />
                      {filterCategory ? `Filtered: ${filterCategory}` : 'Contributing Assets'}
                    </h3>
                    {filterCategory && (
                      <button onClick={() => setFilterCategory(null)} className="text-xs bg-primary/10 text-primary px-3 py-1.5 rounded-lg hover:bg-primary/20 font-bold transition-colors">
                        Clear Filter
                      </button>
                    )}
                  </div>
                  
                  <div className="flex-1 overflow-y-auto custom-scrollbar p-3">
                    <div className="space-y-1">
                      {filteredProjectsList.slice(0, 50).map((item: any, idx: number) => {
                        const isRed = item.value.includes('Delayed') || item.value.includes('-');
                        return (
                          <div 
                            key={idx} 
                            onClick={() => {
                              if (item.id) {
                                onClose();
                                navigate(`/akasha/dashboard/project/${encodeURIComponent(item.id)}${activeKpi === 'Cost Variance' || activeKpi === 'Total PO Value' ? '?tab=sap' : ''}`);
                              }
                            }}
                            className={`flex justify-between items-center px-4 py-3 rounded-xl hover:bg-muted/50 transition-colors ${item.id ? 'cursor-pointer hover:shadow-sm hover:border-primary/20 border border-transparent' : 'cursor-default'}`}
                          >
                            <div className="flex flex-col pr-4 overflow-hidden">
                              <span className="text-sm font-semibold text-foreground truncate group-hover:text-primary transition-colors" title={item.name}>{item.name}</span>
                            </div>
                            <div className="shrink-0 text-right">
                              <span className={`text-sm font-bold ${isRed ? 'text-red-500' : 'text-primary'}`}>
                                {item.value}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                      {filteredProjectsList.length === 0 && (
                        <div className="flex flex-col items-center justify-center h-40 text-muted-foreground opacity-60">
                          <Layers className="w-8 h-8 mb-3 opacity-40" />
                          <span className="text-sm font-medium">No assets found.</span>
                        </div>
                      )}
                    </div>
                    {filteredProjectsList.length > 50 && (
                      <div className="text-xs text-center py-4 text-muted-foreground font-medium mt-2">
                        Showing Top 50 of {filteredProjectsList.length} Assets
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
  );

  return typeof document !== 'undefined' ? ReactDOM.createPortal(modalContent, document.body) : null;
}
