import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import {
  Package, Sun, Truck, CheckCircle2, Clock, Search, ListChecks,
  AlertTriangle, ChevronDown, ChevronRight, Download, RefreshCw,
  Layers, BarChart3, Sparkles, ShieldCheck, Activity, Zap,
  Bot, X, Send, ArrowRight, Columns3, Info, Calendar
} from 'lucide-react';
import type { ModuleDeliveriesSummary, ModuleProject, LtaRisk, MonthPhase } from './types';
import { PLANNING_RULES } from './planningRules';
import { useChartTheme } from '../../lib/chartTheme';
import { FORECAST_MONTHS, exportModuleDeliveriesXLSX, moduleExportName } from './export';
import {
  ADVANCED_COL_COUNT, AdvancedBlankCells, AdvancedCells, AdvancedHeader, AiDeadlineLine, AiFtcLine,
  AiMonthCell, AiOrderLine, AiTcLine, TD_AI, aiMonths, useAdvancedPlan,
} from './AdvancedColumns';
import { InfoTip } from '../../components/ui/primitives/InfoTip';
import { DeliveryLedger, fmtIsoDate } from './DeliveryLedger';
import { DateHistoryButton, changedToday, changedTodayCell } from '../modules/DateChange';
// Module Ordering, same as the live Ordering Schedule: approvals and the LTA / SCOD reason.
import { ApprovalDialog, ApprovalMark, ApprovalSummary, CLOSE_POPOVERS, WaitingForApproval, covers, useApprovalRole } from '../modules/OrderApproval';
import { DateChangeReason } from '../modules/DateChangeReason';
import type { PendingDate } from '../modules/DateChangeReason';
import type { ModuleProject as LiveProject } from '../modules/types';
import { levelVendorQuota, VENDOR_CAP_MWAC, type LeveledPhase } from './vendorLeveling';
import PriorityMenu, { type PlanPriority } from './PriorityMenu';
import { formatProjectName } from '../../lib/projectName';
import { MiniMeter } from '../../components/ui/primitives/Meter';

import { Loader as AkLoader } from '../../components/ui/primitives';
import AIPredictionPanels, {
  AIForecastModal, AIPriorityModal, aiDate, aiPhaseFor, aiPriorityTone, isScored, phaseName,
} from './AIPredictionPanels';
import type { RowAI, ForecastPhase, OrderTcForecastResponse } from './AIPredictionPanels';

/* AI-predicted values are set apart in brand blue across the table and popups,
   so a model's answer is never mistaken for a plan or SAP figure. */
const AI_TEXT = 'text-brand-blue';
const AI_CELL = 'bg-brand-blue/[0.06]';

/* ── AI month view ────────────────────────────────────────────────────────
   For a project the AI scored, the month grid shows the AI's own ordering plan
   (monthly_requirement.ai: each order's month and MWp) instead of the rule
   engine's. buildAIRowView re-expresses that plan in the row's existing shape
   (month_mwp / month_overdue_mwp / month_phases / module_date / tc_date), so
   every cell, chip and popup renders it with the same code. The rule-engine
   dates it replaces are kept on the row (rule_module_date / rule_tc_date) for
   the "Rule:" comparison. Vendor-quota levelling is a rule-engine step and
   does not apply to the AI plan. */
export type AIRowView = ModuleProject & {
  ai_view: true;
  rule_module_date: string;
  rule_tc_date: string;
  /** AI orders that fall after the last grid month (not drawn in a cell). */
  ai_outside: { month: string; mwp: number }[];
};

const MON3 = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
/** 'Feb-27' -> a sortable month number. NaN when unparsable. */
const monthNum = (mo?: string | null) => {
  const m = (mo || '').match(/^([A-Za-z]{3})-(\d{2})$/);
  if (!m) return NaN;
  const i = MON3.indexOf(m[1].toLowerCase());
  return i < 0 ? NaN : (2000 + Number(m[2])) * 12 + i;
};
const bareLabel = (l?: string | null) => (l || '').replace(/\s*\(.*$/, '').replace(/\s+BL-.*$/i, '').trim().toLowerCase();
const isUnphased = (l?: string | null) => !l || /^(main|project balance|single phase)$/i.test(l.trim());

/** The segment of a "Ph-I (75MW): 29-Dec-26 · …" string for one phase. */
function segFor(segs: ReturnType<typeof splitDateField>, label?: string | null) {
  if (segs.length === 0) return undefined;
  if (isUnphased(label)) return segs.length === 1 ? segs[0] : segs.find(s => !s.label);
  return segs.find(s => bareLabel(s.label) === bareLabel(label)) ?? (segs.length === 1 ? segs[0] : undefined);
}

function buildAIRowView(p: ModuleProject, f: OrderTcForecastResponse): AIRowView | null {
  const plan = f.monthly_requirement?.ai?.months;
  if (!plan) return null;
  const firstNum = monthNum(FORECAST_MONTHS[0]);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const month_mwp: Record<string, number> = Object.fromEntries(FORECAST_MONTHS.map(m => [m, 0]));
  const month_overdue_mwp: Record<string, number> = Object.fromEntries(FORECAST_MONTHS.map(m => [m, 0]));
  const month_phases: Record<string, MonthPhase[]> = Object.fromEntries(FORECAST_MONTHS.map(m => [m, []]));
  const ai_outside: { month: string; mwp: number }[] = [];
  const modSegs = splitDateField(p.module_date);
  const tcSegs = splitDateField(p.tc_date);
  const ftcSegs = splitDateField(p.ftc_date);
  const round1 = (n: number) => Math.round(n * 10) / 10;

  for (const m of plan) {
    const mwp = m.required_at_site_mwp ?? 0;
    if (mwp <= 0) continue;
    const n = monthNum(m.order_month);
    // An order whose month has already gone is placed in the first open
    // month and flagged, as the rule engine does with its own overdue orders.
    const target = Number.isNaN(n) ? undefined
      : n < firstNum ? FORECAST_MONTHS[0]
        : FORECAST_MONTHS.find(x => monthNum(x) === n);
    if (!target) { ai_outside.push({ month: m.order_month || '?', mwp }); continue; }
    const overdue = !!m.overdue || (!!m.order_by_date && new Date(m.order_by_date) < today) || n < firstNum;
    month_mwp[target] += mwp;
    if (overdue) month_overdue_mwp[target] += mwp;

    // "Ph-I (75 MWac)" entries; an unphased order reads "paced by structure completion".
    const parts = (m.phases?.length ? m.phases : ['']).map(s => {
      const label = s.split(' (')[0].trim();
      const ac = s.match(/\(([\d.]+)\s*MWac\)/i);
      return { label: /^ph[-\s]/i.test(label) ? label : '', ac: ac ? parseFloat(ac[1]) : 0 };
    });
    const acSum = parts.reduce((a, x) => a + x.ac, 0);
    parts.forEach(x => {
      const share = acSum > 0 ? x.ac / acSum : 1 / parts.length;
      const label = x.label || (f.phases?.length === 1 && !isUnphased(f.phases[0].phase) ? f.phases[0].phase : 'Main');
      const tc = segFor(tcSegs, label)?.date || '-';
      const ftc = segFor(ftcSegs, label)?.date || '-';
      month_phases[target].push({
        phase_label: label,
        mwp: round1(mwp * share),
        mw_ac: x.ac || round1((m.required_at_site_mwac ?? 0) * share),
        // Rule-engine dates: the chips lead with the AI date and show these as "Rule:".
        order_date: segFor(modSegs, label)?.date || '-',
        tc_date: tc,
        ftc_date: ftc,
        order_month: target,
        delay_months: 0,
        ftc_reachable: true,
        ftc_short_days: 0,
        next_tc_date: tc,
        next_ftc_date: ftc,
        overdue,
        shifted: false,
      });
    });
  }

  // AI date strings in the table's own format, so the calendar chips (TC
  // milestone filter) and milestone-only months follow the AI dates too.
  const seg = (ph: ForecastPhase, iso?: string | null) => {
    const d = aiDate(iso);
    if (!d) return null;
    const lab = phaseName(ph.phase);
    if (!lab) return d;
    const mw = segFor(ftcSegs, lab)?.mwAc;
    return `${lab}${mw ? ` (${mw}MW)` : ''}: ${d}`;
  };
  const phases = f.phases ?? [];
  const cls = (f.priority?.ai || '').toUpperCase();
  return {
    ...p,
    ai_view: true,
    rule_module_date: p.module_date,
    rule_tc_date: p.tc_date,
    ai_outside,
    month_mwp,
    month_overdue_mwp,
    month_phases,
    module_date: phases.map(ph => seg(ph, ph.order_by_date)).filter(Boolean).join(' · '),
    tc_date: phases.map(ph => seg(ph, ph.predicted_tc_date)).filter(Boolean).join(' · '),
    // Cell colour follows the AI priority; quota-levelling flags do not apply.
    priority: cls === 'P1' ? 'P1' : cls === 'P2' ? 'P2' : 'standard',
    planning_flags: [],
  } as AIRowView;
}

/** One phase of the AI forecast as the table's "Ph-I: 13-May-27 · …" segments,
 *  for the Module Ordering / TC Delivery columns. */
function AIDatedPhases({ phases, pick }: { phases: ForecastPhase[]; pick: (ph: ForecastPhase) => string | null | undefined }) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return (
    <span className={`font-semibold ${AI_TEXT}`}>
      {phases.map((ph, i) => {
        const iso = pick(ph);
        const shown = aiDate(iso);
        const overdue = !!iso && new Date(iso) < today;
        const label = phaseName(ph.phase);
        return (
          <React.Fragment key={ph.phase}>
            {i > 0 && <span className="text-muted-foreground/40"> · </span>}
            <span className={overdue ? 'text-[var(--status-critical-fg)]' : undefined}>
              {label ? `${label}: ` : ''}{shown ?? <span className="font-normal text-muted-foreground">nothing to order</span>}
            </span>
          </React.Fragment>
        );
      })}
    </span>
  );
}
/* ═══════════════════════════════════════════════════════════════════════════
   MODULE DELIVERIES & FORECAST
   CEO-grade view replicating the PDF tracker with live SAP/P6/TC data.
   ═══════════════════════════════════════════════════════════════════════════ */

const API = import.meta.env.VITE_API_BASE || '';

/* The LTA alert rule (user rule 2026-09-23): a PPA project's LTA must not
   cross its SCOD, every other project's must not cross its AOP (Plan).
   Evaluated on the server against the real dates — see the lta_risk block in
   backend/routers/module_deliveries.py — so nothing here re-parses the
   formatted date strings. A project with no basis date is not flagged. */
const isLTADelayed = (p: ModuleProject) => p.lta_risk?.breached === true;

/** "LTA crosses SCOD by 92 days" — the one phrasing, used in cell and banner. */
const ltaBreachLine = (r: LtaRisk) =>
  `LTA crosses ${r.basis} by ${r.days_late} day${r.days_late === 1 ? '' : 's'}`;

const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Column index where each logical section starts — drives the divider rules. */
const SECTION_EDGE = 'border-l border-border';

// Total <th>/<td> count in the table body, for the group-header row's colSpan.
// A hardcoded 40 here silently went stale when FTC/TC/Module moved after the
// month block — the grouped-by-EPC header row then stopped short of the new
// columns, leaving them uncoloured (user report 2026-09-20). 25 lead columns
// (Sr..Status) + the 4 Ariba proof columns + Priority (AI) + the month block
// (FORECAST_MONTHS + its Total) + FTC / Module Ordering / PO Placed / TC + Remarks.
const TABLE_COLUMN_COUNT = 26 + 4 + 1 + (FORECAST_MONTHS.length + 1) + 4 + 1;

/** '07-Mar-27' -> '2027-03-07' for an <input type="date"> value */
function scodToInputValue(scod: string): string {
  const m = scod.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{2})$/);
  if (!m) return '';
  const monIdx = MONTH_ABBR.findIndex(a => a.toLowerCase() === m[2].toLowerCase());
  if (monIdx === -1) return '';
  return `20${m[3]}-${String(monIdx + 1).padStart(2, '0')}-${m[1].padStart(2, '0')}`;
}

// Whether ANY phase's module date falls within the next 14 days — but not
// already past. "Already past" is no longer a frontend date-parsing guess:
// the planning engine now authoritatively flags that via
// `excluded_module_date_mwp` (a phase whose module date has already passed
// is excluded from the plan entirely — user decision 2026-09-21), so the
// notification banner reads that field instead of re-deriving "overdue"
// here, and this helper only needs to cover the still-upcoming case.
function hasApproachingDate(dateStr: string): boolean {
  if (!dateStr) return false;
  const matches = dateStr.match(/\d{2}-[a-zA-Z]{3}-\d{2}/g);
  if (!matches) return false;

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (const m of matches) {
    const parts = m.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{2})$/);
    if (!parts) continue;
    const monIdx = MONTH_ABBR.findIndex(a => a.toLowerCase() === parts[2].toLowerCase());
    const dt = new Date(2000 + parseInt(parts[3], 10), monIdx, parseInt(parts[1], 10));

    const diffDays = (dt.getTime() - today.getTime()) / (1000 * 3600 * 24);
    if (diffDays >= 0 && diffDays <= 14) {
      return true;
    }
  }
  return false;
}

/** Parses one 'dd-Mon-yy' token (as found inside FTC/TC/Module Date strings) to a Date, or null. */
function parseTrackerDate(token: string): Date | null {
  const m = token.match(/(\d{1,2})-([A-Za-z]{3})-(\d{2})/);
  if (!m) return null;
  const monIdx = MONTH_ABBR.findIndex(a => a.toLowerCase() === m[2].toLowerCase());
  if (monIdx === -1) return null;
  return new Date(2000 + parseInt(m[3], 10), monIdx, parseInt(m[1], 10));
}

/** FTC/TC/Module Date cells hold one or more '·'-separated phase entries
 *  ("Ph-I (150MW): 20-Jun-26 · Ph-II (150MW): 17-Jul-26"). A phase whose date
 *  has already passed needs its own order placed NOW rather than on the
 *  forward plan, so it's coloured apart from phases still ahead of today
 *  (user decision 2026-09-21) instead of reading as one uniform string.
 */
function DatedPhases({ value }: { value: string }) {
  if (!value) return <>-</>;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const segments = value.split(' · ');
  return (
    <>
      {segments.map((seg, i) => {
        const dt = parseTrackerDate(seg);
        const overdue = dt !== null && dt < today;
        return (
          <React.Fragment key={i}>
            {i > 0 && <span className="text-muted-foreground/40"> · </span>}
            <span className={overdue ? 'text-[var(--status-critical-fg)] font-semibold' : undefined}>{seg}</span>
          </React.Fragment>
        );
      })}
    </>
  );
}

/** One segment of a "Ph-I (50MW): 11-Aug-26 · Ph-II (50MW): 20-Aug-26" style
 *  date string: the phase label (null when unphased), its stated AC capacity,
 *  and the date. */
function splitDateField(dateStr: string | null | undefined): { label: string | null; mwAc: number; date: string }[] {
  return (dateStr || '').split(' · ').map(s => s.trim()).filter(Boolean).map(seg => {
    const colonIdx = seg.indexOf(':');
    let label: string | null = null;
    let rest = seg;
    if (colonIdx !== -1) {
      label = seg.slice(0, colonIdx).trim();
      rest = seg.slice(colonIdx + 1).trim();
    }
    const dateMatch = rest.match(/\d{1,2}-[A-Za-z]{3}-\d{2,4}/);
    const date = dateMatch ? dateMatch[0] : rest;
    const mwMatch = label ? label.match(/\(([\d.]+)\s*MW\)/i) : null;
    // The "(50MW)" suffix is only there to carry the capacity — strip it once
    // read, so the phase label shown is just "Ph-I".
    const cleanLabel = label ? label.replace(/\s*\([^)]*\)\s*$/, '').trim() || null : null;
    return { label: cleanLabel, mwAc: mwMatch ? parseFloat(mwMatch[1]) : 0, date };
  });
}

/** "11-Aug-26" -> "Aug-26", to compare against a FORECAST_MONTHS entry. */
function monthOfDate(dateStr: string): string {
  const m = dateStr.match(/\d{1,2}-([A-Za-z]{3})-(\d{2})/);
  return m ? `${m[1]}-${m[2]}` : '';
}

/** The Module Order / TC / FTC grid for a milestone-only month (month_phases
 *  has no entry for it — the order was placed in a different month, this is
 *  only when the milestone lands), rebuilt from the project's own
 *  module_date/tc_date/ftc_date strings so the grid still shows real dates
 *  instead of going blank (user 2026-09-24: "we need to do showing all
 *  dates" — restoring what the page showed before month_phases existed).
 *
 *  No delay_months/ftc_reachable is computed here — those are the planner's
 *  scheduling judgement on a real order, and this is not one; the values are
 *  left at their "nothing to report" defaults so the Chip renders the date
 *  alone. */
function buildFallbackPhases(p: ModuleProject, mo: string): MonthPhase[] {
  const modSegs = splitDateField(p.module_date);
  const tcSegs = splitDateField(p.tc_date);
  const ftcSegs = splitDateField(p.ftc_date);
  const all = [...modSegs, ...tcSegs, ...ftcSegs];
  const relevant = new Set<string | null>();
  all.forEach(s => { if (monthOfDate(s.date) === mo) relevant.add(s.label); });
  if (relevant.size === 0) return [];

  const pick = (segs: typeof modSegs, label: string | null) =>
    segs.find(s => s.label === label) ?? (segs.length === 1 ? segs[0] : undefined);
  const ol = p.ol > 0 ? p.ol : 1.35;

  return Array.from(relevant).map(label => {
    const m = pick(modSegs, label);
    const t = pick(tcSegs, label);
    const f = pick(ftcSegs, label);
    const mwAc = m?.mwAc || t?.mwAc || f?.mwAc || 0;
    return {
      phase_label: label || 'Main',
      mwp: Math.round(mwAc * ol * 10) / 10,
      mw_ac: mwAc,
      order_date: m?.date || '-',
      tc_date: t?.date || '-',
      ftc_date: f?.date || '-',
      order_month: '',
      delay_months: 0,
      ftc_reachable: true,
      ftc_short_days: 0,
      next_tc_date: t?.date || '-',
      next_ftc_date: f?.date || '-',
      overdue: false,
      shifted: false,
    };
  });
}

type ChipData = { label: string; phase: string | null; type: 'module' | 'tc' | 'ftc' };
function getChipsForMonth(p: any, mo: string, cellVal: number, milestoneFilter: string, unitToggle: 'both' | 'mwp' | 'mwac' = 'both'): ChipData[] {
  const chips: ChipData[] = [];
  if (!p.balance_ordering_mwp || p.balance_ordering_mwp <= 0) return chips;

  // The cellVal tracks Module Ordering, so it represents the Blue chip
  if (cellVal > 0) {
      const ac = Math.round(p.ol > 0 ? cellVal / p.ol : cellVal / 1.35);
      const labelStr = unitToggle === 'mwp' ? `${Math.round(cellVal)}` : unitToggle === 'mwac' ? `${ac}` : `${Math.round(cellVal)} / ${ac}`;
      chips.push({ label: labelStr, phase: null, type: 'module' });
  }

  const now = new Date();

  const parseSegments = (val: string, type: 'module' | 'tc' | 'ftc') => {
    if (!val) return;
    let totalDc = 0;
    let totalAc = 0;
    let validCount = 0;
    let hasStringFallback = false;
    let stringFallbackLabel = '';

    val.split(' · ').forEach(seg => {
      if (seg.includes(mo)) {
        // Parse actual date from segment and skip if already passed
        const dateMatch = seg.match(/(\d{1,2})-([A-Za-z]{3})-(\d{2,4})/);
        if (dateMatch) {
          const parsed = new Date(`${dateMatch[2]} ${dateMatch[1]}, 20${dateMatch[3].length === 2 ? dateMatch[3] : dateMatch[3].slice(-2)}`);
          if (!isNaN(parsed.getTime()) && parsed < now) return; // Skip past dates
        }

        const parts = seg.split(': ');
        if (parts.length > 1) {
          const mwMatch = parts[0].match(/\((.*?MW)\)/i);
          if (mwMatch) {
            const acMatch = mwMatch[1].match(/([\d\.]+)/);
            if (acMatch) {
              const ac = parseFloat(acMatch[1]);
              const dc = Math.round(ac * (p.ol > 0 ? p.ol : 1.35));
              totalDc += dc;
              totalAc += ac;
              validCount++;
            } else {
              hasStringFallback = true;
              stringFallbackLabel = mwMatch[1];
            }
          } else {
            hasStringFallback = true;
            stringFallbackLabel = '-';
          }
        } else {
          const phasesCount = val.split(' · ').length;
          const dc = p.balance_ordering_mwp / (phasesCount || 1);
          const ac = Math.round(p.ol > 0 ? dc / p.ol : dc / 1.35);
          totalDc += dc;
          totalAc += ac;
          validCount++;
        }
      }
    });

    if (validCount > 0) {
      const roundedDc = Math.round(totalDc);
      const roundedAc = Math.round(totalAc);
      const labelStr = unitToggle === 'mwp' ? `${roundedDc}` : unitToggle === 'mwac' ? `${roundedAc}` : `${roundedDc} / ${roundedAc}`;
      // Add ' xN' if grouped? User asked to combine them. We'll just show the combined sum, 
      // the tooltip already breaks down the individual phases.
      chips.push({ label: labelStr, phase: validCount > 1 ? `Combined (${validCount})` : null, type });
    } else if (hasStringFallback) {
      chips.push({ label: stringFallbackLabel, phase: null, type });
    }
  };
  
  // DB tc_date = TC Delivery dates (later) → Yellow chips  
  parseSegments(p.tc_date, 'tc');
  // FTC Date (Green)
  parseSegments(p.ftc_date, 'ftc');
  return chips.filter(c => milestoneFilter === 'all' || c.type === milestoneFilter);
}

const container = { hidden: { opacity: 0 }, show: { opacity: 1, transition: { staggerChildren: 0.04 } } };
const item = { hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0, transition: { duration: 0.25 } } };

