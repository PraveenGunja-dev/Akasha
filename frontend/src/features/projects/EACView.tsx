/* ── BESS EAC (Estimate at Completion), a view inside the project's SAP tab ──
   The approved EAC format, one project at a time. Approved Capex, Balance to
   Completion and Remarks are edited in place and saved on leaving the cell;
   Incurred and Committed come from SAP; EAC and Variance are formulas.
   Everything is computed server-side (services/bess_eac.py) so the screen and
   the export can never disagree. */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, AlertTriangle, RefreshCcw, Landmark, Receipt, FileSignature, Calculator, Scale, Table2, Columns3, ChevronRight } from 'lucide-react';
import { Card, CardHeader, KPITile } from '../../components/ui/primitives';

const API = '/akasha/api/bess';

type Kind = 'item' | 'group' | 'total';
export interface EACRow {
  key: string; sr: string; description: string; kind: Kind;
  wbs: { agel: string[]; age6l: string[]; spv: string[] };
  approved: number | null; approvedSource: string | null;
  excluded: string[];
  /** Group / total lines: the Sr of the lines they add up (no WBS of their own). */
  sumOf: string[];
  /** One per WBS suffix on the line, named from SAP's CO object name. */
  subLines: EACSubLine[];
  incurred: number; committed: number; committedPOrd: number; committedPReq: number; balance: number;
  eac: number; variance: number | null; remarks: string | null;
  editable: { approved: boolean; balance: boolean; remarks: boolean };
}
export type Company = 'agel' | 'age6l' | 'spv';
export interface EACSubLine {
  suffix: string; name: string | null; wbs: Record<Company, string[]>;
  incurred: number; committedPOrd: number; committedPReq: number; committed: number; eac: number;
}
export type Category = 'POrd' | 'PReq';
export interface EACSettings {
  categories: Category[];
  /** Per EAC line, the WBS codes not counted on it. */
  excluded: Record<string, string[]>;
  updatedBy: string | null; updatedAt: string | null;
}
export interface EACData {
  projectId: string; pss: string; rows: EACRow[]; settings: EACSettings;
  roots: Record<Company, string>;
  sources: Record<string, { file: string; loadedAt: string | null }>;
  basis: Record<string, string>;
}
type Field = 'approved' | 'balance' | 'remarks';

/* One colour per company, from the brand ramp (the status palette is reserved
   for state). The same colour marks the company's toggle and its WBS column. */
const COMPANY: Record<Company, { label: string; dot: string; on: string }> = {
  agel: { label: 'AGEL', dot: 'bg-brand-blue', on: 'border-brand-blue/60 bg-brand-blue/10 text-foreground' },
  age6l: { label: 'AGE6L', dot: 'bg-brand-purple', on: 'border-brand-purple/60 bg-brand-purple/10 text-foreground' },
  spv: { label: 'SPV', dot: 'bg-brand-pink', on: 'border-brand-pink/60 bg-brand-pink/10 text-foreground' },
};

/* Two decimals, Indian grouping; a value that rounds to zero reads 0.00, never -0.00. */
export const cr = (v: number | null | undefined) =>
  v === null || v === undefined ? '—'
    : (Math.abs(v) < 0.005 ? 0 : v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* Columns. The money columns and the formula inputs are always shown; the
   three WBS columns (one per company) and Remarks can be switched on or off
   from the Columns menu - AGE6L starts hidden to keep the table compact. */
type ColKey = 'sr' | 'description' | 'agel' | 'age6l' | 'spv' | 'approved' | 'incurred'
  | 'committed' | 'committedPOrd' | 'committedPReq' | 'balance' | 'eac' | 'variance' | 'remarks';
const COLUMNS: { key: ColKey; label: string; cls: string; optional?: boolean }[] = [
  { key: 'sr', label: 'Sr', cls: 'w-14' },
  { key: 'description', label: 'Description', cls: '' },
  { key: 'agel', label: 'AGEL WBS', cls: 'w-40', optional: true },
  { key: 'age6l', label: 'AGE6L WBS', cls: 'w-40', optional: true },
  { key: 'spv', label: 'SPV WBS', cls: 'w-40', optional: true },
  { key: 'approved', label: 'Approved Capex', cls: 'w-32 text-right' },
  { key: 'incurred', label: 'Incurred', cls: 'w-28 text-right' },
  { key: 'committed', label: 'Committed', cls: 'w-28 text-right' },
  // The split behind Committed - shown whether or not a type is counted.
  { key: 'committedPOrd', label: 'Committed POrd', cls: 'w-28 text-right', optional: true },
  { key: 'committedPReq', label: 'Committed PReq', cls: 'w-28 text-right', optional: true },
  { key: 'balance', label: 'Balance to Completion', cls: 'w-32 text-right' },
  { key: 'eac', label: 'EAC', cls: 'w-28 text-right' },
  { key: 'variance', label: 'Variance', cls: 'w-28 text-right' },
  { key: 'remarks', label: 'EAC Remarks', cls: 'w-64', optional: true },
];
const OPTIONAL = COLUMNS.filter((c) => c.optional);
const DEFAULT_ON: ColKey[] = ['agel', 'spv', 'remarks'];
const COLS_KEY = 'akasha.eac.columns';

/* Which optional columns are on - remembered per browser; storage may be
   unavailable (private window), so every access is guarded. */
function useEACColumns() {
  const [on, setOn] = useState<Set<ColKey>>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(COLS_KEY) || 'null');
      if (Array.isArray(saved)) {
        return new Set(saved.filter((k: string) => OPTIONAL.some((c) => c.key === k)) as ColKey[]);
      }
    } catch { /* fall back to the defaults */ }
    return new Set(DEFAULT_ON);
  });
  const persist = (next: Set<ColKey>) => {
    setOn(next);
    try { localStorage.setItem(COLS_KEY, JSON.stringify([...next])); } catch { /* not remembered */ }
  };
  return { on, save: persist };
}

