import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import ExecutionIntelligence from './ExecutionIntelligence';
import MaterialValuePanel from './MaterialValuePanel';
import MaterialPipelinePanel from './MaterialPipelinePanel';
import {
  Activity, IndianRupee, AlertTriangle, Zap, Package, CheckCircle2, Shield, Network, HelpCircle, MapPin
} from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import { motion } from 'framer-motion';
import KPIDetailsModal from '../../components/ui/KPIDetailsModal';
import { useChartTheme } from '../../lib/chartTheme';
import {
  KPITile, Card, CardHeader, ChartFrame, PageHeader, SourceTag, Metric, MiniMeter,
  containerVariants, itemVariants,
} from '../../components/ui/primitives';
import NetworkOverviewMap from './NetworkOverviewMap';

/* ── Trajectory data ──────────────────────────────────────────────────────
   /api/metrics/history reconstructs monthly series from the timestamps on the
   underlying records (PO document dates, NC created/approved dates, P6 start
   dates). It publishes a key only where a real series exists.

   The guard below is the important part. These series are computed by a
   different query from the scalars on /dashboard/summary, so they can silently
   disagree — 4,378 Cr against a tile printing 59,753. A sparkline whose last
   point contradicts the number above it is worse than no sparkline, so a
   series is used ONLY if it lands on the displayed value. Anything else keeps
   its proportion bar, and tiles light up on their own as the backend
   reconciles. No tile can contradict itself. */
type HistoryPayload = { series?: Record<string, { series: number[]; period: string }> };

function useTrajectory(phase: string, portfolio: string | null) {
  const [history, setHistory] = useState<HistoryPayload>({});

  useEffect(() => {
    const qs = new URLSearchParams({ months: '12' });
    if (phase) qs.set('phase', phase);
    if (portfolio) qs.set('portfolio', portfolio);
    let live = true;
    fetch(`/akasha/api/metrics/history?${qs}`)
      .then((r) => (r.ok ? r.json() : { series: {} }))
      .then((d) => { if (live) setHistory(d || { series: {} }); })
      .catch(() => { if (live) setHistory({ series: {} }); });
    return () => { live = false; };
  }, [phase, portfolio]);

  /** A series is usable only when its final point agrees with `current`. */
  const reconciles = (key: string, current: number) => {
    const entry = history.series?.[key];
    if (!entry || entry.series.length < 4) return undefined;
    const last = entry.series[entry.series.length - 1];
    const scale = Math.max(Math.abs(current), 1);
    const agrees = Math.abs(last - current) <= 1 || Math.abs(last - current) / scale <= 0.02;
    return agrees ? entry : undefined;
  };

  /* Sparklines only — no proportion bars. A tile shows a plot when its
     series reconciles with the figure printed above it, and nothing when it
     does not. Reconciling today: open NCs, open RFIs, NC closure rate and
     project count. PO value was 10.4% adrift because the headline summed
     per-project WBS matches and dropped unmatched POs; it now reads the ZSPS
     grand total from the API. Still outstanding: COD capacity (derived from
     TC block data, not capacity_mwac) and delayed projects
     (finish_date_variance is a snapshot with no history). */
  return reconciles;
}

