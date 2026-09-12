import React, { useMemo, useState, useRef, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  Activity, Maximize2, Minimize2, ChevronDown, Search, BarChart3,
  AlertTriangle, X, Star, Clock, CheckCircle2,
} from 'lucide-react';
import { useChartTheme } from '../../lib/chartTheme';
import { cx } from '../../components/ui/primitives/cx';
import ConstructionUnits from './ConstructionUnits';

/* ═══════════════════════════════════════════════════════════════════════════
   EXECUTION INTELLIGENCE
   Two readings of the same execution data.

   BUBBLE VIEW answers "where should I look first?" — every mapped project
   placed on progress against capacity, split into quadrants at the portfolio
   medians so the split moves with the portfolio instead of sitting on an
   invented threshold. A 400MW project at 27% is a different problem from a
   50MW project at 27%, and the quadrant is what says so.

   TREND VIEW answers "will this one land?" — planned pace against achieved
   pace, extended at the observed velocity to a projected completion.

   ── On what is measured and what is inferred ──────────────────────────────
   The API returns ONE progress reading per project (`p6.progress`, as at
   `p6.data_date`), not a time series. So the trend view plots what can be
   defended and nothing more:

     Planned    baseline_start -> baseline_finish, 0 -> 100%. Real dates.
     Achieved   two real anchors — 0% at start_date, current % at the data
                date — joined by a straight line. That line is the AVERAGE
                pace to date, not a history of it, and it is drawn and
                labelled as such rather than dressed up as a measured curve.
     Forecast   that same achieved velocity carried forward to 100%.

   Nothing here invents a data point. If a project is missing the dates the
   maths needs, the trend view says so instead of drawing a plausible line.
   ═══════════════════════════════════════════════════════════════════════════ */

const DAY = 24 * 60 * 60 * 1000;
const WEEK = 7 * DAY;

export interface ExecProject {
  name: string;
  capacityMW: number;
  progress: number;
  status: 'On Track' | 'Near Completion' | 'Delayed';
  delayDays: number;
  codLabel: string;
  p6ObjectId: number | null;
  p6ProjectId: string | null;
  startDate: Date | null;
  dataDate: Date | null;
  baselineStart: Date | null;
  baselineFinish: Date | null;
  raw: any;
}

const fmtDate = (d: Date | null) =>
  d ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A';
const fmtMonth = (d: Date | null) =>
  d ? d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' }) : 'N/A';

const toDate = (v: any): Date | null => {
  if (!v) return null;
  const d = new Date(v);
  return isNaN(d.getTime()) ? null : d;
};

/* One definition of the four quadrants: geometry, colour and copy together,
   so the chip and the region it labels can never drift apart. */
const QUADS = [
  { key: 'hl', hiCap: true, hiProg: false, rgb: '217,45,32', note: 'Needs attention',
    title: 'High Capacity · Low Progress',
    cls: 'border-status-critical-border bg-status-critical-bg text-status-critical-fg', pos: 'left-1 top-1' },
  { key: 'hh', hiCap: true, hiProg: true, rgb: '46,144,250', note: 'On track',
    title: 'High Capacity · High Progress',
    cls: 'border-status-done-border bg-status-done-bg text-status-done-fg', pos: 'right-1 top-1' },
  { key: 'll', hiCap: false, hiProg: false, rgb: '18,183,106', note: 'Monitor',
    title: 'Low Capacity · Low Progress',
    cls: 'border-status-healthy-border bg-status-healthy-bg text-status-healthy-fg', pos: 'left-1 bottom-1' },
  { key: 'lh', hiCap: false, hiProg: true, rgb: '247,144,9', note: 'Near completion',
    title: 'Low Capacity · High Progress',
    cls: 'border-status-watch-border bg-status-watch-bg text-status-watch-fg', pos: 'right-1 bottom-1' },
] as const;

const QUAD_ICON: Record<string, any> = { hl: AlertTriangle, hh: Star, ll: CheckCircle2, lh: Clock };

