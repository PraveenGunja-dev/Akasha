/* ── BESS EAC (Estimate at Completion), a view inside the project's SAP tab ──
   The approved EAC format, one project at a time. Approved Capex, Balance to
   Completion and Remarks are edited in place and saved on leaving the cell;
   Incurred and Committed come from SAP; EAC and Variance are formulas.
   Everything is computed server-side (services/bess_eac.py) so the screen and
   the export can never disagree. */
import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, AlertTriangle, RefreshCcw, Landmark, Receipt, FileSignature, Calculator, Scale, Table2 } from 'lucide-react';
import { Card, CardHeader, KPITile } from '../../components/ui/primitives';

const API = '/akasha/api/bess';

type Kind = 'item' | 'group' | 'total';
export interface EACRow {
  key: string; sr: string; description: string; kind: Kind;
  wbs: { agel: string[]; age6l: string[]; spv: string[] };
  approved: number | null; approvedSource: string | null;
  incurred: number; committed: number; balance: number;
  eac: number; variance: number | null; remarks: string | null;
  editable: { approved: boolean; balance: boolean; remarks: boolean };
}
export interface EACData {
  projectId: string; pss: string; rows: EACRow[];
  sources: Record<string, { file: string; loadedAt: string | null }>;
  basis: Record<string, string>;
}
type Field = 'approved' | 'balance' | 'remarks';

