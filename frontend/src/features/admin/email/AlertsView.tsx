/* Alerts - every alert Akasha is following: the level it has been emailed
   up to, whether a To recipient has acknowledged it (who, when, the expected
   date), what happens next, and why it closed. Opens one alert with its
   recipients and timeline; an administrator can record an acknowledgement
   given outside Akasha. */
import { useCallback, useEffect, useState } from 'react';
import { Download, Search } from 'lucide-react';
import { Dialog, Loader, StatusPill, cx } from '../../../components/ui/primitives';
import { btn, field, fmtWhen } from '../adminApi';
import AlertDetail, { LevelBadge, alertState } from '../../alerts/AlertDetail';
import { alertsApi, fmtDay } from '../../alerts/alertsApi';
import type { Alert, AlertDetailData } from '../../alerts/alertsApi';
import { emailApi } from './emailApi';
import type { AlertFilters, AlertList } from './emailApi';

/** Acknowledgement in two colours: green = acknowledged, amber = waiting. */
export function AckMark({ acknowledged }: { acknowledged: boolean }) {
  return (
    <span aria-hidden className={cx('inline-block h-2 w-2 shrink-0 rounded-full',
      acknowledged ? 'bg-[var(--status-healthy-solid)]' : 'bg-[var(--status-watch-solid)]')} />
  );
}

