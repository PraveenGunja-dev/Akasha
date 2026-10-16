/* ── Block plan: module ordering, block by block ───────────────────────────
   Branch feature/block-level-ordering. Reads /module-deliveries/block-plan
   (services/block_ordering.py) and explains it for a reader who is not a
   planner: what each step does, in plain words, with the live figure beside
   it; an AI summary written only from the figures on the page; and the
   project → block detail behind every number. */
import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import {
  Layers, Hammer, Gauge, Warehouse, Clock, Scale, Sparkles, RefreshCcw, ChevronRight,
  AlertTriangle, BookOpen, Package, Truck, CalendarX2,
} from 'lucide-react';
import { Card, CardHeader, KPITile, InfoTip, Loader, cx } from '../../components/ui/primitives';
import { useChartTheme } from '../../lib/chartTheme';

const API = import.meta.env.VITE_API_BASE || '';

// ── Shapes returned by the backend ───────────────────────────────────────────
interface Block {
  block: string; mwp: number; installed_mwp: number; remaining_mwp: number;
  start: string | null; finish: string | null; window?: [string, string];
  basis: string; flags: string[]; slip_days?: number; need_by_month: Record<string, number>;
}
interface Verify {
  block_mwp: number; capacity_mwp: number; sap_ordered_mwp: number; installed_mwp: number;
  pipeline_mwp: number; to_order_by_blocks_mwp: number; to_order_by_sap_mwp: number; agree: boolean;
}
interface PlanProject {
  id: number; project_name: string; cluster?: string; type: string; priority?: string;
  method: 'block' | 'none'; reason?: string;
  lead_days?: number; blocks_total?: number; blocks_open?: number; block_mwp?: number;
  installed_mwp?: number; pipeline_mwp?: number; pace_mwp_per_day?: number; pace_basis?: string;
  new_order_mwp?: number | null; late_need_mwp?: number; quota_delayed_mwp?: number;
  max_quota_delay_months?: number; blocks_after_scod?: number; blocks_after_lta?: number;
  blocks_held_by_mms?: number; scod?: string | null; lta?: string | null; origin_known?: boolean;
  orders_by_month?: Record<string, number>; verify?: Verify; blocks?: Block[];
  ftc_method_balance_mwp?: number | null;
}
interface Plan {
  as_of: string; months: string[];
  assumptions: { site_buffer_days: number; portfolio_pace_mwp_per_day: number; portfolio_mms_to_module_lag_days: number; lead_days: Record<string, number> };
  quota_by_origin: Record<string, { cap_mwac: number; known_origin: boolean; used_mwac_by_month: Record<string, number> }>;
  projects: PlanProject[];
}
interface Explanation { text: string; ai: boolean; provider: string }

// ── Plain words for codes ─────────────────────────────────────────────────────
const ORIGIN_NAME: Record<string, string> = {
  China: 'China', SEA: 'South-East Asia', ALMM: 'Approved Indian makers (ALMM)',
  DCR: 'Indian cells & modules (DCR)', ALCM: 'ALCM', Unknown: 'Origin not set',
};
const GLOSSARY: [string, string][] = [
  ['Block', 'One section of a solar plant, about 17 MWp, with its own installation dates in P6.'],
  ['MWp', 'Module quantity in megawatts (peak). The plant’s grid size is in MWac; MWp is about 1.35–1.4× that.'],
  ['MMS', 'The steel structure the modules are fixed on. Modules can only go on once it is up.'],
  ['Lead time', 'Days a supplier needs from order to delivery: 136 for China / South-East Asia, 98 for Indian makers.'],
  ['Supplier limit', 'The most each supplier origin can deliver in a month, in MWac.'],
  ['SCOD', 'The contract date by which the plant must be running.'],
  ['LTA', 'The date the grid connection is ready to export power.'],
];

const n0 = (v?: number | null) => (v === null || v === undefined ? '—' : Math.round(v).toLocaleString('en-IN'));
const mon = (ym: string) => {
  const [y, m] = ym.split('-').map(Number);
  return new Date(y, m - 1, 1).toLocaleString('en-GB', { month: 'short', year: '2-digit' }).replace(' ', '-');
};
const dmy = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' }) : '—');