/* Two decimals, Indian grouping; a value that rounds to zero reads 0.00, never -0.00. */
export const cr = (v: number | null | undefined) =>
  v === null || v === undefined ? '—'
    : (Math.abs(v) < 0.005 ? 0 : v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const HEADERS: [string, string][] = [
  ['Sr', 'w-14'], ['Description', ''], ['WBS', 'w-44'],
  ['Approved Capex', 'w-32 text-right'], ['Incurred', 'w-28 text-right'],
  ['Committed', 'w-28 text-right'], ['Balance to Completion', 'w-32 text-right'],
  ['EAC', 'w-28 text-right'], ['Variance', 'w-28 text-right'], ['EAC Remarks', 'w-64'],
];

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

  return { data, loading, error, saving, load, save };
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
  const { data, loading, error, saving, load, save } = eac;
  const total = data?.rows.find((r) => r.key === 'L63');
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
              info={data.basis.committed} subtext={src.committed?.file || 'No S_ALR loaded'} />
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
                eyebrow="INR Cr · dashed cells are editable"
                right={
                  <button onClick={load} disabled={loading}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-[12px] font-medium
                               text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50
                               focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">
                    <RefreshCcw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
                  </button>
                }
              />
            </div>

            {/* Fixed-height body: the table scrolls, the page does not. */}
            <div className="max-h-[62vh] overflow-auto custom-scrollbar border-t border-border">
              <table className="w-full min-w-[1200px] border-separate border-spacing-0 text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                    {HEADERS.map(([h, w]) => (
                      <th key={h} scope="col"
                        className={`sticky top-0 z-10 border-b border-border bg-muted px-3 py-2.5 font-semibold ${w}`}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => {
                    const isTotal = r.kind === 'total';
                    const isGroup = r.kind === 'group';
                    const wbs = [...r.wbs.agel, ...r.wbs.age6l, ...r.wbs.spv];
                    const rowCls = isTotal ? 'bg-muted/70 font-semibold' : isGroup ? 'bg-muted/30 font-semibold' : '';
                    const cell = `border-b border-border/60 ${isTotal ? 'border-t border-t-border' : ''}`;
                    return (
                      <tr key={r.key} className={`${rowCls} hover:bg-muted/40`}>
                        <td className={`${cell} px-3 py-1.5 align-middle text-muted-foreground`}>{isTotal ? '' : r.sr}</td>
                        <td className={`${cell} px-3 py-1.5 align-middle text-foreground ${r.kind === 'item' && r.sr.includes('.') ? 'pl-7' : ''}`}>
                          {r.description}
                        </td>
                        <td className={`${cell} px-3 py-1.5 align-middle`}>
                          {wbs.length > 0 && (
                            <span title={wbs.join('\n')} className="block truncate font-mono text-[11px] text-muted-foreground">
                              {wbs[0]}{wbs.length > 1 ? ` +${wbs.length - 1}` : ''}
                            </span>
                          )}
                        </td>
                        <td className={`${cell} px-1 py-1 text-right align-middle tabular-nums`}>
                          {r.editable.approved && !isTotal ? (
                            <div title={r.approvedSource ? `Source: ${r.approvedSource}` : 'Not set'}>
                              <EditCell value={r.approved} numeric placeholder="—" label={`Approved capex, ${r.description}`}
                                saving={saving === `${r.key}:approved`} onCommit={(v) => save(r, 'approved', v)} />
                            </div>
                          ) : <span className="px-2">{cr(r.approved)}</span>}
                        </td>
                        <td className={`${cell} px-3 py-1.5 text-right align-middle tabular-nums`}>{cr(r.incurred)}</td>
                        <td className={`${cell} px-3 py-1.5 text-right align-middle tabular-nums`}>{cr(r.committed)}</td>
                        <td className={`${cell} px-1 py-1 text-right align-middle tabular-nums`}>
                          {r.editable.balance ? (
                            <EditCell value={r.balance || null} numeric placeholder="0.00"
                              label={`Balance to completion, ${r.description}`}
                              saving={saving === `${r.key}:balance`} onCommit={(v) => save(r, 'balance', v)} />
                          ) : <span className="px-2">{cr(r.balance)}</span>}
                        </td>
                        <td className={`${cell} px-3 py-1.5 text-right align-middle font-medium tabular-nums`}>{cr(r.eac)}</td>
                        <td className={`${cell} px-3 py-1.5 text-right align-middle tabular-nums ${r.variance !== null && r.variance < -0.005
                          ? 'text-status-critical-fg' : ''}`}>{cr(r.variance)}</td>
                        <td className={`${cell} px-1 py-1 align-middle`}>
                          {!isTotal && (
                            <EditCell value={r.remarks} placeholder="Add remark" label={`Remarks, ${r.description}`}
                              saving={saving === `${r.key}:remarks`} onCommit={(v) => save(r, 'remarks', v)} />
                          )}
                        </td>
                      </tr>
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
    { header: 'Committed (INR Cr)', key: 'committed', width: 14 },
    { header: 'Balance to Completion (INR Cr)', key: 'balance', width: 18 },
    { header: 'EAC (INR Cr)', key: 'eac', width: 14 },
    { header: 'Variance wrt Approved (INR Cr)', key: 'variance', width: 18 },
    { header: 'EAC Remarks', key: 'remarks', width: 40 },
  ];
  ws.spliceRows(1, 0, [`Estimate at Completion · ${data.pss}`], [
    `EAC = Incurred + Committed + Balance to Completion; Variance = Approved Capex - EAC. `
    + `Incurred: ${data.sources.incurred?.file || '-'}; Committed: ${data.sources.committed?.file || '-'}.`]);
  const head = ws.getRow(3);
  head.font = { bold: true };
  head.alignment = { wrapText: true, vertical: 'middle' };
  ws.getRow(1).font = { bold: true, size: 13 };
  data.rows.forEach((r) => {
    const row = ws.addRow({
      sr: r.kind === 'total' ? '' : r.sr, description: r.description,
      agel: r.wbs.agel.join(', '), age6l: r.wbs.age6l.join(', '), spv: r.wbs.spv.join(', '),
      approved: r.approved, incurred: r.incurred, committed: r.committed, balance: r.balance,
      remarks: r.remarks || '',
    });
    const n = row.number;
    row.getCell('eac').value = { formula: `G${n}+H${n}+I${n}`, result: r.eac };
    row.getCell('variance').value = r.approved === null ? null : { formula: `F${n}-J${n}`, result: r.variance ?? 0 };
    ['approved', 'incurred', 'committed', 'balance', 'eac', 'variance'].forEach((k) => {
      row.getCell(k).numFmt = '#,##0.00';
    });
    if (r.kind !== 'item') row.font = { bold: true };
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