export function AlertsTable({ rows, onOpen, showTemplate = true }: { rows: Alert[]; onOpen: (id: number) => void; showTemplate?: boolean }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[820px] text-[12px]">
        <thead className="border-b border-border bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold">
            <th>Project · phase</th>{showTemplate && <th>Latest email</th>}<th>Level</th><th>Acknowledged</th><th>Expected</th><th>Status · next</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(a => {
            const st = alertState(a);
            const acked = a.recipients.filter(r => r.acknowledged_at).length;
            return (
              <tr key={a.id} tabIndex={0} onClick={() => onOpen(a.id)} onKeyDown={e => { if (e.key === 'Enter') onOpen(a.id); }}
                className="cursor-pointer border-b border-[var(--border-subtle)] align-top last:border-0 hover:bg-[var(--surface-sunken)] focus-visible:bg-[var(--surface-sunken)] focus-visible:outline-none">
                <td className="px-3 py-2">
                  <span className="font-semibold text-foreground">{a.project_name || '—'}</span>
                  <span className="block text-[11px] text-muted-foreground">{[a.phase, a.due_date && `ordering ${a.due_date}`].filter(Boolean).join(' · ') || ' '}</span>
                </td>
                {showTemplate && <td className="px-3 py-2 text-muted-foreground">{a.template_name}<span className="block text-[11px]">{a.emails} email{a.emails === 1 ? '' : 's'} · {fmtWhen(a.last_sent_at)}</span></td>}
                <td className="px-3 py-2"><LevelBadge level={a.level} /></td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1.5">
                    <AckMark acknowledged={!!a.acknowledged_at} />
                    {a.acknowledged_at
                      ? <span className="text-foreground">{a.acknowledged_by}</span>
                      : <span className="text-muted-foreground">Not yet</span>}
                  </span>
                  <span className="block pl-3.5 text-[11px] text-muted-foreground">
                    {a.acknowledged_at ? `${fmtWhen(a.acknowledged_at)} · at L${a.ack_level ?? a.level}` : `${acked} of ${a.recipients.length} To`}
                  </span>
                </td>
                <td className={cx('whitespace-nowrap px-3 py-2 tabular-nums', a.late_commitment ? 'text-[var(--status-risk-fg)]' : 'text-muted-foreground')}>
                  {a.expected_date ? fmtDay(a.expected_date) : '—'}
                </td>
                <td className="max-w-[300px] px-3 py-2">
                  <StatusPill tone={st.tone}>{st.label}</StatusPill>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">{a.status === 'resolved' ? a.resolved_reason : a.next_step}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** One alert in a dialog, refreshed after an acknowledgement. */
export function AlertDialog({ id, onClose, onChanged }: { id: number | null; onClose: () => void; onChanged?: () => void }) {
  const [data, setData] = useState<AlertDetailData | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    setData(null); setError('');
    if (id != null) alertsApi.get(id).then(setData).catch(e => setError((e as Error).message));
  }, [id]);
  return (
    <Dialog open={id != null} onClose={onClose} size="lg" title={`Alert #${id ?? ''}`}
      footer={<button type="button" className={btn.secondary} onClick={onClose}>Close</button>}>
      {error ? <p role="alert" className="text-[12.5px] text-[var(--status-critical-fg)]">{error}</p>
        : !data ? <div className="flex justify-center py-8"><Loader size="md" label="Loading…" /></div>
          : <AlertDetail data={data} onChange={d => { setData(d); onChanged?.(); }} />}
    </Dialog>
  );
}

const ACK_CHIPS: { id: '' | 'awaiting' | 'acknowledged'; label: string }[] = [
  { id: '', label: 'All open' }, { id: 'awaiting', label: 'Awaiting acknowledgement' }, { id: 'acknowledged', label: 'Acknowledged' },
];

export default function AlertsView() {
  const [f, setF] = useState<AlertFilters>({ status: 'open', ack: '' });
  const [q, setQ] = useState('');
  const [data, setData] = useState<AlertList | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<number | null>(null);

  const load = useCallback(() => {
    emailApi.alerts({ ...f, q: q.trim() || undefined }).then(setData).catch(e => setError((e as Error).message));
  }, [f, q]);
  useEffect(() => { const t = window.setTimeout(load, q ? 300 : 0); return () => window.clearTimeout(t); }, [load, q]);

  const c = data?.counts;
  const closed = f.status === 'resolved';
  return (
    <div className="space-y-3">
      <p className="max-w-3xl text-[12.5px] text-muted-foreground">
        Every alert that asks its To recipients to acknowledge. Module ordering climbs a level per reminder (30 days L1, 15 days L2, 7 days L3);
        an acknowledgement with an expected date on or before the ordering date holds it at its level. Alerts close on their own when the PO is in SAP.
        {data?.test_mode && ' Showing test-mode alerts.'}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <div role="tablist" aria-label="Acknowledgement" className="inline-flex flex-wrap rounded-lg border border-border p-0.5">
          {ACK_CHIPS.map(ch => {
            const on = !closed && (f.ack ?? '') === ch.id;
            const n = ch.id === 'awaiting' ? c?.awaiting : ch.id === 'acknowledged' ? c?.acknowledged : c?.open;
            return (
              <button key={ch.id || 'all'} type="button" role="tab" aria-selected={on} onClick={() => setF({ ...f, status: 'open', ack: ch.id })}
                className={cx('inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
                  on ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground')}>
                {ch.id && <AckMark acknowledged={ch.id === 'acknowledged'} />}{ch.label}<span className="tabular-nums text-muted-foreground">{n ?? ''}</span>
              </button>
            );
          })}
          <button type="button" role="tab" aria-selected={closed} onClick={() => setF({ ...f, status: 'resolved', ack: '' })}
            className={cx('rounded-md px-2.5 py-1 text-[12px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
              closed ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground')}>
            Closed <span className="tabular-nums text-muted-foreground">{c?.resolved ?? ''}</span>
          </button>
        </div>
        <select aria-label="Filter by level" className={`${field.replace('w-full ', '')} w-auto py-1.5 text-[12px]`}
          value={f.level ?? 0} onChange={e => setF({ ...f, level: Number(e.target.value) || undefined })}>
          <option value={0}>All levels</option>
          {([1, 2, 3] as const).map(l => <option key={l} value={l}>L{l}{c && !closed ? ` (${c.by_level[String(l) as '1' | '2' | '3'] ?? 0} open)` : ''}</option>)}
        </select>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input aria-label="Search alerts" className={`${field.replace('w-full ', '')} w-56 py-1.5 pl-8 text-[12px]`} value={q}
            placeholder="Project, phase or person" onChange={e => setQ(e.target.value)} />
        </div>
        <button type="button" className={`${btn.secondary} ml-auto`} onClick={() => emailApi.exportAlerts({ ...f, q: q.trim() || undefined }).catch(e => setError((e as Error).message))}>
          <Download className="h-3.5 w-3.5" />Export
        </button>
      </div>
      {error && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}
      {!data ? <div className="flex justify-center py-10"><Loader size="md" label="Loading alerts…" /></div>
        : data.alerts.length === 0
          ? <p className="bento-card px-4 py-10 text-center text-[12.5px] text-muted-foreground">{closed ? 'No closed alerts yet.' : 'No open alerts match.'}</p>
          : <AlertsTable rows={data.alerts} onOpen={setOpen} />}
      {data && data.total > data.alerts.length && <p className="text-[11.5px] text-muted-foreground">Showing the latest {data.alerts.length} of {data.total} - narrow the filters or export them all.</p>}
      <AlertDialog id={open} onClose={() => setOpen(null)} onChanged={load} />
    </div>
  );
}
