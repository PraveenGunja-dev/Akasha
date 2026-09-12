import type { CapacityData, CapacityFilters, CapacityInsight } from './types';
import {
  filterProjects, filterMonths, computeTotals, periodDelta, computeUpcoming, aggregate,
  decumulate,
} from './capacityCalculations';

/* ═══════════════════════════════════════════════════════════════════════════
   CAPACITY INSIGHTS

   `generateCapacityInsights` is the seam the brief asks for: one pure function
   from (data, filters) to a typed list. An AI service can be added later by
   emitting insights with source: 'ai' — the UI already renders and labels the
   two differently.

   Everything here is source: 'calculated'. It is arithmetic over the payload,
   and each insight carries `evidence` naming the fields it came from, so a
   claim can be checked rather than trusted. Nothing is phrased as a
   prediction unless the arithmetic is a stated extrapolation.

   Deliberately NOT produced here:
     • "X% ahead of plan" — the payload has no planned series. There is a
       portfolio total (sum of total_capacity), which is a target, not a
       time-phased plan, so a variance against it would be meaningless.
     • Grid-clearance / land / clearance causes — no such field exists.
   ═══════════════════════════════════════════════════════════════════════════ */

const MW = (n: number) => `${n.toLocaleString('en-IN', { maximumFractionDigits: 1 })} MW`;

