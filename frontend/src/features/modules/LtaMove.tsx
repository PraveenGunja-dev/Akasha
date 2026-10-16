/* Orders moved later because the LTA is late.

   When a project's LTA is 30+ days after its AOP (the SCOD for a PPA), the
   planner places each order a lead time before the modules are needed - 45
   days before the LTA - instead of for the earlier P6 FTC (services/
   module_planner.py, _lta_alignment). These pieces show it on the schedule:

     - where it moved FROM: a dotted outline in the old month, with a dotted
       arrow to the new one and the MWp that moved;
     - where it moved TO: a dotted tag under the figure saying where it came from;
     - the tooltip: the dates and the reason, labelled as a calculation.

   Dotted outline = moved by the plan. Used by both the live page and the Beta. */
import React from 'react';
import { cx } from '../../components/ui/primitives';

export interface LtaMove {
  from_month: string; to_month: string; to_in_view: boolean;
  p6_order_date: string; new_order_date: string; modules_needed_by: string;
  lta_date: string; basis: string; basis_date: string; days_late: number;
}
export interface LtaMoveRow extends LtaMove { phase_label: string; mwp: number }

interface Mover {
  lta_moves?: LtaMoveRow[];
  lta_moved_beyond_mwp?: number;
  month_phases?: Record<string, Array<{ phase_label: string; mwp: number; lta_move?: LtaMove }>>;
}

/** The moves of one (from, to) pair, phases and MWp summed. */
export interface LtaMoveGroup extends LtaMove {
  mwp: number; phases: string[];
  lines: Array<{ phase_label: string; mwp: number; p6_order_date: string; new_order_date: string }>;
}

function group(rows: LtaMoveRow[]): LtaMoveGroup[] {
  const out = new Map<string, LtaMoveGroup>();
  for (const r of rows) {
    const k = `${r.from_month}>${r.to_month}`;
    const g = out.get(k);
    const line = { phase_label: r.phase_label, mwp: r.mwp, p6_order_date: r.p6_order_date, new_order_date: r.new_order_date };
    if (g) { g.mwp = Math.round((g.mwp + r.mwp) * 10) / 10; if (!g.phases.includes(r.phase_label)) g.phases.push(r.phase_label); g.lines.push(line); }
    else out.set(k, { ...r, phases: [r.phase_label], lines: [line] });
  }
  return [...out.values()];
}

/** Moves that leave month `mo` - drawn in that month as the dotted outline. */
export const movesOut = (p: Mover, mo: string): LtaMoveGroup[] => group((p.lta_moves ?? []).filter(m => m.from_month === mo));

/** Moves that arrive in month `mo` - read from the month's own phase records. */
export const movesIn = (p: Mover, mo: string): LtaMoveGroup[] =>
  group((p.month_phases?.[mo] ?? []).filter(x => x.lta_move).map(x => ({ ...x.lta_move!, phase_label: x.phase_label, mwp: x.mwp })));

