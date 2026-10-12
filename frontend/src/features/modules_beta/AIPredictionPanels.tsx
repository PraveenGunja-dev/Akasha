/* BETA: two model-backed what-if forms shown under the AI Procurement Strategy.

   1. Module Ordering & TC Delivery Forecasting -> POST /api/ai/v1/order-tc-forecast?explain=true
   2. Priority Prediction                        -> POST /api/ai/v1/priority-predict?explain=true

   The AI service is separate from the Akasha backend (it runs on :8000). The
   page calls it through the Akasha backend's ai-proxy route, which forwards to
   AI_SERVICE_URL (default http://localhost:8000/api/ai/v1).

   Everything returned is a model prediction, not a plan or SAP figure, and is
   labelled that way. Any part of a response that is missing is simply not
   drawn - nothing is filled in on the client. */
import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Bot, Sparkles, Loader2, AlertTriangle, CalendarClock, ListOrdered, RotateCcw,
  ShieldAlert, Target, ListChecks, Scale, Info, ChevronRight, Timer, PackageSearch, X,
} from 'lucide-react';
import { InfoTip, MiniMeter, StatusPill, cx } from '../../components/ui/primitives';
import type { Tone } from '../../components/ui/primitives';

// Through the Akasha backend (routers/module_deliveries_beta.py ai_proxy), which
// forwards to the AI service - same origin and login, no web-server setup needed.
const AI_API_BASE: string = import.meta.env.VITE_AI_API_BASE || '/akasha/api/module-deliveries-beta/ai-proxy';

/* ── API contracts ─────────────────────────────────────────────────────── */

interface Explanation {
  mode?: string;              // 'template' | 'llm' …
  provider?: string | null;
  executive_summary?: string;
  rule_vs_ai_assessment?: string;
  key_drivers?: string[];
  risks_identified?: Record<string, string | null>;
  business_impact?: Record<string, string | null>;
  recommended_actions?: string[];
  /** Forecast only: one-line ordering status ('Overdue - order immediately'). */
  order_schedule_status_msg?: string;
  /** Forecast only: the answer in one line, for compact places. */
  short_insight?: string;
  text?: string;
  unverified_numbers?: unknown[];
  consistency_flags?: unknown[];
}

interface MatchedProject { p6_name?: string; pid?: number | string; project?: string; match_source?: string }

/** Guardrail shape is not fixed yet: null, a message, or an object. */
type Guardrail = string | Record<string, unknown> | null;

interface RootCause {
  predicted_ftc_shift_days?: number;
  breakdown?: { reason: string; days: number | null; note?: string }[];
  summary?: string;
}

interface RequirementMonth {
  month: string;                  // 'Jun-27' - the TC month modules are needed at site
  required_at_site_mwp?: number;
  required_at_site_mwac?: number;
  need_date?: string;
  order_by_date?: string;
  order_month?: string;
  overdue?: boolean;
  phases?: string[];
}

interface RequirementPlan {
  basis?: string;
  timed_by?: string;
  lead_time_days?: number;        // rule engine
  lead_time_p90_days?: number;    // AI
  order_by_rule?: string;
  total_mwp?: number;
  months?: RequirementMonth[];
}

interface MonthlyRequirement {
  unit_note?: string;
  balance_ordering_mwp?: number;
  balance_ordering_mwac?: number;
  rule_engine?: RequirementPlan;
  ai?: RequirementPlan;
  label?: string;
}

interface LeadTime {
  rule_engine_days?: number;
  rule_engine_basis?: string;
  ai_p50_days?: number;
  ai_p90_days?: number;
  ai_basis?: string;
  how_used?: string;
}

/** Model metadata: shared keys plus whatever each endpoint adds. */
interface ModelInfo {
  site_shift_days?: number;
  transmission_shift_days?: number;
  supply_shortfall_days?: number;
  lead_time_p50_days?: number;
  lead_time_p90_days?: number;
  deadline?: string;
  deadline_basis?: string;
  contract_type?: string;
  feature_coverage?: number;
  confidence_basis?: string;
  score_basis?: string;
  label_provenance?: string;
  assumptions?: string[];
  as_of?: string | null;
}

interface OrderTcForecastRequest {
  project_id: string;
  project_name: string;
  phase: string;
  vendor_type: string;
  priority: string;
  capacity_mwp: number;
  balance_ordering: number;
  inventory: number;
  receipt: number;
  under_transit: number;
  lta_date: string;   // YYYY-MM-DD
  scod_date: string;
  ftc_date: string;
}

/** Batch-scored results (the dashboard JSON) wrap each response with a status
 *  and the per-phase answers; a live API call carries none of these. */
interface BatchEnvelope {
  status?: 'scored' | 'not_scored' | string;
  reason?: string;            // why it was not scored
  phase?: string;             // the phase the top-level answer is for
  notes?: string[];           // data caveats the scorer raised
}

export interface ForecastPhase {
  phase: string;
  p6_ftc_date?: string | null;
  order_by_date?: string | null;
  recommended_order_date?: string | null;
  order_now?: boolean;
  predicted_tc_date?: string | null;
  predicted_tc_date_p90?: string | null;
  projected_ftc_date?: string | null;
  deadline_breach_days?: number | null;
  risk_level?: string | null;
  rule_engine?: { order_by_date?: string | null; tc_date?: string | null };
}

export interface PriorityPhase {
  phase: string;
  p6_ftc_date?: string | null;
  priority_class?: string | null;
  priority_score?: number | null;
  realistic_ftc_date?: string | null;
  rule_engine_priority?: string | null;
}

export interface OrderTcForecastResponse extends BatchEnvelope {
  phases?: ForecastPhase[];
  recommended_order_date?: string;
  predicted_tc_date?: string;
  confidence?: number;                  // 0–1
  risk_level?: string;                  // LOW / MEDIUM / HIGH
  order_by_date?: string;
  order_now?: boolean;
  predicted_tc_date_p90?: string;
  projected_ftc_date?: string;
  deadline_breach_days?: number;        // > 0 = after the deadline
  rule_engine?: { order_by_date?: string; tc_date?: string };
  order_by_shift_vs_rule_days?: number; // < 0 = AI orders earlier than the rule
  priority?: { current?: string; ai?: string; criticality_score?: number; guardrail?: Guardrail };
  project?: MatchedProject;
  root_cause?: RootCause;
  monthly_requirement?: MonthlyRequirement;
  lead_time?: LeadTime;
  model?: ModelInfo;
  explanation?: Explanation;
}

interface PriorityPredictRequest {
  project_id: string;
  project_name: string;
  phase: string;
  category: string;
  capacity_mwp: number;
  balance_ordering: number;
  inventory: number;
  receipt: number;
  under_transit: number;
  lta_date: string;
  scod_date: string;
  ftc_date: string;
  ftc_risk_flag: boolean;
  current_priority: string;
}

export interface PriorityPredictResponse extends BatchEnvelope {
  phases?: PriorityPhase[];
  priority_class?: string;
  priority_score?: number;              // 0–100
  reasons?: string[];
  rule_engine?: { priority_class?: string; basis?: string };
  class_probabilities?: Record<string, number>;
  ftc_date_used?: string;
  realistic_ftc_date?: string;
  guardrail?: Guardrail;
  project?: MatchedProject;
  model?: ModelInfo;
  explanation?: Explanation;
}

/** FastAPI errors: `detail` is a string, or a list of {loc, msg} for a 422. */
function describeError(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: any) => {
      const loc = Array.isArray(d?.loc) ? d.loc.filter((x: unknown) => x !== 'body').join('.') : '';
      return loc ? `${loc}: ${d?.msg ?? ''}` : String(d?.msg ?? JSON.stringify(d));
    }).join('; ');
  }
  return detail == null ? '' : JSON.stringify(detail);
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${AI_API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error('Could not reach the AI prediction service. Check that it is running.');
  }
  if (!res.ok) {
    let detail = '';
    try { detail = describeError((await res.json())?.detail); } catch { /* body was not JSON */ }
    const hint = res.status === 502 || res.status === 504 ? ' The AI service may not be running.' : '';
    throw new Error(`The prediction service returned ${res.status}${detail ? ` — ${detail}` : ''}.${hint}`);
  }
  return res.json();
}

