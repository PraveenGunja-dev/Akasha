/* Advanced AI planning - what the Ordering Schedule gains with the switch on.

   The schedule keeps its own layout. It gains six site-driven columns, and
   its month-wise plan and date columns show the site-driven figure next to
   the standard one - tinted as AI so new reads as new. A cell says one thing;
   a click opens a structured panel where the user clicked: a header with the
   figure that matters, sections of block chips and bars, and suggested next
   steps worked out from the same data.

   Colour: AI purple marks what is new; the status palette marks state only
   (installed / ready / late / at risk); brand blue is weather only.

   Data: GET /api/module-deliveries-beta/advanced-plan (services/advanced_planning.py),
   one plan per P6 project, joined to the schedule's rows by mapping id. Dates
   come from the AI prediction service where it answered, else the measured
   engine - tagged on every date. */
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowRight, ChevronRight, Info, Lightbulb } from 'lucide-react';
import { Dialog } from '../../components/ui/primitives';
import type { AdvancedPlan, BlockPlan, PhasePlan, PlanStatus, ProjectPlan, QuotaUse, StageKey } from './advancedTypes';

const API = import.meta.env.VITE_API_BASE || '';

export const ADVANCED_COL_COUNT = 6;

/* ── Tokens ────────────────────────────────────────────────────────────── */
const TH_AI = '!bg-[var(--status-ai-solid)] !border-[var(--status-ai-border)]';
export const TD_AI = 'bg-[var(--status-ai-bg)]';
const FIRST_EDGE = 'border-l-2 !border-l-[var(--status-ai-solid)]';
const AI_TEXT = 'text-status-ai-fg';
const WX_TEXT = 'text-brand-blue';

type ToneKey = 'critical' | 'risk' | 'watch' | 'healthy' | 'done' | 'ai' | 'neutral';
const TONE: Record<ToneKey, string> = {
  critical: 'bg-status-critical-bg text-status-critical-fg border-status-critical-border',
  risk: 'bg-status-risk-bg text-status-risk-fg border-status-risk-border',
  watch: 'bg-status-watch-bg text-status-watch-fg border-status-watch-border',
  healthy: 'bg-status-healthy-bg text-status-healthy-fg border-status-healthy-border',
  done: 'bg-status-done-bg text-status-done-fg border-status-done-border',
  ai: 'bg-status-ai-bg text-status-ai-fg border-status-ai-border',
  neutral: 'bg-surface-sunken text-fg-secondary border-border-subtle',
};
const FILL: Record<ToneKey, string> = {
  critical: 'bg-status-critical-solid', risk: 'bg-status-risk-solid', watch: 'bg-status-watch-solid',
  healthy: 'bg-status-healthy-solid', done: 'bg-status-done-solid', ai: 'bg-status-ai-solid', neutral: 'bg-fg-tertiary',
};

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const fmtDate = (iso?: string | null) => {
  if (!iso) return '-';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}-${MON[Number(m) - 1]}-${y.slice(2)}`;
};
const monthLabelOf = (iso: string) => `${MON[Number(iso.slice(5, 7)) - 1]}-${iso.slice(2, 4)}`;
const mw = (v: number) => Math.round(v).toLocaleString('en-IN');
const days = (a: string, b: string) => Math.round((Date.parse(a) - Date.parse(b)) / 86400000);
const todayIso = () => new Date().toISOString().slice(0, 10);
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;
const blkList = (bs: string[], max = 6) => bs.slice(0, max).join(', ') + (bs.length > max ? ` +${bs.length - max}` : '');

/** dd-Mon-yy / dd-Mon-yyyy / ISO -> ISO date, or null. */
export function toIso(text?: string | null): string | null {
  if (!text) return null;
  const iso = text.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`;
  const m = text.match(/(\d{1,2})[-\s]([A-Za-z]{3})[a-z]*[-\s](\d{2,4})/);
  if (!m) return null;
  const mi = MON.findIndex(x => x.toLowerCase() === m[2].toLowerCase());
  if (mi < 0) return null;
  const y = m[3].length === 2 ? `20${m[3]}` : m[3];
  return `${y}-${String(mi + 1).padStart(2, '0')}-${m[1].padStart(2, '0')}`;
}

const STAGE_SHORT: Record<StageKey, string> = {
  piling: 'Piling', capping: 'Pile capping', torque_tube: 'Torque tube', bracing: 'Bracing',
  purlin: 'Purlin', module: 'Modules',
};
const STAGE_ORDER: StageKey[] = ['piling', 'capping', 'torque_tube', 'bracing', 'purlin', 'module'];

const STATUS: Record<PlanStatus, { label: string; tone: ToneKey }> = {
  late: { label: 'Late - order now', tone: 'critical' },
  order_now: { label: 'Order this month', tone: 'risk' },
  hold: { label: 'Hold', tone: 'watch' },
  covered: { label: 'Covered', tone: 'healthy' },
  installed: { label: 'Installed', tone: 'done' },
  no_dates: { label: 'No dates', tone: 'neutral' },
};

/* ── Data ──────────────────────────────────────────────────────────────── */
export function useAdvancedPlan(enabled: boolean, portfolio: string | null) {
  const [plan, setPlan] = useState<AdvancedPlan | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    setLoading(true);
    setError('');
    const q = portfolio ? `?portfolio=${encodeURIComponent(portfolio)}` : '';
    fetch(`${API}/akasha/api/module-deliveries-beta/advanced-plan${q}`)
      .then(async r => {
        const body = await r.json().catch(() => null);
        if (!r.ok) throw new Error(body?.detail || `Server returned ${r.status}`);
        if (!body || !Array.isArray(body.projects)) {
          throw new Error(body?.detail || 'The server did not return a plan - restart the backend if it predates this feature.');
        }
        return body as AdvancedPlan;
      })
      .then(d => { if (alive) setPlan(d); })
      .catch(e => { if (alive) setError(e.message || 'Could not load the advanced plan'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [enabled, portfolio]);
  const byId = useMemo(() => {
    const m = new Map<number, ProjectPlan>();
    (plan?.projects ?? []).forEach(p => p.ids.forEach(id => m.set(id, p)));
    return m;
  }, [plan]);
  return { plan, byId, error, loading };
}

/* ── Building blocks ───────────────────────────────────────────────────── */
export function ClickPop({ content, children, className = '', label }: {
  content: React.ReactNode; children: React.ReactNode; className?: string; label?: string;
}) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null);
  const [box, setBox] = useState<{ left: number; top: number } | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!at) return;
    const away = (e: MouseEvent) => {
      if (panel.current?.contains(e.target as Node) || trigger.current?.contains(e.target as Node)) return;
      setAt(null);
    };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { setAt(null); trigger.current?.focus(); } };
    const scroll = (e: Event) => { if (!panel.current?.contains(e.target as Node)) setAt(null); };
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', key);
    window.addEventListener('scroll', scroll, true);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', key);
      window.removeEventListener('scroll', scroll, true);
    };
  }, [at]);

  // Open at the click point, then keep the whole panel on screen.
  useLayoutEffect(() => {
    if (!at || !panel.current) { setBox(null); return; }
    const r = panel.current.getBoundingClientRect();
    const pad = 12;
    const left = Math.max(pad, Math.min(at.x + 8, window.innerWidth - r.width - pad));
    const below = at.y + 12;
    const top = below + r.height + pad > window.innerHeight ? Math.max(pad, at.y - r.height - 12) : below;
    setBox({ left, top });
  }, [at]);

  return (
    <>
      <button
        ref={trigger} type="button" aria-expanded={!!at} aria-haspopup="dialog" aria-label={label}
        onClick={e => {
          if (at) { setAt(null); return; }
          const r = e.currentTarget.getBoundingClientRect();
          setAt({ x: e.clientX || r.left, y: e.clientY || r.bottom });
        }}
        className={`block w-full cursor-pointer rounded-md px-1 py-0.5 text-inherit transition-colors hover:bg-[var(--status-ai-border)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--status-ai-solid)] ${at ? 'bg-[var(--status-ai-border)]' : ''} ${className}`}
      >
        {children}
      </button>
      {at && createPortal(
        <div
          ref={panel} role="dialog" aria-label={label}
          style={{ position: 'fixed', left: box?.left ?? at.x, top: box?.top ?? at.y + 12, visibility: box ? 'visible' : 'hidden' }}
          className="custom-scrollbar z-[9999] max-h-[72vh] w-max max-w-[min(660px,calc(100vw-24px))] overflow-auto rounded-xl border border-border-default bg-surface-1 text-left text-[11px] leading-relaxed text-fg-primary shadow-xl shadow-black/10 dark:shadow-black/40"
        >
          {content}
        </div>,
        document.body,
      )}
    </>
  );
}

/** A detail panel: header (title, one-line context, the number that matters), body, footer. */
function Pop({ title, sub, metric, metricLabel, children, footer, width = 560 }: {
  title: React.ReactNode; sub?: React.ReactNode; metric?: React.ReactNode; metricLabel?: string;
  children: React.ReactNode; footer?: React.ReactNode; width?: number;
}) {
  return (
    <div style={{ width }} className="max-w-full">
      <div className="flex items-start justify-between gap-4 border-b border-border-subtle bg-[var(--status-ai-bg)] px-4 py-3">
        <div className="min-w-0">
          <div className={`text-[12.5px] font-bold leading-tight ${AI_TEXT}`}>✦ {title}</div>
          {sub && <div className="mt-0.5 text-[11px] text-fg-secondary">{sub}</div>}
        </div>
        {metric != null && (
          <div className="shrink-0 text-right">
            <div className="text-[18px] font-bold leading-none tabular-nums text-fg-primary">{metric}</div>
            {metricLabel && <div className="mt-1 text-[10px] text-fg-tertiary">{metricLabel}</div>}
          </div>
        )}
      </div>
      <div className="space-y-3.5 px-4 py-3">{children}</div>
      {footer && <div className="border-t border-border-subtle px-4 py-2 text-[10px] leading-snug text-fg-tertiary">{footer}</div>}
    </div>
  );
}

function Section({ label, right, children }: { label: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-fg-tertiary">{label}</span>
        {right && <span className="text-[10.5px] text-fg-secondary">{right}</span>}
      </div>
      {children}
    </section>
  );
}

