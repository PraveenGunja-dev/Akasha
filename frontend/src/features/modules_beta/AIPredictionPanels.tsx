/* BETA: two model-backed what-if forms shown under the AI Procurement Strategy.

   1. Module Ordering & TC Delivery Forecasting -> POST /api/ai/v1/order-tc-forecast?explain=true
   2. Priority Prediction                        -> POST /api/ai/v1/priority-predict?explain=true

   The AI service is separate from the Akasha backend (it runs on :8000). In dev
   the Vite proxy forwards /akasha/ai-api/* to it (see vite.config.ts), which
   keeps the browser on one origin; elsewhere set VITE_AI_API_BASE to the
   service's /api/ai/v1 address.

   Everything returned is a model prediction, not a plan or SAP figure, and is
   labelled that way. Any part of a response that is missing is simply not
   drawn - nothing is filled in on the client. */
import React, { useState } from 'react';
import {
  Bot, Sparkles, Loader2, AlertTriangle, CalendarClock, ListOrdered, RotateCcw,
  ShieldAlert, Target, ListChecks, Scale, Info,
} from 'lucide-react';
import { InfoTip, MiniMeter, StatusPill, cx } from '../../components/ui/primitives';
import type { Tone } from '../../components/ui/primitives';

const AI_API_BASE: string = import.meta.env.VITE_AI_API_BASE || '/akasha/ai-api';

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
  text?: string;
  unverified_numbers?: unknown[];
}

interface MatchedProject { p6_name?: string; pid?: number | string }

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

