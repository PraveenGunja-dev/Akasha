import React, { useEffect, useState, useMemo } from "react";
import ReactECharts from "echarts-for-react";
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
}

const KPICard = ({ title, value, unit, icon: Icon, color, trend, trendValue, sparklineData, onClick }: any) => {
  const isRed = color === 'red';
  const isEmerald = color === 'emerald';
  const isAmber = color === 'amber';
  const isBlue = color === 'blue';
  
  const iconColor = isRed ? 'text-red-500' : isEmerald ? 'text-emerald-500' : isAmber ? 'text-amber-500' : isBlue ? 'text-blue-500' : 'text-primary';
  const bgColor = isRed ? 'bg-red-50 dark:bg-red-500/10' : isEmerald ? 'bg-emerald-50 dark:bg-emerald-500/10' : isAmber ? 'bg-amber-50 dark:bg-amber-500/10' : isBlue ? 'bg-blue-50 dark:bg-blue-500/10' : 'bg-primary/10';
  const chartColor = isRed ? '#ef4444' : isEmerald ? '#10b981' : isAmber ? '#f59e0b' : isBlue ? '#3b82f6' : '#0ea5e9';

  const sparklineOptions = {
    xAxis: { type: 'category', show: false, data: sparklineData.map((_: any, i: number) => i) },
    yAxis: { type: 'value', show: false, min: 'dataMin' },
    series: [{
      data: sparklineData.map((d: any) => d.value),
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: chartColor },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: chartColor }, { offset: 1, color: 'transparent' }]
        },
        opacity: 0.3
      }
    }],
    grid: { left: 0, right: 0, top: 0, bottom: 0 }
  };

  return (
    <motion.div variants={itemVariants} className="h-full">
      <div 
        onClick={onClick}
        className="bento-card h-full px-5 py-4 flex flex-col justify-between group overflow-hidden relative border border-gray-100 dark:border-gray-800/50 hover:shadow-md transition-shadow cursor-pointer"
      >
        <div className={`absolute -right-6 -top-6 w-24 h-24 rounded-full ${bgColor} opacity-40 blur-2xl group-hover:scale-150 transition-transform duration-700`} />
        
        <div className="flex justify-between items-start mb-2 relative z-10">
          <h4 className="text-[11px] font-bold text-gray-500 uppercase tracking-[0.1em] leading-tight flex items-center gap-1.5">
            <Icon className={`w-3.5 h-3.5 ${iconColor}`} /> {title}
          </h4>
          {trend && (
            <div className={`flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded ${trend === 'up' ? 'text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10' : 'text-red-600 bg-red-50 dark:bg-red-500/10'}`}>
              {trend === 'up' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />} {trendValue}
            </div>
          )}
        </div>
        
        <div className="flex items-end justify-between relative z-10 mt-1">
          <div className="flex items-baseline gap-1">
            <span className="text-3xl font-black tracking-tight text-gray-900 dark:text-white leading-none group-hover:text-primary transition-colors">{value}</span>
            {unit && <span className="text-[11px] font-bold text-gray-400 uppercase tracking-widest">{unit}</span>}
          </div>
          
          <div className="h-8 w-20 opacity-60">
            <ReactECharts option={sparklineOptions} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
      </div>
    </motion.div>
  );
};