/* ── Formatting ────────────────────────────────────────────────────────── */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** '2027-01-25' -> '25-Jan-27', the date style used across this page. */
const fmtDate = (iso?: string | null) => {
  const m = iso?.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso || '—';
  return `${m[3]}-${MONTHS[Number(m[2]) - 1] ?? m[2]}-${m[1].slice(2)}`;
};

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;

/** 408 -> '408', 99.6 -> '99.6', 1234.5 -> '1,234.5' */
const fmtNum = (v?: number | null, digits = 1) =>
  v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('en-IN', { maximumFractionDigits: digits });

/** Day counts arrive as floats (230.7); the UI speaks in whole days. */
const days = (v?: number | null) => (v == null || !Number.isFinite(v) ? null : Math.round(v));

const guardrailText = (g?: Guardrail) => {
  if (g == null) return null;
  if (typeof g === 'string') return g.trim() || null;
  const msg = g.message ?? g.reason ?? g.note ?? g.detail;
  return typeof msg === 'string' ? msg : JSON.stringify(g);
};

/** The guardrail as one note. An object guardrail can say it was NOT applied
 *  (a review reversed it) and which class the model alone gave. */
const guardrailNote = (g?: Guardrail) => {
  const text = guardrailText(g);
  if (!text) return null;
  if (typeof g !== 'object' || g == null) return `Guardrail: ${text}`;
  const applied = g.applied;
  const modelClass = typeof g.model_class === 'string' ? ` (model alone: ${g.model_class})` : '';
  return applied === false
    ? `Guardrail not applied${modelClass}: ${text}`
    : `Guardrail applied${modelClass}: ${text}`;
};

/** Whole days from a to b (b - a); null when either is missing. */
const daysBetween = (a?: string, b?: string) => {
  if (!a || !b) return null;
  const ta = Date.parse(a), tb = Date.parse(b);
  if (Number.isNaN(ta) || Number.isNaN(tb)) return null;
  return Math.round((tb - ta) / 86_400_000);
};

/** Confidence / probability arrives as 0–1; tolerate a 0–100 value too. */
const asPct = (v?: number | null) => (v == null || !Number.isFinite(v) ? null : Math.round(v <= 1 ? v * 100 : v));

/** 'vendor_capacity_risk' -> 'Vendor capacity', 'scod_impact' -> 'SCOD' */
const humanKey = (k: string) => {
  const base = k.replace(/_(risk|impact)$/, '').replace(/_/g, ' ');
  return base.replace(/\b(ftc|scod|lta|ld|aop|tc)\b/gi, s => s.toUpperCase()).replace(/^./, c => c.toUpperCase());
};

const riskTone = (r?: string): Tone => {
  const v = (r || '').toUpperCase();
  if (v === 'HIGH' || v === 'CRITICAL') return 'critical';
  if (v === 'MEDIUM') return 'risk';
  if (v === 'LOW') return 'healthy';
  return 'neutral';
};

const priorityTone = (p?: string): Tone => {
  const v = (p || '').toUpperCase();
  if (v === 'P1') return 'critical';
  if (v === 'P2') return 'risk';
  if (v === 'P3') return 'watch';
  return 'neutral';
};

/* ── Form controls (same input styling as the table toolbar) ───────────── */

const INPUT = 'w-full px-2.5 py-1.5 text-[12px] rounded-lg border border-border bg-card text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary tabular-nums';
const VENDOR_TYPES = ['ALMM', 'ALCM', 'DCR', 'China', 'SEA'];
const PRIORITIES = ['P1', 'P2', 'STANDARD'];

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 min-w-0">
      <span className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}{hint && <span className="ml-1 normal-case tracking-normal font-normal text-muted-foreground/70">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

type NumStr = string; // numeric fields are held as typed text so the box can be empty

const MwField = ({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: React.ChangeEventHandler<HTMLInputElement>; placeholder?: string;
}) => (
  <Field label={label} hint="MWp">
    <input required type="number" min={0} step="any" className={INPUT} value={value} onChange={onChange} placeholder={placeholder} />
  </Field>
);

const DateField = ({ label, value, onChange }: {
  label: string; value: string; onChange: React.ChangeEventHandler<HTMLInputElement>;
}) => (
  <Field label={label}>
    <input required type="date" className={INPUT} value={value} onChange={onChange} />
  </Field>
);

const SelectField = ({ label, value, options, onChange }: {
  label: string; value: string; options: string[]; onChange: React.ChangeEventHandler<HTMLSelectElement>;
}) => (
  <Field label={label}>
    <select required className={cx(INPUT, 'cursor-pointer')} value={value} onChange={onChange}>
      {options.map(v => <option key={v} value={v}>{v}</option>)}
    </select>
  </Field>
);

/* ── Shared shell ──────────────────────────────────────────────────────── */

function PanelShell({ icon, title, sub, info, children }: {
  icon: React.ReactNode; title: string; sub: string; info: string; children: React.ReactNode;
}) {
  return (
    <section className="relative overflow-hidden rounded-xl border border-primary/20 bg-gradient-to-br from-card to-primary/5 p-5 shadow-sm">
      <div className="relative z-10 flex flex-col gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <div className="flex items-center justify-center w-6 h-6 rounded-md bg-primary/10 text-primary">{icon}</div>
            <h2 className="text-base font-semibold text-foreground tracking-tight">{title}</h2>
            <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary border border-primary/20">
              <Sparkles className="mr-1 h-3 w-3" />
              AI Model · Beta
            </span>
          </div>
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            {sub}
            <InfoTip info={info} align="left" />
          </p>
        </div>
        {children}
      </div>
    </section>
  );
}

function FormActions({ loading, label, onReset, onSample }: {
  loading: boolean; label: string; onReset: () => void; onSample: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <button type="button" onClick={onSample} disabled={loading}
        className="px-3 py-1.5 rounded-lg text-[11px] font-semibold text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
        Fill sample
      </button>
      <button type="button" onClick={onReset} disabled={loading}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-card text-[11px] font-semibold text-foreground hover:bg-muted transition-colors disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
        <RotateCcw className="w-3 h-3" /> Clear
      </button>
      <button type="submit" disabled={loading}
        className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-white text-[11px] font-semibold shadow-sm transition-opacity hover:opacity-90 disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1"
        style={{ background: 'var(--linearPrimarySecondary)' }}>
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
        {loading ? 'Predicting…' : label}
      </button>
    </div>
  );
}

/** Loading / error / empty states; children render only once a result exists. */
function ResultFrame({ loading, error, hasResult, children }: {
  loading: boolean; error: string | null; hasResult: boolean; children: React.ReactNode;
}) {
  return (
    <div aria-live="polite">
      {loading ? (
        <div className="rounded-lg border border-border bg-card flex items-center justify-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-[12px]">Calling the model…</span>
        </div>
      ) : error ? (
        <div className="flex items-start gap-2 rounded-lg border border-status-critical-border bg-status-critical-bg p-3 text-[12px] text-status-critical-fg">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-px" />
          <span>{error}</span>
        </div>
      ) : hasResult ? children : (
        <div className="rounded-lg border border-dashed border-border flex items-center justify-center gap-2 py-6 text-muted-foreground">
          <Bot className="w-4 h-4 opacity-60" />
          <span className="text-[12px]">Fill in the project details and run the prediction.</span>
        </div>
      )}
    </div>
  );
}

/** One headline figure in the result strip. */
function Stat({ label, value, sub, tone }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: 'critical' | 'healthy';
}) {
  return (
    <div className="flex flex-col gap-1 min-w-0 rounded-lg border border-border bg-card px-3.5 py-3">
      <span className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className={cx('text-[17px] font-semibold tabular-nums leading-tight',
        tone === 'critical' ? 'text-status-critical-fg' : tone === 'healthy' ? 'text-status-healthy-fg' : 'text-foreground')}>
        {value}
      </span>
      {sub && <span className="text-[11px] leading-snug text-muted-foreground">{sub}</span>}
    </div>
  );
}

