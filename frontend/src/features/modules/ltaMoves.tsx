/* Orders the plan moved later because the LTA is late (services/module_planner.py,
   _lta_alignment), as the schedule shows them:

     - the ORIGINAL month keeps its order exactly as it was before the move
       (from `lta_base`, the plan without the move) - same chip, same popup
       with the original dates;
     - the NEW month shows the same chip in the AI colour with a ✦, and its
       popup the same cards with the revised (AI) dates;
     - one line with an arrow runs from the original month to the new one.

   Used by the live Ordering Schedule and the Beta. */
import { useLayoutEffect, useRef, useState } from 'react';

export interface LtaMoveInfo {
  from_month: string; to_month: string; to_in_view: boolean;
  p6_order_date: string; new_order_date: string;
  p6_tc_date: string; new_tc_date: string;
  p6_ftc_date: string; new_ftc_date: string;
  lta_date: string; basis: string; basis_date: string; days_late: number;
}
interface PhaseRec { phase_label: string; mwp: number; lta_move?: LtaMoveInfo }
interface Movable {
  month_mwp?: Record<string, number>;
  month_phases?: Record<string, PhaseRec[]>;
  lta_moves?: Array<LtaMoveInfo & { phase_label: string; mwp: number }>;
  lta_base?: { month_mwp: Record<string, number>; month_overdue_mwp: Record<string, number>; month_phases: Record<string, PhaseRec[]> };
}

export interface LtaCell {
  /** This month held an order the LTA moved away and holds nothing now: show it as it was. */
  original: boolean;
  originalMwp: number;
  originalOverdue: number;
  originalPhases: PhaseRec[];
  /** MWp the LTA moved into this month (its chip is drawn in the AI colour). */
  movedIn: number;
  /** An arrow passes through this month: show it empty rather than "-". */
  underArrow: boolean;
  /** From an original month: how many month columns to the new one, and whether that is beyond the months shown. */
  steps: number; beyond: boolean; to: string;
  move?: LtaMoveInfo;
}

const NONE: LtaCell = { original: false, originalMwp: 0, originalOverdue: 0, originalPhases: [], movedIn: 0, underArrow: false, steps: 0, beyond: false, to: '' };
const sum = (xs: PhaseRec[]) => xs.reduce((a, x) => a + (x.mwp || 0), 0);

/** Where the arrow from original month index i ends: the next original month
 *  (so several originals chain - 206 -> 64 -> 270 - instead of one arrow
 *  running through the other's chip), else the next month with moved-in MWp,
 *  else - the order went past the months shown - the last month. */
function destination(p: Movable, months: string[], i: number): { j: number; beyond: boolean } {
  for (let j = i + 1; j < months.length; j++) {
    if (isOriginal(p, months[j]) || (p.month_phases?.[months[j]] ?? []).some(x => x.lta_move)) return { j, beyond: false };
  }
  return { j: months.length - 1, beyond: true };
}

function originalAt(p: Movable, mo: string): PhaseRec[] {
  const moved = new Set((p.lta_moves ?? []).map(m => m.phase_label));
  return (p.lta_base?.month_phases?.[mo] ?? []).filter(x => moved.has(x.phase_label));
}

const isOriginal = (p: Movable, mo: string) =>
  !!p.lta_base && (p.month_mwp?.[mo] || 0) <= 0.05 && sum(originalAt(p, mo)) > 0.05;

export function ltaCell(p: Movable, mo: string, months: string[]): LtaCell {
  if (!p.lta_moves?.length) return NONE;
  const i = months.indexOf(mo);
  const inRecs = (p.month_phases?.[mo] ?? []).filter(x => x.lta_move);
  const out: LtaCell = { ...NONE, movedIn: sum(inRecs), move: inRecs[0]?.lta_move };

  if (isOriginal(p, mo)) {
    const recs = originalAt(p, mo);
    const d = destination(p, months, i);
    const mv = (p.lta_moves ?? []).find(m => recs.some(r => r.phase_label === m.phase_label));
    Object.assign(out, {
      original: true, originalMwp: sum(recs), originalPhases: recs,
      originalOverdue: Math.min(sum(recs), p.lta_base?.month_overdue_mwp?.[mo] || 0),
      steps: d.j - i, beyond: d.beyond, to: d.beyond ? (mv?.to_month ?? '') : months[d.j], move: mv,
    });
  }
  // Inside the span of some arrow (after its start, before its end).
  for (let k = 0; k < i; k++) {
    if (!isOriginal(p, months[k])) continue;
    const d = destination(p, months, k);
    if (i < d.j || (d.beyond && i <= d.j)) { out.underArrow = !out.original && out.movedIn <= 0; break; }
  }
  return out;
}

