/* AI forecast & module order plan (training_model/ -> /api/forecast).

   Three questions, in the order a planner asks them:
     1. Which projects need a module decision now, and why?   (order plan)
     2. When will each block really charge?                    (block forecast)
     3. How far can I trust this?                              (tested accuracy)

   Everything the model produces is labelled Forecast and shown as a range.
   A planner can SAVE a project's order decision or a block's FTC date as
   correct: from then on the saved figure is what this page shows, a retrain
   never changes it, and a note appears only when the model's own figure has
   moved away from it. */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, CalendarClock, ChevronRight, Gauge, Info, Lock, PackageX, RotateCcw, Save, Truck,
} from 'lucide-react';
import { Card, CardHeader, Dialog, InfoTip, KPITile, Loader, StatusPill, cx } from '../../components/ui/primitives';
import type { Tone } from '../../components/ui/primitives';

const API = import.meta.env.VITE_API_BASE || '';
const BASE = `${API}/akasha/api/forecast`;

/* ── API shapes ──────────────────────────────────────────────────────── */
interface LockInfo { id: number; payload: Record<string, unknown>; model_version?: string; note?: string; locked_by: string; locked_at: string }
interface Plan {
  project_id: string; project_name?: string; action: string; why?: string; no_sap_po?: boolean;
  remaining_need_mwp?: number; installed_mwp?: number; stock_on_site_mwp?: number; pipeline_mwp?: number;
  uncovered_mwp?: number; ordered_mwp?: number; order_by_import?: string; order_by_domestic?: string;
  lead_import_days?: number; lead_domestic_days?: number; shortfall_from?: string; p6_data_date?: string;
  lock: LockInfo | null; model_now: Record<string, unknown> | null; model_changed: boolean;
}
interface Accuracy { rows: number; blocks: number; model_mae_days: number; p6_mae_days: number; naive_mae_days: number; model_within30_pct: number; p6_within30_pct: number }
interface Overview {
  available: boolean; reason?: string; plan_generated_at?: string;
  model?: { version: string; algorithm: string; trained_at: string; training?: { projects: number; ftc_blocks: number; milestones: number };
            accuracy?: Accuracy; by_horizon?: Array<Accuracy & { horizon: string }>; range_check?: { band_p20_p80_coverage_pct: number; p80_coverage_pct: number } };
  assumptions?: { site_buffer_days: number; hold_window_days: number; lead_time_quantile: string; tested_horizon_days: [number, number] };
  lead_times?: Record<string, { pos_with_receipts: number; po_to_first_receipt: { n: number; p50: number; p80: number }; transit: { p50: number; p80: number } }>;
  counts?: Record<string, number>; plans: Plan[];
}
interface Milestone { activity_name: string; baseline_finish: string; forecast_p20: string; forecast_p50: string; forecast_p80: string;
                      slip_p50: number; days_to_baseline: number; confidence: string; typical_slip_days: number; why: string }
interface Block { block: number; ftc?: Milestone; module_installation?: Milestone;
                  need?: { mwp: number; need_by: string; covered: boolean; site_started: boolean; forecast_shift_days: number };
                  lock: LockInfo | null; drift_days?: number }
interface Detail { plan: Plan | null; blocks: Block[] }

/* ── Formatting ──────────────────────────────────────────────────────── */
const dmy = (s?: string | null) => {
  if (!s) return '—';
  const d = new Date(String(s).slice(0, 10));
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' });
};
const mw = (v?: number | null) => (v == null ? '—' : v < 1 && v > 0 ? v.toFixed(1) : Math.round(v).toLocaleString('en-IN'));
const signed = (n: number) => `${n > 0 ? '+' : ''}${n}`;

const statusGroup = (a: string): 'act' | 'hold' | 'ok' | 'info' =>
  a.startsWith('Order now') || a.startsWith('Late') || a.startsWith('Not ordered') ? 'act'
    : a.startsWith('Hold') ? 'hold' : a === 'Complete' || a === 'Covered' ? 'ok' : 'info';
const statusTone = (a: string): Tone =>
  a.startsWith('Not ordered') || a.startsWith('Late') ? 'critical'
    : a.startsWith('Order now (domestic)') ? 'risk' : a.startsWith('Order now') ? 'watch'
      : a === 'Covered' ? 'healthy' : a === 'Complete' ? 'done' : 'neutral';