function Pill({ tone = 'neutral', children, title, className = '' }: {
  tone?: ToneKey; children: React.ReactNode; title?: string; className?: string;
}) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-1.5 py-[1px] text-[10px] font-semibold leading-tight ${TONE[tone]} ${className}`}>
      {children}
    </span>
  );
}

/** A block as a chip: number, then what matters about it. */
function BlockChip({ tone = 'neutral', block, children, title }: {
  tone?: ToneKey; block: string; children?: React.ReactNode; title?: string;
}) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-[2px] text-[10.5px] leading-tight ${TONE[tone]}`}>
      <b className="font-semibold">Blk {block}</b>
      {children && <span className="opacity-80">{children}</span>}
    </span>
  );
}

function Bar({ pct, tone = 'ai', className = '' }: { pct: number; tone?: ToneKey; className?: string }) {
  return (
    <span className={`relative block h-1.5 overflow-hidden rounded-full bg-[var(--border-subtle)] ${className}`} aria-hidden>
      <span className={`absolute inset-y-0 left-0 rounded-full ${FILL[tone]}`} style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </span>
  );
}

/** Where a date came from: the AI model, or the measured engine (fallback). */
export function SrcTag({ src }: { src?: 'ai' | 'engine' }) {
  if (!src) return null;
  return src === 'ai'
    ? <span className="ml-1 rounded bg-status-ai-solid px-1 py-[0.5px] text-[8.5px] font-bold uppercase tracking-wide text-white" title="AI prediction service">AI</span>
    : <span className="ml-1 rounded border border-border-subtle px-1 py-[0.5px] text-[8.5px] font-semibold uppercase tracking-wide text-fg-tertiary"
        title="Measured engine - the fallback when the AI service has no answer">engine</span>;
}

/** "+4 d weather" in blue, or nothing. */
export function WxDelta({ d, show }: { d?: number | null; show: boolean }) {
  if (!show || d == null || d === 0) return null;
  return <span className={`ml-1 whitespace-nowrap font-semibold ${WX_TEXT}`}>{d > 0 ? `+${d}` : d} d weather</span>;
}

/** A date, then the weather-adjusted one in blue when the switch is on. */
function DateWx({ base, wx, show }: { base?: string | null; wx?: string | null; show: boolean }) {
  const d = show && base && wx ? days(wx, base) : 0;
  return <>{fmtDate(base)}{d !== 0 && <span className={`ml-1 whitespace-nowrap font-semibold ${WX_TEXT}`}>→ {fmtDate(wx)} ({d > 0 ? '+' : ''}{d} d)</span>}</>;
}

/* ── Suggestions: plain next steps from the plan's own figures ─────────── */
interface Suggestion { tone: ToneKey; text: React.ReactNode; topic: 'order' | 'site' | 'ftc' | 'weather' | 'ai' }

function holding(b: BlockPlan): StageKey | null {
  const s = b.stages.find(x => !x.missing && !x.done);
  return s ? s.key : null;
}

export function suggestionsFor(plan: ProjectPlan): Suggestion[] {
  const out: Suggestion[] = [];
  const s = plan.supply;
  const blocks = plan.blocks ?? [];
  const short = blocks.filter(b => b.order_by);
  const late = short.filter(b => b.status === 'late');
  const orderBy = plan.decision?.order_by ?? plan.first_order_by;
  const shortMw = short.reduce((a, b) => a + (b.short_mwp ?? 0), 0);

  if (late.length) {
    const maxLate = Math.max(0, ...late.map(b => b.arrival_late_days ?? 0));
    out.push({ tone: 'critical', topic: 'order', text: <>Order <b>{mw(late.reduce((a, b) => a + (b.short_mwp ?? 0), 0))} MWp now</b> - {plural(late.length, 'block')} ({blkList(late.map(b => b.block))}) are past their order-by date.{maxLate > 0 && <> Ordered today, modules land up to <b>{maxLate} d after</b> the site needs them.</>}</> });
  } else if (plan.status === 'order_now' && orderBy) {
    out.push({ tone: 'risk', topic: 'order', text: <>Raise the PO for <b>{mw(shortMw)} MWp by {fmtDate(orderBy)}</b> so blocks {blkList(short.map(b => b.block))} have modules when their structure is ready.</> });
  } else if (plan.status === 'hold' && orderBy) {
    out.push({ tone: 'watch', topic: 'order', text: <>Hold - the next order is due <b>{fmtDate(orderBy)}</b>. Ordering earlier would leave modules waiting in the yard.</> });
  } else if (plan.status === 'covered' && s) {
    out.push({ tone: 'healthy', topic: 'order', text: <>No order needed: <b>{mw(s.available_mwp)} MWp</b> in the yard, in transit and on POs covers the <b>{mw(s.need_mwp)} MWp</b> still to install.{s.in_transit_mwp > 0 && <> Track the {mw(s.in_transit_mwp)} MWp in transit.</>}</> });
  }
  if (plan.no_po && shortMw > 0) {
    out.push({ tone: 'watch', topic: 'order', text: <>No module PO in SAP for this project - confirm the procurement route before <b>{fmtDate(orderBy)}</b>.</> });
  }

  // The stage holding the most unfinished blocks, and how far behind it runs.
  const counts = new Map<StageKey, number>();
  blocks.forEach(b => { const h = holding(b); if (h) counts.set(h, (counts.get(h) ?? 0) + 1); });
  const [topStage, topCount] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0] ?? [];
  if (topStage && topCount) {
    const st = plan.stages?.find(x => x.key === topStage);
    const delay = st?.worst_delay_days ?? 0;
    out.push({
      tone: delay > 30 ? 'risk' : 'neutral', topic: 'site',
      text: <><b>{STAGE_SHORT[topStage]}</b> is holding {plural(topCount, 'block')}{delay > 0 && <>, up to <b>{delay} d behind</b> baseline</>}{st && st.done_last_30d === 0 && st.blocks_done < st.blocks && <> - no block finished it in the last 30 days</>}.</>,
    });
  }

  // Modules in the yard with nothing ready for them.
  const ready = blocks.filter(b => b.stages.find(x => x.key === 'purlin')?.done && b.remaining_mwp > 0.01).length;
  if (s && s.stock_mwp > 5 && ready === 0) {
    const next = blocks.map(b => b.stages.find(x => x.key === 'purlin')).filter(x => x && !x.done && x.forecast_finish).map(x => x!.forecast_finish!).sort()[0];
    out.push({ tone: 'watch', topic: 'site', text: <><b>{mw(s.stock_mwp)} MWp</b> is in the yard but no block is ready for modules{next ? <> until about <b>{fmtDate(next)}</b></> : ''} - idle stock.</> });
  }

  (plan.phases ?? []).filter(p => p.at_risk && !p.charged).slice(0, 2).forEach(ph => {
    const by = new Map<string, number>();
    ph.late_blocks.forEach(l => l.holding_stage && by.set(l.holding_stage, (by.get(l.holding_stage) ?? 0) + 1));
    const main = [...by.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    out.push({ tone: 'risk', topic: 'ftc', text: <><b>{ph.name.replace(/First Time Charging\s*-?\s*/i, '')}</b>: {plural(ph.late_blocks.length, 'block')} miss the {fmtDate(ph.ftc)} FTC{main && <>, mostly waiting on <b>{main.toLowerCase()}</b></>}{ph.slip_days ? <> (forecast +{ph.slip_days} d)</> : ''}.</> });
  });

  const pushed = blocks.filter(b => b.quota === 'delayed');
  if (pushed.length) {
    const most = Math.max(...pushed.map(b => b.quota_shift_days ?? 0));
    out.push({ tone: 'risk', topic: 'order', text: <>Vendor limit: {plural(pushed.length, 'block')} pushed up to <b>{most} d</b> by the {plan.quota_source} monthly limit - book extra {plan.quota_source} capacity or a second origin to keep the timing.</> });
  }
  const pulled = blocks.filter(b => b.quota === 'early');
  if (pulled.length) {
    out.push({ tone: 'watch', topic: 'order', text: <>{plural(pulled.length, 'block')} ordered early to fit the {plan.quota_source} limit - check yard space for the earlier delivery.</> });
  }

  const heavy = plan.weather?.heavy_rain_ahead ?? [];
  if (heavy.length) {
    out.push({ tone: 'neutral', topic: 'weather', text: <>Heavy rain forecast at {plan.weather?.station} on <b>{heavy.slice(0, 3).map(fmtDate).join(', ')}</b> - plan structure and module work around it.</> });
  }
  (plan.ai?.actions ?? []).slice(0, 2).forEach(a => out.push({ tone: 'ai', topic: 'ai', text: a }));
  return out;
}

