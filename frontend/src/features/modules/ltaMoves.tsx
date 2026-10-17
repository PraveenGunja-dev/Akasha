/* The old plan and the revised plan, side by side on the Ordering Schedule.

   Two things move an order:
     - a plan version (services/plan_versions.py): the plan was saved again
       because something changed - the project's own dates, or another
       project's change freeing / taking vendor quota. `plan_change` holds
       the old plan, which is never edited, and why it was replaced;
     - a late LTA (services/module_planner.py, _lta_alignment): the order was
       placed later, so the plan WITHOUT that move (`lta_base`) is the old one.

   Either way a month shows one of three things:
     - OLD plan, not active: a month the revised plan emptied keeps its order
       as it was, dotted, with a line and an arrow to where it went (the arrow
       points left when an order was pulled earlier);
     - REVISED plan, active: a month that gained MWp carries a marker - the AI
       diamond for an LTA move, a triangle for a plan change (solid ring: the
       project's own dates changed; dashed ring: another project's change
       moved it) - and says where it came from and the window to order in;
     - nothing: a month the arrow crosses stays empty.

   Used by the live Ordering Schedule and the Beta. */
import { useLayoutEffect, useRef, useState } from 'react';

export interface LtaMoveInfo {
  from_month: string; to_month: string; to_in_view: boolean;
  p6_order_date: string; new_order_date: string;
  p6_tc_date: string; new_tc_date: string;
  p6_ftc_date: string; new_ftc_date: string;
  lta_date: string; basis: string; basis_date: string; days_late: number;
}
export interface PlanCause { project: string; field: string; from?: unknown; to?: unknown; by?: string | null }
export interface PlanChange {
  version: number; at: string; own: boolean;
  previous: Record<string, number>;
  previous_phases: Record<string, PhaseRec[]>;
  because: PlanCause[];
}
interface PhaseRec { phase_label: string; mwp: number; overdue?: boolean; order_date?: string; ftc_date?: string; lta_move?: LtaMoveInfo }
interface Movable {
  month_mwp?: Record<string, number>;
  month_phases?: Record<string, PhaseRec[]>;
  lta_moves?: Array<LtaMoveInfo & { phase_label: string; mwp: number }>;
  lta_base?: { month_mwp: Record<string, number>; month_overdue_mwp: Record<string, number>; month_phases: Record<string, PhaseRec[]> };
  plan_change?: PlanChange | null;
}

export interface LtaCell {
  kind: 'plan' | 'lta' | '';
  /** This month held an order the revised plan moved away and holds nothing now: show it as it was (old plan, not active). */
  original: boolean;
  originalMwp: number;
  originalOverdue: number;
  originalPhases: PhaseRec[];
  /** MWp the revised plan added to this month. */
  movedIn: number;
  /** MWp this month held in the old plan (a month that only grew still says what it was). */
  was: number;
  /** An arrow passes through this month: show it empty rather than "-". */
  underArrow: boolean;
  /** From an old-plan month: how many columns to the revised one, which way, and whether that is beyond the months shown. */
  steps: number; dir: 1 | -1; beyond: boolean; to: string;
  move?: LtaMoveInfo;
  change?: PlanChange;
}

const NONE: LtaCell = { kind: '', original: false, originalMwp: 0, originalOverdue: 0, originalPhases: [], movedIn: 0, was: 0, underArrow: false, steps: 0, dir: 1, beyond: false, to: '' };
const TOL = 0.15;
const sum = (xs: PhaseRec[]) => xs.reduce((a, x) => a + (x.mwp || 0), 0);

interface Base { kind: 'plan' | 'lta'; months: Record<string, number>; phases: Record<string, PhaseRec[]>; overdue: Record<string, number> }

function baseOf(p: Movable): Base | null {
  if (p.plan_change) return { kind: 'plan', months: p.plan_change.previous, phases: p.plan_change.previous_phases ?? {}, overdue: {} };
  if (p.lta_base && p.lta_moves?.length) return { kind: 'lta', months: p.lta_base.month_mwp, phases: p.lta_base.month_phases, overdue: p.lta_base.month_overdue_mwp };
  return null;
}

function originalAt(p: Movable, b: Base, mo: string): PhaseRec[] {
  const rows = b.phases?.[mo] ?? [];
  if (b.kind === 'plan') return rows;
  const moved = new Set((p.lta_moves ?? []).map(m => m.phase_label));
  return rows.filter(x => moved.has(x.phase_label));
}

const isOriginal = (p: Movable, b: Base, mo: string) =>
  (p.month_mwp?.[mo] || 0) <= 0.05 && (b.kind === 'plan' ? (b.months[mo] || 0) : sum(originalAt(p, b, mo))) > 0.05;

function grewBy(p: Movable, b: Base, mo: string): number {
  if (b.kind === 'plan') return Math.max(0, (p.month_mwp?.[mo] || 0) - (b.months[mo] || 0));
  return sum((p.month_phases?.[mo] ?? []).filter(x => x.lta_move));
}