export function generateCapacityInsights(
  data: CapacityData | null,
  filters: CapacityFilters,
  now = new Date(),
): CapacityInsight[] {
  if (!data) return [];

  const projects = filterProjects(data.projects || [], filters.segment);
  const months = filterMonths(decumulate(data.monthly_trends || []), filters, now);
  const totals = computeTotals(projects);
  const upcoming = computeUpcoming(projects);
  const at = now.toISOString();
  const out: CapacityInsight[] = [];

  /* 1 ── Commissioning momentum, window against the window before it. */
  const delta = periodDelta(data.monthly_trends || [], filters, ['Solar COD', 'Wind COD'], now);
  if (delta.deltaPct !== null && delta.current > 0) {
    const up = delta.deltaPct >= 0;
    out.push({
      id: 'momentum',
      severity: up ? 'success' : 'warning',
      category: 'Commissioning',
      source: 'calculated',
      title: up
        ? `COD additions up ${Math.abs(delta.deltaPct).toFixed(0)}% on the previous period`
        : `COD additions down ${Math.abs(delta.deltaPct).toFixed(0)}% on the previous period`,
      summary: `${MW(delta.current)} reached COD in this window, against ${MW(delta.previous)} in the one before it.`,
      detail:
        `The comparison uses the same monthly series either side of the selected range — ` +
        `${months.length} months in view against the ${months.length} immediately preceding. ` +
        `No stored "previous period" figure exists in the payload, so it is computed from the series itself.`,
      metric: {
        label: 'COD added this period',
        value: MW(delta.current),
        comparison: `${up ? '+' : ''}${delta.deltaPct.toFixed(1)}% vs previous`,
      },
      affectedProjects: [],
      affectedMW: delta.current,
      recommendation: up
        ? 'Momentum is positive — confirm the next tranche has grid readiness to sustain it.'
        : 'Check whether the slowdown is sequencing or a genuine blockage in the commissioning queue.',
      evidence: 'monthly_trends → Solar COD + Wind COD, current window vs preceding window',
      generatedAt: at,
    });
  }

  /* 2 ── Capacity sitting in trial run: built, not yet earning. */
  if (totals.trMW > 0) {
    const trProjects = projects.filter((p) => (p.tr_mw || 0) > 0);
    out.push({
      id: 'trial-run-stock',
      severity: totals.trMW > totals.codMW * 0.15 ? 'warning' : 'info',
      category: 'Commissioning',
      source: 'calculated',
      title: `${MW(totals.trMW)} is in trial run but not yet at COD`,
      summary: `Across ${trProjects.length} project${trProjects.length === 1 ? '' : 's'}, this capacity is physically built and energised but has not converted to COD.`,
      detail:
        `A block counts as trial run only when it has a trial-run milestone and no COD milestone. ` +
        `This is the closest capacity to revenue: the plant exists, so conversion is a commercial and ` +
        `documentation step rather than a construction one.`,
      metric: {
        label: 'Trial run capacity',
        value: MW(totals.trMW),
        comparison: `${((totals.trMW / (totals.commissionedMW || 1)) * 100).toFixed(0)}% of commissioned`,
      },
      affectedProjects: trProjects.map((p) => p.project_name).slice(0, 12),
      affectedMW: totals.trMW,
      recommendation: 'Prioritise COD conversion here before starting new trial runs — it is the shortest path to earning capacity.',
      evidence: 'projects[].tr_mw where a block has a trial-run milestone and no COD milestone',
      generatedAt: at,
    });
  }

  /* 3 ── Projects that have not started commissioning at all. */
  const notStarted = projects.filter(
    (p) => (p.total_capacity || 0) > 0 && (p.cod_mw || 0) === 0 && (p.tr_mw || 0) === 0,
  );
  if (notStarted.length) {
    const mw = notStarted.reduce((s, p) => s + p.total_capacity, 0);
    out.push({
      id: 'not-started',
      severity: mw > totals.portfolioMW * 0.4 ? 'critical' : 'warning',
      category: 'Execution risk',
      source: 'calculated',
      title: `${notStarted.length} projects (${MW(mw)}) have no commissioned capacity`,
      summary: `${((mw / (totals.portfolioMW || 1)) * 100).toFixed(0)}% of portfolio capacity has neither a COD nor a trial-run block recorded.`,
      detail:
        `These projects carry capacity in ProjectMapping but no block has reached either milestone in P6. ` +
        `That is expected for projects early in construction; it is a concern where the project is late in ` +
        `its schedule. The payload carries no per-project target date, so this flags the population rather ` +
        `than asserting which of them are late.`,
      metric: {
        label: 'Capacity not yet commissioning',
        value: MW(mw),
        comparison: `${notStarted.length} of ${projects.length} projects`,
      },
      affectedProjects: notStarted
        .sort((a, b) => b.total_capacity - a.total_capacity)
        .map((p) => p.project_name).slice(0, 12),
      affectedMW: mw,
      recommendation: 'Review the largest of these against their construction schedules to separate early-stage from stalled.',
      evidence: 'projects[] where cod_mw = 0 and tr_mw = 0',
      generatedAt: at,
    });
  }

  /* 4 ── Segment mix, where one segment dominates the remaining pipeline. */
  if (upcoming.length && totals.remainingMW > 0) {
    const lead = upcoming[0];
    const share = (lead.mw / totals.remainingMW) * 100;
    if (share >= 55) {
      out.push({
        id: 'pipeline-concentration',
        severity: 'info',
        category: 'Segment mix',
        source: 'calculated',
        title: `${share.toFixed(0)}% of remaining capacity is ${lead.segment}`,
        summary: `${MW(lead.mw)} of the ${MW(totals.remainingMW)} still to commission sits in ${lead.segment}, across ${lead.projectCount} projects.`,
        detail:
          `Remaining capacity is total_capacity minus what has reached COD or trial run. Concentration ` +
          `matters because a delay common to one technology — module supply, turbine logistics, a single ` +
          `EPC — moves the whole remaining pipeline rather than part of it.`,
        metric: {
          label: `${lead.segment} remaining`,
          value: MW(lead.mw),
          comparison: `${share.toFixed(0)}% of all remaining`,
        },
        affectedProjects: lead.projects.map((p) => p.project_name).slice(0, 12),
        affectedMW: lead.mw,
        recommendation: `Stress-test the ${lead.segment} supply chain — the pipeline has limited diversification to absorb a common-mode delay.`,
        evidence: 'projects[].remaining_capacity grouped by type',
        generatedAt: at,
      });
    }
  }

  /* 5 ── Run-rate extrapolation. Stated as arithmetic, not a forecast model. */
  const agg = aggregate(months, 'Monthly');
  const active = agg.filter((p) => p.total > 0);
  if (active.length >= 3 && totals.remainingMW > 0) {
    const perMonth = active.reduce((s, p) => s + p.total, 0) / active.length;
    if (perMonth > 0) {
      const monthsNeeded = totals.remainingMW / perMonth;
      const years = monthsNeeded / 12;
      out.push({
        id: 'run-rate',
        severity: years > 5 ? 'warning' : 'info',
        category: 'Pipeline',
        source: 'calculated',
        title: `At the current rate the remaining pipeline takes ${years >= 1 ? `${years.toFixed(1)} years` : `${Math.round(monthsNeeded)} months`}`,
        summary: `${MW(totals.remainingMW)} remains, against an average of ${MW(perMonth)} added per active month.`,
        detail:
          `This is a straight extrapolation of the observed rate over ${active.length} months with activity — ` +
          `not a schedule and not a model. It assumes commissioning continues at the same pace, which a ` +
          `ramp-up or a lumpy block release would change. Treat it as the "if nothing changes" line.`,
        metric: {
          label: 'Average monthly addition',
          value: MW(perMonth),
          comparison: `${active.length} active months in window`,
        },
        affectedProjects: [],
        affectedMW: totals.remainingMW,
        recommendation: 'Compare against the committed COD dates — a gap here is where the plan relies on acceleration.',
        evidence: 'monthly_trends over the selected window ÷ months with non-zero additions',
        generatedAt: at,
      });
    }
  }

  const rank = { critical: 0, warning: 1, success: 2, info: 3 } as const;
  return out.sort((a, b) => rank[a.severity] - rank[b.severity]);
}