/* A block's state in words, for the block table. */
function blockStatus(b: Block): { text: string; tone: 'healthy' | 'watch' | 'risk' | 'neutral' } {
  if (b.remaining_mwp <= 0) return { text: 'Installed', tone: 'healthy' };
  if (b.flags.includes('overdue')) return { text: 'Past its P6 finish — modules needed now', tone: 'risk' };
  const held = b.flags.find((f) => f.startsWith('held by MMS'));
  if (held) return { text: `Waiting for the structure (MMS) — starts later ${held.match(/\(\+(\d+) d\)/)?.[1] ?? ''} d`.trim(), tone: 'watch' };
  if (b.basis.includes('pace')) return { text: 'Plan is faster than this site has managed — slowed to real speed', tone: 'watch' };
  if (b.installed_mwp > 0) return { text: 'Installing now', tone: 'neutral' };
  return { text: 'Planned in P6', tone: 'neutral' };
}
const TONE_TEXT = { healthy: 'text-status-healthy-fg', watch: 'text-status-watch-fg', risk: 'text-status-risk-fg', neutral: 'text-fg-secondary' };

// ── AI text: "- " bullets → list ──────────────────────────────────────────────
const Bullets: React.FC<{ text: string }> = ({ text }) => (
  <ul className="space-y-1.5">
    {text.split('\n').map((l) => l.replace(/^\s*[-*•]\s*/, '').replace(/\*\*/g, '').trim()).filter(Boolean).map((l, i) => (
      <li key={i} className="flex gap-2.5 text-[13.5px] leading-relaxed text-fg-primary">
        <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-status-ai" />{l}
      </li>
    ))}
  </ul>
);

const AiNote: React.FC<{ ex: Explanation | null }> = ({ ex }) => (
  <p className="mt-3 text-[11px] text-fg-tertiary">
    {ex?.ai ? 'Written by AI from the figures on this page only. Check any decision against the tables below.'
      : 'Automatic summary from the figures on this page (AI was not reachable).'}
  </p>
);