/** The line with an arrow from the original month's chip to the new month's
 *  chip. Drawn over the row (no effect on layout, so nothing wraps or grows),
 *  measured from the cells themselves and re-measured when the row resizes. */
export function LtaArrow({ steps, beyond, to }: { steps: number; beyond: boolean; to: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [geo, setGeo] = useState<{ left: number; top: number; width: number } | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    const td = el?.closest('td');
    if (!el || !td) return;
    const measure = () => {
      let target: Element = td;
      for (let k = 0; k < steps; k++) {
        const nx = target.nextElementSibling;
        if (!nx) break;
        target = nx;
      }
      const cell = td.getBoundingClientRect();
      // Positions are relative to the arrow's own positioned parent (the month cell).
      const origin = ((el.offsetParent as HTMLElement | null) ?? td).getBoundingClientRect();
      const src = td.querySelector('[data-lta-src]')?.getBoundingClientRect();
      const end = target.getBoundingClientRect();
      const dest = target.querySelector('[data-lta-dest], [data-lta-src]')?.getBoundingClientRect();
      const startX = (src ? src.right : cell.right - 4) + 2;
      const endX = beyond ? end.right - 2 : dest ? dest.left - 2 : end.right - 2;
      const y = src ? src.top + src.height / 2 : cell.top + cell.height / 2;
      setGeo(endX - startX > 6 ? { left: startX - origin.left, top: y - origin.top, width: endX - startX } : null);
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (td.parentElement) ro.observe(td.parentElement);
    window.addEventListener('resize', measure);
    return () => { ro.disconnect(); window.removeEventListener('resize', measure); };
  }, [steps, beyond]);

  return (
    <span ref={ref} aria-hidden className="pointer-events-none absolute z-10 h-0"
      style={geo ? { left: geo.left, top: geo.top, width: geo.width } : { left: 0, top: 0, width: 0, visibility: 'hidden' }}>
      <span className="absolute inset-x-0 top-0 block border-t-[1.5px] border-brand-purple/70" />
      {beyond ? (
        <span className="absolute right-0 top-0 -translate-y-1/2 whitespace-nowrap rounded border border-brand-purple/40 bg-card px-1 text-[8.5px] font-bold leading-[13px] text-status-ai-fg">
          ✦ {to}
        </span>
      ) : (
        <span className="absolute -top-[4px] right-0 h-0 w-0 border-y-[4px] border-l-[6px] border-y-transparent border-l-brand-purple/80" />
      )}
    </span>
  );
}

/** Top of the popup in the original month: these are the dates before the move. */
export function LtaOriginalNote({ m }: { m?: LtaMoveInfo }) {
  if (!m) return null;
  return (
    <div className="rounded-md border border-brand-purple/25 bg-brand-purple/[0.05] px-2 py-1.5 text-[10.5px] leading-snug text-fg-secondary">
      <span className="font-semibold text-status-ai-fg">✦ AI moved this order to {m.to_month}</span>
      {m.to_in_view ? '' : ' (beyond the months shown)'} because the LTA ({m.lta_date}) is {m.days_late} days after the AOP ({m.basis_date}).
      The dates below are the original plan.
    </div>
  );
}

/** Top of the popup in the new month: the revised dates are the AI's. */
export function LtaRevisedNote({ m }: { m?: LtaMoveInfo }) {
  if (!m) return null;
  return (
    <div className="rounded-md border border-brand-purple/25 bg-brand-purple/[0.05] px-2 py-1.5 text-[10.5px] leading-snug text-fg-secondary">
      <span className="font-semibold text-status-ai-fg">✦ AI revised: moved here from {m.from_month}</span> because the LTA ({m.lta_date}) is{' '}
      {m.days_late} days after the AOP ({m.basis_date}). Modules are needed 45 days before the LTA. Revised dates below,
      with the P6 plan under each - a calculation from the LTA, not a P6 date.
    </div>
  );
}