const median = (xs: number[]) => {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

/* ── Small pieces ─────────────────────────────────────────────────────── */

const Chip = ({ tone, label }: { tone: string; label: string }) => (
  <span className="flex items-center gap-1.5 whitespace-nowrap text-[11px] font-medium text-fg-secondary">
    <span className="h-2 w-2 rounded-full" style={{ background: tone }} />
    {label}
  </span>
);

/* ═══════════════════════════════════════════════════════════════════════ */

export default function ExecutionIntelligence({
  projects,
  onOpenProject,
}: {
  projects: any[];
  onOpenProject?: (p: any) => void;
}) {
  const { themeName, status: statusColors, chrome } = useChartTheme();
  const [view, setView] = useState<'bubble' | 'trend'>('bubble');
  const [expanded, setExpanded] = useState(false);
  const [filter, setFilter] = useState<'all' | 'On Track' | 'Near Completion' | 'Delayed'>('all');
  const [filterOpen, setFilterOpen] = useState(false);
  const [quadFilter, setQuadFilter] = useState<string | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; p: ExecProject } | null>(null);
  const [pinned, setPinned] = useState<ExecProject | null>(null);
  const [compare, setCompare] = useState<ExecProject[]>([]);
  const [trendProject, setTrendProject] = useState<string | null>(null);
  const [trendOpen, setTrendOpen] = useState(false);
  const plotRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  /* echarts-for-react sizes the canvas once at mount and then only listens to
     window resizes. In a flex row the plot's box is still settling at that
     point, so the canvas kept its first (small) height and the chart rendered
     squashed into a band with the card's space left empty underneath. A
     ResizeObserver on the actual container is what makes it fill. */
  useEffect(() => {
    const el = plotRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    let frame = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        try { chartRef.current?.getEchartsInstance?.().resize(); } catch { /* chart not mounted yet */ }
      });
    });
    ro.observe(el);
    return () => { cancelAnimationFrame(frame); ro.disconnect(); };
  }, []);

  /* ── Normalise once ── */
  const all: ExecProject[] = useMemo(() => {
    return (projects || []).map((p: any) => {
      const cap = p.capacity_mwac && p.capacity_mwac > 0
        ? p.capacity_mwac
        : parseFloat((String(p.p6_project_name || p.project_name || '').match(/(\d+(?:\.\d+)?)\s*MW/i) || [])[1] || '0');
      const progress = Number(p.p6?.progress || 0);
      const scheduled = toDate(p.p6?.scheduled_finish_date || p.p6?.finish_date);
      const baselineFinish = toDate(p.p6?.baseline_finish_date);
      let delayDays = 0;
      if (scheduled && baselineFinish) {
        delayDays = Math.max(0, Math.ceil((scheduled.getTime() - baselineFinish.getTime()) / DAY));
      }
      const status: ExecProject['status'] =
        p.p6?.health === 'Delayed' ? 'Delayed' : progress >= 90 ? 'Near Completion' : 'On Track';
      return {
        name: p.p6_project_name || p.project_name || 'Unnamed project',
        capacityMW: Number(cap) || 0,
        progress,
        status,
        delayDays,
        codLabel: fmtDate(toDate(p.p6?.planned_finish_date) || scheduled),
        p6ObjectId: p.p6?.object_id ?? null,
        p6ProjectId: p.p6?.id ?? null,
        startDate: toDate(p.p6?.start_date) || toDate(p.p6?.planned_start_date),
        dataDate: toDate(p.p6?.data_date),
        baselineStart: toDate(p.p6?.baseline_start_date),
        baselineFinish,
        raw: p,
      };
    });
  }, [projects]);

  /* A project with no capacity figure cannot be placed on a capacity axis, so
     it is excluded from the plot — but the count is reported rather than
     hidden. The header said "63 mapped projects" while the chart said
     "56 of 56", and nothing on screen accounted for the 7 that vanished.
     They are the PSS pooling stations, which carry no generation capacity. */
  const plottable = useMemo(() => all.filter((p) => p.capacityMW > 0), [all]);
  const noCapacity = useMemo(() => all.filter((p) => p.capacityMW <= 0), [all]);

  const byStatus = useMemo(
    () => (filter === 'all' ? plottable : plottable.filter((p) => p.status === filter)),
    [plottable, filter]
  );

  const medProgress = useMemo(() => median(plottable.map((p) => p.progress)), [plottable]);
  const medCapacity = useMemo(() => median(plottable.map((p) => p.capacityMW)), [plottable]);

  /* The medians come from the WHOLE portfolio, so the quadrant boundary does
     not move when a filter narrows the marks on screen. */
  const shown = useMemo(() => {
    if (!quadFilter) return byStatus;
    const want = { hl: [true, false], hh: [true, true], ll: [false, false], lh: [false, true] }[quadFilter];
    if (!want) return byStatus;
    return byStatus.filter((p) =>
      (p.capacityMW >= medCapacity) === want[0] && (p.progress >= medProgress) === want[1]
    );
  }, [byStatus, quadFilter, medCapacity, medProgress]);

  const toneFor = (s: ExecProject['status']) =>
    s === 'Delayed' ? statusColors.critical : s === 'Near Completion' ? statusColors.done : statusColors.healthy;

  const active = pinned || hover?.p || null;
  const selected = useMemo(
    () => all.find((p) => p.name === trendProject) || all[0] || null,
    [all, trendProject]
  );

  /* ── Bubble view ─────────────────────────────────────────────────────── */
  const bubbleOption = useMemo(() => {
    /* A round ceiling and a round interval, or the axis prints 850 / 800 /
       600 / 400 with unlabelled ticks in between. */
    const capMax = Math.max(...shown.map((p) => p.capacityMW), 1);
    const step = capMax > 1600 ? 400 : capMax > 800 ? 200 : capMax > 400 ? 100 : 50;
    const yMax = Math.ceil(capMax / step) * step;
    return {
      grid: { left: 30, right: 42, bottom: 40, top: 18, containLabel: true },
      xAxis: {
        type: 'value', name: 'Progress (%)', min: -4, max: 104,
        nameLocation: 'middle', nameGap: 32,
        axisLabel: { formatter: (v: number) => (v < 0 || v > 100 ? '' : `${v}`) },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value', name: 'Capacity (MW)', min: 0, max: yMax, interval: step,
        nameLocation: 'middle', nameRotate: 90, nameGap: 40,
        splitLine: { lineStyle: { opacity: 0.35 } },
      },
      tooltip: { show: false },
      series: [{
        type: 'scatter',
        symbolSize: 14,
        clip: false,
        itemStyle: {
          color: (pr: any) => toneFor(pr.data[3]),
          opacity: 1,
          borderColor: chrome.surface1,
          borderWidth: 1.5,
        },
        emphasis: { itemStyle: { borderWidth: 3, borderColor: chrome.fgPrimary }, scale: 1.5 },
        data: shown.map((p) => [p.progress, p.capacityMW, p.name, p.status, p]),
        /* The four sections carry the same colours as their chips, so the
           chip and the region it names read as one thing. Kept very low
           alpha: the marks are the data, the tint is only the address.
           Selecting a quadrant lifts it and drops the other three. */
        markArea: {
          silent: true,
          data: QUADS.map((q) => {
            const on = !quadFilter || quadFilter === q.key;
            const a = quadFilter ? (on ? 0.14 : 0.02) : 0.075;
            return [
              {
                xAxis: q.hiProg ? medProgress : -4,
                yAxis: q.hiCap ? medCapacity : 0,
                itemStyle: { color: `rgba(${q.rgb},${a})` },
              },
              {
                xAxis: q.hiProg ? 104 : medProgress,
                yAxis: q.hiCap ? 'max' : medCapacity,
              },
            ];
          }),
        },
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { type: 'dashed', color: chrome.fgTertiary, opacity: 0.55, width: 1 },
          label: { show: false },
          data: [{ xAxis: medProgress }, { yAxis: medCapacity }],
        },
      }],
      animationDuration: 600,
    };
  }, [shown, medProgress, medCapacity, chrome, statusColors, quadFilter]);

  /* ── Interactions ────────────────────────────────────────────────────── */
  const onChartEvents = {
    mouseover: (e: any) => {
      if (!e?.data?.[4] || pinned) return;
      const box = plotRef.current?.getBoundingClientRect();
      const ev = e.event?.event;
      if (!box || !ev) return;
      setHover({ x: ev.clientX - box.left, y: ev.clientY - box.top, p: e.data[4] });
    },
    mouseout: () => { if (!pinned) setHover(null); },
    click: (e: any) => {
      if (!e?.data?.[4]) return;
      const box = plotRef.current?.getBoundingClientRect();
      const ev = e.event?.event;
      if (box && ev) setHover({ x: ev.clientX - box.left, y: ev.clientY - box.top, p: e.data[4] });
      setPinned(e.data[4]);
    },
  };

  const addCompare = (p: ExecProject) => {
    setCompare((c) => (c.some((x) => x.name === p.name) ? c : [...c, p].slice(-4)));
    setPinned(null);
    setHover(null);
  };

  const openTrend = (p: ExecProject) => {
    setTrendProject(p.name);
    setView('trend');
    setPinned(null);
    setHover(null);
  };

  /* Captions sit above the plot, not on it. Floating them in the corners put
     them straight on top of the marks in exactly the quadrants that matter
     most, and no amount of padding fixes that when the data reaches a corner. */
  const inQuad = (hiCap: boolean, hiProg: boolean) =>
    byStatus.filter((p) =>
      (p.capacityMW >= medCapacity) === hiCap && (p.progress >= medProgress) === hiProg
    ).length;

  /* Same chip language as the construction stages: colour, label, count —
     and clicking one narrows the plot to that quadrant. */
  const quadrants = QUADS.map((q) => ({
    ...q,
    icon: QUAD_ICON[q.key],
    count: inQuad(q.hiCap, q.hiProg),
  }));

  return (
    <div className={cx(
      'bento-card flex w-full min-h-0 flex-1 flex-col overflow-hidden rounded-xl p-0',
      expanded && 'fixed inset-3 z-[120] shadow-2xl'
    )}>
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 border-b border-border-subtle px-4 py-3">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-blue/10 text-brand-blue">
            <BarChart3 className="h-4.5 w-4.5" strokeWidth={1.8} />
          </span>
          <div className="min-w-0">
            <h3 className="text-[15px] font-bold leading-tight text-fg-primary">Progress vs Capacity</h3>
            <p className="text-[11px] font-semibold text-brand-purple">Project Execution Queue</p>
            <p className="mt-1 text-[11px] leading-snug text-fg-tertiary">
              Each bubble is a project. Quadrants split at the portfolio median, so scale and pace are read together.
            </p>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          {/* Status filter */}
          <div className="relative">
            <button
              onClick={() => setFilterOpen((o) => !o)}
              className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-[12px] font-semibold text-fg-secondary transition-colors hover:border-brand-blue/40"
            >
              {filter === 'all' ? 'All Projects' : filter}
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
            {filterOpen && (
              <div className="surface-raised absolute right-0 top-full z-30 mt-1 w-44 overflow-hidden py-1">
                {(['all', 'On Track', 'Near Completion', 'Delayed'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => { setFilter(f); setFilterOpen(false); }}
                    className={cx(
                      'block w-full px-3 py-1.5 text-left text-[12px] transition-colors hover:bg-brand-blue/10',
                      filter === f ? 'font-bold text-brand-blue' : 'text-fg-secondary'
                    )}
                  >
                    {f === 'all' ? 'All Projects' : f}
                    <span className="ml-1.5 text-[10px] text-fg-tertiary">
                      {f === 'all' ? plottable.length : plottable.filter((p) => p.status === f).length}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* View toggle */}
          <div className="flex overflow-hidden rounded-lg border border-border">
            {([
              ['bubble', 'Portfolio'],
              ['trend', 'Trend'],
            ] as const).map(([v, label]) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={cx(
                  'px-3 py-1.5 text-[12px] font-semibold transition-colors',
                  view === v
                    ? 'bg-gradient-to-r from-brand-blue to-brand-purple text-white'
                    : 'bg-card text-fg-secondary hover:bg-brand-blue/10'
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <button
            onClick={() => setExpanded((e) => !e)}
            className="grid h-8 w-8 place-items-center rounded-lg border border-border text-fg-tertiary transition-colors hover:text-fg-primary"
            title={expanded ? 'Exit full screen' : 'Full screen'}
          >
            {expanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* ── Sub-bar ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-3">
        {view === 'bubble' ? (
          <>
            <div className="flex flex-wrap items-center gap-4">
              <Chip tone={statusColors.healthy} label="On Track (< 90%)" />
              <Chip tone={statusColors.done} label="Near Completion (≥ 90%)" />
              <Chip tone={statusColors.critical} label="Delayed" />
            </div>
            <span className="flex items-center gap-2 text-[11px] font-medium text-fg-tertiary">
              {shown.length} of {all.length} projects · split at portfolio median
              {noCapacity.length > 0 && (
                <span
                  className="cursor-help border-b border-dotted border-fg-tertiary"
                  title={`Not plotted — no capacity recorded:\n${noCapacity.map((p) => p.name).join('\n')}`}
                >
                  · {noCapacity.length} without a capacity figure
                </span>
              )}
              {quadFilter && (
                <button onClick={() => setQuadFilter(null)} className="font-semibold text-brand-blue hover:underline">
                  clear quadrant
                </button>
              )}
            </span>
          </>
        ) : (
          <div className="relative">
            <button
              onClick={() => setTrendOpen((o) => !o)}
              className="flex max-w-[420px] items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-[12px] font-semibold text-fg-secondary transition-colors hover:border-brand-blue/40"
            >
              <span className="truncate">{selected?.name || 'Select a project'}</span>
              <ChevronDown className="h-3.5 w-3.5 shrink-0" />
            </button>
            {trendOpen && (
              <div className="surface-raised absolute left-0 top-full z-30 mt-1 max-h-64 w-[420px] overflow-y-auto py-1">
                {all.map((p, i) => (
                  <button
                    key={`${p.name}-${i}`}
                    onClick={() => { setTrendProject(p.name); setTrendOpen(false); }}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-fg-secondary transition-colors hover:bg-brand-blue/10"
                  >
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: toneFor(p.status) }} />
                    <span className="truncate">{p.name}</span>
                    <span className="ml-auto shrink-0 text-[10px] text-fg-tertiary">{p.progress.toFixed(0)}%</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Plot ── */}
      <div ref={plotRef} className="relative min-h-[320px] w-full flex-1 px-2 pb-2 pt-1">
        {view === 'bubble' ? (
          <>
            <ReactECharts
              ref={chartRef}
              theme={themeName}
              option={bubbleOption}
              onEvents={onChartEvents}
              notMerge
              style={{ height: '100%', width: '100%' }}
            />

            {/* Quadrant captions, one per corner of the plot area. Inset to the
                grid margins so they sit inside the axes, translucent so a mark
                behind one still reads. */}
            <div
              className="pointer-events-none absolute inset-0"
              style={{ paddingLeft: 92, paddingRight: 48, paddingTop: 8, paddingBottom: 56 }}
            >
              <div className="relative h-full w-full">
                {quadrants.map((q) => {
                  const on = quadFilter === q.key;
                  return (
                    <button
                      key={q.key}
                      onClick={() => setQuadFilter(on ? null : q.key)}
                      title={on ? 'Show the whole portfolio' : `Show only ${q.note.toLowerCase()}`}
                      className={cx(
                        'pointer-events-auto absolute flex items-center gap-1.5 rounded-lg border px-2 py-1',
                        'backdrop-blur-[2px] transition-all hover:brightness-[0.97]',
                        q.cls, q.pos,
                        on ? 'ring-2 ring-brand-blue/45' : '',
                        quadFilter && !on ? 'opacity-45' : ''
                      )}
                    >
                      <q.icon className="h-3.5 w-3.5 shrink-0" strokeWidth={2} />
                      <span className="text-left text-[10px] font-bold leading-tight">
                        {q.title}
                        <span className="block font-medium opacity-75">{q.note}</span>
                      </span>
                      <span className="ml-1 text-[13px] font-bold tabular-nums">{q.count}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Hover / pinned card with its own actions */}
            {hover && (
              <div
                className="surface-raised absolute z-20 w-[268px] p-3"
                style={{
                  left: Math.min(Math.max(hover.x - 134, 8), (plotRef.current?.clientWidth || 600) - 276),
                  top: Math.max(hover.y - 190, 8),
                }}
                onMouseLeave={() => { if (!pinned) setHover(null); }}
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <span className="text-[12.5px] font-bold leading-tight text-fg-primary">{hover.p.name}</span>
                  {pinned && (
                    <button onClick={() => { setPinned(null); setHover(null); }} className="text-fg-tertiary hover:text-fg-primary">
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
                <dl className="space-y-1 text-[11.5px]">
                  {[
                    ['Progress', `${hover.p.progress.toFixed(1)}%`],
                    ['Capacity', `${hover.p.capacityMW.toFixed(1)} MW`],
                    ['COD', hover.p.codLabel],
                  ].map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-3">
                      <dt className="text-fg-tertiary">{k}</dt>
                      <dd className="font-semibold text-fg-primary">{v}</dd>
                    </div>
                  ))}
                  <div className="flex justify-between gap-3">
                    <dt className="text-fg-tertiary">Status</dt>
                    <dd className="font-semibold" style={{ color: toneFor(hover.p.status) }}>
                      {hover.p.status}
                      {hover.p.delayDays > 0 && ` (${hover.p.delayDays}d late)`}
                    </dd>
                  </div>
                </dl>
                <div className="mt-2.5 flex items-center gap-3 border-t border-border-subtle pt-2">
                  <button
                    onClick={() => (onOpenProject ? onOpenProject(hover.p.raw) : openTrend(hover.p))}
                    className="flex items-center gap-1.5 text-[11px] font-semibold text-brand-blue hover:underline"
                  >
                    <Search className="h-3 w-3" /> View details
                  </button>
                  <button
                    onClick={() => addCompare(hover.p)}
                    className="flex items-center gap-1.5 text-[11px] font-semibold text-brand-purple hover:underline"
                  >
                    <BarChart3 className="h-3 w-3" /> Add to compare
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <ConstructionUnits
            projectObjectId={selected?.p6ObjectId ?? null}
            projectId={selected?.p6ProjectId ?? null}
            projectName={selected?.name}
          />
        )}
      </div>

      {/* ── Compare tray ── */}
      {view === 'bubble' && compare.length > 0 && (
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-border-subtle px-4 py-2.5">
          <span className="section-label">Comparing</span>
          {compare.map((c) => (
            <span
              key={c.name}
              className="flex items-center gap-1.5 rounded-full border border-border bg-card py-1 pl-2 pr-1 text-[11px] font-medium text-fg-secondary"
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: toneFor(c.status) }} />
              <span className="max-w-[180px] truncate">{c.name}</span>
              <span className="text-fg-tertiary">{c.progress.toFixed(0)}%</span>
              <button
                onClick={() => setCompare((x) => x.filter((y) => y.name !== c.name))}
                className="grid h-4 w-4 place-items-center rounded-full text-fg-tertiary hover:bg-brand-blue/10 hover:text-fg-primary"
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
          {compare.length > 1 && (
            <span className="ml-1 text-[11px] text-fg-tertiary">
              spread {Math.min(...compare.map((c) => c.progress)).toFixed(0)}–
              {Math.max(...compare.map((c) => c.progress)).toFixed(0)}% ·{' '}
              {compare.reduce((a, c) => a + c.capacityMW, 0).toFixed(0)} MW
            </span>
          )}
          <button onClick={() => setCompare([])} className="ml-auto text-[11px] font-semibold text-fg-tertiary hover:text-fg-primary">
            Clear
          </button>
        </div>
      )}

    </div>
  );
}