const KPIBreakdownModal = ({ isOpen, onClose, activeKpi, projects }: { isOpen: boolean, onClose: () => void, activeKpi: string | null, projects: ProjectBreakdown[] }) => {
  if (!isOpen || !projects) return null;

  let filteredProjects = projects;
  let titleColor = "text-primary";
  if (activeKpi === "COD Done") {
    filteredProjects = projects.filter(p => p.cod_mw > 0);
  } else if (activeKpi === "Trial Run Only") {
    titleColor = "text-emerald-500";
    filteredProjects = projects.filter(p => p.tr_mw > 0);
  } else if (activeKpi === "Solar Portfolio") {
    titleColor = "text-amber-500";
    filteredProjects = projects.filter(p => p.type === 'Solar');
  } else if (activeKpi === "Wind Portfolio") {
    titleColor = "text-blue-500";
    filteredProjects = projects.filter(p => p.type === 'Wind');
  }

  const totalCap = filteredProjects.reduce((s, p) => s + p.total_capacity, 0);
  const totalCod = filteredProjects.reduce((s, p) => s + p.cod_mw, 0);
  const totalTr = filteredProjects.reduce((s, p) => s + p.tr_mw, 0);
  const totalRemaining = filteredProjects.reduce((s, p) => s + p.remaining_capacity, 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="bg-white dark:bg-gray-900 w-full max-w-5xl rounded-2xl shadow-2xl relative z-10 overflow-hidden flex flex-col max-h-[85vh]"
      >
        <div className="px-6 py-5 border-b border-gray-100 dark:border-gray-800 flex justify-between items-center bg-gray-50/50 dark:bg-gray-800/30">
          <div>
            <h2 className={`text-lg font-bold ${titleColor} flex items-center gap-2`}>
              <Layers className="w-5 h-5" /> {activeKpi} — Project Breakdown
            </h2>
            <div className="flex gap-3 mt-2 flex-wrap">
              <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider bg-white dark:bg-gray-800 px-2 py-1 rounded shadow-sm border border-gray-100 dark:border-gray-700">Total: <span className="text-gray-900 dark:text-white">{totalCap.toFixed(1)} MW</span></span>
              <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider bg-white dark:bg-gray-800 px-2 py-1 rounded shadow-sm border border-gray-100 dark:border-gray-700">COD: <span className="text-primary">{totalCod.toFixed(1)} MW</span></span>
              <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider bg-white dark:bg-gray-800 px-2 py-1 rounded shadow-sm border border-gray-100 dark:border-gray-700">TR Only: <span className="text-emerald-600 dark:text-emerald-400">{totalTr.toFixed(1)} MW</span></span>
              <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider bg-white dark:bg-gray-800 px-2 py-1 rounded shadow-sm border border-gray-100 dark:border-gray-700">Remaining: <span className="text-amber-600 dark:text-amber-400">{totalRemaining.toFixed(1)} MW</span></span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 rounded-full transition-colors self-start">
            <span className="sr-only">Close</span>
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M11.7816 4.03157C12.0062 3.80702 12.0062 3.44295 11.7816 3.2184C11.5571 2.99385 11.193 2.99385 10.9685 3.2184L7.50005 6.68682L4.03164 3.2184C3.80708 2.99385 3.44301 2.99385 3.21846 3.2184C2.99391 3.44295 2.99391 3.80702 3.21846 4.03157L6.68688 7.49999L3.21846 10.9684C2.99391 11.193 2.99391 11.557 3.21846 11.7816C3.44301 12.0061 3.80708 12.0061 4.03164 11.7816L7.50005 8.31316L10.9685 11.7816C11.193 12.0061 11.5571 12.0061 11.7816 11.7816C12.0062 11.557 12.0062 11.193 11.7816 10.9684L8.31322 7.49999L11.7816 4.03157Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd"></path></svg>
          </button>
        </div>
        <div className="flex-1 overflow-auto custom-scrollbar bg-gray-50/30 dark:bg-gray-900">
          {filteredProjects.length === 0 ? (
            <div className="text-center py-10 text-gray-500 font-medium">No projects found for this metric.</div>
          ) : (
            <div className="px-4 pb-4">
              <table className="w-full text-left text-sm border-separate border-spacing-y-1">
                <thead className="text-[10px] font-black text-gray-400 uppercase tracking-[0.1em] sticky top-0 bg-white/95 dark:bg-gray-900/95 backdrop-blur z-10">
                <tr>
                  <th className="pb-2 pl-4">Project</th>
                  <th className="pb-2 text-center">Type</th>
                  <th className="pb-2 text-center">Total Cap</th>
                  <th className="pb-2 text-center">Total Blocks</th>
                  <th className="pb-2 text-center">COD Blocks</th>
                  <th className="pb-2 text-center">COD MW</th>
                  <th className="pb-2 text-center">TR Blocks</th>
                  <th className="pb-2 text-center">TR MW</th>
                  <th className="pb-2 text-center">Remaining</th>
                </tr>
              </thead>
              <tbody>
                {filteredProjects.map((p, idx) => {
                  const pct = p.total_capacity > 0 ? ((p.cod_mw + p.tr_mw) / p.total_capacity * 100) : 0;
                  return (
                    <tr key={idx} className="bg-white dark:bg-gray-800/60 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                      <td className="px-4 py-2.5 font-bold text-[11px] text-gray-900 dark:text-white max-w-[200px] truncate" title={p.project_name}>{p.project_name}</td>
                      <td className="px-2 py-2.5 text-center">
                        {p.type === 'Solar' ? <Sun size={14} className="text-amber-500 mx-auto" /> : <Wind size={14} className="text-blue-500 mx-auto" />}
                      </td>
                      <td className="px-2 py-2.5 text-center text-[11px] font-black text-gray-700 dark:text-gray-300">{p.total_capacity.toFixed(1)}</td>
                      <td className="px-2 py-2.5 text-center text-[11px] font-bold text-gray-600">{p.total_blocks}</td>
                      <td className="px-2 py-2.5 text-center">
                        {p.cod_blocks > 0 ? <span className="text-[11px] font-bold text-primary bg-primary/10 px-2 py-0.5 rounded">{p.cod_blocks}</span> : <span className="text-gray-300">-</span>}
                      </td>
                      <td className="px-2 py-2.5 text-center">
                        {p.cod_mw > 0 ? <span className="text-[11px] font-black text-primary">{p.cod_mw.toFixed(1)}</span> : <span className="text-gray-300">-</span>}
                      </td>
                      <td className="px-2 py-2.5 text-center">
                        {p.tr_blocks > 0 ? <span className="text-[11px] font-bold text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10 px-2 py-0.5 rounded">{p.tr_blocks}</span> : <span className="text-gray-300">-</span>}
                      </td>
                      <td className="px-2 py-2.5 text-center">
                        {p.tr_mw > 0 ? <span className="text-[11px] font-black text-emerald-600">{p.tr_mw.toFixed(1)}</span> : <span className="text-gray-300">-</span>}
                      </td>
                      <td className="px-2 py-2.5 text-center">
                        <div className="flex flex-col items-center gap-0.5">
                          <span className="text-[11px] font-bold text-amber-600">{p.remaining_capacity.toFixed(1)}</span>
                          <div className="w-16 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div className="h-full bg-gradient-to-r from-primary to-emerald-500 rounded-full transition-all" style={{ width: `${Math.min(pct, 100)}%` }} />
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
  );
};

export default function CapacityOverview() {
  const [data, setData] = useState<CapacityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeKpi, setActiveKpi] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'FY' | 'Monthly'>('FY');

  useEffect(() => {
    fetch('/akasha/api/dashboard/capacity-overview')
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
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[500px] w-full">
        <RefreshCw className="w-8 h-8 text-primary animate-spin mb-4" />
        <p className="text-muted-foreground font-medium">Analyzing Capacity Metrics...</p>
      </div>
    );
  }

  if (error || !data) return <div className="text-red-500 flex justify-center items-center h-64 font-bold">{error || "No data available"}</div>;

  const { financial_years, recent_milestones, totals, projects } = data;

  // FY Chart Data
  const fyDataObj = financial_years.map(fy => ({
    name: fy.name,
    "Solar COD": fy.solar_cod,
    "Solar Trial Run": fy.solar_tr,
    "Wind COD": fy.wind_cod,
    "Wind Trial Run": fy.wind_tr,
    total: fy.solar_cod + fy.solar_tr + fy.wind_cod + fy.wind_tr
  })).filter(d => d.total > 0);

  // Monthly Chart Data Generation
  const monthlyDataMap: Record<string, any> = {};
  recent_milestones.forEach(m => {
    let dt: string | null = null;
    let typeKey = '';
    if (m.status === 'COD') {
      dt = m.cod_finish || m.cod_start;
      typeKey = m.type === 'Solar' ? 'Solar COD' : 'Wind COD';
    } else if (m.status === 'Trial Run') {
      dt = m.tr_finish || m.tr_start;
      typeKey = m.type === 'Solar' ? 'Solar Trial Run' : 'Wind Trial Run';
    }
    if (dt && typeKey) {
      const monthStr = dt.substring(0, 7);
      if (!monthlyDataMap[monthStr]) {
        monthlyDataMap[monthStr] = { "Solar COD": 0, "Solar Trial Run": 0, "Wind COD": 0, "Wind Trial Run": 0 };
      }
      monthlyDataMap[monthStr][typeKey] += m.capacity;
    }
  });

  // Calculate Cumulative Monthly Data for the Trajectory
  const sortedMonths = Object.keys(monthlyDataMap).sort();
  let cumSolarCod = 0, cumSolarTr = 0, cumWindCod = 0, cumWindTr = 0;
  const cumulativeMonthlyData = sortedMonths.map(month => {
     cumSolarCod += monthlyDataMap[month]["Solar COD"];
     cumSolarTr += monthlyDataMap[month]["Solar Trial Run"];
     cumWindCod += monthlyDataMap[month]["Wind COD"];
     cumWindTr += monthlyDataMap[month]["Wind Trial Run"];
     return {
       name: month,
       "Solar COD": cumSolarCod,
       "Solar Trial Run": cumSolarTr,
       "Wind COD": cumWindCod,
       "Wind Trial Run": cumWindTr
     };
  });

  const totalCod = projects.reduce((s, p) => s + p.cod_mw, 0);
  const totalTr = projects.reduce((s, p) => s + p.tr_mw, 0);
  const totalSolar = projects.filter(p => p.type === 'Solar').reduce((s, p) => s + p.total_capacity, 0);
  const totalWind = projects.filter(p => p.type === 'Wind').reduce((s, p) => s + p.total_capacity, 0);

  // Common Premium Chart Styling
  const commonChartOptions = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(255, 255, 255, 0.95)', borderColor: '#e5e7eb', textStyle: { color: '#374151', fontSize: 12 }, padding: [10, 15], borderRadius: 8, extraCssText: 'box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);' },
    legend: { bottom: 0, itemWidth: 14, itemHeight: 14, textStyle: { color: '#6b7280', fontSize: 11, fontWeight: 600, fontFamily: 'inherit' }, icon: 'circle' },
    grid: { top: 20, left: 10, right: 20, bottom: 40, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, axisLine: { lineStyle: { color: '#e5e7eb' } }, axisLabel: { color: '#6b7280', fontWeight: 'bold', fontFamily: 'inherit', margin: 12 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed', color: '#f3f4f6' } }, axisLabel: { color: '#9ca3af', fontFamily: 'inherit' } },
  };

  const getSeries = (data: any[], key: string, color: string, name: string) => ({
    name, type: 'line', smooth: true, showSymbol: data.length < 5, symbol: 'circle', symbolSize: 6,
    lineStyle: { width: 3, color },
    itemStyle: { color },
    areaStyle: {
      color: {
        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: color + '60' }, { offset: 1, color: color + '05' }]
      }
    },
    data: data.map(d => d[key])
  });

  const fyEchartOption = {
    ...commonChartOptions,
    xAxis: { ...commonChartOptions.xAxis, data: fyDataObj.map(d => d.name) },
    series: [
      getSeries(fyDataObj, "Solar COD", "#f59e0b", "Solar COD"),
      getSeries(fyDataObj, "Solar Trial Run", "#fde047", "Solar TR"),
      getSeries(fyDataObj, "Wind COD", "#3b82f6", "Wind COD"),
      getSeries(fyDataObj, "Wind Trial Run", "#93c5fd", "Wind TR"),
    ]
  };

  const monthlyEchartOption = {
    ...commonChartOptions,
    xAxis: { ...commonChartOptions.xAxis, data: cumulativeMonthlyData.map(d => d.name) },
    series: [
      getSeries(cumulativeMonthlyData, "Solar COD", "#f59e0b", "Solar COD"),
      getSeries(cumulativeMonthlyData, "Solar Trial Run", "#fde047", "Solar TR"),
      getSeries(cumulativeMonthlyData, "Wind COD", "#3b82f6", "Wind COD"),
      getSeries(cumulativeMonthlyData, "Wind Trial Run", "#93c5fd", "Wind TR"),
    ]
  };

  const pieEchartOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} MW ({d}%)' },
    series: [
      {
        type: 'pie',
        radius: ['50%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        data: [
          { value: totalSolar, name: 'Solar', itemStyle: { color: '#f59e0b' } },
          { value: totalWind, name: 'Wind', itemStyle: { color: '#3b82f6' } }
        ]
      }
    ]
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
    if (gap === null) return <span className="text-gray-300">-</span>;
    let colorClass = "bg-emerald-50 border-emerald-100 text-emerald-700";
    if (gap > 20) colorClass = "bg-red-50 border-red-100 text-red-700";
    else if (gap > 15) colorClass = "bg-amber-50 border-amber-100 text-amber-700";
    return <span className={`px-2.5 py-1 rounded-md text-[11px] font-bold border shadow-sm ${colorClass}`}>{gap} d</span>;
  };

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="show" className="flex flex-col gap-4 w-full pb-8">
      <KPIBreakdownModal isOpen={!!activeKpi} onClose={() => setActiveKpi(null)} activeKpi={activeKpi} projects={projects || []} />
      
      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title="COD Done" value={totalCod.toFixed(1)} unit="MW" icon={Zap} color="primary" trend={trendCod?.dir} trendValue={trendCod?.val} sparklineData={spark1} onClick={() => setActiveKpi('COD Done')} />
        <KPICard title="Trial Run Only" value={totalTr.toFixed(1)} unit="MW" icon={Activity} color="emerald" trend={trendTr?.dir} trendValue={trendTr?.val} sparklineData={spark2} onClick={() => setActiveKpi('Trial Run Only')} />
        <KPICard title="Solar Portfolio" value={totalSolar.toFixed(1)} unit="MW" icon={Sun} color="amber" trend={trendSolar?.dir} trendValue={trendSolar?.val} sparklineData={spark3} onClick={() => setActiveKpi('Solar Portfolio')} />
        <KPICard title="Wind Portfolio" value={totalWind.toFixed(1)} unit="MW" icon={Wind} color="blue" trend={trendWind?.dir} trendValue={trendWind?.val} sparklineData={spark4} onClick={() => setActiveKpi('Wind Portfolio')} />
      </div>

      {/* Analytics Dashboard Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Main Chart */}
        <motion.div variants={itemVariants} className="bento-card p-5 lg:col-span-2 flex flex-col h-[400px]">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-[12px] font-bold text-gray-900 dark:text-white uppercase tracking-[0.08em] flex items-center gap-2">
              <Calendar className="w-4 h-4 text-primary" /> Capacity Trajectory
            </h3>
            <div className="flex bg-gray-100 dark:bg-gray-800 p-1 rounded-lg">
              <button 
                onClick={() => setViewMode('FY')} 
                className={`px-3 py-1 text-[11px] font-bold uppercase rounded-md transition-all ${viewMode === 'FY' ? 'bg-white dark:bg-gray-700 shadow text-primary' : 'text-gray-500 hover:text-gray-900'}`}
              >
                Financial Year
              </button>
              <button 
                onClick={() => setViewMode('Monthly')} 
                className={`px-3 py-1 text-[11px] font-bold uppercase rounded-md transition-all ${viewMode === 'Monthly' ? 'bg-white dark:bg-gray-700 shadow text-primary' : 'text-gray-500 hover:text-gray-900'}`}
              >
                Monthly Trend
              </button>
            </div>
          </div>
          <div className="flex-1 w-full min-h-0">
            {viewMode === 'FY' ? (
              <ReactECharts option={fyEchartOption} style={{ height: '100%', width: '100%' }} />
            ) : (
              <ReactECharts option={monthlyEchartOption} style={{ height: '100%', width: '100%' }} />
            )}
          </div>
        </motion.div>

        {/* Donut Chart */}
        <motion.div variants={itemVariants} className="bento-card p-5 flex flex-col h-[400px]">
          <h3 className="text-[12px] font-bold text-gray-900 dark:text-white uppercase tracking-[0.08em] mb-2 flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" /> Portfolio Mix
          </h3>
          <div className="flex-1 relative flex items-center justify-center">
            <ReactECharts option={pieEchartOption} style={{ height: '100%', width: '100%' }} />
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Total</span>
              <span className="text-2xl font-black text-gray-900 dark:text-white leading-none mt-1">{(totalSolar + totalWind).toFixed(0)}</span>
              <span className="text-[10px] font-bold text-gray-400">MW</span>
            </div>
          </div>
          <div className="flex justify-center gap-6 mt-2 pt-4 border-t border-gray-100 dark:border-gray-800">
            <div className="flex flex-col items-center">
              <div className="flex items-center gap-1.5 mb-1"><div className="w-2 h-2 rounded-full bg-amber-500"></div><span className="text-[11px] font-bold text-gray-500 uppercase">Solar</span></div>
              <span className="text-[13px] font-bold text-gray-900 dark:text-white">{totalSolar.toFixed(1)} MW</span>
            </div>
            <div className="flex flex-col items-center">
              <div className="flex items-center gap-1.5 mb-1"><div className="w-2 h-2 rounded-full bg-blue-500"></div><span className="text-[11px] font-bold text-gray-500 uppercase">Wind</span></div>
              <span className="text-[13px] font-bold text-gray-900 dark:text-white">{totalWind.toFixed(1)} MW</span>
            </div>
          </div>
        </motion.div>
      </div>


    </motion.div>
  );
}