/* One company's WBS on one line, as a single toggle: clicking counts or
   leaves out all of that company's codes on the line together. Counted reads
   normally; left out is struck through and greyed. A dashed outline marks a
   change not yet saved. The "Other SAP cost" line's long list shows two codes
   and a count. */
const WbsToggle: React.FC<{
  codes: string[]; company: Company; left: Set<string>; savedLeft: Set<string>;
  disabled: boolean; onSet: (count: boolean) => void;
}> = ({ codes, company, left, savedLeft, disabled, onSet }) => {
  if (!codes.length) return <span className="px-2 text-muted-foreground/50">—</span>;
  const outN = codes.filter((c) => left.has(c)).length;
  const state = outN === 0 ? 'on' : outN === codes.length ? 'off' : 'some';
  const changed = codes.some((c) => left.has(c) !== savedLeft.has(c));
  const shown = codes.length > 3 ? codes.slice(0, 2) : codes;
  const name = COMPANY[company].label;
  return (
    <button type="button" disabled={disabled} aria-pressed={state === 'on' ? true : state === 'off' ? false : 'mixed'}
      onClick={() => onSet(state !== 'on')}
      title={codes.join('\n')}
      aria-label={`${name} WBS on this line: ${state === 'on' ? 'counted' : state === 'off' ? 'left out' : 'partly counted'}`}
      className={`flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-1.5 text-left transition-colors
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-60
                  ${state === 'off' ? 'border-transparent hover:border-border hover:bg-muted/60' : `${COMPANY[company].on} hover:brightness-95`}
                  ${changed ? 'outline outline-1 outline-offset-1 outline-dashed outline-primary/60' : ''}`}>
      <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border
                        ${state === 'off' ? 'border-border' : `${COMPANY[company].dot} border-transparent`}`}>
        {state === 'on' && <span className="text-[9px] leading-none text-white">✓</span>}
        {state === 'some' && <span className="h-0.5 w-1.5 rounded bg-white" />}
      </span>
      <span className={`min-w-0 font-mono text-[11px] leading-snug ${state === 'off' ? 'text-muted-foreground/60 line-through' : 'text-foreground/80'}`}>
        {shown.map((c) => <span key={c} className="block truncate">{c}</span>)}
        {codes.length > shown.length && <span className="block text-muted-foreground">+{codes.length - shown.length} more</span>}
      </span>
    </button>
  );
};

/* Committed with its POrd / PReq split in a hover card. The card opens to the
   left of the figure, so the table's scroll box never clips it at the top or
   bottom; it also opens on keyboard focus. */
const CommittedValue: React.FC<{ row: Pick<EACRow, 'committed' | 'committedPOrd' | 'committedPReq'> }> = ({ row }) => (
  <span tabIndex={0} aria-label={`Committed ${cr(row.committed)} Cr: purchase orders ${cr(row.committedPOrd)}, requisitions ${cr(row.committedPReq)}`}
    className="group relative inline-block rounded px-1 outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-primary/50">
    {cr(row.committed)}
    <span role="tooltip"
      className="pointer-events-none invisible absolute right-full top-1/2 z-30 mr-2 w-60 -translate-y-1/2 rounded-lg border border-border
                 bg-card px-3 py-2.5 text-left text-[12px] font-normal opacity-0 shadow-xl transition-opacity duration-150
                 group-hover:visible group-hover:opacity-100 group-focus-visible:visible group-focus-visible:opacity-100">
      <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Committed · INR Cr</span>
      <span className="flex justify-between gap-4 py-0.5">
        <span className="text-muted-foreground">Purchase orders (POrd)</span>
        <span className="tabular-nums text-foreground">{cr(row.committedPOrd)}</span>
      </span>
      <span className="flex justify-between gap-4 py-0.5">
        <span className="text-muted-foreground">Requisitions (PReq)</span>
        <span className="tabular-nums text-foreground">{cr(row.committedPReq)}</span>
      </span>
      <span className="mt-1 flex justify-between gap-4 border-t border-border pt-1.5 font-semibold">
        <span className="text-foreground">Total</span>
        <span className="tabular-nums text-foreground">{cr(row.committed)}</span>
      </span>
    </span>
  </span>
);

/* Column picker. Ticks edit a draft; Save applies and remembers it (per
   browser), Cancel or closing the menu discards it. */
const ColumnsMenu: React.FC<{ cols: ReturnType<typeof useEACColumns> }> = ({ cols }) => {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Set<ColKey>>(cols.on);
  const ref = useRef<HTMLDivElement>(null);
  const openMenu = () => { setDraft(new Set(cols.on)); setOpen(true); };
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);
  const toggle = (k: ColKey) => setDraft((prev) => {
    const n = new Set(prev);
    if (n.has(k)) n.delete(k); else n.add(k);
    return n;
  });
  const same = (x: Set<ColKey>, y: Set<ColKey>) => x.size === y.size && [...x].every((k) => y.has(k));
  const dirty = !same(draft, cols.on);
  const isDefault = same(draft, new Set(DEFAULT_ON));
  return (
    <div ref={ref} className="relative">
      <button onClick={() => (open ? setOpen(false) : openMenu())} aria-haspopup="dialog" aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-[12px] font-medium
                   text-muted-foreground transition-colors hover:bg-muted hover:text-foreground
                   focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">
        <Columns3 className="h-3.5 w-3.5" /> Columns
        <span className="tabular-nums text-muted-foreground/70">{cols.on.size}/{OPTIONAL.length}</span>
      </button>
      {open && (
        <div role="dialog" aria-label="Choose columns"
          className="absolute right-0 top-full z-30 mt-1 w-56 rounded-lg border border-border bg-card p-1.5 shadow-xl">
          <div className="flex items-center justify-between px-2 pb-1.5 pt-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Show columns</span>
            <button onClick={() => setDraft(new Set(DEFAULT_ON))} disabled={isDefault}
              className="text-[11px] font-medium text-primary hover:underline disabled:text-muted-foreground disabled:no-underline">
              Defaults
            </button>
          </div>
          {OPTIONAL.map((c) => (
            <label key={c.key}
              className="flex cursor-pointer select-none items-center gap-2.5 rounded-md px-2 py-1.5 text-[12px] text-foreground hover:bg-muted/60">
              <input type="checkbox" checked={draft.has(c.key)} onChange={() => toggle(c.key)}
                className="h-3.5 w-3.5 cursor-pointer accent-[var(--primary)]" />
              <span className={draft.has(c.key) ? 'font-medium' : 'text-muted-foreground'}>{c.label}</span>
            </label>
          ))}
          <div className="mt-1.5 flex items-center justify-end gap-1.5 border-t border-border px-1 pt-2">
            <button type="button" onClick={() => setOpen(false)}
              className="rounded-md border border-border px-2.5 py-1 text-[12px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground">
              Cancel
            </button>
            <button type="button" disabled={!dirty} onClick={() => { cols.save(draft); setOpen(false); }}
              className="rounded-md bg-primary px-3 py-1 text-[12px] font-semibold text-primary-foreground hover:bg-primary/90
                         disabled:cursor-not-allowed disabled:opacity-40
                         focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export function useEAC(projectId: string | undefined, active: boolean) {
  const [data, setData] = useState<EACData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);   // "key:field"

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true); setError(null);
    fetch(`${API}/${projectId}/eac`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: EACData) => setData(d))
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => { if (active) load(); }, [active, load]);

  const save = useCallback((row: EACRow, field: Field, raw: string) => {
    if (!projectId) return;
    const value = field === 'remarks' ? raw : raw === '' ? null : Number(raw);
    if (field !== 'remarks' && value !== null && Number.isNaN(value as number)) return;
    setSaving(`${row.key}:${field}`); setError(null);
    fetch(`${API}/${projectId}/eac/${row.key}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [field]: value }),
    })
      .then((r) => (r.ok ? r.json() : r.json().then((j) => Promise.reject(new Error(j.detail || `HTTP ${r.status}`)))))
      .then((d: EACData) => setData(d))
      .catch((e) => setError(`Not saved: ${String(e.message || e)}`))
      .finally(() => setSaving(null));
  }, [projectId]);

  /* What counts (commitment types, WBS left out per line) applies only when
     saved; the server recomputes every figure, so screen and export agree. */
  const saveSettings = useCallback((excluded: Record<string, string[]>) => {
    if (!projectId) return Promise.resolve(false);
    setSaving('settings'); setError(null);
    return fetch(`${API}/${projectId}/eac/settings`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ excluded }),
    })
      .then((r) => (r.ok ? r.json() : r.json().then((j) => Promise.reject(new Error(j.detail || `HTTP ${r.status}`)))))
      .then((d: EACData) => { setData(d); return true; })
      .catch((e) => { setError(`Not saved: ${String(e.message || e)}`); return false; })
      .finally(() => setSaving(null));
  }, [projectId]);

  return { data, loading, error, saving, load, save, saveSettings };
}