/** "Matched in P6: ASEJ6PL_S07_FT_300MW_PPA (pid 16) · via Ordering Schedule snapshot · as of 10-Oct-26" */
function MatchedLine({ project, asOf, children }: { project?: MatchedProject; asOf?: string | null; children?: React.ReactNode }) {
  if (!project?.p6_name && !asOf && !children) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px] text-muted-foreground">
      {project?.p6_name && (
        <span>
          Matched in P6: <span className="font-semibold text-foreground">{project.p6_name}</span>
          {project.pid != null && ` (pid ${project.pid})`}
          {project.match_source && ` · via ${project.match_source}`}
        </span>
      )}
      {asOf && <span>Model as of {fmtDate(asOf)}</span>}
      {children}
    </div>
  );
}

/** Amber notes the model attaches to its own answer - assumptions and guardrails. */
function ModelNotes({ assumptions, guardrail }: { assumptions?: string[]; guardrail?: Guardrail }) {
  const g = guardrailNote(guardrail);
  const notes = [...(g ? [g] : []), ...(assumptions ?? []).filter(Boolean)];
  if (notes.length === 0) return null;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-status-watch-border bg-status-watch-bg p-3 text-[11.5px] leading-relaxed text-status-watch-fg">
      <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
      <ul className="flex flex-col gap-1">
        {notes.map((n, i) => <li key={i}>{n}</li>)}
      </ul>
    </div>
  );
}

/** Collapsed by default: how the model reached its answer, for whoever wants to audit it. */
function ModelDetails({ rows }: { rows: [string, React.ReactNode][] }) {
  const shown = rows.filter(([, v]) => v != null && v !== '' && v !== '—');
  if (shown.length === 0) return null;
  return (
    <details className="group rounded-lg border border-border bg-card">
      <summary className="flex cursor-pointer select-none items-center gap-1.5 px-3.5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-primary/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-lg">
        <ChevronRight className="w-3.5 h-3.5 transition-transform group-open:rotate-90" />
        Model details
      </summary>
      <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 border-t border-border px-3.5 py-3">
        {shown.map(([k, v]) => (
          <div key={k} className="flex flex-col gap-0.5 min-w-0">
            <dt className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">{k}</dt>
            <dd className="text-[12px] leading-relaxed text-foreground/90 break-words">{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((line, i) => (
        <li key={i} className="flex items-start gap-2 text-[12px] leading-relaxed text-foreground/90">
          <div className="mt-[7px] shrink-0 w-1.5 h-1.5 rounded-full bg-primary/50" />
          <span>{line}</span>
        </li>
      ))}
    </ul>
  );
}

/** A paragraph as its sentences, for bullets. Splits only on ". " before a
 *  capital, so decimals (30.4 MWp) and ISO dates stay whole. */
const sentences = (text: string) =>
  text.split(/(?<=[.;!?])\s+(?=[A-Z])/).map(s => s.trim()).filter(Boolean);

/** "FTC risk: ..." rows as bullets, the label in bold. */
function LabelledBullets({ rows, suffix }: { rows: [string, string][]; suffix: string }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map(([k, v]) => (
        <li key={k} className="flex items-start gap-2 text-[12px] leading-relaxed">
          <div className="mt-[7px] shrink-0 w-1.5 h-1.5 rounded-full bg-primary/50" />
          <span><span className="font-semibold text-foreground">{humanKey(k)} {suffix}: </span><span className="text-foreground/90">{v}</span></span>
        </li>
      ))}
    </ul>
  );
}

/** Non-null entries of a {key: text|null} block, labelled. */
const labelled = (rec?: Record<string, string | null>) =>
  Object.entries(rec || {}).filter((e): e is [string, string] => typeof e[1] === 'string' && e[1].trim() !== '');

function ExplainBlock({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3.5">
      <h4 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-primary/80 mb-2">
        {icon}{title}
      </h4>
      {children}
    </div>
  );
}

/** The model's written explanation, section by section; empty sections are skipped. */
function ExplanationView({ ex, driversTitle = 'Key drivers' }: { ex?: Explanation; driversTitle?: string }) {
  if (!ex) return null;
  const risks = labelled(ex.risks_identified);
  const impact = labelled(ex.business_impact);
  const unverified = ex.unverified_numbers ?? [];
  const flags = (ex.consistency_flags ?? []).map(f =>
    typeof f === 'string' ? f : (f as any)?.message ?? (f as any)?.flag ?? JSON.stringify(f));
  return (
    <div className="flex flex-col gap-3">
      {ex.executive_summary && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3.5">
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-primary/80 mb-1.5">Executive summary</h4>
          <p className="text-[12.5px] leading-relaxed text-foreground">{ex.executive_summary}</p>
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {ex.rule_vs_ai_assessment && (
          <ExplainBlock icon={<Scale className="w-3.5 h-3.5" />} title="Rule engine vs AI">
            <BulletList items={sentences(ex.rule_vs_ai_assessment)} />
          </ExplainBlock>
        )}
        {ex.key_drivers && ex.key_drivers.length > 0 && (
          <ExplainBlock icon={<Target className="w-3.5 h-3.5" />} title={driversTitle}>
            <BulletList items={ex.key_drivers} />
          </ExplainBlock>
        )}
        {risks.length > 0 && (
          <ExplainBlock icon={<ShieldAlert className="w-3.5 h-3.5" />} title="Risks identified">
            <LabelledBullets rows={risks} suffix="risk" />
          </ExplainBlock>
        )}
        {impact.length > 0 && (
          <ExplainBlock icon={<AlertTriangle className="w-3.5 h-3.5" />} title="Business impact">
            <LabelledBullets rows={impact} suffix="impact" />
          </ExplainBlock>
        )}
      </div>
      {ex.recommended_actions && ex.recommended_actions.length > 0 && (
        <ExplainBlock icon={<ListChecks className="w-3.5 h-3.5" />} title="Recommended actions">
          <ol className="flex flex-col gap-1.5">
            {ex.recommended_actions.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] leading-relaxed text-foreground/90">
                <span className="shrink-0 w-4 h-4 mt-px rounded-full bg-primary/10 text-primary text-[10px] font-bold flex items-center justify-center">{i + 1}</span>
                <span>{a}</span>
              </li>
            ))}
          </ol>
        </ExplainBlock>
      )}
      {unverified.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-status-watch-border bg-status-watch-bg p-3 text-[11.5px] text-status-watch-fg">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-px" />
          <span>
            The explanation mentions figures the service could not verify against its inputs:{' '}
            <span className="font-semibold">{unverified.map(n => String(n)).join(', ')}</span>. Treat those with caution.
          </span>
        </div>
      )}
      {flags.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-status-watch-border bg-status-watch-bg p-3 text-[11.5px] text-status-watch-fg">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-px" />
          <div>
            The explanation may not match the model's figures:
            <ul className="mt-1 list-disc pl-4">{flags.map((f, i) => <li key={i}>{f}</li>)}</ul>
          </div>
        </div>
      )}
      <p className="flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
        <Info className="w-3 h-3" />
        Explanation {ex.mode ? `mode: ${ex.mode}` : ''}{ex.provider ? ` · ${ex.provider}` : ''}. Model output — verify before acting.
      </p>
    </div>
  );
}

/* ═══ 1. Module Ordering & TC Delivery Forecasting ═══════════════════════ */

type ForecastForm = Omit<OrderTcForecastRequest,
  'capacity_mwp' | 'balance_ordering' | 'inventory' | 'receipt' | 'under_transit'> & {
  capacity_mwp: NumStr; balance_ordering: NumStr; inventory: NumStr; receipt: NumStr; under_transit: NumStr;
};