const mw = (v: number) => v.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** A dotted arrow: round dots on a line, an open arrowhead. */
export function DottedArrow({ className, width = 26 }: { className?: string; width?: number }) {
  return (
    <svg viewBox="0 0 26 8" width={width} height={(width * 8) / 26} className={cx('shrink-0', className)} aria-hidden>
      <line x1="1.5" y1="4" x2="20" y2="4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeDasharray="0.1 3.4" />
      <path d="M18.5 1.2 L23.5 4 L18.5 6.8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** In the month the order left: "120.0 ┈┈▶ Mar-27" in a dotted outline. */
export function LtaMovedOut({ moves }: { moves: LtaMoveGroup[] }) {
  return (
    <div className="flex flex-col items-end gap-1">
      {moves.map(m => (
        <span key={m.to_month}
          aria-label={`${mw(m.mwp)} MWp moved from ${m.from_month} to ${m.to_month}${m.to_in_view ? '' : ', beyond this view'} for the LTA`}
          className="inline-flex flex-col items-end whitespace-nowrap rounded border border-dotted border-primary/60 px-1 py-[1px] leading-tight text-primary/90">
          <span className="text-[10.5px] font-semibold tabular-nums">{mw(m.mwp)}</span>
          <span className="inline-flex items-center gap-0.5 text-[9px] font-semibold">
            <DottedArrow width={15} />{m.to_month}
          </span>
        </span>
      ))}
    </div>
  );
}

/** In the month the order lands: a dotted tag saying where it came from. */
export function LtaMovedIn({ moves }: { moves: LtaMoveGroup[] }) {
  return (
    <div className="flex flex-col items-end gap-1">
      {moves.map(m => (
        <span key={m.from_month}
          aria-label={`${mw(m.mwp)} MWp moved here from ${m.from_month} for the LTA`}
          className="inline-flex items-center gap-0.5 whitespace-nowrap rounded border border-dotted border-primary/60 bg-primary/5 px-1 py-[1px] text-[9px] font-semibold text-primary">
          <DottedArrow width={13} className="rotate-180 opacity-80" />{m.from_month}
        </span>
      ))}
    </div>
  );
}

/** Tooltip body: each move with its dates, and why. */
export function LtaMoveTip({ outs, ins }: { outs: LtaMoveGroup[]; ins: LtaMoveGroup[] }) {
  const all = [...outs.map(m => ({ m, out: true })), ...ins.filter(i => !outs.some(o => o.from_month === i.from_month && o.to_month === i.to_month)).map(m => ({ m, out: false }))];
  if (all.length === 0) return null;
  return (
    <div className="space-y-2 rounded-lg border border-dotted border-primary/60 bg-primary/5 p-2.5 text-left">
      <div className="text-[10px] font-bold uppercase tracking-wider text-primary">Moved for the LTA</div>
      {all.map(({ m }) => (
        <div key={`${m.from_month}>${m.to_month}`} className="space-y-1">
          <div className="flex flex-wrap items-center gap-1.5 text-[12px] font-semibold text-fg-primary">
            <span className="rounded border border-dotted border-primary/50 px-1.5 py-px">{m.from_month}</span>
            <DottedArrow className="text-primary" />
            <span className="rounded border border-dotted border-primary/50 px-1.5 py-px">{m.to_month}{m.to_in_view ? '' : ' · beyond this view'}</span>
            <span className="tabular-nums text-primary">{mw(m.mwp)} MWp</span>
          </div>
          <ul className="space-y-0.5 text-[10.5px] leading-snug text-fg-secondary">
            {m.lines.map((l, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-1.5">
                <span className="font-semibold text-fg-primary">{l.phase_label}</span>
                <span className="tabular-nums">{mw(l.mwp)} MWp</span>
                <span>&middot; order date <span className="font-semibold text-fg-primary">{l.p6_order_date}</span> in P6 &rarr;{' '}
                  <span className="font-semibold text-fg-primary">{l.new_order_date}</span> now</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div className="border-t border-dotted border-primary/40 pt-1.5 text-[10.5px] leading-relaxed text-fg-secondary">
        The LTA ({all[0].m.lta_date}) is <span className="font-semibold text-fg-primary">{all[0].m.days_late} days after the {all[0].m.basis}</span>{' '}
        ({all[0].m.basis_date}). Modules are needed 45 days before the LTA, so each order is placed a lead time before that,
        not for the earlier P6 FTC.
      </div>
      <div className="text-[10px] italic text-fg-tertiary">Calculated from the LTA, not a P6 date - the P6 FTC is unchanged.</div>
    </div>
  );
}

/** In the row total: MWp that moved beyond the months on screen. */
export function LtaBeyond({ p }: { p: Mover }) {
  const beyond = p.lta_moved_beyond_mwp ?? 0;
  if (beyond <= 0) return null;
  const rows = (p.lta_moves ?? []).filter(m => !m.to_in_view);
  const last = rows.length ? rows[rows.length - 1].to_month : undefined;
  return (
    <span aria-label={`${mw(beyond)} MWp moved beyond this view for the LTA`}
      className="mt-0.5 inline-flex flex-col items-end whitespace-nowrap rounded border border-dotted border-primary/60 px-1 py-px leading-tight text-primary">
      <span className="text-[9.5px] font-semibold tabular-nums">+{mw(beyond)}</span>
      <span className="inline-flex items-center gap-0.5 text-[9px] font-semibold"><DottedArrow width={15} />{last ?? 'later'}</span>
    </span>
  );
}

export function LtaBeyondTip({ p }: { p: Mover }) {
  const rows = (p.lta_moves ?? []).filter(m => !m.to_in_view);
  return <LtaMoveTip outs={group(rows)} ins={[]} />;
}
