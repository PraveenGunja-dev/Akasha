/* BETA: one vendor-quota levelling pass over the whole Ordering Schedule grid.

   The Beta draws AI-scored rows on the AI's own order months, which the
   rule engine never levelled - so an AI row could land on top of a month the
   engine had already filled, and the vendor's monthly limit was crossed. And
   because those placements were fixed, changing a project's priority could
   not move anything.

   This pass takes every row's orders as they are drawn (rule engine or AI),
   finds each order's TARGET month, and places them again against each
   vendor's monthly MWac limit:

     - in priority order: P1, then P2, then standard; within a priority PPA
       first, then the earliest target month - so a priority change decides
       who gets a full month;
     - target month first, then earlier months (pulled early, as the rule
       engine does), then later months;
     - an order moved out of its target month is marked shifted, with the
       reason - which vendor's monthly limit was full - and, when it moves
       later, its delay and the TC / FTC that follow from the new month.

   Orders are in MWp; each is converted with the project's DC/AC ratio (OL)
   before it counts against the MWac limit, as in the rule engine. */
import type { ModuleProject, MonthPhase } from './types';

/** Monthly vendor limits (MWac) - the rule engine's planning assumptions. */
export const VENDOR_CAP_MWAC: Record<string, number> = { China: 750, SEA: 500, ALMM: 500, ALCM: 100, DCR: 100 };
const DEFAULT_CAP = 500;
const LEAD_DAYS: Record<string, number> = { China: 136, SEA: 136 };
const DEFAULT_LEAD = 98;
const TC_OFFSET_DAYS = 45;
const PRIORITY_RANK: Record<string, number> = { p1: 1, p2: 2, standard: 3, std: 3 };

export type LeveledPhase = MonthPhase & {
  /** Why the order is not in its target month: the vendor limit that was full. */
  shift_reason?: string;
  /** The month the order was meant for. */
  target_month?: string;
};

/** Planning flags this pass owns; re-derived from its own result. */
const OWN_FLAGS = ['leveled_early', 'extended_to_lta', 'capacity_delayed'];

export interface VendorUse {
  cap_mwac: number;
  mwac: number[];
  mwp: number[];
}

export interface LeveledPlan<T extends ModuleProject> {
  rows: Map<number, T>;
  /** Per source, MWac and MWp placed in each grid month. */
  vendors: Record<string, VendorUse>;
  /** Orders no month in the grid had room for, per row (MWp). */
  outside: Map<number, number>;
}

const MON = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const MON_TITLE = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** 'dd-Mon-yy' (or 'dd-Mon-yyyy') -> Date, else null. */
function parseDay(s?: string | null): Date | null {
  const m = (s || '').match(/(\d{1,2})-([A-Za-z]{3})-(\d{2,4})/);
  if (!m) return null;
  const mi = MON.indexOf(m[2].toLowerCase());
  if (mi < 0) return null;
  const y = m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3]);
  return new Date(y, mi, Number(m[1]));
}
const fmtDay = (d: Date) => `${String(d.getDate()).padStart(2, '0')}-${MON_TITLE[d.getMonth()]}-${String(d.getFullYear()).slice(-2)}`;
/** 'Feb-27' -> index in the grid months, or -1. */
const monthIndexOfDate = (d: Date | null, months: string[]) =>
  d ? months.findIndex(mo => mo.toLowerCase() === `${MON[d.getMonth()]}-${String(d.getFullYear()).slice(-2)}`) : -1;
const monthStart = (mo: string) => {
  const [m, y] = mo.split('-');
  return new Date(2000 + Number(y), MON.indexOf(m.toLowerCase()), 1);
};
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const round1 = (n: number) => Math.round(n * 10) / 10;

interface Part {
  row: ModuleProject;
  phase: MonthPhase;
  mwp: number;
  target: number;
  source: string;
  ol: number;
  /** An approved order frozen in its month (Request approval): placed there
   *  first, never moved by the levelling. */
  fixed?: boolean;
}

/* Same rules as the backend planner (services/module_planner.py):
   - demo projects (portfolio "Akasha Demo...") level against their own copy
     of the vendor quota, so they never move a real project's order;
   - an approved, frozen quantity stays in its month. */
const DEMO_POOL = ' (demo)';
const isDemoRow = (r: ModuleProject) => String((r as { cluster?: string }).cluster ?? '').toLowerCase().startsWith('akasha demo');
const frozenOf = (ph: MonthPhase) => Number((ph as { frozen_mwp?: number }).frozen_mwp) || 0;

/**
 * Re-level every row of the grid against the vendor monthly limits.
 * `isAI(row)` marks rows drawn on the AI plan: their target is the month the
 * AI put them in (their phase order_date is the rule-engine date, kept for
 * the "Rule:" line). Rule-engine rows target the month of their own planned
 * order date (the first grid month when that has already passed).
 */
