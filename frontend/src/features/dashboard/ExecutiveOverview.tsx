import React, { useMemo, useState, useRef, useEffect } from 'react';
import {
  TrendingUp, Activity, DollarSign, IndianRupee,
  AlertTriangle, Zap, Clock, Layers, MapPin, Package, RefreshCw, AlertCircle, Bot, CheckCircle2, Shield, Info
} from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import { motion, AnimatePresence } from 'framer-motion';
import KPIDetailsModal from '../../components/ui/KPIDetailsModal';
import { useChartTheme } from '../../lib/chartTheme';

const containerVariants: any = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.04 }
  }
};

const itemVariants: any = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } }
};

const KPIInfoTooltip = ({ info, align = 'center' }: { info: React.ReactNode, align?: 'left' | 'center' | 'right' }) => {
  const [isOpen, setIsOpen] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (tooltipRef.current && !tooltipRef.current.contains(e.target as Node) &&
          triggerRef.current && !triggerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  let alignClasses = "left-1/2 -translate-x-1/2";
  let arrowClasses = "left-1/2 -translate-x-1/2";
  
  if (align === 'right') {
    alignClasses = "right-0 translate-x-2";
    arrowClasses = "right-4 translate-x-0";
  } else if (align === 'left') {
    alignClasses = "left-0 -translate-x-2";
    arrowClasses = "left-4 translate-x-0";
  }

  return (
    <div className="relative" style={{ zIndex: isOpen ? 50 : 1 }}>
      <button
        ref={triggerRef}
        onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen); }}
        onMouseEnter={() => setIsOpen(true)}
        onMouseLeave={() => setIsOpen(false)}
        className="p-0.5 rounded-full hover:bg-primary/10 transition-colors focus:outline-none"
        aria-label="More info"
      >
        <Info className="w-3 h-3 text-muted-foreground hover:text-primary transition-colors" />
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            ref={tooltipRef}
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className={`absolute top-full mt-2 w-64 p-3 rounded-xl
              bg-white/95 dark:bg-gray-900/95 backdrop-blur-xl
              border border-gray-200/60 dark:border-gray-700/60
              shadow-[0_8px_32px_rgba(0,0,0,0.12)] dark:shadow-[0_8px_32px_rgba(0,0,0,0.4)]
              pointer-events-auto text-left ${alignClasses}`}
            style={{ zIndex: 9999 }}
          >
            <div className={`absolute -top-1.5 w-3 h-3 rotate-45
              bg-white/95 dark:bg-gray-900/95
              border-l border-t border-gray-200/60 dark:border-gray-700/60 ${arrowClasses}`} />
            <div className="text-[11px] leading-relaxed text-gray-600 dark:text-gray-300 font-medium relative z-10 normal-case tracking-normal">
              {info}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

/* Three tile weights. The KPI band uses one hero, two primary and four
   supporting tiles so the eye lands somewhere first — an equal grid of seven
   gives the reader no entry point. */
const KPI_SIZE: Record<string, { metric: string; pad: string }> = {
  hero:       { metric: 'metric-xl', pad: 'px-5 py-4' },
  primary:    { metric: 'metric-lg', pad: 'px-4 py-3.5' },
  supporting: { metric: 'metric-md', pad: 'px-3.5 py-3' },
};