/** Where the arrow from original month i ends. A plan change: the nearest month that grew, either side. An LTA
 *  move: the next original month (so several chain instead of one running through another's chip), else the
 *  next month that gained, else - it went past the months shown - the last month. */
function destination(p: Movable, b: Base, months: string[], i: number): { j: number; dir: 1 | -1; beyond: boolean } {
  const gained = (j: number) => grewBy(p, b, months[j]) > TOL;
  if (b.kind === 'plan') {
    for (let d = 1; d < months.length; d++) {
      if (i + d < months.length && gained(i + d)) return { j: i + d, dir: 1, beyond: false };
      if (i - d >= 0 && gained(i - d)) return { j: i - d, dir: -1, beyond: false };
    }
    return { j: i, dir: 1, beyond: false };
  }
  for (let j = i + 1; j < months.length; j++) {
    if (isOriginal(p, b, months[j]) || gained(j)) return { j, dir: 1, beyond: false };
  }
  return { j: months.length - 1, dir: 1, beyond: true };
}

export function ltaCell(p: Movable, mo: string, months: string[]): LtaCell {
  const b = baseOf(p);
  if (!b) return NONE;
  const i = months.indexOf(mo);
  const inRecs = (p.month_phases?.[mo] ?? []).filter(x => x.lta_move);
  const grew = grewBy(p, b, mo);
  const out: LtaCell = { ...NONE, kind: b.kind, movedIn: grew > TOL ? grew : 0, was: b.months[mo] || 0, move: inRecs[0]?.lta_move, change: p.plan_change ?? undefined };

  if (isOriginal(p, b, mo)) {
    const recs = originalAt(p, b, mo);
    const d = destination(p, b, months, i);
    const mv = (p.lta_moves ?? []).find(m => recs.some(r => r.phase_label === m.phase_label));
    Object.assign(out, {
      original: true, originalMwp: b.kind === 'plan' ? (b.months[mo] || 0) : sum(recs), originalPhases: recs,
      originalOverdue: b.kind === 'plan' ? sum(recs.filter(r => r.overdue)) : Math.min(sum(recs), b.overdue?.[mo] || 0),
      steps: Math.abs(d.j - i), dir: d.dir, beyond: d.beyond, to: d.beyond ? (mv?.to_month ?? '') : months[d.j], move: mv ?? out.move,
    });
  }
  // Inside the span of some arrow (strictly between its two ends).
  if (!out.original && out.movedIn <= 0) {
    for (let k = 0; k < months.length; k++) {
      if (k === i || !isOriginal(p, b, months[k])) continue;
      const d = destination(p, b, months, k);
      const lo = Math.min(k, d.j), hi = Math.max(k, d.j);
      if (i > lo && (i < hi || (d.beyond && i <= hi))) { out.underArrow = true; break; }
    }
  }
  return out;
}

/** The line with an arrow from the old-plan chip to the revised chip, drawn over the row (it takes no space, so
 *  nothing wraps or widens), measured from the cells and re-measured when the row resizes. */
export function LtaArrow({ steps, dir, beyond, to }: { steps: number; dir: 1 | -1; beyond: boolean; to: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [geo, setGeo] = useState<{ left: number; top: number; width: number } | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    const td = el?.closest('td');
    if (!el || !td || steps < 1) return;
    const measure = () => {
      let target: Element = td;
      for (let k = 0; k < steps; k++) {
        const nx = dir > 0 ? target.nextElementSibling : target.previousElementSibling;
        if (!nx) break;
        target = nx;
      }
      const cell = td.getBoundingClientRect();
      const origin = ((el.offsetParent as HTMLElement | null) ?? td).getBoundingClientRect();
      const src = td.querySelector('[data-lta-src]')?.getBoundingClientRect();
      const end = target.getBoundingClientRect();
      const dest = target.querySelector('[data-lta-dest], [data-lta-src]')?.getBoundingClientRect();
      const y = src ? src.top + src.height / 2 : cell.top + cell.height / 2;
      let a: number, b: number;                                    // a = where the line starts, b = where it ends (arrowhead)
      if (dir > 0) { a = (src ? src.right : cell.right - 4) + 2; b = beyond ? end.right - 2 : dest ? dest.left - 2 : end.right - 2; }
      else { a = (src ? src.left : cell.left + 4) - 2; b = dest ? dest.right + 2 : end.left + 2; }
      const w = Math.abs(b - a);
      setGeo(w > 6 ? { left: Math.min(a, b) - origin.left, top: y - origin.top, width: w } : null);
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (td.parentElement) ro.observe(td.parentElement);
    window.addEventListener('resize', measure);
    return () => { ro.disconnect(); window.removeEventListener('resize', measure); };
  }, [steps, dir, beyond]);

  return (
    <span ref={ref} aria-hidden className="pointer-events-none absolute z-10 h-0"
      style={geo ? { left: geo.left, top: geo.top, width: geo.width } : { left: 0, top: 0, width: 0, visibility: 'hidden' }}>
      <span className="absolute inset-x-0 top-0 block border-t-[1.5px] border-dotted border-brand-purple/70" />
      {beyond ? (
        <span className="absolute right-0 top-0 -translate-y-1/2 whitespace-nowrap rounded border border-brand-purple/40 bg-card px-1 text-[8.5px] font-bold leading-[13px] text-status-ai-fg">
          ✦ {to}
        </span>
      ) : dir > 0 ? (
        <span className="absolute -top-[4px] right-0 h-0 w-0 border-y-[4px] border-l-[6px] border-y-transparent border-l-brand-purple/80" />
      ) : (
        <span className="absolute -top-[4px] left-0 h-0 w-0 border-y-[4px] border-r-[6px] border-y-transparent border-r-brand-purple/80" />
      )}
    </span>
  );
}