const STATUS_HELP: Record<string, string> = {
  'Order now (import)': 'Inside the import order window - order now so modules arrive before the first uncovered block needs them.',
  'Order now (domestic)': 'Import can no longer arrive in time; domestic still can.',
  'Late - expedite': 'POs exist, but they arrive after a block needs modules. Expedite or re-sequence blocks.',
  'Not ordered - needed now': 'SAP shows no module PO for this project, and a block needs modules before a new order could arrive.',
  Hold: 'Not needed yet. Ordering earlier would park modules in stores.',
  Covered: 'Stock on site and open POs reach every block before it needs them.',
  Complete: 'Every block’s modules are installed.',
  'No P6 dates': 'P6 has no module installation baseline for a block, so no need-by date can be worked out.',
};
const sentences = (why?: string) => (why || '').split(/(?<=\.)\s+(?=[A-Z])/).filter(Boolean);
const reasons = (why?: string) => (why || '').split(' | ').filter(Boolean);

/* ── Save dialog ─────────────────────────────────────────────────────── */
function SaveDialog({ target, onClose, onSaved }: {
  target: { title: string; body: React.ReactNode; request: Record<string, unknown> } | null;
  onClose: () => void; onSaved: () => void;
}) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setNote(''); setError(null); }, [target]);
  const save = async () => {
    if (!target) return;
    setBusy(true); setError(null);
    try {
      const r = await fetch(`${BASE}/locks`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...target.request, note: note.trim() || null }),
      });
      if (!r.ok) throw new Error(r.status === 403 ? 'You need edit rights to save a plan.' : `Save failed (${r.status})`);
      onSaved(); onClose();
    } catch (e) { setError(e instanceof Error ? e.message : 'Save failed'); } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!target} onClose={onClose} busy={busy} title={target?.title || ''}
      description="Saved figures stay as they are - a later forecast will not change them. You can unlock them at any time."
      footer={<>
        <button type="button" onClick={onClose} disabled={busy}
          className="rounded-lg border border-border-subtle px-3 py-1.5 text-[13px] text-fg-secondary hover:bg-surface-sunken disabled:opacity-50">Cancel</button>
        <button type="button" onClick={save} disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-blue px-3 py-1.5 text-[13px] font-semibold text-white hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50 disabled:opacity-50">
          {busy ? <Loader inline size="sm" label="Saving…" /> : <><Save className="h-3.5 w-3.5" /> Save as correct</>}
        </button>
      </>}>
      <div className="space-y-3 text-[13px]">
        {target?.body}
        <label className="block">
          <span className="text-[12px] font-medium text-fg-secondary">Note (optional) - why this is right</span>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3}
            placeholder="e.g. Confirmed with site: block 4 MMS starts 15-Nov"
            className="mt-1 w-full rounded-lg border border-border-subtle bg-surface-1 px-2.5 py-2 text-[13px] text-fg-primary focus:outline-none focus:ring-2 focus:ring-brand-blue/40" />
        </label>
        {error && <p className="text-[12.5px] text-status-critical-fg">{error}</p>}
      </div>
    </Dialog>
  );
}

function SavedBadge({ lock, onUnlock }: { lock: LockInfo; onUnlock: () => void }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-[11.5px] text-fg-secondary">
      <Lock className="h-3 w-3 text-status-healthy-fg" aria-hidden />
      Saved by <span className="font-medium text-fg-primary">{lock.locked_by}</span> on {dmy(lock.locked_at)}
      {lock.note && <InfoTip info={lock.note} />}
      <button type="button" onClick={(e) => { e.stopPropagation(); onUnlock(); }}
        className="ml-1 inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-fg-tertiary hover:bg-surface-sunken hover:text-fg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50">
        <RotateCcw className="h-3 w-3" /> Unlock
      </button>
    </span>
  );
}