const KPICard = ({
  title, value, unit, subtext, stats, trend, trendValue, trendLabel,
  icon: Icon, color, tone, size = 'primary', onClick, info, infoAlign, className = '',
}: any) => {
  const s = KPI_SIZE[size] ?? KPI_SIZE.primary;

  // Legacy `color` prop maps onto the status system.
  const resolved = tone ?? (
    color === 'red' ? 'critical' :
    color === 'amber' ? 'warning' :
    color === 'emerald' ? 'healthy' : 'neutral'
  );

  const iconColor =
    resolved === 'critical' ? 'text-destructive' :
    resolved === 'warning' ? 'text-warning' :
    resolved === 'healthy' ? 'text-success' : 'text-primary';

  // Only states that demand attention get an accent rail — colour stays
  // informational rather than decorative.
  const accent =
    resolved === 'critical' ? 'intelligence-card-critical' :
    resolved === 'warning' ? 'intelligence-card-warning' : '';

  return (
    <motion.div variants={itemVariants} className={`h-full ${className}`}>
      <div
        onClick={onClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e: React.KeyboardEvent) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.(); }
        }}
        className={`bento-card ${accent} h-full ${s.pad} cursor-pointer flex flex-col justify-between group`}
      >
        <div className="flex justify-between items-start gap-2 mb-2">
          <div className="flex items-center gap-1 min-w-0">
            <h4 className="section-label leading-tight truncate">{title}</h4>
            {info && <KPIInfoTooltip info={info} align={infoAlign} />}
          </div>
          <Icon className={`w-4 h-4 shrink-0 ${iconColor} opacity-70 group-hover:opacity-100 transition-opacity`} />
        </div>

        <div>
          <div className={s.metric}>
            <span>{value}</span>
            {unit && <span className="metric-unit">{unit}</span>}
          </div>

          {subtext && <div className="text-[10px] text-fg-tertiary font-medium mt-1.5">{subtext}</div>}

          {/* Supporting figures share the tile rather than each claiming one. */}
          {stats?.length > 0 && (
            <div className="flex items-center gap-5 mt-3 pt-2.5 border-t border-border-subtle">
              {stats.map((st: any) => (
                <div key={st.label} className="min-w-0">
                  <div className="text-[9px] uppercase tracking-[0.07em] text-fg-tertiary font-semibold">{st.label}</div>
                  <div className="metric-sm mt-0.5">
                    <span>{st.value}</span>
                    {st.unit && <span className="metric-unit">{st.unit}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {trend && (
            <div className="flex items-center gap-1.5 mt-2.5">
              <span className={`delta ${trend === 'up' ? 'delta-up' : trend === 'down' ? 'delta-down' : 'delta-flat'}`}>
                {trend === 'up' ? '▲' : trend === 'down' ? '▼' : '●'} {trendValue}
              </span>
              <span className="text-[10px] text-fg-tertiary font-medium">{trendLabel}</span>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default function ExecutiveOverview({ dashboardData, briefing, briefingLoading, briefingError }: any) {
  const [activeKpiModal, setActiveKpiModal] = useState<string | null>(null);
  const [activeListTab, setActiveListTab] = useState<'top' | 'low' | 'delayed'>('top');
  // Axis/grid/tooltip chrome and the series palette all come from the shared
  // theme — nothing below hardcodes a colour any more.
  const { themeName, categorical, status: statusColors, chrome } = useChartTheme();
  const summary = dashboardData?.summary || {};
  const projects = dashboardData?.projects || [];

  const getProjectCapacity = (p: any) => {
    if (p.capacity_mwac && p.capacity_mwac > 0) return p.capacity_mwac;
    const name = p.p6_project_name || p.project_name || '';
    const match = name.match(/(\d+(?:\.\d+)?)\s*MW/i);
    if (match) return parseFloat(match[1]);
    return 0;
  };

  const totalProjects = summary.total_projects || 0;
  const delayedProjects = summary.delayed_projects || 0;
  const onTrackProjects = summary.on_track_projects || 0;
  const totalMW = summary.total_mw || 0;
  
  const { codMW, trMW } = useMemo(() => {
    return projects.reduce((acc: any, p: any) => {
      acc.codMW += (p.cod_mw || 0);
      acc.trMW += (p.tr_mw || 0);
      return acc;
    }, { codMW: 0, trMW: 0 });
  }, [projects]);

  const { totalPOValue, avgProgress, poDeliveredCr } = useMemo(() => {
    let poVal = 0;
    let progSum = 0;
    let validProg = 0;
    let deliveredCr = 0;
    projects.forEach((p: any) => {
      poVal += (p.sap?.po_value || 0);
      deliveredCr += (p.sap?.po_delivered_cr || 0);
      
      let prog = 0;
      const rawProg = p.p6?.progress;
      if (typeof rawProg === 'string' && rawProg.includes('%')) {
        prog = parseFloat(rawProg.replace('%', ''));
      } else {
        prog = Number(rawProg) || 0;
      }

      if (prog > 0) {
        progSum += prog;
        validProg++;
      }
    });
    return {
      totalPOValue: poVal,
      avgProgress: validProg ? (progSum / validProg) : 0,
      poDeliveredCr: deliveredCr
    };
  }, [projects]);

  const remainingPOValue = (totalPOValue / 10000000) - poDeliveredCr;

  const progressStages = useMemo(() => {
    let stages = { initiation: 0, early: 0, mid: 0, late: 0, completed: 0 };
    projects.forEach((p: any) => {
      const rawProg = p.p6?.progress;
      let prog = 0;
      if (typeof rawProg === 'string' && rawProg.includes('%')) {
        prog = parseFloat(rawProg.replace('%', ''));
      } else {
        prog = Number(rawProg) || 0;
      }
      
      if (prog >= 99.9) stages.completed++;
      else if (prog >= 75) stages.late++;
      else if (prog >= 50) stages.mid++;
      else if (prog >= 25) stages.early++;
      else stages.initiation++;
    });
    return stages;
  }, [projects]);

  const transmissionOverview = useMemo(() => {
    const map = new Map<string, Set<string | number>>();
    projects.forEach((p: any) => {
      const tc = p.tc?.data || {};
      ['khavda', 'rajasthan'].forEach(loc => {
        (tc[loc] || []).forEach((item: any) => {
          if (item.phase && item.voltage) {
            const key = `${item.phase} - ${item.voltage}`;
            if (!map.has(key)) map.set(key, new Set());
            // Use item.id for deduplication, fallback to random to count everything if no ID
            map.get(key)!.add(item.id || Math.random());
          }
        });
      });
    });
    return Array.from(map.entries())
      .map(([key, idSet]) => ({ key, count: idSet.size }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
  }, [projects]);

  const listProjects = useMemo(() => {
    if (activeListTab === 'delayed') return [...projects].filter((p: any) => p.p6?.health === 'Delayed');
    if (activeListTab === 'low') return [...projects].filter((p: any) => ((p.p6?.progress || 0) * 100) < 50);
    return projects;
  }, [projects, activeListTab]);

  const topSapProjects = useMemo(() => {
    return [...projects]
      .filter((p: any) => (p.sap?.req_qty || p.sap?.po_qty || p.sap?.inventory_qty) > 0)
      .sort((a, b) => (b.sap?.req_qty || b.sap?.po_qty || 0) - (a.sap?.req_qty || a.sap?.po_qty || 0))
      .slice(0, 5);
  }, [projects]);

  // Material pipeline is an ordered progression (Requirement → PO → Transit →
  // GRN), so it reads as one sequential ramp rather than four unrelated hues.
  const costChartOptions = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, right: 0 },
    grid: { left: 8, right: 16, bottom: 4, top: 32, containLabel: true },
    xAxis: { type: 'value', name: 'Qty', nameLocation: 'end' },
    yAxis: {
      type: 'category',
      data: topSapProjects.map(p => p.p6_project_name || p.project_name),
      axisLabel: { fontWeight: 600, fontSize: 11 }
    },
    series: [
      { name: 'Requirement', type: 'bar', stack: 'sap', data: topSapProjects.map(p => p.sap?.req_qty || 0) },
      { name: 'PO Raised', type: 'bar', stack: 'sap', data: topSapProjects.map(p => p.sap?.po_qty || 0) },
      { name: 'In-Transit', type: 'bar', stack: 'sap', data: topSapProjects.map(p => p.sap?.in_transit_qty || 0) },
      { name: 'Inventory/GRN', type: 'bar', stack: 'sap', data: topSapProjects.map(p => p.sap?.inventory_qty || 0) }
    ].map((s, i) => ({
      ...s,
      itemStyle: { color: [chrome.gridLine, categorical[0], categorical[3], categorical[1]][i] }
    }))
  };

  const originalScatterOptions = {
    tooltip: { trigger: 'item', formatter: (p: any) => `<strong>${p.data[2]}</strong><br/>Progress: ${p.data[0]}%<br/>Capacity: ${Number(p.data[1]).toFixed(1)} MW<br/>COD: ${p.data[3]}` },
    grid: { left: 8, right: 24, bottom: 4, top: 32, containLabel: true },
    xAxis: { type: 'value', name: 'Progress (%)', nameTextStyle: { padding: [0, 0, 10, 0] } },
    yAxis: { type: 'value', name: 'Capacity (MW)' },
    series: [{
      name: 'Projects', type: 'scatter',
      symbolSize: (data: any) => Math.max(10, Math.min(data[1] / 10, 40)),
      itemStyle: { color: categorical[0], opacity: 0.7, borderColor: chrome.surface1, borderWidth: 1 },
      data: projects.map((p: any) => ({ ...p, extractedCap: getProjectCapacity(p) })).filter((p: any) => p.extractedCap > 0).map((p: any) => {
        const codDateStr = p.p6?.planned_finish_date || p.p6?.scheduled_finish_date || p.p6?.finish_date;
        const cod = codDateStr ? new Date(codDateStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A';
        return [Math.round(p.p6?.progress || 0), parseFloat(p.extractedCap.toFixed(1)), p.p6_project_name || p.project_name, cod];
      })
    }]
  };

  // Here colour DOES encode state (complete / delayed / running), so this is
  // the one series on the screen allowed to use the reserved status palette.
  const queueScatterOptions = {
    tooltip: { trigger: 'item', formatter: (p: any) => `<strong>${p.data[2]}</strong><br/>Progress: ${Number(p.data[0]).toFixed(1)}%<br/>Capacity: ${Number(p.data[1]).toFixed(1)} MW<br/>COD: ${p.data[5]}<br/>Status: ${p.data[3]}${p.data[4] > 0 ? ' (' + p.data[4] + ' days delayed)' : ''}` },
    grid: { left: 8, right: 16, bottom: 0, top: 24, containLabel: true },
    xAxis: { type: 'value', name: 'Progress (%)' },
    yAxis: { type: 'value', name: 'Capacity (MW)' },
    series: [{
      name: 'Projects', type: 'scatter',
      symbolSize: (data: any) => Math.max(8, Math.min(data[1] / 15, 30)),
      itemStyle: {
        color: (params: any) =>
          params.data[0] >= 90 ? statusColors.done
            : params.data[3] === 'Delayed' ? statusColors.critical
            : statusColors.healthy,
        opacity: 0.85, borderColor: chrome.surface1, borderWidth: 1
      },
      data: listProjects.map((p: any) => ({ ...p, extractedCap: getProjectCapacity(p) })).filter((p: any) => p.extractedCap > 0).map((p: any) => {
        let delayDays = 0;
        const codDateStr = p.p6?.planned_finish_date || p.p6?.scheduled_finish_date || p.p6?.finish_date;
        const cod = codDateStr ? new Date(codDateStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A';
        if (p.p6?.baseline_finish_date) {
          const finishStr = p.p6?.scheduled_finish_date || p.p6?.finish_date;
          if (finishStr) {
            const finish = new Date(finishStr);
            const baseline = new Date(p.p6.baseline_finish_date);
            if (!isNaN(finish.getTime()) && !isNaN(baseline.getTime())) {
              delayDays = Math.max(0, Math.ceil((finish.getTime() - baseline.getTime()) / (1000 * 60 * 60 * 24)));
            }
          }
        }
        return [p.p6?.progress || 0, parseFloat(p.extractedCap.toFixed(1)), p.p6_project_name || p.project_name, p.p6?.health || 'On Track', delayDays, cod];
      })
    }]
  };

  const isLoading = !dashboardData || !dashboardData.summary || Object.keys(dashboardData.summary).length === 0;

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 w-full pb-8">
        {/* KPI band skeleton — mirrors the real two-tier layout so the page
            doesn't reflow when data lands. */}
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-3">
            {/* Spans written out in full — Tailwind's JIT scans literal text,
                so an interpolated `lg:col-span-${n}` would never be emitted. */}
            {['lg:col-span-6', 'lg:col-span-3', 'lg:col-span-3'].map((span, i) => (
              <div key={i} className={`${span} bento-card h-[132px] px-5 py-4 flex flex-col justify-between animate-pulse`}>
                <div className="flex justify-between items-start">
                  <div className="h-2.5 w-28 bg-fg-tertiary/20 rounded-sm"></div>
                  <div className="w-4 h-4 bg-fg-tertiary/20 rounded-full"></div>
                </div>
                <div>
                  <div className={`${i === 0 ? 'h-8 w-40' : 'h-6 w-20'} bg-fg-tertiary/20 rounded-sm mb-2`}></div>
                  <div className="h-2 w-32 bg-fg-tertiary/20 rounded-sm"></div>
                </div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-12 gap-3">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="lg:col-span-3 bento-card h-[96px] px-3.5 py-3 flex flex-col justify-between animate-pulse">
                <div className="flex justify-between items-start">
                  <div className="h-2.5 w-24 bg-fg-tertiary/20 rounded-sm"></div>
                  <div className="w-4 h-4 bg-fg-tertiary/20 rounded-full"></div>
                </div>
                <div>
                  <div className="h-5 w-16 bg-fg-tertiary/20 rounded-sm mb-2"></div>
                  <div className="h-2 w-24 bg-fg-tertiary/20 rounded-sm"></div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ROW 2: Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 bg-card border border-border rounded-xl shadow-sm p-6 min-h-[300px] animate-pulse">
            <div className="flex justify-between items-center mb-6">
              <div className="h-4 w-48 bg-muted-foreground/20 rounded"></div>
              <div className="flex gap-4">
                <div className="h-3 w-20 bg-muted-foreground/20 rounded"></div>
                <div className="h-3 w-20 bg-muted-foreground/20 rounded"></div>
              </div>
            </div>
            <div className="w-full h-[350px] bg-muted/40 rounded-lg"></div>
          </div>
          <div className="lg:col-span-1 bg-card border border-border rounded-xl shadow-sm p-6 min-h-[300px] animate-pulse">
            <div className="flex justify-between items-center mb-6">
              <div className="h-4 w-40 bg-muted-foreground/20 rounded"></div>
            </div>
            <div className="w-full h-[350px] bg-muted/40 rounded-lg"></div>
          </div>
        </div>

        {/* ROW 3: Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-1">
           <div className="bg-card border border-border rounded-xl shadow-sm p-6 min-h-[300px] animate-pulse">
            <div className="flex justify-between items-center mb-6">
              <div className="h-4 w-48 bg-muted-foreground/20 rounded"></div>
            </div>
            <div className="w-full h-[300px] bg-muted/40 rounded-lg"></div>
          </div>
          <div className="bg-card border border-border rounded-xl shadow-sm p-6 min-h-[300px] animate-pulse">
            <div className="flex justify-between items-center mb-6">
              <div className="h-4 w-48 bg-muted-foreground/20 rounded"></div>
            </div>
            <div className="w-full h-[300px] bg-muted/40 rounded-lg"></div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 w-full pb-8">

      {/* ══ KPI BAND ══
          Two tiers on a 12-column grid: one hero + two primary tiles carry the
          "how are we doing" answer, four supporting tiles sit beneath. All
          seven drill-downs are preserved. At 2560 the extra width flows into
          the hero tile rather than into dead margin. */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="flex flex-col gap-3"
      >
        {/* Tier 1 — focal */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-3">
          <KPICard
            className="lg:col-span-6"
            size="hero"
            tone="neutral"
            title="Portfolio Capacity"
            value={Math.round(codMW).toLocaleString('en-IN')}
            unit="MW at COD"
            stats={[
              { label: 'Trial Run', value: Math.round(trMW).toLocaleString('en-IN'), unit: 'MW' },
              { label: 'Total Planned', value: Math.round(totalMW).toLocaleString('en-IN'), unit: 'MW' },
            ]}
            icon={Zap}
            onClick={() => setActiveKpiModal('Portfolio Capacity')}
            info={
              <div className="space-y-1">
                <div><strong>Breaks down our power generation:</strong></div>
                <div><strong>COD</strong> is capacity that is fully operational and generating revenue.</div>
                <div><strong>Trial Run</strong> is capacity currently being tested. <strong>Total</strong> is the overall planned capacity.</div>
              </div>
            }
          />
          <KPICard
            className="lg:col-span-3"
            size="primary"
            tone="neutral"
            title="Total Projects"
            value={totalProjects}
            trend="up"
            trendValue={onTrackProjects}
            trendLabel="on track"
            icon={Activity}
            onClick={() => setActiveKpiModal('Total Projects')}
            info="Total number of active projects we are monitoring. 'On Track' means the project is running on schedule without any delays."
          />
          <KPICard
            className="lg:col-span-3"
            size="primary"
            tone={delayedProjects > 0 ? 'critical' : 'healthy'}
            title="Delayed Projects"
            value={delayedProjects}
            subtext="behind P6 baseline finish"
            icon={AlertTriangle}
            onClick={() => setActiveKpiModal('Delayed Projects')}
            info="Projects that have fallen behind their original planned completion dates in our Primavera P6 schedule."
          />
        </div>

        {/* Tier 2 — supporting */}
        <div className="grid grid-cols-2 lg:grid-cols-12 gap-3">
          <KPICard
            className="lg:col-span-3"
            size="supporting"
            tone="warning"
            title="Quality (Pulse)"
            value={summary?.quality?.open_ncs || 0}
            unit="open NCs"
            subtext={`${(summary?.quality?.total_rfis || 0) - (summary?.quality?.completed_rfis || 0)} open RFIs`}
            icon={Shield}
            onClick={() => setActiveKpiModal('Quality (Pulse)')}
            info="Live data from the Pulse Quality system. Shows how many Non-Conformance (NC) and Request for Information (RFI) issues are currently open and need attention."
          />
          <KPICard
            className="lg:col-span-3"
            size="supporting"
            tone="neutral"
            title="Total PO Value"
            value={`₹${(totalPOValue / 10000000).toFixed(1)}`}
            unit="Cr"
            subtext="all purchase orders, SAP"
            icon={IndianRupee}
            onClick={() => setActiveKpiModal('Total PO Value')}
            info="The total value of all Purchase Orders across every project, pulled directly from SAP. Click this card to see the breakdown by project."
          />
          {/*
          <KPICard
            className="lg:col-span-3"
            size="supporting"
            tone="warning"
            title="Remaining PO Value"
            value={`₹${Math.max(0, remainingPOValue).toFixed(1)}`}
            unit="Cr"
            subtext="pending delivery"
            icon={IndianRupee}
            onClick={() => setActiveKpiModal('Remaining PO Value')}
            info="The value of materials we have ordered from vendors but haven't received yet. Calculated by taking Total PO Value minus materials already delivered."
          />
          */}
          <KPICard
            className="lg:col-span-3"
            size="supporting"
            tone="healthy"
            title="Completed Projects"
            value={progressStages.completed}
            subtext="100% delivered"
            icon={CheckCircle2}
            onClick={() => setActiveKpiModal('Completed Projects')}
            info="Projects that are 100% complete and successfully delivered."
            infoAlign="right"
          />
        </div>
      </motion.div>

      {/* ROW 2: Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Left Col (Span 2) */}
        <div className="lg:col-span-2 flex flex-col gap-4">

          {/* SECTION: AI EXECUTIVE BRIEF
          <motion.div variants={itemVariants} initial="hidden" animate="show" className="bento-card p-4">
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-2">
                <Bot className="w-4 h-4 text-primary" />
                <h3 className="text-[14px] font-bold text-foreground dark:text-white">Executive Intelligence Brief</h3>
              </div>
              <div className="text-[10px] font-bold text-success bg-success/10 px-2.5 py-0.5 rounded-full flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-success/100 animate-pulse"></span> {briefing?.confidenceScore || 87}%
              </div>
            </div>

            <div className="bg-muted dark:bg-gray-900/50 rounded-lg p-4 border border-muted dark:border-border">
              <div className="flex justify-between items-center mb-3">
                <div className="flex items-center gap-1.5 text-[10px] font-bold text-muted-foreground uppercase tracking-[0.08em]">
                  <Zap className="w-3 h-3 text-primary" /> AI-GENERATED SUMMARY
                </div>
                <div className="text-[9px] font-medium text-muted-foreground uppercase tracking-[0.08em]">
                  Generated Live
                </div>
              </div>

              <div className="mt-2">
                {briefingLoading ? (
                  <div className="flex items-center gap-3 py-6 text-primary text-sm font-medium justify-center">
                    <RefreshCw className="w-5 h-5 animate-spin" /> Analyzing live SAP & P6 data...
                  </div>
                ) : briefingError ? (
                  <div className="text-sm text-destructive font-medium py-4 flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" /> {briefingError}
                  </div>
                ) : (
                  <>
                    <p className="text-[13px] text-foreground dark:text-muted-foreground leading-relaxed">
                      {briefing?.toplineSummary || "Insufficient data to generate portfolio summary."}
                    </p>
                    <div className="flex items-center gap-2 mt-4 flex-wrap">
                      {briefing?.keyActions?.map((a: any, i: number) => {
                        const isRed = a.title.toLowerCase().includes('risk') || a.color === 'red';
                        const isAmber = a.title.toLowerCase().includes('cost') || a.color === 'amber' || a.title.toLowerCase().includes('monitor');
                        const colorTheme = isRed ? 'text-destructive bg-destructive/10 border-destructive/20 dark:text-destructive dark:bg-destructive/100/10 dark:border-destructive/20' :
                          isAmber ? 'text-warning bg-warning/10 border-warning/20 dark:text-warning dark:bg-warning/100/10 dark:border-warning/20' :
                            'text-success bg-success/10 border-success/20 dark:text-success dark:bg-success/100/10 dark:border-success/20';

                        return (
                          <span key={i} className={`text-[11px] px-3 py-1.5 flex items-center gap-1.5 border rounded-full font-semibold shadow-sm ${colorTheme}`}>
                            <AlertCircle className="w-3.5 h-3.5" /> {a.title}
                          </span>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            </div>
          </motion.div>
          */}

          <motion.div variants={itemVariants} initial="hidden" animate="show" className="bg-card border border-border dark:border-border rounded-xl shadow-sm p-6 flex-1 flex flex-col min-h-[300px]">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-6">
              <h4 className="text-sm font-bold text-foreground dark:text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-primary" /> Project Execution Queue
              </h4>
              {/*
              <div className="flex bg-muted dark:bg-card p-1 border border-border dark:border-gray-700 rounded-lg text-xs font-semibold">
                <button onClick={() => setActiveListTab('top')} className={`px-4 py-1.5 rounded-md transition-all ${activeListTab === 'top' ? 'bg-white dark:bg-gray-700 text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground dark:hover:text-white'}`}>All</button>
                <button onClick={() => setActiveListTab('low')} className={`px-4 py-1.5 rounded-md transition-all ${activeListTab === 'low' ? 'bg-white dark:bg-gray-700 text-warning shadow-sm' : 'text-muted-foreground hover:text-foreground dark:hover:text-white'}`}>&lt; 50%</button>
                <button onClick={() => setActiveListTab('delayed')} className={`px-4 py-1.5 rounded-md transition-all ${activeListTab === 'delayed' ? 'bg-white dark:bg-gray-700 text-destructive shadow-sm' : 'text-muted-foreground hover:text-foreground dark:hover:text-white'}`}>Delayed</button>
              </div>
              */}
              <div className="flex items-center gap-5 text-xs font-medium text-foreground dark:text-muted-foreground">
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#3b82f6] shadow-sm ring-1 ring-white/10"></div> On Track (&lt; 90%)</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#10b981] shadow-sm ring-1 ring-white/10"></div> Near Completion (&ge; 90%)</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#ef4444] shadow-sm ring-1 ring-white/10"></div> Delayed</div>
              </div>
            </div>
            <div className="flex-1 w-full min-h-[250px]">
              <ReactECharts theme={themeName} option={queueScatterOptions} style={{ height: '100%', width: '100%' }} />
            </div>
          </motion.div>
        </div>

        {/* Right Col */}
        <div className="flex flex-col gap-4">
          {/*
          <motion.div variants={itemVariants} initial="hidden" animate="show" className="bento-card p-6 flex-none">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-sm font-bold text-foreground dark:text-white flex items-center gap-2"><Layers className="w-5 h-5 text-primary" /> Progress Stage</h3>
              <div className="text-[11px] font-bold text-muted-foreground uppercase bg-muted dark:bg-card px-2 py-1 rounded-md">{totalProjects} total</div>
            </div>
            <div className="space-y-5 text-xs font-semibold">
              {[
                { phase: 'Initiation (0-25%)', count: progressStages.initiation, color: 'bg-gray-400' },
                { phase: 'Early (26-50%)', count: progressStages.early, color: 'bg-blue-400' },
                { phase: 'Mid (51-75%)', count: progressStages.mid, color: 'bg-amber-400' },
                { phase: 'Late (76-99%)', count: progressStages.late, color: 'bg-primary' },
                { phase: 'Completed (100%)', count: progressStages.completed, color: 'bg-success/100' }
              ].map((p, i) => (
                <div key={i} className="flex items-center justify-between group">
                  <div className="w-32 text-muted-foreground group-hover:text-foreground dark:group-hover:text-white transition-colors">{p.phase}</div>
                  <div className="flex-1 h-2.5 bg-muted dark:bg-card rounded-full mx-4 overflow-hidden"><div className={`h-full ${p.color}`} style={{ width: `${(p.count / Math.max(1, totalProjects)) * 100}%` }}></div></div>
                  <div className="w-6 text-right text-foreground dark:text-white">{p.count}</div>
                </div>
              ))}
            </div>
          </motion.div>
          */}

          <motion.div variants={itemVariants} initial="hidden" animate="show" className="bento-card p-6 h-fit">
            <h3 className="text-sm font-bold text-foreground dark:text-white flex items-center justify-between mb-4 shrink-0">
              <span className="flex items-center gap-2"><Activity className="w-5 h-5 text-primary" /> Transmission Network</span>
            </h3>
            <div className="space-y-1 overflow-y-auto custom-scrollbar pr-2">
              {transmissionOverview.map((node, i) => (
                <div key={i} className="flex justify-between items-center py-1.5 border-b border-muted dark:border-border last:border-0 text-sm">
                  <div className="flex items-center gap-2.5 text-foreground dark:text-muted-foreground font-semibold flex-1 pr-2">
                    <Zap className={`w-4 h-4 text-success shrink-0`} />
                    <span className="line-clamp-1" title={node.key}>{node.key}</span>
                  </div>
                  <div className="text-[11px] font-bold text-muted-foreground bg-muted dark:bg-gray-900/50 px-2.5 py-1 rounded-md shrink-0 border border-border dark:border-gray-700">{node.count} Lines</div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>

      {/* ROW 3: ECharts */}
      <motion.div variants={itemVariants} initial="hidden" animate="show" className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bento-card p-4 flex flex-col h-[350px]">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-sm font-bold text-foreground dark:text-white flex items-center gap-2"><Package className="w-5 h-5 text-primary" /> SAP Material Pipeline (Qty)</h3>
          </div>
          <div className="flex-1 w-full">
            <ReactECharts theme={themeName} option={costChartOptions} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        <div className="bento-card p-4 flex flex-col h-[350px]">
          <h3 className="text-sm font-bold text-foreground dark:text-white flex items-center gap-2 mb-4"><Activity className="w-5 h-5 text-primary" /> Progress vs Capacity Distribution</h3>
          <div className="flex-1 w-full">
            <ReactECharts theme={themeName} option={originalScatterOptions} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
      </motion.div>

      <KPIDetailsModal
        isOpen={!!activeKpiModal}
        onClose={() => setActiveKpiModal(null)}
        activeKpi={activeKpiModal}
        projects={projects}
        summary={summary}
      />
    </div>
  );
}