/* ── Rich Tooltip Content Formatter with Vibrant Date & Days Styling ────── */
function renderHighlightedText(rawText: string) {
  if (!rawText) return null;

  // Split into the remark vs its suggested action (both rule-based, written by the planning engine)
  const parts = rawText.split(/(?=💡 Suggested action:)/g);

  return (
    <div className="space-y-2">
      {parts.map((part, pIdx) => {
        const isSuggestion = part.trim().startsWith('💡 Suggested action:');
        const contentText = isSuggestion ? part.replace('💡 Suggested action:', '').trim() : part.trim();

        // Match exact DD-Mon-YY, Mon-YY, X days overdue, X days remaining, due today, gain X days, lead times, and plain days
        const regex = /(\b\d{1,2}-[A-Za-z]{3}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}\b|\b\d+\s*days?\s*(?:overdue|remaining)\b|\bdue\s*today\b|\bgain\s*\d+\s*days\b|\b\d+d\b|\b\d+\s*days\b)/gi;
        const tokens = contentText.split(regex);

        const renderedTokens = tokens.map((tok, tIdx) => {
          if (!tok) return null;
          // Exact date DD-Mon-YY (e.g. 20-Sep-26, 30-Apr-26)
          if (/^\d{1,2}-[A-Za-z]{3}-\d{2}$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-mono font-bold text-status-risk-fg bg-status-risk-bg border border-status-risk-border">
                {tok}
              </span>
            );
          }
          // Month-Year (e.g. Sep-26, May-26)
          if (/^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-mono font-bold text-status-healthy-fg bg-status-healthy-bg border border-status-healthy-border">
                {tok}
              </span>
            );
          }
          // X days overdue
          if (/days?\s*overdue/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-bold text-status-critical-fg bg-status-critical-bg border border-status-critical-border shadow-sm">
                ⚠️ {tok}
              </span>
            );
          }
          // X days remaining / due today
          if (/days?\s*remaining|due\s*today/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-bold text-cyan-300 bg-cyan-500/20 border border-cyan-500/40">
                ⏱️ {tok}
              </span>
            );
          }
          // gain X days
          if (/gain\s*\d+\s*days/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-bold text-status-healthy-fg bg-status-healthy-bg border border-status-healthy-border">
                ⚡ {tok}
              </span>
            );
          }
          // Lead time (e.g. 98d, 136d, 45d)
          if (/^\d+d$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-mono font-bold text-status-ai-fg bg-status-ai-bg border border-status-ai-border">
                {tok}
              </span>
            );
          }
          // General days mention (e.g. 30 days, 45 days)
          if (/^\d+\s*days$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1 py-0.5 mx-0.5 rounded font-medium text-status-risk-fg bg-status-risk-bg border border-status-risk-border">
                {tok}
              </span>
            );
          }
          return <span key={tIdx}>{tok}</span>;
        });

        if (isSuggestion) {
          return (
            <div key={pIdx} className="mt-2.5 pt-2 border-t border-border-default bg-primary/10 -mx-1 px-3 py-2 rounded-lg border border-primary/30">
              <div className="flex items-center gap-1.5 text-[11px] font-bold text-status-risk-fg mb-1">
                <span>💡 Suggested action</span>
              </div>
              <div className="text-[11px] leading-relaxed text-fg-primary font-normal">
                {renderedTokens}
              </div>
            </div>
          );
        }

        return (
          <div key={pIdx} className="text-[11px] leading-relaxed text-fg-primary font-normal">
            {renderedTokens}
          </div>
        );
      })}
    </div>
  );
}

function Tip({
  text,
  content,
  children,
  className = '',
  wide = false,
}: {
  text?: string | null;
  content?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  wide?: boolean;
}) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number; below: boolean }>({ x: 0, y: 0, below: false });
  const wrapRef = React.useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!show) return;
    const handleGlobalClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setShow(false);
      }
    };
    const close = () => setShow(false);
    document.addEventListener('mousedown', handleGlobalClick);
    window.addEventListener(CLOSE_POPOVERS, close);
    return () => {
      document.removeEventListener('mousedown', handleGlobalClick);
      window.removeEventListener(CLOSE_POPOVERS, close);
    };
  }, [show]);

  if (!text && !content) return <>{children}</>;

  const isDetailed = wide || (text && (text.length > 60 || text.includes('FTC') || text.includes('Suggested action')));
  const targetWidth = isDetailed ? 900 : 260;

  const toggleTip = (e: React.MouseEvent) => {
    if (show) {
      setShow(false);
      return;
    }
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const vw = typeof window !== 'undefined' ? window.innerWidth : 1200;
    
    // Effective tooltip width clamped to available screen width
    const effectiveW = Math.min(targetWidth, vw - 32);
    const halfW = effectiveW / 2;

    // Ideal center over trigger element
    const idealX = rect.left + rect.width / 2;

    // Strictly clamp left position so [left - halfW, left + halfW] is fully within [16, vw - 16]
    const clampedX = Math.max(halfW + 16, Math.min(vw - halfW - 16, idealX));

    // Vertical placement: if element is near the top of viewport, render tooltip below.
    const clearanceThreshold = content ? 380 : (isDetailed ? 250 : 150);
    const showBelow = rect.top < clearanceThreshold;
    const targetY = showBelow ? rect.bottom + 8 : rect.top - 8;

    setPos({ x: clampedX, y: targetY, below: showBelow });
    setShow(true);
  };

  const vw = typeof window !== 'undefined' ? window.innerWidth : 1200;
  const renderWidth = Math.min(targetWidth, vw - 32);

  return (
    <span
      ref={wrapRef}
      className={`cursor-pointer ${className}`}
      onClick={toggleTip}
    >
      {children}
      {show && (
        <span
          style={{ left: pos.x, top: pos.y }}
          className={`fixed z-[9999] -translate-x-1/2 ${pos.below ? 'translate-y-0' : '-translate-y-full'} animate-[tipIn_150ms_ease-out]`}
          onClick={(e) => e.stopPropagation()}
        >
          <span
            style={{ width: 'max-content', maxWidth: `${renderWidth}px` }}
            className="block rounded-xl border border-border-default bg-popover/95 p-3.5 text-left text-[11px] font-medium leading-relaxed text-fg-primary shadow-lg shadow-black/10 backdrop-blur-md dark:shadow-black/40 whitespace-pre-line break-words cursor-auto"
          >
            {content ? content : text ? renderHighlightedText(text) : null}
          </span>
        </span>
      )}
    </span>
  );
}

// Every MWp figure across this table (capacity, ordered, erected, FTC
// completed, the AI's month-wise allocations, ...) is rounded to a whole
// number — one decimal place read as false precision on what are mostly
// derived/apportioned figures anyway (user decision 2026-09-21).
const MW = (n: number) => Math.round(n).toLocaleString('en-IN');
const sum = <T,>(rows: T[], pick: (r: T) => number) => rows.reduce((s, r) => s + (pick(r) || 0), 0);

/* ── Status Badge ────────────────────────────────────────────────────────── */
function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { cls: string; label: string; icon: React.ReactNode }> = {
    delivered: { cls: 'status-pill-healthy', label: 'Delivered', icon: <CheckCircle2 className="w-3 h-3" /> },
    in_progress: { cls: 'status-pill-risk', label: 'In Progress', icon: <Truck className="w-3 h-3" /> },
    ordered: { cls: 'status-pill-done', label: 'Ordered', icon: <Clock className="w-3 h-3" /> },
    pending: { cls: 'status-pill', label: 'Pending', icon: <Clock className="w-3 h-3" /> },
  };
  const c = cfg[status] || cfg.pending;
  return <span className={`${c.cls} inline-flex items-center gap-1`}>{c.icon}{c.label}</span>;
}

/* ── Progress Ring ───────────────────────────────────────────────────────── */
function ProgressRing({ pct, size = 36, stroke = 3, color = 'var(--primary-600)' }: { pct: number; size?: number; stroke?: number; color?: string }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - Math.min(pct, 1));
  return (
    <svg width={size} height={size} className="shrink-0 -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border-subtle)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
        className="transition-all duration-700"
      />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central"
        className="fill-[var(--fg-primary)] text-[8px] font-bold rotate-90" style={{ transformOrigin: 'center' }}>
        {Math.round(pct * 100)}%
      </text>
    </svg>
  );
}

/* ── KPI Card ────────────────────────────────────────────────────────────── */
function KpiCard({ title, value, unit, sub, icon: Icon, tint, pct }: {
  title: string; value: number; unit: string; sub?: string;
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>; tint: string; pct?: number;
}) {
  return (
    <motion.div variants={item}
      className="kpi-card group flex flex-col rounded-xl border border-border bg-card p-3 transition-all hover:-translate-y-0.5"
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: tint }} />
        <span className="section-label truncate text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</span>
      </div>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-light tabular-nums text-foreground leading-none">{MW(value)}</p>
          <p className="mt-0.5 text-[10px] text-muted-foreground">{unit}</p>
          {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
        </div>
        {pct !== undefined && <ProgressRing pct={pct} color={tint} />}
      </div>
    </motion.div>
  );
}

/* ── Table chrome, matching the printed tracker ───────────────────────────
   The header is a solid inverted band with stacked unit labels, and every
   cell carries a hairline grid, exactly as the PDF reads. The neutral scale
   flips between themes, so neutral-900 on neutral-50 stays a strong band in
   both light and dark rather than hardcoding black. */
const GRID_LINE = 'border-b border-r border-[var(--border-subtle)]';

/** Header label with its unit stacked underneath, as the tracker prints it. */
function ThLabel({ label, unit }: { label: string; unit?: string }) {
  return (
    <>
      {label}
      {unit && <><br /><span className="font-semibold opacity-80">{unit}</span></>}
    </>
  );
}

function Th({ children, className = '', stickyLeft, rowSpan, colSpan, tip }: {
  children: React.ReactNode; className?: string; stickyLeft?: number; rowSpan?: number; colSpan?: number; tip?: string;
}) {
  const inner = (
    <th
      rowSpan={rowSpan} colSpan={colSpan}
      style={stickyLeft !== undefined ? { left: stickyLeft } : undefined}
      className={`px-1.5 py-1.5 align-middle text-center text-[9px] font-bold leading-[1.2] tracking-tight border-b border-r border-[var(--neutral-700)] bg-[var(--neutral-900)] text-[var(--neutral-50)] ${stickyLeft !== undefined ? 'sticky z-30' : ''} ${className}`}
    >
      {tip ? <Tip text={tip}>{children}</Tip> : children}
    </th>
  );
  return inner;
}

/** Centre is the default — the tracker centres every short code, date and
    flag, and only the name and remarks columns run left. */
function Td({ children, className = '', stickyLeft, align = 'center', tip, tipContent, tipWide, colSpan }: {
  children?: React.ReactNode; className?: string; stickyLeft?: number; align?: 'left' | 'center' | 'right'; tip?: string; tipContent?: React.ReactNode; tipWide?: boolean; colSpan?: number;
}) {
  const alignCls = align === 'right' ? 'text-right' : align === 'left' ? 'text-left' : 'text-center';
  return (
    <td
      colSpan={colSpan}
      style={stickyLeft !== undefined ? { left: stickyLeft } : undefined}
      className={`px-1.5 py-[3px] text-[10px] leading-[1.35] tabular-nums whitespace-nowrap ${GRID_LINE} ${alignCls} ${stickyLeft !== undefined ? 'sticky z-20' : ''} ${className}`}
    >
      {tipContent ? <Tip content={tipContent} wide={tipWide}>{children}</Tip> : tip ? <Tip text={tip}>{children}</Tip> : children}
    </td>
  );
}

/* ── MW Cell with conditional coloring ───────────────────────────────────── */
function MwCell({ value, cap, className = '' }: { value: number; cap: number; className?: string }) {
  const pct = cap > 0 ? value / cap : 0;
  const color = value === 0 ? 'text-muted-foreground' : pct >= 0.95 ? 'text-status-healthy-fg dark:text-status-healthy-fg font-medium' : pct >= 0.5 ? 'text-foreground' : 'text-status-risk-fg dark:text-status-risk-fg';
  return <Td align="right" className={`${color} ${className}`}>{value > 0 ? MW(value) : '-'}</Td>;
}

