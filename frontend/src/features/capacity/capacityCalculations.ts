import type {
  CapacityFilters, MonthPoint, ProjectBreakdown, BlockMilestone, Segment,
} from './types';

/* ═══════════════════════════════════════════════════════════════════════════
   CAPACITY CALCULATIONS — the single source of truth

   Every panel derives from these functions rather than computing its own
   totals, so the donut, the KPI row and the drill-down cannot disagree.
   Percentages are calculated here; nothing downstream hardcodes one.
   ═══════════════════════════════════════════════════════════════════════════ */

const MONTHS_FOR: Record<string, number> = { '3M': 3, '6M': 6, '12M': 12 };

const SERIES_KEYS = ['Solar COD', 'Solar Trial Run', 'Wind COD', 'Wind Trial Run'] as const;
type SeriesKey = typeof SERIES_KEYS[number];

/** Indian FY starts 1 April. */
export function currentFYStart(now = new Date()): Date {
  const y = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  return new Date(y, 3, 1);
}

export function fyLabel(now = new Date()): string {
  const start = currentFYStart(now);
  return `FY${String((start.getFullYear() + 1) % 100).padStart(2, '0')}`;
}

/** "2025-07" → Date at the first of that month. */
const parseMonth = (name: string): Date | null => {
  const m = /^(\d{4})-(\d{2})$/.exec(name);
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, 1) : null;
};

/* ── Cumulative → incremental ─────────────────────────────────────────────
   The API builds monthly_trends as a RUNNING TOTAL (`cum_solar_cod += …` in
   dashboard.py), so each month carries capacity-to-date, not capacity added.
   Summing those values counts every earlier month again and again: it reported
   10,422 MW of COD added against a real portfolio COD of 2,655 MW.

   Everything downstream wants per-period additions, so the series is
   differenced once, here, at the boundary. Decreases are clamped to zero — a
   cumulative series that falls is a restatement, not negative capacity. */
export function decumulate(months: MonthPoint[]): MonthPoint[] {
  const sorted = [...(months || [])].sort((a, b) => a.name.localeCompare(b.name));
  let prev: MonthPoint | null = null;
  return sorted.map((m) => {
    const row: MonthPoint = { ...m };
    SERIES_KEYS.forEach((k) => {
      const now = Number(m[k]) || 0;
      const before = prev ? Number(prev[k]) || 0 : 0;
      row[k] = Math.max(now - before, 0);
    });
    prev = m;
    return row;
  });
}

/** Capacity-to-date at the end of a cumulative series. */
export function cumulativeTotal(months: MonthPoint[]): number {
  const sorted = [...(months || [])].sort((a, b) => a.name.localeCompare(b.name));
  const last = sorted[sorted.length - 1];
  return last ? SERIES_KEYS.reduce((s, k) => s + (Number(last[k]) || 0), 0) : 0;
}

/* ── Filtering ───────────────────────────────────────────────────────────── */

export function filterMonths(months: MonthPoint[], filters: CapacityFilters, now = new Date()): MonthPoint[] {
  if (!months?.length) return [];
  const sorted = [...months].sort((a, b) => a.name.localeCompare(b.name));

  if (filters.dateRange === 'ALL') return sorted;
  if (filters.dateRange === 'FY') {
    const start = currentFYStart(now);
    return sorted.filter((m) => {
      const d = parseMonth(m.name);
      return d ? d >= start : false;
    });
  }
  const n = MONTHS_FOR[filters.dateRange] ?? 12;
  return sorted.slice(-n);
}

export function filterProjects(projects: ProjectBreakdown[], segment: Segment): ProjectBreakdown[] {
  if (segment === 'All') return projects || [];
  return (projects || []).filter((p) => p.type === segment);
}

export function filterMilestones(milestones: BlockMilestone[], segment: Segment): BlockMilestone[] {
  if (segment === 'All') return milestones || [];
  return (milestones || []).filter((m) => m.type === segment);
}

/* ── Portfolio totals ────────────────────────────────────────────────────── */

