export type WindowKey = 'NEXT6' | 'FY' | 'ALL';
export type BasisKey = 'planned' | 'baseline';
export type ShowKey = 'all' | 'behind' | 'notstarted' | 'done';
export type UnitKey = 'blocks' | 'modules';

export interface PlannerFilters { window: WindowKey; basis: BasisKey; show: ShowKey; search: string; unit: UnitKey }
export const DEFAULT_FILTERS: PlannerFilters = { window: 'NEXT6', basis: 'planned', show: 'all', search: '', unit: 'blocks' };

export const WINDOW_LABELS: Record<WindowKey, string> = { NEXT6: 'Next 6 months', FY: 'This FY', ALL: 'All months' };
export const BASIS_LABELS: Record<BasisKey, string> = { planned: 'Current plan', baseline: 'Baseline' };
export const SHOW_LABELS: Record<ShowKey, string> = { all: 'All projects', behind: 'Behind plan', notstarted: 'Not started', done: 'Completed' };
export const UNIT_LABELS: Record<UnitKey, string> = { blocks: 'Show in Blocks', modules: 'Show in Modules' };

export interface MonthCell { 
  planned: number; 
  baseline: number; 
  completed: number;
  modules_planned: number;
  modules_baseline: number;
  modules_completed: number;
  activities?: { name: string; status: string; baseline_start: string | null; baseline_finish: string | null; forecast_start: string | null; forecast_finish: string | null; actual_start: string | null; actual_finish: string | null; modules_scope: number; modules_actual: number }[];
}

export interface PlannerProject {
  project_id: string; name: string; cluster: string | null; capacity_mwac: number; is_commissioned: boolean;
  ordered_cr: number; delivered_cr: number;
  ecod: { scheduled: string | null; baseline: string | null; slip_days: number | null };
  tc: { lines: number; charged: number };
  not_applicable: boolean;
  summary: {
    planned: number; completed: number; in_progress: number; not_started: number; pct_complete: number;
    modules_scope: number; modules_completed: number; modules_in_progress: number; modules_not_started: number; modules_pct: number;
  } | null;
  monthly: Record<string, MonthCell>;
  behind: number;
  modules_behind: number;
  next_due: string | null;
}

export interface PlannerData {
  months: string[];
  today: string;
  totals: {
    planned: number; completed: number; in_progress: number; not_started: number;
    this_month: { planned: number; completed: number }; behind_projects: number;
    ordered_cr: number; delivered_cr: number;
    modules_planned: number; modules_completed: number; modules_in_progress: number; modules_not_started: number;
    this_month_modules: { planned: number; completed: number };
  };
  projects: PlannerProject[];
  basis: string;
}

/** "2026-09" → "Sep 26" */
export const monthLabel = (ym: string) => {
  const [y, m] = ym.split('-');
  return new Date(+y, +m - 1, 1).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' });
};

/** Inclusive list of YYYY-MM between two keys. */
export const monthRange = (from: string, to: string): string[] => {
  const out: string[] = [];
  let [y, m] = from.split('-').map(Number);
  const [ty, tm] = to.split('-').map(Number);
  while (y < ty || (y === ty && m <= tm)) {
    out.push(`${y}-${String(m).padStart(2, '0')}`);
    m += 1; if (m > 12) { m = 1; y += 1; }
  }
  return out;
};

export const shiftMonth = (ym: string, delta: number): string => {
  const [y, m] = ym.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

/** Indian financial year: 1 April → 31 March, as capacityCalculations.currentFYStart does. */
export const fyMonths = (today: string): [string, string] => {
  const [y, m] = today.split('-').map(Number);
  const startYear = m >= 4 ? y : y - 1;
  return [`${startYear}-04`, `${startYear + 1}-03`];
};