/* ── Best-in-Class Priority & Quota Cell Theming ────────────────────────── */
function getMonthCellTheme(
  val: number,
  priority: string | undefined,
  flags: string[] | undefined,
  /** This month's figure includes demand whose ordering window has already
   *  closed. Outranks every other state: a date we have already missed is the
   *  most urgent thing the cell can be saying. */
  isOverdue = false
) {
  if (val <= 0) {
    return {
      cellClass: 'text-muted-foreground/25',
      badgeClass: '',
      dotColor: '',
      label: '-',
      tag: '',
    };
  }

  if (isOverdue) {
    return {
      cellClass: 'bg-status-critical-bg dark:bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg font-semibold ring-1 ring-inset ring-status-critical-solid hover:bg-status-critical-bg transition-colors',
      badgeClass: 'bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg border border-status-critical-solid',
      dotColor: 'bg-status-critical-solid',
      label: MW(val),
      tag: 'Overdue — ordering window already passed, placed in the earliest open month',
    };
  }

  const p = (priority || 'standard').toLowerCase();
  const isLeveled = flags?.includes('leveled_early');
  const isDelayed = flags?.includes('capacity_delayed');
  const isLtaExtended = flags?.includes('extended_to_lta');

  if (p === 'p1') {
    return {
      cellClass: 'bg-status-critical-bg dark:bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg font-semibold border-y border-status-critical-border hover:bg-status-critical-bg transition-colors',
      badgeClass: 'bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg border border-status-critical-border',
      dotColor: 'bg-status-critical-bg ring-2 ring-status-critical-border',
      label: MW(val),
      tag: 'P1 Priority (Critical COD/PPA)',
    };
  }

  if (p === 'p2') {
    return {
      cellClass: 'bg-status-risk-bg dark:bg-status-risk-bg text-status-risk-fg dark:text-status-risk-fg font-semibold border-y border-status-risk-border hover:bg-status-risk-bg transition-colors',
      badgeClass: 'bg-status-risk-bg text-status-risk-fg dark:text-status-risk-fg border border-status-risk-border',
      dotColor: 'bg-status-risk-bg',
      label: MW(val),
      tag: 'P2 Priority (Fast-Track)',
    };
  }

  if (isDelayed) {
    return {
      cellClass: 'bg-status-critical-bg dark:bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg font-semibold border-y border-status-critical-border hover:bg-status-critical-bg transition-colors',
      badgeClass: 'bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg border border-status-critical-border',
      dotColor: 'bg-status-critical-bg',
      label: MW(val),
      tag: 'Delayed past LTA (Vendor Quota Full, Critical Commercial Risk)',
    };
  }

  if (isLtaExtended) {
    return {
      cellClass: 'bg-status-risk-bg dark:bg-status-risk-bg text-status-risk-fg dark:text-status-risk-fg font-semibold border-y border-status-risk-border hover:bg-status-risk-bg transition-colors',
      badgeClass: 'bg-status-risk-bg text-status-risk-fg dark:text-status-risk-fg border border-status-risk-border',
      dotColor: 'bg-status-risk-bg',
      label: MW(val),
      tag: 'Extended to LTA (Vendor Quota Full, Safe for Transmission)',
    };
  }

  if (isLeveled) {
    return {
      cellClass: 'bg-status-ai-bg dark:bg-status-ai-bg text-status-ai-fg dark:text-status-ai-fg font-semibold border-y border-status-ai-border hover:bg-status-ai-bg transition-colors',
      badgeClass: 'bg-status-ai-bg text-status-ai-fg dark:text-status-ai-fg border border-status-ai-border',
      dotColor: 'bg-status-ai-bg',
      label: MW(val),
      tag: 'Quota Leveled (Pulled Early)',
    };
  }

  return {
    cellClass: 'bg-status-healthy-bg dark:bg-status-healthy-bg text-status-healthy-fg dark:text-status-healthy-fg font-medium border-y border-status-healthy-border hover:bg-status-healthy-bg transition-colors',
    badgeClass: 'bg-status-healthy-bg text-status-healthy-fg dark:text-status-healthy-fg border border-status-healthy-border',
    dotColor: 'bg-status-healthy-bg',
    label: MW(val),
    tag: 'Standard Schedule',
  };
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN PAGE COMPONENT
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Column Visibility System ─────────────────────────────────────────────
   Default-visible columns are the ones the user most frequently needs.
   The remaining columns are hidden by default but can be toggled on via
   a "Columns" dropdown in the toolbar. */
type ColumnKey =
  | 'project' | 'p6_name' | 'spv' | 'plot' | 'category' | 'type' | 'mms_type'
  | 'epc' | 'priority' | 'ol' | 'capacity_mwac' | 'capacity_mwp'
  | 'ftc_completed' | 'connectivity' | 'lta' | 'scod' | 'aop'
  | 'ordered' | 'balance_ordering' | 'total_receipt' | 'erection_done'
  | 'module_inventory' | 'under_transit'
  | 'ariba_grn' | 'awaiting_grn' | 'checklist_status' | 'deliveries'
  | 'balance_dispatch' | 'ai_priority' | 'status'
  | 'month_wise' | 'ftc_date' | 'module_ordering_date' | 'po_placed' | 'tc_delivery_date' | 'remarks';

const ALL_COLUMNS: { key: ColumnKey; label: string }[] = [
  { key: 'project', label: 'Project' },
  { key: 'p6_name', label: 'P6 Name' },
  { key: 'spv', label: 'SPV' },
  { key: 'plot', label: 'Plot' },
  { key: 'category', label: 'Category' },
  { key: 'type', label: 'Type' },
  { key: 'mms_type', label: 'MMS Type' },
  { key: 'epc', label: 'AGEL / EPC' },
  // Beta: the visible "Priority" column is the AI one; this is the planner's own toggle.
  { key: 'priority', label: 'Priority (Plan)' },
  { key: 'ol', label: 'OL' },
  { key: 'capacity_mwac', label: 'Capacity (MWac)' },
  { key: 'capacity_mwp', label: 'Capacity (MWp)' },
  { key: 'ftc_completed', label: 'FTC Completed' },
  { key: 'connectivity', label: 'Connectivity Phase' },
  { key: 'lta', label: 'LTA' },
  { key: 'scod', label: 'SCOD' },
  { key: 'aop', label: 'AOP' },
  { key: 'ordered', label: 'Ordered' },
  { key: 'balance_ordering', label: 'Balance Ordering' },
  { key: 'total_receipt', label: 'Total Receipt' },
  { key: 'erection_done', label: 'Erection Done' },
  { key: 'module_inventory', label: 'Module Inventory' },
  { key: 'under_transit', label: 'Under Transit' },
  { key: 'ariba_grn', label: 'Ariba GRN (proof)' },
  { key: 'awaiting_grn', label: 'Awaiting GRN' },
  { key: 'checklist_status', label: 'Finance Checklist' },
  { key: 'deliveries', label: 'Delivery Ledger' },
  { key: 'balance_dispatch', label: 'Balance Dispatch' },
  { key: 'ai_priority', label: 'Priority' },
  { key: 'status', label: 'Status' },
  { key: 'month_wise', label: 'Month Wise Allocation' },
  { key: 'ftc_date', label: 'FTC Date' },
  { key: 'module_ordering_date', label: 'Module Ordering Date (Plan)' },
  { key: 'po_placed', label: 'PO Placed (Actual)' },
  { key: 'tc_delivery_date', label: 'TC Delivery Date' },
  { key: 'remarks', label: 'Remarks' },
];

const DEFAULT_VISIBLE: Set<ColumnKey> = new Set([
  'project', 'spv', 'plot',
  'capacity_mwac', 'capacity_mwp', 'ftc_completed',
  'lta', 'scod', 'aop',
  'ordered', 'balance_ordering', 'total_receipt',
  'erection_done', 'module_inventory', 'under_transit',
  'ariba_grn', 'awaiting_grn', 'checklist_status', 'deliveries', 'balance_dispatch',
  'ai_priority',
  'month_wise', 'remarks',
]);
const ALL_COLUMN_KEYS = new Set<string>(ALL_COLUMNS.map(c => c.key));
/** Shown while Advanced AI planning is on: they carry the original vs AI dates. */
const ADVANCED_DATE_COLS = new Set<ColumnKey>(['ftc_date', 'module_ordering_date', 'tc_delivery_date']);
// Beta keeps its own saved layout, so saving columns here never changes the live page.
const COLS_STORAGE_KEY = 'akasha_mod_cols_beta_v1';

/** `advanced`: the Advanced AI planning switch (OrderingSchedule) - adds the
    site-driven columns; the schedule itself is unchanged. */
export default function ModuleDeliveriesPage({ advanced = false, weather = false }: { advanced?: boolean; weather?: boolean } = {}) {
  const [data, setData] = useState<ModuleDeliveriesSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [groupBy, setGroupBy] = useState<'epc' | 'category' | 'type' | 'none'>('epc');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [editingScodId, setEditingScodId] = useState<number | null>(null);
  const [savingScodId, setSavingScodId] = useState<number | null>(null);
  const [editingLtaId, setEditingLtaId] = useState<number | null>(null);
  const [savingLtaId, setSavingLtaId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  // The printed tracker covers Khavda projects not yet commissioned (33 rows).
  // Default to that so the figures reconcile with it; 'all' reveals the wider
  // portfolio (Rajasthan, commissioned, and Khavda projects the PDF omits).
  const [scope, setScope] = useState<'tracker' | 'all'>('tracker');
  const [milestoneFilter, setMilestoneFilter] = useState<'all' | 'module' | 'tc' | 'ftc'>('module');
  const [unitToggle, setUnitToggle] = useState<'both' | 'mwp' | 'mwac'>('mwp');
  const [rulesOpen, setRulesOpen] = useState(false);
  const [visibleCols, setVisibleCols] = useState<Set<ColumnKey>>(() => {
    try {
      const saved = localStorage.getItem(COLS_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        // Drop keys of columns that no longer exist, so a saved layout cannot
        // hide a renamed column or reference a removed one.
        const keys = Array.isArray(parsed) ? parsed.filter((k): k is ColumnKey => ALL_COLUMN_KEYS.has(k)) : [];
        if (keys.length > 0) return new Set(keys);
      }
    } catch { /* storage unavailable — fall back to the defaults */ }
    return new Set(DEFAULT_VISIBLE);
  });

  const saveColumnsLayout = () => {
    try { localStorage.setItem(COLS_STORAGE_KEY, JSON.stringify(Array.from(visibleCols))); } catch { /* not persisted */ }
  };
  // Projects whose delivery ledger is open under their row.
  const [openLedgers, setOpenLedgers] = useState<Set<number>>(new Set());
  const toggleLedger = (id: number) => setOpenLedgers(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const [colDropdownOpen, setColDropdownOpen] = useState(false);
  const [isLegendOpen, setIsLegendOpen] = useState(false);
  const [insightsOpen, setInsightsOpen] = useState(false);
  // Optimistic tracking state — keeps the UI stable while the PUT is in flight
  const [trackingOverrides, setTrackingOverrides] = useState<Record<number, boolean>>({});
  const colDropdownRef = React.useRef<HTMLDivElement>(null);

  const isColVisible = useCallback((key: ColumnKey) => visibleCols.has(key) || (advanced && ADVANCED_DATE_COLS.has(key)),
    [visibleCols, advanced]);
  const toggleCol = useCallback((key: ColumnKey) => {
    setVisibleCols(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }, []);

  // Close column dropdown on outside click
  useEffect(() => {
    if (!colDropdownOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (colDropdownRef.current && !colDropdownRef.current.contains(e.target as Node)) {
        setColDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [colDropdownOpen]);
  const chartTheme = useChartTheme();

  // AI Strategic Planning & Priority States
  const [scenario, setScenario] = useState<'v1_baseline' | 'v2_strategic' | 'v3_commercial'>('v2_strategic');
  const [priorities, setPriorities] = useState<Record<number, string>>({});
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [copilotQuery, setCopilotQuery] = useState('');
  const [copilotMessages, setCopilotMessages] = useState<Array<{ role: 'user' | 'assistant'; text: string; time: string }>>([
    {
      role: 'assistant',
      text: 'Hello! I am your Akasha Strategic Module Planning Copilot. I analyze backward scheduling from FTC milestones, origin supplier quotas, PPA commitments, and laydown readiness. How can I assist your delivery optimization today?',
      time: 'Just now',
    },
  ]);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [activePerspectiveProject, setActivePerspectiveProject] = useState<ModuleProject | null>(null);

  /* AI results (UC1 forecast + UC2 priority), scored offline and served by
     /module-deliveries/ai-results. Merged by row id, and only while the id
     still points at the project the AI scored. */
  const [aiById, setAiById] = useState<Record<string, RowAI>>({});
  const [aiMeta, setAiMeta] = useState<{ generated_at?: string; label?: string; summary?: Record<string, unknown> } | null>(null);
  const [aiForecastRow, setAiForecastRow] = useState<ModuleProject | null>(null);
  const [aiPriorityRow, setAiPriorityRow] = useState<ModuleProject | null>(null);
  // The Priority (AI) pill's menu: which row, and the pill it opens from.
  const [prioMenu, setPrioMenu] = useState<{ row: ModuleProject; anchor: HTMLElement } | null>(null);
  // Why the AI layer is missing, shown on the page rather than failing silently.
  const [aiLoadError, setAiLoadError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fetch(`${API}/akasha/api/module-deliveries-beta/ai-results`)
      .then(r => {
        if (!r.ok) throw new Error(r.status === 404
          ? 'the AI results endpoint is not on the server - restart the backend'
          : `the AI results request failed (HTTP ${r.status})`);
        return r.json();
      })
      .then(d => {
        if (!alive) return;
        if (d?.available) { setAiById(d.by_id || {}); setAiMeta(d.meta || null); setAiLoadError(null); }
        else setAiLoadError(d?.reason || 'no AI results file on the server');
      })
      .catch((e: unknown) => { if (alive) setAiLoadError(e instanceof Error ? e.message : 'the AI results could not be loaded'); });
    return () => { alive = false; };
  }, []);
  /* The export is keyed by the scoring database's project_mapping ids. Another
     database (UAT / production) numbers projects differently, so fall back to
     the P6 name, which is the same everywhere; a P6 name shared by several
     rows is told apart by plot + project name. */
  const aiByP6 = useMemo(() => {
    const m = new Map<string, RowAI[]>();
    for (const a of Object.values(aiById)) {
      if (!a.p6_name) continue;
      const k = a.p6_name.trim().toLowerCase();
      m.set(k, [...(m.get(k) ?? []), a]);
    }
    return m;
  }, [aiById]);
  const aiFor = useCallback((p: ModuleProject): RowAI | null => {
    const a = aiById[String(p.id)];
    if (a && (!a.p6_name || !p.p6_name || a.p6_name === p.p6_name)) return a;
    const cands = p.p6_name ? aiByP6.get(p.p6_name.trim().toLowerCase()) : undefined;
    if (!cands?.length) return null;
    if (cands.length === 1) return cands[0];
    const norm = (s?: string | null) => (s || '').trim().toLowerCase();
    return cands.find(c => norm(c.plot) === norm(p.plot) && norm(c.project_name) === norm(p.project_name))
      ?? cands.find(c => norm(c.project_name) === norm(p.project_name))
      ?? null;
  }, [aiById, aiByP6]);
  const aiAsOf = aiMeta?.generated_at;
  /* The priority that drives the allocation: the user's own choice when they
     changed it, else the AI's priority class, else the plan's (standard). */
  const planPriority = useCallback((p: ModuleProject): string => {
    if (priorities[p.id]) return priorities[p.id];
    const pr = aiFor(p)?.ai_priority;
    const cls = isScored(pr) ? (pr?.priority_class || '').toUpperCase() : '';
    if (cls === 'P1' || cls === 'P2') return cls;
    if (cls === 'STANDARD') return 'standard';
    return p.priority || 'standard';
  }, [priorities, aiFor]);
  const prioritySource = (p: ModuleProject) => (priorities[p.id] ? 'set by you' : isScored(aiFor(p)?.ai_priority) ? 'from the AI' : 'plan default');
  /* Rows the AI scored, re-expressed on the AI's ordering plan (see
     buildAIRowView). Everything that reads the month grid goes through pvOf,
     so a row's cells, its total, the column totals and the Planned-by-Month
     chart all agree. */
  const aiViewById = useMemo(() => {
    const m = new Map<number, AIRowView>();
    for (const p of data?.projects ?? []) {
      const f = aiFor(p)?.ai_monthly_order_tc_forecast;
      if (f && isScored(f)) {
        const v = buildAIRowView(p, f);
        if (v) m.set(p.id, v);
      }
    }
    return m;
  }, [data, aiFor]);
  /* Then one vendor-quota levelling pass over the whole grid (rule-engine and
     AI rows together), in priority order - see vendorLeveling.ts. Without it
     AI rows sat on months the engine had already filled and the vendor's
     monthly limit was crossed, and a priority change could not move them. */
  const leveled = useMemo(() => {
    const caps: Record<string, number> = { ...VENDOR_CAP_MWAC };
    Object.entries(data?.capacity_summary ?? {}).forEach(([src, v]) => { if (v.monthly_cap_mwac) caps[src] = v.monthly_cap_mwac; });
    const rows = (data?.projects ?? []).map(p => aiViewById.get(p.id) ?? p);
    return levelVendorQuota<ModuleProject | AIRowView>(rows, FORECAST_MONTHS, r => 'ai_view' in r, caps, planPriority);
  }, [data, aiViewById, planPriority]);
  const pvOf = useCallback((p: ModuleProject): ModuleProject | AIRowView =>
    leveled.rows.get(p.id) ?? aiViewById.get(p.id) ?? p, [leveled, aiViewById]);

  const [searchParams] = useSearchParams();
  const portfolio = searchParams.get('portfolio');
  const phase = searchParams.get('phase');
  const adv = useAdvancedPlan(advanced, portfolio);
  const columnCount = TABLE_COLUMN_COUNT + (advanced ? ADVANCED_COL_COUNT : 0);
  const advShare = useMemo(() => {
    const total = new Map<string, number>();
    (data?.projects ?? []).forEach(r => {
      const pl = adv.byId.get(r.id);
      if (pl) total.set(pl.project_id, (total.get(pl.project_id) ?? 0) + (r.capacity_mwac || 0));
    });
    return (r: ModuleProject) => {
      const pl = adv.byId.get(r.id);
      const t = pl ? total.get(pl.project_id) ?? 0 : 0;
      return t > 0 ? (r.capacity_mwac || 0) / t : 1;
    };
  }, [data, adv.byId]);

  /* Priorities are NOT part of this fetch: the Beta applies them in the
     browser (vendorLeveling.ts), so changing one re-levels the grid in place.
     Sending them here re-fetched the whole summary on every change and put the
     full-page loader up. The loader shows only for the first load; a later
     refresh (an LTA edit, a scenario change) keeps the table on screen. */
  const loadedOnce = React.useRef(false);
  const loadData = React.useCallback((sc = scenario) => {
    if (!loadedOnce.current) setLoading(true);
    const params = new URLSearchParams();
    if (sc) params.append('scenario', sc);
    if (portfolio) params.append('portfolio', portfolio);
    if (phase) params.append('phase', phase);
    return fetch(`${API}/akasha/api/module-deliveries/summary?${params.toString()}`)
      .then(r => r.json())
      .then(d => { setData(d); loadedOnce.current = true; setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [scenario, portfolio, phase]);

  useEffect(() => { loadData(); }, [loadData]);

  // Changing a priority re-levels the grid on the spot (vendorLeveling.ts),
  // starting from the priority currently in force - the AI's, unless changed.
  const cyclePriority = (projectId: number) => {
    const row = data?.projects.find(p => p.id === projectId);
    const current = (row ? planPriority(row) : 'standard').toLowerCase();
    const next = current === 'standard' || current === 'std' ? 'P1' : current === 'p1' ? 'P2' : 'standard';
    setPriorities({ ...priorities, [projectId]: next });
  };

  const handleScenarioChange = (newSc: 'v1_baseline' | 'v2_strategic' | 'v3_commercial') => {
    setScenario(newSc);
    loadData(newSc);
  };

  const handleCopilotSubmit = async (queryText?: string) => {
    const q = (queryText || copilotQuery).trim();
    if (!q || copilotLoading) return;
    const userMsg = { role: 'user' as const, text: q, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
    setCopilotMessages(prev => [...prev, userMsg]);
    setCopilotQuery('');
    setCopilotLoading(true);
    try {
      const res = await fetch(`${API}/akasha/api/module-deliveries/copilot-chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: q,
          scenario,
          context_filter: search || undefined,
        }),
      });
      const resJson = await res.json();
      const botMsg = {
        role: 'assistant' as const,
        text: resJson.reply || 'No response from copilot.',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setCopilotMessages(prev => [...prev, botMsg]);
    } catch (err: any) {
      setCopilotMessages(prev => [
        ...prev,
        { role: 'assistant', text: `Failed to consult AI Copilot: ${err.message}`, time: 'Just now' },
      ]);
    } finally {
      setCopilotLoading(false);
    }
  };

  // A changed LTA / SCOD is saved only with a reason (DateChangeReason): it
  // goes into the date history and the schedule-change email.
  const [pendingDate, setPendingDate] = useState<PendingDate | null>(null);
  const [approvalTarget, setApprovalTarget] = useState<{ mapping: LiveProject; month: string; id?: number } | null>(null);
  const [approvalsKey, setApprovalsKey] = useState(0);
  const approvalRole = useApprovalRole(approvalsKey);
  const location = useLocation();
  const saveScod = async (id: number, isoDateOrNull: string | null) => {
    const row = data?.projects.find(x => x.id === id);
    setEditingScodId(null);
    setPendingDate({ id, field: 'scod', project: row?.project_name ?? '', from: row?.scod ?? '', to: isoDateOrNull });
  };

  // LTA has the same "sometimes there is no source date at all" problem SCOD
  // had (see MANUAL_LTA in update_lta_from_123.py — 4 solar projects carry no
  // ECOD anywhere in the connectivity export), so it gets the same
  // check-it-yourself editing rather than being stuck blank until the master
  // sheet catches up.
  const saveLta = async (id: number, isoDateOrNull: string | null) => {
    const row = data?.projects.find(x => x.id === id);
    setEditingLtaId(null);
    setPendingDate({ id, field: 'lta', project: row?.project_name ?? '', from: row?.lta ?? '', to: isoDateOrNull });
  };

  const toggleTracking = async (id: number, is_tracked: boolean) => {
    // Optimistic update: immediately reflect the change in UI
    setTrackingOverrides(prev => ({ ...prev, [id]: is_tracked }));
    try {
      await fetch(`${API}/akasha/api/mappings/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_tracked }),
      });
      // Silently refresh data in background without showing loading state
      const params = new URLSearchParams();
      if (scenario) params.append('scenario', scenario);
      // Priorities are applied in the browser (vendorLeveling.ts), not sent.
      fetch(`${API}/akasha/api/module-deliveries/summary?${params.toString()}`)
        .then(r => r.json())
        .then(d => {
          setData(d);
          // Clear the optimistic override once real data arrives
          setTrackingOverrides(prev => {
            const next = { ...prev };
            delete next[id];
            return next;
          });
        })
        .catch(() => {
          // Revert optimistic override on error
          setTrackingOverrides(prev => {
            const next = { ...prev };
            delete next[id];
            return next;
          });
        });
    } catch (e) {
      console.error("Failed to update tracking status", e);
      // Revert optimistic override on error
      setTrackingOverrides(prev => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }
  };

  // Filtered projects
  const filtered = useMemo(() => {
    if (!data) return [];
    return data.projects.filter(p => {
      // Use optimistic override if present, otherwise fall back to server value
      const effectiveTracked = trackingOverrides[p.id] !== undefined ? trackingOverrides[p.id] : p.is_tracked;
      if (scope === 'tracker' && (p.cluster !== 'Solar Khavda' || p.is_commissioned || effectiveTracked === false)) return false;
      if (statusFilter !== 'all') {
        if (statusFilter === 'exception_orders') {
          if (p.balance_ordering_mwp <= 0 || (p.excluded_module_date_mwp ?? 0) <= 0) return false;
        } else if (statusFilter === 'upcoming_orders') {
          if (p.balance_ordering_mwp <= 0 || (p.excluded_module_date_mwp ?? 0) > 0 || !hasApproachingDate(p.module_date)) return false;
        } else if (statusFilter === 'lta_delayed') {
          if (!isLTADelayed(p)) return false;
        } else if (p.status !== statusFilter) {
          return false;
        }
      }
      if (search) {
        const q = search.toLowerCase();
        return (
          p.project_name.toLowerCase().includes(q) ||
          p.spv.toLowerCase().includes(q) ||
          p.plot.toLowerCase().includes(q) ||
          p.epc.toLowerCase().includes(q) ||
          p.p6_name.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [data, search, statusFilter, scope, trackingOverrides]);

  // Split into the two tiers the planning engine actually distinguishes now:
  // an exception order (module date already passed — outside the plan,
  // needs placing immediately) is a different, more urgent action than a
  // normal order that's simply coming up soon.
  const exceptionOrderProjects = useMemo(() => {
    if (!data) return [];
    return data.projects.filter(p => (p.excluded_module_date_mwp ?? 0) > 0);
  }, [data]);
  const approachingOrderProjects = useMemo(() => {
    if (!data) return [];
    return data.projects.filter(p =>
      p.balance_ordering_mwp > 0 && (p.excluded_module_date_mwp ?? 0) <= 0 && hasApproachingDate(p.module_date));
  }, [data]);

  const ltaDelayedProjects = useMemo(() => {
    if (!data) return [];
    return data.projects.filter(isLTADelayed);
  }, [data]);

  /* The banner names the worst slip rather than a count alone: a count says
     something is wrong, the worst row says where to look first. */
  const worstLtaBreach = useMemo(
    () => ltaDelayedProjects.reduce<ModuleProject | null>(
      (worst, p) => (!worst || (p.lta_risk?.days_late ?? 0) > (worst.lta_risk?.days_late ?? 0) ? p : worst), null),
    [ltaDelayedProjects]);

  // Totals are summed from the rows actually on screen. Using the server's
  // all-projects totals under a filtered table would put a 49-project figure
  // above 33 rows — a number that looks right and is not.
  const totals = useMemo(() => ({
    total_mwac: sum(filtered, p => p.capacity_mwac),
    total_mwp: sum(filtered, p => p.capacity_mwp),
    ordered_mwp: sum(filtered, p => p.ordered_mwp),
    balance_ordering_mwp: sum(filtered, p => p.balance_ordering_mwp),
    received_mwp: sum(filtered, p => p.total_receipt_mwp),
    erection_mwp: sum(filtered, p => p.erection_done_mwp),
    inventory_mwp: sum(filtered, p => p.module_inventory_mwp),
    under_transit_mwp: sum(filtered, p => p.under_transit_mwp),
    ariba_received_mwp: sum(filtered, p => p.procurement?.received_mwp ?? 0),
    awaiting_grn_mwp: sum(filtered, p => p.procurement?.awaiting_grn_mwp ?? 0),
    balance_dispatch_mwp: sum(filtered, p => p.balance_dispatch_mwp),
    completed_ftc_mwp: sum(filtered, p => p.completed_ftc_mwp),
  }), [filtered]);

  // Grouped projects
  const grouped = useMemo(() => {
    if (groupBy === 'none') return { 'All Projects': filtered };
    const groups: Record<string, ModuleProject[]> = {};
    filtered.forEach(p => {
      const key = groupBy === 'epc' ? (p.epc || 'AGEL (Direct)')
        : groupBy === 'category' ? (p.category || (p.project_name?.toUpperCase().includes('PPA') ? 'PPA' : p.project_name?.toUpperCase().includes('MERCHANT') ? 'Merchant' : p.project_name?.toUpperCase().includes('GROUP') ? 'Group' : 'Unknown'))
        : (p.type || 'Unknown');
      (groups[key] = groups[key] || []).push(p);
    });
    return groups;
  }, [filtered, groupBy]);

  const toggleGroup = (g: string) => {
    setCollapsed(prev => {
      const next = new Set(prev);
      if (next.has(g)) {
        next.delete(g);
      } else {
        next.add(g);
      }
      return next;
    });
  };

  // Exports exactly what is on screen — current search, status filter and grouping.
  const handleExport = async () => {
    if (!data) return;
    setExporting(true);
    try {
      await exportModuleDeliveriesXLSX(grouped, data.totals, data, moduleExportName('xlsx'), milestoneFilter, 'both');
    } finally {
      setExporting(false);
    }
  };


  // Type breakdown pie chart
  const typeChart = useMemo(() => {
    if (!data || !data.type_breakdowns) return {};
    const types = Object.keys(data.type_breakdowns);
    const colors: Record<string, string> = Object.fromEntries(
      types.map((t, i) => [t, t === 'Unknown' ? chartTheme.status.neutral : chartTheme.categorical[i % chartTheme.categorical.length]])
    );
    const pieData = types.map(t => ({
      name: t,
      value: data.type_breakdowns[t].mwp,
      itemStyle: { color: colors[t] },
    }));

    return {
      tooltip: { trigger: 'item', valueFormatter: (v: number) => `${MW(v)} MWp` },
      legend: { bottom: 0, textStyle: { fontSize: 10, color: chartTheme.chrome.fgSecondary } },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 5,
            borderColor: chartTheme.chrome.surface1,
            borderWidth: 2
          },
          label: { show: false },
          data: pieData,
        }
      ],
      animationDuration: 600,
    };
  }, [data, chartTheme]);

  const plannedByMonth = useMemo(() => {
    return FORECAST_MONTHS.map(mo => {
      return sum(filtered, p => pvOf(p).month_mwp?.[mo] || 0);
    });
  }, [filtered, pvOf]);

  const plannedByMonthChart = useMemo(() => {
    if (!data) return {};
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${MW(v)} MWp` },
      grid: { left: 20, right: 20, top: 30, bottom: 30, containLabel: true },
      xAxis: {
        type: 'category',
        data: FORECAST_MONTHS,
        axisLabel: { fontSize: 10, color: chartTheme.chrome.fgTertiary, interval: 'auto', rotate: 30 },
        axisLine: { show: false }, axisTick: { show: false },
      },
      yAxis: {
        type: 'value', name: 'MWp',
        nameTextStyle: { fontSize: 10, color: chartTheme.chrome.fgTertiary },
        axisLabel: { fontSize: 10, color: chartTheme.chrome.fgTertiary },
        splitLine: { lineStyle: { color: chartTheme.chrome.gridLine, type: 'dashed' } },
      },
      series: [{
        type: 'bar',
        barMaxWidth: 30,
        itemStyle: { color: chartTheme.categorical[1], borderRadius: [3, 3, 0, 0] },
        data: plannedByMonth,
      }],
      animationDuration: 600,
    };
  }, [data, chartTheme, plannedByMonth]);

  // Source rows for the AI capacity-plan table below the grid: only sources
  // the engine actually allocated anything to, largest total first.
  // Built from the levelled grid, so the table shows what the grid orders.
  const capacitySources = useMemo(() => {
    const cs = Object.fromEntries(Object.entries(leveled.vendors).map(([src, v]) => {
      const peak = v.mwac.reduce((bi, x, i, a) => (x > a[bi] ? i : bi), 0);
      const base = data?.capacity_summary?.[src];
      return [src, {
        monthly_cap_mwp: v.cap_mwac, monthly_cap_mwac: v.cap_mwac,
        lead_time_days: base?.lead_time_days ?? 0,
        allocated_by_month: v.mwp.map(x => Math.round(x * 10) / 10),
        allocated_by_month_mwac: v.mwac.map(x => Math.round(x * 10) / 10),
        utilization_pct_by_month: v.mwac.map(x => (v.cap_mwac > 0 ? Math.round((x / v.cap_mwac) * 1000) / 10 : 0)),
        peak_month: FORECAST_MONTHS[peak], peak_mwp: v.mwp[peak], peak_mwac: v.mwac[peak],
      }];
    })) as NonNullable<typeof data>['capacity_summary'] & object;
    if (Object.keys(cs).length === 0) return [];
    return Object.entries(cs)
      .sort(([, a], [, b]) => b.allocated_by_month.reduce((s, x) => s + x, 0) - a.allocated_by_month.reduce((s, x) => s + x, 0));
  }, [data, leveled]);

  if (loading) {
    return (
      <AkLoader size="md" label="Loading module deliveries…" className="min-h-[60vh] w-full" />
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center min-h-[400px] gap-3 text-destructive">
        <AlertTriangle className="w-5 h-5" />
        <span className="text-sm">{error || 'Failed to load data'}</span>
      </div>
    );
  }

  const t = totals;
  const pct = (a: number, b: number) => (b > 0 ? Math.round((a / b) * 100) : 0);
  const orderedPct = pct(t.ordered_mwp, t.total_mwp);
  const receivedPct = pct(t.received_mwp, t.ordered_mwp);

  /* AI results that loaded but match no row on screen: the export was scored
     against another database, whose project ids differ from this one. */
  const aiScoredCount = Object.keys(aiById).length;
  const aiMatchedCount = (data?.projects ?? []).filter(p => aiFor(p)).length;
  const aiNotice = aiLoadError
    ? `AI columns are empty: ${aiLoadError}.`
    : aiScoredCount > 0 && (data?.projects?.length ?? 0) > 0 && aiMatchedCount === 0
      ? `AI columns are empty: none of the ${aiScoredCount} projects in the AI results match a project here by id or P6 name - the results were exported from a different database.`
      : null;

  return (
    <div className="flex w-full flex-col gap-5 animate-in fade-in duration-500 pb-10">
      {aiNotice && (
        <div role="status" className="flex items-start gap-2 rounded-lg border border-[var(--status-watch-border)] bg-[var(--status-watch-bg)] px-3 py-2 text-[12px] text-[var(--status-watch-fg)]">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{aiNotice} The rest of the page uses live data as normal.</span>
        </div>
      )}

      <motion.div variants={container} initial="hidden" animate="show"
        className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3"
      >
        <KpiCard title="Total Capacity" value={t.total_mwac} unit="MWac" icon={Zap} tint="#06b6d4" />
        <KpiCard title="Total Capacity" value={t.total_mwp} unit="MWp" icon={Sun} tint="var(--primary-500)" />
        <KpiCard title="Ordered" value={t.ordered_mwp} unit="MWp" icon={Package} tint="var(--secondary-500)"
          pct={t.total_mwp > 0 ? t.ordered_mwp / t.total_mwp : 0}
          sub={`${orderedPct}% of capacity`} />
        <KpiCard title="Received" value={t.received_mwp} unit="MWp" icon={CheckCircle2} tint="#10b981"
          pct={t.ordered_mwp > 0 ? t.received_mwp / t.ordered_mwp : 0}
          sub={`${receivedPct}% of ordered`} />
        <KpiCard title="Erected" value={t.erection_mwp} unit="MWp" icon={Layers} tint="#3b82f6"
          pct={t.received_mwp > 0 ? t.erection_mwp / t.received_mwp : 0} />
        <KpiCard title="Inventory" value={t.inventory_mwp} unit="MWp" icon={BarChart3} tint="#f59e0b" />
        <KpiCard title="In Transit" value={t.under_transit_mwp} unit="MWp" icon={Truck} tint="#8b5cf6" />
        <KpiCard title="Balance to Order" value={t.balance_ordering_mwp} unit="MWp" icon={AlertTriangle}
          tint={t.balance_ordering_mwp > 0 ? '#ef4444' : '#10b981'} />
      </motion.div>

      {/* ── CHARTS ──────────────────────────────────────────────────────────── */}
      <motion.div variants={item} initial="hidden" animate="show" className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bento-card p-4">
          <div className="flex items-baseline justify-between gap-2 mb-3">
            <h2 className="text-sm font-semibold text-foreground">Planned by Month</h2>
            <span className="section-label">MWp</span>
          </div>
          <div className="h-[220px]">
            <ReactECharts notMerge theme={chartTheme.themeName} option={plannedByMonthChart} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
        <div className="bento-card p-4">
          <div className="flex items-baseline justify-between gap-2 mb-3">
            <h2 className="text-sm font-semibold text-foreground">Capacity by Type</h2>
            <span className="section-label">MWp</span>
          </div>
          <div className="h-[220px]">
            <ReactECharts notMerge theme={chartTheme.themeName} option={typeChart} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
      </motion.div>

      {data && <WaitingForApproval projects={data.projects as unknown as LiveProject[]} refreshKey={approvalsKey} onOpen={setApprovalTarget} />}

      {/* ── Notification Banner ──────────────────────────────────────────────
          Two tiers, matching what the planning engine actually distinguishes
          now: a phase whose module date already passed is excluded from the
          plan entirely and needs an immediate exception order (critical) —
          a different, more urgent action than one simply coming up soon
          (watch). Reads the engine's own exclusion field rather than
          re-deriving "overdue" from the date string independently (user
          decision 2026-09-21). */}
      {(exceptionOrderProjects.length > 0 || approachingOrderProjects.length > 0 || ltaDelayedProjects.length > 0) && (
        <motion.div variants={item} className="grid grid-cols-1 lg:grid-cols-3 gap-2">
          {exceptionOrderProjects.length > 0 && (
            <div className="flex items-center justify-between gap-4 rounded-md border px-4 py-3 text-sm"
              style={{ borderColor: 'var(--status-critical-border)', background: 'var(--status-critical-bg)', color: 'var(--status-critical-fg)' }}>
              <div className="flex items-center gap-3">
                <AlertTriangle className="h-5 w-5 shrink-0" />
                <div>
                  <p className="font-semibold">Immediate Exception Orders</p>
                  <p className="opacity-90 text-[12px] mt-0.5 leading-snug">
                    {exceptionOrderProjects.length} project(s) missed their ordering window ({MW(sum(exceptionOrderProjects, p => p.excluded_module_date_mwp ?? 0))} MWp),
                    now planned into the earliest month still open and marked overdue in the grid. Ordering on that date will not recover the original FTC.
                  </p>
                </div>
              </div>
              {statusFilter !== 'exception_orders' && (
                <button
                  onClick={() => setStatusFilter('exception_orders')}
                  className="shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
                  style={{ background: 'var(--status-critical-fg)' }}
                >
                  Review
                </button>
              )}
            </div>
          )}
          {approachingOrderProjects.length > 0 && (
            <div className="flex items-center justify-between gap-4 rounded-md border px-4 py-3 text-sm"
              style={{ borderColor: 'var(--status-watch-border)', background: 'var(--status-watch-bg)', color: 'var(--status-watch-fg)' }}>
              <div className="flex items-center gap-3">
                <Clock className="h-5 w-5 shrink-0" />
                <div>
                  <p className="font-semibold">Upcoming Module Orders</p>
                  <p className="opacity-90 text-[12px] mt-0.5 leading-snug">
                    {approachingOrderProjects.length} project(s) require procurement within the next 14 days.
                  </p>
                </div>
              </div>
              {statusFilter !== 'upcoming_orders' && (
                <button
                  onClick={() => setStatusFilter('upcoming_orders')}
                  className="shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
                  style={{ background: 'var(--status-watch-fg)' }}
                >
                  Review
                </button>
              )}
            </div>
          )}
          {ltaDelayedProjects.length > 0 && (
            <div className="flex items-center justify-between gap-4 rounded-md border px-4 py-3 text-sm border-status-critical-border bg-status-critical-bg text-status-critical-fg">
              <div className="flex items-center gap-3">
                <AlertTriangle className="h-5 w-5 shrink-0 text-status-critical-fg" />
                <div>
                  <p className="font-semibold text-status-critical-fg">LTA Breach (Review)</p>
                  <p className="opacity-90 text-[12px] mt-0.5 text-status-critical-fg leading-snug">
                    {ltaDelayedProjects.length} project(s) have an LTA date past their delivery commitment &mdash; SCOD on PPA projects, AOP (Plan) on the rest
                    {worstLtaBreach?.lta_risk && <> · worst: <span className="font-semibold">{worstLtaBreach.project_name}</span>, {ltaBreachLine(worstLtaBreach.lta_risk)}</>}.
                  </p>
                </div>
              </div>
              {statusFilter !== 'lta_delayed' && (
                <button
                  onClick={() => setStatusFilter('lta_delayed')}
                  className="shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-900 bg-status-critical-bg hover:bg-status-critical-bg"
                >
                  Review
                </button>
              )}
            </div>
          )}
        </motion.div>
      )}

      {/* ── TOOLBAR ───────────────────────────────────────────────────────── */}
      <motion.div variants={item} initial="hidden" animate="show" className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="text" placeholder="Search project, SPV, plot..."
            value={search} onChange={e => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-[11px] rounded-lg border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Group</span>
            <select value={groupBy} onChange={e => setGroupBy(e.target.value as 'epc' | 'category' | 'type' | 'none')}
              className="pl-2 pr-6 py-1 bg-card border border-border rounded-md text-[11px] font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer"
            >
              <option value="none">None</option>
              <option value="epc">EPC</option>
              <option value="category">Category</option>
              <option value="type">Type</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Status</span>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              className="pl-2 pr-6 py-1 bg-card border border-border rounded-md text-[11px] font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer"
            >
              <option value="all">All</option>
              <option value="delivered">Delivered</option>
              <option value="in_progress">In Progress</option>
              <option value="ordered">Ordered</option>
              <option value="pending">Pending</option>
              <option value="exception_orders">Exception Orders</option>
              <option value="upcoming_orders">Upcoming Orders</option>
              <option value="lta_delayed">LTA Breach</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Scope</span>
            <select value={scope} onChange={e => setScope(e.target.value as 'tracker' | 'all')}
              className="pl-2 pr-6 py-1 bg-card border border-border rounded-md text-[11px] font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer"
            >
              <option value="tracker">Khavda tracker</option>
              <option value="all">All projects</option>
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Milestone</span>
            <select value={milestoneFilter} onChange={e => setMilestoneFilter(e.target.value as 'all' | 'module' | 'tc' | 'ftc')}
              className="pl-2 pr-6 py-1 bg-card border border-border rounded-md text-[11px] font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer"
            >
              <option value="all">All Phases</option>
              <option value="module">Module Ordering Date</option>
              <option value="tc">TC Delivery Date</option>
              <option value="ftc">FTC Date</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Unit</span>
            <select value={unitToggle} onChange={e => setUnitToggle(e.target.value as 'both' | 'mwp' | 'mwac')}
              className="pl-2 pr-6 py-1 bg-card border border-border rounded-md text-[11px] font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer"
            >
              <option value="both">MWp / MWac</option>
              <option value="mwp">MWp</option>
              <option value="mwac">MWac</option>
            </select>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {/* Row count, SAP coverage and data freshness — the provenance the
              removed page header used to carry, on one muted line. */}
          <span className="text-[10px] tabular-nums text-muted-foreground">
            {filtered.length} of {data.projects.length} projects
            <span className="mx-1.5 text-border">|</span>
            {data.data_coverage.with_sap_data}/{data.data_coverage.total_projects} with SAP data
            <span className="mx-1.5 text-border">|</span>
            updated {new Date(data.generated_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
          </span>

          {/* Column Visibility Dropdown */}
          <div ref={colDropdownRef} className="relative">
            <button
              onClick={() => setColDropdownOpen(o => !o)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-primary shadow-sm"
            >
              <Columns3 className="w-3.5 h-3.5" />
              Columns
              <span className="text-[9px] text-muted-foreground tabular-nums">({visibleCols.size}/{ALL_COLUMNS.length})</span>
            </button>
            {colDropdownOpen && (
              <div className="absolute right-0 top-full mt-1 z-50 w-56 max-h-[400px] overflow-y-auto rounded-lg border border-border bg-card shadow-xl custom-scrollbar animate-in fade-in slide-in-from-top-1 duration-150">
                <div className="sticky top-0 bg-card border-b border-border px-3 py-2 flex items-center justify-between z-10">
                  <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Show / Hide Columns</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setVisibleCols(new Set(DEFAULT_VISIBLE))}
                      className="text-[10px] text-muted-foreground hover:text-foreground font-medium transition-colors"
                    >Reset</button>
                    <button
                      onClick={saveColumnsLayout}
                      className="text-[10px] text-primary hover:text-primary/80 font-semibold transition-colors"
                    >Save</button>
                  </div>
                </div>
                {ALL_COLUMNS.map(col => (
                  <label
                    key={col.key}
                    className="flex items-center gap-2.5 px-3 py-1.5 text-[11px] text-foreground hover:bg-muted/50 cursor-pointer transition-colors select-none"
                  >
                    <input
                      type="checkbox"
                      checked={visibleCols.has(col.key)}
                      onChange={() => toggleCol(col.key)}
                      className="w-3.5 h-3.5 rounded border-border text-primary cursor-pointer focus:ring-1 focus:ring-primary accent-[var(--primary)]"
                    />
                    <span className={visibleCols.has(col.key) ? 'font-medium' : 'text-muted-foreground'}>{col.label}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          <Link to={location.pathname === '/tc-ordering' ? { search: '?view=order_approvals' } : '/approvals'}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[11px] font-medium text-foreground shadow-sm transition-colors hover:bg-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-primary">
            Approvals
            {(approvalRole?.waiting ?? 0) > 0 && (
              <span className="rounded-full bg-[var(--status-watch-solid)] px-1.5 text-[10px] font-bold tabular-nums text-white" aria-label={`${approvalRole?.waiting} waiting for you`}>{approvalRole?.waiting}</span>
            )}
          </Link>

          <button
            onClick={handleExport}
            disabled={exporting}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-primary disabled:opacity-60 shadow-sm"
          >
            {exporting
              ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Preparing…</>
              : <><Download className="w-3.5 h-3.5" /> Export to Excel</>}
          </button>
          
          <button
            onClick={() => setIsLegendOpen(true)}
            className="inline-flex items-center justify-center rounded-lg border border-border bg-card w-8 h-8 text-foreground transition-colors hover:bg-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-primary shadow-sm"
            title="Legend & Logic"
          >
            <Info className="w-4 h-4" />
          </button>
        </div>
      </motion.div>

      {/* ── MAIN DATA TABLE ───────────────────────────────────────────────── */}
      <motion.div variants={item} initial="hidden" animate="show" className="bento-card overflow-hidden">
        {/* Color Legend Bar */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b border-border bg-card/60 text-[10px]">
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <span className="font-semibold text-foreground flex items-center gap-1">
              <Layers className="w-3.5 h-3.5 text-primary" />
              Priority Delivery Cells:
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-status-critical-border bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-status-critical-bg" />
              P1 Critical / COD Urgent
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-status-risk-border bg-status-risk-bg text-status-risk-fg dark:text-status-risk-fg font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-status-risk-bg" />
              P2 Elevated Priority
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-status-critical-solid bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg font-semibold ring-1 ring-inset ring-status-critical-solid">
              <span className="w-1.5 h-1.5 rounded-full bg-status-critical-solid" />
              Overdue (ordering window passed)
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-status-ai-border bg-status-ai-bg text-status-ai-fg dark:text-status-ai-fg font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-status-ai-bg" />
              Quota Leveled (Pulled Early)
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-status-risk-border bg-status-risk-bg text-status-risk-fg dark:text-status-risk-fg font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-status-risk-bg" />
              Capacity Overload (exceeds monthly quota)
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-status-healthy-border bg-status-healthy-bg text-status-healthy-fg dark:text-status-healthy-fg font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-status-healthy-bg" />
              Standard P6 Scheduled
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-[color-mix(in_srgb,var(--brand-blue)_35%,transparent)] bg-[color-mix(in_srgb,var(--brand-blue)_9%,transparent)] text-[var(--brand-blue)] font-semibold"
              title="LTA or SCOD changed in today's transmission sync or by an edit - click the history icon in the cell for from / to">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--brand-blue)]" />
              LTA / SCOD changed today
            </span>
          </div>

          {/* Every rule behind these numbers, from the same source the export
              writes to its Planning Rules sheet — so what is defended in a
              meeting matches what is read on screen. */}
          <button
            type="button"
            onClick={() => setRulesOpen(o => !o)}
            aria-expanded={rulesOpen}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1 text-[10px] font-semibold text-fg-secondary transition-colors hover:border-primary/40 hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          >
            <Info className="h-3 w-3" />
            How this plan is built
            <ChevronDown className={`h-3 w-3 transition-transform ${rulesOpen ? 'rotate-180' : ''}`} />
          </button>
        </div>

        {rulesOpen && (
          <div className="border-b border-border bg-surface-sunken/60 px-4 py-4">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <p className="text-[11px] leading-relaxed text-fg-secondary">
                Every rule the monthly plan applies. The same list is written to the
                <span className="font-semibold text-fg-primary"> Planning Rules </span>
                sheet of the Excel export.
              </p>
              <span className="shrink-0 font-mono text-[10px] tabular-nums text-fg-tertiary">
                {PLANNING_RULES.reduce((a, g) => a + g.rules.length, 0)} rules ·{' '}
                {PLANNING_RULES.length} areas
              </span>
            </div>

            {/* A column flow, not a grid: with a grid every row was as tall as its
                tallest group, which left big dead bands between the two rows. Columns
                let each group pack against the one above it, and break-inside-avoid
                keeps a group from being split down the middle. */}
            <div className="columns-1 gap-x-8 md:columns-2 xl:columns-3 [column-fill:_balance]">
              {PLANNING_RULES.map(group => (
                <section key={group.title} className="mb-4 break-inside-avoid">
                  <h4 className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-fg-tertiary">
                    <span className="shrink-0">{group.title}</span>
                    <span className="h-px flex-1 bg-border-subtle" />
                  </h4>
                  <dl className="space-y-2">
                    {group.rules.map(rule => (
                      <div key={rule.name} className="border-l-2 border-border-subtle pl-2.5">
                        <dt className="text-[11px] font-semibold leading-snug text-fg-primary">
                          {rule.name}
                        </dt>
                        {/* Where a rule is enforced (rule.source) stays out of this view —
                            a source-code filename means nothing to the person reading this
                            to understand the plan, and reads as an error message rather than
                            an explanation (user 2026-09-25). It is still on the data for
                            engineers, just not rendered here or in the export. */}
                        <dd className="mt-0.5 text-[10.5px] leading-[1.55] text-fg-secondary">
                          {rule.detail}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </section>
              ))}
            </div>
          </div>
        )}

        <div className="max-h-[72vh] overflow-auto custom-scrollbar">
          <table className="min-w-full text-left border-separate border-spacing-0">
            <thead className="sticky top-0 z-40">
              <tr>
                <Th stickyLeft={0} rowSpan={2} className="w-[34px] min-w-[34px]">Sr</Th>
                {isColVisible('project') && <Th stickyLeft={34} rowSpan={2} className="min-w-[188px] text-left">Project</Th>}
                {isColVisible('p6_name') && <Th rowSpan={2} className="min-w-[178px] text-left">P6 Name</Th>}
                {isColVisible('spv') && <Th rowSpan={2} className="min-w-[62px]">SPV</Th>}
                {isColVisible('plot') && <Th rowSpan={2} className="min-w-[46px]">Plot</Th>}
                {isColVisible('category') && <Th rowSpan={2} className="min-w-[62px]">Category</Th>}
                {isColVisible('type') && <Th rowSpan={2} className="min-w-[52px]">Type</Th>}
                {isColVisible('mms_type') && <Th rowSpan={2} className="min-w-[46px]"><ThLabel label="MMS" unit="Type" /></Th>}
                {isColVisible('epc') && <Th rowSpan={2} className="min-w-[124px] text-left">AGEL / EPC</Th>}
                {isColVisible('priority') && <Th rowSpan={2} className="min-w-[62px]"><ThLabel label="Priority" unit="(Plan)" /></Th>}
                {isColVisible('ol') && <Th rowSpan={2} className={`min-w-[38px] ${SECTION_EDGE}`}>OL</Th>}
                {isColVisible('capacity_mwac') && <Th rowSpan={2} className="min-w-[58px]"><ThLabel label="Capacity" unit="(MWac)" /></Th>}
                {isColVisible('capacity_mwp') && <Th rowSpan={2} className="min-w-[58px]"><ThLabel label="Capacity" unit="(MWp)" /></Th>}
                {isColVisible('ftc_completed') && <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="FTC Completed" unit="(MWp)" /></Th>}
                {isColVisible('connectivity') && <Th rowSpan={2} className={`min-w-[74px] ${SECTION_EDGE}`}><ThLabel label="Connectivity" unit="Phase" /></Th>}
                {isColVisible('lta') && <Th rowSpan={2} className="min-w-[62px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    LTA
                    <InfoTip info="Long Term Access date (pulled from ECOD in master sheets). Flagged red when it crosses the project's delivery commitment — SCOD for a PPA project, AOP (Plan) for every other. Contract type is read from the _PPA / _MERCHANT / _GROUP token in the P6 name." align="center" />
                  </div>
                </Th>}
                {isColVisible('scod') && <Th rowSpan={2} className="min-w-[80px]">SCOD</Th>}
                {isColVisible('aop') && <Th rowSpan={2} className="min-w-[66px]"><ThLabel label="AOP" unit="(Plan)" /></Th>}
                {isColVisible('ordered') && <Th rowSpan={2} className={`min-w-[64px] ${SECTION_EDGE}`}><ThLabel label="Ordered" unit="(MWp)" /></Th>}
                {isColVisible('balance_ordering') && <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Balance Ordering" unit="(MWp)" /></Th>}
                {isColVisible('total_receipt') && <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Total Receipt" unit="(MWp)" /></Th>}
                {isColVisible('erection_done') && <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Erection done" unit="(MWp)" /></Th>}
                {isColVisible('module_inventory') && <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Module Inventory" unit="(MWp)" /></Th>}
                {isColVisible('under_transit') && <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Under Transit" unit="(MWp)" /></Th>}
                {isColVisible('ariba_grn') && <Th rowSpan={2} className={`min-w-[70px] ${SECTION_EDGE}`}
                  tip="Ariba proof of receipt: GRN posted at site on this project's module PO lines, in MWp, with its share of SAP's Total Receipt underneath">
                  <ThLabel label="Ariba GRN" unit="(MWp)" /></Th>}
                {isColVisible('awaiting_grn') && <Th rowSpan={2} className="min-w-[64px]"
                  tip="Dispatched in Ariba (IBD created) with no GR posting yet: on the way or not yet booked at site">
                  <ThLabel label="Awaiting GRN" unit="(MWp)" /></Th>}
                {isColVisible('checklist_status') && <Th rowSpan={2} className="min-w-[64px]"
                  tip="Finance checklist raised after receipt, the handover for PO release: raised / receipts">
                  <ThLabel label="Checklist" unit="(Raised)" /></Th>}
                {isColVisible('deliveries') && <Th rowSpan={2} className="min-w-[78px]"
                  tip="Every dispatch and receipt, each on its own dates. Click a row's count to open its ledger">
                  <ThLabel label="Delivery" unit="Ledger" /></Th>}
                {advanced && <AdvancedHeader Th={Th} ThLabel={ThLabel} />}
                {isColVisible('balance_dispatch') && <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Balance Dispatch" unit="(MWp)" /></Th>}
                {isColVisible('ai_priority') && <Th rowSpan={2} className={`min-w-[78px] ${SECTION_EDGE} !bg-brand-blue`}>
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="Priority" />
                    <InfoTip align="center" info={<span>
                      AI-predicted ordering priority (Priority Prediction model). Click a value for the reasons, score and rule-engine comparison.
                      {aiAsOf && <><br /><b>Scored:</b> {aiDate(aiAsOf.slice(0, 10))}</>}
                      <br />A model prediction, not the priority set in the plan.
                    </span>} />
                  </div>
                </Th>}
                {isColVisible('status') && <Th rowSpan={2} className={`min-w-[78px] ${SECTION_EDGE}`}>Status</Th>}
                {isColVisible('month_wise') && (advanced
                  ? <Th colSpan={FORECAST_MONTHS.length + 1} className={`${SECTION_EDGE} !bg-[var(--status-ai-solid)]`}
                      tip="Site-driven: each block left short is ordered in the month of its order-by date (modules needed on site minus the lead time). Anything already past its order-by date sits in the current month. Click a figure for its blocks.">
                      ✦ Month-wise order, site-driven ({unitToggle === 'both' ? 'MWp / MWac' : unitToggle === 'mwp' ? 'MWp' : 'MWac'})
                    </Th>
                  : <Th colSpan={FORECAST_MONTHS.length + 1} className={SECTION_EDGE} tip="AI-scored projects: placed in the month of the AI order-by date (need date minus measured lead time). Other projects: rule engine - backward-scheduled from FTC (-45d TC, -lead time) and leveled against vendor origin limits">
                  Month wise Module Requirement at Site ({unitToggle === 'both' ? 'MWp / MWac' : unitToggle === 'mwp' ? 'MWp' : 'MWac'})
                </Th>)}
                {isColVisible('ftc_date') && <Th rowSpan={2} className={`min-w-[76px] ${SECTION_EDGE}`}>
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="FTC" unit="Date" />
                    <InfoTip info="First Time Charging. Base date mapped for the project." align="center" />
                  </div>
                </Th>}
                {isColVisible('module_ordering_date') && <Th rowSpan={2} className="min-w-[96px] !bg-brand-blue">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="Module Ordering" unit="Date (AI)" />
                    <InfoTip info={<span>AI order-by date per phase: the TC need date minus the measured P90 supplier lead time (Ariba).<br/>Projects the AI did not score show the rule-engine date (TC − 98/136 d) in grey.</span>} align="center" />
                  </div>
                </Th>}
                {isColVisible('po_placed') && <Th rowSpan={2} className="min-w-[76px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="PO Placed" unit="(Actual)" />
                    <InfoTip info={<span>Document date of the first module PO in SAP, against the earliest pending ordering date. Hover a cell for every PO.</span>} align="center" />
                  </div>
                </Th>}
                {isColVisible('tc_delivery_date') && <Th rowSpan={2} className="min-w-[96px] !bg-brand-blue">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="TC Delivery" unit="Date (AI)" />
                    <InfoTip info={<span>AI-predicted date modules reach site per phase: order date + measured P50 lead time.<br/>Projects the AI did not score show the rule-engine date (FTC − 45 d) in grey.</span>} align="center" />
                  </div>
                </Th>}
                {isColVisible('remarks') && <Th rowSpan={2} className="min-w-[210px] text-left">Remarks</Th>}
              </tr>
              <tr>
                {isColVisible('month_wise') && <>
                  {FORECAST_MONTHS.map((mo, i) => (
                    <Th key={mo} className={`min-w-[48px] font-semibold ${i === 0 ? SECTION_EDGE : ''}`}>{mo}</Th>
                  ))}
                  <Th className="min-w-[52px]">Total</Th>
                </>}
              </tr>
            </thead>
            <tbody>
              {Object.entries(grouped).map(([group, projects]) => (
                <React.Fragment key={group}>
                  {/* Group Header */}
                  {groupBy !== 'none' && (
                    <tr className="cursor-pointer" onClick={() => toggleGroup(group)}>
                      <td colSpan={columnCount} className="border-y border-[var(--border-default)] bg-[var(--neutral-200)] px-1.5 py-1">
                        <div className="sticky left-2 flex w-fit items-center gap-1.5">
                          {collapsed.has(group)
                            ? <ChevronRight className="h-3 w-3 text-muted-foreground" />
                            : <ChevronDown className="h-3 w-3 text-muted-foreground" />
                          }
                          <span className="text-[10px] font-bold uppercase tracking-wide text-foreground">{group}</span>
                          <span className="text-[10px] tabular-nums text-muted-foreground">
                            {projects.length} project{projects.length !== 1 ? 's' : ''} · {MW(projects.reduce((s, p) => s + p.capacity_mwp, 0))} MWp
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                  {/* Rows. The frozen Sr/Project cells hover to a SOLID colour,
                      never a translucent one — they sit above the scrolling
                      columns, so any alpha lets that content bleed through. */}
                  {!collapsed.has(group) && projects.map((p, idx) => {
                    const effectiveTracked = trackingOverrides[p.id] !== undefined ? trackingOverrides[p.id] : (p.is_tracked !== false);
                    const proc = p.procurement;
                    const ledgerOpen = openLedgers.has(p.id);
                    // The row as the month grid draws it: on the AI plan where the AI scored it.
                    const pv = pvOf(p);
                    return (
                    <React.Fragment key={p.id}>
                    <tr className="group hover:bg-[var(--surface-sunken)]">
                      <Td stickyLeft={0} className="bg-card group-hover:bg-[var(--surface-sunken)] text-muted-foreground font-mono">{idx + 1}</Td>
                      {isColVisible('project') && <Td stickyLeft={34} align="left" className="bg-card group-hover:bg-[var(--surface-sunken)] font-medium text-foreground shadow-[1px_0_0_0_var(--border-default)]">
                        <div className="flex items-center gap-2">
                          <input 
                            type="checkbox" 
                            checked={effectiveTracked}
                            onChange={(e) => {
                              e.stopPropagation();
                              toggleTracking(p.id, e.target.checked);
                            }}
                            onClick={(e) => e.stopPropagation()}
                            title={effectiveTracked ? "Tracked in Khavda (uncheck to move to All Projects)" : "Untracked (check to track in Khavda)"}
                            className="w-3.5 h-3.5 rounded border-border text-primary cursor-pointer focus:ring-1 focus:ring-primary shrink-0"
                          />
                          <span className="truncate">{p.project_name || p.p6_name}</span>
                        </div>
                      </Td>}
                      {isColVisible('p6_name') && <Td align="left" className="text-muted-foreground">{p.p6_name || '-'}</Td>}
                      {isColVisible('spv') && <Td className="font-mono">{p.spv}</Td>}
                      {isColVisible('plot') && <Td className="font-mono">{p.plot}</Td>}
                      {isColVisible('category') && <Td>{p.category || (p.project_name?.toUpperCase().includes('PPA') ? 'PPA' : p.project_name?.toUpperCase().includes('MERCHANT') ? 'Merchant' : p.project_name?.toUpperCase().includes('GROUP') ? 'Group' : '-')}</Td>}
                      {isColVisible('type') && <Td>{p.type}</Td>}
                      {isColVisible('mms_type') && <Td className="font-mono">{p.mms_type || '-'}</Td>}
                      {isColVisible('epc') && <Td align="left" className="font-medium">{p.epc || '-'}</Td>}
                      {isColVisible('priority') && <Td align="center">
                        <Tip text={`Priority used for vendor allocation: ${planPriority(p).toUpperCase()} (${prioritySource(p)})\nClick to change: P1 → P2 → Standard`}>
                          <button
                            type="button"
                            onClick={() => cyclePriority(p.id)}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold tracking-wider transition-all transform active:scale-95 ${
                              planPriority(p).toLowerCase() === 'p1'
                                ? 'bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg border border-status-critical-border shadow-sm shadow-status-critical-fg/20'
                                : planPriority(p).toLowerCase() === 'p2'
                                  ? 'bg-status-risk-bg text-status-risk-fg dark:text-status-risk-fg border border-status-risk-border'
                                  : 'bg-muted/60 text-muted-foreground hover:text-foreground border border-border/60'
                            }`}
                          >
                            {planPriority(p).toLowerCase() === 'p1' && (
                              <span className="w-1.5 h-1.5 rounded-full bg-status-critical-bg" />
                            )}
                            {planPriority(p).toUpperCase()}
                          </button>
                        </Tip>
                      </Td>}
                      {isColVisible('ol') && <Td align="right" className={SECTION_EDGE}>{p.ol > 0 ? p.ol.toFixed(2) : '-'}</Td>}
                      {isColVisible('capacity_mwac') && <Td align="right">{MW(p.capacity_mwac)}</Td>}
                      {isColVisible('capacity_mwp') && <Td align="right" className="font-semibold text-foreground">{MW(p.capacity_mwp)}</Td>}
                      {isColVisible('ftc_completed') && <Td align="right" className="font-semibold text-[var(--status-watch-fg)]">{p.completed_ftc_mwp > 0 ? MW(p.completed_ftc_mwp) : '-'}</Td>}
                      {isColVisible('connectivity') && <Td className={SECTION_EDGE}>{p.connectivity_phase || <span className="text-muted-foreground/50">-</span>}</Td>}
                      {isColVisible('lta') && (() => {
                        const r = p.lta_risk;
                        const delayed = r?.breached === true;
                        // Editable for the same reason SCOD is: the connectivity export
                        // carries no ECOD at all for some projects (see MANUAL_LTA in
                        // update_lta_from_123.py), so a row can sit blank or wrong until
                        // planning corrects it here rather than waiting on the master sheet.
                        if (editingLtaId === p.id) {
                          return (
                            <Td className="relative">
                              <input
                                type="date"
                                autoFocus
                                defaultValue={scodToInputValue(p.lta)}
                                disabled={savingLtaId === p.id}
                                className="w-[112px] rounded border border-border bg-background px-1 py-0 text-[10px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
                                onBlur={e => {
                                  const v = e.target.value;
                                  if (v === scodToInputValue(p.lta)) { setEditingLtaId(null); return; }
                                  saveLta(p.id, v || null);
                                }}
                                onKeyDown={e => {
                                  if (e.key === 'Escape') setEditingLtaId(null);
                                  if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                                }}
                              />
                            </Td>
                          );
                        }
                        return (
                          <Td className={delayed ? "bg-status-critical-bg text-status-critical-fg font-semibold relative"
                            : changedToday(p.date_history, 'lta') ? changedTodayCell : ""}>
                            <div className="flex items-center justify-center gap-1 w-full h-full">
                              {savingLtaId === p.id ? (
                                <RefreshCw className="w-3 h-3 animate-spin text-muted-foreground" />
                              ) : (
                                <Tip text={p.lta ? 'Click to change the LTA date' : 'No LTA on file — click to set one'}>
                                  <button
                                    type="button"
                                    onClick={() => setEditingLtaId(p.id)}
                                    className={`inline-flex items-center gap-1 rounded px-1 -mx-1 py-px focus:outline-none focus-visible:ring-1 focus-visible:ring-primary ${delayed ? 'hover:bg-status-critical-solid/10' : 'hover:bg-primary/5 hover:text-primary'}`}
                                  >
                                    <span>{p.lta || '-'}</span>
                                    <Calendar className={`h-3 w-3 shrink-0 ${delayed ? 'opacity-70' : 'text-fg-tertiary opacity-60'}`} />
                                  </button>
                                </Tip>
                              )}
                              <DateHistoryButton history={p.date_history} field="lta" projectName={p.project_name} />
                              {delayed && r && (
                                <Tip wide content={
                                  <div className="w-[300px] max-w-[calc(100vw-48px)] text-left">
                                    <div className="flex items-center gap-2">
                                      <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-status-critical-fg" />
                                      <span className="text-[12px] font-semibold text-fg-primary">LTA breach</span>
                                      <span className="ml-auto rounded bg-status-critical-bg px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-status-critical-fg">
                                        +{r.days_late}d
                                      </span>
                                    </div>
                                    {/* The number first, in plain body text: the red badge above
                                        already carries the alarm, so repeating it on every line
                                        would leave nothing for the eye to land on. */}
                                    <p className="mt-2 text-[11px] leading-relaxed text-fg-secondary">
                                      LTA <b className="text-fg-primary">{p.lta}</b> lands{' '}
                                      <b className="text-fg-primary">{r.days_late} day{r.days_late === 1 ? '' : 's'}</b> after the{' '}
                                      {r.basis} commitment of <b className="text-fg-primary">{r.basis_date}</b>.
                                    </p>
                                    {/* Which rule applied, and on what evidence. A row measured
                                        against AOP only because the P6 name carries no contract
                                        token says so, rather than implying it is merchant. */}
                                    <p className="mt-1.5 border-t border-border-subtle pt-1.5 text-[10.5px] leading-relaxed text-fg-tertiary">
                                      {r.is_ppa
                                        ? <>PPA project &mdash; measured against SCOD.</>
                                        : r.contract
                                          ? <>Non-PPA ({r.contract.toLowerCase()}) &mdash; measured against AOP (Plan).</>
                                          : <>No contract token in the P6 name, so this row falls back to <b className="text-fg-secondary">AOP</b>. Confirm the contract type before acting.</>}
                                    </p>
                                  </div>
                                }>
                                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-status-critical-fg" />
                                </Tip>
                              )}
                            </div>
                            {advanced && <AiDeadlineLine plan={adv.byId.get(p.id)} deadline={p.lta} label="LTA" weather={weather} />}
                          </Td>
                        );
                      })()}
                      {isColVisible('scod') && <td className={`px-1.5 py-[3px] text-center text-[10px] leading-[1.35] whitespace-nowrap ${GRID_LINE} ${changedToday(p.date_history, 'scod') ? changedTodayCell : ''}`}>
                        {editingScodId === p.id ? (
                          <input
                            type="date"
                            autoFocus
                            defaultValue={scodToInputValue(p.scod)}
                            disabled={savingScodId === p.id}
                            className="w-[112px] rounded border border-border bg-background px-1 py-0 text-[10px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
                            onBlur={e => {
                              const v = e.target.value;
                              if (v === scodToInputValue(p.scod)) { setEditingScodId(null); return; }
                              saveScod(p.id, v || null);
                            }}
                            onKeyDown={e => {
                              if (e.key === 'Escape') setEditingScodId(null);
                              if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                            }}
                          />
                        ) : savingScodId === p.id ? (
                          <RefreshCw className="w-3 h-3 animate-spin text-muted-foreground" />
                        ) : (
                          <Tip text={`${p.scod_source === 'manual_lta' ? 'Derived from LTA offset' : p.scod_source === 'manual' ? 'Manually entered' : `Derived from ${p.scod_source ?? 'no source'}`} ${p.scod_lta_diff_days != null ? `\n(LTA ${p.scod_lta_diff_days >= 0 ? '+' : ''}${p.scod_lta_diff_days} days)` : ''} — click to override`}>
                            <button
                              type="button"
                              onClick={() => setEditingScodId(p.id)}
                              className={`inline-flex items-center gap-1 rounded px-1 -mx-1 py-px text-[10px] decoration-dotted underline-offset-2 hover:bg-primary/5 hover:text-primary hover:underline focus:outline-none focus-visible:ring-1 focus-visible:ring-primary ${p.scod_source === 'manual_lta' ? 'text-status-risk-fg font-semibold' : 'text-foreground'}`}
                            >
                              <span>{p.scod || '-'}</span>
                              {p.scod_source === 'manual' && <Tip text="Manually entered"><span className="h-1 w-1 shrink-0 rounded-full bg-primary" /></Tip>}
                            </button>
                          </Tip>
                        )}
                        {editingScodId !== p.id && <span className="ml-0.5 inline-flex align-middle"><DateHistoryButton history={p.date_history} field="scod" projectName={p.project_name} /></span>}
                        {advanced && <AiDeadlineLine plan={adv.byId.get(p.id)} deadline={p.scod} label="SCOD" weather={weather} />}
                      </td>}
                      {isColVisible('aop') && <Td>{p.aop_plan || '-'}</Td>}
                      {/* An apportioned figure is derived, not measured — mark it. */}
                      {isColVisible('ordered') && <Td align="right" className={`${SECTION_EDGE} ${p.ordered_mwp === 0 ? 'text-muted-foreground' : ''}`}
                        tip={p.po_apportioned ? `Apportioned: ${p.po_share_pct}% of a PO on WBS shared with other projects` : undefined}>
                        {p.ordered_mwp > 0 ? MW(p.ordered_mwp) : '-'}
                        {p.po_apportioned && <span className="ml-0.5 text-[8px] align-super text-[var(--status-watch-fg)]">~</span>}
                      </Td>}
                      {isColVisible('balance_ordering') && <Td align="right" className={p.balance_ordering_mwp > 0 ? 'text-[var(--status-critical-fg)]' : 'text-muted-foreground'}>
                        {p.balance_ordering_mwp > 0 ? MW(p.balance_ordering_mwp) : '-'}
                      </Td>}
                      {isColVisible('total_receipt') && <MwCell value={p.total_receipt_mwp} cap={p.ordered_mwp} />}
                      {isColVisible('erection_done') && <Td align="right"
                        tip={p.erection_done_mwp > 0 ? 'Measured MWp installed, from the P6 Module Installation activities' : undefined}>
                        {p.erection_done_mwp > 0 ? MW(p.erection_done_mwp) : '-'}
                      </Td>}
                      {isColVisible('module_inventory') && <Td align="right"
                        tip={p.module_inventory_negative
                          ? `SAP receipt (${MW(p.total_receipt_mwp)}) is below P6 erected (${MW(p.erection_done_mwp)}) — ZSPS carries no delivery history for this project. MB52 stock on hand: ${MW(p.module_inventory_sap_mwp)} MWp`
                          : undefined}>
                        {p.module_inventory_mwp > 0 ? MW(p.module_inventory_mwp) : '-'}
                      </Td>}
                      {isColVisible('under_transit') && <Td align="right">{p.under_transit_mwp > 0 ? MW(p.under_transit_mwp) : '-'}</Td>}
                      {isColVisible('ariba_grn') && (() => {
                        if (!proc?.lots) {
                          return p.total_receipt_mwp > 0
                            ? <Td align="right" className={`text-muted-foreground ${SECTION_EDGE}`}
                                tip={`SAP shows ${MW(p.total_receipt_mwp)} MWp received, but none of this project's ${proc?.pos.length ?? 0} module PO(s) appear in the Ariba extract, so the receipt is unproven`}>No record</Td>
                            : <Td align="right" className={`text-muted-foreground ${SECTION_EDGE}`}>-</Td>;
                        }
                        const cov = p.total_receipt_mwp > 0 ? proc.received_mwp / p.total_receipt_mwp : null;
                        return (
                          <Td align="right" className={SECTION_EDGE}
                            tip={`Ariba GRN ${MW(proc.received_mwp)} MWp against SAP Total Receipt ${MW(p.total_receipt_mwp)} MWp${cov != null ? ` (${Math.round(cov * 100)}%)` : ''}. Last receipt ${fmtIsoDate(proc.last_receipt)}`}>
                            {MW(proc.received_mwp)}
                            {cov != null && <span className={`ml-1 text-[9px] ${cov < 0.9 ? 'text-[var(--status-watch-fg)]' : 'text-muted-foreground'}`}>{Math.round(cov * 100)}%</span>}
                          </Td>
                        );
                      })()}
                      {isColVisible('awaiting_grn') && (proc && proc.awaiting_grn_mwp > 0
                        ? <Td align="right"
                            className={(proc.oldest_awaiting_days ?? 0) > 30 ? 'text-[var(--status-risk-fg)] font-medium' : 'text-[var(--status-watch-fg)]'}
                            tip={`${proc.awaiting_grn_lots} consignment(s) dispatched with no GRN; oldest dispatched ${proc.oldest_awaiting_days} days ago`}>
                            {MW(proc.awaiting_grn_mwp)}
                          </Td>
                        : <Td align="right" className="text-muted-foreground">-</Td>)}
                      {isColVisible('checklist_status') && (proc && proc.checklist_due > 0
                        ? <Td className={proc.checklist_created < proc.checklist_due ? 'text-[var(--status-risk-fg)] font-medium' : 'text-muted-foreground'}
                            tip={proc.checklist_created < proc.checklist_due
                              ? `${proc.checklist_due - proc.checklist_created} receipt(s) without a finance checklist`
                              : 'A checklist is raised for every receipt'}>
                            {proc.checklist_created}/{proc.checklist_due}
                          </Td>
                        : <Td className="text-muted-foreground">-</Td>)}
                      {isColVisible('deliveries') && <Td>
                        {proc && (proc.lots > 0 || proc.pos.length > 0) ? (
                          <button type="button" onClick={() => toggleLedger(p.id)} aria-expanded={ledgerOpen}
                            className="inline-flex items-center gap-0.5 rounded px-1 py-px font-medium text-primary hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary">
                            {ledgerOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                            {proc.lots > 0 ? `${proc.lots} lot${proc.lots > 1 ? 's' : ''}` : 'POs'}
                          </button>
                        ) : <span className="text-muted-foreground">-</span>}
                      </Td>}
                      {advanced && <AdvancedCells plan={adv.byId.get(p.id)} Td={Td} standardModuleDate={p.module_date}
                        error={adv.error} loading={adv.loading} weather={weather} />}
                      {isColVisible('balance_dispatch') && <Td align="right" className={p.balance_dispatch_mwp > 0 ? 'text-[var(--status-risk-fg)]' : 'text-muted-foreground'}>
                        {p.balance_dispatch_mwp > 0 ? MW(p.balance_dispatch_mwp) : '-'}
                      </Td>}
                      {isColVisible('ai_priority') && (() => {
                        // What the allocation uses: the user's choice, else the AI's.
                        const eff = planPriority(p).toUpperCase();
                        const changed = !!priorities[p.id];
                        const tone = aiPriorityTone(eff);
                        const pill = tone === 'critical' ? 'bg-status-critical-bg text-status-critical-fg border-status-critical-border'
                          : tone === 'risk' ? 'bg-status-risk-bg text-status-risk-fg border-status-risk-border'
                          : tone === 'watch' ? 'bg-status-watch-bg text-status-watch-fg border-status-watch-border'
                          : 'bg-brand-blue/10 text-brand-blue border-brand-blue/30';
                        return (
                          <Td className={`${SECTION_EDGE} ${AI_CELL}`}>
                            <Tip text={(changed ? `Priority ${eff} · changed by you\n` : '')
                                + 'Click to change the priority'}>
                              <button type="button" aria-haspopup="dialog" aria-expanded={prioMenu?.row.id === p.id}
                                onClick={e => { const a = e.currentTarget; setPrioMenu(m => (m?.row.id === p.id ? null : { row: p, anchor: a })); }}
                                className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-bold tracking-wider transition-transform active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50 ${pill} ${changed ? 'ring-1 ring-offset-1 ring-fg-tertiary/60' : ''}`}>
                                {eff === 'P1' && <span className="h-1.5 w-1.5 rounded-full bg-status-critical-solid" />}
                                {eff}
                                {changed && <span className="text-[8px] font-semibold opacity-70" aria-label="changed by you">✎</span>}
                              </button>
                            </Tip>
                          </Td>
                        );
                      })()}
                      {isColVisible('status') && <Td className={SECTION_EDGE}><StatusBadge status={p.status} /></Td>}
                      {isColVisible('month_wise') && advanced && (() => {
                        const ai = aiMonths(adv.byId.get(p.id), advShare(p));
                        const total = [...ai.values()].reduce((a, e) => a + e.mwp, 0);
                        return <>
                          {FORECAST_MONTHS.map((mo, i) => (
                            <AiMonthCell key={mo} mo={mo} entry={ai.get(mo)} standard={p.month_mwp?.[mo] || 0}
                              first={i === 0} unitToggle={unitToggle} ol={p.ol} Td={Td} plan={adv.byId.get(p.id)} quota={adv.plan?.quota} milestone={milestoneFilter}
                              row={{ name: p.project_name || p.p6_name, capacityMwp: p.capacity_mwp, capacityMwac: p.capacity_mwac,
                                lta: p.lta, balanceMwp: p.balance_ordering_mwp }} />
                          ))}
                          <Td align="right" className={`${TD_AI} font-semibold text-[var(--status-ai-fg)] tabular-nums`}
                            tip={`Site-driven total to order. Standard plan: ${MW(Object.values(p.month_mwp || {}).reduce((a: number, b: any) => a + (b as number), 0))} MWp`}>
                            {total > 0.5 ? MW(total) : '-'}
                          </Td>
                        </>;
                      })()}
                      {isColVisible('month_wise') && !advanced && FORECAST_MONTHS.map((mo, i) => {
                        // Every read below (months, dates, chips, colour) is the AI view when there is one.
                        const p = pv;
                        const val = p.month_mwp?.[mo] || 0;
                        const overdueVal = p.month_overdue_mwp?.[mo] || 0;
                        const cellPhases = p.month_phases?.[mo] ?? [];
                        /* month_phases only carries the month an ORDER is placed. A
                           milestone-only month (val<=0, this cell just marks when a
                           module/TC/FTC date lands) has no entry there at all, so the
                           four-column grid went blank for it and a date that used to be
                           on screen disappeared (user 2026-09-24: "we need to do showing
                           all dates"). displayPhases falls back to the project's own
                           module_date/tc_date/ftc_date strings for that case, so the grid
                           always shows the real dates it can find. No delay/reachability
                           is computed for the fallback — it is a display of the existing
                           plan, not a new scheduling decision. */
                        const displayPhases = cellPhases.length > 0 ? cellPhases
                          : 'ai_view' in p
                            // On the AI view the fallback is built from the AI date strings;
                            // put the rule-engine dates back for the chips' "Rule:" line.
                            ? buildFallbackPhases(p, mo).map(ph => ({
                                ...ph,
                                order_date: segFor(splitDateField(p.rule_module_date), ph.phase_label)?.date || '-',
                                tc_date: segFor(splitDateField(p.rule_tc_date), ph.phase_label)?.date || '-',
                                next_tc_date: segFor(splitDateField(p.rule_tc_date), ph.phase_label)?.date || '-',
                              }))
                            : buildFallbackPhases(p, mo);
                        // Is this the month an order is actually placed, or only a month a
                        // milestone date lands in (module_date/tc_date/ftc_date land past
                        // this cell's own order month, shown via the date-string fallback)?
                        const isRealOrder = cellPhases.length > 0;
                        /* Whether THIS month's order can still hold its FTC. Judged only
                           on a REAL order (cellPhases) — a fallback display phase has no
                           scheduling basis to judge reachability against. */
                        const unreachable = cellPhases.filter(x => !x.ftc_reachable);
                        const worstShort = unreachable.reduce((a, x) => Math.max(a, x.ftc_short_days), 0);
                        /* A phase can reach its FTC and still charge after the LTA. This
                           is real information even for a milestone-only month, so it is
                           judged on displayPhases, not cellPhases. */
                        const ltaDue = p.lta ? Date.parse(p.lta.replace(/-/g, ' ')) : NaN;
                        const ltaLate = Number.isNaN(ltaDue) ? [] : displayPhases.filter(
                          x => Date.parse(x.ftc_date.replace(/-/g, ' ')) > ltaDue);
                        const theme = getMonthCellTheme(val, p.priority, p.planning_flags, overdueVal > 0);
                        // The AI forecast for this row, when the AI scored it.
                        const rowAI = aiFor(p);
                        const aiF = isScored(rowAI?.ai_monthly_order_tc_forecast) ? rowAI!.ai_monthly_order_tc_forecast! : null;

                        const getShiftMonths = () => {
                          if (!p.module_date) return 0;
                          const match = p.module_date.match(/(\d{1,2})-([A-Za-z]{3})-(\d{2,4})/);
                          if (!match) return 0;
                          const monIdx = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                            .findIndex(a => a.toLowerCase() === match[2].toLowerCase());
                          const year = parseInt(match[3].length === 2 ? match[3] : match[3].slice(-2), 10);
                          const origMonths = year * 12 + monIdx;

                          const targetMonIdx = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                            .findIndex(a => a.toLowerCase() === mo.split('-')[0].toLowerCase());
                          const targetYear = parseInt(mo.split('-')[1], 10);
                          const targetMonths = targetYear * 12 + targetMonIdx;

                          return targetMonths - origMonths;
                        };
                        const shiftMonths = getShiftMonths();
                        const isShifted = Math.abs(shiftMonths) > 0 && (p.planning_flags?.includes('extended_to_lta') || p.planning_flags?.includes('capacity_delayed') || p.planning_flags?.includes('leveled_early'));
                        
                        // Capacity Delayed = Red
                        // Extended to LTA = Purple (Matches LTA box)
                        // Leveled Early = Cyan
                        const shiftLabel = shiftMonths > 0 ? `${shiftMonths}mo Delay` : `${Math.abs(shiftMonths)}mo Early`;
                        const shiftTriangleColor = p.planning_flags?.includes('capacity_delayed') ? 'border-t-red-500' : p.planning_flags?.includes('extended_to_lta') ? 'border-t-purple-500' : 'border-t-cyan-500';

                        return (
                          <Td
                            key={mo}
                            align="right"
                            className={`${i === 0 ? SECTION_EDGE : ''} relative`}
                            tipWide
                            tipContent={(val > 0 || getChipsForMonth(p, mo, val, milestoneFilter, unitToggle).length > 0) ? (
                              <div className="space-y-2.5 text-left w-[660px] max-w-[calc(100vw-48px)]">
                                <div>
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="font-semibold text-fg-primary text-[12px]">{p.project_name || p.p6_name}</div>
                                    <div className="text-[10px] text-fg-tertiary font-mono">
                                      Project Total: <span className="text-fg-primary font-bold">{MW(p.capacity_mwp)} MWp</span> {p.capacity_mwac ? `(${p.capacity_mwac} MWac)` : ''}
                                    </div>
                                  </div>
                                  {/* AI rows: the forecast's risk and confidence, as in the AI popup. */}
                                  {aiF ? (
                                    <div className="mt-1 flex items-center gap-3 text-[10px] text-fg-tertiary">
                                      {aiF.risk_level && (
                                        <span className="flex items-center gap-1.5">Risk
                                          <span className={`rounded border px-1.5 py-px text-[9.5px] font-bold ${
                                            /high|critical/i.test(aiF.risk_level) ? 'border-status-critical-border bg-status-critical-bg text-status-critical-fg'
                                              : /medium/i.test(aiF.risk_level) ? 'border-status-risk-border bg-status-risk-bg text-status-risk-fg'
                                              : 'border-status-healthy-border bg-status-healthy-bg text-status-healthy-fg'}`}>
                                            {aiF.risk_level.toUpperCase()}
                                          </span>
                                        </span>
                                      )}
                                      {aiF.confidence != null && (
                                        <span>Confidence <span className="font-semibold tabular-nums text-fg-primary">
                                          {Math.round(aiF.confidence <= 1 ? aiF.confidence * 100 : aiF.confidence)}%
                                        </span></span>
                                      )}
                                      {aiF.explanation?.order_schedule_status_msg && (
                                        <span className={`rounded border px-1.5 py-px text-[9.5px] font-semibold ${
                                          /overdue|passed|immediate/i.test(aiF.explanation.order_schedule_status_msg)
                                            ? 'border-status-critical-border bg-status-critical-bg text-status-critical-fg'
                                            : 'border-brand-blue/30 bg-brand-blue/10 text-brand-blue'}`}>
                                          {aiF.explanation.order_schedule_status_msg}
                                        </span>
                                      )}
                                    </div>
                                  ) : (
                                    <div className="text-[10px] text-fg-tertiary mt-0.5">{theme.tag}</div>
                                  )}
                                </div>

                                {/* Dynamic Planned / Milestone Section */}
                                {(() => {
                                  const monthChips = getChipsForMonth(p, mo, val, milestoneFilter, unitToggle);
                                  const isMilestoneOnly = val <= 0 && monthChips.length > 0;
                                  
                                  return (
                                    <div className="pt-2 border-t border-border-subtle space-y-1.5">
                                      <div className="flex items-center justify-between gap-2 text-[11px]">
                                        <div className="flex items-center gap-1.5">
                                          <span className="text-fg-tertiary font-medium">
                                            {isMilestoneOnly ? 'Milestone Target:' : 'Planned Order:'}
                                          </span>
                                          <span className={`inline-flex items-center px-2 py-0.5 rounded font-mono font-bold ${
                                            overdueVal > 0
                                              ? 'text-status-critical-fg bg-status-critical-bg border border-status-critical-solid'
                                              : aiF
                                                ? `${AI_TEXT} bg-brand-blue/10 border border-brand-blue/40`
                                                : 'text-status-healthy-fg bg-status-healthy-bg border border-status-healthy-border'
                                          }`}>
                                            {isMilestoneOnly 
                                              ? `${monthChips.map(c => `${c.label} MW`).join(', ')} · ${mo}`
                                              : `${MW(val)} MWp · ${mo}`}
                                          </span>
                                        </div>
                                        <div className="text-[10px] text-fg-tertiary font-mono">
                                          Balance to Order: <span className={`font-semibold ${p.balance_ordering_mwp > 0 ? 'text-status-risk-fg' : 'text-status-healthy-fg'}`}>{p.balance_ordering_mwp > 0 ? `${MW(p.balance_ordering_mwp)} MWp` : '0 MWp'}</span>
                                        </div>
                                      </div>

                                      {isMilestoneOnly && (
                                        <div className="text-[10px] text-fg-tertiary leading-snug">
                                          Target milestone scheduled in <span className="font-semibold text-fg-primary">{mo}</span>.{' '}
                                          {aiF
                                            ? <>The related module order follows the AI order-by date (measured supplier lead time).</>
                                            : <>Related module procurement orders are scheduled <span className="font-semibold text-fg-primary">{p.type === 'China' || p.type === 'SEA' ? '136' : '98'} days earlier</span>.</>}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })()}

                                {/* AI rows: the guardrail the AI applied (where it applied one),
                                    else - only if an AI order date has already gone - say so.
                                    Rule rows: how much of the figure is already late. */}
                                {aiF ? (() => {
                                  // The forecast's own guardrail (the one its AI popup shows) first.
                                  const g = aiF.priority?.guardrail ?? rowAI?.ai_priority?.guardrail;
                                  const gText = !g ? null
                                    : typeof g === 'string' ? g
                                      : (g as any).applied === false ? null
                                        : String((g as any).reason ?? (g as any).message ?? '');
                                  if (gText) return (
                                    <div className="flex items-start gap-1.5 rounded-md border border-status-watch-border bg-status-watch-bg px-2 py-1.5 text-[10.5px] leading-relaxed text-status-watch-fg">
                                      <AlertTriangle className="mt-px h-3 w-3 shrink-0" />
                                      <span>Guardrail applied: {gText}</span>
                                    </div>
                                  );
                                  return overdueVal > 0 ? (
                                    <div className="text-[10.5px] leading-relaxed text-status-critical-fg">
                                      <b>{MW(overdueVal)} MWp</b> of this has an AI order-by date that has already passed &mdash; order now.
                                    </div>
                                  ) : null;
                                })() : overdueVal > 0 && (
                                  <div className="text-[10.5px] leading-relaxed text-status-critical-fg">
                                    <b>{MW(overdueVal)} MWp</b> of this is overdue — its ordering date has already passed.{' '}
                                    {mo} is the earliest month still open.
                                  </div>
                                )}

                                {/* The four milestone columns, but showing only the phases
                                    THIS month's order actually covers, each with how much of
                                    it is being taken. Before, every column listed the whole
                                    project's phase list, so a 114 MWp order displayed all
                                    318 MWp of phases. month_phases comes from the planner,
                                    which fills one phase in full before starting the next. */}
                                {(() => {
                                  const phases = displayPhases;
                                  if (phases.length === 0) return null;

                                  /* Quantity follows the Unit selector in the toolbar, so the
                                     tooltip never contradicts the column it came from. */
                                  const qty = (ph: MonthPhase) =>
                                    unitToggle === 'mwac' ? `${ph.mw_ac} MWac`
                                      : unitToggle === 'mwp' ? `${MW(ph.mwp)} MWp`
                                        : `${MW(ph.mwp)} MWp / ${ph.mw_ac} MWac`;

                                  const taken = phases.reduce((a, x) => a + (x.mwp || 0), 0);
                                  const takenAc = phases.reduce((a, x) => a + (x.mw_ac || 0), 0);
                                  const takenLabel =
                                    unitToggle === 'mwac' ? `${MW(takenAc)} MWac`
                                      : unitToggle === 'mwp' ? `${MW(taken)} MWp`
                                        : `${MW(taken)} MWp / ${MW(takenAc)} MWac`;

                                  /* One chip: a phase's date for one milestone. Real P6 dates
                                     only -- a delayed order keeps its dates and says it is
                                     delayed, because a recalculated FTC would be our arithmetic
                                     presented as a commitment. */
                                  const Chip = ({ ph, field, text, border, bg }: {
                                    ph: MonthPhase; field: 'order' | 'tc' | 'ftc';
                                    text: string; border: string; bg: string;
                                  }) => {
                                    /* A delayed order pushes TC/FTC forward with it. Showing the
                                       stale P6 date as the headline while the order itself is
                                       already marked "delayed to Oct-26" reads as if December is
                                       still coming — it isn't, because ordering hasn't happened
                                       yet. The headline follows the delay (next_tc_date /
                                       next_ftc_date); the untouched P6 plan date moves to the
                                       annotation line below (user 2026-09-24: "the allocation
                                       should [put] the TC at Jan[uary], not [still show] Dec as
                                       the main date — fall back to the projected date, the
                                       Original only if it isn't missed"). */
                                    const delayed = ph.delay_months > 0;
                                    /* Module Ordering and TC Delivery are the AI's predicted
                                       dates when the AI scored this phase; the rule-engine
                                       date they replace stays underneath for comparison. FTC
                                       is still the P6 plan. */
                                    const aiPh = aiF && (field === 'order' || field === 'tc')
                                      ? aiPhaseFor(aiF.phases, ph.phase_label) : undefined;
                                    if (aiPh) {
                                      const ruleDate = field === 'order' ? ph.order_date : (delayed ? ph.next_tc_date : ph.tc_date);
                                      const aiShown = field === 'order'
                                        ? (aiPh.order_by_date ? aiDate(aiPh.order_by_date) : 'Nothing to order')
                                        : (aiDate(aiPh.predicted_tc_date) ?? '-');
                                      const named = ph.phase_label && !/^(main|project balance)$/i.test(ph.phase_label);
                                      return (
                                        <div className="flex h-full flex-col rounded-md border border-brand-blue/40 bg-brand-blue/[0.07] px-1.5 py-1">
                                          <div className="flex items-baseline justify-between gap-1.5">
                                            {named ? <span className={`text-[9px] font-semibold ${AI_TEXT}`}>{ph.phase_label}</span> : <span />}
                                            <span className="rounded-sm bg-brand-blue px-1 text-[8px] font-bold tracking-wide text-white">AI</span>
                                          </div>
                                          <div className={`font-mono text-[10.5px] font-bold tabular-nums ${AI_TEXT}`}>{aiShown}</div>
                                          {field === 'order' && aiPh.order_now && (
                                            <div className="mt-0.5 text-[9px] font-bold leading-tight text-status-critical-fg">order now</div>
                                          )}
                                          {field === 'tc' && aiPh.predicted_tc_date_p90 && (
                                            <div className="mt-0.5 text-[9px] leading-tight text-fg-tertiary">
                                              latest <span className="font-mono tabular-nums">{aiDate(aiPh.predicted_tc_date_p90)}</span>
                                            </div>
                                          )}
                                          <div className="mt-0.5 text-[9px] leading-tight text-fg-tertiary">
                                            Rule: <span className="font-mono tabular-nums">{ruleDate}</span>
                                          </div>
                                        </div>
                                      );
                                    }
                                    const date = field === 'order' ? ph.order_date
                                      : field === 'tc' ? (delayed ? ph.next_tc_date : ph.tc_date)
                                        : (delayed ? ph.next_ftc_date : ph.ftc_date);
                                    /* An unphased project has no phase to name: the planner calls
                                       it "Main"/"Project Balance" internally, and printing that
                                       invented a phase the project has not got. */
                                    const named = ph.phase_label
                                      && !/^(main|project balance)$/i.test(ph.phase_label);
                                    return (
                                      <div className={`flex h-full flex-col rounded-md border px-1.5 py-1 ${border} ${bg}`}>
                                        <div className="flex items-baseline justify-between gap-1.5">
                                          {named
                                            ? <span className={`text-[9px] font-semibold ${text}`}>{ph.phase_label}</span>
                                            : <span />}
                                          {/* An unphased project's date strings carry no per-phase MW
                                              annotation, so a milestone-only fallback for it has no
                                              honest quantity to report — showing "0 MWp" next to a real
                                              project would read as a measured zero, not an unknown. */}
                                          {(ph.mwp > 0 || ph.mw_ac > 0) && (
                                            <span className="font-mono text-[9px] tabular-nums text-fg-tertiary">{qty(ph)}</span>
                                          )}
                                        </div>
                                        <div className={`font-mono text-[10.5px] font-bold tabular-nums ${text}`}>
                                          {date}
                                        </div>
                                        {/* Order still leads with its own delay state. TC/FTC now lead
                                            with the projected date (above), so the annotation here is
                                            the untouched P6 plan date they've slipped past — still
                                            visible, just no longer the headline, per the data-honesty
                                            rule that inference must be labelled and the P6 commitment
                                            stays auditable. */}
                                        {field === 'order' && ph.delay_months > 0 && (
                                          <div className="mt-0.5 font-mono text-[9px] font-bold leading-tight tabular-nums text-status-critical-fg">
                                            delayed to {ph.order_month} (+{ph.delay_months}mo)
                                          </div>
                                        )}
                                        {field === 'tc' && ph.delay_months > 0 && (
                                          <div className="mt-0.5 text-[9px] font-bold leading-tight text-status-risk-fg">
                                            P6 plan: <span className="font-mono tabular-nums">{ph.tc_date}</span>
                                          </div>
                                        )}
                                        {field === 'ftc' && ph.delay_months > 0 && (
                                          <div className="mt-0.5 text-[9px] font-bold leading-tight text-status-critical-fg">
                                            {!ph.ftc_reachable && <div>not achievable &mdash; {ph.ftc_short_days}d short</div>}
                                            P6 plan: <span className="font-mono tabular-nums">{ph.ftc_date}</span>
                                          </div>
                                        )}
                                      </div>
                                    );
                                  };

                                  /* The milestones in view, and the gap label that sits between
                                     each pair. Built as data so the grid can size itself: the
                                     Unit and Milestone selectors both change how many there are. */
                                  type Milestone = {
                                    title: string; text: string; border: string; bg: string;
                                    field?: 'order' | 'tc' | 'ftc'; gapBefore?: string;
                                  };
                                  /* The Milestone selector filters which chip a calendar cell shows
                                     (getChipsForMonth, above) — it is a view of one stage at a time
                                     on the grid. This tooltip is the opposite: it exists to show how
                                     one stage's date drives the next, so it always carries the full
                                     Module Ordering -> TC Delivery -> FTC Date pipeline regardless of
                                     which single milestone is selected in the toolbar (user
                                     2026-09-24: selecting the module filter must not drop TC/FTC from
                                     here — only the calendar chips narrow). */
                                  const milestones: Milestone[] = [];
                                  milestones.push({ title: aiF ? 'Module Ordering (AI)' : 'Module Ordering', field: 'order',
                                    text: aiF ? AI_TEXT : 'text-primary',
                                    border: 'border-primary/30', bg: 'bg-primary/[0.07]' });
                                  milestones.push({ title: aiF ? 'TC Delivery (AI)' : 'TC Delivery', field: 'tc',
                                    text: aiF ? AI_TEXT : 'text-status-risk-fg',
                                    border: 'border-status-risk-border', bg: 'bg-status-risk-bg/60',
                                    gapBefore: ' ' });
                                  milestones.push({ title: 'FTC Date', field: 'ftc', text: 'text-status-healthy-fg',
                                    border: 'border-status-healthy-border', bg: 'bg-status-healthy-bg/60',
                                    gapBefore: ' ' });
                                  if (p.lta) {
                                    // One date for the whole project, so it spans every phase row.
                                    milestones.push({ title: 'LTA Date', text: 'text-status-ai-fg',
                                      border: 'border-status-ai-border', bg: 'bg-status-ai-bg/60',
                                      gapBefore: milestones.length ? ' ' : undefined });
                                  }

                                  /* A grid, not a flex row. Flex sized each column to its own
                                     content, so a column carrying a "delayed" or "not achievable"
                                     line grew taller than its neighbours and the arrows floated at
                                     whatever height they happened to land. In a grid every cell in
                                     a row shares one height and the arrows centre against it. */
                                  const track: string[] = [];
                                  milestones.forEach((m, i) => {
                                    if (i > 0) track.push('40px');
                                    track.push('minmax(104px, 1fr)');
                                  });

                                  return (
                                    <div className="border-t border-border-subtle pt-2">
                                      <div className="mb-2 flex items-baseline justify-between gap-2">
                                        <span className="text-[10px] font-semibold uppercase tracking-wider text-fg-tertiary">
                                          {isRealOrder ? 'Ordering in' : 'Milestone dates for'} {mo} &middot; {phases.length} phase{phases.length === 1 ? '' : 's'}
                                        </span>
                                        {/* "taking X MWp" only for a real order: for a milestone-only
                                            month the MW figure is already stated above as "Milestone
                                            Target", and this fallback total is a re-derivation from date
                                            strings that could round differently — showing a second number
                                            here risked exactly the kind of contradiction this page keeps
                                            getting caught on. */}
                                        {isRealOrder && (
                                          <span className="font-mono text-[10px] tabular-nums text-fg-secondary">
                                            taking <span className="font-bold text-fg-primary">{takenLabel}</span>
                                          </span>
                                        )}
                                      </div>

                                      <div
                                        className="grid w-full items-stretch gap-x-1 gap-y-1"
                                        style={{
                                          gridTemplateColumns: track.join(' '),
                                          gridTemplateRows: `auto repeat(${phases.length}, minmax(0, auto))`,
                                        }}
                                      >
                                        {milestones.map((m, i) => {
                                          const col = i * 2 + 1;
                                          return (
                                            <React.Fragment key={m.title}>
                                              {i > 0 && (
                                                /* Spans every phase row and centres in it. */
                                                <div
                                                  className="flex flex-col items-center justify-center"
                                                  style={{ gridColumn: col - 1, gridRow: `2 / span ${phases.length}` }}
                                                >
                                                  <div className="relative flex w-full items-center justify-center">
                                                    <div className="h-px w-full rounded-full bg-border-default" />
                                                    <ArrowRight className="absolute -right-0.5 h-3 w-3 text-fg-tertiary" />
                                                  </div>
                                                  {m.gapBefore && m.gapBefore.trim() && (
                                                    <div className="mt-1 whitespace-nowrap text-[8px] font-medium text-fg-tertiary">
                                                      {m.gapBefore}
                                                    </div>
                                                  )}
                                                </div>
                                              )}
                                              <div
                                                className={`whitespace-nowrap text-[9px] font-bold uppercase tracking-wider ${m.text}`}
                                                style={{ gridColumn: col, gridRow: 1 }}
                                              >
                                                {m.title}
                                              </div>
                                              {m.field
                                                ? phases.map((ph, j) => (
                                                  <div key={`${m.title}-${j}`} style={{ gridColumn: col, gridRow: j + 2 }}>
                                                    <Chip ph={ph} field={m.field!} text={m.text}
                                                      border={m.border} bg={m.bg} />
                                                  </div>
                                                ))
                                                : (
                                                  <div style={{ gridColumn: col, gridRow: `2 / span ${phases.length}` }}>
                                                    <div className={`flex h-full flex-col justify-center rounded-md border px-1.5 py-1 ${m.border} ${m.bg}`}>
                                                      <div className={`text-[9px] font-semibold ${m.text}`}>Project</div>
                                                      <div className={`font-mono text-[10.5px] font-bold tabular-nums ${m.text}`}>
                                                        {p.lta}
                                                      </div>
                                                    </div>
                                                  </div>
                                                )}
                                            </React.Fragment>
                                          );
                                        })}
                                      </div>

                                      {/* Flags belong on the phase, not the project: only some of
                                          a month's phases may be overdue or quota-moved. */}
                                      {phases.some(x => x.overdue || x.shifted) && (
                                        <div className="mt-2 flex flex-wrap items-center gap-1">
                                          {phases.filter(x => x.overdue).map((x, i) => (
                                            <span key={`o${i}`} className="rounded bg-status-critical-bg px-1.5 py-0.5 text-[9px] font-bold text-status-critical-fg">
                                              {x.phase_label && !/^(main|project balance)$/i.test(x.phase_label) ? `${x.phase_label} ` : ''}ordering window passed
                                            </span>
                                          ))}
                                          {phases.filter(x => !x.overdue && x.shifted).map((x, i) => (
                                            <span key={`s${i}`} className="rounded bg-status-risk-bg px-1.5 py-0.5 text-[9px] font-bold text-status-risk-fg">
                                              {x.phase_label && !/^(main|project balance)$/i.test(x.phase_label) ? `${x.phase_label} ` : ''}shifted due to vendor allocation
                                              {(x as LeveledPhase).shift_reason && (
                                                <span className="font-normal"> - {(x as LeveledPhase).shift_reason}{(x as LeveledPhase).target_month ? `, moved from ${(x as LeveledPhase).target_month}` : ''}</span>
                                              )}
                                            </span>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })()}

                                {/* One verdict for this month, read off the phases above. An
                                    unreachable FTC outranks everything else: it is the fact that
                                    decides whether the order, as scheduled, still works.
                                    AI rows replace this rule-engine verdict with the AI's own
                                    executive summary (below). */}
                                {aiF ? null : unreachable.length > 0 ? (
                                  <div className="border-t border-border-subtle pt-2 text-[10.5px] leading-relaxed text-status-critical-fg">
                                    Ordering in <span className="font-semibold">{mo}</span> cannot meet the FTC for{' '}
                                    <span className="font-semibold">
                                      {unreachable.length} of {cellPhases.length} phase{cellPhases.length === 1 ? '' : 's'}
                                    </span>{' '}
                                    &mdash; up to <span className="font-semibold">{worstShort} days short</span>.
                                    The FTC dates above are the P6 plan and will slip by at least that much;
                                    an order needs its full lead time plus 45 days to install.
                                  </div>
                                ) : ltaLate.length > 0 ? (
                                  <div className="border-t border-border-subtle pt-2 text-[10.5px] leading-relaxed text-status-risk-fg">
                                    {isRealOrder ? 'Every FTC above is reachable, but' : 'This is a milestone month, and'}{' '}
                                    <span className="font-semibold">
                                      {ltaLate.length} of {displayPhases.length} phase{displayPhases.length === 1 ? '' : 's'}
                                    </span>{' '}
                                    charges only after the LTA of <span className="font-semibold">{p.lta}</span> &mdash;
                                    transmission, not supply, is the binding constraint here.
                                  </div>
                                ) : !isRealOrder ? null
                                : p.planning_flags?.includes('extended_to_lta') ? (
                                  <div className="border-t border-border-subtle pt-2 text-[10.5px] leading-relaxed text-status-risk-fg">
                                    Vendor capacity in the earlier months was full, so this order was extended to{' '}
                                    <span className="font-semibold">{mo}</span>. It misses the original TC date but is
                                    still inside the LTA, so transmission is not the constraint.
                                  </div>
                                ) : p.planning_flags?.includes('leveled_early') ? (
                                  <div className="border-t border-border-subtle pt-2 text-[10.5px] leading-relaxed text-status-ai-fg">
                                    Pulled early to <span className="font-semibold">{mo}</span> to stay inside the vendor's
                                    monthly limit. Material arrives ahead of schedule &mdash; check laydown space.
                                  </div>
                                ) : (
                                  <div className="border-t border-border-subtle pt-2 text-[10.5px] leading-relaxed text-fg-secondary">
                                    Ordering in <span className="font-semibold text-status-healthy-fg">{mo}</span> lands the
                                    material on site in time to support every FTC above.
                                  </div>
                                )}
                                {(val > 0 || ((p as unknown as LiveProject).approvals ?? []).some(a => a.month === mo)) && (
                                  <ApprovalSummary p={p as unknown as LiveProject} month={mo} planned={val} onOpen={setApprovalTarget}
                                    canRequest={!!approvalRole && (approvalRole.superadmin || covers(approvalRole.request, p.cluster))} />
                                )}

                                {/* AI rows: the AI's executive summary in neutral text (not an
                                    alarm colour), the AI button that opens the full forecast,
                                    then the AI's recommended actions. */}
                                {aiF ? (
                                  <>
                                    <div className="border-t border-border-subtle pt-2 text-[10.5px] leading-relaxed text-fg-secondary">
                                      {aiF.explanation?.executive_summary || 'The AI scored this project but returned no summary.'}{' '}
                                      <button
                                        type="button"
                                        onClick={() => setAiForecastRow(p)}
                                        title="Open the full AI forecast: why the FTC moves, lead time, monthly requirement, risks"
                                        className="ml-1 inline-flex translate-y-[1px] items-center gap-1 rounded border border-brand-blue/40 bg-brand-blue/10 px-1.5 py-px align-baseline text-[9px] font-bold tracking-wide text-brand-blue shadow-sm transition-colors hover:bg-brand-blue hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50"
                                      >
                                        <Bot className="h-2.5 w-2.5" />
                                        AI
                                      </button>
                                    </div>
                                    {(aiF.explanation?.recommended_actions?.length ?? 0) > 0 && (
                                      <div className="rounded-md border border-brand-blue/30 bg-brand-blue/[0.05] px-2.5 py-2">
                                        <div className={`flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider ${AI_TEXT}`}>
                                          <ListChecks className="h-3 w-3" />
                                          Recommended actions
                                        </div>
                                        <ol className="mt-1.5 flex flex-col gap-1">
                                          {aiF.explanation!.recommended_actions!.map((a, k) => (
                                            <li key={k} className="flex items-start gap-1.5 text-[10.5px] leading-relaxed text-fg-secondary">
                                              <span className="mt-px flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-brand-blue/15 text-[8.5px] font-bold text-brand-blue">{k + 1}</span>
                                              <span>{a}</span>
                                            </li>
                                          ))}
                                        </ol>
                                      </div>
                                    )}
                                  </>
                                ) : rowAI?.ai_monthly_order_tc_forecast ? (
                                  <div className="border-t border-border-subtle pt-2 text-[10px] text-fg-tertiary">
                                    AI forecast not available for this project
                                    {rowAI.ai_monthly_order_tc_forecast.reason ? <> &mdash; {rowAI.ai_monthly_order_tc_forecast.reason}</> : ''}. Dates above are the rule engine&apos;s.
                                  </div>
                                ) : null}
                              </div>
                            ) : undefined}
                          >
                            {getChipsForMonth(p, mo, val, milestoneFilter, unitToggle).length > 0 ? (
                              <div className="flex flex-col items-end justify-center w-full gap-1.5">
                                <div className="flex flex-col items-end gap-1 w-full">
                                  {getChipsForMonth(p, mo, val, milestoneFilter, unitToggle).map((c, idx) => (
                                    <div key={idx} className={`relative px-1.5 py-[2px] rounded flex items-center font-bold whitespace-nowrap overflow-hidden max-w-full shadow-sm
                                      ${c.type === 'module' ? 'bg-primary/20 text-primary border border-primary/30 shadow-primary/20' :
                                        c.type === 'tc' ? 'bg-status-risk-bg text-status-risk-fg border border-status-risk-border shadow-status-risk-fg/20' :
                                        'bg-status-healthy-bg text-status-healthy-fg border border-status-healthy-border shadow-status-healthy-fg/20'}`}>
                                      {isShifted && (
                                        <div
                                          className={`absolute top-0 right-0 w-0 h-0 border-t-[10px] border-l-[10px] border-l-transparent ${shiftTriangleColor} opacity-100 z-10 drop-shadow-sm`}
                                          title={shiftLabel}
                                        />
                                      )}
                                      {theme.dotColor && <span className={`w-1.5 h-1.5 rounded-full ${theme.dotColor} shrink-0 mr-1.5 relative z-20`} />}
                                      {c.type === 'module' && <span className="relative z-20 inline-flex"><ApprovalMark p={p as unknown as LiveProject} month={mo} /></span>}
                                      <span className="tabular-nums text-[11px] tracking-tight font-extrabold relative z-20">
                                        {c.label.split(' / ')[0]}
                                        {c.label.includes(' / ') && (
                                          <>
                                            <span className="opacity-40 mx-px font-semibold">/</span>
                                            <span className="text-[10px] font-bold opacity-80">{c.label.split(' / ')[1]}</span>
                                          </>
                                        )}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : (
                              <span className="text-muted-foreground/30">-</span>
                            )}
                          </Td>
                        );
                      })}
                      {isColVisible('month_wise') && !advanced && (() => {
                        const v = pvOf(p);
                        const planned = Object.values(v.month_mwp || {}).reduce((a: number, b: any) => a + (b as number), 0);
                        const outside = 'ai_view' in v ? v.ai_outside : [];
                        const tip = outside.length > 0
                          ? `AI plan: ${outside.map(o => `${MW(o.mwp)} MWp ordered ${o.month}`).join(', ')} - after the last month shown, so not in a cell`
                          : planned < (p.balance_ordering_mwp || 0) ? 'Total planned is less than balance to order due to missed dates or completed FTCs' : undefined;
                        return (
                          <Td align="right" className="font-semibold text-foreground tabular-nums" tip={tip}>
                            {planned > 0 ? MW(planned) : '-'}
                            {outside.length > 0 && <span className={`ml-0.5 text-[8px] align-super ${AI_TEXT}`}>+{MW(outside.reduce((a, o) => a + o.mwp, 0))}</span>}
                          </Td>
                        );
                      })()}
                      {isColVisible('ftc_date') && <Td className={SECTION_EDGE}>
                        {p.ftc_date
                          ? <DatedPhases value={p.ftc_date} />
                          : p.ftc_all_charged
                            ? <Tip text="Every FTC phase for this project is already charged, so no delivery date is pending"><span className="text-muted-foreground">No pending FTC</span></Tip>
                            : '-'}
                        {advanced && <AiFtcLine plan={adv.byId.get(p.id)} weather={weather} />}
                      </Td>}
                      {isColVisible('module_ordering_date') && <Td>
                        {p.module_date ? <DatedPhases value={p.module_date} /> : '-'}
                        {advanced && <AiOrderLine plan={adv.byId.get(p.id)} />}
                      </Td>}
                      {/* AI dates where the AI scored the row; otherwise the rule
                          engine's own (module_date = TC - lead, tc_date = FTC - 45 d),
                          greyed so the two are never confused. */}
                      {(isColVisible('module_ordering_date') || isColVisible('tc_delivery_date')) && (() => {
                        const f = aiFor(p)?.ai_monthly_order_tc_forecast;
                        const aiPhases = isScored(f) ? f?.phases ?? [] : [];
                        const fallback = (v: string) => v
                          ? <Tip text={f && !isScored(f) ? `Rule engine date - AI not scored: ${f.reason || 'no reason given'}` : 'Rule engine date - no AI result for this row'}>
                              <span className="text-muted-foreground"><DatedPhases value={v} /></span>
                            </Tip>
                          : '-';
                        return <>
                          {isColVisible('module_ordering_date') && <Td className={AI_CELL}>
                            {aiPhases.length > 0 ? <AIDatedPhases phases={aiPhases} pick={ph => ph.order_by_date} /> : fallback(p.module_date)}
                          </Td>}
                          {isColVisible('po_placed') && (proc?.po_first_date
                              ? <Td tipWide tipContent={
                                  <div className="min-w-[260px] space-y-0.5 text-[10px]">
                                    <div className="mb-1 font-semibold">Module POs (SAP)</div>
                                    {proc.pos.map(po => (
                                      <div key={po.po} className="flex justify-between gap-3 tabular-nums">
                                        <span><span className="font-mono">{po.po}</span> <span className="text-muted-foreground">{po.vendor}</span></span>
                                        <span className="whitespace-nowrap">{fmtIsoDate(po.po_date)} · {MW(po.ordered_mwp)} MWp</span>
                                      </div>
                                    ))}
                                  </div>}>
                                  {fmtIsoDate(proc.po_first_date)}
                                  {proc.order_variance_days != null && proc.order_variance_days > 0 && (
                                    <span className="ml-1 text-[9px] font-medium text-[var(--status-risk-fg)]">+{proc.order_variance_days}d</span>
                                  )}
                                </Td>
                              : <Td className="text-muted-foreground">-</Td>)}
                          {isColVisible('tc_delivery_date') && <Td className={AI_CELL}>
                            {aiPhases.length > 0 ? <AIDatedPhases phases={aiPhases} pick={ph => ph.predicted_tc_date} /> : fallback(p.tc_date)}
                            {advanced && <AiTcLine plan={adv.byId.get(p.id)} />}
                          </Td>}
                        </>;
                      })()}
                      {isColVisible('remarks') && <Td align="left" className="min-w-[240px] max-w-[280px]">
                        <div className={`flex items-center justify-between gap-1.5 overflow-hidden transition-all duration-200 ${
                          p.perspectives 
                            ? 'bg-gradient-to-r from-primary/5 to-transparent border border-primary/20 rounded-md pl-1.5 pr-0.5 py-0.5 group-hover:border-primary/40' 
                            : ''
                        }`}>
                          <div className="flex items-center gap-1.5 overflow-hidden flex-1">
                            {p.planning_flags?.includes('critical_ordering') && (
                              <Tip text="Critical: Immediate PO required due to lead time">
                                <span className="inline-block w-1.5 h-1.5 shrink-0 rounded-full bg-status-critical-bg shadow-[0_0_4px_var(--rose-500)]" />
                              </Tip>
                            )}
                            {p.planning_flags?.includes('leveled_early') && (
                              <Tip text="Leveled early to avoid vendor monthly quota limit">
                                <span className="inline-block w-1.5 h-1.5 shrink-0 rounded-full bg-status-risk-bg" />
                              </Tip>
                            )}
                            <Tip 
                              text={(() => {
                                if (!p.remarks) return undefined;
                                // The AI's recommended actions go under the suggested action.
                                const f = aiFor(p)?.ai_monthly_order_tc_forecast;
                                const actions = isScored(f) ? f?.explanation?.recommended_actions ?? [] : [];
                                const aiBlock = actions.length > 0
                                  ? `${p.ai_suggestion ? '\n\n' : ''}AI recommended actions:\n${actions.map((a, k) => `${k + 1}. ${a}`).join('\n')}`
                                  : '';
                                const suggestion = p.ai_suggestion || aiBlock
                                  ? `\n\n💡 Suggested action:\n${p.ai_suggestion ?? ''}${aiBlock}`
                                  : '';
                                return `${p.remarks}${suggestion}`;
                              })()}
                              className="overflow-hidden flex-1"
                            >
                              <span className={`block truncate text-[10px] ${p.remarks ? (p.perspectives ? 'text-primary/90 font-medium' : 'text-foreground/90') : 'text-muted-foreground'}`}>
                                {p.remarks || '-'}
                              </span>
                            </Tip>
                          </div>
                          {/* Beta: opens the AI's full Module Ordering & TC Delivery
                              forecast - the same popup as the AI button in the month cell. */}
                          {aiFor(p)?.ai_monthly_order_tc_forecast && (() => {
                            const f = aiFor(p)!.ai_monthly_order_tc_forecast!;
                            return (
                              <Tip text={isScored(f) ? 'AI forecast: why the FTC moves, lead time, monthly requirement, actions' : `AI did not score this project: ${f.reason || 'no reason given'}`}>
                                <button
                                  type="button"
                                  onClick={() => setAiForecastRow(p)}
                                  className={`shrink-0 flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] font-bold tracking-wide shadow-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50 ${
                                    isScored(f)
                                      ? 'border-brand-blue/40 bg-brand-blue/10 text-brand-blue hover:bg-brand-blue hover:text-white'
                                      : 'border-border bg-muted/50 text-muted-foreground hover:text-foreground'}`}
                                >
                                  <Bot className="w-2.5 h-2.5" />
                                  <span>AI</span>
                                </button>
                              </Tip>
                            );
                          })()}
                        </div>
                      </Td>}
                    </tr>
                    {ledgerOpen && proc && (
                      <tr>
                        <td colSpan={columnCount} className="border-b border-[var(--border-default)] bg-[var(--surface-sunken)] p-0">
                          {/* Pinned to the viewport's left edge so the ledger stays in
                              view however far the wide table is scrolled. */}
                          <div className="sticky left-0 max-w-[min(1200px,calc(100vw-3rem))]">
                            <DeliveryLedger proc={proc} sapReceivedMwp={p.total_receipt_mwp} sharePct={p.po_apportioned ? p.po_share_pct : null} />
                          </div>
                        </td>
                      </tr>
                    )}
                    </React.Fragment>
                  );})}

                </React.Fragment>
              ))}

              {/* ── TOTALS ROW ──────────────────────────────────────────────── */}
              <tr className="border-t-2 border-[var(--neutral-700)] bg-[var(--neutral-200)] font-bold">
                {/* One cell per visible column — no colSpan arithmetic to drift
                    out of step when the view changes. */}
                <Td stickyLeft={0} className="bg-[var(--neutral-200)] text-muted-foreground">Σ</Td>
                {isColVisible('project') && <Td stickyLeft={34} align="left" className="bg-[var(--neutral-200)] text-foreground shadow-[1px_0_0_0_var(--border-default)]">Total ({filtered.length} projects)</Td>}
                {isColVisible('p6_name') && <Td />}
                {isColVisible('spv') && <Td />}
                {isColVisible('plot') && <Td />}
                {isColVisible('category') && <Td />}
                {isColVisible('type') && <Td />}
                {isColVisible('mms_type') && <Td />}
                {isColVisible('epc') && <Td />}
                {isColVisible('priority') && <Td />}
                {isColVisible('ol') && <Td className={SECTION_EDGE} />}
                {isColVisible('capacity_mwac') && <Td align="right" className={`text-foreground tabular-nums `}>{MW(t.total_mwac)}</Td>}
                {isColVisible('capacity_mwp') && <Td align="right" className="text-foreground tabular-nums">{MW(t.total_mwp)}</Td>}
                {isColVisible('ftc_completed') && <Td align="right" className="text-foreground tabular-nums">{MW(t.completed_ftc_mwp)}</Td>}
                {isColVisible('connectivity') && <Td className={SECTION_EDGE} />}
                {isColVisible('lta') && <Td />}
                {isColVisible('scod') && <Td />}
                {isColVisible('aop') && <Td />}
                {isColVisible('ordered') && <Td align="right" className={`text-foreground tabular-nums ${SECTION_EDGE}`}>{MW(t.ordered_mwp)}</Td>}
                {isColVisible('balance_ordering') && <Td align="right" className="text-[var(--status-critical-fg)] tabular-nums">{MW(t.balance_ordering_mwp)}</Td>}
                {isColVisible('total_receipt') && <Td align="right" className="text-foreground tabular-nums">{MW(t.received_mwp)}</Td>}
                {isColVisible('erection_done') && <Td align="right" className="text-foreground tabular-nums">{MW(t.erection_mwp)}</Td>}
                {isColVisible('module_inventory') && <Td align="right" className="text-foreground tabular-nums">{MW(t.inventory_mwp)}</Td>}
                {isColVisible('under_transit') && <Td align="right" className="text-foreground tabular-nums">{MW(t.under_transit_mwp)}</Td>}
                {isColVisible('ariba_grn') && <Td align="right" className={`text-foreground tabular-nums ${SECTION_EDGE}`}>{MW(t.ariba_received_mwp)}</Td>}
                {isColVisible('awaiting_grn') && <Td align="right" className="text-foreground tabular-nums">{MW(t.awaiting_grn_mwp)}</Td>}
                {isColVisible('checklist_status') && <Td />}
                {isColVisible('deliveries') && <Td />}
                {advanced && <AdvancedBlankCells Td={Td} />}
                {isColVisible('balance_dispatch') && <Td align="right" className="text-foreground tabular-nums">{MW(t.balance_dispatch_mwp)}</Td>}
                {isColVisible('ai_priority') && (() => {
                  // How many of the rows on screen the AI put at P1 - a count, so it adds up.
                  const p1 = filtered.filter(p => isScored(aiFor(p)?.ai_priority) && (aiFor(p)?.ai_priority?.priority_class || '').toUpperCase() === 'P1').length;
                  return <Td className={`${SECTION_EDGE} ${AI_CELL} ${AI_TEXT}`} tip={`${p1} of ${filtered.length} projects shown are AI P1`}>{p1 > 0 ? `${p1} × P1` : '-'}</Td>;
                })()}
                {isColVisible('status') && <Td className={SECTION_EDGE} />}
                {isColVisible('month_wise') && advanced && <>
                {FORECAST_MONTHS.map((mo, i) => {
                  const mTotal = sum(filtered, p => aiMonths(adv.byId.get(p.id), advShare(p)).get(mo)?.mwp || 0);
                  return (
                    <Td key={mo} className={`${TD_AI} tabular-nums font-bold text-[var(--status-ai-fg)] ${i === 0 ? SECTION_EDGE : ''}`}>
                      {mTotal > 0.5 ? MW(mTotal) : '-'}
                    </Td>
                  );
                })}
                <Td align="right" className={`${TD_AI} tabular-nums font-bold text-[var(--status-ai-fg)]`}>
                  {MW(sum(filtered, p => [...aiMonths(adv.byId.get(p.id), advShare(p)).values()].reduce((a, e) => a + e.mwp, 0)))}
                </Td>
                </>}
                {isColVisible('month_wise') && !advanced && <>
                {FORECAST_MONTHS.map((mo, i) => {
                  const mTotal = sum(filtered, p => pvOf(p).month_mwp?.[mo] || 0);
                  const acTotal = sum(filtered, p => {
                    const v = pvOf(p).month_mwp?.[mo] || 0;
                    return p.ol > 0 ? v / p.ol : v / 1.35;
                  });
                  return (
                    <Td
                      key={mo}
                      align="center"
                      className={`tabular-nums font-bold ${i === 0 ? SECTION_EDGE : ''} ${mTotal > 0 ? 'bg-primary/5 text-primary' : ''}`}
                    >
                      {mTotal > 0 ? (
                        <span className="whitespace-nowrap">
                          {MW(mTotal)} <span className="text-muted-foreground/60 mx-[1px]">/</span> <span className="text-[11px] font-medium opacity-80">{MW(acTotal)}</span>
                        </span>
                      ) : '-'}
                    </Td>
                  );
                })}
                <Td align="right" className="text-foreground tabular-nums font-bold">
                  {MW(sum(filtered, p => Object.values(pvOf(p).month_mwp || {}).reduce((s: number, v: any) => s + (v as number), 0)))}
                </Td>
                </>}
                {isColVisible('ftc_date') && <Td className={SECTION_EDGE} />}
                {isColVisible('module_ordering_date') && <Td />}
                {isColVisible('po_placed') && <Td />}
                {isColVisible('tc_delivery_date') && <Td />}
                {isColVisible('remarks') && <Td />}
              </tr>
            </tbody>
          </table>
        </div>
      </motion.div>

      {/* ── AI PROCUREMENT PLAN: MONTHLY ORDERING BY SOURCE ─────────────────
          The planning engine (services/module_planner.py) already allocates
          every project's balance-to-order across months against a per-source
          monthly quota — that's what colours the month columns above. This is
          the same allocation rolled up by source instead of by project, which
          was being computed on every request and silently dropped: nothing
          rendered capacity_summary or strategic_briefing before this. */}
      {capacitySources.length > 0 && (
        <motion.div variants={item} initial="hidden" animate="show"
          className="relative overflow-hidden rounded-xl border border-primary/20 bg-gradient-to-br from-card to-primary/5 p-5 shadow-sm"
        >
          {/* Subtle glow effect in the background */}
          <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
          
          <div className="relative z-10 flex flex-col gap-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="flex items-center justify-center w-6 h-6 rounded-md bg-primary/10 text-primary">
                    <Bot className="w-3.5 h-3.5" />
                  </div>
                  <h2 className="text-base font-semibold text-foreground tracking-tight">AI Procurement Strategy</h2>
                  <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary border border-primary/20">
                    <Sparkles className="mr-1 h-3 w-3" />
                    Auto-Generated
                  </span>
                </div>
                <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                  Monthly ordering plan by origin, respecting factory quotas (rule engine). The grid above places AI-scored projects in their AI order month.
                  <InfoTip
                    info="Monthly factory/import quotas (China 750, SEA 500, ALMM 500, ALCM & DCR 100 MWac) are planning assumptions built into the engine. Orders are shown in MWp; each is converted to MWac with the project's DC/AC ratio before it counts against the quota."
                    align="left"
                  />
                </div>
              </div>
              
              {data.strategic_briefing?.executive_takeaways && data.strategic_briefing.executive_takeaways.length > 0 && (
                <button
                  onClick={() => setInsightsOpen(!insightsOpen)}
                  className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary/20 bg-primary/10 text-[11px] font-semibold text-primary hover:bg-primary/20 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1"
                >
                  <Sparkles className="w-3 h-3" />
                  {insightsOpen ? 'Hide Insights' : 'View Insights'}
                  {insightsOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                </button>
              )}
            </div>

            {insightsOpen && data.strategic_briefing?.executive_takeaways && data.strategic_briefing.executive_takeaways.length > 0 && (
              <div className="rounded-lg border border-primary/10 bg-card/60 backdrop-blur-sm p-3.5 shadow-sm animate-in slide-in-from-top-2 fade-in duration-200">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-primary/80 mb-2">Executive Takeaways</h3>
                <ul className="flex flex-col gap-2">
                  {data.strategic_briefing.executive_takeaways.map((line, i) => (
                    <li key={i} className="flex items-start gap-2 text-[12px] leading-relaxed text-foreground/90">
                      <div className="mt-[3px] shrink-0 w-1.5 h-1.5 rounded-full bg-primary/50" />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

          <div className="overflow-x-auto custom-scrollbar rounded-lg border border-border bg-card">
            <table className="min-w-full text-left border-separate border-spacing-0">
              <thead>
                <tr>
                  <Th className="min-w-[120px] text-left">Source</Th>
                  <Th className="min-w-[70px]">Quota (MWac)</Th>
                  {FORECAST_MONTHS.map(mo => <Th key={mo} className="min-w-[64px]">{mo}</Th>)}
                  <Th className="min-w-[110px]">Peak (MWac)</Th>
                </tr>
              </thead>
              <tbody>
                {capacitySources.map(([source, v]) => (
                  <tr key={source} className="hover:bg-[var(--surface-sunken)]">
                    <Td align="left" className="font-semibold text-foreground">{source}</Td>
                    <Td align="right" className="text-muted-foreground whitespace-nowrap">
                      {MW(v.monthly_cap_mwac ?? 500)}
                    </Td>
                    {v.allocated_by_month.map((val, i) => {
                      const pctUsed = v.utilization_pct_by_month[i] ?? 0;
                      const tone = pctUsed >= 100 ? 'critical' : pctUsed >= 80 ? 'risk' : pctUsed >= 50 ? 'watch' : 'healthy';
                      return (
                        <Td key={FORECAST_MONTHS[i]} align="right"
                          tip={val > 0 ? `${source} in ${FORECAST_MONTHS[i]}\nConsuming: ${MW(v.allocated_by_month_mwac?.[i] ?? 0)} MWac of ${MW(v.monthly_cap_mwac ?? v.monthly_cap_mwp)} MWac quota (${Math.round(pctUsed)}%)` : undefined}>
                          {val > 0 ? (
                            <div className="flex flex-col items-end gap-0.5 py-0.5">
                              <span className="tabular-nums">
                                {MW(v.allocated_by_month_mwac?.[i] ?? 0)}
                              </span>
                              <MiniMeter pct={pctUsed} tone={tone} className="w-10" />
                            </div>
                          ) : <span className="text-muted-foreground/25">-</span>}
                        </Td>
                      );
                    })}
                    <Td align="right" className="text-muted-foreground">
                      {v.peak_mwac > 0 ? `${MW(v.peak_mwac)} in ${v.peak_month}` : '-'}
                    </Td>
                  </tr>
                ))}
                <tr className="border-t-2 border-[var(--neutral-700)] bg-[var(--neutral-200)] font-bold">
                  <Td className="text-muted-foreground">Σ Total</Td>
                  <Td align="right" className="text-foreground tabular-nums whitespace-nowrap">
                    {MW(capacitySources.reduce((s, [, v]) => s + (v.monthly_cap_mwac ?? 500), 0))}
                  </Td>
                  {FORECAST_MONTHS.map((mo, i) => (
                    <Td key={mo} align="right" className="text-foreground tabular-nums">
                      {MW(capacitySources.reduce((s, [, v]) => s + (v.allocated_by_month_mwac?.[i] || 0), 0))}
                    </Td>
                  ))}
                  <Td />
                </tr>
              </tbody>
            </table>
          </div>
          </div>
        </motion.div>
      )}

      {/* ── BETA: AI forecast + priority prediction forms ── */}
      <motion.div variants={item} initial="hidden" animate="show">
        <AIPredictionPanels />
      </motion.div>

      {/* ── 360° MULTI-PERSPECTIVE MODAL ────────────────────────────────────── */}
      {aiForecastRow && (
        <AIForecastModal row={aiForecastRow} ai={aiFor(aiForecastRow)?.ai_monthly_order_tc_forecast}
          asOf={aiAsOf?.slice(0, 10)} onClose={() => setAiForecastRow(null)} />
      )}
      {prioMenu && (() => {
        const r = prioMenu.row;
        const pr = aiFor(r)?.ai_priority;
        const cls = isScored(pr) ? (pr?.priority_class || '').toUpperCase() : '';
        const cur = planPriority(r).toLowerCase();
        return (
          <PriorityMenu anchor={prioMenu.anchor} projectName={formatProjectName(r.project_name) || r.project_name}
            current={(cur === 'p1' ? 'P1' : cur === 'p2' ? 'P2' : 'standard') as PlanPriority}
            aiClass={cls}
            overridden={!!priorities[r.id]}
            onPick={v => setPriorities(prev => ({ ...prev, [r.id]: v }))}
            onReset={() => setPriorities(prev => { const n = { ...prev }; delete n[r.id]; return n; })}
            onDetails={cls ? () => setAiPriorityRow(r) : undefined}
            onClose={() => setPrioMenu(null)} />
        );
      })()}
      {aiPriorityRow && (
        <AIPriorityModal row={aiPriorityRow} ai={aiFor(aiPriorityRow)?.ai_priority}
          asOf={aiAsOf?.slice(0, 10)} onClose={() => setAiPriorityRow(null)} />
      )}

      {activePerspectiveProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="relative w-full max-w-2xl rounded-xl border border-border bg-card p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4 pb-4 border-b border-border">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                    (activePerspectiveProject.priority || 'standard').toLowerCase() === 'p1'
                      ? 'bg-status-critical-bg text-status-critical-fg border border-status-critical-border'
                      : (activePerspectiveProject.priority || 'standard').toLowerCase() === 'p2'
                        ? 'bg-status-risk-bg text-status-risk-fg border border-status-risk-border'
                        : 'bg-status-healthy-bg text-status-healthy-fg border border-status-healthy-border'
                  }`}>
                    {activePerspectiveProject.priority || 'STANDARD'} PRIORITY
                  </span>
                  <span className="text-xs font-semibold text-muted-foreground">
                    {activePerspectiveProject.type} Source ({activePerspectiveProject.type === 'China' || activePerspectiveProject.type === 'SEA' ? '136d Lead' : '98d Lead'})
                  </span>
                </div>
                <h3 className="text-base font-bold text-foreground">{activePerspectiveProject.project_name || activePerspectiveProject.p6_name}</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  SPV: {activePerspectiveProject.spv} · Capacity: {MW(activePerspectiveProject.capacity_mwp)} MWp · FTC: {activePerspectiveProject.ftc_date || 'N/A'} · SCOD: {activePerspectiveProject.scod || 'N/A'}
                </p>
              </div>
              <button
                onClick={() => setActivePerspectiveProject(null)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Commercial */}
              <div className="rounded-lg border border-border bg-muted/20 p-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-1">
                  <ShieldCheck className="w-4 h-4 text-status-critical-fg" />
                  Commercial &amp; PPA Safeguard
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  {activePerspectiveProject.perspectives?.commercial || 'Standard PPA milestone alignment.'}
                </p>
              </div>

              {/* Supply Chain */}
              <div className="rounded-lg border border-border bg-muted/20 p-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-1">
                  <Truck className="w-4 h-4 text-status-risk-fg" />
                  Supply Chain &amp; Quota
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  {activePerspectiveProject.perspectives?.supply_chain || 'Scheduled under monthly origin limits.'}
                </p>
              </div>

              {/* Site Execution */}
              <div className="rounded-lg border border-border bg-muted/20 p-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-1">
                  <Layers className="w-4 h-4 text-primary" />
                  Site Laydown &amp; Civil
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  {activePerspectiveProject.perspectives?.site_execution || 'Laydown readiness in sync with delivery target.'}
                </p>
              </div>

              {/* Grid Transmission */}
              <div className="rounded-lg border border-border bg-muted/20 p-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-1">
                  <Activity className="w-4 h-4 text-status-healthy-fg" />
                  Grid &amp; Transmission
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  {activePerspectiveProject.perspectives?.grid_transmission || 'Substation and line charging aligned.'}
                </p>
              </div>
            </div>

            {/* AI Recommendation */}
            {activePerspectiveProject.ai_suggestion && (
              <div className="mt-4 rounded-lg border border-primary/30 bg-primary/5 p-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-primary mb-1">
                  <Sparkles className="w-4 h-4" />
                  AI Synthesis &amp; Action Plan
                </div>
                <p className="text-[11px] leading-relaxed text-foreground/90 font-medium">
                  {activePerspectiveProject.ai_suggestion}
                </p>
              </div>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  cyclePriority(activePerspectiveProject.id);
                  setActivePerspectiveProject(prev => prev ? {
                    ...prev,
                    priority: (prev.priority === 'standard' || !prev.priority) ? 'P1' : prev.priority === 'P1' ? 'P2' : 'standard'
                  } : null);
                }}
                className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors"
              >
                Toggle Priority (Now: {activePerspectiveProject.priority || 'standard'})
              </button>
              <button
                type="button"
                onClick={() => setActivePerspectiveProject(null)}
                className="rounded-lg bg-primary px-4 py-1.5 text-xs font-semibold text-white hover:bg-primary/90 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── STRATEGIC AI COPILOT DRAWER ────────────────────────────────────── */}
      {copilotOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative flex h-full w-full max-w-md flex-col bg-card border-l border-border shadow-2xl animate-in slide-in-from-right duration-300">
            {/* Drawer Header */}
            <div className="flex items-center justify-between border-b border-border p-4 bg-muted/20">
              <div className="flex items-center gap-2">
                <div className="rounded-lg bg-primary/10 p-2 text-primary">
                  <Bot className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                    Module Planning AI Copilot
                    <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold text-primary">Live LLM</span>
                  </h3>
                  <p className="text-[10px] text-muted-foreground">
                    Scenario: {scenario.replace('_', ' ').toUpperCase()} · Context: {filtered.length} projects
                  </p>
                </div>
              </div>
              <button
                onClick={() => setCopilotOpen(false)}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Prompt Quick Chips */}
            <div className="border-b border-border p-2 bg-muted/10 flex flex-wrap gap-1.5">
              {[
                'Which projects risk missing SCOD?',
                'What if China quota drops to 500 MW?',
                'Why is Baiya scheduled in May-26?',
                'Summarize procurement balance by source',
              ].map(chip => (
                <button
                  key={chip}
                  onClick={() => handleCopilotSubmit(chip)}
                  disabled={copilotLoading}
                  className="rounded-full border border-border/80 bg-card px-2.5 py-1 text-[10px] text-foreground hover:border-primary/50 hover:bg-primary/5 transition-all text-left truncate max-w-full"
                >
                  {chip}
                </button>
              ))}
            </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
              {copilotMessages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
                >
                  <div
                    className={`max-w-[88%] rounded-xl px-3.5 py-2.5 text-xs leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-primary text-white rounded-br-none shadow-sm'
                        : 'bg-muted/60 text-foreground border border-border rounded-bl-none shadow-sm'
                    }`}
                  >
                    <div className="whitespace-pre-line">{msg.text}</div>
                  </div>
                  <span className="text-[9px] text-muted-foreground mt-1 px-1">{msg.time}</span>
                </div>
              ))}
              {copilotLoading && (
                <div className="flex items-center gap-2 text-muted-foreground text-xs p-2">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-primary" />
                  <span>Synthesizing procurement &amp; schedule strategy…</span>
                </div>
              )}
            </div>

            {/* Input Footer */}
            <div className="border-t border-border p-3 bg-card">
              <form
                onSubmit={e => {
                  e.preventDefault();
                  handleCopilotSubmit();
                }}
                className="flex items-center gap-2"
              >
                <input
                  type="text"
                  placeholder="Ask AI Copilot about deliveries, quotas, or SCODs..."
                  value={copilotQuery}
                  onChange={e => setCopilotQuery(e.target.value)}
                  disabled={copilotLoading}
                  className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={!copilotQuery.trim() || copilotLoading}
                  className="rounded-lg bg-primary p-2 text-white hover:bg-primary/90 focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-40 transition-all"
                >
                  <Send className="w-4 h-4" />
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
      {/* ── LEGEND MODAL ─────────────────────────────────────────────────── */}
      {isLegendOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-md animate-in fade-in duration-200">
          <div className="relative w-full max-w-2xl rounded-2xl border border-border/50 bg-card/95 p-0 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="px-6 py-4 border-b border-border/50 bg-muted/30 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-primary/10 rounded-lg">
                  <Info className="w-5 h-5 text-primary" />
                </div>
                <h3 className="text-lg font-bold tracking-tight text-foreground">Legend & Table Logic</h3>
              </div>
              <button
                onClick={() => setIsLegendOpen(false)}
                className="rounded-full p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors focus:outline-none"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            {/* Content */}
            <div className="p-6 space-y-8 overflow-y-auto max-h-[75vh] custom-scrollbar">
              {/* Section 1 */}
              <section>
                <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                  <Layers className="w-3.5 h-3.5" />
                  Capacity Block Chips
                </h4>
                <div className="grid grid-cols-[120px_1fr] sm:grid-cols-[140px_1fr] gap-x-6 gap-y-4 items-center">
                  <div className="flex justify-end">
                    <span className="inline-flex w-16 justify-center px-1.5 py-[3px] rounded items-center font-bold text-[11px] tracking-tight bg-status-healthy-bg text-status-healthy-fg border border-status-healthy-border shadow-sm">
                      <span className="w-1.5 h-1.5 rounded-full bg-status-healthy-bg mr-1.5"></span>
                      100
                    </span>
                  </div>
                  <div className="text-sm">
                    <strong className="text-foreground font-semibold">FTC (First Time Commissioning)</strong>
                    <div className="text-fg-secondary text-xs mt-0.5">Target or actual commissioning dates.</div>
                  </div>
                  
                  <div className="flex justify-end">
                    <span className="inline-flex w-16 justify-center px-1.5 py-[3px] rounded items-center font-bold text-[11px] tracking-tight bg-status-risk-bg text-status-risk-fg border border-status-risk-border shadow-sm">
                      <span className="w-1.5 h-1.5 rounded-full bg-status-risk-bg mr-1.5"></span>
                      100
                    </span>
                  </div>
                  <div className="text-sm">
                    <strong className="text-foreground font-semibold">Module Delivery</strong>
                    <div className="text-fg-secondary text-xs mt-0.5">Target or actual date modules arrive on site.</div>
                  </div>

                  <div className="flex justify-end">
                    <span className="inline-flex w-16 justify-center px-1.5 py-[3px] rounded items-center font-bold text-[11px] tracking-tight bg-primary/20 text-primary border border-primary/30 shadow-sm">
                      <span className="w-1.5 h-1.5 rounded-full bg-primary/20 mr-1.5"></span>
                      100
                    </span>
                  </div>
                  <div className="text-sm">
                    <strong className="text-foreground font-semibold">TC (Trial Commissioning)</strong>
                    <div className="text-fg-secondary text-xs mt-0.5">Blocks energised but not yet reached FTC.</div>
                  </div>
                </div>
              </section>
              
              <div className="h-px bg-border-subtle w-full" />

              <section>
                <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  Delivery Priority Rows
                </h4>
                <div className="grid grid-cols-[120px_1fr] sm:grid-cols-[140px_1fr] gap-x-6 gap-y-5 items-center">
                  <div className="flex justify-end">
                    <span className="inline-flex px-2.5 py-1 rounded border border-status-critical-border bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg font-semibold text-[10px] shadow-sm whitespace-nowrap">
                      P1 Critical / COD Urgent
                    </span>
                  </div>
                  <div className="text-sm text-fg-secondary">
                    High-priority deliveries tied to imminent COD commitments.
                  </div>
                  
                  <div className="flex justify-end">
                    <span className="inline-flex px-2.5 py-1 rounded border border-status-risk-border bg-status-risk-bg text-status-risk-fg dark:text-status-risk-fg font-semibold text-[10px] shadow-sm whitespace-nowrap">
                      P2 Elevated Priority
                    </span>
                  </div>
                  <div className="text-sm text-fg-secondary">
                    Medium-to-high priority deliveries slightly further out.
                  </div>
                </div>
              </section>

              <div className="h-px bg-border-subtle w-full" />

              <section>
                <h4 className="mb-4 text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                  <Sparkles className="w-3.5 h-3.5" />
                  Planning Adjustments (Inside Tooltips)
                </h4>
                <div className="grid grid-cols-[120px_1fr] sm:grid-cols-[140px_1fr] gap-x-6 gap-y-4 items-center">
                  <div className="flex justify-end">
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-status-critical-fg bg-status-critical-bg px-2.5 py-1 rounded border border-status-critical-border whitespace-nowrap">
                      Capacity Delayed
                    </span>
                  </div>
                  <div className="text-sm text-fg-secondary">
                    Modules arriving later than initially planned, pushing schedule out.
                  </div>
                  
                  <div className="flex justify-end">
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-cyan-400 bg-cyan-400/10 px-2.5 py-1 rounded border border-cyan-400/20 whitespace-nowrap">
                      Leveled Early
                    </span>
                  </div>
                  <div className="text-sm text-fg-secondary">
                    Modules pulled in early to smooth out quota or supply chain constraints.
                  </div>
                  
                  <div className="flex justify-end">
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-status-ai-fg bg-status-ai-bg px-2.5 py-1 rounded border border-status-ai-border whitespace-nowrap">
                      Extended to LTA
                    </span>
                  </div>
                  <div className="text-sm text-fg-secondary">
                    Aligned to LTA constraints.
                  </div>
                </div>
              </section>
            </div>
          </div>
        </div>
      )}
      <DateChangeReason pending={pendingDate} onClose={() => setPendingDate(null)} onSaved={() => loadData()} />
      <ApprovalDialog target={approvalTarget} onClose={() => setApprovalTarget(null)}
        onChanged={() => { loadData(); setApprovalsKey(k => k + 1); }} />
    </div>
  );
}