export interface CapacityTotals {
  codMW: number;
  trMW: number;
  solarMW: number;
  windMW: number;
  portfolioMW: number;       // total installed capacity of the filtered projects
  commissionedMW: number;    // COD + TR
  remainingMW: number;
  projectCount: number;
  codPct: number;
  commissionedPct: number;
}

export function computeTotals(projects: ProjectBreakdown[]): CapacityTotals {
  const list = projects || [];
  const codMW = list.reduce((s, p) => s + (p.cod_mw || 0), 0);
  const trMW = list.reduce((s, p) => s + (p.tr_mw || 0), 0);
  const portfolioMW = list.reduce((s, p) => s + (p.total_capacity || 0), 0);
  const solarMW = list.filter((p) => p.type === 'Solar').reduce((s, p) => s + (p.total_capacity || 0), 0);
  const windMW = list.filter((p) => p.type === 'Wind').reduce((s, p) => s + (p.total_capacity || 0), 0);
  const commissionedMW = codMW + trMW;

  return {
    codMW, trMW, solarMW, windMW, portfolioMW, commissionedMW,
    remainingMW: Math.max(portfolioMW - commissionedMW, 0),
    projectCount: list.length,
    codPct: portfolioMW ? (codMW / portfolioMW) * 100 : 0,
    commissionedPct: portfolioMW ? (commissionedMW / portfolioMW) * 100 : 0,
  };
}

/* ── Period-over-period ──────────────────────────────────────────────────
   The KPI trend compares the visible window against the window immediately
   before it, from the same monthly series — not a stored "previous period"
   figure, which does not exist in this payload. */

export interface PeriodDelta {
  current: number;
  previous: number;
  deltaPct: number | null;   // null when there is no comparable prior window
  series: number[];
}


export function periodDelta(
  allMonths: MonthPoint[],
  filters: CapacityFilters,
  keys: SeriesKey[],
  now = new Date(),
): PeriodDelta {
  const sorted = decumulate(allMonths || []);
  const window = filterMonths(sorted, filters, now);
  const sum = (m: MonthPoint) => keys.reduce((s, k) => s + (Number(m[k]) || 0), 0);

  const current = window.reduce((s, m) => s + sum(m), 0);
  const startIdx = sorted.findIndex((m) => m.name === window[0]?.name);
  const prior = startIdx > 0 ? sorted.slice(Math.max(0, startIdx - window.length), startIdx) : [];
  const previous = prior.reduce((s, m) => s + sum(m), 0);

  return {
    current,
    previous,
    deltaPct: prior.length && previous > 0 ? ((current - previous) / previous) * 100 : null,
    series: window.map(sum),
  };
}

/* ── Aggregation for the trajectory chart ───────────────────────────────── */

export interface TrajectoryPoint {
  label: string;
  'Solar COD': number;
  'Solar Trial Run': number;
  'Wind COD': number;
  'Wind Trial Run': number;
  total: number;
  cumulative: number;
}

const quarterOf = (d: Date) => `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`;

export function aggregate(months: MonthPoint[], aggregation: string): TrajectoryPoint[] {
  const buckets = new Map<string, TrajectoryPoint>();

  for (const m of months) {
    const d = parseMonth(m.name);
    if (!d) continue;
    const label =
      aggregation === 'Yearly' ? String(d.getFullYear())
        : aggregation === 'Quarterly' ? quarterOf(d)
          : d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' });

    const b = buckets.get(label) || {
      label, 'Solar COD': 0, 'Solar Trial Run': 0, 'Wind COD': 0, 'Wind Trial Run': 0,
      total: 0, cumulative: 0,
    };
    SERIES_KEYS.forEach((k) => { b[k] += Number(m[k]) || 0; });
    b.total = SERIES_KEYS.reduce((s, k) => s + b[k], 0);
    buckets.set(label, b);
  }

  const out = Array.from(buckets.values());
  /* Cumulative WITHIN the selected window — the tooltip labels it as such, so
     it is never mistaken for portfolio capacity-to-date. */
  let running = 0;
  out.forEach((p) => { running += p.total; p.cumulative = running; });
  return out;
}

