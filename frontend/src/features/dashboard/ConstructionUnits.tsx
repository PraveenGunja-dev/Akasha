import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { CheckCircle2, CircleDot, Circle, Zap, AlertTriangle, Sparkles } from 'lucide-react';
import { cx } from '../../components/ui/primitives/cx';
import { useChartTheme } from '../../lib/chartTheme';

/* ═══════════════════════════════════════════════════════════════════════════
   CONSTRUCTION UNITS — block-wise (solar) / WTG-wise (wind)

   Project-level percent-complete answers "how far along", which is the wrong
   question once a plant energises in stages: revenue starts per BLOCK, at its
   COD. So this reads the P6 construction WBS the way the plant is actually
   built and handed over — one point per block or turbine.

   Three series on one frame:

     area    construction progress   left axis, % of activities complete
     line    Trial Run               right axis, date
     line    COD                     right axis, date

   Two axes because they answer different questions in different units. A COD
   line climbing away while the progress area stays flat is a block whose
   dates are drifting with no work behind them — the pattern worth catching.

   Progress is COMPLETED ACTIVITIES / TOTAL ACTIVITIES for the block, by P6
   status — the figure site reports against. `weighted` (the mean of
   percent_complete) is carried alongside and always reads higher, because it
   credits part-finished work; showing it as "progress" overstates the block.

   Every figure comes from p6_activity. COD and SCOD are the same milestone.
   Trial Run is matched on "Trial Run"; "Trial Operation" is a separate
   activity and is deliberately excluded.
   ═══════════════════════════════════════════════════════════════════════════ */

type Milestone = { activity: string; done: boolean; actual: string | null; forecast: string | null } | null;

interface Unit {
  kind: string;
  number: number;
  label: string;
  total: number;
  completed: number;
  in_progress: number;
  not_started: number;
  progress: number;
  weighted: number;
  cod: Milestone;
  trial_run: Milestone;
}

interface Payload {
  unit_type: string | null;
  unit_count: number;
  unassigned: number;
  units: Unit[];
}

/* Four stages, four colours — deliberately NOT the portfolio view's three,
   since these encode handover stage rather than schedule health. */
const STAGE = {
  cod: {
    label: 'At COD', icon: CheckCircle2, dot: 'bg-emerald-500',
    card: 'border-emerald-500/35 bg-emerald-500/[0.07]',
    text: 'text-emerald-600 dark:text-emerald-400', bar: 'bg-emerald-500',
  },
  trial: {
    label: 'Trial Run done', icon: Zap, dot: 'bg-violet-500',
    card: 'border-violet-500/35 bg-violet-500/[0.07]',
    text: 'text-violet-600 dark:text-violet-400', bar: 'bg-violet-500',
  },
  building: {
    label: 'Under construction', icon: CircleDot, dot: 'bg-amber-500',
    card: 'border-amber-500/35 bg-amber-500/[0.07]',
    text: 'text-amber-600 dark:text-amber-400', bar: 'bg-amber-500',
  },
  queued: {
    label: 'Not started', icon: Circle, dot: 'bg-slate-400',
    card: 'border-border bg-muted/30',
    text: 'text-fg-tertiary', bar: 'bg-slate-400',
  },
} as const;

type StageKey = keyof typeof STAGE;

const stageOf = (u: Unit): StageKey => {
  if (u.cod?.done) return 'cod';
  if (u.trial_run?.done) return 'trial';
  if (u.completed > 0 || u.in_progress > 0) return 'building';
  return 'queued';
};

const fmt = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: '2-digit' }) : '—';
const fmtMonth = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', year: 'numeric' }) : '—';

const PROGRESS = '#38bdf8';
const TRIAL = '#8b5cf6';
const COD = '#10b981';