export function levelVendorQuota<T extends ModuleProject>(
  rows: T[], months: string[], isAI: (row: T) => boolean,
  caps: Record<string, number> = VENDOR_CAP_MWAC,
  /** The priority that decides who gets a full month (default: row.priority). */
  priorityOf: (row: T) => string = r => r.priority || 'standard',
): LeveledPlan<T> {
  const N = months.length;
  const parts: Part[] = [];
  for (const row of rows) {
    const ai = isAI(row);
    months.forEach((mo, i) => {
      const val = row.month_mwp?.[mo] || 0;
      if (val <= 0) return;
      const phases = row.month_phases?.[mo] ?? [];
      const listed = phases.reduce((s, x) => s + (x.mwp || 0), 0);
      // A month's figure without (complete) phase detail still has to count.
      const entries: MonthPhase[] = phases.length > 0 && Math.abs(listed - val) < 0.6 ? phases : [{
        phase_label: 'Main', mwp: val, mw_ac: 0, order_date: '-', tc_date: '-', ftc_date: '-',
        order_month: mo, delay_months: 0, ftc_reachable: true, ftc_short_days: 0,
        next_tc_date: '-', next_ftc_date: '-', overdue: (row.month_overdue_mwp?.[mo] || 0) > 0, shifted: false,
      }];
      for (const ph of entries) {
        if (!(ph.mwp > 0)) continue;
        const source = (row.type || 'ALMM') + (isDemoRow(row) ? DEMO_POOL : '');
        const ol = row.ol > 0 ? row.ol : 1.35;
        // The frozen share stays in this month; only the rest is levelled.
        const frozen = Math.min(frozenOf(ph), ph.mwp);
        if (frozen > 0.05) parts.push({ row, phase: ph, mwp: frozen, target: i, source, ol, fixed: true });
        if (ph.mwp - frozen <= 0.05) continue;
        let target = i;
        if (!ai) {
          const planned = parseDay(ph.order_date);
          const idx = monthIndexOfDate(planned, months);
          if (planned && planned < monthStart(months[0])) target = 0;
          else if (idx >= 0) target = idx;
        }
        parts.push({ row, phase: ph, mwp: ph.mwp - frozen, target, source, ol });
      }
    });
  }

  const rank = (r: ModuleProject) => PRIORITY_RANK[(priorityOf(r as T) || 'standard').toLowerCase()] ?? 3;
  const isPPA = (r: ModuleProject) => (r.category || '').toUpperCase() === 'PPA' || /PPA/i.test(r.project_name || '');
  // The rule engine's own tie-breaks (earliest FTC, then earliest order date),
  // so with no priority set the standard plan comes out as the engine made it.
  const dayNum = (s?: string) => parseDay(s)?.getTime() ?? Number.MAX_SAFE_INTEGER;
  parts.sort((a, b) => (a.fixed ? 0 : 1) - (b.fixed ? 0 : 1)
    || rank(a.row) - rank(b.row)
    || (isPPA(a.row) ? 0 : 1) - (isPPA(b.row) ? 0 : 1)
    || dayNum(a.phase.ftc_date) - dayNum(b.phase.ftc_date)
    || dayNum(a.phase.order_date) - dayNum(b.phase.order_date)
    || a.target - b.target
    || a.row.id - b.row.id);

  const vendors: Record<string, VendorUse> = {};
  const use = (src: string) => (vendors[src] ??= {
    cap_mwac: caps[src] ?? caps[src.endsWith(DEMO_POOL) ? src.slice(0, -DEMO_POOL.length) : src] ?? DEFAULT_CAP,
    mwac: Array(N).fill(0), mwp: Array(N).fill(0),
  });
  const placed = new Map<number, { month: number; part: Part; mwp: number }[]>();
  const outside = new Map<number, number>();

  for (const part of parts) {
    const v = use(part.source);
    if (part.fixed) {
      // Frozen: its month only, taking that month's quota first.
      v.mwac[part.target] += part.mwp / part.ol;
      v.mwp[part.target] += part.mwp;
      const list = placed.get(part.row.id) ?? [];
      list.push({ month: part.target, part, mwp: part.mwp });
      placed.set(part.row.id, list);
      continue;
    }
    let rem = part.mwp;
    // Target, then earlier (pulled early), then later.
    const order = [part.target, ...Array.from({ length: part.target }, (_, k) => part.target - 1 - k),
      ...Array.from({ length: N - part.target - 1 }, (_, k) => part.target + 1 + k)];
    for (const m of order) {
      if (rem <= 1e-4) break;
      const room = v.cap_mwac - v.mwac[m];
      if (room <= 1e-4) continue;
      const takeAc = Math.min(rem / part.ol, room);
      const take = takeAc * part.ol;
      v.mwac[m] += takeAc;
      v.mwp[m] += take;
      rem -= take;
      const list = placed.get(part.row.id) ?? [];
      list.push({ month: m, part, mwp: take });
      placed.set(part.row.id, list);
    }
    if (rem > 1e-4) outside.set(part.row.id, (outside.get(part.row.id) ?? 0) + rem);
  }

  const out = new Map<number, T>();
  for (const row of rows) {
    const list = placed.get(row.id);
    if (!list && !outside.has(row.id)) { out.set(row.id, row); continue; }
    const month_mwp: Record<string, number> = Object.fromEntries(months.map(m => [m, 0]));
    const month_overdue_mwp: Record<string, number> = Object.fromEntries(months.map(m => [m, 0]));
    const month_phases: Record<string, LeveledPhase[]> = Object.fromEntries(months.map(m => [m, []]));
    const month_frozen_mwp: Record<string, number> = Object.fromEntries(months.map(m => [m, 0]));
    const flags = new Set((row.planning_flags ?? []).filter(f => !OWN_FLAGS.includes(f)));
    const lta = parseDay(row.lta);
    const lead = LEAD_DAYS[row.type] ?? DEFAULT_LEAD;
    for (const { month, part, mwp } of list ?? []) {
      const mo = months[month];
      const ph = part.phase;
      month_mwp[mo] += mwp;
      if (ph.overdue) month_overdue_mwp[mo] += mwp;
      if (part.fixed) month_frozen_mwp[mo] += mwp;
      let rec: LeveledPhase = { ...ph, mwp: round1(mwp), order_month: mo, shifted: false, shift_reason: undefined,
        frozen_mwp: part.fixed ? round1(mwp) : 0 } as LeveledPhase;
      if (month !== part.target) {
        const cap = vendors[part.source].cap_mwac;
        const reason = `${part.source} ${Math.round(cap)} MWac/month vendor allocation full in ${months[part.target]}`;
        rec = { ...rec, shifted: true, shift_reason: reason, target_month: months[part.target] };
        if (month < part.target) {
          flags.add('leveled_early');
        } else {
          // Ordered later than its target: the delay, and where TC / FTC land from here.
          const planned = parseDay(ph.order_date);
          const effective = new Date(monthStart(mo).getFullYear(), monthStart(mo).getMonth(), planned ? Math.min(planned.getDate(), 28) : 1);
          const nextTc = addDays(effective, lead);
          const nextFtc = addDays(nextTc, TC_OFFSET_DAYS);
          const ftc = parseDay(ph.ftc_date);
          const daysAvail = ftc ? Math.round((ftc.getTime() - effective.getTime()) / 86400000) : Infinity;
          const need = lead + TC_OFFSET_DAYS;
          rec = {
            ...rec,
            delay_months: Math.max(rec.delay_months || 0, month - part.target),
            ftc_reachable: (rec.ftc_reachable ?? true) && daysAvail >= need,
            ftc_short_days: Math.max(rec.ftc_short_days || 0, Number.isFinite(daysAvail) ? Math.max(0, need - daysAvail) : 0),
            next_tc_date: fmtDay(nextTc),
            next_ftc_date: fmtDay(nextFtc),
          };
          flags.add(lta && nextFtc > lta ? 'capacity_delayed' : 'extended_to_lta');
        }
      }
      // Same phase twice in a month (two parts of one order): add them up.
      const same = month_phases[mo].find(x => x.phase_label === rec.phase_label && x.shifted === rec.shifted);
      if (same) {
        same.mwp = round1(same.mwp + rec.mwp);
        (same as { frozen_mwp?: number }).frozen_mwp = round1(frozenOf(same) + frozenOf(rec));
      }
      else month_phases[mo].push(rec);
    }
    for (const mo of months) {
      month_mwp[mo] = round1(month_mwp[mo]);
      month_overdue_mwp[mo] = round1(month_overdue_mwp[mo]);
      month_frozen_mwp[mo] = round1(month_frozen_mwp[mo]);
    }
    out.set(row.id, { ...row, month_mwp, month_overdue_mwp, month_phases, month_frozen_mwp, planning_flags: [...flags] } as T);
  }
  // Every row carries the priority it was levelled with (cell colours read it).
  for (const [id, row] of out) {
    const pr = (priorityOf(row) || 'standard').toLowerCase();
    out.set(id, { ...row, priority: pr === 'p1' ? 'P1' : pr === 'p2' ? 'P2' : 'standard' });
  }
  return { rows: out, vendors, outside };
}