function useExplain() {
  const [busy, setBusy] = useState<string | null>(null);
  const call = async (body: unknown, key: string): Promise<Explanation | null> => {
    setBusy(key);
    try {
      const r = await fetch(`${API}/akasha/api/module-deliveries/block-plan/explain`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      return r.ok ? await r.json() : null;
    } catch { return null; } finally { setBusy(null); }
  };
  return { busy, call };
}

export default function BlockPlanView() {
  const [searchParams] = useSearchParams();
  const portfolio = searchParams.get('portfolio');
  const phase = searchParams.get('phase') || 'ongoing';
  const { themeName, categorical } = useChartTheme();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<Explanation | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [projectEx, setProjectEx] = useState<Record<number, Explanation | null>>({});
  const [showWords, setShowWords] = useState(false);
  const { busy, call } = useExplain();

  // Plan, then the AI summary of it. A newer request wins over an older one.
  useEffect(() => {
    let live = true;
    setLoading(true); setError(null); setSummary(null);
    const q = new URLSearchParams({ phase });
    if (portfolio) q.set('portfolio', portfolio);
    fetch(`${API}/akasha/api/module-deliveries/block-plan?${q}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Block plan unavailable (${r.status})`))))
      .then(async (d: Plan) => {
        if (!live) return;
        setPlan(d);
        setLoading(false);
        const slim = { ...d, projects: d.projects.map(({ blocks: _b, ...rest }) => rest) };
        const ex = await call({ scope: 'portfolio', plan: slim }, 'portfolio');
        if (live) setSummary(ex);
      })
      .catch((e: Error) => { if (live) { setError(e.message); setLoading(false); } });
    return () => { live = false; };
  }, [portfolio, phase]);   // eslint-disable-line react-hooks/exhaustive-deps

  const blk = useMemo(() => (plan?.projects || []).filter((p) => p.method === 'block'), [plan]);
  const none = useMemo(() => (plan?.projects || []).filter((p) => p.method === 'none'), [plan]);
  const sum = (f: (p: PlanProject) => number | null | undefined) => blk.reduce((s, p) => s + (f(p) || 0), 0);
  const t = {
    blocks: sum((p) => p.blocks_total), open: sum((p) => p.blocks_open), held: sum((p) => p.blocks_held_by_mms),
    pipeline: sum((p) => p.pipeline_mwp), toOrder: sum((p) => p.new_order_mwp), late: sum((p) => p.late_need_mwp),
    delayed: sum((p) => p.quota_delayed_mwp), afterScod: sum((p) => p.blocks_after_scod), installed: sum((p) => p.installed_mwp),
  };
  const delayedProjects = blk.filter((p) => (p.quota_delayed_mwp || 0) > 0.5).length;

  // Orders per month, stacked by supplier origin.
  const chart = useMemo(() => {
    if (!plan) return {};
    const origins = Array.from(new Set(blk.map((p) => p.type)));
    const months = plan.months;
    return {
      grid: { left: 48, right: 16, top: 36, bottom: 28 },
      legend: { top: 0, itemWidth: 10, itemHeight: 10 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
        valueFormatter: (v: number) => `${Math.round(v).toLocaleString('en-IN')} MWp` },
      xAxis: { type: 'category', data: months.map(mon) },
      yAxis: { type: 'value', name: 'MWp', nameTextStyle: { align: 'right' } },
      series: origins.map((o, i) => ({
        name: ORIGIN_NAME[o] || o, type: 'bar', stack: 'orders', barMaxWidth: 34,
        itemStyle: { color: categorical[i % categorical.length] },
        data: months.map((m) => blk.filter((p) => p.type === o).reduce((s, p) => s + (p.orders_by_month?.[m] || 0), 0)),
      })),
    };
  }, [plan, blk, categorical]);

  if (loading) return <Loader size="md" className="py-24" label="Working out the block-by-block plan…" detail="Reading every block from P6 and the module stock from SAP." />;
  if (error || !plan) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-status-critical-border bg-status-critical-bg px-4 py-3 text-[13px] text-status-critical-fg">
        <AlertTriangle className="h-4 w-4" /> {error || 'Block plan unavailable'}
      </div>
    );
  }

  const leadText = Object.entries(plan.assumptions.lead_days).map(([k, v]) => `${k} ${v} d`).join(' · ');
  const steps = [
    { icon: Layers, title: 'Read the site plan', text: `Every block of every project, from the P6 schedule, with the modules each block needs.`,
      fig: `${n0(t.blocks)} blocks · ${n0(t.open)} still to fit modules` },
    { icon: Hammer, title: 'Wait for the structure', text: `Modules go on only after a block’s steel structure (MMS) is up, so a block still waiting for it needs modules later.`,
      fig: `${n0(t.held)} blocks waiting for their structure` },
    { icon: Gauge, title: 'Use the real speed', text: `Sites have fitted about ${plan.assumptions.portfolio_pace_mwp_per_day.toFixed(2)} MWp a day per block. A plan faster than that is slowed down to it.`,
      fig: 'Based on blocks already finished' },
    { icon: Warehouse, title: 'Count what we have', text: 'Modules on site, on the way, or ordered but not yet sent are used first. Only the rest is ordered.',
      fig: `${n0(t.pipeline)} MWp already covered` },
    { icon: Clock, title: 'Order in time', text: `Suppliers need ${leadText} to deliver. Each order is placed that early, plus ${plan.assumptions.site_buffer_days} days spare.`,
      fig: `${n0(t.late)} MWp is already late — order now` },
    { icon: Scale, title: 'Stay within supplier limits', text: 'Each supplier can only deliver so much a month. Urgent projects (P1, P2) go first, then the earliest need.',
      fig: `${n0(t.delayed)} MWp has to wait for space` },
  ];

  const issues: { title: string; detail: string; who: string }[] = [];
  const unknown = blk.filter((p) => !p.origin_known);
  if (unknown.length) issues.push({ title: `${unknown.length} projects have no supplier origin`, who: 'Master data',
    detail: `${unknown.map((p) => p.project_name).join(', ')}. Their limit is assumed; set China / SEA / ALMM / DCR in the project master.` });
  const mismatch = blk.filter((p) => p.verify && !p.verify.agree);
  if (mismatch.length) issues.push({ title: `${mismatch.length} projects where P6 and SAP disagree`, who: 'Planning + procurement',
    detail: mismatch.map((p) => `${p.project_name}: P6 says ${n0(p.verify?.to_order_by_blocks_mwp)} MWp to order, SAP says ${n0(p.verify?.to_order_by_sap_mwp)}`).join(' · ') });
  if (!blk.some((p) => (p.priority || 'standard') !== 'standard')) issues.push({ title: 'No project is marked P1 or P2', who: 'Planning',
    detail: 'Without priorities, scarce supplier space is shared by need date only. Mark the critical projects in the project master.' });
  if (none.length) issues.push({ title: `${none.length} projects have no block plan in P6`, who: 'Planning',
    detail: `${none.map((p) => p.project_name).join(', ')} — not planned here until P6 has block-level Module Installation activities.` });

  return (
    <div className="flex flex-col gap-5 pb-10">
      {/* Intro */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="max-w-3xl">
            <p className="section-label text-brand-blue">Module ordering · new method</p>
            <h2 className="mt-1 text-lg font-semibold text-fg-primary">Block-by-block ordering plan</h2>
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-fg-secondary">
              Instead of ordering a whole phase for its charging date, this plan orders modules for each block of the plant
              as that block is built. Orders become smaller, arrive closer to when the site needs them, and follow the real
              progress on site. It is being compared with the current schedule before it replaces it.
            </p>
          </div>
          <span className="text-[11px] text-fg-tertiary">As of {dmy(plan.as_of)} · {blk.length} projects</span>
        </div>
      </Card>

      {/* How it works */}
      <Card>
        <CardHeader icon={BookOpen} title="How this plan works" eyebrow="Six steps, each with today’s figure"
          right={<button onClick={() => setShowWords((v) => !v)} className="text-[12px] font-medium text-brand-blue hover:underline">
            {showWords ? 'Hide' : 'Words used on this page'}</button>} />
        {showWords && (
          <dl className="mt-3 grid gap-x-6 gap-y-2 rounded-lg border border-border-subtle bg-surface-sunken/50 p-4 sm:grid-cols-2">
            {GLOSSARY.map(([k, v]) => (
              <div key={k} className="text-[12.5px]"><dt className="inline font-semibold text-fg-primary">{k}: </dt><dd className="inline text-fg-secondary">{v}</dd></div>
            ))}
          </dl>
        )}
        <ol className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {steps.map((s, i) => (
            <li key={s.title} className="flex gap-3 rounded-xl border border-border-subtle p-4">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-blue/10 text-[13px] font-semibold text-brand-blue">{i + 1}</span>
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-[14px] font-semibold text-fg-primary"><s.icon className="h-4 w-4 text-fg-tertiary" />{s.title}</p>
                <p className="mt-1 text-[12.5px] leading-relaxed text-fg-secondary">{s.text}</p>
                <p className="mt-2 text-[12.5px] font-semibold tabular-nums text-fg-primary">{s.fig}</p>
              </div>
            </li>
          ))}
        </ol>
      </Card>

      {/* Key figures */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KPITile label="Still to order" icon={Package} size="supporting" value={n0(t.toOrder)} unit="MWp"
          subtext={`For ${n0(t.open)} blocks not yet finished`}
          info="Modules the remaining blocks need, less what is on site, on the way or already ordered." />
        <KPITile label="Order now" icon={Truck} size="supporting" value={n0(t.late)} unit="MWp" tone={t.late > 0 ? 'watch' : 'neutral'}
          subtext="Needed sooner than suppliers can deliver"
          info="These blocks need modules before a new order could arrive, so they should be ordered this month." />
        <KPITile label="Waiting for supplier space" icon={Scale} size="supporting" value={n0(t.delayed)} unit="MWp" tone={t.delayed > 0 ? 'risk' : 'neutral'}
          subtext={`${delayedProjects} projects arrive later than needed`}
          info="A supplier’s monthly limit is full, so these orders move to a later month and arrive after the site needs them." />
        <KPITile label="Blocks after SCOD" icon={CalendarX2} size="supporting" value={n0(t.afterScod)} unit="blocks" tone={t.afterScod > 0 ? 'risk' : 'neutral'}
          subtext="Will finish after the contract date" infoAlign="right"
          info="Blocks whose modules are expected to be fitted after the project’s SCOD - the date the plant must be running." />
      </div>

      {/* AI summary */}
      <Card tone="ai">
        <CardHeader icon={Sparkles} title="What this means" eyebrow={summary?.ai ? 'AI summary' : 'Summary'}
          right={<button onClick={async () => {
            const slim = { ...plan, projects: plan.projects.map(({ blocks: _b, ...rest }) => rest) };
            setSummary(await call({ scope: 'portfolio', plan: slim }, 'portfolio'));
          }} disabled={busy === 'portfolio'}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-[12px] font-medium text-fg-secondary hover:bg-surface-sunken disabled:opacity-50">
            <RefreshCcw className={cx('h-3.5 w-3.5', busy === 'portfolio' && 'animate-spin')} /> Rewrite</button>} />
        <div className="mt-3">
          {busy === 'portfolio' && !summary ? <Loader inline size="sm" label="Writing the summary…" />
            : summary ? <><Bullets text={summary.text} /><AiNote ex={summary} /></>
              : <p className="text-[13px] text-fg-tertiary">The summary could not be written right now. The figures below are complete.</p>}
        </div>
      </Card>

      {/* Orders by month */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardHeader title="When to order" eyebrow="MWp to order each month, by supplier origin" />
          <p className="mt-1 text-[12.5px] text-fg-secondary">
            Each bar is what should be ordered in that month, after supplier limits. The first bar includes everything that is already late.
          </p>
          <div className="mt-3 h-[260px]"><ReactECharts notMerge theme={themeName} option={chart} style={{ height: '100%', width: '100%' }} /></div>
        </Card>
        <Card>
          <CardHeader title="Supplier limits" eyebrow="How full each month is (MWac)" />
          <p className="mt-1 text-[12.5px] text-fg-secondary">A full bar means that supplier cannot take more orders that month.</p>
          <div className="mt-3 space-y-4">
            {Object.entries(plan.quota_by_origin).map(([o, q]) => (
              <div key={o}>
                <div className="flex items-baseline justify-between text-[12.5px]">
                  <span className="font-semibold text-fg-primary">{ORIGIN_NAME[o] || o}</span>
                  <span className="text-fg-tertiary">limit {n0(q.cap_mwac)} MWac / month{q.known_origin ? '' : ' · assumed'}</span>
                </div>
                <div className="mt-1.5 flex gap-1">
                  {plan.months.slice(0, 12).map((m) => {
                    const used = q.used_mwac_by_month[m] || 0;
                    const pct = Math.min(100, (used / q.cap_mwac) * 100);
                    return (
                      <div key={m} className="flex-1" title={`${mon(m)}: ${n0(used)} of ${n0(q.cap_mwac)} MWac`}>
                        <div className="relative h-8 overflow-hidden rounded bg-surface-sunken">
                          <div className={cx('absolute inset-x-0 bottom-0', pct >= 99.5 ? 'bg-status-risk-solid' : 'bg-brand-blue/60')} style={{ height: `${pct}%` }} />
                        </div>
                        <p className="mt-0.5 text-center text-[9.5px] text-fg-tertiary">{mon(m).slice(0, 3)}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Things to fix */}
      {issues.length > 0 && (
        <Card tone="watch">
          <CardHeader icon={AlertTriangle} title="Things to fix" eyebrow="These change the plan once corrected" />
          <ul className="mt-3 divide-y divide-border-subtle">
            {issues.map((x) => (
              <li key={x.title} className="flex flex-wrap items-start justify-between gap-2 py-2.5">
                <div className="min-w-0 max-w-4xl">
                  <p className="text-[13.5px] font-semibold text-fg-primary">{x.title}</p>
                  <p className="mt-0.5 text-[12.5px] leading-relaxed text-fg-secondary">{x.detail}</p>
                </div>
                <span className="rounded-md border border-border-subtle px-2 py-0.5 text-[11px] text-fg-tertiary">{x.who}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Projects */}
      <Card pad="none" className="overflow-hidden">
        <div className="px-4 pt-3.5">
          <CardHeader title="Projects" eyebrow="Click a project to see its blocks and an explanation" />
        </div>
        <div className="mt-3 max-h-[70vh] overflow-auto custom-scrollbar border-t border-border">
          <table className="w-full min-w-[980px] border-separate border-spacing-0 text-[13px]">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-fg-tertiary">
                {[['Project', ''], ['Supplier', ''], ['Blocks left', 'text-right'], ['Still to order', 'text-right'],
                  ['Order now', 'text-right'], ['Waiting for space', 'text-right'], ['After SCOD', 'text-right'], ['P6 = SAP?', 'text-center']].map(([h, c]) => (
                  <th key={h} className={cx('sticky top-0 z-10 border-b border-border bg-surface-sunken px-3 py-2.5 font-semibold', c)}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...blk].sort((a, b) => (b.new_order_mwp || 0) - (a.new_order_mwp || 0)).map((p) => {
                const isOpen = open === p.id;
                const ex = projectEx[p.id];
                return (
                  <React.Fragment key={p.id}>
                    <tr onClick={() => setOpen(isOpen ? null : p.id)} className="cursor-pointer hover:bg-surface-sunken/50">
                      <td className="border-b border-border-subtle px-3 py-2">
                        <span className="inline-flex items-center gap-1.5 font-medium text-fg-primary">
                          <ChevronRight className={cx('h-3.5 w-3.5 text-fg-tertiary transition-transform', isOpen && 'rotate-90')} />
                          {p.project_name}
                        </span>
                        <span className="ml-5 block text-[11px] text-fg-tertiary">{p.cluster}{p.priority && p.priority !== 'standard' ? ` · ${p.priority}` : ''}</span>
                      </td>
                      <td className="border-b border-border-subtle px-3 py-2 text-fg-secondary">{ORIGIN_NAME[p.type] || p.type}</td>
                      <td className="border-b border-border-subtle px-3 py-2 text-right tabular-nums">{p.blocks_open} / {p.blocks_total}</td>
                      <td className="border-b border-border-subtle px-3 py-2 text-right font-medium tabular-nums">{n0(p.new_order_mwp)}</td>
                      <td className={cx('border-b border-border-subtle px-3 py-2 text-right tabular-nums', (p.late_need_mwp || 0) > 0.5 && 'text-status-watch-fg')}>{n0(p.late_need_mwp)}</td>
                      <td className={cx('border-b border-border-subtle px-3 py-2 text-right tabular-nums', (p.quota_delayed_mwp || 0) > 0.5 && 'text-status-risk-fg')}>
                        {n0(p.quota_delayed_mwp)}{(p.max_quota_delay_months || 0) > 0 && <span className="ml-1 text-[11px] text-fg-tertiary">({p.max_quota_delay_months} mo)</span>}
                      </td>
                      <td className={cx('border-b border-border-subtle px-3 py-2 text-right tabular-nums', (p.blocks_after_scod || 0) > 0 && 'text-status-risk-fg')}>{p.blocks_after_scod || 0}</td>
                      <td className="border-b border-border-subtle px-3 py-2 text-center">
                        {p.verify?.agree ? <span className="text-status-healthy-fg">✓</span>
                          : <span className="text-status-risk-fg" title="P6 and SAP give different quantities to order">✗</span>}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={8} className="border-b border-border bg-surface-sunken/30 px-5 py-4">
                          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
                            <div>
                              <div className="flex items-center justify-between gap-2">
                                <p className="text-[13px] font-semibold text-fg-primary">In plain words</p>
                                <button onClick={async (e) => { e.stopPropagation(); setProjectEx((s) => ({ ...s, [p.id]: null })); const r = await call({ scope: 'project', project: p }, `p${p.id}`); setProjectEx((s) => ({ ...s, [p.id]: r })); }}
                                  disabled={busy === `p${p.id}`}
                                  className="inline-flex items-center gap-1.5 rounded-lg border border-status-ai/40 bg-status-ai/10 px-2.5 py-1 text-[12px] font-medium text-fg-primary hover:bg-status-ai/15 disabled:opacity-50">
                                  <Sparkles className="h-3.5 w-3.5" /> {ex ? 'Explain again' : 'Explain this project'}
                                </button>
                              </div>
                              <div className="mt-2">
                                {busy === `p${p.id}` ? <Loader inline size="sm" label="Writing…" />
                                  : ex ? <><Bullets text={ex.text} /><AiNote ex={ex} /></>
                                    : <p className="text-[12.5px] text-fg-tertiary">Ask for a short explanation of this project’s plan.</p>}
                              </div>
                              <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
                                {[
                                  ['Modules in its blocks', `${n0(p.verify?.block_mwp)} MWp`],
                                  ['Already fitted', `${n0(p.installed_mwp)} MWp`],
                                  ['On site / on the way / ordered', `${n0(p.pipeline_mwp)} MWp`],
                                  ['Ordered in SAP (all time)', `${n0(p.verify?.sap_ordered_mwp)} MWp`],
                                  ['Supplier lead time', `${p.lead_days} days`],
                                  ['Fitting speed used', `${p.pace_mwp_per_day?.toFixed(2)} MWp/day`],
                                  ['SCOD', dmy(p.scod)], ['LTA', dmy(p.lta)],
                                ].map(([k, v]) => (
                                  <React.Fragment key={k}><dt className="text-fg-tertiary">{k}</dt><dd className="text-right font-medium tabular-nums text-fg-primary">{v}</dd></React.Fragment>
                                ))}
                              </dl>
                              <p className="mt-3 text-[11.5px] font-semibold text-fg-secondary">Order plan</p>
                              <div className="mt-1 flex flex-wrap gap-1.5">
                                {Object.entries(p.orders_by_month || {}).filter(([, v]) => v > 0.5).map(([m, v]) => (
                                  <span key={m} className="rounded-md border border-border-subtle bg-surface-1 px-2 py-0.5 text-[11.5px] tabular-nums">
                                    <span className="text-fg-tertiary">{mon(m)}</span> <span className="font-semibold text-fg-primary">{n0(v)}</span>
                                  </span>
                                ))}
                              </div>
                            </div>
                            <div className="min-w-0">
                              <p className="text-[13px] font-semibold text-fg-primary">Blocks <InfoTip info="Each block’s module quantity and installation dates come from its own Module Installation activity in P6." /></p>
                              <div className="mt-2 max-h-[340px] overflow-auto custom-scrollbar rounded-lg border border-border-subtle">
                                <table className="w-full text-[12px]">
                                  <thead className="sticky top-0 bg-surface-sunken text-left text-[10.5px] uppercase tracking-wide text-fg-tertiary">
                                    <tr><th className="px-2.5 py-2">Block</th><th className="px-2.5 py-2 text-right">MWp</th><th className="px-2.5 py-2 text-right">Fitted</th>
                                      <th className="px-2.5 py-2">Fitting dates</th><th className="px-2.5 py-2">Status</th></tr>
                                  </thead>
                                  <tbody>
                                    {(p.blocks || []).map((b) => {
                                      const st = blockStatus(b);
                                      return (
                                        <tr key={b.block} className="border-t border-border-subtle">
                                          <td className="px-2.5 py-1.5 font-medium text-fg-primary">{b.block}</td>
                                          <td className="px-2.5 py-1.5 text-right tabular-nums">{b.mwp.toFixed(1)}</td>
                                          <td className="px-2.5 py-1.5 text-right tabular-nums">{b.installed_mwp.toFixed(1)}</td>
                                          <td className="px-2.5 py-1.5 tabular-nums text-fg-secondary">
                                            {b.window ? `${dmy(b.window[0])} → ${dmy(b.window[1])}` : `${dmy(b.start)} → ${dmy(b.finish)}`}
                                          </td>
                                          <td className={cx('px-2.5 py-1.5', TONE_TEXT[st.tone])}>
                                            {st.text}
                                            {b.flags.filter((f) => f.includes('SCOD') || f.includes('LTA')).map((f) => (
                                              <span key={f} className="ml-1 block text-[11px] text-status-risk-fg">{f.replace('installs', 'Fitted')}</span>
                                            ))}
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="border-t border-border px-4 py-2.5 text-[11px] text-fg-tertiary">
          Sources: P6 (blocks, dates, fitted quantities) · SAP (modules ordered, delivered, on the way) · project master (supplier origin, priority, SCOD, LTA).
          Speeds and structure waits are worked out from blocks already finished.
        </p>
      </Card>
    </div>
  );
}