export default function ConstructionUnits({
  projectObjectId,
  projectId,
  projectName,
}: {
  projectObjectId: number | null;
  projectId?: string | null;
  projectName?: string;
}) {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stageFilter, setStageFilter] = useState<StageKey | 'all'>('all');
  const [showGrid, setShowGrid] = useState(false);
  const { themeName, chrome } = useChartTheme();
  const plotRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    if (!projectObjectId && !projectId) { setData(null); return; }
    let live = true;
    setLoading(true);
    setError(null);
    const qs = projectObjectId
      ? `project_object_id=${projectObjectId}`
      : `project_id=${encodeURIComponent(projectId as string)}`;
    fetch(`/akasha/api/p6/construction-units?${qs}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { if (live) { setData(d); setLoading(false); } })
      .catch((e) => { if (live) { setError(String(e.message || e)); setLoading(false); } });
    return () => { live = false; };
  }, [projectObjectId, projectId]);

  /* The canvas measures once at mount, before the flex box has settled, so it
     needs re-measuring whenever its container actually changes. */
  useEffect(() => {
    const el = plotRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    let frame = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        try { chartRef.current?.getEchartsInstance?.().resize(); } catch { /* not mounted */ }
      });
    });
    ro.observe(el);
    return () => { cancelAnimationFrame(frame); ro.disconnect(); };
  }, []);

  const units = data?.units || [];
  const nounShort = (data?.unit_type || 'Block') === 'WTG' ? 'WTGs' : 'Blocks';

  const tally = useMemo(() => {
    const t: Record<StageKey, number> = { cod: 0, trial: 0, building: 0, queued: 0 };
    units.forEach((u) => { t[stageOf(u)] += 1; });
    return t;
  }, [units]);

  const shown = useMemo(
    () => (stageFilter === 'all' ? units : units.filter((u) => stageOf(u) === stageFilter)),
    [units, stageFilter]
  );

  const brief = useMemo(() => {
    if (!units.length) return null;
    const noun = (data?.unit_type || 'Block') === 'WTG' ? 'turbines' : 'blocks';
    const atCod = tally.cod;
    const pctCod = (atCod / units.length) * 100;

    const pending = units.filter((u) => !u.cod?.done && u.cod?.forecast);
    const dates = pending.map((u) => new Date(u.cod!.forecast!).getTime()).filter((n) => !isNaN(n));
    const nextDate = dates.length ? new Date(Math.min(...dates)) : null;
    const lastDate = dates.length ? new Date(Math.max(...dates)) : null;
    const nextUnits = nextDate
      ? pending.filter((u) => {
          const d = new Date(u.cod!.forecast!);
          return d.getMonth() === nextDate.getMonth() && d.getFullYear() === nextDate.getFullYear();
        }).length
      : 0;

    const stalled = tally.queued;
    const avg = units.reduce((a, u) => a + u.progress, 0) / units.length;
    return { noun, atCod, pctCod, nextDate, lastDate, nextUnits, stalled, avg, pendingCount: pending.length };
  }, [units, tally, data]);

  /* ── The chart ── */
  const chartOption = useMemo(() => {
    if (!units.length) return null;

    const labels = units.map((u) => u.label);
    const progress = units.map((u) => Number(u.progress.toFixed(1)));

    const dateOf = (m: Milestone) => {
      const iso = m?.done ? (m.actual || m.forecast) : m?.forecast;
      if (!iso) return null;
      const t = new Date(iso).getTime();
      return isNaN(t) ? null : t;
    };
    const cod = units.map((u) => dateOf(u.cod));
    const trial = units.map((u) => dateOf(u.trial_run));
    const codDone = units.map((u) => !!u.cod?.done);
    const trialDone = units.map((u) => !!u.trial_run?.done);
    const hasCod = cod.some((v) => v !== null);
    const hasTrial = trial.some((v) => v !== null);

    /* Point labels are the reference's look, but they only stay legible while
       the units are few; past that they collide into a grey smear. */
    const dense = units.length > 18;

    /* A project's blocks often hand over within one month, so a month/year
       label repeats down the whole axis ("May 27" five times). Fall back to
       day + month whenever the spread is short. */
    const stamps = [...cod, ...trial].filter((v): v is number => v !== null);
    const spanDays = stamps.length > 1
      ? (Math.max(...stamps) - Math.min(...stamps)) / 86400000
      : 0;

    const grad = (top: string, bottom: string) => ({
      type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
      colorStops: [{ offset: 0, color: top }, { offset: 1, color: bottom }],
    });

    return {
      grid: { left: 40, right: 76, bottom: 58, top: 36, containLabel: true },
      legend: { top: 0, itemHeight: 8, itemWidth: 16, textStyle: { fontSize: 11, color: chrome.fgSecondary } },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', label: { show: false } },
        formatter: (ps: any[]) => {
          if (!ps?.length) return '';
          const u = units[ps[0].dataIndex];
          if (!u) return '';
          const row = (c: string, k: string, v: string) =>
            `<div style="display:flex;gap:12px;justify-content:space-between">
               <span style="color:${c}">&#9679; ${k}</span><b>${v}</b></div>`;
          return `<b>${u.label}</b>
            ${row(PROGRESS, 'Progress', `${u.completed}/${u.total} activities · ${u.progress.toFixed(1)}%`)}
            ${row(TRIAL, 'Trial Run', u.trial_run ? (u.trial_run.done ? fmt(u.trial_run.actual || u.trial_run.forecast) + ' ✓' : fmt(u.trial_run.forecast)) : '—')}
            ${row(COD, 'COD', u.cod ? (u.cod.done ? fmt(u.cod.actual || u.cod.forecast) + ' ✓' : fmt(u.cod.forecast)) : '—')}
            <div style="margin-top:4px;font-size:10px;opacity:.7">${u.completed} done · ${u.in_progress} running · ${u.not_started} to start · ${u.weighted.toFixed(0)}% incl. part-done</div>`;
        },
      },
      xAxis: {
        type: 'category',
        data: labels,
        axisLabel: { rotate: 45, fontSize: 9, interval: dense ? 'auto' : 0, color: chrome.fgTertiary, margin: 10 },
        axisTick: { alignWithLabel: true },
      },
      yAxis: [
        {
          type: 'value', min: 0, max: 100,
          name: 'Activities complete (%)', nameLocation: 'middle', nameRotate: 90, nameGap: 40,
          nameTextStyle: { fontSize: 10, color: chrome.fgTertiary },
          axisLabel: { formatter: '{value}%', fontSize: 10 },
          splitLine: { lineStyle: { type: 'dashed', opacity: 0.35 } },
        },
        {
          type: 'time',
          name: 'Milestone date', nameLocation: 'middle', nameRotate: 90, nameGap: 62,
          nameTextStyle: { fontSize: 10, color: chrome.fgTertiary },
          /* Month + 2-digit year, thinned out — the full label on every tick
             was what made the right edge read as a wall of dates. */
          axisLabel: {
            fontSize: 9.5, margin: 10, hideOverlap: true,
            formatter: (v: number) => new Date(v).toLocaleDateString(undefined,
              spanDays < 400
                ? { day: '2-digit', month: 'short' }
                : { month: 'short', year: '2-digit' }),
          },
          splitNumber: 4,
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: 'Activities complete', type: 'line', smooth: true, yAxisIndex: 0,
          data: progress,
          symbol: 'circle', symbolSize: dense ? 4 : 7,
          lineStyle: { width: 2.5, color: PROGRESS },
          itemStyle: { color: PROGRESS, borderColor: chrome.surface1, borderWidth: 1.5 },
          areaStyle: { color: grad('rgba(56,189,248,0.38)', 'rgba(56,189,248,0.02)') },
          label: { show: !dense, position: 'top', fontSize: 9, color: chrome.fgSecondary, formatter: (d: any) => `${d.value}%` },
          z: 2,
        },
        ...(hasTrial ? [{
          name: 'Trial Run', type: 'line', smooth: true, yAxisIndex: 1,
          data: trial, connectNulls: true,
          symbol: 'circle', symbolSize: dense ? 5 : 8,
          lineStyle: { width: 2, color: TRIAL, type: 'dashed' },
          itemStyle: {
            color: (pr: any) => (trialDone[pr.dataIndex] ? TRIAL : chrome.surface1),
            borderColor: TRIAL, borderWidth: 2,
          },
          z: 3,
        }] : []),
        ...(hasCod ? [{
          name: 'COD', type: 'line', smooth: true, yAxisIndex: 1,
          data: cod, connectNulls: true,
          symbol: 'circle', symbolSize: dense ? 5 : 9,
          lineStyle: { width: 3, color: COD },
          itemStyle: {
            color: (pr: any) => (codDone[pr.dataIndex] ? COD : chrome.surface1),
            borderColor: COD, borderWidth: 2,
          },
          z: 4,
        }] : []),
      ],
      animationDuration: 700,
    };
  }, [units, chrome]);

  /* ── States ── */
  if (!projectObjectId && !projectId) {
    return <div className="flex h-full items-center justify-center p-6 text-[12px] text-fg-tertiary">
      Select a project to see its blocks.
    </div>;
  }
  if (loading) {
    return <div className="flex h-full items-center justify-center p-6 text-[12px] text-fg-tertiary">
      Reading the construction WBS…
    </div>;
  }
  if (error) {
    return <div className="flex h-full items-center justify-center p-6 text-center text-[12px] text-status-critical-fg">
      Could not load construction units — {error}
    </div>;
  }
  if (!units.length) {
    return <div className="flex h-full items-center justify-center px-8 text-center text-[12px] leading-relaxed text-fg-tertiary">
      No block or WTG activities found for {projectName || 'this project'}. Its P6 activities carry no
      <code className="mx-1 rounded bg-muted px-1">Block-NN</code> or
      <code className="mx-1 rounded bg-muted px-1">WTG-NN</code> prefix, so there is nothing to roll up per unit.
    </div>;
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Stage tally — doubles as the filter for the detail grid */}
      <div className="grid shrink-0 grid-cols-2 gap-2 px-3 pt-2 lg:grid-cols-4">
        {(Object.keys(STAGE) as StageKey[]).map((k) => {
          const st = STAGE[k];
          const on = stageFilter === k;
          return (
            <button
              key={k}
              onClick={() => { setStageFilter(on ? 'all' : k); if (!on) setShowGrid(true); }}
              className={cx(
                'flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left transition-all',
                st.card,
                on ? 'ring-2 ring-brand-blue/40' : 'hover:brightness-[0.98]'
              )}
            >
              <span className={cx('h-2.5 w-2.5 shrink-0 rounded-full', st.dot)} />
              <span className={cx('min-w-0 flex-1 truncate text-[10px] font-bold uppercase tracking-wider', st.text)}>
                {st.label}
              </span>
              <span className={cx('text-[15px] font-bold tabular-nums', st.text)}>{tally[k]}</span>
            </button>
          );
        })}
      </div>

      {/* The chart is the view */}
      <div ref={plotRef} className="relative min-h-[260px] flex-1 px-2 pt-1">
        {chartOption ? (
          <ReactECharts ref={chartRef} theme={themeName} option={chartOption} notMerge style={{ height: '100%', width: '100%' }} />
        ) : (
          <div className="flex h-full items-center justify-center px-8 text-center text-[12px] text-fg-tertiary">
            No milestone dates for these {nounShort.toLowerCase()}, so the handover curve cannot be drawn.
          </div>
        )}
      </div>

      <div className="flex shrink-0 items-center justify-between gap-2 px-3 pb-1">
        <span className="text-[10px] font-medium text-fg-tertiary">
          Filled marker = achieved · hollow = forecast · {units.length} {nounShort.toLowerCase()}
        </span>
        <button
          onClick={() => setShowGrid((g) => !g)}
          className="text-[11px] font-semibold text-brand-blue hover:underline"
        >
          {showGrid ? 'Hide' : 'Show'} {nounShort.toLowerCase()} detail
        </button>
      </div>

      {/* Per-unit cards, on demand — the curve raises the question, these
          answer "which one". */}
      {showGrid && (
        <div className="custom-scrollbar max-h-[38%] shrink-0 overflow-y-auto px-3 pb-2">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {shown.map((u) => {
              const st = STAGE[stageOf(u)];
              const codDone = !!u.cod?.done;
              return (
                <div
                  key={u.label}
                  className={cx('rounded-lg border p-2.5 transition-colors', st.card)}
                  title={`${u.completed} complete · ${u.in_progress} running · ${u.not_started} not started of ${u.total} activities`}
                >
                  <div className="mb-1.5 flex items-center justify-between gap-1">
                    <span className="truncate text-[11.5px] font-bold text-fg-primary">{u.label}</span>
                    <st.icon className={cx('h-3.5 w-3.5 shrink-0', st.text)} strokeWidth={2} />
                  </div>
                  <div className="mb-1 flex items-baseline gap-1">
                    <span className="text-[17px] font-bold leading-none tabular-nums text-fg-primary">
                      {u.progress.toFixed(0)}
                    </span>
                    <span className="text-[10px] font-medium text-fg-tertiary">%</span>
                  </div>
                  <div className="mb-2 h-1 w-full overflow-hidden rounded-full bg-fg-tertiary/15">
                    <div className={cx('h-full rounded-full', st.bar)} style={{ width: `${Math.min(100, u.progress)}%` }} />
                  </div>
                  <dl className="space-y-0.5 text-[9.5px] leading-tight">
                    <div className="flex justify-between gap-1">
                      <dt className="text-fg-tertiary">Trial Run</dt>
                      <dd className={cx('font-semibold', u.trial_run?.done ? STAGE.trial.text : 'text-fg-secondary')}>
                        {u.trial_run ? fmt(u.trial_run.done ? (u.trial_run.actual || u.trial_run.forecast) : u.trial_run.forecast) : '—'}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-1">
                      <dt className="text-fg-tertiary">COD</dt>
                      <dd className={cx('font-semibold', codDone ? STAGE.cod.text : 'text-fg-secondary')}>
                        {u.cod ? fmt(codDone ? (u.cod.actual || u.cod.forecast) : u.cod.forecast) : '—'}
                      </dd>
                    </div>
                  </dl>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* CEO read-out */}
      {brief && (
        <div className="shrink-0 border-t border-border-subtle p-3">
          <div className="flex items-start gap-2.5 rounded-xl border border-border bg-card p-3">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-purple/10 text-brand-purple">
              <Sparkles className="h-3.5 w-3.5" strokeWidth={1.8} />
            </span>
            <div className="min-w-0">
              <p className="text-[11px] font-bold uppercase tracking-wider text-brand-purple">Handover position</p>
              <p className="mt-0.5 text-[12px] leading-relaxed text-fg-secondary">
                <strong>{brief.atCod} of {units.length} {brief.noun}</strong> have reached COD
                — <strong>{brief.pctCod.toFixed(0)}%</strong> of the plant is through the gate and earning.
                {brief.pendingCount > 0 && brief.nextDate && (
                  <> The next <strong>{brief.nextUnits}</strong> {brief.nextUnits === 1 ? 'is' : 'are'} scheduled
                    for <strong>{fmtMonth(brief.nextDate.toISOString())}</strong>, and the remaining {brief.pendingCount} run
                    through to <strong>{fmtMonth(brief.lastDate!.toISOString())}</strong>.</>
                )}
                {brief.stalled > 0 && (
                  <> <strong className="text-status-critical-fg">{brief.stalled} {brief.noun} have not started</strong> —
                    no activity has moved, so their COD dates are the first to question.</>
                )}
                {brief.stalled === 0 && brief.atCod < units.length && <> Every remaining unit has work under way.</>}
              </p>
              <p className="mt-1.5 flex items-center gap-1.5 text-[10px] leading-relaxed text-fg-tertiary">
                <AlertTriangle className="h-3 w-3 shrink-0" />
                Progress is completed activities over total activities per {brief.noun.slice(0, -1)}, by P6 status —
                averaging {brief.avg.toFixed(1)}% across {units.length} {brief.noun}. The tooltip also shows the
                part-done figure, which credits activities in progress and always reads higher. Dates without an actual are the P6 baseline — the forecast the schedule still
                carries, not a projection of ours.
                {data?.unassigned ? ` ${data.unassigned} plant-level activities sit outside any ${brief.noun.slice(0, -1)} and are excluded.` : ''}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