function Suggestions({ items, max = 4 }: { items: Suggestion[]; max?: number }) {
  if (!items.length) return null;
  return (
    <div className="rounded-lg border border-[var(--status-ai-border)] bg-[var(--status-ai-bg)] p-2.5">
      <div className={`mb-1.5 flex items-center gap-1.5 text-[11px] font-bold ${AI_TEXT}`}>
        <Lightbulb className="h-3.5 w-3.5" strokeWidth={2} /> Suggested next steps
      </div>
      <ul className="space-y-1">
        {items.slice(0, max).map((s, i) => (
          <li key={i} className="flex gap-2">
            <span className={`mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full ${FILL[s.tone]}`} aria-hidden />
            <span className="text-[11px] leading-snug text-fg-primary">{s.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ── Injected table parts (the page's own Th / Td / ThLabel) ───────────── */
type ThComp = React.ComponentType<{ children: React.ReactNode; className?: string; rowSpan?: number; tip?: string }>;
export type TdComp = React.ComponentType<{
  children?: React.ReactNode; className?: string; align?: 'left' | 'center' | 'right';
  tipContent?: React.ReactNode; tipWide?: boolean; tip?: string;
}>;
type ThLabelComp = React.ComponentType<{ label: string; unit?: string }>;

export function AdvancedHeader({ Th, ThLabel }: { Th: ThComp; ThLabel: ThLabelComp }) {
  return (
    <>
      <Th rowSpan={2} className={`min-w-[128px] ${TH_AI} ${FIRST_EDGE}`}
        tip="New - Advanced AI planning. Each block's site stages from P6. Dates come from the AI prediction service where it answers (tagged AI), else the measured engine (tagged engine). Click a cell for the full plan and suggested next steps.">
        <ThLabel label="✦ Site progress" unit="& plan" />
      </Th>
      <Th rowSpan={2} className={`min-w-[112px] ${TH_AI}`}
        tip="New. Blocks whose structure (purlin) is complete and can take modules, and when the rest will be ready.">
        <ThLabel label="✦ Blocks ready" unit="for modules" />
      </Th>
      <Th rowSpan={2} className={`min-w-[104px] ${TH_AI}`}
        tip="New. Modules each block needs on site, 14 days before its forecast module installation start - by month, MWp.">
        <ThLabel label="✦ Modules needed" unit="on site (MWp)" />
      </Th>
      <Th rowSpan={2} className={`min-w-[124px] ${TH_AI}`}
        tip="New. Stock and open POs go to blocks in the order they need modules; a block left short must be ordered by its need date minus the lead time.">
        <ThLabel label="✦ Order & arrival" unit="(site-driven)" />
      </Th>
      <Th rowSpan={2} className={`min-w-[96px] ${TH_AI}`}
        tip="New. When the advanced plan orders compared with the standard plan's first module ordering date (FTC - 45 d - lead time).">
        <ThLabel label="✦ Impact vs" unit="standard plan" />
      </Th>
      <Th rowSpan={2} className={`min-w-[100px] ${TH_AI}`}
        tip="New. FTC phases where a block is forecast to finish modules after the phase FTC date.">
        <ThLabel label="✦ FTC risk" unit="(forecast)" />
      </Th>
    </>
  );
}

export function AdvancedBlankCells({ Td }: { Td: TdComp }) {
  return (
    <>
      <Td className={`${TD_AI} ${FIRST_EDGE}`} /><Td className={TD_AI} /><Td className={TD_AI} />
      <Td className={TD_AI} /><Td className={TD_AI} /><Td className={TD_AI} />
    </>
  );
}

/* ── Per-row cells ─────────────────────────────────────────────────────── */
function groupByMonth<T>(items: T[], key: (t: T) => string | null | undefined) {
  const now = todayIso().slice(0, 7);
  const g = new Map<string, T[]>();
  items.forEach(t => {
    const k = key(t);
    if (!k) return;
    const m = k.slice(0, 7) < now ? 'now' : k.slice(0, 7);
    g.set(m, [...(g.get(m) ?? []), t]);
  });
  return [...g.entries()].sort((a, b) => (a[0] === 'now' ? -1 : b[0] === 'now' ? 1 : a[0].localeCompare(b[0])));
}
const groupLabel = (m: string) => (m === 'now' ? 'Now' : monthLabelOf(`${m}-01`));

/** Earliest dd-Mon-yy date in the standard plan's module ordering text. */
function firstStandardDate(text?: string | null): string | null {
  const out: string[] = [];
  for (const m of (text || '').matchAll(/\d{1,2}-[A-Za-z]{3}-\d{2}/g)) {
    const iso = toIso(m[0]);
    if (iso) out.push(iso);
  }
  return out.sort()[0] ?? null;
}

export function AdvancedCells({ plan, Td, standardModuleDate, error, loading, weather }: {
  plan?: ProjectPlan; Td: TdComp; standardModuleDate?: string | null; error?: string; loading?: boolean; weather: boolean;
}) {
  if (loading || error || !plan || !plan.plannable) {
    const msg = loading ? 'Loading…' : error ? 'Unavailable' : plan && !plan.plannable ? 'No block data in P6' : '-';
    return (
      <>
        <Td className={`${TD_AI} ${FIRST_EDGE} text-fg-tertiary`} tip={error || plan?.reason || undefined}>{msg}</Td>
        <Td className={TD_AI} /><Td className={TD_AI} /><Td className={TD_AI} /><Td className={TD_AI} /><Td className={TD_AI} />
      </>
    );
  }
  const blocks = plan.blocks ?? [];
  return (
    <>
      <Td className={`${TD_AI} ${FIRST_EDGE}`} align="left"><SiteProgress plan={plan} weather={weather} /></Td>
      <Td className={TD_AI} align="left"><Ready plan={plan} blocks={blocks} weather={weather} /></Td>
      <Td className={TD_AI} align="left"><Need plan={plan} blocks={blocks} /></Td>
      <Td className={TD_AI} align="left"><Order plan={plan} /></Td>
      <Td className={TD_AI}><Impact plan={plan} standard={firstStandardDate(standardModuleDate)} /></Td>
      <Td className={TD_AI}><FtcRisk plan={plan} weather={weather} /></Td>
    </>
  );
}

function stageState(s?: { blocks: number; blocks_done: number; pct: number }): { text: string; tone: ToneKey } {
  if (!s) return { text: '-', tone: 'neutral' };
  if (s.blocks_done >= s.blocks) return { text: 'Completed', tone: 'healthy' };
  if (s.pct > 0.5) return { text: 'In progress', tone: 'ai' };
  return { text: 'Not started', tone: 'neutral' };
}

/** Per stage, the finish of the block that finishes it last (and with weather). */
function stageFinish(plan: ProjectPlan, k: StageKey) {
  let best: { f?: string | null; wx?: string | null } = {};
  (plan.blocks ?? []).forEach(b => {
    const s = b.stages.find(x => x.key === k);
    if (s?.forecast_finish && (!best.f || s.forecast_finish > best.f)) best = { f: s.forecast_finish, wx: s.forecast_finish_wx };
  });
  return best;
}

/** The plan as four steps: order -> on site -> installed -> FTC. */
function PlanSteps({ plan, weather }: { plan: ProjectPlan; weather: boolean }) {
  const dec = plan.decision;
  const orderBy = dec ? dec.order_by : plan.first_order_by;
  const tc = dec?.tc;
  const short = (plan.blocks ?? []).filter(b => b.order_by);
  const lastArrival = short.map(b => b.arrival).filter(Boolean).sort().slice(-1)[0];
  const mods = stageFinish(plan, 'module');
  const modDone = (plan.stages ?? []).find(s => s.key === 'module');
  const today = todayIso();
  const steps: { label: string; date?: string | null; wx?: string | null; src?: 'ai' | 'engine'; note?: React.ReactNode; tone: ToneKey }[] = [
    { label: 'Order modules by', date: orderBy, src: dec?.order_by_source,
      note: !orderBy ? 'nothing to order' : orderBy < today ? `${days(today, orderBy)} d late` : `in ${days(orderBy, today)} d`,
      tone: !orderBy ? 'healthy' : orderBy < today ? 'critical' : days(orderBy, today) <= 30 ? 'risk' : 'ai' },
    { label: 'Needed on site', date: tc, src: dec?.tc_source,
      note: lastArrival ? <>arrive by {fmtDate(lastArrival)}</> : tc ? 'first block' : 'all installed', tone: 'ai' },
    { label: 'All modules installed', date: modDone && modDone.blocks_done >= modDone.blocks ? null : mods.f, wx: mods.wx,
      note: modDone && modDone.blocks_done >= modDone.blocks ? 'completed' : 'forecast', tone: modDone && modDone.blocks_done >= modDone.blocks ? 'healthy' : 'ai' },
    { label: dec?.phase && dec.ftc ? 'Next FTC' : 'Last FTC', date: dec?.ftc ?? plan.completion_forecast,
      wx: dec?.ftc_source === 'ai' ? null : plan.completion_forecast_wx, src: dec?.ftc ? dec.ftc_source : undefined,
      note: dec?.phase ? dec.phase.replace(/First Time Charging\s*-?\s*/i, '') : 'forecast', tone: 'ai' },
  ];
  return (
    <ol className="grid grid-cols-4 gap-2">
      {steps.map((s, i) => (
        <li key={i} className="relative">
          <div className={`mb-1.5 h-1 rounded-full ${FILL[s.tone]}`} aria-hidden />
          <div className="flex items-center gap-1 text-[10px] text-fg-tertiary">
            <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full border border-border-subtle text-[8.5px] font-bold">{i + 1}</span>
            {s.label}
          </div>
          <div className="mt-0.5 text-[12.5px] font-bold tabular-nums text-fg-primary">
            {s.date ? fmtDate(s.date) : s.note === 'completed' ? 'Done' : '-'}<SrcTag src={s.date ? s.src : undefined} />
          </div>
          {weather && s.date && s.wx && days(s.wx, s.date) !== 0 && (
            <div className={`text-[10px] font-semibold ${WX_TEXT}`}>{days(s.wx, s.date) > 0 ? '+' : ''}{days(s.wx, s.date)} d weather</div>
          )}
          <div className={`text-[10px] ${s.tone === 'critical' ? 'font-semibold text-status-critical-fg' : 'text-fg-secondary'}`}>{s.note}</div>
        </li>
      ))}
    </ol>
  );
}

/** Everything about one project: the plan, the stages, the AI's view, next steps. */
export function PlanDetail({ plan, weather }: { plan: ProjectPlan; weather: boolean }) {
  const st = (k: StageKey) => plan.stages?.find(s => s.key === k);
  const dec = plan.decision;
  const w = plan.weather;
  const total = (plan.blocks ?? []).length;
  return (
    <Pop width={620}
      title={plan.project_name}
      sub={<>{plural(total, 'block')} · {plan.origin ?? 'Domestic'} modules, lead {plan.lead_days} d
        {dec && <> · <span className={dec.source.startsWith('AI') ? `font-semibold ${AI_TEXT}` : ''}>{dec.source}</span>
          {dec.confidence != null && <> ({Math.round(dec.confidence * 100)}% confidence{dec.risk ? `, ${dec.risk.toLowerCase()} risk` : ''})</>}</>}</>}
      metric={STATUS[plan.status ?? 'covered'].label}
      footer={<>
        {plan.has_baseline ? <>Behind baseline = forecast vs the assigned P6 baseline <b>{plan.baseline}</b>. </> : 'No baseline assigned in P6 - no delay figures. '}
        Forecasts are estimates: piling, capping and modules at their planned duration; structure at the pace this project's finished blocks show (backtested on completed projects).
        {' '}Weather: {w?.station ? `${w.station}, ${w.source}.` : `${w?.source ?? 'not available'}.`}
      </>}
    >
      <Section label="The plan"><PlanSteps plan={plan} weather={weather} /></Section>

      <Section label="Site stages" right={<>{st('module')?.blocks_done ?? 0} of {total} blocks with modules complete</>}>
        <div className="grid grid-cols-[96px_84px_1fr_64px_86px_118px] items-center gap-x-2.5 gap-y-1.5">
          <span className="text-[10px] text-fg-tertiary">Stage</span><span className="text-[10px] text-fg-tertiary">Status</span>
          <span className="text-[10px] text-fg-tertiary">Progress</span><span className="text-right text-[10px] text-fg-tertiary">Blocks</span>
          <span className="text-right text-[10px] text-fg-tertiary">vs baseline</span><span className="text-[10px] text-fg-tertiary">All blocks done by</span>
          {STAGE_ORDER.map(k => {
            const s = st(k);
            if (!s) return null;
            const state = stageState(s);
            const fin = stageFinish(plan, k);
            const complete = s.blocks_done >= s.blocks;
            return (
              <React.Fragment key={k}>
                <span className="font-medium text-fg-primary">{STAGE_SHORT[k]}</span>
                <span><Pill tone={state.tone}>{state.text}</Pill></span>
                <span className="flex items-center gap-2">
                  <Bar pct={s.pct} tone={complete ? 'healthy' : 'ai'} className="flex-1" />
                  <span className="w-8 text-right tabular-nums text-fg-secondary">{Math.round(s.pct)}%</span>
                </span>
                <span className="text-right tabular-nums">{s.blocks_done}/{s.blocks}</span>
                <span className="text-right">
                  {complete ? <span className="text-fg-tertiary">-</span>
                    : s.worst_delay_days && s.worst_delay_days > 0
                      ? <Pill tone={s.worst_delay_days > 30 ? 'critical' : 'risk'}>+{s.worst_delay_days} d</Pill>
                      : <Pill tone="healthy">on time</Pill>}
                </span>
                <span className="tabular-nums">{complete ? <span className="text-status-healthy-fg">Completed</span> : <DateWx base={fin.f} wx={fin.wx} show={weather} />}</span>
              </React.Fragment>
            );
          })}
        </div>
      </Section>

      {plan.ai && (plan.ai.summary || (plan.ai.drivers ?? []).length > 0) && (
        <Section label="AI model says">
          {plan.ai.summary && <div className="text-fg-primary">{plan.ai.summary}</div>}
          {(plan.ai.drivers ?? []).length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">{plan.ai.drivers!.map((d, i) => <Pill key={i} tone="ai">{d}</Pill>)}</div>
          )}
        </Section>
      )}

      <Suggestions items={suggestionsFor(plan)} max={5} />
    </Pop>
  );
}

function SiteProgress({ plan, weather }: { plan: ProjectPlan; weather: boolean }) {
  const st = (k: StageKey) => plan.stages?.find(s => s.key === k);
  const structure = st('purlin'), modules = st('module');
  const mod = stageFinish(plan, 'module');
  const wxd = mod.f && mod.wx ? days(mod.wx, mod.f) : 0;
  const worst = Math.max(0, ...(plan.stages ?? []).filter(s => s.blocks_done < s.blocks).map(s => s.worst_delay_days ?? 0));
  return (
    <ClickPop content={<PlanDetail plan={plan} weather={weather} />} label={`Site progress and plan for ${plan.project_name}`}>
      <div className="flex gap-[2px]" aria-hidden>
        {STAGE_ORDER.map(k => {
          const s = st(k);
          const done = s && s.blocks_done >= s.blocks;
          return (
            <span key={k} className="h-[5px] w-[16px] overflow-hidden rounded-[1px] bg-[var(--border-subtle)]">
              <span className={`block h-full ${done ? 'bg-status-healthy-solid' : 'bg-status-ai-solid'}`} style={{ width: `${Math.min(100, s?.pct ?? 0)}%` }} />
            </span>
          );
        })}
      </div>
      <div className="mt-0.5 flex items-center gap-1.5">
        <span>Structure <b>{Math.round(structure?.pct ?? 0)}%</b> · Modules <b>{Math.round(modules?.pct ?? 0)}%</b></span>
      </div>
      <div className="flex items-center gap-1">
        {worst > 30 && <Pill tone="critical">+{worst} d</Pill>}
        {weather && wxd !== 0 && <span className={`text-[9px] font-semibold ${WX_TEXT}`}>{wxd > 0 ? `+${wxd}` : wxd} d weather</span>}
      </div>
    </ClickPop>
  );
}

function Ready({ plan, blocks, weather }: { plan: ProjectPlan; blocks: BlockPlan[]; weather: boolean }) {
  const purlin = (b: BlockPlan) => b.stages.find(s => s.key === 'purlin');
  const ready = blocks.filter(b => purlin(b)?.done);
  const coming = groupByMonth(blocks.filter(b => !purlin(b)?.done && !purlin(b)?.missing),
    b => (weather ? purlin(b)?.forecast_finish_wx : null) || purlin(b)?.forecast_finish);
  const installed = ready.filter(b => b.remaining_mwp <= 0.01);
  const content = (
    <Pop title="Blocks ready for modules" sub="Structure complete (purlin done) - the block can take modules"
      metric={`${ready.length}/${blocks.length}`} metricLabel="blocks ready"
      footer="Future months are forecasts from each block's progress and this project's pace.">
      <Section label="Ready now" right={installed.length ? `${installed.length} already have modules` : undefined}>
        {ready.length
          ? <div className="flex flex-wrap gap-1">{ready.map(b => (
              <BlockChip key={b.block} block={b.block} tone={b.remaining_mwp <= 0.01 ? 'done' : 'healthy'}
                title={b.remaining_mwp <= 0.01 ? 'Modules installed' : 'Ready - waiting for modules'}>{b.remaining_mwp <= 0.01 ? 'installed' : 'ready'}</BlockChip>))}</div>
          : <div className="text-fg-tertiary">None yet.</div>}
      </Section>
      {coming.map(([m, bs]) => (
        <Section key={m} label={groupLabel(m)} right={plural(bs.length, 'block')}>
          <div className="flex flex-wrap gap-1">
            {bs.map(b => {
              const p = purlin(b);
              return (
                <BlockChip key={b.block} block={b.block} tone="ai" title={p?.basis}>
                  {Math.round(p?.pct ?? 0)}% → {fmtDate((weather && p?.forecast_finish_wx) || p?.forecast_finish)}
                  {weather && p?.weather_days ? <span className={`ml-0.5 font-semibold ${WX_TEXT}`}>{p.weather_days > 0 ? '+' : ''}{p.weather_days}d</span> : null}
                </BlockChip>
              );
            })}
          </div>
        </Section>
      ))}
      <Suggestions items={suggestionsFor(plan).filter(s => s.topic === 'site')} max={2} />
    </Pop>
  );
  return (
    <ClickPop content={content} label="Blocks ready for modules">
      <div className="flex items-baseline gap-1"><b className="text-[11px]">{ready.length}</b><span>of {blocks.length} ready</span></div>
      <Bar pct={blocks.length ? (ready.length / blocks.length) * 100 : 0} tone={ready.length === blocks.length ? 'healthy' : 'ai'} className="my-0.5 w-[92px]" />
      <div className="text-fg-tertiary">
        {coming.slice(0, 2).map(([m, bs]) => `${groupLabel(m)} ${bs.length}`).join(' · ')}{coming.length > 2 ? ' …' : ''}
      </div>
    </ClickPop>
  );
}

function Need({ plan, blocks }: { plan: ProjectPlan; blocks: BlockPlan[] }) {
  const open = blocks.filter(b => b.remaining_mwp > 0.01);
  if (!open.length) return <span className="text-fg-tertiary">All installed</span>;
  const groups = groupByMonth(open, b => b.need_by);
  const sum = (bs: BlockPlan[]) => bs.reduce((a, b) => a + b.remaining_mwp, 0);
  const total = sum(open);
  const peak = Math.max(...groups.map(([, bs]) => sum(bs)));
  const content = (
    <Pop title="Modules needed on site" sub={`${plural(open.length, 'block')} still to receive modules, by the month they are needed`}
      metric={mw(total)} metricLabel="MWp to install"
      footer={<>Needed = 14 days before the block's forecast module installation start. <b>Now</b> = installation is running or due. Chip colour: green = covered by stock / POs, red = ordered late, purple = to be ordered.</>}>
      <div className="space-y-2.5">
        {groups.map(([m, bs]) => (
          <div key={m}>
            <div className="mb-1 grid grid-cols-[52px_1fr_64px] items-center gap-2">
              <span className={`text-[11px] font-bold ${m === 'now' ? 'text-status-critical-fg' : 'text-fg-primary'}`}>{groupLabel(m)}</span>
              <Bar pct={(sum(bs) / peak) * 100} tone={m === 'now' ? 'critical' : 'ai'} />
              <span className="text-right text-[11px] font-bold tabular-nums">{mw(sum(bs))} <span className="font-normal text-fg-tertiary">MWp</span></span>
            </div>
            <div className="ml-[60px] flex flex-wrap gap-1">
              {bs.map(b => (
                <BlockChip key={b.block} block={b.block}
                  tone={b.order_by ? (b.status === 'late' ? 'critical' : 'ai') : 'healthy'}
                  title={b.order_by ? `To order ${b.short_mwp?.toFixed(1)} MWp by ${fmtDate(b.order_by)}` : 'Covered by stock / open POs'}>
                  {b.remaining_mwp.toFixed(1)} · {fmtDate(b.need_by)}
                </BlockChip>
              ))}
            </div>
          </div>
        ))}
      </div>
      <Suggestions items={suggestionsFor(plan).filter(s => s.topic === 'order')} max={2} />
    </Pop>
  );
  return (
    <ClickPop content={content} label="Modules needed by month">
      <div className="flex flex-col items-start gap-[2px]">
        {groups.slice(0, 3).map(([m, bs]) => (
          <span key={m} className={`inline-flex w-full items-center justify-between gap-2 rounded-full border px-1.5 py-[0.5px] text-[9.5px] ${m === 'now' ? TONE.critical : TONE.ai}`}>
            <span className="font-medium">{groupLabel(m)}</span><b className="tabular-nums">{mw(sum(bs))}</b>
          </span>
        ))}
        {groups.length > 3 && <span className="text-[9.5px] text-fg-tertiary">+{groups.length - 3} more months</span>}
      </div>
    </ClickPop>
  );
}

function Order({ plan }: { plan: ProjectPlan }) {
  const s = plan.supply!;
  const st = STATUS[plan.status ?? 'covered'];
  const short = (plan.blocks ?? []).filter(b => b.order_by).sort((a, b) => (a.order_by! < b.order_by! ? -1 : 1));
  const lastArrival = short.map(b => b.arrival).filter(Boolean).sort().slice(-1)[0];
  const orderBy = plan.decision?.order_by ?? plan.first_order_by;
  const tiles: [string, number, ToneKey?][] = [
    ['Ordered', s.ordered_mwp], ['Received', s.received_mwp], ['Installed', s.erected_mwp],
    ['In yard', s.stock_mwp], ['In transit', s.in_transit_mwp], ['To order', s.short_mwp, s.short_mwp > 0.5 ? st.tone : 'healthy'],
  ];
  const content = (
    <Pop width={640} title="Order & arrival" sub={<>{plan.origin ?? 'Domestic'} modules · lead time {plan.lead_days} d · SAP / Ariba figures as on the schedule</>}
      metric={st.label}
      footer={<>Arrives = the need date when ordered on time; for a block already past its order-by date, a lead time from today. {plan.no_po && <b className="text-status-watch-fg">No module PO in SAP for this project yet.</b>}</>}>
      <div className="grid grid-cols-6 gap-1.5">
        {tiles.map(([label, v, tone]) => (
          <div key={label} className={`rounded-md border px-2 py-1.5 ${tone ? TONE[tone] : 'border-border-subtle bg-surface-sunken'}`}>
            <div className="text-[9.5px] opacity-80">{label}</div>
            <div className="text-[13px] font-bold tabular-nums">{mw(v)}</div>
          </div>
        ))}
      </div>
      {short.length > 0 && (
        <Section label="Blocks to order" right={<>first by <b>{fmtDate(orderBy)}</b><SrcTag src={plan.decision?.order_by_source} /></>}>
          <div className="overflow-hidden rounded-md border border-border-subtle">
            <table className="w-full text-[11px]">
              <thead className="bg-surface-sunken text-left text-[10px] text-fg-tertiary">
                <tr><th className="px-2 py-1 font-medium">Block</th><th className="px-2 py-1 text-right font-medium">MWp</th>
                  <th className="px-2 py-1 font-medium">Order by</th><th className="px-2 py-1 font-medium">Needed on site</th>
                  <th className="px-2 py-1 font-medium">Arrives</th><th className="px-2 py-1 font-medium">Held by</th></tr>
              </thead>
              <tbody>
                {short.slice(0, 12).map(b => {
                  const h = holding(b);
                  const hs = h ? b.stages.find(x => x.key === h) : null;
                  return (
                    <tr key={b.block} className="border-t border-border-subtle">
                      <td className="px-2 py-1 font-semibold">{b.block}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{b.short_mwp?.toFixed(1)}</td>
                      <td className="px-2 py-1" title={b.quota_reason ?? undefined}>
                        <Pill tone={b.status === 'late' ? 'critical' : b.status === 'order_now' ? 'risk' : 'neutral'}>{fmtDate(b.order_by_leveled ?? b.order_by)}</Pill>
                        {b.quota === 'delayed' && <span className="ml-1 text-[9.5px] font-semibold text-status-risk-fg">+{b.quota_shift_days} d limit</span>}
                        {b.quota === 'early' && <span className="ml-1 text-[9.5px] font-semibold text-status-watch-fg">{b.quota_shift_days} d early</span>}
                      </td>
                      <td className="px-2 py-1 tabular-nums">{fmtDate(b.need_by)}</td>
                      <td className={`px-2 py-1 tabular-nums ${(b.arrival_late_days ?? 0) > 0 ? 'font-semibold text-status-risk-fg' : ''}`}>
                        {fmtDate(b.arrival)}{(b.arrival_late_days ?? 0) > 0 ? ` (+${b.arrival_late_days} d)` : ''}
                      </td>
                      <td className="px-2 py-1 text-fg-secondary">{h ? `${STAGE_SHORT[h]} ${Math.round(hs?.pct ?? 0)}%` : '-'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {short.length > 12 && <div className="mt-1 text-fg-tertiary">+{short.length - 12} more blocks</div>}
        </Section>
      )}
      <Suggestions items={suggestionsFor(plan).filter(x => x.topic === 'order' || x.topic === 'ai')} max={3} />
    </Pop>
  );
  return (
    <ClickPop content={content} label="Order and arrival">
      <Pill tone={st.tone}>{st.label}</Pill>
      {orderBy
        ? <>
            <div className="mt-0.5 flex items-center">by <b className="ml-1">{fmtDate(orderBy)}</b><SrcTag src={plan.decision?.order_by_source} /><span className="ml-1">· {mw(s.short_mwp)}</span></div>
            {lastArrival && <div className="text-fg-tertiary">arrives {fmtDate(lastArrival)}</div>}
          </>
        : <div className="mt-0.5 text-fg-tertiary">nothing to order</div>}
    </ClickPop>
  );
}

function Impact({ plan, standard }: { plan: ProjectPlan; standard: string | null }) {
  const site = plan.decision?.order_by ?? plan.first_order_by ?? null;
  let text = '-', tone: ToneKey = 'neutral', why = '';
  const d = site && standard ? days(site, standard) : null;
  if (d != null) {
    if (Math.abs(d) <= 7) { text = 'Same timing'; why = 'The site is moving as the FTC plan assumes.'; }
    else if (d > 0) {
      text = `${d} d later`; tone = 'healthy';
      why = 'The site is behind the FTC plan, so modules ordered on the standard date would wait in the yard. Ordering later avoids idle stock.';
    } else {
      text = `${-d} d earlier`; tone = 'risk';
      why = 'Blocks will be ready sooner than the standard plan assumes. Ordering on the standard date would leave finished structures waiting for modules.';
    }
  } else if (!site && standard) { text = 'Covered'; tone = 'healthy'; why = 'Stock and open POs already cover every block the site will build.'; }
  else if (site && !standard) { text = 'New need'; tone = 'risk'; why = 'The site needs modules the standard plan has no ordering date for.'; }
  const content = (
    <Pop width={460} title="Impact vs the standard plan" sub="When to place the first module order"
      metric={d != null && Math.abs(d) > 7 ? `${d > 0 ? '+' : ''}${d} d` : text}>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="rounded-md border border-border-subtle bg-surface-sunken p-2.5">
          <div className="text-[10px] text-fg-tertiary">Standard plan</div>
          <div className="text-[14px] font-bold tabular-nums">{fmtDate(standard)}</div>
          <div className="text-[10px] text-fg-secondary">phase FTC - 45 d - lead time</div>
        </div>
        <ArrowRight className="h-4 w-4 text-fg-tertiary" aria-hidden />
        <div className={`rounded-md border p-2.5 ${TONE.ai}`}>
          <div className="text-[10px] opacity-80">Advanced plan</div>
          <div className="flex items-center text-[14px] font-bold tabular-nums">{fmtDate(site)}<SrcTag src={plan.decision?.order_by_source} /></div>
          <div className="text-[10px] opacity-80">{plan.decision?.order_by_source === 'ai' ? 'AI model' : 'each block\'s need - lead time'}</div>
        </div>
      </div>
      {why && <div className="flex items-start gap-2"><Pill tone={tone}>{text}</Pill><span className="text-fg-secondary">{why}</span></div>}
    </Pop>
  );
  return <ClickPop content={content} label="Impact vs standard plan"><Pill tone={tone}>{d != null && Math.abs(d) > 7 ? `Order ${text}` : text}</Pill></ClickPop>;
}

function FtcRisk({ plan, weather }: { plan: ProjectPlan; weather: boolean }) {
  const phases: PhasePlan[] = plan.phases ?? [];
  const open = phases.filter(p => !p.charged);
  const risk = open.filter(p => p.at_risk);
  if (!phases.length) return <span className="text-fg-tertiary">No FTC milestone</span>;
  if (!open.length) return <Pill tone="done">All charged</Pill>;
  const content = (
    <Pop width={620} title="FTC phases" sub="P6 FTC date against the site forecast, phase by phase"
      metric={`${risk.length}/${open.length}`} metricLabel="open phases at risk"
      footer="Forecast FTC = the phase's last block: modules installed + the gap to charging finished blocks show (median 4 d), plus any wait for late modules. Estimates.">
      <div className="space-y-2">
        {phases.map(ph => {
          const slip = ph.slip_days ?? 0;
          const tone: ToneKey = ph.charged ? 'done' : slip > 30 ? 'critical' : slip > 0 ? 'risk' : 'healthy';
          return (
            <div key={ph.index} className="rounded-md border border-border-subtle p-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-fg-primary">{ph.name.replace(/First Time Charging\s*-?\s*/i, '') || ph.name}
                  <span className="ml-1.5 font-normal text-fg-tertiary">{plural(ph.blocks.length, 'block')} · {mw(ph.mwp)} MWp</span></span>
                <Pill tone={tone}>{ph.charged ? 'Charged' : slip > 0 ? `+${slip} d late` : 'On track'}</Pill>
              </div>
              {!ph.charged && (
                <div className="mt-1.5 grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-[11px]">
                  <div><div className="text-[10px] text-fg-tertiary">P6 FTC</div><b className="tabular-nums">{fmtDate(ph.ftc)}</b></div>
                  <ArrowRight className="h-3.5 w-3.5 text-fg-tertiary" aria-hidden />
                  <div><div className="text-[10px] text-fg-tertiary">Forecast FTC</div>
                    <b className="tabular-nums"><DateWx base={ph.ftc_forecast} wx={ph.ftc_forecast_wx} show={weather} /></b></div>
                </div>
              )}
              {!ph.charged && ph.late_blocks.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {ph.late_blocks.slice(0, 10).map(l => (
                    <BlockChip key={l.block} block={l.block} tone="risk" title={`Modules done ${fmtDate(l.modules_done)}`}>
                      {l.holding_stage ? l.holding_stage.toLowerCase() : 'late'}
                    </BlockChip>
                  ))}
                  {ph.late_blocks.length > 10 && <span className="text-fg-tertiary">+{ph.late_blocks.length - 10}</span>}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <Suggestions items={suggestionsFor(plan).filter(s => s.topic === 'ftc' || s.topic === 'site')} max={3} />
    </Pop>
  );
  return (
    <ClickPop content={content} label="FTC risk">
      {risk.length ? <Pill tone="risk">{risk.length} of {open.length} at risk</Pill> : <Pill tone="healthy">{open.length} on track</Pill>}
    </ClickPop>
  );
}

/* ── The schedule's own columns, AI figure added ───────────────────────── */

/** "✦ ..." line under a standard value. */
export function AiLine({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <div className={`mt-0.5 border-t border-dashed border-[var(--status-ai-border)] pt-0.5 text-[9.5px] font-semibold ${AI_TEXT}`} title={title}>
      ✦ {children}
    </div>
  );
}

/** FTC Date column: forecast FTC per open phase. */
export function AiFtcLine({ plan, weather }: { plan?: ProjectPlan; weather: boolean }) {
  if (!plan?.plannable) return null;
  const open = (plan.phases ?? []).filter(p => !p.charged && p.ftc_forecast);
  if (!open.length) return null;
  const d = plan.decision;
  return (
    <AiLine title={d?.source}>
      {open.slice(0, 3).map((ph, i) => (
        <div key={ph.index}>
          {i === 0 && d?.ftc_source === 'ai' && d.ftc
            ? <>fc {fmtDate(d.ftc)}<SrcTag src="ai" /></>
            : <>fc {fmtDate(ph.ftc_forecast)}{(ph.slip_days ?? 0) > 0 && <span className="text-status-risk-fg"> +{ph.slip_days}d</span>}</>}
          <WxDelta d={ph.ftc_forecast && ph.ftc_forecast_wx ? days(ph.ftc_forecast_wx, ph.ftc_forecast) : 0} show={weather} />
        </div>
      ))}
      {open.length > 3 && <div>+{open.length - 3} phases</div>}
    </AiLine>
  );
}

/** Module Ordering Date column: the advanced plan's order-by. */
export function AiOrderLine({ plan }: { plan?: ProjectPlan }) {
  if (!plan?.plannable) return null;
  const d = plan.decision;
  const v = d ? d.order_by : plan.first_order_by;
  return <AiLine title={d?.source}>{v ? <>order by {fmtDate(v)}<SrcTag src={d?.order_by_source} /></> : 'covered'}</AiLine>;
}

/** TC Delivery Date column: modules needed on site from. */
export function AiTcLine({ plan }: { plan?: ProjectPlan }) {
  if (!plan?.plannable) return null;
  const d = plan.decision;
  const first = d ? d.tc : (plan.blocks ?? []).filter(b => b.remaining_mwp > 0.01).map(b => b.need_by).filter(Boolean).sort()[0];
  return <AiLine title={d?.source}>{first ? <>on site from {fmtDate(first)}<SrcTag src={d?.tc_source} /></> : 'all installed'}</AiLine>;
}

/** LTA / SCOD: the project's last FTC - forecast, or the actual date once
    every phase is charged - against the date in the cell. */
export function AiDeadlineLine({ plan, deadline, label, weather }: {
  plan?: ProjectPlan; deadline?: string | null; label: 'LTA' | 'SCOD'; weather: boolean;
}) {
  if (!plan?.plannable || !plan.completion_forecast) return null;
  const phases = plan.phases ?? [];
  if (phases.length > 0 && phases.every(p => p.charged)) {
    return <AiLine title="Every FTC phase of the project is charged (actual date)">Charged {fmtDate(plan.completion_forecast)}</AiLine>;
  }
  const dl = toIso(deadline);
  const wxOn = weather && plan.completion_forecast_wx && plan.completion_forecast_wx !== plan.completion_forecast;
  const fc = wxOn ? plan.completion_forecast_wx! : plan.completion_forecast;
  const d = dl ? days(fc, dl) : null;
  return (
    <AiLine title={`Forecast of the project's last FTC${dl ? `, compared with the ${label}` : ''}${wxOn ? ' - with weather' : ''}`}>
      FTC forecast {fmtDate(fc)}
      {wxOn && <span className={`ml-1 ${WX_TEXT}`}>(weather)</span>}
      {d != null && (
        <div className={d > 0 ? 'text-status-critical-fg' : 'text-status-healthy-fg'}>
          {d === 0 ? `on the ${label} date` : d > 0 ? `${d} d after ${label}` : `${-d} d before ${label}`}
        </div>
      )}
    </AiLine>
  );
}

/* ── Month-wise plan, site-driven ──────────────────────────────────────── */
export interface AiMonth {
  /** Modules ordered this month (MWp, after the vendor limit) - the blue chip. */
  mwp: number; overdue: boolean; blocks: BlockPlan[]; parts: Map<string, number>; month: string;
  /** Modules landing on site this month - the orange chip. */
  tcMwp: number; tcBlocks: BlockPlan[];
  /** Blocks reaching FTC this month (their MWp) - the green chip. */
  ftcMwp: number; ftcBlocks: BlockPlan[];
}

/** Per schedule month ("Oct-26"), this row's share: what is ordered (after the
    vendor monthly limit), what lands on site, and what reaches FTC. */
export function aiMonths(plan: ProjectPlan | undefined, share: number): Map<string, AiMonth> {
  const out = new Map<string, AiMonth>();
  if (!plan?.plannable) return out;
  const today = todayIso();
  const at = (iso: string) => {
    const d = iso < today ? today : iso;          // a date already passed counts now
    const label = monthLabelOf(d);
    let e = out.get(label);
    if (!e) {
      e = { mwp: 0, overdue: false, blocks: [], parts: new Map(), month: d.slice(0, 7), tcMwp: 0, tcBlocks: [], ftcMwp: 0, ftcBlocks: [] };
      out.set(label, e);
    }
    return e;
  };
  (plan.blocks ?? []).forEach(b => {
    if (b.order_by && b.short_mwp) {
      const late = b.order_by < today;
      const allocs = b.allocations?.length ? b.allocations
        : [{ month: (late ? today : b.order_by).slice(0, 7), mwp: b.short_mwp, mwac: 0 }];
      allocs.forEach(a => {
        const e = at(`${a.month}-01` < today.slice(0, 7) + '-01' ? today : `${a.month}-15`);
        e.mwp += a.mwp * share;
        e.overdue = e.overdue || late;
        if (!e.parts.has(b.block)) e.blocks.push(b);
        e.parts.set(b.block, (e.parts.get(b.block) ?? 0) + a.mwp);
      });
    }
    if (b.remaining_mwp > 0.01) {
      const onSite = (b.arrival_late_days ?? 0) > 0 ? b.arrival : b.need_by;
      if (onSite) { const e = at(onSite); e.tcMwp += b.remaining_mwp * share; e.tcBlocks.push(b); }
      if (b.ftc_forecast && !b.ftc_actual) { const e = at(b.ftc_forecast); e.ftcMwp += b.remaining_mwp * share; e.ftcBlocks.push(b); }
    }
  });
  return out;
}

/** The schedule row a month cell sits in - what the standard panel shows too. */
export interface MonthRowInfo {
  name: string; capacityMwp: number; capacityMwac?: number | null; lta?: string | null; balanceMwp: number;
}

const addDays = (iso: string, n: number) => new Date(Date.parse(iso) + n * 86400000).toISOString().slice(0, 10);

/** One milestone chip, the standard panel's shape: the new date leads, the
    original sits under it with the shift. A new date already past is "Today". */
function MilestoneChip({ title, cls, nu, nuEnd, orig, src, qty, label, pastIsToday = true, note }: {
  title: string; cls: { text: string; border: string; bg: string }; nu?: string | null; nuEnd?: string | null; orig?: string | null;
  src?: 'ai' | 'engine'; qty?: string; label?: string; pastIsToday?: boolean; note?: React.ReactNode;
}) {
  const today = todayIso();
  const past = !!nu && nu < today && pastIsToday;
  const shown = past ? today : nu;
  const end = nuEnd && nuEnd !== nu && !(pastIsToday && nuEnd < today) ? nuEnd : null;
  const shift = shown && orig ? days(shown, orig) : null;
  return (
    <div className={`flex h-full flex-col rounded-md border px-1.5 py-1 ${cls.border} ${cls.bg}`} title={title}>
      <div className="flex items-baseline justify-between gap-1.5">
        {label ? <span className={`text-[9px] font-semibold ${cls.text}`}>{label}</span> : <span />}
        {qty && <span className="font-mono text-[9px] tabular-nums text-fg-tertiary">{qty}</span>}
      </div>
      <div className={`flex items-center font-mono text-[10.5px] font-bold tabular-nums ${cls.text}`}>
        {past ? 'Today' : fmtDate(shown)}{end && <span className="font-semibold opacity-80">&nbsp;– {fmtDate(end)}</span>}<SrcTag src={src} />
      </div>
      {past && <div className="text-[9px] font-bold leading-tight text-status-critical-fg">was due {fmtDate(nu)} - overdue</div>}
      {note}
      <div className="mt-0.5 text-[9px] leading-tight text-fg-tertiary">
        Original: <span className="font-mono tabular-nums">{fmtDate(orig)}</span>
        {shift != null && shift !== 0 && (
          <span className={`ml-1 font-bold ${shift > 0 ? 'text-status-risk-fg' : 'text-status-healthy-fg'}`}>{shift > 0 ? '+' : ''}{shift} d</span>
        )}
      </div>
    </div>
  );
}

/* The standard schedule's chip colours: ordering blue, TC orange, FTC green. */
const CHIP = {
  module: 'bg-primary/20 text-primary border border-primary/30',
  tc: 'bg-status-risk-bg text-status-risk-fg border border-status-risk-border',
  ftc: 'bg-status-healthy-bg text-status-healthy-fg border border-status-healthy-border',
};

export function AiMonthCell({ entry, standard, first, unitToggle, ol, Td, mo, plan, row, quota, milestone = 'all' }: {
  entry?: AiMonth; standard: number; first: boolean; unitToggle: 'both' | 'mwp' | 'mwac'; ol: number; Td: TdComp; mo: string;
  plan?: ProjectPlan; row?: MonthRowInfo; quota?: QuotaUse; milestone?: 'all' | 'module' | 'tc' | 'ftc';
}) {
  const [deep, setDeep] = useState(false);
  const edge = first ? 'border-l border-border' : '';
  const olv = ol > 0 ? ol : 1.35;
  const fmtQty = (mwp: number) => unitToggle === 'mwp' ? mw(mwp) : unitToggle === 'mwac' ? mw(mwp / olv) : `${mw(mwp)} / ${mw(mwp / olv)}`;
  const show = (k: 'module' | 'tc' | 'ftc') => milestone === 'all' || milestone === k;
  const chips: { type: 'module' | 'tc' | 'ftc'; mwp: number; title: string }[] = [];
  if (entry && entry.mwp >= 0.5 && show('module')) chips.push({ type: 'module', mwp: entry.mwp, title: 'Modules ordered this month (site-driven, within the vendor limit)' });
  if (entry && entry.tcMwp >= 0.5 && show('tc')) chips.push({ type: 'tc', mwp: entry.tcMwp, title: 'Modules on site this month (TC)' });
  if (entry && entry.ftcMwp >= 0.5 && show('ftc')) chips.push({ type: 'ftc', mwp: entry.ftcMwp, title: 'Blocks reaching FTC this month (forecast)' });
  if (!entry || !chips.length) {
    return <Td className={`${TD_AI} ${edge} text-fg-tertiary/50`}>{standard > 0.5 ? <span title={`Standard plan: ${mw(standard)} MWp`}>-</span> : '-'}</Td>;
  }
  const qtyOf = (mwp: number) => unitToggle === 'mwac' ? `${mw(mwp / olv)} MWac` : unitToggle === 'mwp' ? `${mw(mwp)} MWp` : `${mw(mwp)} MWp / ${mw(mwp / olv)} MWac`;
  const lead = plan?.lead_days ?? 98;
  const phases = plan?.phases ?? [];

  // Blocks sharing the same dates read as one line, as the standard panel's phases do.
  type Row = { blocks: string[]; mwp: number; order?: string | null; tc?: string | null; ftc?: string | null;
               origFtc?: string | null; phase?: string; late: boolean; quota?: string; shift?: number; reason?: string | null;
               parts?: BlockPlan['ftc_parts']; orderEnd?: string | null; tcEnd?: string | null; ftcEnd?: string | null;
               phaseRow?: boolean };
  const rows = new Map<string, Row>();
  const touched = [...new Map([...entry.blocks, ...entry.tcBlocks, ...entry.ftcBlocks].map(b => [b.block, b])).values()];
  touched.forEach(b => {
    const ph = b.phase != null ? phases[b.phase] : undefined;
    const tc = (b.arrival_late_days ?? 0) > 0 ? b.arrival : b.need_by;
    const order = b.order_by_leveled ?? b.order_by;
    const key = [order, tc, b.ftc_forecast, b.phase, b.quota].join('|');
    const r = rows.get(key) ?? { blocks: [], mwp: 0, order, tc, ftc: b.ftc_forecast, origFtc: ph?.ftc,
                                 phase: ph?.name.replace(/First Time Charging\s*-?\s*/i, ''), late: !!b.order_by && b.order_by < todayIso(),
                                 quota: b.quota, shift: b.quota_shift_days, reason: b.quota_reason, parts: b.ftc_parts };
    r.blocks.push(b.block);
    r.mwp += entry.parts.get(b.block) ?? b.remaining_mwp ?? 0;
    rows.set(key, r);
  });
  const list = [...rows.values()].sort((a, b) => (a.order ?? '').localeCompare(b.order ?? ''));
  const byPhase = new Map<string, Row>();
  touched.forEach(b => {
    const ph = b.phase != null ? phases[b.phase] : undefined;
    const k = String(b.phase ?? 'none');
    const tc = (b.arrival_late_days ?? 0) > 0 ? b.arrival : b.need_by;
    const order = b.order_by_leveled ?? b.order_by;
    const r = byPhase.get(k) ?? { blocks: [], mwp: 0, origFtc: ph?.ftc, phaseRow: true, late: false,
      phase: ph?.name.replace(/First Time Charging\s*-?\s*/i, '') || undefined } as Row;
    const lo = (a?: string | null, v?: string | null) => (!v ? a : !a || v < a ? v : a);
    const hi = (a?: string | null, v?: string | null) => (!v ? a : !a || v > a ? v : a);
    r.blocks.push(b.block);
    r.mwp += entry.parts.get(b.block) ?? b.remaining_mwp ?? 0;
    r.order = lo(r.order, order); r.orderEnd = hi(r.orderEnd, order);
    r.tc = lo(r.tc, tc); r.tcEnd = hi(r.tcEnd, tc);
    r.ftc = lo(r.ftc, b.ftc_forecast); r.ftcEnd = hi(r.ftcEnd, b.ftc_forecast);
    if (b.quota === 'delayed') { r.quota = 'delayed'; r.shift = Math.max(r.shift ?? 0, b.quota_shift_days ?? 0); }
    byPhase.set(k, r);
  });
  const phaseList = [...byPhase.values()].sort((a, b) => (a.order ?? '').localeCompare(b.order ?? ''));
  const ltaIso = toIso(row?.lta);
  const ORDER = { text: 'text-primary', border: 'border-primary/30', bg: 'bg-primary/[0.07]' };
  const TC = { text: 'text-status-risk-fg', border: 'border-status-risk-border', bg: 'bg-status-risk-bg/60' };
  const FTC = { text: 'text-status-healthy-fg', border: 'border-status-healthy-border', bg: 'bg-status-healthy-bg/60' };
  const LTA = { text: 'text-status-ai-fg', border: 'border-status-ai-border', bg: 'bg-status-ai-bg/60' };
  const cols = ltaIso ? 'minmax(118px,1fr) 44px minmax(118px,1fr) 64px minmax(118px,1fr) 8px minmax(96px,0.8fr)'
    : 'minmax(118px,1fr) 44px minmax(118px,1fr) 64px minmax(118px,1fr)';
  const Gap = ({ text, sub, title }: { text: string; sub?: string; title?: string }) => (
    <div className="flex flex-col items-center justify-center text-center text-fg-tertiary" title={title}>
      <ArrowRight className="h-3 w-3" aria-hidden />
      <span className="whitespace-nowrap text-[8.5px] font-semibold">{text}</span>
      {sub && <span className="whitespace-nowrap text-[8px] leading-tight">{sub}</span>}
    </div>
  );
  /** On site -> FTC, and what fills the gap. */
  const toFtc = (r: Row) => {
    if (!r.tc || !r.ftc) return { text: 'to FTC' };
    const total = Math.max(0, days(r.ftc, r.tc));
    const p = r.parts;
    if (!p) return { text: `${total} d to FTC` };
    const RECEIPT = 14;     // on site before installation starts: unloading, receipt, inspection
    const wait = p.modules_done ? Math.max(0, days(p.modules_done, r.tc) - RECEIPT - p.install_days) : 0;
    const site = p.held_by === 'site progress' && wait > 0;
    return {
      text: `${total} d to FTC`,
      sub: site ? 'waits for structure' : `${RECEIPT} receipt + ${p.install_days} install`,
      title: [`Modules on site ${fmtDate(r.tc)} -> FTC ${fmtDate(r.ftc)}: ${total} d (standard rule: 45 d)`,
        `receipt & inspection ${RECEIPT} d`,
        site ? `waiting for the structure ~${wait} d, installation running inside it (modules done ${fmtDate(p.modules_done)})`
             : `module installation ${p.install_days} d, as planned in P6 (modules done ${fmtDate(p.modules_done)})`,
        `charging after modules ${p.charge_gap_days} d (median of finished blocks)`,
        `held by: ${p.held_by}`].join('\n'),
    };
  };

  const panel = (list: Row[], full: boolean) => (
    <div className="space-y-2.5">
      <div>
        <div className="flex items-center justify-between gap-2">
          <div className="text-[12px] font-semibold text-fg-primary">{row?.name ?? plan?.project_name}</div>
          {row && <div className="font-mono text-[10px] text-fg-tertiary">
            Project Total: <span className="font-bold text-fg-primary">{mw(row.capacityMwp)} MWp</span>{row.capacityMwac ? ` (${row.capacityMwac} MWac)` : ''}
          </div>}
        </div>
        <div className={`mt-0.5 text-[10px] font-semibold ${AI_TEXT}`}>✦ Advanced plan - site-driven, against the original (standard) plan</div>
      </div>

      <div className="space-y-1.5 border-t border-border-subtle pt-2">
        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
          <div className="flex items-center gap-1.5">
            <span className="font-medium text-fg-tertiary">{entry.mwp >= 0.5 ? 'Planned Order:' : 'Milestone Target:'}</span>
            {entry.mwp >= 0.5
              ? <span className={`inline-flex items-center rounded border px-2 py-0.5 font-mono font-bold ${entry.overdue ? 'border-status-critical-solid bg-status-critical-bg text-status-critical-fg' : TONE.ai}`}>
                  {qtyOf(entry.mwp)} · {mo}
                </span>
              : <span className="inline-flex items-center gap-1 font-mono font-bold">
                  {entry.tcMwp >= 0.5 && <span className={`rounded px-1.5 py-0.5 ${CHIP.tc}`}>TC {qtyOf(entry.tcMwp)}</span>}
                  {entry.ftcMwp >= 0.5 && <span className={`rounded px-1.5 py-0.5 ${CHIP.ftc}`}>FTC {qtyOf(entry.ftcMwp)}</span>}
                  <span className="text-fg-tertiary">· {mo}</span>
                </span>}
            <span className="text-[10px] text-fg-tertiary">original this month: <b className="text-fg-secondary">{standard > 0.5 ? `${mw(standard)} MWp` : 'nothing'}</b></span>
          </div>
          {row && <div className="font-mono text-[10px] text-fg-tertiary">
            Balance to Order: <span className={`font-semibold ${row.balanceMwp > 0 ? 'text-status-risk-fg' : 'text-status-healthy-fg'}`}>{mw(row.balanceMwp)} MWp</span>
          </div>}
        </div>
        {plan?.quota_source && quota && (() => {
          const lim = quota.limits_mwac[plan.quota_source] ?? quota.limits_mwac['Origin not set'];
          const used = quota.used_mwac[plan.quota_source]?.[entry.month] ?? 0;
          const pct = lim ? (used / lim) * 100 : 0;
          return (
            <div className="flex items-center gap-2 text-[10px] text-fg-tertiary">
              <span className="whitespace-nowrap">{plan.quota_source} vendor limit {mo}:</span>
              <Bar pct={pct} tone={pct >= 99.5 ? 'risk' : 'ai'} className="w-28" />
              <span className="whitespace-nowrap font-mono"><b className="text-fg-primary">{mw(used)}</b> of {mw(lim ?? 0)} MWac used, all projects</span>
            </div>
          );
        })()}
        {entry.overdue && (
          <div className="text-[10.5px] leading-relaxed text-status-critical-fg">
            Some blocks are past their order-by date - they show <b>Today</b> and are counted in {mo}, the earliest month still open.
          </div>
        )}
      </div>

      <div className="border-t border-border-subtle pt-2">
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-fg-tertiary">
            {entry.mwp >= 0.5 ? 'Ordering in' : 'Milestone dates for'} {mo} · {full ? plural(list.length, 'group') + ' of blocks' : plural(list.length, 'phase')}
          </span>
          {entry.mwp >= 0.5 && <span className="font-mono text-[10px] text-fg-secondary">taking <b className="text-fg-primary">{qtyOf(entry.mwp)}</b></span>}
        </div>
        <div className="grid w-full items-stretch gap-x-1 gap-y-1.5" style={{ gridTemplateColumns: cols }}>
          <div className="text-[9.5px] font-semibold uppercase tracking-wide text-primary">Module Ordering</div><div />
          <div className="text-[9.5px] font-semibold uppercase tracking-wide text-status-risk-fg">TC Delivery</div><div />
          <div className="text-[9.5px] font-semibold uppercase tracking-wide text-status-healthy-fg">FTC Date</div>
          {ltaIso && <><div /><div className="text-[9.5px] font-semibold uppercase tracking-wide text-status-ai-fg">LTA Date</div></>}
          {list.map((r, i) => {
            const origTc = r.origFtc ? addDays(r.origFtc, -45) : null;
            const origOrder = origTc ? addDays(origTc, -lead) : null;
            const blk = r.blocks.length === 1 ? `Blk ${r.blocks[0]}` : `Blks ${r.blocks.slice(0, 6).join(', ')}${r.blocks.length > 6 ? '…' : ''}`;
            const lbl = r.phaseRow ? `${r.phase ?? 'Blocks'} · ${plural(r.blocks.length, 'blk')}` : r.phase ? `${blk} · ${r.phase}` : blk;
            return (
              <React.Fragment key={i}>
                <MilestoneChip title={r.reason ?? 'Order by: modules needed on site minus the lead time, within the vendor monthly limit'}
                  cls={ORDER} nu={r.order} nuEnd={r.orderEnd} orig={origOrder}
                  src={plan?.decision?.order_by_source === 'ai' && i === 0 ? 'ai' : undefined} qty={qtyOf(r.mwp)} label={lbl}
                  note={r.quota === 'delayed'
                    ? <div className="text-[9px] font-bold leading-tight text-status-risk-fg">vendor limit +{r.shift} d</div>
                    : r.quota === 'early'
                      ? <div className="text-[9px] font-bold leading-tight text-status-watch-fg">pulled {-(r.shift ?? 0)} d earlier (limit)</div>
                      : null} />
                <Gap text={`${lead}d lead`} />
                <MilestoneChip title="Modules on site: 14 days before the blocks' forecast module installation (or when they land, if ordered late)"
                  cls={TC} nu={r.tc} nuEnd={r.tcEnd} orig={origTc} label={lbl} />
                <Gap {...toFtc(r)} />
                <MilestoneChip title="Forecast FTC of these blocks: modules installed + the gap to charging" cls={FTC}
                  nu={r.ftc} nuEnd={r.ftcEnd} orig={r.origFtc} label={lbl} pastIsToday={false} />
                {ltaIso && <><div /><div className={`flex h-full flex-col justify-center rounded-md border px-1.5 py-1 ${LTA.border} ${LTA.bg}`}>
                  <div className={`font-mono text-[10.5px] font-bold tabular-nums ${LTA.text}`}>{fmtDate(ltaIso)}</div>
                  {r.ftc && <div className={`text-[9px] font-bold ${days(r.ftc, ltaIso) > 0 ? 'text-status-critical-fg' : 'text-status-healthy-fg'}`}>
                    FTC {days(r.ftc, ltaIso) > 0 ? `${days(r.ftc, ltaIso)} d after` : `${-days(r.ftc, ltaIso)} d before`}
                  </div>}
                </div></>}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {full && (<>
      {/* The reasoning, in words, for every group - not hidden in a hover. */}
      <div className="rounded-lg border border-border-subtle bg-surface-sunken p-2.5">
        <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold text-fg-primary">
          <Info className="h-3.5 w-3.5 text-fg-tertiary" strokeWidth={2} /> Why these dates
        </div>
        <ul className="space-y-1.5">
          {list.map((r, i) => {
            const blk = r.blocks.length === 1 ? `Blk ${r.blocks[0]}` : `Blks ${r.blocks.slice(0, 6).join(', ')}${r.blocks.length > 6 ? '…' : ''}`;
            const today = todayIso();
            const overdue = !!r.order && r.order < today;
            const total = r.tc && r.ftc ? Math.max(0, days(r.ftc, r.tc)) : null;
            const p = r.parts;
            const RECEIPT = 14;
            const wait = p?.modules_done && r.tc ? Math.max(0, days(p.modules_done, r.tc) - RECEIPT - p.install_days) : 0;
            const lateMods = p?.held_by === 'modules arriving late';
            return (
              <li key={i} className="text-[10.5px] leading-snug text-fg-secondary">
                <b className="text-fg-primary">{blk}:</b>{' '}
                {overdue
                  ? <>order <b className="text-status-critical-fg">today</b> (was due {fmtDate(r.order)} - overdue)</>
                  : <>order by <b className="text-fg-primary">{fmtDate(r.order)}</b></>}
                {r.quota === 'delayed' && <> - moved {r.shift} d later because the {plan?.quota_source} vendor limit is full</>}
                {r.quota === 'early' && <> - moved {-(r.shift ?? 0)} d earlier to fit the {plan?.quota_source} vendor limit</>}
                {' '}→ on site <b className="text-fg-primary">{fmtDate(r.tc)}</b> after the {lead} d lead
                {' '}→ FTC <b className="text-fg-primary">{fmtDate(r.ftc)}</b>.
                {total != null && p && <>
                  {' '}That is <b className="text-fg-primary">{total} d</b> from on site to FTC:
                  {' '}{RECEIPT} d receipt & inspection + {p.install_days} d installation{wait > 0 && <> + {wait} d waiting for the structure</>} + {p.charge_gap_days} d to charge
                  {' '}<span className="text-fg-tertiary">(the standard plan assumes 45 d)</span>.
                </>}
                {lateMods && <> Modules reach site after the blocks need them, so the late order sets the FTC.</>}
                {p?.held_by === 'site progress' && wait > 0 && <> The structure is not ready before then, so the order date is not what holds the FTC.</>}
              </li>
            );
          })}
        </ul>
      </div>
      </>)}
      {!full && (
        <button type="button" onClick={() => setDeep(true)}
          className="flex w-full items-center justify-center gap-1 rounded-md border border-[var(--status-ai-border)] bg-[var(--status-ai-bg)] py-1.5 text-[11px] font-semibold text-status-ai-fg transition-colors hover:bg-[var(--status-ai-border)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--status-ai-solid)]">
          Deep dive - every block and why <ChevronRight className="h-3.5 w-3.5" aria-hidden />
        </button>
      )}

      <div className="border-t border-border-subtle pt-2 text-[10px] leading-snug text-fg-tertiary">
        Headline = the advanced plan's date, inside the {plan?.quota_source ?? 'origin'} vendor monthly limit (PPA first, then P1 / P2 / standard; a full month moves an order earlier, and later only when every earlier month is full).
        {' '}<b>Original</b> = the standard plan for the blocks' FTC phase (P6 FTC, TC = FTC - 45 d, order = TC - {lead} d lead).
        A date already passed shows <b>Today</b>. Figures are project level, shared across this project's rows by capacity.
      </div>
    </div>
  );
  const detail = panel(list, true);
  const content = <div className="w-[720px] max-w-full p-3.5">{panel(phaseList, false)}</div>;

  return (
    <Td className={`${TD_AI} ${edge}`}>
      {deep && createPortal(
        // Above the click panel it was opened from (that panel sits at z 9999).
        <div className="relative z-[10000]"><Dialog open size="lg" onClose={() => setDeep(false)}
          title={<span className={AI_TEXT}>✦ {row?.name ?? plan?.project_name} · {mo}</span>}
          description="Advanced plan, block by block, against the original (standard) plan">
          <div className="max-h-[70vh] overflow-auto custom-scrollbar text-left">{detail}</div>
        </Dialog></div>,
        document.body,
      )}
      <ClickPop content={content} label={`${mo} site-driven milestones`}>
        <div className="flex w-full flex-col items-end gap-1">
          {chips.map(c => {
            const [a, b] = fmtQty(c.mwp).split(' / ');
            return (
              <div key={c.type} title={c.title}
                className={`relative flex max-w-full items-center overflow-hidden whitespace-nowrap rounded px-1.5 py-[2px] font-bold shadow-sm ${CHIP[c.type]}`}>
                {c.type === 'module' && entry.overdue && <span className="mr-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-status-critical-solid" aria-label="overdue" />}
                <span className="text-[11px] font-extrabold tracking-tight tabular-nums">
                  {a}{b && <><span className="mx-px font-semibold opacity-40">/</span><span className="text-[10px] font-bold opacity-80">{b}</span></>}
                </span>
              </div>
            );
          })}
        </div>
      </ClickPop>
    </Td>
  );
}