interface OrderTcForecastResponse {
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
  priority?: { current?: string; ai?: string; criticality_score?: number };
  project?: MatchedProject;
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

interface PriorityPredictResponse {
  priority_class?: string;
  priority_score?: number;              // 0–100
  reasons?: string[];
  rule_engine?: { priority_class?: string; basis?: string };
  class_probabilities?: Record<string, number>;
  ftc_date_used?: string;
  realistic_ftc_date?: string;
  project?: MatchedProject;
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

/** "Matched in P6: ARE55L_S03_HSAT_500MW_MERCHANT (pid 4337)" */
function MatchedLine({ project, children }: { project?: MatchedProject; children?: React.ReactNode }) {
  if (!project?.p6_name && !children) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px] text-muted-foreground">
      {project?.p6_name && (
        <span>Matched in P6: <span className="font-semibold text-foreground">{project.p6_name}</span>{project.pid != null && ` (pid ${project.pid})`}</span>
      )}
      {children}
    </div>
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
            <p className="text-[12px] leading-relaxed text-foreground/90">{ex.rule_vs_ai_assessment}</p>
          </ExplainBlock>
        )}
        {ex.key_drivers && ex.key_drivers.length > 0 && (
          <ExplainBlock icon={<Target className="w-3.5 h-3.5" />} title={driversTitle}>
            <BulletList items={ex.key_drivers} />
          </ExplainBlock>
        )}
        {risks.length > 0 && (
          <ExplainBlock icon={<ShieldAlert className="w-3.5 h-3.5" />} title="Risks identified">
            <dl className="flex flex-col gap-1.5">
              {risks.map(([k, v]) => (
                <div key={k} className="text-[12px] leading-relaxed">
                  <dt className="inline font-semibold text-foreground">{humanKey(k)} risk: </dt>
                  <dd className="inline text-foreground/90">{v}</dd>
                </div>
              ))}
            </dl>
          </ExplainBlock>
        )}
        {impact.length > 0 && (
          <ExplainBlock icon={<AlertTriangle className="w-3.5 h-3.5" />} title="Business impact">
            <dl className="flex flex-col gap-1.5">
              {impact.map(([k, v]) => (
                <div key={k} className="text-[12px] leading-relaxed">
                  <dt className="inline font-semibold text-foreground">{humanKey(k)} impact: </dt>
                  <dd className="inline text-foreground/90">{v}</dd>
                </div>
              ))}
            </dl>
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
  project_id: 'ARE55L_S03', project_name: 'MSEDCL PPA Ph-3', phase: 'PH-1', vendor_type: 'ALMM', priority: 'STANDARD',
  capacity_mwp: '203', balance_ordering: '203', inventory: '0', receipt: '0', under_transit: '0',
  lta_date: '2028-06-30', scod_date: '2027-04-29', ftc_date: '2027-05-19',
};

function ForecastResult({ r, asked }: { r: OrderTcForecastResponse; asked: OrderTcForecastRequest | null }) {
  const confPct = asPct(r.confidence);
  const orderBy = r.order_by_date || r.recommended_order_date;
  // The service sends day counts as floats (71.0); whole days are what the UI says.
  const shift = r.order_by_shift_vs_rule_days == null ? undefined : Math.round(r.order_by_shift_vs_rule_days);
  const breach = r.deadline_breach_days == null ? undefined : Math.round(r.deadline_breach_days);
  const tcVsFtc = daysBetween(asked?.ftc_date, r.predicted_tc_date);
  const pr = r.priority;

  return (
    <div className="flex flex-col gap-3">
      <MatchedLine project={r.project}>
        {r.risk_level && <span className="flex items-center gap-1.5">Risk <StatusPill tone={riskTone(r.risk_level)}>{r.risk_level.toUpperCase()}</StatusPill></span>}
        {confPct != null && (
          <span className="flex items-center gap-1.5">Confidence
            <MiniMeter pct={confPct} tone="ai" className="w-14" />
            <span className="font-semibold text-foreground tabular-nums">{confPct}%</span>
          </span>
        )}
        {r.order_now === true && <StatusPill tone="critical">ORDER NOW</StatusPill>}
      </MatchedLine>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Order by (AI)" value={fmtDate(orderBy)}
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
            ? breach > 0 ? `${plural(breach, 'day')} after the deadline` : breach < 0 ? `${plural(-breach, 'day')} ahead of the deadline` : 'On the deadline'
            : undefined} />
        <Stat label="Priority (AI)"
          value={pr?.ai ? <StatusPill tone={priorityTone(pr.ai)}>{pr.ai.toUpperCase()}</StatusPill> : '—'}
          sub={<>
            {pr?.current && <>Current {pr.current}</>}
            {pr?.criticality_score != null && <>{pr?.current ? ' · ' : ''}Criticality {Math.round(pr.criticality_score * 10) / 10}/100</>}
          </>} />
      </div>

      <ExplanationView ex={r.explanation} />
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
  project_id: 'ARE55L_S03', project_name: 'MSEDCL PPA Ph-3', phase: 'PH-1', category: 'PPA',
  capacity_mwp: '675', balance_ordering: '675', inventory: '0', receipt: '0', under_transit: '0',
  lta_date: '2028-06-30', scod_date: '2027-04-29', ftc_date: '2027-05-19',
  ftc_risk_flag: true, current_priority: 'STANDARD',
};

function PriorityResult({ r, asked }: { r: PriorityPredictResponse; asked: PriorityPredictRequest | null }) {
  const tone = priorityTone(r.priority_class);
  const probs = Object.entries(r.class_probabilities || {})
    .map(([k, v]) => [k, asPct(v)] as const)
    .filter((e): e is readonly [string, number] => e[1] != null)
    .sort((a, b) => b[1] - a[1]);
  const ftcSlip = daysBetween(r.ftc_date_used, r.realistic_ftc_date);
  const differs = asked?.current_priority && r.priority_class
    && asked.current_priority.toUpperCase() !== r.priority_class.toUpperCase();

  return (
    <div className="flex flex-col gap-3">
      <MatchedLine project={r.project} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="AI priority"
          value={r.priority_class ? <StatusPill tone={tone}>{r.priority_class.toUpperCase()}</StatusPill> : '—'}
          sub={asked?.current_priority ? <>Current {asked.current_priority}{differs && <span className="text-status-risk-fg"> · changes</span>}</> : undefined} />
        <Stat label="Priority score"
          value={r.priority_score != null ? <>{Math.round(r.priority_score)}<span className="text-[12px] font-normal text-muted-foreground"> / 100</span></> : '—'}
          sub={r.priority_score != null ? <MiniMeter pct={r.priority_score} tone={tone === 'neutral' ? 'ai' : tone} className="mt-1" /> : undefined} />
        <Stat label="Rule engine priority"
          value={r.rule_engine?.priority_class ? <StatusPill tone={priorityTone(r.rule_engine.priority_class)}>{r.rule_engine.priority_class.toUpperCase()}</StatusPill> : '—'}
          sub={r.rule_engine?.basis} />
        <Stat label="Realistic FTC" value={fmtDate(r.realistic_ftc_date)}
          tone={ftcSlip != null && ftcSlip > 0 ? 'critical' : undefined}
          sub={r.ftc_date_used ? <>FTC used {fmtDate(r.ftc_date_used)}{ftcSlip != null && ftcSlip !== 0 && ` · ${plural(Math.abs(ftcSlip), 'day')} ${ftcSlip > 0 ? 'later' : 'earlier'}`}</> : undefined} />
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
                  <div key={k} className="grid grid-cols-[36px_minmax(0,1fr)_44px] items-center gap-2 text-[12px]">
                    <span className="font-semibold text-foreground">{k}</span>
                    <MiniMeter pct={pct} tone={priorityTone(k) === 'neutral' ? 'ai' : priorityTone(k)} />
                    <span className="text-right tabular-nums text-muted-foreground">{pct}%</span>
                  </div>
                ))}
              </div>
            </ExplainBlock>
          )}
        </div>
      )}

      {/* Key drivers repeat the reasons above, so the explanation is shown without them. */}
      <ExplanationView ex={r.explanation ? { ...r.explanation, key_drivers: undefined } : undefined} />
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

export default function AIPredictionPanels() {
  return (
    <div className="flex flex-col gap-4">
      <OrderTcForecastPanel />
      <PriorityPredictionPanel />
    </div>
  );
}
