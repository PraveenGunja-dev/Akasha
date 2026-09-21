import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import {
  Package, Sun, Truck, CheckCircle2, Clock, Search,
  AlertTriangle, ChevronDown, ChevronRight, Download, RefreshCw,
  Layers, BarChart3, Sparkles, ShieldCheck, Activity, Zap,
  Bot, X, Send, ArrowRight, Star
} from 'lucide-react';
import type { ModuleDeliveriesSummary, ModuleProject } from './types';
import { useChartTheme } from '../../lib/chartTheme';
import { FORECAST_MONTHS, exportModuleDeliveriesXLSX, moduleExportName } from './export';
import { InfoTip } from '../../components/ui/primitives/InfoTip';
import { MiniMeter } from '../../components/ui/primitives/Meter';

/* ═══════════════════════════════════════════════════════════════════════════
   MODULE DELIVERIES & FORECAST
   CEO-grade view replicating the PDF tracker with live SAP/P6/TC data.
   ═══════════════════════════════════════════════════════════════════════════ */

const API = import.meta.env.VITE_API_BASE || '';

const DateChipGroup = ({ dateStr, colorClass, borderColorClass, badgeBgClass }: { dateStr?: string | null, colorClass: string, borderColorClass: string, badgeBgClass: string }) => {
  if (!dateStr || dateStr === 'N/A') return <span className={`font-mono text-[11px] font-semibold ${colorClass}`}>N/A</span>;
  
  const parts = dateStr.split(' · ');
  return (
    <div className="flex flex-wrap gap-1.5 mt-1 mb-1">
      {parts.map((part, i) => {
        const colonIdx = part.indexOf(':');
        if (colonIdx !== -1) {
          const label = part.substring(0, colonIdx).trim();
          const date = part.substring(colonIdx + 1).trim();
          return (
            <div key={i} className={`flex items-center rounded overflow-hidden border ${borderColorClass} bg-neutral-900/50 whitespace-nowrap`}>
              <span className={`px-1.5 py-0.5 text-[9.5px] uppercase tracking-wider font-bold ${badgeBgClass} text-neutral-300 whitespace-nowrap`}>{label}</span>
              <span className={`px-2 py-0.5 font-mono text-[10.5px] font-bold ${colorClass} whitespace-nowrap`}>{date}</span>
            </div>
          );
        } else {
          return (
            <div key={i} className={`flex items-center rounded overflow-hidden border ${borderColorClass} bg-neutral-900/50 whitespace-nowrap`}>
              <span className={`px-2 py-0.5 font-mono text-[10.5px] font-bold ${colorClass} whitespace-nowrap`}>{part}</span>
            </div>
          );
        }
      })}
    </div>
  );
};

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
function getChipsForMonth(p: any, mo: string, cellVal: number): ChipData[] {
  const chips: ChipData[] = [];
  if (!p.balance_ordering_mwp || p.balance_ordering_mwp <= 0) return chips;

  // The cellVal tracks TC Ordering, so it represents the Blue chip
  if (cellVal > 0) {
      const ac = Math.round(p.ol > 0 ? cellVal / p.ol : cellVal / 1.35);
      chips.push({ label: `${Math.round(cellVal)} / ${ac}`, phase: null, type: 'tc' });
  }

  const now = new Date();

  const parseSegments = (val: string, type: 'tc' | 'module' | 'ftc') => {
    if (!val) return;
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
              chips.push({ label: `${dc} / ${ac}`, phase: parts[0], type });
            } else {
              chips.push({ label: mwMatch[1], phase: parts[0], type });
            }
          } else {
            chips.push({ label: '-', phase: parts[0], type });
          }
        } else {
          const phasesCount = val.split(' · ').length;
          const dc = p.balance_ordering_mwp / (phasesCount || 1);
          const ac = Math.round(p.ol > 0 ? dc / p.ol : dc / 1.35);
          chips.push({ label: `${Math.round(dc)} / ${ac}`, phase: null, type });
        }
      }
    });
  };
  
  // DB tc_date = Module delivery dates (later) → Yellow chips  
  parseSegments(p.tc_date, 'module');
  // FTC Date (Green)
  parseSegments(p.ftc_date, 'ftc');
  return chips;
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
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-mono font-bold text-amber-300 bg-amber-500/20 border border-amber-500/40">
                {tok}
              </span>
            );
          }
          // Month-Year (e.g. Sep-26, May-26)
          if (/^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-mono font-bold text-emerald-300 bg-emerald-500/20 border border-emerald-500/40">
                {tok}
              </span>
            );
          }
          // X days overdue
          if (/days?\s*overdue/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-bold text-rose-300 bg-rose-500/25 border border-rose-500/50 shadow-sm animate-pulse">
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
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-bold text-emerald-300 bg-emerald-500/20 border border-emerald-500/40">
                ⚡ {tok}
              </span>
            );
          }
          // Lead time (e.g. 98d, 136d, 45d)
          if (/^\d+d$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-mono font-bold text-purple-300 bg-purple-500/20 border border-purple-500/40">
                {tok}
              </span>
            );
          }
          // General days mention (e.g. 30 days, 45 days)
          if (/^\d+\s*days$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1 py-0.5 mx-0.5 rounded font-medium text-amber-200 bg-amber-500/15 border border-amber-500/30">
                {tok}
              </span>
            );
          }
          return <span key={tIdx}>{tok}</span>;
        });

        if (isSuggestion) {
          return (
            <div key={pIdx} className="mt-2.5 pt-2 border-t border-neutral-700/80 bg-primary/10 -mx-1 px-3 py-2 rounded-lg border border-primary/30">
              <div className="flex items-center gap-1.5 text-[11px] font-bold text-amber-300 mb-1">
                <span>💡 AI Strategic Recommendation</span>
              </div>
              <div className="text-[11px] leading-relaxed text-neutral-100 font-normal">
                {renderedTokens}
              </div>
            </div>
          );
        }

        return (
          <div key={pIdx} className="text-[11px] leading-relaxed text-neutral-100 font-normal">
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
  const targetWidth = isDetailed ? 540 : 260;

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
            style={{ width: `${renderWidth}px` }}
            className="block rounded-xl bg-neutral-950/95 backdrop-blur-md border border-neutral-700/80 p-3.5 text-[11px] text-left leading-relaxed font-medium text-neutral-100 shadow-2xl shadow-black/90 whitespace-pre-line break-words cursor-auto"
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
  const color = value === 0 ? 'text-muted-foreground' : pct >= 0.95 ? 'text-emerald-600 dark:text-emerald-400 font-medium' : pct >= 0.5 ? 'text-foreground' : 'text-amber-600 dark:text-amber-400';
  return <Td align="right" className={`${color} ${className}`}>{value > 0 ? MW(value) : '-'}</Td>;
}