/* One editable cell: formatted at rest, the raw number while editing.
   Commits on blur or Enter, reverts on Escape. */
const EditCell: React.FC<{
  value: number | string | null; numeric?: boolean; placeholder?: string;
  label: string; saving: boolean; onCommit: (v: string) => void;
}> = ({ value, numeric, placeholder, label, saving, onCommit }) => {
  const raw = value === null || value === undefined ? '' : String(value);
  const [focused, setFocused] = useState(false);
  const [draft, setDraft] = useState(raw);
  useEffect(() => { if (!focused) setDraft(raw); }, [raw, focused]);
  const shown = focused ? draft : numeric ? (raw === '' ? '' : cr(Number(raw))) : raw;
  return (
    <input
      aria-label={label}
      value={shown}
      inputMode={numeric ? 'decimal' : 'text'}
      placeholder={placeholder}
      disabled={saving}
      onFocus={() => { setFocused(true); setDraft(raw); }}
      onChange={(e) => setDraft(numeric ? e.target.value.replace(/[^0-9.\-]/g, '') : e.target.value)}
      onBlur={() => { setFocused(false); if (draft.trim() !== raw.trim()) onCommit(draft.trim()); }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
        if (e.key === 'Escape') { setDraft(raw); (e.target as HTMLInputElement).blur(); }
      }}
      className={`w-full rounded-md border border-dashed border-border/70 bg-transparent px-2 py-1 ${numeric ? 'text-right tabular-nums' : ''}
                  text-[13px] text-foreground placeholder:text-muted-foreground/50
                  hover:border-primary/50 focus:border-solid focus:border-primary focus:bg-background focus:outline-none
                  focus:ring-2 focus:ring-primary/30 disabled:opacity-50`}
    />
  );
};

