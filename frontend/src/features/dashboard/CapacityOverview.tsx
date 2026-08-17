import React, { useEffect, useState, useMemo } from "react";
import { createPortal } from "react-dom";
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import { Activity, Zap, Sun, Wind, Calendar, ServerCrash, RefreshCw, TrendingUp, TrendingDown, Info, Layers } from "lucide-react";
import { motion, AnimatePresence } from 'framer-motion';

const containerVariants: any = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.1 } }
};

const itemVariants: any = {
  hidden: { opacity: 0, y: 15 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } }
};

interface FYData {
  name: string;
  solar_cod: number;
  solar_tr: number;
  wind_cod: number;
  wind_tr: number;
}

interface BlockMilestone {
  project: string;
  block: string;
  type: string;
  capacity: number;
  status: 'COD' | 'Trial Run';
  tr_start: string | null;
  tr_finish: string | null;
  cod_start: string | null;
  cod_finish: string | null;
  tr_duration: number | null;
  cod_duration: number | null;
  gap_days: number | null;
}

interface ProjectBreakdown {
  project_id: string;
  project_name: string;
  type: string;
  total_capacity: number;
  total_blocks: number;
  tr_blocks: number;
  tr_mw: number;
  cod_blocks: number;
  cod_mw: number;
  remaining_capacity: number;
  remaining_blocks: number;
}

interface CapacityData {
  financial_years: FYData[];
  recent_milestones: BlockMilestone[];
  totals: {
    solar_cod: number;
    solar_tr: number;
    wind_cod: number;
    wind_tr: number;
  };
  projects: ProjectBreakdown[];
  monthly_trends?: any[];
}