const when = (iso?: string) => {
  const d = iso ? new Date(iso) : null;
  return d && !isNaN(d.getTime()) ? d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
};

const val = (v: unknown) => (v === null || v === undefined || v === '' ? 'not set' : String(v));
const because = (c: PlanChange) => c.because.map(x => `${x.field}${x.project ? ` of ${x.project}` : ''}: ${val(x.from)} → ${val(x.to)}${x.by ? ` by ${x.by}` : ''}`);

function Note({ children }: { children: React.ReactNode }) {
  return <div className="rounded-md border border-dotted border-brand-purple/40 bg-brand-purple/[0.05] px-2 py-1.5 text-[10.5px] leading-snug text-fg-secondary">{children}</div>;
}

/** Popup of an old-plan month: what it was, that it is not active, and why it was replaced. */
export function LtaOriginalNote({ c }: { c: LtaCell }) {
  if (c.kind === 'plan' && c.change) {
    return (
      <Note>
        <span className="font-semibold text-status-ai-fg">Old plan - not active.</span> Revised {when(c.change.at)}
        {c.change.own ? ' - this project\'s own dates changed' : ' - moved by another project\'s change'}: {because(c.change).join('; ')}.
        {c.to ? <> The order now sits in <span className="font-semibold text-fg-primary">{c.to}</span>.</> : null} The dates below are the old plan.
      </Note>
    );
  }
  const m = c.move;
  if (!m) return null;
  return (
    <Note>
      <span className="font-semibold text-status-ai-fg">✦ AI moved this order to {m.to_month}</span>
      {m.to_in_view ? '' : ' (beyond the months shown)'} because the LTA ({m.lta_date}) is {m.days_late} days after the AOP ({m.basis_date}).
      The dates below are the original plan.
    </Note>
  );
}

/** Popup of a revised-plan month: the revised plan is the active one; where it came from, why, and the window to order in. */
export function LtaRevisedNote({ c, phases, firstMonth }: { c: LtaCell; phases?: PhaseRec[]; firstMonth?: string }) {
  const win = (phases ?? []).filter(x => x.order_date).map(x => `${x.phase_label ? x.phase_label + ': ' : ''}order from ${firstMonth ?? 'now'} up to ${x.order_date} to meet the FTC${x.ftc_date ? ` (${x.ftc_date})` : ''}`);
  if (c.kind === 'plan' && c.change) {
    return (
      <Note>
        <span className="font-semibold text-status-ai-fg">Revised plan - active.</span> {c.movedIn.toFixed(1)} MWp more here{c.was > 0 ? ` (was ${c.was.toFixed(1)})` : ''}
        {c.change.own ? ' - this project\'s own dates changed' : ' - another project\'s change freed this month'}: {because(c.change).join('; ')}. {when(c.change.at)}.
        {win.length > 0 && <div className="mt-1 text-fg-primary">{win.join(' · ')}</div>}
      </Note>
    );
  }
  const m = c.move;
  if (!m) return null;
  return (
    <Note>
      <span className="font-semibold text-status-ai-fg">✦ AI revised: moved here from {m.from_month}</span> because the LTA ({m.lta_date}) is{' '}
      {m.days_late} days after the AOP ({m.basis_date}). Modules are needed 45 days before the LTA. Revised dates below,
      with the P6 plan under each - a calculation from the LTA, not a P6 date.
      {win.length > 0 && <div className="mt-1 text-fg-primary">{win.join(' · ')}</div>}
    </Note>
  );
}

/** One line above the schedule when the plan was revised recently: what changed, how many projects it moved, and how to read the marks. */
export function PlanRevisedBanner({ pv }: { pv?: { version: number; at: string; cause: string; moved: number } | null }) {
  if (!pv) return null;
  return (
    <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-dotted border-brand-purple/50 bg-brand-purple/[0.05] px-3 py-2 text-[11.5px] leading-snug text-fg-secondary">
      <span className="font-semibold text-status-ai-fg">Plan revised - version {pv.version}</span>
      <span className="min-w-0 flex-1">{when(pv.at)} · {pv.cause} · <span className="font-semibold text-fg-primary">{pv.moved} project{pv.moved === 1 ? '' : 's'} moved</span>.
        The old plan is kept (dotted, not active) with an arrow to where each order went; the revised plan is the active one.</span>
    </div>
  );
}