export const EACView: React.FC<{ eac: ReturnType<typeof useEAC> }> = ({ eac }) => {
  const { data, loading, error, saving, load, save, saveSettings } = eac;
  const cols = useEACColumns();
  const visible = COLUMNS.filter((c) => !c.optional || cols.on.has(c.key));
  const total = data?.rows.find((r) => r.key === 'L63');

  // Draft of what counts; reset whenever the saved settings change.
  const savedKey = data ? JSON.stringify(data.settings) : '';
  const [draftLeft, setDraftLeft] = useState<Record<string, string[]>>({});
  useEffect(() => {
    if (!data) return;
    setDraftLeft(data.settings.excluded);
  }, [savedKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  // Lines whose WBS sub-lines are folded away. Shown by default: an EAC line
  // often combines distinct SAP items (BESS Containers + Logistics).
  const [folded, setFolded] = useState<Set<string>>(new Set());
  // Group lines (3.1, 5, 7, 12, 13) read as section headers; hidden unless asked.
  const [showHeaders, setShowHeaders] = useState<boolean>(() => {
    try { return localStorage.getItem('akasha.eac.headers') === '1'; } catch { return false; }
  });
  const toggleHeaders = () => setShowHeaders((v) => {
    try { localStorage.setItem('akasha.eac.headers', v ? '0' : '1'); } catch { /* not remembered */ }
    return !v;
  });
  const hasSubs = (r: EACRow) => r.subLines.length > 1 || (r.key === 'L64' && r.subLines.length > 0);
  const toggleFold = (key: string) => setFolded((prev) => {
    const n = new Set(prev);
    if (n.has(key)) n.delete(key); else n.add(key);
    return n;
  });
  // Count (or leave out) every code of one company on one line.
  const setLineCompany = (key: string, codes: string[], count: boolean) => setDraftLeft((prev) => {
    const keep = (prev[key] || []).filter((x) => !codes.includes(x));
    const next = count ? keep : [...keep, ...codes];
    const out = { ...prev };
    if (next.length) out[key] = next; else delete out[key];
    return out;
  });
  const lineChanges = !data ? 0 : data.rows.reduce((n, r) =>
    n + (Object.keys(COMPANY) as Company[]).filter((c) => r.wbs[c].some(
      (code) => (draftLeft[r.key] || []).includes(code) !== (data.settings.excluded[r.key] || []).includes(code))).length, 0);
  const src = data?.sources || {};

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading EAC…
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-status-critical-border bg-status-critical-bg px-3 py-2 text-[13px] text-status-critical-fg">
          <AlertTriangle className="h-4 w-4 shrink-0" /> {error}
          <button onClick={load} className="ml-auto rounded-md px-2 py-0.5 text-[12px] font-medium underline-offset-2 hover:underline">
            Retry
          </button>
        </div>
      )}
      {data && total && (
        <>
          {/* Summary: the Total Cost row - the figures a reviewer reads first */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            <KPITile label="Approved Capex" icon={Landmark} size="supporting"
              value={total.approved === null ? '—' : `₹${cr(total.approved)}`} unit="Cr"
              subtext={total.approved === null ? 'Enter approved capex per line' : 'Project CAPEX sheet, editable'} />
            <KPITile label="Incurred" icon={Receipt} size="supporting" value={`₹${cr(total.incurred)}`} unit="Cr"
              info={data.basis.incurred} subtext={src.incurred?.file || 'No CJI3 loaded'} />
            <KPITile label="Committed" icon={FileSignature} size="supporting" value={`₹${cr(total.committed)}`} unit="Cr"
              info={data.basis.committed}
              subtext={`POrd ₹${cr(total.committedPOrd)} + PReq ₹${cr(total.committedPReq)} Cr`} />
            <KPITile label="EAC" icon={Calculator} size="supporting" value={`₹${cr(total.eac)}`} unit="Cr"
              info={data.basis.eac} subtext="Incurred + Committed + Balance" />
            <KPITile label="Variance" icon={Scale} size="supporting" infoAlign="right"
              value={total.variance === null ? '—' : `₹${cr(total.variance)}`} unit="Cr"
              tone={total.variance !== null && total.variance < -0.005 ? 'critical' : 'neutral'}
              info={data.basis.variance}
              subtext={total.variance === null ? 'Needs approved capex'
                : total.variance < -0.005 ? 'Over approved capex' : 'Within approved capex'} />
          </div>

          <Card pad="none" className="overflow-hidden">
            <div className="px-4 pt-3.5">
              <CardHeader
                icon={Table2}
                title="Cost breakdown by activity"
                eyebrow="INR Cr · dashed cells are editable · tick a company's WBS to count it on that line"
                right={
                  <div className="flex items-center gap-2">
                    {lineChanges > 0 ? (
                      <>
                        <span className="text-[11px] text-status-watch-fg">
                          {lineChanges} unsaved WBS change{lineChanges === 1 ? '' : 's'}
                        </span>
                        <button type="button" disabled={saving === 'settings'} onClick={() => setDraftLeft(data.settings.excluded)}
                          className="rounded-lg border border-border px-2.5 py-1 text-[12px] font-medium text-muted-foreground
                                     hover:bg-muted hover:text-foreground disabled:opacity-50">
                          Cancel
                        </button>
                        <button type="button" disabled={saving === 'settings'} onClick={() => { void saveSettings(draftLeft); }}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1 text-[12px] font-semibold
                                     text-primary-foreground hover:bg-primary/90 disabled:opacity-50
                                     focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">
                          {saving === 'settings' && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
                        </button>
                      </>
                    ) : data.settings.updatedAt ? (
                      <span className="text-[11px] text-muted-foreground">WBS choice saved {data.settings.updatedAt.slice(0, 10)}</span>
                    ) : null}
                    <button type="button"
                      onClick={() => setFolded(folded.size ? new Set() : new Set(data.rows.filter(hasSubs).map((r) => r.key)))}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-[12px] font-medium
                                 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground
                                 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">
                      {folded.size ? 'Show WBS lines' : 'Hide WBS lines'}
                    </button>
                    <button type="button" onClick={toggleHeaders} aria-pressed={showHeaders}
                      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[12px] font-medium transition-colors
                                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50
                                  ${showHeaders ? 'border-brand-purple/50 bg-brand-purple/10 text-foreground'
                                    : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground'}`}>
                      {showHeaders ? 'Hide headers' : 'Show headers'}
                    </button>
                    <ColumnsMenu cols={cols} />
                    <button onClick={load} disabled={loading}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-[12px] font-medium
                                 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50
                                 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">
                      <RefreshCcw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
                    </button>
                  </div>
                }
              />
            </div>

            {/* Fixed-height body: the table scrolls, the page does not. */}
            <div className="max-h-[62vh] overflow-auto custom-scrollbar border-t border-border">
              <table className="w-full min-w-[1200px] border-separate border-spacing-0 text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                    {visible.map((c) => (
                      <th key={c.key} scope="col"
                        className={`sticky top-0 z-10 border-b border-border bg-muted px-3 py-2.5 font-semibold ${c.cls}`}>
                        {c.key in COMPANY ? (
                          <span className="inline-flex items-center gap-1.5" title="Tick to count this company's WBS on that line">
                            <span className={`h-2 w-2 rounded-full ${COMPANY[c.key as Company].dot}`} />{c.label}
                          </span>
                        ) : c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.filter((r) => showHeaders || r.kind !== 'group').map((r) => {
                    const isTotal = r.kind === 'total';
                    const isGroup = r.kind === 'group';
                    const rowCls = isTotal ? 'bg-muted/70 font-semibold'
                      : isGroup ? 'bg-brand-purple/10 font-semibold text-brand-purple dark:text-foreground' : '';
                    const cell = `border-b border-border/60 ${isTotal ? 'border-t border-t-border' : ''}`;
                    const td = (c: ColKey) => {
                      switch (c) {
                        case 'sr':
                          if (isGroup) return null;   // the header label spans the Sr column
                          return <td key={c} className={`${cell} px-3 py-1.5 align-middle text-muted-foreground`}>{isTotal ? '' : r.sr}</td>;
                        case 'description':
                          if (r.sumOf.length) {
                            // Subtotal / total line: no WBS of its own, so the label runs
                            // across the WBS columns and names the lines it adds up.
                            const span = (isGroup ? 2 : 1) + visible.filter((v) => v.key in COMPANY).length;
                            return (
                              <td key={c} colSpan={span}
                                title={`${isTotal ? 'Total' : 'Subtotal'} of lines ${r.sumOf.join(', ')}`}
                                className={`${cell} px-3 py-1.5 align-middle ${isGroup ? 'border-l-2 border-l-brand-purple text-[12px] uppercase tracking-wide' : 'text-foreground'}`}>
                                {r.description}
                              </td>
                            );
                          }
                          return (
                            <td key={c} className={`${cell} px-3 py-1.5 align-middle text-foreground ${r.kind === 'item' && r.sr.includes('.') ? 'pl-7' : ''}`}>
                              {hasSubs(r) ? (
                                <button type="button" onClick={() => toggleFold(r.key)} aria-expanded={!folded.has(r.key)}
                                  className="-ml-1 inline-flex items-start gap-1 rounded px-1 text-left hover:bg-muted
                                             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">
                                  <ChevronRight className={`mt-[3px] h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform ${folded.has(r.key) ? '' : 'rotate-90'}`} />
                                  <span>{r.description}
                                    <span className="ml-1.5 text-[11px] font-normal text-muted-foreground">{r.subLines.length} WBS</span>
                                  </span>
                                </button>
                              ) : r.description}
                            </td>
                          );
                        case 'agel': case 'age6l': case 'spv': {
                          // A subtotal row has no WBS cells: its description spans them.
                          if (r.sumOf.length) return null;
                          return (
                            <td key={c} className={`${cell} px-1.5 py-1 align-middle`}>
                              <WbsToggle codes={r.wbs[c]} company={c} left={new Set(draftLeft[r.key] || [])}
                                savedLeft={new Set(r.excluded)} disabled={saving === 'settings'}
                                onSet={(count) => setLineCompany(r.key, r.wbs[c], count)} />
                            </td>
                          );
                        }
                        case 'approved':
                          return (
                            <td key={c} className={`${cell} px-1 py-1 text-right align-middle tabular-nums`}>
                              {r.editable.approved && !isTotal ? (
                                <div title={r.approvedSource ? `Source: ${r.approvedSource}` : 'Not set'}>
                                  <EditCell value={r.approved} numeric placeholder="—" label={`Approved capex, ${r.description}`}
                                    saving={saving === `${r.key}:approved`} onCommit={(v) => save(r, 'approved', v)} />
                                </div>
                              ) : <span className="px-2">{cr(r.approved)}</span>}
                            </td>
                          );
                        case 'incurred':
                          return <td key={c} className={`${cell} px-3 py-1.5 text-right align-middle tabular-nums`}>{cr(r.incurred)}</td>;
                        case 'committed':
                          return (
                            <td key={c} className={`${cell} px-3 py-1.5 text-right align-middle tabular-nums`}>
                              <CommittedValue row={r} />
                            </td>
                          );
                        case 'committedPOrd': case 'committedPReq': {
                          return (
                            <td key={c} className={`${cell} px-3 py-1.5 text-right align-middle tabular-nums text-muted-foreground`}>{cr(r[c])}</td>
                          );
                        }
                        case 'balance':
                          return (
                            <td key={c} className={`${cell} px-1 py-1 text-right align-middle tabular-nums`}>
                              {r.editable.balance ? (
                                <EditCell value={r.balance || null} numeric placeholder="0.00"
                                  label={`Balance to completion, ${r.description}`}
                                  saving={saving === `${r.key}:balance`} onCommit={(v) => save(r, 'balance', v)} />
                              ) : <span className="px-2">{cr(r.balance)}</span>}
                            </td>
                          );
                        case 'eac':
                          return <td key={c} className={`${cell} px-3 py-1.5 text-right align-middle font-medium tabular-nums`}>{cr(r.eac)}</td>;
                        case 'variance':
                          return (
                            <td key={c} className={`${cell} px-3 py-1.5 text-right align-middle tabular-nums ${r.variance !== null && r.variance < -0.005
                              ? 'text-status-critical-fg' : ''}`}>{cr(r.variance)}</td>
                          );
                        case 'remarks':
                          return (
                            <td key={c} className={`${cell} px-1 py-1 align-middle`}>
                              {!isTotal && (
                                <EditCell value={r.remarks} placeholder="Add remark" label={`Remarks, ${r.description}`}
                                  saving={saving === `${r.key}:remarks`} onCommit={(v) => save(r, 'remarks', v)} />
                              )}
                            </td>
                          );
                      }
                    };
                    const subTd = (sub: EACSubLine, c: ColKey) => {
                      const sc = 'border-b border-border/40 py-1 align-middle text-[12px]';
                      switch (c) {
                        case 'description':
                          return (
                            <td key={c} className={`${sc} pl-10 pr-3 text-muted-foreground`}>
                              <span className="text-foreground/80">{sub.name || 'Unnamed WBS'}</span>
                              <span className="ml-2 font-mono text-[10px] text-muted-foreground/70">{sub.suffix}</span>
                            </td>
                          );
                        case 'agel': case 'age6l': case 'spv':
                          return (
                            <td key={c} className={`${sc} px-1.5`}>
                              <WbsToggle codes={sub.wbs[c]} company={c} left={new Set(draftLeft[r.key] || [])}
                                savedLeft={new Set(r.excluded)} disabled={saving === 'settings'}
                                onSet={(count) => setLineCompany(r.key, sub.wbs[c], count)} />
                            </td>
                          );
                        case 'incurred':
                          return <td key={c} className={`${sc} px-3 text-right tabular-nums text-muted-foreground`}>{cr(sub.incurred)}</td>;
                        case 'committed':
                          return <td key={c} className={`${sc} px-3 text-right tabular-nums text-muted-foreground`}><CommittedValue row={sub} /></td>;
                        case 'committedPOrd': case 'committedPReq':
                          return <td key={c} className={`${sc} px-3 text-right tabular-nums text-muted-foreground`}>{cr(sub[c])}</td>;
                        case 'eac':
                          return <td key={c} className={`${sc} px-3 text-right tabular-nums text-muted-foreground`}>{cr(sub.eac)}</td>;
                        default:
                          return <td key={c} className={sc} />;
                      }
                    };
                    return (
                      <React.Fragment key={r.key}>
                        <tr className={`${rowCls} hover:bg-muted/40`}>
                          {visible.map((c) => td(c.key))}
                        </tr>
                        {hasSubs(r) && !folded.has(r.key) && r.subLines.map((sub) => (
                          <tr key={`${r.key}${sub.suffix}`} className="bg-background/40 hover:bg-muted/30">
                            {visible.map((c) => subTd(sub, c.key))}
                          </tr>
                        ))}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap gap-x-5 gap-y-1 border-t border-border px-4 py-2.5 text-[11px] text-muted-foreground">
              <span>Incurred: {src.incurred?.file || 'no CJI3 loaded'}{src.incurred?.loadedAt ? ` · loaded ${src.incurred.loadedAt.slice(0, 10)}` : ''}</span>
              <span>Committed: {src.committed?.file || 'no S_ALR_87013558 loaded'}{src.committed?.loadedAt ? ` · loaded ${src.committed.loadedAt.slice(0, 10)}` : ''}</span>
              <span>Approved Capex: project CAPEX sheet, editable</span>
            </div>
          </Card>
        </>
      )}
    </div>
  );
};

/* The EAC as an .xlsx in the approved format. EAC and Variance are written as
   Excel formulas on every row, so the file stays checkable in Excel. */
export async function exportEAC(data: EACData) {
  const ExcelJS = await import('exceljs');
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet(`EAC ${data.pss}`.slice(0, 31));
  ws.columns = [
    { header: 'Sr No', key: 'sr', width: 8 },
    { header: 'Description', key: 'description', width: 44 },
    { header: 'AGEL WBS', key: 'agel', width: 24 },
    { header: 'AGE6L WBS', key: 'age6l', width: 24 },
    { header: 'SPV WBS', key: 'spv', width: 24 },
    { header: 'Approved Capex (INR Cr)', key: 'approved', width: 16 },
    { header: 'Incurred (INR Cr)', key: 'incurred', width: 14 },
    // The commitment split sits beside its total, which is a formula over it.
    { header: 'Committed - POrd (INR Cr)', key: 'cpo', width: 15 },
    { header: 'Committed - PReq (INR Cr)', key: 'cpr', width: 15 },
    { header: 'Committed Total (INR Cr)', key: 'committed', width: 15 },
    { header: 'Balance to Completion (INR Cr)', key: 'balance', width: 18 },
    { header: 'EAC (INR Cr)', key: 'eac', width: 14 },
    { header: 'Variance wrt Approved (INR Cr)', key: 'variance', width: 18 },
    { header: 'EAC Remarks', key: 'remarks', width: 40 },
  ];
  ws.spliceRows(1, 0, [`Estimate at Completion · ${data.pss}`], [
    `Committed = POrd + PReq; EAC = Incurred + Committed + Balance to Completion; Variance = Approved Capex - EAC. `
    + `Incurred: ${data.sources.incurred?.file || '-'}; Committed: ${data.sources.committed?.file || '-'}. `
    + `WBS marked "(not counted)" are left out of that line.`]);
  const head = ws.getRow(3);
  head.font = { bold: true };
  head.alignment = { wrapText: true, vertical: 'middle' };
  ws.getRow(1).font = { bold: true, size: 13 };
  const mark = (r: EACRow, c: Company) =>
    r.wbs[c].map((w) => (r.excluded.includes(w) ? `${w} (not counted)` : w)).join(', ');
  data.rows.forEach((r) => {
    const row = ws.addRow({
      sr: r.kind === 'total' ? '' : r.sr, description: r.description,
      agel: mark(r, 'agel'), age6l: mark(r, 'age6l'), spv: mark(r, 'spv'),
      approved: r.approved, incurred: r.incurred, committed: r.committed, balance: r.balance,
      remarks: r.remarks || '', cpo: r.committedPOrd, cpr: r.committedPReq,
    });
    const n = row.number;
    // G Incurred, H POrd, I PReq, J Committed, K Balance, L EAC, F Approved.
    row.getCell('committed').value = { formula: `H${n}+I${n}`, result: r.committed };
    row.getCell('eac').value = { formula: `G${n}+J${n}+K${n}`, result: r.eac };
    row.getCell('variance').value = r.approved === null ? null : { formula: `F${n}-L${n}`, result: r.variance ?? 0 };
    ['approved', 'incurred', 'committed', 'balance', 'eac', 'variance', 'cpo', 'cpr'].forEach((k) => {
      row.getCell(k).numFmt = '#,##0.00';
    });
    if (r.kind !== 'item') row.font = { bold: true };
    // The line's WBS, one row each, named from SAP; Approved and Balance stay on the line.
    if (r.subLines.length > 1 || (r.key === 'L64' && r.subLines.length)) {
      r.subLines.forEach((sub) => {
        const sr2 = ws.addRow({
          sr: '', description: `    ${sub.name || 'Unnamed WBS'} (${sub.suffix})`,
          agel: sub.wbs.agel.join(', '), age6l: sub.wbs.age6l.join(', '), spv: sub.wbs.spv.join(', '),
          incurred: sub.incurred, cpo: sub.committedPOrd, cpr: sub.committedPReq,
        });
        const m = sr2.number;
        sr2.getCell('committed').value = { formula: `H${m}+I${m}`, result: sub.committed };
        sr2.getCell('eac').value = { formula: `G${m}+J${m}`, result: sub.eac };
        ['incurred', 'cpo', 'cpr', 'committed', 'eac'].forEach((k) => { sr2.getCell(k).numFmt = '#,##0.00'; });
        sr2.font = { italic: true, color: { argb: 'FF595959' } };
      });
    }
  });
  ws.views = [{ state: 'frozen', ySplit: 3 }];
  const buf = await wb.xlsx.writeBuffer();
  const url = URL.createObjectURL(new Blob([buf], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
  const a = document.createElement('a');
  a.href = url; a.download = `EAC_${data.pss.replace(/[^A-Za-z0-9]+/g, '_')}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}

export default EACView;
