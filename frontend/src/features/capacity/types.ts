/* ═══════════════════════════════════════════════════════════════════════════
   CAPACITY OVERVIEW — shared types

   One filter object drives every section, so a segment or date change cannot
   leave one panel describing a different population from its neighbour.
   ═══════════════════════════════════════════════════════════════════════════ */

/** Segments are the ones the data actually carries. `capacity-overview` types
 *  every project by ProjectMapping.cluster into exactly Solar or Wind, so
 *  offering Hydro/Thermal/Hybrid would be empty tabs. */
export type Segment = 'All' | 'Solar' | 'Wind';

export type DateRangeKey = '3M' | '6M' | '12M' | 'FY' | 'ALL';

export type Aggregation = 'Monthly' | 'Quarterly' | 'Yearly';

export type ChartSeriesKey = 'All' | 'COD' | 'Trial Run' | 'Solar' | 'Wind';

export interface CapacityFilters {
  segment: Segment;
  dateRange: DateRangeKey;
  aggregation: Aggregation;
  series: ChartSeriesKey;
}

export const DEFAULT_FILTERS: CapacityFilters = {
  segment: 'All',
  dateRange: '12M',
  aggregation: 'Monthly',
  series: 'All',
};

export const DATE_RANGE_LABELS: Record<DateRangeKey, string> = {
  '3M': 'Last 3 months',
  '6M': 'Last 6 months',
  '12M': 'Last 12 months',
  FY: 'Current FY',
  ALL: 'All time',
};

/* ── API payload (as returned by /api/dashboard/capacity-overview) ───────── */

export interface FYData {
  name: string;
  solar_cod: number;
  solar_tr: number;
  wind_cod: number;
  wind_tr: number;
}

export interface MonthPoint {
  name: string;               // "2025-07"
  'Solar COD': number;
  'Solar Trial Run': number;
  'Wind COD': number;
  'Wind Trial Run': number;
}

export interface BlockMilestone {
  project: string;
  block: string;
  type: string;
  capacity: number;
  status: 'COD' | 'Trial Run' | 'Pending';
  tr_start: string | null;
  tr_finish: string | null;
  cod_start: string | null;
  cod_finish: string | null;
  tr_duration: number | null;
  cod_duration: number | null;
  gap_days: number | null;
}

export interface ProjectBreakdown {
  project_id: string;
  project_name: string;
  type: string;                // 'Solar' | 'Wind'
  total_capacity: number;
  total_blocks: number;
  tr_blocks: number;
  tr_mw: number;
  cod_blocks: number;
  cod_mw: number;
  remaining_capacity: number;
  remaining_blocks: number;
}

export interface CapacityData {
  financial_years: FYData[];
  monthly_trends?: MonthPoint[];
  recent_milestones: BlockMilestone[];
  totals: { solar_cod: number; solar_tr: number; wind_cod: number; wind_tr: number };
  projects: ProjectBreakdown[];
}

/* ── Insights ────────────────────────────────────────────────────────────
   Severity drives colour AND an icon + written label, so status is never
   carried by hue alone. */

export type Severity = 'critical' | 'warning' | 'success' | 'info';

export type InsightCategory =
  | 'Commissioning'
  | 'Pipeline'
  | 'Segment mix'
  | 'Execution risk'
  | 'Opportunity';

/** `source` is deliberate: a calculated figure must never be presented as a
 *  model output. Anything derived by generateCapacityInsights is 'calculated'. */
export type InsightSource = 'calculated' | 'ai';

export interface CapacityInsight {
  id: string;
  severity: Severity;
  category: InsightCategory;
  source: InsightSource;
  title: string;
  /** One sentence a CEO can act on. */
  summary: string;
  /** Why the figure is what it is — the arithmetic, in words. */
  detail: string;
  metric: { label: string; value: string; comparison?: string };
  /** Project names this is computed from, so the claim is traceable. */
  affectedProjects: string[];
  affectedMW: number;
  recommendation: string;
  /** Which fields of the payload produced it. */
  evidence: string;
  generatedAt: string;
}

/* ── Actions ─────────────────────────────────────────────────────────────── */

export type ActionStatus = 'Open' | 'In Progress' | 'Blocked' | 'Completed' | 'Dismissed';
export type ActionPriority = 'High' | 'Medium' | 'Low';

export interface CapacityAction {
  id: string;
  title: string;
  description: string;
  priority: ActionPriority;
  owner: string;
  dueDate: string;            // ISO date
  status: ActionStatus;
  sourceInsightId?: string;
  affectedProjects: string[];
  affectedMW: number;
  createdAt: string;
  updatedAt: string;
}
