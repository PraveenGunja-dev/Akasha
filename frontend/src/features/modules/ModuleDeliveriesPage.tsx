import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import {
  Package, Sun, Truck, CheckCircle2, Clock, Search,
  AlertTriangle, ChevronDown, ChevronRight, Download, RefreshCw,
  Layers, BarChart3, Sparkles, ShieldCheck, Activity, Zap,
  Bot, X, Send, ArrowRight, Columns3, Info
} from 'lucide-react';
import type { ModuleDeliveriesSummary, ModuleProject, LtaRisk, MonthPhase } from './types';
import { PLANNING_RULES } from './planningRules';
import { useChartTheme } from '../../lib/chartTheme';
import { FORECAST_MONTHS, exportModuleDeliveriesXLSX, moduleExportName } from './export';
import { InfoTip } from '../../components/ui/primitives/InfoTip';
import { MiniMeter } from '../../components/ui/primitives/Meter';

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
// (Sr..Status) + the month block (FORECAST_MONTHS + its Total) + FTC/TC/Module
// + Remarks.
const TABLE_COLUMN_COUNT = 26 + (FORECAST_MONTHS.length + 1) + 3 + 1;

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

type ChipData = { label: string; phase: string | null; type: 'tc' | 'module' | 'ftc' };
function getChipsForMonth(p: any, mo: string, cellVal: number, milestoneFilter: string, unitToggle: 'both' | 'mwp' | 'mwac' = 'both'): ChipData[] {
  const chips: ChipData[] = [];
  if (!p.balance_ordering_mwp || p.balance_ordering_mwp <= 0) return chips;

  // The cellVal tracks TC Ordering, so it represents the Blue chip
  if (cellVal > 0) {
      const ac = Math.round(p.ol > 0 ? cellVal / p.ol : cellVal / 1.35);
      const labelStr = unitToggle === 'mwp' ? `${Math.round(cellVal)}` : unitToggle === 'mwac' ? `${ac}` : `${Math.round(cellVal)} / ${ac}`;
      chips.push({ label: labelStr, phase: null, type: 'tc' });
  }

  const now = new Date();

  const parseSegments = (val: string, type: 'tc' | 'module' | 'ftc') => {
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
  
  // DB tc_date = Module delivery dates (later) → Yellow chips  
  parseSegments(p.tc_date, 'module');
  // FTC Date (Green)
  parseSegments(p.ftc_date, 'ftc');
  return chips.filter(c => milestoneFilter === 'all' || c.type === milestoneFilter);
}

const container = { hidden: { opacity: 0 }, show: { opacity: 1, transition: { staggerChildren: 0.04 } } };
const item = { hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0, transition: { duration: 0.25 } } };