/* ── Best-in-Class Priority & Quota Cell Theming ────────────────────────── */
function getMonthCellTheme(
  val: number,
  priority: string | undefined,
  flags: string[] | undefined
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

  const p = (priority || 'standard').toLowerCase();
  const isLeveled = flags?.includes('leveled_early');
  const isDelayed = flags?.includes('capacity_delayed');
  const isLtaExtended = flags?.includes('extended_to_lta');

  if (p === 'p1') {
    return {
      cellClass: 'bg-rose-500/15 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 font-semibold border-y border-rose-500/30 hover:bg-rose-500/25 transition-colors',
      badgeClass: 'bg-rose-500/20 text-rose-700 dark:text-rose-200 border border-rose-500/40',
      dotColor: 'bg-rose-500 ring-2 ring-rose-500/30 animate-pulse',
      label: MW(val),
      tag: 'P1 Priority (Critical COD/PPA)',
    };
  }

  if (p === 'p2') {
    return {
      cellClass: 'bg-amber-500/15 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 font-semibold border-y border-amber-500/30 hover:bg-amber-500/25 transition-colors',
      badgeClass: 'bg-amber-500/20 text-amber-700 dark:text-amber-200 border border-amber-500/40',
      dotColor: 'bg-amber-500',
      label: MW(val),
      tag: 'P2 Priority (Fast-Track)',
    };
  }

  if (isDelayed) {
    return {
      cellClass: 'bg-red-500/15 dark:bg-red-950/40 text-red-700 dark:text-red-300 font-semibold border-y border-red-500/30 hover:bg-red-500/25 transition-colors',
      badgeClass: 'bg-red-500/20 text-red-700 dark:text-red-200 border border-red-500/40',
      dotColor: 'bg-red-500',
      label: MW(val),
      tag: 'Delayed past LTA (Vendor Quota Full, Critical Commercial Risk)',
    };
  }

  if (isLtaExtended) {
    return {
      cellClass: 'bg-yellow-500/15 dark:bg-yellow-950/40 text-yellow-700 dark:text-yellow-300 font-semibold border-y border-yellow-500/30 hover:bg-yellow-500/25 transition-colors',
      badgeClass: 'bg-yellow-500/20 text-yellow-700 dark:text-yellow-200 border border-yellow-500/40',
      dotColor: 'bg-yellow-500',
      label: MW(val),
      tag: 'Extended to LTA (Vendor Quota Full, Safe for Transmission)',
    };
  }

  if (isLeveled) {
    return {
      cellClass: 'bg-purple-500/15 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 font-semibold border-y border-purple-500/30 hover:bg-purple-500/25 transition-colors',
      badgeClass: 'bg-purple-500/20 text-purple-700 dark:text-purple-200 border border-purple-500/40',
      dotColor: 'bg-purple-500',
      label: MW(val),
      tag: 'Quota Leveled (Pulled Early)',
    };
  }

  return {
    cellClass: 'bg-emerald-500/10 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 font-medium border-y border-emerald-500/25 hover:bg-emerald-500/20 transition-colors',
    badgeClass: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-200 border border-emerald-500/30',
    dotColor: 'bg-emerald-500',
    label: MW(val),
    tag: 'Standard Schedule',
  };
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN PAGE COMPONENT
   ═══════════════════════════════════════════════════════════════════════════ */

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

  const loadData = React.useCallback((sc = scenario, prio = priorities) => {
    setLoading(true);
    const params = new URLSearchParams();
    if (sc) params.append('scenario', sc);
    if (Object.keys(prio).length > 0) {
      params.append('priorities', JSON.stringify(prio));
    }
    return fetch(`${API}/akasha/api/module-deliveries/summary?${params.toString()}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [scenario, priorities]);

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
    try {
      await fetch(`${API}/akasha/api/mappings/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_tracked }),
      });
      await loadData();
    } catch (e) {
      console.error("Failed to update tracking status", e);
    }
  };

  // Filtered projects
  const filtered = useMemo(() => {
    if (!data) return [];
    return data.projects.filter(p => {
      if (scope === 'tracker' && (p.cluster !== 'Solar Khavda' || p.is_commissioned || p.is_tracked === false)) return false;
      if (statusFilter !== 'all') {
        if (statusFilter === 'needs_ordering') {
          if (p.balance_ordering_mwp <= 0) return false;
          const isException = (p.excluded_module_date_mwp ?? 0) > 0;
          if (!isException && !hasApproachingDate(p.module_date)) return false;
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
  }, [data, search, statusFilter, scope]);

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
        : groupBy === 'category' ? (p.category || 'Unknown')
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
      await exportModuleDeliveriesXLSX(grouped, data.totals, data, moduleExportName('xlsx'), milestoneFilter);
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

      {/* ── HEADER ────────────────────────────────────────────────────────── */}
      <motion.div variants={item} initial="hidden" animate="show" className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="rounded-lg border border-border bg-[var(--surface-sunken)] p-1.5">
              <Package className="w-4 h-4 text-primary" />
            </div>
            <h1 className="text-xl font-semibold text-foreground tracking-tight">Module Deliveries &amp; Forecast</h1>
          </div>
          <p className="text-xs text-muted-foreground">
            Khavda FY 26-27 Solar Projects · Live data from SAP, P6 &amp; Transmission · Updated {new Date(data.generated_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {data.data_coverage.with_sap_data}/{data.data_coverage.total_projects} with SAP data
          </span>
        </div>
      </motion.div>

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
      {(exceptionOrderProjects.length > 0 || approachingOrderProjects.length > 0) && (
        <motion.div variants={item} className="grid grid-cols-1 lg:grid-cols-2 gap-2">
          {exceptionOrderProjects.length > 0 && (
            <div className="flex items-center justify-between gap-4 rounded-md border px-4 py-3 text-sm"
              style={{ borderColor: 'var(--status-critical-border)', background: 'var(--status-critical-bg)', color: 'var(--status-critical-fg)' }}>
              <div className="flex items-center gap-3">
                <AlertTriangle className="h-5 w-5 shrink-0" />
                <div>
                  <p className="font-semibold">Immediate Exception Orders Required</p>
                  <p className="opacity-90 text-[13px]">
                    {exceptionOrderProjects.length} project(s) have a phase whose module date has already passed — its ordering window is gone, so it's excluded from the monthly plan and needs to be placed now as an exception ({MW(sum(exceptionOrderProjects, p => p.excluded_module_date_mwp ?? 0))} MWp total).
                  </p>
                </div>
              </div>
              {statusFilter !== 'needs_ordering' && (
                <button
                  onClick={() => setStatusFilter('needs_ordering')}
                  className="shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
                  style={{ background: 'var(--status-critical-fg)' }}
                >
                  Review Projects
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
                  <p className="font-semibold">Module Ordering Coming Up</p>
                  <p className="opacity-90 text-[13px]">{approachingOrderProjects.length} project(s) have a Module Date within the next 14 days and still require procurement (Balance Ordering &gt; 0).</p>
                </div>
              </div>
              {statusFilter !== 'needs_ordering' && (
                <button
                  onClick={() => setStatusFilter('needs_ordering')}
                  className="shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
                  style={{ background: 'var(--status-watch-fg)' }}
                >
                  Review Projects
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
              <option value="needs_ordering">Needs Ordering</option>
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
            <Sparkles className="w-3.5 h-3.5 text-primary" />
            <span className="text-[10px] font-semibold text-primary uppercase tracking-wider">Scenario</span>
            <select value={scenario} onChange={e => handleScenarioChange(e.target.value as 'v1_baseline' | 'v2_strategic' | 'v3_commercial')}
              className="pl-2 pr-6 py-1 bg-primary/10 border border-primary/30 rounded-md text-[11px] font-semibold text-primary focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer"
            >
              <option value="v1_baseline">V1 Baseline</option>
              <option value="v2_strategic">V2 Strategic</option>
              <option value="v3_commercial">V3 PPA Safeguard</option>
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
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span className="text-[10px] tabular-nums text-muted-foreground">{filtered.length} of {data.projects.length} projects</span>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-primary disabled:opacity-60 shadow-sm"
          >
            {exporting
              ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Preparing…</>
              : <><Download className="w-3.5 h-3.5" /> Export to Excel</>}
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
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-rose-500/30 bg-rose-500/15 text-rose-700 dark:text-rose-300 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
              P1 Critical / COD Urgent
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-300 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              P2 Elevated Priority
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-purple-500/30 bg-purple-500/15 text-purple-700 dark:text-purple-300 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-500" />
              Quota Leveled (Pulled Early)
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-orange-500/30 bg-orange-500/15 text-orange-700 dark:text-orange-300 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />
              Capacity Overload (exceeds monthly quota)
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Standard P6 Scheduled
            </span>
          </div>
          <span className="text-[10px] text-muted-foreground italic">
            * Click project's Priority badge to toggle Std → P1 → P2 &amp; auto-recalculate schedule. Capacity Overload means this order exceeds the source's assumed monthly quota — it's still placed on time against its module-date deadline rather than deferred, since a deadline can't slip but the quota assumption can.
          </span>
        </div>

        <div className="max-h-[72vh] overflow-auto custom-scrollbar">
          <table className="min-w-full text-left border-separate border-spacing-0">
            <thead className="sticky top-0 z-40">
              <tr>
                <Th stickyLeft={0} rowSpan={2} className="w-[34px] min-w-[34px]">Sr</Th>
                <Th stickyLeft={34} rowSpan={2} className="min-w-[188px] text-left">Project</Th>
                <Th rowSpan={2} className="min-w-[178px] text-left">P6 Name</Th>
                <Th rowSpan={2} className="min-w-[62px]">SPV</Th>
                <Th rowSpan={2} className="min-w-[46px]">Plot</Th>
                <Th rowSpan={2} className="min-w-[62px]">Category</Th>
                <Th rowSpan={2} className="min-w-[52px]">Type</Th>
                <Th rowSpan={2} className="min-w-[46px]"><ThLabel label="MMS" unit="Type" /></Th>
                <Th rowSpan={2} className="min-w-[124px] text-left">AGEL / EPC</Th>
                <Th rowSpan={2} className="min-w-[62px]">Priority</Th>
                <Th rowSpan={2} className={`min-w-[38px] ${SECTION_EDGE}`}>OL</Th>
                <Th rowSpan={2} className="min-w-[58px]"><ThLabel label="Capacity" unit="(MWac)" /></Th>
                <Th rowSpan={2} className="min-w-[58px]"><ThLabel label="Capacity" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="FTC Completed" unit="(MWp)" /></Th>
                <Th rowSpan={2} className={`min-w-[74px] ${SECTION_EDGE}`}><ThLabel label="Connectivity" unit="Phase" /></Th>
                <Th rowSpan={2} className="min-w-[62px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    LTA
                    <InfoTip info="Long Term Access date (pulled from ECOD in master sheets)" align="center" />
                  </div>
                </Th>
                <Th rowSpan={2} className="min-w-[80px]">SCOD</Th>
                <Th rowSpan={2} className="min-w-[66px]"><ThLabel label="AOP" unit="(Plan)" /></Th>
                <Th rowSpan={2} className={`min-w-[64px] ${SECTION_EDGE}`}><ThLabel label="Ordered" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Balance Ordering" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Total Receipt" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Erection done" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Module Inventory" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Under Transit" unit="(MWp)" /></Th>
                <Th rowSpan={2} className="min-w-[64px]"><ThLabel label="Balance Dispatch" unit="(MWp)" /></Th>
                <Th rowSpan={2} className={`min-w-[78px] ${SECTION_EDGE}`}>Status</Th>
                <Th colSpan={FORECAST_MONTHS.length + 1} className={SECTION_EDGE} tip="AI Leveled Monthly Requirement: Backward-scheduled from FTC (-45d TC, -lead time) and leveled against vendor origin limits to protect COD milestones">
                  Month wise Module Requirement at Site (MWp / MWac)
                </Th>
                <Th rowSpan={2} className={`min-w-[76px] ${SECTION_EDGE}`}>
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="FTC" unit="Date" />
                    <InfoTip info="First Time Charging. Base date mapped for the project." align="center" />
                  </div>
                </Th>
                <Th rowSpan={2} className="min-w-[76px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="Module Ordering" unit="Date" />
                    <InfoTip info={<span>Trial Commissioning.<br/><b>Calculation:</b> FTC Date - 45 days.</span>} align="center" />
                  </div>
                </Th>
                <Th rowSpan={2} className="min-w-[76px]">
                  <div className="flex flex-col items-center justify-center gap-0.5">
                    <ThLabel label="TC Delivery" unit="Date" />
                    <InfoTip info={<span>Target delivery date at site.<br/><b>Calculation:</b> TC Date - Lead Time (98 or 136 days based on origin).</span>} align="center" />
                  </div>
                </Th>
                <Th rowSpan={2} className="min-w-[210px] text-left">Remarks</Th>
              </tr>
              <tr>
                {FORECAST_MONTHS.map((mo, i) => (
                  <Th key={mo} className={`min-w-[48px] font-semibold ${i === 0 ? SECTION_EDGE : ''}`}>{mo}</Th>
                ))}
                <Th className="min-w-[52px]">Total</Th>
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
                  {!collapsed.has(group) && projects.map((p, idx) => (
                    <tr key={p.id} className="group hover:bg-[var(--surface-sunken)]">
                      <Td stickyLeft={0} className="bg-card group-hover:bg-[var(--surface-sunken)] text-muted-foreground font-mono">{idx + 1}</Td>
                      <Td stickyLeft={34} align="left" className="bg-card group-hover:bg-[var(--surface-sunken)] font-medium text-foreground shadow-[1px_0_0_0_var(--border-default)]">
                        <div className="flex items-center gap-2">
                          <Tip text={p.is_tracked !== false ? "Tracked in Khavda (uncheck to move to All Projects)" : "Untracked (check to track in Khavda)"}>
                            <input 
                              type="checkbox" 
                              checked={p.is_tracked !== false}
                              onChange={(e) => toggleTracking(p.id, e.target.checked)}
                              className="w-3.5 h-3.5 rounded border-border text-primary cursor-pointer focus:ring-1 focus:ring-primary shrink-0"
                            />
                          </Tip>
                          <span className="truncate">{p.project_name || p.p6_name}</span>
                        </div>
                      </Td>
                      <Td align="left" className="text-muted-foreground">{p.p6_name || '-'}</Td>
                      <Td className="font-mono">{p.spv}</Td>
                      <Td className="font-mono">{p.plot}</Td>
                      <Td>{p.category || '-'}</Td>
                      <Td>{p.type}</Td>
                      <Td className="font-mono">{p.mms_type || '-'}</Td>
                      <Td align="left" className="font-medium">{p.epc || '-'}</Td>
                      <Td align="center">
                        <Tip text={`Click to toggle priority: Std → P1 → P2\nCurrent: ${p.priority || 'standard'}`}>
                          <button
                            type="button"
                            onClick={() => cyclePriority(p.id)}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold tracking-wider transition-all transform active:scale-95 ${
                              (p.priority || 'standard').toLowerCase() === 'p1'
                                ? 'bg-rose-500/20 text-rose-600 dark:text-rose-300 border border-rose-500/40 shadow-sm shadow-rose-500/20'
                                : (p.priority || 'standard').toLowerCase() === 'p2'
                                  ? 'bg-amber-500/20 text-amber-600 dark:text-amber-300 border border-amber-500/40'
                                  : 'bg-muted/60 text-muted-foreground hover:text-foreground border border-border/60'
                            }`}
                          >
                            {(p.priority || 'standard').toLowerCase() === 'p1' && (
                              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
                            )}
                            {(p.priority || 'standard').toUpperCase()}
                          </button>
                        </Tip>
                      </Td>
                      <Td align="right" className={SECTION_EDGE}>{p.ol > 0 ? p.ol.toFixed(2) : '-'}</Td>
                      <Td align="right">{MW(p.capacity_mwac)}</Td>
                      <Td align="right" className="font-semibold text-foreground">{MW(p.capacity_mwp)}</Td>
                      <Td align="right" className="font-semibold text-[var(--status-watch-fg)]">{p.completed_ftc_mwp > 0 ? MW(p.completed_ftc_mwp) : '-'}</Td>
                      <Td className={SECTION_EDGE}>{p.connectivity_phase || <span className="text-muted-foreground/50">-</span>}</Td>
                      <Td>{p.lta || '-'}</Td>
                      <td className={`px-1.5 py-[3px] text-center text-[10px] leading-[1.35] whitespace-nowrap ${GRID_LINE}`}>
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
                              className={`inline-flex items-center gap-1 rounded px-1 -mx-1 py-px text-[10px] decoration-dotted underline-offset-2 hover:bg-primary/5 hover:text-primary hover:underline focus:outline-none focus-visible:ring-1 focus-visible:ring-primary ${p.scod_source === 'manual_lta' ? 'text-amber-500 font-semibold' : 'text-foreground'}`}
                            >
                              <span>{p.scod || '-'}</span>
                              {p.scod_source === 'manual' && <Tip text="Manually entered"><span className="h-1 w-1 shrink-0 rounded-full bg-primary" /></Tip>}
                            </button>
                          </Tip>
                        )}
                      </td>
                      <Td>{p.aop_plan || '-'}</Td>
                      {/* An apportioned figure is derived, not measured — mark it. */}
                      <Td align="right" className={`${SECTION_EDGE} ${p.ordered_mwp === 0 ? 'text-muted-foreground' : ''}`}
                        tip={p.po_apportioned ? `Apportioned: ${p.po_share_pct}% of a PO on WBS shared with other projects` : undefined}>
                        {p.ordered_mwp > 0 ? MW(p.ordered_mwp) : '-'}
                        {p.po_apportioned && <span className="ml-0.5 text-[8px] align-super text-[var(--status-watch-fg)]">~</span>}
                      </Td>
                      <Td align="right" className={p.balance_ordering_mwp > 0 ? 'text-[var(--status-critical-fg)]' : 'text-muted-foreground'}>
                        {p.balance_ordering_mwp > 0 ? MW(p.balance_ordering_mwp) : '-'}
                      </Td>
                      <MwCell value={p.total_receipt_mwp} cap={p.ordered_mwp} />
                      <Td align="right"
                        tip={p.erection_done_mwp > 0 ? 'Measured MWp installed, from the P6 Module Installation activities' : undefined}>
                        {p.erection_done_mwp > 0 ? MW(p.erection_done_mwp) : '-'}
                      </Td>
                      <Td align="right"
                        tip={p.module_inventory_negative
                          ? `SAP receipt (${MW(p.total_receipt_mwp)}) is below P6 erected (${MW(p.erection_done_mwp)}) — ZSPS carries no delivery history for this project. MB52 stock on hand: ${MW(p.module_inventory_sap_mwp)} MWp`
                          : undefined}>
                        {p.module_inventory_mwp > 0 ? MW(p.module_inventory_mwp) : '-'}
                      </Td>
                      <Td align="right">{p.under_transit_mwp > 0 ? MW(p.under_transit_mwp) : '-'}</Td>
                      <Td align="right" className={p.balance_dispatch_mwp > 0 ? 'text-[var(--status-risk-fg)]' : 'text-muted-foreground'}>
                        {p.balance_dispatch_mwp > 0 ? MW(p.balance_dispatch_mwp) : '-'}
                      </Td>
                      <Td className={SECTION_EDGE}><StatusBadge status={p.status} /></Td>
                      {FORECAST_MONTHS.map((mo, i) => {
                        const val = p.month_mwp?.[mo] || 0;
                        const theme = getMonthCellTheme(val, p.priority, p.planning_flags);
                        return (
                          <Td
                            key={mo}
                            align="right"
                            className={`${i === 0 ? SECTION_EDGE : ''}`}
                            tipWide
                            tipContent={(val > 0 || getChipsForMonth(p, mo, val).length > 0) ? (
                              <div className="space-y-2 text-left">
                                <div>
                                  <div className="font-semibold text-neutral-50">{p.project_name || p.p6_name}</div>
                                  <div className="text-[10px] text-neutral-400 mt-0.5">{theme.tag}</div>
                                </div>
                                <div className="flex items-center gap-1.5 text-[11px] pt-2 border-t border-neutral-800">
                                  <span className="text-neutral-400">Planned</span>
                                  <span className="inline-block px-1.5 py-0.5 rounded font-mono font-bold text-emerald-300 bg-emerald-500/20 border border-emerald-500/40">
                                    {MW(val)} MWp · {mo}
                                  </span>
                                </div>
                                <div className="pt-2 pb-1 border-t border-neutral-800">
                                  {(() => {
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
                                    const shiftColor = p.planning_flags?.includes('capacity_delayed') ? 'text-red-400' : p.planning_flags?.includes('extended_to_lta') ? 'text-purple-400' : 'text-cyan-400';
                                    const shiftBorder = p.planning_flags?.includes('capacity_delayed') ? 'border-red-500/30' : p.planning_flags?.includes('extended_to_lta') ? 'border-purple-500/30' : 'border-cyan-500/30';
                                    const shiftLabel = shiftMonths > 0 ? `${shiftMonths}mo Delay` : `${Math.abs(shiftMonths)}mo Early`;

                                      // 1. Identify which phases (if any) apply to this specific column's month (mo)
                                      const tcParts = (p.tc_date || '').split(' · ');
                                      const matchingTcParts = tcParts.filter(part => part.includes(mo));
                                      const matchingPhaseLabels = matchingTcParts.map(part => {
                                        const colonIdx = part.indexOf(':');
                                        return colonIdx !== -1 ? part.substring(0, colonIdx).trim() : null;
                                      }).filter(Boolean) as string[];
                                      const matchingPhasePrefixes = matchingPhaseLabels.map(l => l.split(' ')[0]);
  
                                      // 2. Generic filter function to narrow down any date string to the matched phases
                                      const filterPhases = (dateStr: string | null | undefined) => {
                                        if (!dateStr || matchingPhaseLabels.length === 0) return dateStr;
                                        const parts = dateStr.split(' · ');
                                        const matched = parts.filter(part => {
                                          const colonIdx = part.indexOf(':');
                                          if (colonIdx === -1) return true; // Keep parts without phase labels
                                          const label = part.substring(0, colonIdx).trim();
                                          return matchingPhaseLabels.includes(label) || matchingPhasePrefixes.some(pref => label.startsWith(pref));
                                        });
                                        return matched.length > 0 ? matched.join(' · ') : dateStr;
                                      };

                                      const renderRevised = (labelMo: string) => {
                                        if (!isShifted) return null;
                                        return (
                                          <div className="mt-2 pt-2 border-t border-neutral-700/50 flex flex-col items-center justify-center">
                                            <div className={`flex items-center gap-1 text-[9px] font-bold ${shiftColor} mb-1.5`}>
                                              <ArrowRight className="w-3 h-3 rotate-90" />
                                              {shiftLabel}
                                            </div>
                                            <div className={`text-[10.5px] font-mono font-bold ${shiftColor} bg-neutral-900/50 px-2 py-0.5 rounded border ${shiftBorder}`}>
                                              {labelMo}
                                            </div>
                                          </div>
                                        );
                                      };

                                      return (
                                      <div className="flex items-start justify-between group/timeline gap-1.5 w-full max-w-[500px]">
                                        {(milestoneFilter === 'all' || milestoneFilter === 'tc') && (
                                          <>
                                            {/* TC Block (Blue) */}
                                            <div className="flex-1 min-w-0 p-2 rounded-lg border-2 border-blue-500/80 bg-blue-500/20 shadow-[0_0_20px_rgba(59,130,246,0.25)] transition-all group-hover/timeline:opacity-40 hover:!opacity-100 cursor-default relative z-10">
                                              <div className="text-[9px] uppercase tracking-wider text-blue-500 font-bold mb-1.5 transition-colors flex items-center gap-1.5 whitespace-nowrap">
                                                <Star className="w-3 h-3 shrink-0 fill-blue-500 text-blue-500 animate-pulse drop-shadow-[0_0_4px_rgba(59,130,246,0.8)]" />
                                                TC Date
                                              </div>
                                              <DateChipGroup dateStr={filterPhases(p.tc_date)} colorClass="text-blue-200" borderColorClass="border-blue-500/50" badgeBgClass="bg-blue-900/80" />
                                              {renderRevised(mo)}
                                            </div>

                                            {/* Arrow 1 */}
                                            {milestoneFilter === 'all' && (
                                              <div className="flex flex-col items-center justify-center shrink-0 w-16 group-hover/timeline:opacity-40 transition-opacity mt-6">
                                                <div className="w-full flex items-center justify-center relative group-hover/timeline:translate-x-1 transition-transform">
                                                  <div className="h-[2px] w-full bg-gradient-to-r from-blue-500/70 via-amber-400/70 to-blue-500/70 bg-[length:200%_auto] animate-[gradient-flow_2s_linear_infinite] rounded-full" />
                                                  <ArrowRight className="w-3 h-3 text-amber-500 absolute -right-1" />
                                                </div>
                                                <div className="text-[8px] text-neutral-500 mt-1.5 font-medium whitespace-nowrap">{p.type === 'China' || p.type === 'SEA' ? 136 : 98}d Lead</div>
                                              </div>
                                            )}
                                          </>
                                        )}

                                        {(milestoneFilter === 'all' || milestoneFilter === 'module') && (
                                          <>
                                            {/* Module Block (Yellow) */}
                                            <div className="flex-1 min-w-0 p-2 rounded-lg border border-amber-500/20 bg-amber-500/5 shadow-[inset_0_0_12px_rgba(245,158,11,0.02)] transition-all group-hover/timeline:opacity-40 hover:!opacity-100 cursor-default">
                                              <div className="text-[9px] uppercase tracking-wider text-amber-500/80 font-bold mb-1.5 transition-colors whitespace-nowrap">Module Date</div>
                                              <DateChipGroup dateStr={filterPhases(p.module_date)} colorClass="text-amber-300" borderColorClass="border-amber-500/30" badgeBgClass="bg-amber-950/50" />
                                              {renderRevised((() => {
                                                const d = new Date(`${mo.split('-')[0]} 15, 20${mo.split('-')[1]}`);
                                                d.setDate(d.getDate() + (p.type === 'China' || p.type === 'SEA' ? 136 : 98));
                                                return d.toLocaleString('en-GB', { month: 'short', year: '2-digit' }).replace(' ', '-');
                                              })())}
                                            </div>

                                            {/* Arrow 2 */}
                                            {milestoneFilter === 'all' && (
                                              <div className="flex flex-col items-center justify-center shrink-0 w-16 group-hover/timeline:opacity-40 transition-opacity mt-6">
                                                <div className="w-full flex items-center justify-center relative group-hover/timeline:translate-x-1 transition-transform">
                                                  <div className="h-[2px] w-full bg-gradient-to-r from-amber-400/70 via-emerald-400/70 to-amber-400/70 bg-[length:200%_auto] animate-[gradient-flow_2s_linear_infinite] rounded-full" />
                                                  <ArrowRight className="w-3 h-3 text-emerald-500 absolute -right-1" />
                                                </div>
                                                <div className="text-[8px] text-neutral-500 mt-1.5 font-medium whitespace-nowrap">45d Install</div>
                                              </div>
                                            )}
                                          </>
                                        )}

                                        {(milestoneFilter === 'all' || milestoneFilter === 'ftc') && (
                                          <div className="flex-1 min-w-0 p-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 shadow-[inset_0_0_12px_rgba(16,185,129,0.02)] transition-all group-hover/timeline:opacity-40 hover:!opacity-100 cursor-default">
                                            <div className="text-[9px] uppercase tracking-wider text-emerald-500/80 font-bold mb-1.5 transition-colors whitespace-nowrap">FTC Date</div>
                                            <DateChipGroup dateStr={filterPhases(p.ftc_date)} colorClass="text-emerald-300" borderColorClass="border-emerald-500/30" badgeBgClass="bg-emerald-950/50" />
                                            {renderRevised((() => {
                                              const d = new Date(`${mo.split('-')[0]} 15, 20${mo.split('-')[1]}`);
                                              d.setDate(d.getDate() + (p.type === 'China' || p.type === 'SEA' ? 136 : 98) + 45);
                                              return d.toLocaleString('en-GB', { month: 'short', year: '2-digit' }).replace(' ', '-');
                                            })())}
                                          </div>
                                        )}

                                        {/* LTA Block (Purple) */}
                                        {p.lta && (
                                          <>
                                            <div className="flex flex-col items-center justify-center shrink-0 w-10 group-hover/timeline:opacity-40 transition-opacity mt-6">
                                              <div className="w-full flex items-center justify-center relative group-hover/timeline:translate-x-1 transition-transform">
                                                <div className="h-[2px] w-full bg-gradient-to-r from-emerald-400/70 via-purple-400/70 to-emerald-400/70 bg-[length:200%_auto] animate-[gradient-flow_2s_linear_infinite] rounded-full" />
                                                <ArrowRight className="w-3 h-3 text-purple-500 absolute -right-1" />
                                              </div>
                                            </div>
                                            <div className="flex-1 min-w-0 p-2 rounded-lg border border-purple-500/20 bg-purple-500/5 shadow-[inset_0_0_12px_rgba(168,85,247,0.02)] transition-all group-hover/timeline:opacity-40 hover:!opacity-100 cursor-default">
                                              <div className="text-[9px] uppercase tracking-wider text-purple-500/80 font-bold mb-1.5 transition-colors whitespace-nowrap">LTA Date</div>
                                              <DateChipGroup dateStr={filterPhases(p.lta)} colorClass="text-purple-300" borderColorClass="border-purple-500/30" badgeBgClass="bg-purple-950/50" />
                                            </div>
                                          </>
                                        )}
                                      </div>
                                    );
                                  })()}
                                </div>

                                {p.planning_flags?.includes('extended_to_lta') ? (
                                  <div className="text-[10.5px] text-amber-300 leading-relaxed pt-2 border-t border-neutral-800">
                                    ⚠️ Due to vendor capacity limits in earlier months, this order was extended to <span className="font-semibold">{mo}</span>. This misses the original TC date, but is still safe for transmission (LTA).
                                  </div>
                                ) : p.planning_flags?.includes('capacity_delayed') ? (
                                  <div className="text-[10.5px] text-red-300 leading-relaxed pt-2 border-t border-neutral-800">
                                    🚨 Due to vendor capacity limits, this order was delayed to <span className="font-semibold">{mo}</span>, which misses BOTH the FTC and LTA timelines! Critical commercial risk.
                                  </div>
                                ) : p.planning_flags?.includes('leveled_early') ? (
                                  <div className="text-[10.5px] text-purple-300 leading-relaxed pt-2 border-t border-neutral-800">
                                    ✨ To avoid vendor capacity limits in later months, this order was proactively pulled early to <span className="font-semibold">{mo}</span>. Materials will arrive ahead of schedule.
                                  </div>
                                ) : (
                                  <div className="text-[10.5px] text-neutral-300 leading-relaxed pt-2 border-t border-neutral-800">
                                    Ordering in <span className="text-emerald-300 font-semibold">{mo}</span> lands the material on site by Module Delivery Date, in time to support FTC.
                                  </div>
                                )}
                                {p.planning_flags?.includes('leveled_early') && (
                                  <div className="text-[10.5px] text-purple-300 pt-2 border-t border-neutral-800">
                                    ⚡ Leveled early to protect vendor monthly capacity limits
                                  </div>
                                )}
                              </div>
                            ) : undefined}
                          >
                            {getChipsForMonth(p, mo, val).length > 0 ? (
                              <div className="flex flex-col items-end justify-center w-full gap-1.5">
                                <div className="flex flex-col items-end gap-1 w-full">
                                  {getChipsForMonth(p, mo, val).map((c, idx) => (
                                    <div key={idx} className={`px-1.5 py-[2px] rounded flex items-center font-bold whitespace-nowrap overflow-hidden max-w-full shadow-sm
                                      ${c.type === 'tc' ? 'bg-blue-500/20 text-blue-600 border border-blue-500/50 shadow-blue-500/10' : 
                                        c.type === 'module' ? 'bg-amber-500/20 text-amber-600 border border-amber-500/50 shadow-amber-500/10' : 
                                        'bg-emerald-500/20 text-emerald-600 border border-emerald-500/50 shadow-emerald-500/10'}`}>
                                      {theme.dotColor && <span className={`w-1.5 h-1.5 rounded-full ${theme.dotColor} shrink-0 mr-1.5`} />}
                                      <span className="tabular-nums text-[11px] tracking-tight font-extrabold">{c.label.split(' / ')[0]} <span className="opacity-40 mx-px font-semibold">/</span> <span className="text-[10px] font-bold opacity-80">{c.label.split(' / ')[1] || ''}</span></span>
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
                      <Td align="right" className="font-semibold text-foreground tabular-nums">
                        {p.balance_ordering_mwp > 0 ? MW(p.balance_ordering_mwp) : '-'}
                      </Td>
                      <Td className={SECTION_EDGE}>
                        {p.ftc_date
                          ? <DatedPhases value={p.ftc_date} />
                          : p.ftc_all_charged
                            ? <Tip text="Every FTC phase for this project is already charged, so no delivery date is pending"><span className="text-muted-foreground">No pending FTC</span></Tip>
                            : '-'}
                      </Td>
                      <Td>{p.tc_date ? <DatedPhases value={p.tc_date} /> : '-'}</Td>
                      <Td>{p.module_date ? <DatedPhases value={p.module_date} /> : '-'}</Td>
                      <Td align="left" className="max-w-[280px] truncate text-muted-foreground"
                        tip={p.remarks ? `${p.remarks}${p.ai_suggestion ? `\n\n💡 AI Suggestion:\n${p.ai_suggestion}` : ''}` : undefined}>
                        <div className="flex items-center justify-between gap-1.5 overflow-hidden">
                          <div className="flex items-center gap-1.5 overflow-hidden">
                            {p.planning_flags?.includes('critical_ordering') && (
                              <Tip text="Critical: Immediate PO required due to lead time">
                                <span className="inline-block w-2 h-2 shrink-0 rounded-full bg-rose-500 animate-pulse" />
                              </Tip>
                            )}
                            {p.planning_flags?.includes('leveled_early') && (
                              <Tip text="Leveled early to avoid vendor monthly quota limit">
                                <span className="inline-block w-2 h-2 shrink-0 rounded-full bg-amber-500" />
                              </Tip>
                            )}
                            <span className={`truncate text-[10px] ${p.remarks ? 'text-foreground/90' : ''}`}>{p.remarks || '-'}</span>
                          </div>
                          {p.perspectives && (
                            <Tip text="View 360° AI Multi-Perspective Strategy">
                              <button
                                type="button"
                                onClick={() => setActivePerspectiveProject(p)}
                                className="shrink-0 rounded p-0.5 text-primary/70 hover:text-primary hover:bg-primary/10 transition-colors"
                              >
                                <Sparkles className="w-3 h-3" />
                              </button>
                            </Tip>
                          )}
                        </div>
                      </Td>
                    </tr>
                  ))}
                </React.Fragment>
              ))}

              {/* ── TOTALS ROW ──────────────────────────────────────────────── */}
              <tr className="border-t-2 border-[var(--neutral-700)] bg-[var(--neutral-200)] font-bold">
                {/* One cell per visible column — no colSpan arithmetic to drift
                    out of step when the view changes. */}
                <Td stickyLeft={0} className="bg-[var(--neutral-200)] text-muted-foreground">Σ</Td>
                <Td stickyLeft={34} align="left" className="bg-[var(--neutral-200)] text-foreground shadow-[1px_0_0_0_var(--border-default)]">Total ({filtered.length} projects)</Td>
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td className={SECTION_EDGE} />
                <Td align="right" className={`text-foreground tabular-nums `}>{MW(t.total_mwac)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.total_mwp)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.completed_ftc_mwp)}</Td>
                <Td className={SECTION_EDGE} />
                <Td />
                <Td />
                <Td />
                <Td align="right" className={`text-foreground tabular-nums ${SECTION_EDGE}`}>{MW(t.ordered_mwp)}</Td>
                <Td align="right" className="text-[var(--status-critical-fg)] tabular-nums">{MW(t.balance_ordering_mwp)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.received_mwp)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.erection_mwp)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.inventory_mwp)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.under_transit_mwp)}</Td>
                <Td align="right" className="text-foreground tabular-nums">{MW(t.balance_dispatch_mwp)}</Td>
                <Td className={SECTION_EDGE} />
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
                <Td className={SECTION_EDGE} />
                <Td />
                <Td />
                <Td />
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
        <motion.div variants={item} initial="hidden" animate="show" className="bento-card p-4">
          <div className="flex items-baseline justify-between gap-2 mb-1">
            <div className="flex items-center gap-1.5">
              <h2 className="text-sm font-semibold text-foreground">AI Procurement Plan — Ordering by Source</h2>
              <InfoTip
                info="Monthly factory/import quotas (China 750, SEA 500, ALMM 500, ALCM & DCR 100 MWp) are planning assumptions built into the engine, not measured vendor commitments — confirm against current contracts before relying on them as hard limits. Bars show each month's planned order against that assumed quota."
                align="center"
              />
            </div>
            <span className="section-label">MWp planned per month, by origin</span>
          </div>

          {data.strategic_briefing?.executive_takeaways && data.strategic_briefing.executive_takeaways.length > 0 && (
            <ul className="mb-3 flex flex-col gap-1">
              {data.strategic_briefing.executive_takeaways.map((line, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
                  <Sparkles className="w-3 h-3 mt-0.5 shrink-0 text-primary" />
                  {line}
                </li>
              ))}
            </ul>
          )}

          <div className="overflow-x-auto custom-scrollbar rounded-md border border-border">
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
                      ? 'bg-rose-500/20 text-rose-500 border border-rose-500/40'
                      : (activePerspectiveProject.priority || 'standard').toLowerCase() === 'p2'
                        ? 'bg-amber-500/20 text-amber-500 border border-amber-500/40'
                        : 'bg-emerald-500/20 text-emerald-500 border border-emerald-500/40'
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
                  <ShieldCheck className="w-4 h-4 text-rose-500" />
                  Commercial &amp; PPA Safeguard
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  {activePerspectiveProject.perspectives?.commercial || 'Standard PPA milestone alignment.'}
                </p>
              </div>

              {/* Supply Chain */}
              <div className="rounded-lg border border-border bg-muted/20 p-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-1">
                  <Truck className="w-4 h-4 text-amber-500" />
                  Supply Chain &amp; Quota
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  {activePerspectiveProject.perspectives?.supply_chain || 'Scheduled under monthly origin limits.'}
                </p>
              </div>

              {/* Site Execution */}
              <div className="rounded-lg border border-border bg-muted/20 p-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-1">
                  <Layers className="w-4 h-4 text-blue-500" />
                  Site Laydown &amp; Civil
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  {activePerspectiveProject.perspectives?.site_execution || 'Laydown readiness in sync with delivery target.'}
                </p>
              </div>

              {/* Grid Transmission */}
              <div className="rounded-lg border border-border bg-muted/20 p-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-1">
                  <Activity className="w-4 h-4 text-emerald-500" />
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
    </div>
  );
}