const EMPTY_FORECAST: ForecastForm = {
  project_id: '', project_name: '', phase: '', vendor_type: 'ALMM', priority: 'STANDARD',
  capacity_mwp: '', balance_ordering: '', inventory: '0', receipt: '0', under_transit: '0',
  lta_date: '', scod_date: '', ftc_date: '',
};

const SAMPLE_FORECAST: ForecastForm = {
  project_id: 'ASEJ6PL_S07', project_name: 'SECI VIII PPA', phase: 'Ph-I', vendor_type: 'China', priority: 'STANDARD',
  capacity_mwp: '408', balance_ordering: '408', inventory: '0', receipt: '0', under_transit: '0',
  lta_date: '2027-01-31', scod_date: '2027-03-02', ftc_date: '2026-12-21',
};

const signedDays = (d: number) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d)} d`;

/** Which causes move the FTC, in days. A cause the model has no data for shows its note, not a zero. */
function RootCauseBlock({ rc }: { rc?: RootCause }) {
  const rows = rc?.breakdown ?? [];
  if (!rc || (rows.length === 0 && !rc.summary)) return null;
  const total = days(rc.predicted_ftc_shift_days);
  const maxAbs = Math.max(1, ...rows.map(b => Math.abs(days(b.days) ?? 0)));
  return (
    <ExplainBlock icon={<Target className="w-3.5 h-3.5" />} title="Why the FTC moves">
      {total != null && (
        <p className="mb-2 text-[12px] text-foreground">
          Predicted FTC shift <span className={cx('font-semibold tabular-nums', total > 0 && 'text-status-critical-fg')}>{signedDays(total)}</span>
        </p>
      )}
      <div className="flex flex-col gap-2">
        {rows.map((b, i) => {
          const d = days(b.days);
          return (
            <div key={i} className="grid grid-cols-[minmax(0,1fr)_72px_52px] items-center gap-2 text-[11.5px]">
              <span className="text-foreground/90 leading-snug">{b.reason}</span>
              {d != null
                ? <MiniMeter pct={(Math.abs(d) / maxAbs) * 100} tone={d > 0 ? 'critical' : 'healthy'} />
                : <span />}
              <span className={cx('text-right tabular-nums', d == null ? 'text-muted-foreground' : 'font-semibold text-foreground')}>
                {d != null ? signedDays(d) : 'no data'}
              </span>
              {d == null && b.note && <span className="col-span-3 -mt-1 text-[10.5px] text-muted-foreground">{b.note}</span>}
            </div>
          );
        })}
      </div>
      {rc.summary && <p className="mt-2.5 text-[11.5px] leading-relaxed text-muted-foreground">{rc.summary}</p>}
    </ExplainBlock>
  );
}

/** Rule-engine lead time against the measured (Ariba) AI lead times. */
function LeadTimeBlock({ lt }: { lt?: LeadTime }) {
  if (!lt || (lt.rule_engine_days == null && lt.ai_p50_days == null && lt.ai_p90_days == null)) return null;
  const cell = (label: string, v: number | undefined, sub: string, tip?: string) => (
    <div className="flex flex-col gap-0.5 rounded-md border border-border bg-muted/20 px-2.5 py-2 min-w-0">
      <span className="flex items-center gap-1 text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}{tip && <InfoTip info={tip} align="left" />}
      </span>
      <span className="text-[15px] font-semibold tabular-nums text-foreground">{v != null ? `${days(v)} d` : '—'}</span>
      <span className="text-[10.5px] text-muted-foreground">{sub}</span>
    </div>
  );
  return (
    <ExplainBlock icon={<Timer className="w-3.5 h-3.5" />} title="Supplier lead time (order → at site)">
      <div className="grid grid-cols-3 gap-2">
        {cell('Rule engine', lt.rule_engine_days, 'Planning rules', lt.rule_engine_basis)}
        {cell('AI typical', lt.ai_p50_days, 'P50, measured', lt.ai_basis)}
        {cell('AI latest', lt.ai_p90_days, 'P90, measured', lt.ai_basis)}
      </div>
      {lt.how_used && <p className="mt-2.5 text-[11px] leading-relaxed text-muted-foreground">{lt.how_used}</p>}
    </ExplainBlock>
  );
}

const TH = 'px-2.5 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground whitespace-nowrap border-b border-border';
const TD = 'px-2.5 py-2 text-[11.5px] align-top border-b border-border';

/** One plan's month-by-month module need: when it must be at site and when it must be ordered. */
function RequirementTable({ title, lead, plan }: { title: string; lead?: string; plan?: RequirementPlan }) {
  const months = plan?.months ?? [];
  if (!plan || months.length === 0) return null;
  const info = [plan.basis, plan.order_by_rule && `Order-by: ${plan.order_by_rule}.`].filter(Boolean).join(' ');
  return (
    <div className="flex flex-col gap-1.5 min-w-0">
      <div className="flex items-center gap-1.5">
        <h5 className="text-[12px] font-semibold text-foreground">{title}</h5>
        {lead && <span className="text-[11px] text-muted-foreground">· {lead}</span>}
        {info && <InfoTip info={info} align="left" />}
      </div>
      <div className="overflow-x-auto custom-scrollbar rounded-md border border-border">
        <table className="min-w-full border-separate border-spacing-0 text-left">
          <thead className="bg-muted/40">
            <tr>
              <th className={TH}>Needed at site</th>
              <th className={cx(TH, 'text-right')}>MWp</th>
              <th className={cx(TH, 'text-right')}>MWac</th>
              <th className={TH}>Order by</th>
              <th className={TH}>Phases</th>
            </tr>
          </thead>
          <tbody>
            {months.map((m, i) => (
              <tr key={`${m.month}-${i}`} className="hover:bg-[var(--surface-sunken)]">
                <td className={TD}>
                  <div className="font-semibold text-foreground">{m.month}</div>
                  {m.need_date && <div className="text-[10.5px] text-muted-foreground">{fmtDate(m.need_date)}</div>}
                </td>
                <td className={cx(TD, 'text-right tabular-nums text-foreground')}>{fmtNum(m.required_at_site_mwp)}</td>
                <td className={cx(TD, 'text-right tabular-nums text-muted-foreground')}>{fmtNum(m.required_at_site_mwac)}</td>
                <td className={TD}>
                  <div className={cx('tabular-nums', m.overdue ? 'text-status-critical-fg font-semibold' : 'text-foreground')}>{fmtDate(m.order_by_date)}</div>
                  {m.overdue && <StatusPill tone="critical" className="mt-0.5">Overdue</StatusPill>}
                </td>
                <td className={cx(TD, 'text-[11px] text-muted-foreground min-w-[140px]')}>{(m.phases ?? []).join(', ') || '—'}</td>
              </tr>
            ))}
            {plan.total_mwp != null && (
              <tr className="bg-muted/30 font-semibold">
                <td className="px-2.5 py-2 text-[11.5px] text-muted-foreground">Σ Total</td>
                <td className="px-2.5 py-2 text-right text-[11.5px] tabular-nums text-foreground">{fmtNum(plan.total_mwp)}</td>
                <td className="px-2.5 py-2 text-right text-[11.5px] tabular-nums text-muted-foreground">
                  {fmtNum(months.reduce((s, m) => s + (m.required_at_site_mwac ?? 0), 0))}
                </td>
                <td colSpan={2} />
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MonthlyRequirementBlock({ mr }: { mr?: MonthlyRequirement }) {
  if (!mr || (!mr.rule_engine?.months?.length && !mr.ai?.months?.length)) return null;
  const re = mr.rule_engine, ai = mr.ai;
  return (
    <ExplainBlock icon={<PackageSearch className="w-3.5 h-3.5" />} title="Monthly module requirement · rule engine vs AI">
      {(mr.balance_ordering_mwp != null || mr.balance_ordering_mwac != null) && (
        <p className="mb-2.5 text-[11.5px] text-muted-foreground">
          Balance to order <span className="font-semibold text-foreground tabular-nums">{fmtNum(mr.balance_ordering_mwp)} MWp</span>
          {mr.balance_ordering_mwac != null && <> / {fmtNum(mr.balance_ordering_mwac)} MWac</>}
          {ai?.timed_by && <> · AI timed by {ai.timed_by}</>}
        </p>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <RequirementTable title="Rule engine" plan={re}
          lead={re?.lead_time_days != null ? `lead ${days(re.lead_time_days)} d` : undefined} />
        <RequirementTable title="AI" plan={ai}
          lead={ai?.lead_time_p90_days != null ? `P90 lead ${days(ai.lead_time_p90_days)} d` : undefined} />
      </div>
      {(mr.label || mr.unit_note) && (
        <p className="mt-2.5 flex items-start gap-1.5 text-[10.5px] leading-relaxed text-muted-foreground">
          <Info className="w-3 h-3 shrink-0 mt-0.5" />
          <span>{[mr.label && mr.label.charAt(0).toUpperCase() + mr.label.slice(1), mr.unit_note].filter(Boolean).join('. ')}.</span>
        </p>
      )}
    </ExplainBlock>
  );
}

function ForecastResult({ r, asked }: { r: OrderTcForecastResponse; asked: Partial<OrderTcForecastRequest> | null }) {
  const confPct = asPct(r.confidence);
  const orderBy = r.order_by_date || r.recommended_order_date;
  const shift = days(r.order_by_shift_vs_rule_days);
  const breach = days(r.deadline_breach_days);
  const tcVsFtc = daysBetween(asked?.ftc_date, r.predicted_tc_date);
  const pr = r.priority;
  const m = r.model;
  const deadlineName = m?.deadline_basis || 'deadline';

  return (
    <div className="flex flex-col gap-3">
      <MatchedLine project={r.project} asOf={m?.as_of}>
        {r.risk_level && <span className="flex items-center gap-1.5">Risk <StatusPill tone={riskTone(r.risk_level)}>{r.risk_level.toUpperCase()}</StatusPill></span>}
        {confPct != null && (
          <span className="flex items-center gap-1.5">Confidence
            <MiniMeter pct={confPct} tone="ai" className="w-14" />
            <span className="font-semibold text-foreground tabular-nums">{confPct}%</span>
            {m?.confidence_basis && <InfoTip info={`Confidence = ${m.confidence_basis}.`} align="left" />}
          </span>
        )}
        {r.order_now === true && <StatusPill tone="critical">ORDER NOW</StatusPill>}
      </MatchedLine>

      {(r.explanation?.order_schedule_status_msg || r.explanation?.short_insight) && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-brand-blue/30 bg-brand-blue/[0.05] px-3 py-2 text-[12px]">
          {r.explanation?.order_schedule_status_msg && (
            <StatusPill tone={/overdue|passed|immediate/i.test(r.explanation.order_schedule_status_msg) ? 'critical'
              : /quota|lta|early/i.test(r.explanation.order_schedule_status_msg) ? 'risk' : 'neutral'}>
              {r.explanation.order_schedule_status_msg}
            </StatusPill>
          )}
          {r.explanation?.short_insight && <span className="text-foreground/90">{r.explanation.short_insight}</span>}
        </div>
      )}

      <ModelNotes assumptions={[...(r.notes ?? []), ...(m?.assumptions ?? [])]} guardrail={pr?.guardrail} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Order by (AI)"
          value={!orderBy && r.monthly_requirement?.balance_ordering_mwp === 0 ? 'Nothing to order' : fmtDate(orderBy)}
          sub={r.rule_engine?.order_by_date
            ? <>Rule engine {fmtDate(r.rule_engine.order_by_date)}{shift != null && shift !== 0 && ` · AI ${plural(Math.abs(shift), 'day')} ${shift < 0 ? 'earlier' : 'later'}`}</>
            : r.order_now === false ? 'Not yet due' : undefined} />
        <Stat label="Predicted TC (modules at site)" value={fmtDate(r.predicted_tc_date)}
          sub={<>
            {r.predicted_tc_date_p90 && <>Latest (P90) {fmtDate(r.predicted_tc_date_p90)}</>}
            {r.rule_engine?.tc_date && <>{r.predicted_tc_date_p90 ? ' · ' : ''}Rule {fmtDate(r.rule_engine.tc_date)}</>}
            {tcVsFtc != null && tcVsFtc > 0 && <span className="block text-status-critical-fg">{plural(tcVsFtc, 'day')} after the FTC entered</span>}
          </>} />
        <Stat label="Projected FTC (first charging)" value={fmtDate(r.projected_ftc_date)}
          tone={breach != null ? (breach > 0 ? 'critical' : 'healthy') : undefined}
          sub={breach != null
            ? <>
                {breach > 0 ? `${plural(breach, 'day')} after ${deadlineName}` : breach < 0 ? `${plural(-breach, 'day')} ahead of ${deadlineName}` : `On ${deadlineName}`}
                {m?.deadline && ` (${fmtDate(m.deadline)})`}
              </>
            : undefined} />
        <Stat label="Priority (AI)"
          value={pr?.ai ? <StatusPill tone={priorityTone(pr.ai)}>{pr.ai.toUpperCase()}</StatusPill> : '—'}
          sub={<>
            {pr?.current && <>Current {pr.current.toUpperCase()}</>}
            {pr?.criticality_score != null && <>{pr?.current ? ' · ' : ''}Criticality {fmtNum(pr.criticality_score)}/100</>}
          </>} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <RootCauseBlock rc={r.root_cause} />
        <LeadTimeBlock lt={r.lead_time} />
      </div>

      <MonthlyRequirementBlock mr={r.monthly_requirement} />

      <ExplanationView ex={r.explanation} />

      <ModelDetails rows={[
        ['Site-readiness shift', m?.site_shift_days != null ? signedDays(days(m.site_shift_days)!) : null],
        ['Transmission shift', m?.transmission_shift_days != null ? signedDays(days(m.transmission_shift_days)!) : null],
        ['Lead time P50 / P90', m?.lead_time_p50_days != null || m?.lead_time_p90_days != null
          ? `${days(m?.lead_time_p50_days) ?? '—'} d / ${days(m?.lead_time_p90_days) ?? '—'} d` : null],
        ['Deadline', m?.deadline ? `${fmtDate(m.deadline)}${m.deadline_basis ? ` (${m.deadline_basis})` : ''}` : null],
        ['Feature coverage', m?.feature_coverage != null ? `${asPct(m.feature_coverage)}% of model inputs available` : null],
        ['Confidence basis', m?.confidence_basis],
        ['Where the labels come from', m?.label_provenance],
      ]} />
    </div>
  );
}

function OrderTcForecastPanel() {
  const [form, setForm] = useState<ForecastForm>(EMPTY_FORECAST);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OrderTcForecastResponse | null>(null);
  // The inputs the shown result was computed from, so editing the form does not relabel it.
  const [asked, setAsked] = useState<OrderTcForecastRequest | null>(null);

  const set = <K extends keyof ForecastForm>(k: K) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm(f => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: OrderTcForecastRequest = {
      ...form,
      project_id: form.project_id.trim(),
      project_name: form.project_name.trim(),
      phase: form.phase.trim(),
      capacity_mwp: Number(form.capacity_mwp),
      balance_ordering: Number(form.balance_ordering),
      inventory: Number(form.inventory),
      receipt: Number(form.receipt),
      under_transit: Number(form.under_transit),
    };
    setLoading(true); setError(null); setResult(null);
    try {
      setResult(await postJSON<OrderTcForecastResponse>('/order-tc-forecast?explain=true', body));
      setAsked(body);
    } catch (err: any) {
      setError(err?.message || 'Could not reach the prediction service.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PanelShell
      icon={<CalendarClock className="w-3.5 h-3.5" />}
      title="Module Ordering & TC Delivery Forecasting"
      sub="AI order-by date, predicted module arrival (TC) and first-charging date for one project phase."
      info="Sends the inputs to the order-tc-forecast model. Dates, confidence, risk and priority are model predictions and are shown next to the rule engine's dates for comparison — they are not plan or SAP figures."
    >
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <Field label="Project ID"><input required className={INPUT} value={form.project_id} onChange={set('project_id')} placeholder="ARE55L_S03" /></Field>
          <Field label="Project name"><input required className={INPUT} value={form.project_name} onChange={set('project_name')} placeholder="MSEDCL PPA Ph-3" /></Field>
          <Field label="Phase"><input required className={INPUT} value={form.phase} onChange={set('phase')} placeholder="PH-1" /></Field>
          <SelectField label="Vendor type" value={form.vendor_type} options={VENDOR_TYPES} onChange={set('vendor_type')} />
          <SelectField label="Current priority" value={form.priority} options={PRIORITIES} onChange={set('priority')} />
          <MwField label="Capacity" value={form.capacity_mwp} onChange={set('capacity_mwp')} placeholder="203" />
          <MwField label="Balance to order" value={form.balance_ordering} onChange={set('balance_ordering')} placeholder="203" />
          <MwField label="Inventory" value={form.inventory} onChange={set('inventory')} />
          <MwField label="Received" value={form.receipt} onChange={set('receipt')} />
          <MwField label="In transit" value={form.under_transit} onChange={set('under_transit')} />
          <DateField label="LTA date" value={form.lta_date} onChange={set('lta_date')} />
          <DateField label="SCOD date" value={form.scod_date} onChange={set('scod_date')} />
          <DateField label="FTC date" value={form.ftc_date} onChange={set('ftc_date')} />
        </div>
        <FormActions loading={loading} label="Forecast"
          onSample={() => setForm(SAMPLE_FORECAST)}
          onReset={() => { setForm(EMPTY_FORECAST); setResult(null); setError(null); setAsked(null); }} />
      </form>

      <ResultFrame loading={loading} error={error} hasResult={!!result}>
        {result && <ForecastResult r={result} asked={asked} />}
      </ResultFrame>
    </PanelShell>
  );
}

/* ═══ 2. Priority Prediction ═════════════════════════════════════════════ */

type PriorityForm = Omit<PriorityPredictRequest,
  'capacity_mwp' | 'balance_ordering' | 'inventory' | 'receipt' | 'under_transit'> & {
  capacity_mwp: NumStr; balance_ordering: NumStr; inventory: NumStr; receipt: NumStr; under_transit: NumStr;
};

const EMPTY_PRIORITY: PriorityForm = {
  project_id: '', project_name: '', phase: '', category: '', capacity_mwp: '', balance_ordering: '',
  inventory: '0', receipt: '0', under_transit: '0', lta_date: '', scod_date: '', ftc_date: '',
  ftc_risk_flag: false, current_priority: 'STANDARD',
};

const SAMPLE_PRIORITY: PriorityForm = {
  project_id: 'ASEJ6PL_S07', project_name: 'SECI VIII PPA', phase: 'Ph-I', category: 'PPA',
  capacity_mwp: '408', balance_ordering: '408', inventory: '0', receipt: '0', under_transit: '0',
  lta_date: '2027-01-31', scod_date: '2027-03-02', ftc_date: '2026-12-21',
  ftc_risk_flag: false, current_priority: 'STANDARD',
};

function PriorityResult({ r, asked }: { r: PriorityPredictResponse; asked: Partial<PriorityPredictRequest> | null }) {
  const tone = priorityTone(r.priority_class);
  // One decimal: 0.004 is 0.4%, not 0%.
  const probs = Object.entries(r.class_probabilities || {})
    .filter((e): e is [string, number] => typeof e[1] === 'number' && Number.isFinite(e[1]))
    .map(([k, v]) => [k, v <= 1 ? v * 100 : v] as const)
    .sort((a, b) => b[1] - a[1]);
  const ftcSlip = daysBetween(r.ftc_date_used, r.realistic_ftc_date);
  const m = r.model;
  const vsDeadline = daysBetween(m?.deadline, r.realistic_ftc_date);
  const deadlineName = m?.deadline_basis || 'deadline';
  const differs = asked?.current_priority && r.priority_class
    && asked.current_priority.toUpperCase() !== r.priority_class.toUpperCase();
  // Template explanations repeat the reasons as key drivers; LLM ones rephrase and add to them.
  const reasonSet = new Set((r.reasons ?? []).map(x => x.trim().toLowerCase()));
  const driversRepeat = (r.explanation?.key_drivers ?? []).every(d => reasonSet.has(d.trim().toLowerCase()));

  return (
    <div className="flex flex-col gap-3">
      <MatchedLine project={r.project} asOf={m?.as_of} />

      <ModelNotes assumptions={[...(r.notes ?? []), ...(m?.assumptions ?? [])]} guardrail={r.guardrail} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="AI priority"
          value={r.priority_class ? <StatusPill tone={tone}>{r.priority_class.toUpperCase()}</StatusPill> : '—'}
          sub={asked?.current_priority ? <>Current {asked.current_priority}{differs && <span className="text-status-risk-fg"> · changes</span>}</> : undefined} />
        {/* The score is an URGENCY score - 100 x (P(P1) + 0.5 x P(P2)) - so a
            STANDARD project correctly sits near 0 (0.8/100). Shown bare, that
            reads as "the model is unsure". For STANDARD the card shows what the
            model actually knows: how confident it is in STANDARD. */}
        {(r.priority_class || '').toUpperCase() === 'STANDARD' && r.class_probabilities?.STANDARD != null ? (
          <Stat label="Model confidence"
            value={<span className="flex items-center gap-1.5">{fmtNum(r.class_probabilities.STANDARD * 100)}%
              <InfoTip align="left" info={`How sure the model is that this project is STANDARD (class probability). The urgency score ${m?.score_basis ? `(${m.score_basis}) ` : ''}is ${fmtNum(r.priority_score)}/100 - low, as expected for a STANDARD project.`} />
            </span>}
            sub={<>
              <MiniMeter pct={r.class_probabilities.STANDARD * 100} tone="ai" className="mt-1" />
              <span className="mt-1 block">Urgency score {fmtNum(r.priority_score)} / 100 (low)</span>
            </>} />
        ) : <Stat label="Priority score"
          value={r.priority_score != null
            ? <span className="flex items-center gap-1.5">{fmtNum(r.priority_score)}<span className="text-[12px] font-normal text-muted-foreground">/ 100</span>
                {m?.score_basis && <InfoTip info={`Score = ${m.score_basis}.`} align="left" />}
              </span>
            : '—'}
          sub={r.priority_score != null ? <MiniMeter pct={r.priority_score} tone={tone === 'neutral' ? 'ai' : tone} className="mt-1" /> : undefined} />}
        <Stat label="Rule engine priority"
          value={r.rule_engine?.priority_class ? <StatusPill tone={priorityTone(r.rule_engine.priority_class)}>{r.rule_engine.priority_class.toUpperCase()}</StatusPill> : '—'}
          sub={r.rule_engine?.basis} />
        <Stat label="Realistic FTC" value={fmtDate(r.realistic_ftc_date)}
          tone={vsDeadline != null ? (vsDeadline > 0 ? 'critical' : 'healthy') : ftcSlip != null && ftcSlip > 0 ? 'critical' : undefined}
          sub={<>
            {vsDeadline != null && (
              <span className="block">
                {vsDeadline > 0 ? `${plural(vsDeadline, 'day')} after ${deadlineName}` : vsDeadline < 0 ? `${plural(-vsDeadline, 'day')} ahead of ${deadlineName}` : `On ${deadlineName}`}
                {` (${fmtDate(m?.deadline)})`}
              </span>
            )}
            {r.ftc_date_used && <>P6 FTC used {fmtDate(r.ftc_date_used)}{ftcSlip != null && ftcSlip !== 0 && ` · ${plural(Math.abs(ftcSlip), 'day')} ${ftcSlip > 0 ? 'later' : 'earlier'}`}</>}
          </>} />
      </div>

      {(probs.length > 0 || (r.reasons && r.reasons.length > 0)) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {r.reasons && r.reasons.length > 0 && (
            <ExplainBlock icon={<Target className="w-3.5 h-3.5" />} title="Reasons">
              <div className="flex flex-wrap gap-1.5">
                {r.reasons.map((x, i) => (
                  <span key={i} className="inline-flex items-center rounded-md border border-border bg-muted/40 px-2 py-0.5 text-[11.5px] text-foreground">{x}</span>
                ))}
              </div>
            </ExplainBlock>
          )}
          {probs.length > 0 && (
            <ExplainBlock icon={<Scale className="w-3.5 h-3.5" />} title="Class probabilities">
              <div className="flex flex-col gap-2">
                {probs.map(([k, pct]) => (
                  <div key={k} className="grid grid-cols-[72px_minmax(0,1fr)_48px] items-center gap-2 text-[12px]">
                    <span className="font-semibold text-foreground">{k}</span>
                    <MiniMeter pct={pct} tone={priorityTone(k) === 'neutral' ? 'ai' : priorityTone(k)} />
                    <span className="text-right tabular-nums text-muted-foreground">{fmtNum(pct)}%</span>
                  </div>
                ))}
              </div>
            </ExplainBlock>
          )}
        </div>
      )}

      {/* Key drivers are dropped only when they just repeat the reasons above. */}
      <ExplanationView ex={r.explanation && driversRepeat ? { ...r.explanation, key_drivers: undefined } : r.explanation} />

      <ModelDetails rows={[
        ['Site-readiness shift', m?.site_shift_days != null ? signedDays(days(m.site_shift_days)!) : null],
        ['Supply shortfall', m?.supply_shortfall_days != null ? `${days(m.supply_shortfall_days)} d` : null],
        ['Deadline', m?.deadline ? `${fmtDate(m.deadline)}${m.deadline_basis ? ` (${m.deadline_basis})` : ''}` : null],
        ['Contract type', m?.contract_type],
        ['Score formula', m?.score_basis],
        ['Where the labels come from', m?.label_provenance],
      ]} />
    </div>
  );
}

function PriorityPredictionPanel() {
  const [form, setForm] = useState<PriorityForm>(EMPTY_PRIORITY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PriorityPredictResponse | null>(null);
  const [asked, setAsked] = useState<PriorityPredictRequest | null>(null);

  const set = <K extends keyof PriorityForm>(k: K) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm(f => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: PriorityPredictRequest = {
      ...form,
      project_id: form.project_id.trim(),
      project_name: form.project_name.trim(),
      phase: form.phase.trim(),
      category: form.category.trim(),
      capacity_mwp: Number(form.capacity_mwp),
      balance_ordering: Number(form.balance_ordering),
      inventory: Number(form.inventory),
      receipt: Number(form.receipt),
      under_transit: Number(form.under_transit),
    };
    setLoading(true); setError(null); setResult(null);
    try {
      setResult(await postJSON<PriorityPredictResponse>('/priority-predict?explain=true', body));
      setAsked(body);
    } catch (err: any) {
      setError(err?.message || 'Could not reach the prediction service.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PanelShell
      icon={<ListOrdered className="w-3.5 h-3.5" />}
      title="Priority Prediction"
      sub="AI ordering priority for a project, compared with the rule engine and the current priority."
      info="Sends the inputs to the priority-predict model. The class, score (0–100), probabilities and realistic FTC are model output — a recommendation, not the priority currently set in the plan."
    >
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <Field label="Project ID"><input required className={INPUT} value={form.project_id} onChange={set('project_id')} placeholder="ARE55L_S03" /></Field>
          <Field label="Project name"><input required className={INPUT} value={form.project_name} onChange={set('project_name')} placeholder="MSEDCL PPA Ph-3" /></Field>
          <Field label="Phase"><input required className={INPUT} value={form.phase} onChange={set('phase')} placeholder="PH-1" /></Field>
          <Field label="Category">
            <input required className={INPUT} value={form.category} onChange={set('category')} placeholder="PPA" list="ai-priority-categories" />
            <datalist id="ai-priority-categories">
              <option value="PPA" /><option value="Merchant" />
            </datalist>
          </Field>
          <SelectField label="Current priority" value={form.current_priority} options={PRIORITIES} onChange={set('current_priority')} />
          <MwField label="Capacity" value={form.capacity_mwp} onChange={set('capacity_mwp')} placeholder="675" />
          <MwField label="Balance to order" value={form.balance_ordering} onChange={set('balance_ordering')} placeholder="675" />
          <MwField label="Inventory" value={form.inventory} onChange={set('inventory')} />
          <MwField label="Received" value={form.receipt} onChange={set('receipt')} />
          <MwField label="In transit" value={form.under_transit} onChange={set('under_transit')} />
          <DateField label="LTA date" value={form.lta_date} onChange={set('lta_date')} />
          <DateField label="SCOD date" value={form.scod_date} onChange={set('scod_date')} />
          <DateField label="FTC date" value={form.ftc_date} onChange={set('ftc_date')} />
          <Field label="FTC at risk">
            <label className="flex items-center gap-2 h-[30px] px-2.5 rounded-lg border border-border bg-card cursor-pointer text-[12px] text-foreground">
              <input type="checkbox" className="accent-[var(--brand-purple)]" checked={form.ftc_risk_flag}
                onChange={e => setForm(f => ({ ...f, ftc_risk_flag: e.target.checked }))} />
              {form.ftc_risk_flag ? 'Yes' : 'No'}
            </label>
          </Field>
        </div>
        <FormActions loading={loading} label="Predict"
          onSample={() => setForm(SAMPLE_PRIORITY)}
          onReset={() => { setForm(EMPTY_PRIORITY); setResult(null); setError(null); setAsked(null); }} />
      </form>

      <ResultFrame loading={loading} error={error} hasResult={!!result}>
        {result && <PriorityResult r={result} asked={asked} />}
      </ResultFrame>
    </PanelShell>
  );
}

/* ═══ Dashboard integration: batch-scored AI results per table row ═══════ */

/** One field the governance review changed in an AI answer. */
export interface ReviewChange { field: string; before: unknown; after: unknown }

/** One dashboard row's AI results, as served by GET /module-deliveries/ai-results. */
export interface RowAI {
  p6_name?: string | null;
  ai_priority?: PriorityPredictResponse | null;
  ai_monthly_order_tc_forecast?: OrderTcForecastResponse | null;
  /** A governance review checked the two answers against the planning flags:
   *  VALIDATED (left as is) or CORRECTED (fields changed, listed below). */
  ai_review_status?: string | null;
  ai_review_reason?: string | null;
  ai_review_changes?: ReviewChange[];
}

export const isScored = (x?: BatchEnvelope | null) => x?.status === 'scored';

/** ISO date -> '13-May-27', the table's own date style. Null stays null. */
export const aiDate = (iso?: string | null) => (iso ? fmtDate(iso) : null);

/** The table and the AI name an unphased project differently ('Main' vs
 *  'Single phase'), and the table appends capacity / block range to a phase
 *  label ('Ph-II (125MW) BL-01 to 14'). Both reduce to the bare phase. */
const barePhase = (label?: string | null) =>
  (label || '').replace(/\s*\(.*$/, '').replace(/\s+BL-.*$/i, '').trim().toLowerCase();

export function aiPhaseFor<T extends { phase: string }>(phases: T[] | undefined, tableLabel?: string | null): T | undefined {
  const list = phases ?? [];
  if (list.length === 0) return undefined;
  if (list.length === 1) return list[0];
  const want = barePhase(tableLabel);
  return list.find(ph => barePhase(ph.phase) === want);
}

/** 'Single phase' says nothing on a one-phase project; other labels stay. */
export const phaseName = (label?: string | null) => (!label || /^single phase$/i.test(label) ? '' : label);

function useEscape(onClose: () => void) {
  React.useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
}

function AIModalShell({ title, subtitle, badge, onClose, children }: {
  title: string; subtitle?: React.ReactNode; badge: string; onClose: () => void; children: React.ReactNode;
}) {
  useEscape(onClose);
  // Portalled: the dashboard sits inside animated (transformed) containers,
  // which would otherwise pin a `fixed` overlay to them instead of the window.
  return createPortal(
    // Above the month-cell popup (z 9999) that the AI button is clicked from.
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label={title}
        className="relative flex w-full max-w-5xl max-h-[88vh] flex-col rounded-xl border border-border bg-card shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-full border border-brand-blue/30 bg-brand-blue/10 px-2 py-0.5 text-[10px] font-semibold text-brand-blue">
                <Sparkles className="h-3 w-3" />{badge}
              </span>
            </div>
            <h3 className="truncate text-base font-semibold text-foreground">{title}</h3>
            {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close"
            className="rounded-lg p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="overflow-y-auto custom-scrollbar px-5 py-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

function NotScored({ reason, notes }: { reason?: string; notes?: string[] }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-[12px] text-foreground/90">
        <Info className="mt-px h-4 w-4 shrink-0 text-muted-foreground" />
        <span>The AI did not score this project{reason ? <>: <b>{reason}</b></> : '.'}</span>
      </div>
      <ModelNotes assumptions={notes} />
    </div>
  );
}

const PH_TH = 'px-2.5 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground whitespace-nowrap border-b border-border';
const PH_TD = 'px-2.5 py-2 text-[11.5px] border-b border-border whitespace-nowrap tabular-nums';

/** Every pending phase's AI dates. The detail below is for one phase (r.phase). */
function ForecastPhaseTable({ phases, focus }: { phases?: ForecastPhase[]; focus?: string }) {
  if (!phases || phases.length < 2) return null;
  return (
    <ExplainBlock icon={<CalendarClock className="w-3.5 h-3.5" />} title="AI dates by phase">
      <div className="overflow-x-auto custom-scrollbar rounded-md border border-border">
        <table className="min-w-full border-separate border-spacing-0 text-left">
          <thead className="bg-muted/40">
            <tr>
              {['Phase', 'P6 FTC', 'AI order by', 'Rule order by', 'AI TC', 'TC latest (P90)', 'Projected FTC', 'vs deadline', 'Risk'].map(h =>
                <th key={h} className={PH_TH}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {phases.map(ph => {
              const b = days(ph.deadline_breach_days);
              return (
                <tr key={ph.phase} className={cx(ph.phase === focus && 'bg-brand-blue/[0.05]')}>
                  <td className={cx(PH_TD, 'font-semibold text-foreground')}>{phaseName(ph.phase) || 'Project'}</td>
                  <td className={cx(PH_TD, 'text-muted-foreground')}>{fmtDate(ph.p6_ftc_date)}</td>
                  <td className={cx(PH_TD, 'font-semibold text-brand-blue')}>{ph.order_by_date ? fmtDate(ph.order_by_date) : 'Nothing to order'}</td>
                  <td className={cx(PH_TD, 'text-muted-foreground')}>{fmtDate(ph.rule_engine?.order_by_date)}</td>
                  <td className={cx(PH_TD, 'font-semibold text-brand-blue')}>{fmtDate(ph.predicted_tc_date)}</td>
                  <td className={cx(PH_TD, 'text-muted-foreground')}>{fmtDate(ph.predicted_tc_date_p90)}</td>
                  <td className={PH_TD}>{fmtDate(ph.projected_ftc_date)}</td>
                  <td className={cx(PH_TD, b != null && b > 0 ? 'text-status-critical-fg font-semibold' : 'text-muted-foreground')}>
                    {b == null ? '—' : b > 0 ? `${b} d late` : b < 0 ? `${-b} d early` : 'on time'}
                  </td>
                  <td className={PH_TD}>{ph.risk_level ? <StatusPill tone={riskTone(ph.risk_level)}>{ph.risk_level.toUpperCase()}</StatusPill> : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[10.5px] text-muted-foreground">
        The detail below is for {phaseName(focus) || 'the first pending phase'}. AI dates are model predictions, not plan or SAP figures.
      </p>
    </ExplainBlock>
  );
}

function PriorityPhaseTable({ phases, focus }: { phases?: PriorityPhase[]; focus?: string }) {
  if (!phases || phases.length < 2) return null;
  return (
    <ExplainBlock icon={<ListOrdered className="w-3.5 h-3.5" />} title="AI priority by phase">
      <div className="overflow-x-auto custom-scrollbar rounded-md border border-border">
        <table className="min-w-full border-separate border-spacing-0 text-left">
          <thead className="bg-muted/40">
            <tr>{['Phase', 'P6 FTC', 'AI priority', 'Score', 'Realistic FTC', 'Rule engine'].map(h => <th key={h} className={PH_TH}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {phases.map(ph => (
              <tr key={ph.phase} className={cx(ph.phase === focus && 'bg-brand-blue/[0.05]')}>
                <td className={cx(PH_TD, 'font-semibold text-foreground')}>{phaseName(ph.phase) || 'Project'}</td>
                <td className={cx(PH_TD, 'text-muted-foreground')}>{fmtDate(ph.p6_ftc_date)}</td>
                <td className={PH_TD}>{ph.priority_class ? <StatusPill tone={priorityTone(ph.priority_class)}>{ph.priority_class.toUpperCase()}</StatusPill> : '—'}</td>
                <td className={PH_TD}>{fmtNum(ph.priority_score)}</td>
                <td className={PH_TD}>{fmtDate(ph.realistic_ftc_date)}</td>
                <td className={cx(PH_TD, 'text-muted-foreground')}>{ph.rule_engine_priority || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ExplainBlock>
  );
}

type RowLike = { project_name?: string; p6_name?: string; priority?: string; spv?: string };

/** Use case 1 in full for one dashboard row (opened from the Remarks AI button). */
export function AIForecastModal({ row, ai, asOf, onClose }: {
  row: RowLike; ai?: OrderTcForecastResponse | null; asOf?: string; onClose: () => void;
}) {
  const focus = aiPhaseFor(ai?.phases, ai?.phase);
  return (
    <AIModalShell badge="AI · Module Ordering & TC Delivery Forecast" onClose={onClose}
      title={row.project_name || row.p6_name || 'Project'}
      subtitle={<>{row.p6_name}{ai?.phase && phaseName(ai.phase) && <> · detail for {ai.phase}</>}{asOf && <> · scored {fmtDate(asOf)}</>}</>}>
      {!ai ? <NotScored reason="no AI result for this row" />
        : !isScored(ai) ? <NotScored reason={ai.reason} notes={ai.notes} />
        : (
          <div className="flex flex-col gap-3">
            <ForecastPhaseTable phases={ai.phases} focus={focus?.phase ?? ai.phase} />
            <ForecastResult r={ai} asked={{ ftc_date: focus?.p6_ftc_date ?? undefined }} />
          </div>
        )}
    </AIModalShell>
  );
}

/** Use case 2 in full for one dashboard row (opened from the Priority (AI) cell). */
export function AIPriorityModal({ row, ai, asOf, onClose }: {
  row: RowLike; ai?: PriorityPredictResponse | null; asOf?: string; onClose: () => void;
}) {
  return (
    <AIModalShell badge="AI · Priority Prediction" onClose={onClose}
      title={row.project_name || row.p6_name || 'Project'}
      subtitle={<>{row.p6_name}{ai?.phase && phaseName(ai.phase) && <> · detail for {ai.phase}</>}{asOf && <> · scored {fmtDate(asOf)}</>}</>}>
      {!ai ? <NotScored reason="no AI result for this row" />
        : !isScored(ai) ? <NotScored reason={ai.reason} notes={ai.notes} />
        : (
          <div className="flex flex-col gap-3">
            <PriorityPhaseTable phases={ai.phases} focus={ai.phase} />
            <PriorityResult r={ai} asked={{ current_priority: (row.priority || 'STANDARD').toUpperCase() }} />
          </div>
        )}
    </AIModalShell>
  );
}

export { priorityTone as aiPriorityTone };

export default function AIPredictionPanels() {
  return (
    <div className="flex flex-col gap-4">
      <OrderTcForecastPanel />
      <PriorityPredictionPanel />
    </div>
  );
}
