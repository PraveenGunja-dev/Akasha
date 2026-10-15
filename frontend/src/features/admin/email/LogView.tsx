/* The email log: every email Akasha produced, filterable by date, status,
   template and project; each opens as it was sent, can be resent, and the
   filtered log exports to CSV. */
import { useCallback, useEffect, useState } from 'react';
import { Download, Paperclip, RefreshCw, Search } from 'lucide-react';
import { Dialog, StatusPill } from '../../../components/ui/primitives';
import { btn, field, fmtWhen } from '../adminApi';
import { emailApi, STATUS_META } from './emailApi';
import type { EmailTemplate, LogEntry, LogFilters, LogStatus } from './emailApi';

const PAGE = 100;
const STATUSES: LogStatus[] = ['sent', 'test', 'failed', 'no_recipients', 'baseline'];
const day = (offset: number) => { const d = new Date(); d.setDate(d.getDate() + offset); return d.toISOString().slice(0, 10); };

export default function LogView() {
  const [from, setFrom] = useState(day(-30));
  const [to, setTo] = useState(day(0));
  const [status, setStatus] = useState('');
  const [template, setTemplate] = useState('');
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [rows, setRows] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [byStatus, setByStatus] = useState<Partial<Record<LogStatus, number>>>({});
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [open, setOpen] = useState<(LogEntry & { html: string; event_key: string }) | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');

  useEffect(() => { emailApi.templates().then(setTemplates).catch(() => undefined); }, []);
  useEffect(() => { const t = window.setTimeout(() => setDebounced(q.trim()), 300); return () => window.clearTimeout(t); }, [q]);

  // Dates are local calendar days; the server compares in UTC.
  const filters = useCallback((): LogFilters => ({
    since: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
    until: to ? new Date(new Date(`${to}T00:00:00`).getTime() + 86400000).toISOString() : undefined,
    status, template, q: debounced,
  }), [from, to, status, template, debounced]);

  const load = useCallback(async (offset = 0) => {
    setLoading(true); setError('');
    try {
      const r = await emailApi.log({ ...filters(), limit: PAGE, offset });
      setTotal(r.total); setByStatus(r.by_status);
      setRows(prev => (offset ? [...prev, ...r.entries] : r.entries));
    } catch (e) {
      setError((e as Error).message);
    } finally { setLoading(false); }
  }, [filters]);
  useEffect(() => { load(0); }, [load]);

  const name = (k: string) => templates.find(t => t.key === k)?.name ?? k;
  const resend = async (id: number) => {
    setNote('');
    try {
      const r = await emailApi.resend(id);
      setNote(r.status === 'failed' ? `Resend failed: ${r.detail}` : `Resent (${r.status})`);
      load(0);
    } catch (e) { setNote((e as Error).message); }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] font-medium text-muted-foreground">From
          <input type="date" className={`${field} mt-0.5 w-auto py-1.5 text-[12px]`} value={from} max={to} onChange={e => setFrom(e.target.value)} />
        </label>
        <label className="text-[11px] font-medium text-muted-foreground">To
          <input type="date" className={`${field} mt-0.5 w-auto py-1.5 text-[12px]`} value={to} min={from} onChange={e => setTo(e.target.value)} />
        </label>
        <label className="text-[11px] font-medium text-muted-foreground">Status
          <select className={`${field} mt-0.5 w-auto py-1.5 text-[12px]`} value={status} onChange={e => setStatus(e.target.value)}>
            <option value="">All</option>
            {STATUSES.map(s => <option key={s} value={s}>{STATUS_META[s].label}</option>)}
          </select>
        </label>
        <label className="text-[11px] font-medium text-muted-foreground">Template
          <select className={`${field} mt-0.5 w-auto max-w-[220px] py-1.5 text-[12px]`} value={template} onChange={e => setTemplate(e.target.value)}>
            <option value="">All</option>
            {templates.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}
          </select>
        </label>
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input aria-label="Search project or subject" className={`${field} py-1.5 pl-8 text-[12px]`} value={q} onChange={e => setQ(e.target.value)} placeholder="Project or subject" />
        </div>
        <button type="button" className={btn.secondary} onClick={() => emailApi.exportLog(filters()).catch(e => setError((e as Error).message))}>
          <Download className="h-3.5 w-3.5" />Export CSV
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {STATUSES.filter(s => byStatus[s]).map(s => (
          <button key={s} type="button" onClick={() => setStatus(status === s ? '' : s)} aria-pressed={status === s}
            className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
            <StatusPill tone={STATUS_META[s].tone}>{STATUS_META[s].label} · {byStatus[s]}</StatusPill>
          </button>
        ))}
      </div>
      {error && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}

      <div className="bento-card overflow-x-auto p-0">
        <table className="w-full min-w-[900px] text-[12px]">
          <thead className="border-b border-border bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold"><th>When</th><th>Status</th><th>Email</th><th>Project</th><th>Recipients</th><th>By</th></tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id} tabIndex={0} onClick={() => emailApi.logEntry(r.id).then(setOpen).catch(e => setError((e as Error).message))}
                onKeyDown={e => { if (e.key === 'Enter') emailApi.logEntry(r.id).then(setOpen).catch(() => undefined); }}
                className="cursor-pointer border-b border-[var(--border-subtle)] align-top last:border-0 hover:bg-[var(--surface-sunken)] focus-visible:bg-[var(--surface-sunken)] focus-visible:outline-none">
                <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted-foreground">{fmtWhen(r.at)}</td>
                <td className="whitespace-nowrap px-3 py-2"><StatusPill tone={(STATUS_META[r.status] ?? STATUS_META.error).tone}>{(STATUS_META[r.status] ?? { label: r.status }).label}</StatusPill>
                  {r.attempts > 1 && <span className="ml-1 text-[10.5px] text-muted-foreground">try {r.attempts}</span>}</td>
                <td className="max-w-[360px] px-3 py-2">
                  <span className="text-foreground">{r.subject ?? name(r.template_key)}</span>
                  <span className="block text-[11px] text-muted-foreground">{name(r.template_key)}{r.template_version ? ` · v${r.template_version}` : ''}
                    {r.attachments.length > 0 && <> · <Paperclip className="inline h-3 w-3" /> {r.attachments.length}</>}</span>
                  {r.detail && <span className="block text-[11px] text-[var(--status-watch-fg)]">{r.detail}</span>}
                </td>
                <td className="px-3 py-2">{r.project_name ?? '—'}{r.phase && <span className="block text-[11px] text-muted-foreground">{r.phase}</span>}</td>
                <td className="px-3 py-2 text-muted-foreground">{r.to.length + r.cc.length > 0 ? `${r.to.length} to · ${r.cc.length} cc` : '—'}</td>
                <td className="px-3 py-2 text-muted-foreground">{r.triggered_by ?? ''}</td>
              </tr>
            ))}
            {!loading && rows.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">No emails match.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Showing {rows.length.toLocaleString('en-IN')} of {total.toLocaleString('en-IN')} · times in your local zone</span>
        {rows.length < total && <button type="button" className={btn.secondary} disabled={loading} onClick={() => load(rows.length)}>{loading ? 'Loading…' : 'Load more'}</button>}
      </div>

      <Dialog open={!!open} onClose={() => { setOpen(null); setNote(''); }} size="lg" title={open?.subject ?? 'Email'}
        description={open ? `${fmtWhen(open.at)} · ${name(open.template_key)}${open.template_version ? ` v${open.template_version}` : ''} · ${open.triggered_by ?? ''}` : ''}
        footer={<>{note && <span className="mr-auto text-[12px] text-muted-foreground">{note}</span>}
          {open && ['sent', 'test', 'failed'].includes(open.status) && (
            <button type="button" className={btn.secondary} onClick={() => resend(open.id)}><RefreshCw className="h-3.5 w-3.5" />Resend</button>)}
          <button type="button" className={btn.secondary} onClick={() => setOpen(null)}>Close</button></>}>
        {open && (
          <div className="space-y-2 text-[12px]">
            <p><span className="text-muted-foreground">To:</span> {open.to.join(', ') || '—'}</p>
            {open.cc.length > 0 && <p><span className="text-muted-foreground">Cc:</span> {open.cc.join(', ')}</p>}
            {open.attachments.length > 0 && <p><span className="text-muted-foreground">Attached:</span> {open.attachments.join(', ')}</p>}
            {open.detail && <p className="text-[var(--status-watch-fg)]">{open.detail}</p>}
            {open.html
              ? <iframe title="Email as sent" sandbox="" srcDoc={open.html} className="h-[520px] w-full rounded-lg border border-border bg-white" />
              : <p className="text-muted-foreground">No message body - this alert was recorded without sending.</p>}
          </div>
        )}
      </Dialog>
    </div>
  );
}