/** Which series the chart's segment tab should draw. */
export function seriesForFilter(series: string): SeriesKey[] {
  switch (series) {
    case 'COD': return ['Solar COD', 'Wind COD'];
    case 'Trial Run': return ['Solar Trial Run', 'Wind Trial Run'];
    case 'Solar': return ['Solar COD', 'Solar Trial Run'];
    case 'Wind': return ['Wind COD', 'Wind Trial Run'];
    default: return [...SERIES_KEYS];
  }
}

/* ── Upcoming capacity ───────────────────────────────────────────────────
   Remaining capacity is total minus what has reached COD or trial run. It is
   a pipeline figure, NOT a forecast: the payload carries no commissioning
   dates per project, so nothing here claims when it will land. */

export interface UpcomingRow {
  segment: string;
  mw: number;
  projectCount: number;
  pctOfSegment: number;
  projects: ProjectBreakdown[];
}

export function computeUpcoming(projects: ProjectBreakdown[]): UpcomingRow[] {
  const segments = ['Solar', 'Wind'];
  return segments
    .map((segment) => {
      const inSeg = (projects || []).filter((p) => p.type === segment && (p.remaining_capacity || 0) > 0);
      const mw = inSeg.reduce((s, p) => s + (p.remaining_capacity || 0), 0);
      const segTotal = (projects || []).filter((p) => p.type === segment)
        .reduce((s, p) => s + (p.total_capacity || 0), 0);
      return {
        segment,
        mw,
        projectCount: inSeg.length,
        pctOfSegment: segTotal ? (mw / segTotal) * 100 : 0,
        projects: [...inSeg].sort((a, b) => b.remaining_capacity - a.remaining_capacity),
      };
    })
    .filter((r) => r.mw > 0)
    .sort((a, b) => b.mw - a.mw);
}

/* ── Segment mix (donut) ─────────────────────────────────────────────────── */

export interface SegmentSlice {
  label: string;
  mw: number;
  pct: number;
  projectCount: number;
  segment: Segment;
}

export function computeSegmentMix(projects: ProjectBreakdown[]): SegmentSlice[] {
  const t = computeTotals(projects);
  const rows: SegmentSlice[] = [
    { label: 'Solar', mw: t.solarMW, pct: 0, segment: 'Solar' as Segment, projectCount: (projects || []).filter((p) => p.type === 'Solar').length },
    { label: 'Wind', mw: t.windMW, pct: 0, segment: 'Wind' as Segment, projectCount: (projects || []).filter((p) => p.type === 'Wind').length },
  ].filter((r) => r.mw > 0);
  rows.forEach((r) => { r.pct = t.portfolioMW ? (r.mw / t.portfolioMW) * 100 : 0; });
  return rows;
}

/* ── Milestones ──────────────────────────────────────────────────────────
   Built from real block-level dates. Blocks with no date are excluded rather
   than given a placeholder. */

export interface MilestoneRow {
  key: string;
  date: Date;
  dateLabel: string;
  title: string;
  project: string;
  block: string;
  capacity: number;
  status: BlockMilestone['status'];
  type: string;
}

export function computeMilestones(milestones: BlockMilestone[], limit = 6): MilestoneRow[] {
  const rows: MilestoneRow[] = [];
  for (const m of milestones || []) {
    const iso = m.cod_finish || m.tr_finish;
    if (!iso) continue;
    const d = new Date(iso);
    if (isNaN(d.getTime())) continue;
    rows.push({
      key: `${m.project}-${m.block}-${iso}`,
      date: d,
      dateLabel: d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' }),
      title: m.cod_finish ? `${m.block} reached COD` : `${m.block} entered trial run`,
      project: m.project,
      block: m.block,
      capacity: m.capacity || 0,
      status: m.status,
      type: m.type,
    });
  }
  return rows.sort((a, b) => b.date.getTime() - a.date.getTime()).slice(0, limit);
}