const KPICard = ({ title, value, unit, icon: Icon, color, onClick }: any) => {
  // Vibrant solid colors matching reference image
  const bgColors: Record<string, string> = {
    primary: 'bg-blue-600 hover:bg-blue-700 text-white border-blue-500',
    emerald: 'bg-emerald-500 hover:bg-emerald-600 text-white border-emerald-400',
    amber: 'bg-amber-500 hover:bg-amber-600 text-white border-amber-400',
    purple: 'bg-purple-600 hover:bg-purple-700 text-white border-purple-500',
    pink: 'bg-pink-600 hover:bg-pink-700 text-white border-pink-500'
  };

  const cardClass = bgColors[color] || bgColors.primary;

  return (
    <motion.div variants={itemVariants} whileHover={{ y: -4, scale: 1.02 }} className="h-full">
      <div 
        onClick={onClick}
        className={`relative h-full px-6 py-5 flex flex-col justify-between group overflow-hidden cursor-pointer rounded-2xl shadow-lg transition-all duration-300 border ${cardClass}`}
      >
        {/* Subtle texture/gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-br from-white/10 to-transparent opacity-50" />
        <div className="absolute -right-8 -top-8 w-32 h-32 rounded-full bg-white/10 blur-2xl group-hover:bg-white/20 transition-all duration-700" />
        
        <div className="flex justify-between items-start mb-4 relative z-10">
          <h4 className="text-[12px] font-bold uppercase tracking-[0.1em] leading-tight flex items-center gap-2 text-white/90">
            <Icon className="w-4 h-4 opacity-80" /> {title}
          </h4>
        </div>
        
        <div className="flex items-end justify-between relative z-10 mt-2">
          <div className="flex items-baseline gap-1.5">
            <span className="text-4xl font-black tracking-tight leading-none text-white drop-shadow-sm">{value}</span>
            {unit && <span className="text-[12px] font-bold uppercase tracking-widest text-white/80">{unit}</span>}
          </div>
        </div>
      </div>
    </motion.div>
  );
};


const KPIBreakdownModal = ({ isOpen, onClose, activeKpi, projects }: { isOpen: boolean, onClose: () => void, activeKpi: string | null, projects: ProjectBreakdown[] }) => {
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
      document.body.style.overflow = 'unset';
      document.documentElement.style.overflow = 'unset';
    }
  }, [isOpen, onClose]);

  if (!isOpen || !projects) return null;

  let filteredProjects = projects;
  let titleColor = "text-primary";
  if (activeKpi === "COD Done") {
    filteredProjects = projects.filter(p => p.cod_mw > 0);
  } else if (activeKpi === "Trial Run Only") {
    titleColor = "text-success";
    filteredProjects = projects.filter(p => p.tr_mw > 0);
  } else if (activeKpi === "Solar Portfolio") {
    titleColor = "text-warning";
    filteredProjects = projects.filter(p => p.type === 'Solar');
  } else if (activeKpi === "Wind Portfolio") {
    titleColor = "text-primary";
    filteredProjects = projects.filter(p => p.type === 'Wind');
  }

  const totalCap = filteredProjects.reduce((s, p) => s + p.total_capacity, 0);
  const totalCod = filteredProjects.reduce((s, p) => s + p.cod_mw, 0);
  const totalTr = filteredProjects.reduce((s, p) => s + p.tr_mw, 0);
  const totalRemaining = filteredProjects.reduce((s, p) => s + p.remaining_capacity, 0);

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
          <motion.div 
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/40 backdrop-blur-md" 
            onClick={onClose} 
            
          />
          <motion.div 
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1, transition: { type: 'spring', bounce: 0, duration: 0.4 } }}
            exit={{ opacity: 0, y: 20, scale: 0.95, transition: { duration: 0.2 } }}
            className="bg-white/80 dark:bg-gray-900/80 backdrop-blur-2xl w-full max-w-5xl rounded-3xl shadow-2xl relative z-10 overflow-hidden flex flex-col max-h-[85vh] border border-white/50 dark:border-white/10"
          >
            <div className="px-6 py-6 border-b border-border/50 dark:border-border/50 flex justify-between items-start bg-gradient-to-r from-gray-50/50 to-transparent dark:from-gray-800/20">
              <div>
                <h2 className={`text-xl font-black ${titleColor} flex items-center gap-2 mb-1 tracking-tight`}>
                  <Layers className="w-6 h-6" /> {activeKpi}
                </h2>
                <div className="flex gap-2 mt-3 flex-wrap">
                  <span className="text-[11px] font-bold text-foreground dark:text-muted-foreground uppercase tracking-wider bg-white/50 dark:bg-gray-900/50 px-3 py-1.5 rounded-full shadow-sm backdrop-blur-sm border border-border/50 dark:border-gray-700/50">Total Cap: <span className="text-foreground dark:text-white ml-1">{totalCap.toFixed(1)} MW</span></span>
                  <span className="text-[11px] font-bold text-primary uppercase tracking-wider bg-primary/5 dark:bg-primary/10 px-3 py-1.5 rounded-full shadow-sm backdrop-blur-sm border border-primary/20">COD: <span className="ml-1 font-black">{totalCod.toFixed(1)} MW</span></span>
                  <span className="text-[11px] font-bold text-success dark:text-success uppercase tracking-wider bg-success/100/5 dark:bg-success/100/10 px-3 py-1.5 rounded-full shadow-sm backdrop-blur-sm border border-success/20">TR Only: <span className="ml-1 font-black">{totalTr.toFixed(1)} MW</span></span>
                  <span className="text-[11px] font-bold text-warning dark:text-warning uppercase tracking-wider bg-warning/100/5 dark:bg-warning/100/10 px-3 py-1.5 rounded-full shadow-sm backdrop-blur-sm border border-warning/20">Remaining: <span className="ml-1 font-black">{totalRemaining.toFixed(1)} MW</span></span>
                </div>
              </div>
              <button onClick={onClose} className="p-2.5 bg-muted hover:bg-gray-200 dark:bg-gray-900/80 dark:hover:bg-gray-700 rounded-full transition-colors self-start backdrop-blur-sm group">
                <span className="sr-only">Close</span>
                <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className="text-muted-foreground group-hover:text-foreground dark:text-muted-foreground dark:group-hover:text-white transition-colors"><path d="M11.7816 4.03157C12.0062 3.80702 12.0062 3.44295 11.7816 3.2184C11.5571 2.99385 11.193 2.99385 10.9685 3.2184L7.50005 6.68682L4.03164 3.2184C3.80708 2.99385 3.44301 2.99385 3.21846 3.2184C2.99391 3.44295 2.99391 3.80702 3.21846 4.03157L6.68688 7.49999L3.21846 10.9684C2.99391 11.193 2.99391 11.557 3.21846 11.7816C3.44301 12.0061 3.80708 12.0061 4.03164 11.7816L7.50005 8.31316L10.9685 11.7816C11.193 12.0061 11.5571 12.0061 11.7816 11.7816C12.0062 11.557 12.0062 11.193 11.7816 10.9684L8.31322 7.49999L11.7816 4.03157Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd"></path></svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto min-h-0 custom-scrollbar">
              {filteredProjects.length === 0 ? (
                <div className="text-center py-16 text-muted-foreground font-medium">No projects found for this metric.</div>
              ) : (
                <div className="px-6 pb-6 pt-2">
                  <table className="w-full text-left text-sm border-separate border-spacing-y-2">
                    <thead className="text-[10px] font-black text-muted-foreground uppercase tracking-[0.1em] sticky top-0 bg-white/95 dark:bg-gray-900/95 backdrop-blur-md z-10">
                    <tr>
                      <th className="py-3 pl-4 rounded-l-xl">Project</th>
                      <th className="py-3 text-center">Type</th>
                      <th className="py-3 text-center">Total Cap</th>
                      <th className="py-3 text-center">Blocks</th>
                      <th className="py-3 text-center">COD</th>
                      <th className="py-3 text-center">TR Only</th>
                      <th className="py-3 text-center rounded-r-xl">Remaining Progress</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredProjects.map((p, idx) => {
                      const pct = p.total_capacity > 0 ? ((p.cod_mw + p.tr_mw) / p.total_capacity * 100) : 0;
                      return (
                        <tr key={idx} className="bg-white/40 dark:bg-gray-900/40 hover:bg-white dark:hover:bg-card transition-all duration-200 group shadow-sm hover:shadow-md rounded-xl">
                          <td className="px-4 py-3.5 font-bold text-[12px] text-foreground dark:text-white max-w-[200px] truncate rounded-l-xl" title={p.project_name}>{p.project_name}</td>
                          <td className="px-2 py-3.5 text-center">
                            {p.type === 'Solar' ? <div className="mx-auto w-6 h-6 rounded-full bg-warning/100/10 flex items-center justify-center"><Sun size={12} className="text-warning" /></div> : <div className="mx-auto w-6 h-6 rounded-full bg-primary/100/10 flex items-center justify-center"><Wind size={12} className="text-primary" /></div>}
                          </td>
                          <td className="px-2 py-3.5 text-center text-[12px] font-black text-foreground dark:text-muted-foreground">{p.total_capacity.toFixed(1)}</td>
                          <td className="px-2 py-3.5 text-center text-[11px] font-bold text-muted-foreground">{p.total_blocks}</td>
                          <td className="px-2 py-3.5 text-center">
                            {p.cod_mw > 0 ? <span className="text-[11px] font-black text-primary bg-primary/10 px-2.5 py-1 rounded-full">{p.cod_mw.toFixed(1)} MW <span className="font-normal opacity-60">({p.cod_blocks})</span></span> : <span className="text-muted-foreground">-</span>}
                          </td>
                          <td className="px-2 py-3.5 text-center">
                            {p.tr_mw > 0 ? <span className="text-[11px] font-black text-success bg-success/100/10 px-2.5 py-1 rounded-full">{p.tr_mw.toFixed(1)} MW <span className="font-normal opacity-60">({p.tr_blocks})</span></span> : <span className="text-muted-foreground">-</span>}
                          </td>
                          <td className="px-4 py-3.5 text-center rounded-r-xl">
                            <div className="flex flex-col gap-1.5">
                              <div className="flex justify-between items-center px-1">
                                <span className="text-[10px] font-bold text-muted-foreground">{pct.toFixed(0)}% Done</span>
                                <span className="text-[10px] font-bold text-warning dark:text-warning">{p.remaining_capacity.toFixed(1)} MW Left</span>
                              </div>
                              <div className="w-full h-1.5 bg-gray-200/50 dark:bg-gray-700/50 rounded-full overflow-hidden shadow-inner flex">
                                {p.cod_mw > 0 && <div className="h-full bg-primary transition-all duration-700 ease-out" style={{ width: `${Math.min((p.cod_mw / p.total_capacity) * 100, 100)}%` }}></div>}
                                {p.tr_mw > 0 && <div className="h-full bg-success/100 transition-all duration-700 ease-out" style={{ width: `${Math.min((p.tr_mw / p.total_capacity) * 100, 100)}%` }}></div>}
                              </div>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
};

export default function CapacityOverview() {
  const [data, setData] = useState<CapacityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeKpi, setActiveKpi] = useState<string | null>(null);
  const [chartFilter, setChartFilter] = useState<string>('All');
  const [viewMode, setViewMode] = useState<'FY' | 'Monthly'>('Monthly');
  const [searchParams] = useSearchParams();
  const portfolio = searchParams.get('portfolio');

  useEffect(() => {
    setLoading(true);
    const url = portfolio ? `/akasha/api/dashboard/capacity-overview?portfolio=${encodeURIComponent(portfolio)}` : '/akasha/api/dashboard/capacity-overview';
    fetch(url)
      .then(res => res.json())
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(e => {
        console.error(e);
        setError("Failed to load Capacity Overview data.");
        setLoading(false);
      });
  }, [portfolio]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[500px] w-full">
        <RefreshCw className="w-8 h-8 text-primary animate-spin mb-4" />
        <p className="text-muted-foreground font-medium">Analyzing Capacity Metrics...</p>
      </div>
    );
  }

  if (error || !data) return <div className="text-destructive flex justify-center items-center h-64 font-bold">{error || "No data available"}</div>;

  const { financial_years, monthly_trends, recent_milestones, totals, projects } = data;

  // FY Chart Data
  const fyDataObj = financial_years.map(fy => ({
    name: fy.name,
    "Solar COD": fy.solar_cod,
    "Solar Trial Run": fy.solar_tr,
    "Wind COD": fy.wind_cod,
    "Wind Trial Run": fy.wind_tr,
    total: fy.solar_cod + fy.solar_tr + fy.wind_cod + fy.wind_tr
  })).filter(d => d.total > 0);

  // Read Monthly Chart Data generated by backend (across full historical dataset)
  const cumulativeMonthlyData = monthly_trends || [];

  const totalCod = projects.reduce((s, p) => s + p.cod_mw, 0);
  const totalTr = projects.reduce((s, p) => s + p.tr_mw, 0);
  const totalSolar = projects.filter(p => p.type === 'Solar').reduce((s, p) => s + p.total_capacity, 0);
  const totalWind = projects.filter(p => p.type === 'Wind').reduce((s, p) => s + p.total_capacity, 0);

  // Common Premium Chart Styling
  const commonChartOptions = {
    tooltip: { 
      trigger: 'axis', 
      backgroundColor: 'rgba(255, 255, 255, 0.95)', 
      borderColor: '#e5e7eb', 
      textStyle: { color: '#374151', fontSize: 13, fontWeight: 500 }, 
      padding: [12, 16], 
      borderRadius: 12, 
      extraCssText: 'backdrop-filter: blur(10px); box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);',
      valueFormatter: (value: any) => Number(value).toFixed(1) + ' MW'
    },
    legend: { bottom: 0, itemWidth: 12, itemHeight: 12, textStyle: { color: '#6b7280', fontSize: 11, fontWeight: 600, fontFamily: 'inherit' }, icon: 'circle' },
    grid: { top: 30, left: 10, right: 30, bottom: 45, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, axisLine: { lineStyle: { color: '#e5e7eb' } }, axisLabel: { color: '#6b7280', fontWeight: '600', fontFamily: 'inherit', margin: 12, fontSize: 11 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed', color: '#f3f4f6' } }, axisLabel: { color: '#9ca3af', fontFamily: 'inherit', fontWeight: 600, fontSize: 11 } },
  };

  const getSeries = (data: any[], key: string, color: string, name: string) => ({
    name, type: 'line', smooth: true, showSymbol: false, symbol: 'circle', symbolSize: 6,
    lineStyle: { width: 2.5, color },
    itemStyle: { color },
    data: data.map(d => d[key])
  });

  const getBarSeries = (data: any[], key: string, color: string, name: string) => ({
    name, type: 'bar', barMaxWidth: 40,
    itemStyle: { color, borderRadius: [4, 4, 0, 0] },
    data: data.map(d => d[key])
  });

  const allSeries = [
    { key: "Solar COD", color: "#ea580c", name: "Solar COD", type: 'Solar', kpi: 'COD' },
    { key: "Solar Trial Run", color: "#eab308", name: "Solar TR", type: 'Solar', kpi: 'TR' },
    { key: "Wind COD", color: "#0284c7", name: "Wind COD", type: 'Wind', kpi: 'COD' },
    { key: "Wind Trial Run", color: "#38bdf8", name: "Wind TR", type: 'Wind', kpi: 'TR' },
  ];

  const visibleSeriesDef = allSeries.filter(s => {
    if (chartFilter === 'All') return true;
    if (chartFilter === 'COD Done') return s.kpi === 'COD';
    if (chartFilter === 'Trial Run Only') return s.kpi === 'TR';
    if (chartFilter === 'Solar Portfolio') return s.type === 'Solar';
    if (chartFilter === 'Wind Portfolio') return s.type === 'Wind';
    return true;
  });

  // Helper to format "YYYY-MM" to "MMM 'YY" (e.g. "2025-07" -> "Jul '25")
  const formatMonthLabel = (label: string) => {
    if (!label || !label.includes('-')) return label;
    const [year, month] = label.split('-');
    const date = new Date(parseInt(year), parseInt(month) - 1);
    return date.toLocaleDateString('en-US', { month: 'short' }) + " '" + year.substring(2);
  };

  const fyEchartOption = {
    ...commonChartOptions,
    xAxis: { ...commonChartOptions.xAxis, data: fyDataObj.map(d => d.name) },
    series: visibleSeriesDef.map(s => getBarSeries(fyDataObj, s.key, s.color, s.name))
  };

  const monthlyEchartOption = {
    ...commonChartOptions,
    xAxis: { ...commonChartOptions.xAxis, data: cumulativeMonthlyData.map((d: any) => formatMonthLabel(d.name)) },
    series: visibleSeriesDef.map(s => getSeries(cumulativeMonthlyData, s.key, s.color, s.name))
  };

  // KPI Calculations
  let runningCod = 0; let runningTr = 0; let runningSolar = 0; let runningWind = 0;
  const spark1: any[] = []; const spark2: any[] = []; const spark3: any[] = []; const spark4: any[] = [];
  const sortedFys = [...financial_years].sort((a, b) => a.name.localeCompare(b.name));
  sortedFys.forEach(fy => {
    runningCod += (fy.solar_cod + fy.wind_cod);
    runningTr += (fy.solar_tr + fy.wind_tr);
    runningSolar += (fy.solar_cod + fy.solar_tr);
    runningWind += (fy.wind_cod + fy.wind_tr);
    spark1.push({ value: runningCod }); spark2.push({ value: runningTr }); spark3.push({ value: runningSolar }); spark4.push({ value: runningWind });
  });

  let trendCod = { dir: 'up', val: '+0%' }; let trendTr = { dir: 'up', val: '+0%' }; let trendSolar = { dir: 'up', val: '+0%' }; let trendWind = { dir: 'up', val: '+0%' };
  if (sortedFys.length >= 2) {
    const current = sortedFys[sortedFys.length - 1]; const prev = sortedFys[sortedFys.length - 2];
    const calcTrend = (currVal: number, prevVal: number) => {
      if (prevVal === 0 && currVal > 0) return { dir: 'up', val: '+100%' };
      if (prevVal === 0 && currVal === 0) return null;
      const pct = ((currVal - prevVal) / prevVal) * 100;
      return { dir: pct >= 0 ? 'up' : 'down', val: `${pct >= 0 ? '+' : ''}${pct.toFixed(0)}%` };
    };
    trendCod = calcTrend((current.solar_cod + current.wind_cod), (prev.solar_cod + prev.wind_cod)) || trendCod;
    trendTr = calcTrend((current.solar_tr + current.wind_tr), (prev.solar_tr + prev.wind_tr)) || trendTr;
    trendSolar = calcTrend((current.solar_cod + current.solar_tr), (prev.solar_cod + prev.solar_tr)) || trendSolar;
    trendWind = calcTrend((current.wind_cod + current.wind_tr), (prev.wind_cod + prev.wind_tr)) || trendWind;
  }

  const renderGap = (gap: number | null) => {
    if (gap === null) return <span className="text-muted-foreground">-</span>;
    let colorClass = "bg-success/10 border-success/20 text-success";
    if (gap > 20) colorClass = "bg-destructive/10 border-destructive/20 text-destructive";
    else if (gap > 15) colorClass = "bg-warning/10 border-warning/20 text-warning";
    return <span className={`px-2.5 py-1 rounded-md text-[11px] font-bold border shadow-sm ${colorClass}`}>{gap} d</span>;
  };

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="show" className="flex flex-col gap-4 w-full pb-8">
      <KPIBreakdownModal isOpen={!!activeKpi} onClose={() => setActiveKpi(null)} activeKpi={activeKpi} projects={projects || []} />
      
      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title="COD Done" value={totalCod.toFixed(1)} unit="MW" icon={Zap} color="primary" onClick={() => { setActiveKpi('COD Done'); setChartFilter('COD Done'); }} />
        <KPICard title="Trial Run Only" value={totalTr.toFixed(1)} unit="MW" icon={Activity} color="emerald" onClick={() => { setActiveKpi('Trial Run Only'); setChartFilter('Trial Run Only'); }} />
        <KPICard title="Solar Portfolio" value={totalSolar.toFixed(1)} unit="MW" icon={Sun} color="amber" onClick={() => { setActiveKpi('Solar Portfolio'); setChartFilter('Solar Portfolio'); }} />
        <KPICard title="Wind Portfolio" value={totalWind.toFixed(1)} unit="MW" icon={Wind} color="purple" onClick={() => { setActiveKpi('Wind Portfolio'); setChartFilter('Wind Portfolio'); }} />
      </div>

      {/* Analytics Dashboard Section */}
      <div className="flex flex-col gap-4">
        {/* Main Chart */}
        <motion.div variants={itemVariants} className="p-5 flex flex-col h-[400px] rounded-2xl bg-white/70 dark:bg-gray-900/70 backdrop-blur-xl border border-white/40 dark:border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-[12px] font-bold text-foreground dark:text-white uppercase tracking-[0.08em] flex items-center gap-2">
              <Calendar className="w-4 h-4 text-primary" /> Capacity Trajectory
            </h3>
            
            <div className="flex flex-col sm:flex-row items-end sm:items-center gap-3">
              {/* Chart Filters */}
              <div className="flex bg-muted dark:bg-gray-900/80 backdrop-blur p-1 rounded-xl shadow-inner border border-border/50 dark:border-gray-700/50">
                {['All', 'COD', 'TR', 'Solar', 'Wind'].map(f => {
                   const mappedFilter = f === 'COD' ? 'COD Done' : f === 'TR' ? 'Trial Run Only' : f === 'Solar' ? 'Solar Portfolio' : f === 'Wind' ? 'Wind Portfolio' : 'All';
                   return (
                     <button
                       key={f}
                       onClick={() => setChartFilter(mappedFilter)}
                       className={`px-3 py-1.5 text-[11px] font-bold uppercase rounded-lg transition-colors ${chartFilter === mappedFilter ? 'bg-white dark:bg-gray-700 text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
                     >
                       {f}
                     </button>
                   );
                })}
              </div>

              <div className="flex bg-muted dark:bg-gray-900/80 backdrop-blur p-1 rounded-xl shadow-inner border border-border/50 dark:border-gray-700/50 relative">
                {viewMode === 'FY' ? (
                   <motion.div layoutId="chartViewToggle" className="absolute left-1 top-1 bottom-1 w-[calc(50%-4px)] bg-white dark:bg-gray-700 rounded-lg shadow-sm" />
                ) : (
                   <motion.div layoutId="chartViewToggle" className="absolute right-1 top-1 bottom-1 w-[calc(50%-4px)] bg-white dark:bg-gray-700 rounded-lg shadow-sm" />
                )}
                <button 
                  onClick={() => setViewMode('FY')} 
                  className={`px-4 py-1.5 text-[11px] font-bold uppercase rounded-lg transition-colors relative z-10 w-28 ${viewMode === 'FY' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'}`}
                >
                  Financial Year
                </button>
                <button 
                  onClick={() => setViewMode('Monthly')} 
                  className={`px-4 py-1.5 text-[11px] font-bold uppercase rounded-lg transition-colors relative z-10 w-28 ${viewMode === 'Monthly' ? 'text-primary' : 'text-muted-foreground hover:text-foreground'}`}
                >
                  Monthly Trend
                </button>
              </div>
            </div>
          </div>
          <div className="flex-1 w-full min-h-0 relative">
            <AnimatePresence mode="wait">
              <motion.div 
                key={viewMode}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
                className="absolute inset-0"
              >
                {viewMode === 'FY' ? (
                  <ReactECharts option={fyEchartOption} style={{ height: '100%', width: '100%' }} notMerge={true} />
                ) : (
                  <ReactECharts option={monthlyEchartOption} style={{ height: '100%', width: '100%' }} notMerge={true} />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>
      </div>

    </motion.div>
  );
}