/* ── Range bar: P6 date vs the forecast range ────────────────────────── */
function RangeCell({ m }: { m: Milestone }) {
  const late = m.slip_p50;
  return (
    <div className="min-w-[150px]">
      <div className="flex items-baseline gap-1.5">
        <span className="font-semibold tabular-nums text-fg-primary">{dmy(m.forecast_p50)}</span>
        <span className={cx('text-[11px] tabular-nums', late > 30 ? 'text-status-risk-fg' : late < -15 ? 'text-status-healthy-fg' : 'text-fg-tertiary')}>
          {late === 0 ? 'on P6' : `${signed(late)} d vs P6`}
        </span>
      </div>
      <div className="text-[11px] tabular-nums text-fg-tertiary">likely {dmy(m.forecast_p20)} – {dmy(m.forecast_p80)}</div>
    </div>
  );
}

/* ── Main view ───────────────────────────────────────────────────────── */
export default function ForecastPlanView() {
  const [ov, setOv] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'act' | 'hold' | 'ok' | 'all'>('act');
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, Detail | null>>({});
  const [save, setSave] = useState<{ title: string; body: React.ReactNode; request: Record<string, unknown> } | null>(null);
  const [showAcc, setShowAcc] = useState(false);

  const load = useCallback(() => {
    fetch(`${BASE}/overview`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setOv).catch((e) => setError(String(e.message || e)));
  }, []);
  useEffect(load, [load]);

  const loadDetail = useCallback((pid: string) => {
    setDetail((d) => ({ ...d, [pid]: null }));
    fetch(`${BASE}/projects/${encodeURIComponent(pid)}`).then((r) => r.json())
      .then((j) => setDetail((d) => ({ ...d, [pid]: j })));
  }, []);
  const refresh = (pid?: string) => { load(); if (pid) loadDetail(pid); };
  const unlock = async (id: number, pid: string) => {
    await fetch(`${BASE}/locks/${id}/unlock`, { method: 'POST' });
    refresh(pid);
  };

  const plans = useMemo(() => (ov?.plans || []).filter((p) => filter === 'all' || statusGroup(p.action) === filter)
    .sort((a, b) => (b.uncovered_mwp || 0) - (a.uncovered_mwp || 0)), [ov, filter]);

  if (error) return <Card><p className="text-[13px] text-status-critical-fg">Could not load the forecast: {error}</p></Card>;
  if (!ov) return <Card><Loader label="Loading the forecast…" /></Card>;
  if (!ov.available) return <Card tone="watch"><CardHeader icon={Info} title="No forecast yet" /><p className="mt-2 text-[13px] text-fg-secondary">{ov.reason}</p></Card>;

  const acc = ov.model?.accuracy;
  const c = ov.counts || {};
  const nOrderNow = (c['Order now (import)'] || 0) + (c['Order now (domestic)'] || 0);
  const groupCount = (g: string) => (ov.plans || []).filter((p) => g === 'all' || statusGroup(p.action) === g).length;

  return (
    <div className="flex w-full flex-col gap-4">
      {/* What this is */}
      <Card>
        <CardHeader icon={Gauge} title="AI forecast & module order plan"
          eyebrow={`Forecast - not a P6 or SAP figure · model ${ov.model?.version} · plan built ${dmy(ov.plan_generated_at)}`}
          right={<button type="button" onClick={() => setShowAcc((s) => !s)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border-subtle px-2.5 py-1 text-[12px] font-medium text-fg-secondary hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50">
            <Info className="h-3.5 w-3.5" /> {showAcc ? 'Hide' : 'How accurate is this?'}
          </button>} />
        <p className="mt-2 max-w-4xl text-[12.5px] leading-relaxed text-fg-secondary">
          For each project: when its blocks really need modules (P6 dates moved by the forecast), whether stock and open POs cover them,
          and if not, the latest safe order date - and why not earlier. Click a project for its blocks and reasons.
          Save a plan or a block date once it is confirmed; saved figures do not change when the forecast is re-run.
        </p>
        {showAcc && ov.model && <AccuracyPanel ov={ov} />}
      </Card>

      {/* Headline numbers */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KPITile icon={Gauge} tone="ai" label="Forecast error (avg)" value={acc ? `${Math.round(acc.model_mae_days)} days` : '—'}
          subtext={acc ? `P6 date misses by ${Math.round(acc.p6_mae_days)} days · tested on projects the model never saw` : undefined}
          info="Average gap between the forecast and the actual block FTC date, on projects held out of training. Lower is better." />
        <KPITile icon={CalendarClock} tone="watch" label="Order now" value={String(nOrderNow)}
          subtext={`${c['Order now (import)'] || 0} import · ${c['Order now (domestic)'] || 0} domestic only`} />
        <KPITile icon={PackageX} tone="critical" label="Not ordered - needed now" value={String(c['Not ordered - needed now'] || 0)}
          subtext="No module PO in SAP for the project" info={STATUS_HELP['Not ordered - needed now']} />
        <KPITile icon={Truck} tone="risk" label="Late - expedite" value={String(c['Late - expedite'] || 0)}
          subtext="POs arrive after a block needs them" />
      </div>

      {/* Projects */}
      <Card pad="none" className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-3.5">
          <CardHeader title="Projects" eyebrow="Sorted by modules not yet on any PO" />
          <div role="tablist" aria-label="Filter projects" className="inline-flex gap-1 rounded-lg border border-border-subtle bg-surface-sunken p-0.5">
            {([['act', 'Needs action'], ['hold', 'Hold'], ['ok', 'Covered / done'], ['all', 'All']] as const).map(([k, label]) => (
              <button key={k} type="button" role="tab" aria-selected={filter === k} onClick={() => setFilter(k)}
                className={cx('rounded-md px-2.5 py-1 text-[12px] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50',
                  filter === k ? 'bg-surface-1 text-fg-primary shadow-sm' : 'text-fg-secondary hover:text-fg-primary')}>
                {label} <span className="tabular-nums text-fg-tertiary">{groupCount(k)}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="mt-3 max-h-[72vh] overflow-auto custom-scrollbar border-t border-border">
          <table className="w-full min-w-[1040px] border-separate border-spacing-0 text-[13px]">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-fg-tertiary">
                {[['Project', ''], ['Decision', ''], ['Still to install', 'text-right'], ['On site', 'text-right'],
                  ['On order', 'text-right'], ['Not ordered', 'text-right'], ['Order by · import', 'text-right'],
                  ['Order by · domestic', 'text-right']].map(([h, cl]) => (
                  <th key={h} className={cx('sticky top-0 z-10 border-b border-border bg-surface-sunken px-3 py-2.5 font-semibold', cl)}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {plans.length === 0 && (
                <tr><td colSpan={8} className="px-3 py-6 text-center text-[12.5px] text-fg-tertiary">No projects in this group.</td></tr>
              )}
              {plans.map((p) => {
                const isOpen = open === p.project_id;
                return (
                  <React.Fragment key={p.project_id}>
                    <tr tabIndex={0} aria-expanded={isOpen}
                      onClick={() => { setOpen(isOpen ? null : p.project_id); if (!isOpen && !detail[p.project_id]) loadDetail(p.project_id); }}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); (e.currentTarget as HTMLElement).click(); } }}
                      className="cursor-pointer hover:bg-surface-sunken/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-blue/50">
                      <td className="border-b border-border-subtle px-3 py-2">
                        <span className="inline-flex items-center gap-1.5 font-medium text-fg-primary">
                          <ChevronRight className={cx('h-3.5 w-3.5 text-fg-tertiary transition-transform', isOpen && 'rotate-90')} />
                          {p.project_id}
                          {p.lock && <Lock className="h-3 w-3 text-status-healthy-fg" aria-label="Saved" />}
                        </span>
                        <span className="ml-5 block text-[11px] text-fg-tertiary">{p.project_name}</span>
                      </td>
                      <td className="border-b border-border-subtle px-3 py-2">
                        <span className="inline-flex items-center gap-1">
                          <StatusPill tone={statusTone(p.action)}>{p.action}</StatusPill>
                          <InfoTip info={STATUS_HELP[p.action.startsWith('Hold') ? 'Hold' : p.action] || p.action} />
                        </span>
                        {p.model_changed && <span className="mt-0.5 block text-[11px] text-status-watch-fg">Forecast now differs from the saved plan</span>}
                      </td>
                      <td className="border-b border-border-subtle px-3 py-2 text-right tabular-nums">{mw(p.remaining_need_mwp)} <span className="text-[11px] text-fg-tertiary">MWp</span></td>
                      <td className="border-b border-border-subtle px-3 py-2 text-right tabular-nums">{mw(p.stock_on_site_mwp)}</td>
                      <td className="border-b border-border-subtle px-3 py-2 text-right tabular-nums">{mw(p.pipeline_mwp)}</td>
                      <td className={cx('border-b border-border-subtle px-3 py-2 text-right font-medium tabular-nums', (p.uncovered_mwp || 0) > 0.5 && 'text-status-critical-fg')}>{mw(p.uncovered_mwp)}</td>
                      <td className="border-b border-border-subtle px-3 py-2 text-right tabular-nums">{dmy(p.order_by_import)}</td>
                      <td className="border-b border-border-subtle px-3 py-2 text-right tabular-nums">{dmy(p.order_by_domestic)}</td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={8} className="border-b border-border bg-surface-sunken/30 px-5 py-4">
                          <ProjectDetail plan={p} detail={detail[p.project_id]} ov={ov}
                            onSave={setSave} onUnlock={(id) => unlock(id, p.project_id)} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <SaveDialog target={save} onClose={() => setSave(null)} onSaved={() => refresh(open || undefined)} />
    </div>
  );
}

/* ── One project, opened ─────────────────────────────────────────────── */
function ProjectDetail({ plan, detail, ov, onSave, onUnlock }: {
  plan: Plan; detail: Detail | null | undefined; ov: Overview;
  onSave: (t: { title: string; body: React.ReactNode; request: Record<string, unknown> }) => void;
  onUnlock: (id: number) => void;
}) {
  const a = ov.assumptions;
  const blocks = (detail?.blocks || []).filter((b) => b.ftc || b.need);
  const savePlan = () => onSave({
    title: `Save the order plan for ${plan.project_id}`,
    body: <p className="text-fg-secondary"><StatusPill tone={statusTone(plan.action)}>{plan.action}</StatusPill>
      <span className="ml-2">Import order-by {dmy(plan.order_by_import)} · domestic {dmy(plan.order_by_domestic)} · not ordered {mw(plan.uncovered_mwp)} MWp</span></p>,
    request: { scope: 'order_plan', project_id: plan.project_id, model_version: ov.model?.version,
               payload: Object.fromEntries(['action', 'remaining_need_mwp', 'stock_on_site_mwp', 'pipeline_mwp', 'uncovered_mwp',
                 'order_by_import', 'order_by_domestic', 'shortfall_from', 'shortfall_block', 'why'].map((k) => [k, (plan as unknown as Record<string, unknown>)[k]])) },
  });
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      {/* Why */}
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[13px] font-semibold text-fg-primary">Why this decision</p>
          {plan.lock ? <SavedBadge lock={plan.lock} onUnlock={() => onUnlock(plan.lock!.id)} />
            : <button type="button" onClick={savePlan}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border-subtle bg-surface-1 px-2.5 py-1 text-[12px] font-medium text-fg-primary hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50">
                <Save className="h-3.5 w-3.5" /> Save as correct</button>}
        </div>
        <ul className="mt-2 space-y-1.5 text-[12.5px] leading-relaxed text-fg-secondary">
          {sentences(plan.why).map((s) => <li key={s} className="flex gap-2"><span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-fg-tertiary" />{s}</li>)}
        </ul>
        {plan.model_changed && plan.model_now && (
          <div className="mt-3 rounded-lg border border-status-watch-border bg-status-watch-bg px-3 py-2 text-[12px] text-fg-secondary">
            <span className="inline-flex items-center gap-1 font-semibold text-status-watch-fg"><AlertTriangle className="h-3.5 w-3.5" /> The latest forecast differs</span>
            <span className="mt-0.5 block">Now: {String(plan.model_now.action)} · import order-by {dmy(plan.model_now.order_by_import as string)}. The saved plan above is unchanged - unlock it to take the new one.</span>
          </div>
        )}
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
          {[
            ['Already installed', `${mw(plan.installed_mwp)} MWp`],
            ['Ordered in SAP', `${mw(plan.ordered_mwp)} MWp`],
            ['Import lead time used', plan.lead_import_days ? `${plan.lead_import_days} days` : '—'],
            ['Domestic lead time used', plan.lead_domestic_days ? `${plan.lead_domestic_days} days` : '—'],
            ['Modules on site before installation', `${a?.site_buffer_days ?? '—'} days`],
            ['Site progress as of', dmy(plan.p6_data_date)],
          ].map(([k, v]) => (
            <React.Fragment key={k}><dt className="text-fg-tertiary">{k}</dt><dd className="text-right font-medium tabular-nums text-fg-primary">{v}</dd></React.Fragment>
          ))}
        </dl>
      </div>

      {/* Blocks */}
      <div className="min-w-0">
        <p className="text-[13px] font-semibold text-fg-primary">Blocks still to charge</p>
        <p className="text-[11.5px] text-fg-tertiary">FTC forecast as a likely range · reasons are what the model relied on, not proven causes</p>
        {detail === null || detail === undefined ? <div className="mt-3"><Loader inline size="sm" label="Loading blocks…" /></div>
          : blocks.length === 0 ? <p className="mt-3 text-[12.5px] text-fg-tertiary">No open blocks with dates in P6.</p>
            : (
              <div className="mt-2 max-h-[420px] overflow-auto custom-scrollbar rounded-lg border border-border-subtle">
                <table className="w-full text-[12px]">
                  <thead className="sticky top-0 bg-surface-sunken text-left text-[10.5px] uppercase tracking-wide text-fg-tertiary">
                    <tr>{['Block', 'Modules needed by', 'P6 FTC', 'Forecast FTC', 'Main reason', ''].map((h) => <th key={h} className="px-2.5 py-2 font-semibold">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {blocks.map((b) => {
                      const f = b.ftc;
                      const saved = b.lock?.payload as Record<string, string> | undefined;
                      const top = f ? reasons(f.why)[0] : undefined;
                      return (
                        <tr key={b.block} className="border-t border-border-subtle align-top">
                          <td className="px-2.5 py-2 font-medium text-fg-primary">{b.block}</td>
                          <td className="px-2.5 py-2 tabular-nums">
                            {b.need ? <>{dmy(b.need.need_by)}<span className="block text-[10.5px] text-fg-tertiary">{mw(b.need.mwp)} MWp{b.need.covered ? ' · covered' : ''}</span></> : '—'}
                          </td>
                          <td className="px-2.5 py-2 tabular-nums text-fg-secondary">{f ? dmy(f.baseline_finish) : '—'}</td>
                          <td className="px-2.5 py-2">
                            {saved ? (
                              <div>
                                <span className="font-semibold tabular-nums text-fg-primary">{dmy(saved.forecast_p50)}</span>
                                <span className="ml-1 text-[10.5px] text-status-healthy-fg">saved</span>
                                {b.drift_days != null && Math.abs(b.drift_days) > 15 && (
                                  <span className="block text-[10.5px] text-status-watch-fg">forecast now {signed(b.drift_days)} d</span>
                                )}
                              </div>
                            ) : f ? (
                              <>
                                <RangeCell m={f} />
                                {f.confidence !== 'tested' && <span className="block text-[10.5px] text-status-watch-fg">beyond tested range - indicative</span>}
                              </>
                            ) : '—'}
                          </td>
                          <td className="max-w-[260px] px-2.5 py-2 text-[11.5px] text-fg-secondary">
                            {top || '—'}
                            {f && <InfoTip align="end" info={
                              <div className="space-y-1 text-[12px]">
                                <p className="font-semibold">Why this forecast</p>
                                <p>A typical block here charged about {f.typical_slip_days} days after its P6 date. From there:</p>
                                <ul className="list-disc pl-4">{reasons(f.why).map((r) => <li key={r}>{r}</li>)}</ul>
                              </div>} />}
                          </td>
                          <td className="px-2.5 py-2 text-right">
                            {b.lock ? <SavedBadge lock={b.lock} onUnlock={() => onUnlock(b.lock!.id)} />
                              : f && (
                                <button type="button" title="Save this block's FTC date as correct"
                                  onClick={() => onSave({
                                    title: `Save block ${b.block} FTC for ${plan.project_id}`,
                                    body: <p className="text-fg-secondary">Forecast FTC <b className="text-fg-primary">{dmy(f.forecast_p50)}</b> (likely {dmy(f.forecast_p20)} – {dmy(f.forecast_p80)}); P6 says {dmy(f.baseline_finish)}.</p>,
                                    request: { scope: 'block_ftc', project_id: plan.project_id, block: b.block, model_version: ov.model?.version,
                                               payload: { forecast_p20: f.forecast_p20, forecast_p50: f.forecast_p50, forecast_p80: f.forecast_p80, baseline_finish: f.baseline_finish } },
                                  })}
                                  className="inline-flex items-center gap-1 rounded-md border border-border-subtle px-2 py-0.5 text-[11px] text-fg-secondary hover:bg-surface-1 hover:text-fg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50">
                                  <Save className="h-3 w-3" /> Save
                                </button>
                              )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
      </div>
    </div>
  );
}

/* ── How accurate is this? ───────────────────────────────────────────── */
function AccuracyPanel({ ov }: { ov: Overview }) {
  const m = ov.model!;
  const rc = m.range_check;
  const order = ['overdue', '0-45d', '46-100d', '100d+'];
  const label: Record<string, string> = { overdue: 'Already past the P6 date', '0-45d': '0–45 days ahead', '46-100d': '46–100 days ahead', '100d+': '100–180 days ahead' };
  return (
    <div className="mt-4 grid gap-5 border-t border-border-subtle pt-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div>
        <p className="text-[12.5px] font-semibold text-fg-primary">Average error in days - tested on projects the model never saw</p>
        <table className="mt-2 w-full text-[12px]">
          <thead className="text-left text-[10.5px] uppercase tracking-wide text-fg-tertiary">
            <tr><th className="py-1.5">Forecast made</th><th className="py-1.5 text-right">P6 date</th><th className="py-1.5 text-right">Earlier blocks</th><th className="py-1.5 text-right">Model</th><th className="py-1.5 text-right">Blocks</th></tr>
          </thead>
          <tbody>
            {[...(m.by_horizon || [])].sort((a, b) => order.indexOf(a.horizon) - order.indexOf(b.horizon)).map((r) => (
              <tr key={r.horizon} className="border-t border-border-subtle">
                <td className="py-1.5 text-fg-secondary">{label[r.horizon] || r.horizon}</td>
                <td className="py-1.5 text-right tabular-nums">{Math.round(r.p6_mae_days)}</td>
                <td className="py-1.5 text-right tabular-nums">{Math.round(r.naive_mae_days)}</td>
                <td className="py-1.5 text-right font-semibold tabular-nums text-fg-primary">{Math.round(r.model_mae_days)}</td>
                <td className="py-1.5 text-right tabular-nums text-fg-tertiary">{r.blocks}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[11.5px] leading-relaxed text-fg-tertiary">
          Trained on {m.training?.ftc_blocks} charged blocks from {m.training?.projects} projects ({m.algorithm}, {dmy(m.trained_at)}).
          {rc && ` The likely range held the actual date ${Math.round(rc.band_p20_p80_coverage_pct)}% of the time (target 60%); ${Math.round(rc.p80_coverage_pct)}% charged by its late end (target 80%).`}
          {' '}Within ±30 days: model {Math.round(m.accuracy?.model_within30_pct || 0)}% vs P6 {Math.round(m.accuracy?.p6_within30_pct || 0)}%.
        </p>
      </div>
      <div>
        <p className="text-[12.5px] font-semibold text-fg-primary">Lead times used (measured from Ariba receipts)</p>
        <dl className="mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-[12px]">
          {Object.entries(ov.lead_times || {}).map(([o, v]) => (
            <React.Fragment key={o}>
              <dt className="capitalize text-fg-tertiary">{o} · PO to first receipt</dt>
              <dd className="text-right tabular-nums text-fg-primary">{v.po_to_first_receipt.p50}–{v.po_to_first_receipt.p80} days <span className="text-fg-tertiary">({v.po_to_first_receipt.n} POs)</span></dd>
            </React.Fragment>
          ))}
          <dt className="text-fg-tertiary">Plan uses</dt><dd className="text-right text-fg-primary">{ov.assumptions?.lead_time_quantile?.toUpperCase()} - 4 in 5 POs were faster</dd>
          <dt className="text-fg-tertiary">Hold rule</dt><dd className="text-right text-fg-primary">no order &gt;{ov.assumptions?.hold_window_days} days before needed</dd>
          <dt className="text-fg-tertiary">Tested forecast range</dt><dd className="text-right text-fg-primary">{ov.assumptions?.tested_horizon_days?.[0]} to {ov.assumptions?.tested_horizon_days?.[1]} days</dd>
        </dl>
        <p className="mt-2 text-[11.5px] text-fg-tertiary">Full logic: training_model/HOW_IT_WORKS.md</p>
      </div>
    </div>
  );
}