export default function ExecutiveOverview({ dashboardData, briefing, briefingLoading, briefingError, onTabChange }: any) {
  const [activeKpiModal, setActiveKpiModal] = useState<string | null>(null);
  const [activeListTab, setActiveListTab] = useState<'top' | 'low' | 'delayed'>('top');
  // Axis/grid/tooltip chrome and the series palette all come from the shared
  // theme — nothing below hardcodes a colour any more.
  const { themeName, categorical, status: statusColors, chrome } = useChartTheme();
  const summary = dashboardData?.summary || {};
  const projects = dashboardData?.projects || [];

  /* Same scope the header applies, so the series matches the visible figures. */
  const [searchParams] = useSearchParams();
  const trajectoryFor = useTrajectory(
    searchParams.get('phase') || 'Ongoing',
    searchParams.get('portfolio')
  );

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

  /* Rupees → crore happens once, here, rather than at each call site.
     The portfolio PO figure comes from the ZSPS grand total the API now
     returns; totalPOValue (summed from per-project WBS matches) is only a
     fallback, and it undercounts by every PO with no project prefix. */
  const totalPOCr = (summary.total_po_value ?? totalPOValue) / 10000000;

  /* Crore values were the one figure not going through en-IN grouping, so a
     portfolio total rendered as "59753.0" beside neighbours like "9,832".
     Past four digits the decimal is noise, so it is dropped. */
  const fmtCr = (n: number) =>
    n >= 1000 ? Math.round(n).toLocaleString('en-IN') : n.toFixed(1);
  const poDeliveredTotalCr = summary.total_po_delivered_cr ?? poDeliveredCr;
  const remainingPOValue = totalPOCr - poDeliveredTotalCr;

  /* Pulse quality. `total_ncs` is what gives the KPI tile a real denominator —
     without it the tile falls back to trajectory mode C. */
  const totalNCs = summary?.quality?.total_ncs || 0;
  const openNCs = summary?.quality?.open_ncs || 0;
  const openRFIs = summary?.quality?.rfis_in_flight || 0;
  const totalRFIs = summary?.quality?.total_rfis || 0;
  const closureRate = Math.round(summary?.quality?.closure_rate || 0);

  /* Transmission coverage: how much of the portfolio has grid connectivity
     mapped at all. Readiness would be the better measure, but TcNetworkEdge
     .status holds mis-parsed values ('7', '11', 'Mar-30') rather than a state,
     so it cannot be derived until that sync is fixed. */
  const tc = useMemo(() => {
    let mapped = 0;
    let lines = 0;
    projects.forEach((p: any) => {
      if (p.tc?.has_data) mapped++;
      const d = p.tc?.data || {};
      lines += (d.khavda?.length || 0) + (d.rajasthan?.length || 0);
    });
    return { mapped, lines };
  }, [projects]);

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
      /* 10 rather than 6: the rail now stretches to the height of the plot
         beside it, and the panel scrolls, so more of the network is visible
         before the reader has to open the Transmission module. */
      .slice(0, 10);
  }, [projects]);

  /* Scales each row's bar against the busiest group, so the rail reads as a
     comparison rather than ten unrelated numbers. */
  const maxLineCount = useMemo(
    () => Math.max(1, ...transmissionOverview.map((n) => n.count)),
    [transmissionOverview]
  );

  const listProjects = useMemo(() => {
    if (activeListTab === 'delayed') return [...projects].filter((p: any) => p.p6?.health === 'Delayed');
    if (activeListTab === 'low') return [...projects].filter((p: any) => ((p.p6?.progress || 0) * 100) < 50);
    return projects;
  }, [projects, activeListTab]);

  // Material pipeline is an ordered progression (Requirement → PO → Transit →
  // GRN), so it reads as one sequential ramp rather than four unrelated hues.
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
    <div className="flex w-full flex-col gap-4 pb-8">

      {/* Names the surface and states where its figures come from. On a screen
          that drives capital decisions, provenance is part of the design. */}
      <PageHeader
        title="Portfolio Overview"
        subtitle={`${totalProjects} mapped projects · ${Math.round(totalMW).toLocaleString('en-IN')} MW planned capacity`}
        right={
          <div className="flex flex-wrap items-center gap-1.5">
            <SourceTag system="P6" />
            <SourceTag system="SAP" />
            <SourceTag system="TC" />
            <SourceTag system="Pulse" />
          </div>
        }
      />

      {/* ══ KPI BAND ══
          One hero + two primary tiles carry the "how are we doing" answer;
          three supporting tiles sit beneath. Every drill-down is preserved,
          and the tile stays visibly selected while its modal is open.

          No KPI here has a measured history yet (see /api/metrics/history in
          the KPI spec), so every tile resolves to trajectory mode B — the
          figure against its own total — rather than showing an invented line.
          When the snapshot endpoint lands, adding `trajectory` to a tile is
          the only change needed to promote it to a sparkline. */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="flex flex-col gap-3"
      >
        {/* One weight for every KPI. A CSS grid with auto-rows-fr rather than
            flex-wrap: KPITile sets h-full on its wrapper, and a percentage
            height on a flex item in an auto-height row resolves to auto, which
            is what left the cards ragged. Grid rows have a definite height. */}
        <div className="grid auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <KPITile
            className="min-w-0"
            size="primary"
            tone="neutral"
            polarity="up-good"
            label="Portfolio Capacity"
            value={Math.round(codMW).toLocaleString('en-IN')}
            unit="MW at COD"
            subtext={`of ${Math.round(totalMW).toLocaleString('en-IN')} MW planned`}
            trajectory={trajectoryFor('portfolio_capacity', codMW)}
            icon={Zap}
            selected={activeKpiModal === 'Portfolio Capacity'}
            onClick={() => setActiveKpiModal('Portfolio Capacity')}
            info={
              <div className="space-y-1">
                <div><strong>Breaks down our power generation:</strong></div>
                <div><strong>COD</strong> is capacity that is fully operational and generating revenue.</div>
                <div><strong>Trial Run</strong> is capacity currently being tested. <strong>Total</strong> is the overall planned capacity.</div>
              </div>
            }
          />

          {/* Total + Delayed + Completed folded into one tile: the portfolio
              count leads, and its two states sit beneath as the breakdown. */}
          <KPITile
            className="min-w-0"
            size="primary"
            tone={delayedProjects > 0 ? 'critical' : 'healthy'}
            polarity="down-good"
            label="Project Delivery"
            value={totalProjects}
            stats={[
              { label: 'Delayed', value: delayedProjects },
              { label: 'Completed', value: progressStages.completed },
            ]}
            trajectory={trajectoryFor('total_projects', totalProjects)}
            icon={Activity}
            selected={activeKpiModal === 'Total Projects'}
            onClick={() => setActiveKpiModal('Total Projects')}
            info="Every project we monitor, split by state. Delayed means behind the Primavera P6 baseline finish; Completed means 100% delivered. The remainder are on track."
          />

          <KPITile
            className="min-w-0"
            size="primary"
            tone="neutral"
            polarity="neutral"
            label="Total PO Value"
            value={`₹${fmtCr(totalPOCr)}`}
            unit="Cr"
            subtext={`${fmtCr(poDeliveredTotalCr)} Cr delivered`}
            trajectory={trajectoryFor('po_value', totalPOCr)}
            icon={IndianRupee}
            selected={activeKpiModal === 'Total PO Value'}
            onClick={() => setActiveKpiModal('Total PO Value')}
            info="Every purchase order in ZSPS, ordered value against delivered value. Read from the ZSPS grand total rather than summed per project, so POs whose WBS maps to no project are still counted."
          />

          {/* Open NCs, closure rate and open RFIs on one tile: the open count
              leads, the other two ride beneath it as the breakdown. */}
          <KPITile
            className="min-w-0"
            size="primary"
            tone={closureRate >= 80 ? 'healthy' : closureRate >= 50 ? 'watch' : 'risk'}
            polarity="down-good"
            label="Quality"
            value={openNCs}
            unit="open NCs"
            stats={[
              { label: 'Closure', value: `${closureRate}%` },
              { label: 'Open RFIs', value: openRFIs.toLocaleString('en-IN') },
            ]}
            trajectory={trajectoryFor('open_ncs', openNCs)}
            icon={Shield}
            selected={activeKpiModal === 'Quality (Pulse)'}
            onClick={() => setActiveKpiModal('Quality (Pulse)')}
            info="Live from Pulse. The figure is open Non-Conformances; Closure is the share of all NCs resolved and approved, and Open RFIs are site questions still awaiting an answer."
          />

          <KPITile
            className="min-w-0"
            size="primary"
            tone="neutral"
            polarity="up-good"
            label="Grid Connectivity"
            value={tc.mapped}
            denominator={`/${totalProjects}`}
            subtext={`${tc.lines.toLocaleString('en-IN')} lines mapped`}
            icon={Network}
            info="Projects with transmission connectivity mapped in the TC portal. Evacuation readiness is not shown because the TC status field currently holds unparsed values."
            infoAlign="right"
          />
        </div>
      </motion.div>

      {/* ══ ANALYTICAL ROW ══
          Sized in viewport units rather than a fixed 350px, so at 1920 it
          fills the fold and at 2560 it grows with the screen instead of
          leaving a band of dead canvas underneath. The right rail stretches
          to the same height as the plot beside it — previously it was `h-fit`
          and left roughly 200px of empty column. */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 items-stretch gap-3 lg:min-h-[540px] lg:grid-cols-12"
      >
        <motion.div variants={itemVariants} className="flex min-h-0 lg:col-span-8">
          <ExecutionIntelligence projects={listProjects} />
        </motion.div>

        {/* Right rail */}
        <motion.div variants={itemVariants} className="flex min-h-0 flex-col lg:col-span-4 h-full">
          {transmissionOverview.length === 0 ? (
            <Card pad="md" className="flex min-h-0 flex-1 flex-col">
              <CardHeader
                eyebrow="Evacuation readiness"
                title="Transmission Network"
                icon={Network}
                right={<SourceTag system="TC" />}
              />
              <div className="flex flex-1 items-center justify-center px-4 py-8 text-center text-[12px] text-fg-tertiary">
                No transmission lines mapped for this scope.
              </div>
            </Card>
          ) : (
            <div className="flex-1 w-full h-full min-h-[400px]">
              <NetworkOverviewMap onTabChange={onTabChange} />
            </div>
          )}
        </motion.div>
      </motion.div>

      {/* ══ SECONDARY ROW ══
          7/5 rather than 6/6: the stacked pipeline carries four series and
          long project names on its category axis, so it needs the wider half. */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 items-stretch gap-3 lg:grid-cols-12"
      >
        <ChartFrame
          className="lg:col-span-7"
          eyebrow="Delivered + in transit = ordered"
          title="SAP Material Pipeline"
          icon={Package}
          right={<SourceTag system="SAP" />}
          height={360}
        >
          <MaterialPipelinePanel projects={projects} />
        </ChartFrame>

        <ChartFrame
          className="lg:col-span-5"
          eyebrow="Ordered · delivered · in transit"
          title="Material Value"
          icon={Package}
          right={<SourceTag system="SAP" />}
          height={360}
        >
          <MaterialValuePanel />
        </ChartFrame>

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