/* ── Rich Tooltip Content Formatter with Vibrant Date & Days Styling ────── */
function renderHighlightedText(rawText: string) {
  if (!rawText) return null;

  // Split into Primary Remark vs AI Suggestion
  const parts = rawText.split(/(?=💡 AI Suggestion:)/g);

  return (
    <div className="space-y-2">
      {parts.map((part, pIdx) => {
        const isSuggestion = part.trim().startsWith('💡 AI Suggestion:');
        const contentText = isSuggestion ? part.replace('💡 AI Suggestion:', '').trim() : part.trim();

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
                <span>💡 AI Strategic Recommendation</span>
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
    document.addEventListener('mousedown', handleGlobalClick);
    return () => document.removeEventListener('mousedown', handleGlobalClick);
  }, [show]);

  if (!text && !content) return <>{children}</>;

  const isDetailed = wide || (text && (text.length > 60 || text.includes('FTC') || text.includes('AI Suggestion')));
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
  | 'module_inventory' | 'under_transit' | 'balance_dispatch' | 'status'
  | 'month_wise' | 'ftc_date' | 'module_ordering_date' | 'tc_delivery_date' | 'remarks';

const ALL_COLUMNS: { key: ColumnKey; label: string }[] = [
  { key: 'project', label: 'Project' },
  { key: 'p6_name', label: 'P6 Name' },
  { key: 'spv', label: 'SPV' },
  { key: 'plot', label: 'Plot' },
  { key: 'category', label: 'Category' },
  { key: 'type', label: 'Type' },
  { key: 'mms_type', label: 'MMS Type' },
  { key: 'epc', label: 'AGEL / EPC' },
  { key: 'priority', label: 'Priority' },
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
  { key: 'balance_dispatch', label: 'Balance Dispatch' },
  { key: 'status', label: 'Status' },
  { key: 'month_wise', label: 'Month Wise Allocation' },
  { key: 'ftc_date', label: 'FTC Date' },
  { key: 'module_ordering_date', label: 'Module Ordering Date' },
  { key: 'tc_delivery_date', label: 'TC Delivery Date' },
  { key: 'remarks', label: 'Remarks' },
];

const DEFAULT_VISIBLE: Set<ColumnKey> = new Set([
  'project', 'spv', 'plot',
  'capacity_mwac', 'capacity_mwp', 'ftc_completed',
  'lta', 'scod', 'aop',
  'ordered', 'balance_ordering', 'total_receipt',
  'erection_done', 'module_inventory', 'under_transit', 'balance_dispatch',
  'month_wise', 'remarks',
]);

export default function ModuleDeliveriesPage() {
  const [data, setData] = useState<ModuleDeliveriesSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [groupBy, setGroupBy] = useState<'epc' | 'category' | 'type' | 'none'>('epc');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [editingScodId, setEditingScodId] = useState<number | null>(null);
  const [savingScodId, setSavingScodId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  // The printed tracker covers Khavda projects not yet commissioned (33 rows).
  // Default to that so the figures reconcile with it; 'all' reveals the wider
  // portfolio (Rajasthan, commissioned, and Khavda projects the PDF omits).
  const [scope, setScope] = useState<'tracker' | 'all'>('tracker');
  const [milestoneFilter, setMilestoneFilter] = useState<'all' | 'tc' | 'module' | 'ftc'>('all');
  const [unitToggle, setUnitToggle] = useState<'both' | 'mwp' | 'mwac'>('mwp');
  const [rulesOpen, setRulesOpen] = useState(false);
  const [visibleCols, setVisibleCols] = useState<Set<ColumnKey>>(() => new Set(DEFAULT_VISIBLE));
  const [colDropdownOpen, setColDropdownOpen] = useState(false);
  const [isLegendOpen, setIsLegendOpen] = useState(false);
  const [insightsOpen, setInsightsOpen] = useState(false);
  // Optimistic tracking state — keeps the UI stable while the PUT is in flight
  const [trackingOverrides, setTrackingOverrides] = useState<Record<number, boolean>>({});
  const colDropdownRef = React.useRef<HTMLDivElement>(null);

  const isColVisible = useCallback((key: ColumnKey) => visibleCols.has(key), [visibleCols]);
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

  const [searchParams] = useSearchParams();
  const portfolio = searchParams.get('portfolio');
  const phase = searchParams.get('phase');

  const loadData = React.useCallback((sc = scenario, prio = priorities) => {
    setLoading(true);
    const params = new URLSearchParams();
    if (sc) params.append('scenario', sc);
    if (portfolio) params.append('portfolio', portfolio);
    if (phase) params.append('phase', phase);
    if (Object.keys(prio).length > 0) {
      params.append('priorities', JSON.stringify(prio));
    }
    return fetch(`${API}/akasha/api/module-deliveries/summary?${params.toString()}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [scenario, priorities, portfolio, phase]);

  useEffect(() => { loadData(); }, [loadData]);

  const cyclePriority = (projectId: number) => {
    const current = priorities[projectId] || data?.projects.find(p => p.id === projectId)?.priority || 'standard';
    const next = current === 'standard' || current === 'std' ? 'P1' : current === 'P1' ? 'P2' : 'standard';
    const updated = { ...priorities, [projectId]: next };
    setPriorities(updated);
    loadData(scenario, updated);
  };

  const handleScenarioChange = (newSc: 'v1_baseline' | 'v2_strategic' | 'v3_commercial') => {
    setScenario(newSc);
    loadData(newSc, priorities);
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

  const saveScod = async (id: number, isoDateOrNull: string | null) => {
    setSavingScodId(id);
    try {
      await fetch(`${API}/akasha/api/mappings/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manual_scod: isoDateOrNull }),
      });
      await loadData();
    } finally {
      setSavingScodId(null);
      setEditingScodId(null);
    }
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
      if (Object.keys(priorities).length > 0) {
        params.append('priorities', JSON.stringify(priorities));
      }
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
      return sum(filtered, p => p.month_mwp?.[mo] || 0);
    });
  }, [filtered]);

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
  const capacitySources = useMemo(() => {
    const cs = data?.capacity_summary;
    if (!cs) return [];
    return Object.entries(cs)
      .sort(([, a], [, b]) => b.allocated_by_month.reduce((s, x) => s + x, 0) - a.allocated_by_month.reduce((s, x) => s + x, 0));
  }, [data]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px] gap-3">
        <RefreshCw className="w-5 h-5 animate-spin text-primary" />
        <span className="text-muted-foreground text-sm">Loading module deliveries data...</span>
      </div>
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

  return (
    <div className="flex w-full flex-col gap-5 animate-in fade-in duration-500 pb-10">

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
            <select value={milestoneFilter} onChange={e => setMilestoneFilter(e.target.value as 'all' | 'tc' | 'module' | 'ftc')}
              className="pl-2 pr-6 py-1 bg-card border border-border rounded-md text-[11px] font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer"
            >
              <option value="all">All Phases</option>
              <option value="tc">TC Date</option>
              <option value="module">Module Date</option>
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
                  <button
                    onClick={() => setVisibleCols(new Set(DEFAULT_VISIBLE))}
                    className="text-[10px] text-primary hover:underline font-medium"
                  >Reset</button>
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
                        <dd className="mt-0.5 text-[10.5px] leading-[1.55] text-fg-secondary">
                          {rule.detail}
                          {rule.source && (
                            /* Kept on one line so it reads as a citation rather than
                               stray text wrapping onto its own row. */
                            <span className="ml-1.5 inline-block whitespace-nowrap rounded border border-border-subtle bg-surface-2 px-1 py-px font-mono text-[9px] text-fg-tertiary">
                              {rule.source}
                            </span>
                          )}
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
                {isColVisible('priority') && <Th rowSpan={2} className="min-w-[62px]">Priority</Th>}
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
                {isColVisible('balance_dispatch') && <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Balance Dispatch" unit="(MWp)" /></Th>}
                {isColVisible('status') && <Th rowSpan={2} className={`min-w-[78px] ${SECTION_EDGE}`}>Status</Th>}
                {isColVisible('month_wise') && <Th colSpan={FORECAST_MONTHS.length + 1} className={SECTION_EDGE} tip="AI Leveled Monthly Requirement: Backward-scheduled from FTC (-45d TC, -lead time) and leveled against vendor origin limits to protect COD milestones">
                  Month wise Module Requirement at Site ({unitToggle === 'both' ? 'MWp / MWac' : unitToggle === 'mwp' ? 'MWp' : 'MWac'})
                </Th>}
                {isColVisible('ftc_date') && <Th rowSpan={2} className={`min-w-[76px] ${SECTION_EDGE}`}>
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="FTC" unit="Date" />
                    <InfoTip info="First Time Charging. Base date mapped for the project." align="center" />
                  </div>
                </Th>}
                {isColVisible('module_ordering_date') && <Th rowSpan={2} className="min-w-[76px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="Module Ordering" unit="Date" />
                    <InfoTip info={<span>Trial Commissioning.<br/><b>Calculation:</b> FTC Date - 45 days.</span>} align="center" />
                  </div>
                </Th>}
                {isColVisible('tc_delivery_date') && <Th rowSpan={2} className="min-w-[76px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="TC Delivery" unit="Date" />
                    <InfoTip info={<span>Target delivery date at site.<br/><b>Calculation:</b> TC Date - Lead Time (98 or 136 days based on origin).</span>} align="center" />
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
                      <td colSpan={TABLE_COLUMN_COUNT} className="border-y border-[var(--border-default)] bg-[var(--neutral-200)] px-1.5 py-1">
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
                    return (
                    <tr key={p.id} className="group hover:bg-[var(--surface-sunken)]">
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
                        <Tip text={`Click to toggle priority: Std → P1 → P2\nCurrent: ${p.priority || 'standard'}`}>
                          <button
                            type="button"
                            onClick={() => cyclePriority(p.id)}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold tracking-wider transition-all transform active:scale-95 ${
                              (p.priority || 'standard').toLowerCase() === 'p1'
                                ? 'bg-status-critical-bg text-status-critical-fg dark:text-status-critical-fg border border-status-critical-border shadow-sm shadow-status-critical-fg/20'
                                : (p.priority || 'standard').toLowerCase() === 'p2'
                                  ? 'bg-status-risk-bg text-status-risk-fg dark:text-status-risk-fg border border-status-risk-border'
                                  : 'bg-muted/60 text-muted-foreground hover:text-foreground border border-border/60'
                            }`}
                          >
                            {(p.priority || 'standard').toLowerCase() === 'p1' && (
                              <span className="w-1.5 h-1.5 rounded-full bg-status-critical-bg" />
                            )}
                            {(p.priority || 'standard').toUpperCase()}
                          </button>
                        </Tip>
                      </Td>}
                      {isColVisible('ol') && <Td align="right" className={SECTION_EDGE}>{p.ol > 0 ? p.ol.toFixed(2) : '-'}</Td>}
                      {isColVisible('capacity_mwac') && <Td align="right">{MW(p.capacity_mwac)}</Td>}
                      {isColVisible('capacity_mwp') && <Td align="right" className="font-semibold text-foreground">{MW(p.capacity_mwp)}</Td>}
                      {isColVisible('ftc_completed') && <Td align="right" className="font-semibold text-[var(--status-watch-fg)]">{p.completed_ftc_mwp > 0 ? MW(p.completed_ftc_mwp) : '-'}</Td>}
                      {isColVisible('connectivity') && <Td className={SECTION_EDGE}>{p.connectivity_phase || <span className="text-muted-foreground/50">-</span>}</Td>}
                      {isColVisible('lta') && (() => {
                        if (!p.lta || p.lta === '-') return <Td>-</Td>;
                        const r = p.lta_risk;
                        const delayed = r?.breached === true;
                        return (
                          <Td className={delayed ? "bg-status-critical-bg text-status-critical-fg font-semibold relative" : ""}>
                            <div className="flex items-center justify-center gap-1.5 w-full h-full">
                              {p.lta}
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
                          </Td>
                        );
                      })()}
                      {isColVisible('scod') && <td className={`px-1.5 py-[3px] text-center text-[10px] leading-[1.35] whitespace-nowrap ${GRID_LINE}`}>
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
                      {isColVisible('balance_dispatch') && <Td align="right" className={p.balance_dispatch_mwp > 0 ? 'text-[var(--status-risk-fg)]' : 'text-muted-foreground'}>
                        {p.balance_dispatch_mwp > 0 ? MW(p.balance_dispatch_mwp) : '-'}
                      </Td>}
                      {isColVisible('status') && <Td className={SECTION_EDGE}><StatusBadge status={p.status} /></Td>}
                      {isColVisible('month_wise') && FORECAST_MONTHS.map((mo, i) => {
                        const val = p.month_mwp?.[mo] || 0;
                        const overdueVal = p.month_overdue_mwp?.[mo] || 0;
                        const cellPhases = p.month_phases?.[mo] ?? [];
                        /* Whether THIS month's order can still hold its FTC. The
                           footer used to read project-level planning flags, which
                           do not know about per-phase reachability, so a month whose
                           FTC was 92 days out of reach still printed "in time to
                           support FTC" directly under the box saying it was not. */
                        const unreachable = cellPhases.filter(x => !x.ftc_reachable);
                        const worstShort = unreachable.reduce((a, x) => Math.max(a, x.ftc_short_days), 0);
                        /* A phase can reach its FTC and still charge after the LTA. The
                           audit found 2 month-cells reading "on time" in exactly that
                           state, so it gets its own verdict rather than being folded
                           into success. */
                        const ltaDue = p.lta ? Date.parse(p.lta.replace(/-/g, ' ')) : NaN;
                        const ltaLate = Number.isNaN(ltaDue) ? [] : cellPhases.filter(
                          x => Date.parse(x.ftc_date.replace(/-/g, ' ')) > ltaDue);
                        const theme = getMonthCellTheme(val, p.priority, p.planning_flags, overdueVal > 0);
                        
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
                                  <div className="text-[10px] text-fg-tertiary mt-0.5">{theme.tag}</div>
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
                                          Target milestone scheduled in <span className="font-semibold text-fg-primary">{mo}</span>. Related module procurement orders are scheduled <span className="font-semibold text-fg-primary">{p.type === 'China' || p.type === 'SEA' ? '136' : '98'} days earlier</span>.
                                        </div>
                                      )}
                                    </div>
                                  );
                                })()}

                                {/* Say plainly how much of the figure is already late */}
                                {overdueVal > 0 && (
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
                                  const phases = p.month_phases?.[mo] ?? [];
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
                                    const date = field === 'order' ? ph.order_date : field === 'tc' ? ph.tc_date : ph.ftc_date;
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
                                          <span className="font-mono text-[9px] tabular-nums text-fg-tertiary">{qty(ph)}</span>
                                        </div>
                                        <div className={`font-mono text-[10.5px] font-bold tabular-nums ${text}`}>
                                          {date}
                                        </div>
                                        {field === 'order' && ph.delay_months > 0 && (
                                          <div className="mt-0.5 font-mono text-[9px] font-bold leading-tight tabular-nums text-status-critical-fg">
                                            delayed to {ph.order_month} (+{ph.delay_months}mo)
                                          </div>
                                        )}
                                        {field === 'ftc' && !ph.ftc_reachable && (
                                          <div className="mt-0.5 text-[9px] font-bold leading-tight text-status-critical-fg">
                                            not achievable &mdash; {ph.ftc_short_days}d short
                                          </div>
                                        )}
                                      </div>
                                    );
                                  };

                                  /* The milestones in view, and the gap label that sits between
                                     each pair. Built as data so the grid can size itself: the
                                     Unit and Milestone selectors both change how many there are. */
                                  const lead = p.type === 'China' || p.type === 'SEA' ? 136 : 98;
                                  type Milestone = {
                                    title: string; text: string; border: string; bg: string;
                                    field?: 'order' | 'tc' | 'ftc'; gapBefore?: string;
                                  };
                                  const milestones: Milestone[] = [];
                                  if (milestoneFilter === 'all' || milestoneFilter === 'module') {
                                    milestones.push({ title: 'Module Order', field: 'order', text: 'text-primary',
                                      border: 'border-primary/30', bg: 'bg-primary/[0.07]' });
                                  }
                                  if (milestoneFilter === 'all' || milestoneFilter === 'tc') {
                                    milestones.push({ title: 'TC Date', field: 'tc', text: 'text-status-risk-fg',
                                      border: 'border-status-risk-border', bg: 'bg-status-risk-bg/60',
                                      gapBefore: milestones.length ? `${lead}d Lead` : undefined });
                                  }
                                  if (milestoneFilter === 'all' || milestoneFilter === 'ftc') {
                                    milestones.push({ title: 'FTC Date', field: 'ftc', text: 'text-status-healthy-fg',
                                      border: 'border-status-healthy-border', bg: 'bg-status-healthy-bg/60',
                                      gapBefore: milestones.length ? '45d Install' : undefined });
                                  }
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
                                          Ordering in {mo} &middot; {phases.length} phase{phases.length === 1 ? '' : 's'}
                                        </span>
                                        <span className="font-mono text-[10px] tabular-nums text-fg-secondary">
                                          taking <span className="font-bold text-fg-primary">{takenLabel}</span>
                                        </span>
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
                                              {x.phase_label && !/^(main|project balance)$/i.test(x.phase_label) ? `${x.phase_label} ` : ''}moved by vendor quota
                                            </span>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })()}

                                {/* One verdict for this month, read off the phases above. An
                                    unreachable FTC outranks everything else: it is the fact that
                                    decides whether the order, as scheduled, still works. */}
                                {unreachable.length > 0 ? (
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
                                    Every FTC above is reachable, but{' '}
                                    <span className="font-semibold">
                                      {ltaLate.length} of {cellPhases.length} phase{cellPhases.length === 1 ? '' : 's'}
                                    </span>{' '}
                                    charges only after the LTA of <span className="font-semibold">{p.lta}</span> &mdash;
                                    transmission, not supply, is the binding constraint here.
                                  </div>
                                ) : p.planning_flags?.includes('extended_to_lta') ? (
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
                              </div>
                            ) : undefined}
                          >
                            {getChipsForMonth(p, mo, val, milestoneFilter, unitToggle).length > 0 ? (
                              <div className="flex flex-col items-end justify-center w-full gap-1.5">
                                <div className="flex flex-col items-end gap-1 w-full">
                                  {getChipsForMonth(p, mo, val, milestoneFilter, unitToggle).map((c, idx) => (
                                    <div key={idx} className={`relative px-1.5 py-[2px] rounded flex items-center font-bold whitespace-nowrap overflow-hidden max-w-full shadow-sm
                                      ${c.type === 'tc' ? 'bg-primary/20 text-primary border border-primary/30 shadow-primary/20' : 
                                        c.type === 'module' ? 'bg-status-risk-bg text-status-risk-fg border border-status-risk-border shadow-status-risk-fg/20' : 
                                        'bg-status-healthy-bg text-status-healthy-fg border border-status-healthy-border shadow-status-healthy-fg/20'}`}>
                                      {isShifted && (
                                        <div
                                          className={`absolute top-0 right-0 w-0 h-0 border-t-[10px] border-l-[10px] border-l-transparent ${shiftTriangleColor} opacity-100 z-10 drop-shadow-sm`}
                                          title={shiftLabel}
                                        />
                                      )}
                                      {theme.dotColor && <span className={`w-1.5 h-1.5 rounded-full ${theme.dotColor} shrink-0 mr-1.5 relative z-20`} />}
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
                      {isColVisible('month_wise') && <Td align="right" className="font-semibold text-foreground tabular-nums">
                        {p.balance_ordering_mwp > 0 ? MW(p.balance_ordering_mwp) : '-'}
                      </Td>}
                      {isColVisible('ftc_date') && <Td className={SECTION_EDGE}>
                        {p.ftc_date
                          ? <DatedPhases value={p.ftc_date} />
                          : p.ftc_all_charged
                            ? <Tip text="Every FTC phase for this project is already charged, so no delivery date is pending"><span className="text-muted-foreground">No pending FTC</span></Tip>
                            : '-'}
                      </Td>}
                      {isColVisible('module_ordering_date') && <Td>{p.tc_date ? <DatedPhases value={p.tc_date} /> : '-'}</Td>}
                      {isColVisible('tc_delivery_date') && <Td>{p.module_date ? <DatedPhases value={p.module_date} /> : '-'}</Td>}
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
                              text={p.remarks ? `${p.remarks}${p.ai_suggestion ? `\n\n💡 AI Suggestion:\n${p.ai_suggestion}` : ''}` : undefined}
                              className="overflow-hidden flex-1"
                            >
                              <span className={`block truncate text-[10px] ${p.remarks ? (p.perspectives ? 'text-primary/90 font-medium' : 'text-foreground/90') : 'text-muted-foreground'}`}>
                                {p.remarks || '-'}
                              </span>
                            </Tip>
                          </div>
                          {p.perspectives && (
                            <Tip text="View 360° AI Multi-Perspective Strategy">
                              <button
                                type="button"
                                onClick={() => setActivePerspectiveProject(p)}
                                className="shrink-0 flex items-center gap-1 rounded border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-[9px] font-bold tracking-wide text-primary shadow-sm hover:bg-primary hover:text-primary-foreground transition-colors"
                              >
                                <Bot className="w-2.5 h-2.5" />
                                <span>AI</span>
                              </button>
                            </Tip>
                          )}
                        </div>
                      </Td>}
                    </tr>
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
                {isColVisible('balance_dispatch') && <Td align="right" className="text-foreground tabular-nums">{MW(t.balance_dispatch_mwp)}</Td>}
                {isColVisible('status') && <Td className={SECTION_EDGE} />}
                {isColVisible('month_wise') && <>
                {FORECAST_MONTHS.map((mo, i) => {
                  const mTotal = sum(filtered, p => p.month_mwp?.[mo] || 0);
                  const acTotal = sum(filtered, p => {
                    const v = p.month_mwp?.[mo] || 0;
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
                  {MW(sum(filtered, p => p.balance_ordering_mwp || 0))}
                </Td>
                </>}
                {isColVisible('ftc_date') && <Td className={SECTION_EDGE} />}
                {isColVisible('module_ordering_date') && <Td />}
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
                <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                  Monthly ordering plan by origin, respecting factory quotas.
                  <InfoTip
                    info="Monthly factory/import quotas (China 750, SEA 500, ALMM 500, ALCM & DCR 100 MWp) are planning assumptions built into the engine. Confirm against contracts before relying on them as hard limits."
                    align="left"
                  />
                </p>
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
                    <Td align="right" className="text-muted-foreground">{MW(v.monthly_cap_mwp)}</Td>
                    {v.allocated_by_month.map((val, i) => {
                      const pctUsed = v.utilization_pct_by_month[i] ?? 0;
                      const tone = pctUsed >= 100 ? 'critical' : pctUsed >= 80 ? 'risk' : pctUsed >= 50 ? 'watch' : 'healthy';
                      return (
                        <Td key={FORECAST_MONTHS[i]} align="right"
                          tip={val > 0 ? `${source} in ${FORECAST_MONTHS[i]}\nConsuming: ${MW(v.allocated_by_month_mwac?.[i] ?? 0)} MWac of ${MW(v.monthly_cap_mwac ?? v.monthly_cap_mwp)} MWac quota (${Math.round(pctUsed)}%)` : undefined}>
                          {val > 0 ? (
                            <div className="flex flex-col items-end gap-0.5 py-0.5">
                              <span className="tabular-nums">{MW(v.allocated_by_month_mwac?.[i] ?? 0)}</span>
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
                  <Td align="right" className="text-foreground tabular-nums">
                    {MW(capacitySources.reduce((s, [, v]) => s + (v.monthly_cap_mwac ?? v.monthly_cap_mwp), 0))}
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

      {/* ── 360° MULTI-PERSPECTIVE MODAL ────────────────────────────────────── */}
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
    </div>
  );
}
