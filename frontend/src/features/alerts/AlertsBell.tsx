/* The Alerts panel every dashboard carries: what Akasha has emailed this
   person. "Needs your action" = open alerts they are a To recipient of and
   have not acknowledged (approvals included); "Sent to you" = every email
   addressed to them, To or Cc. Each opens in Akasha, in the same template as
   the email: the alert or approval page, or the email itself. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Inbox } from 'lucide-react';
import { fmtWhen } from '../admin/adminApi';
import { LevelBadge } from './AlertDetail';
import { alertsApi } from './alertsApi';
import type { Inbox as InboxData } from './alertsApi';

const POLL_MS = 60_000;

export default function AlertsBell() {
  const [data, setData] = useState<InboxData | null>(null);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  const load = useCallback(() => { alertsApi.inbox().then(setData).catch(() => undefined); }, []);
  useEffect(() => {
    load();
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') load(); }, POLL_MS);
    window.addEventListener('focus', load);
    return () => { window.clearInterval(t); window.removeEventListener('focus', load); };
  }, [load]);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', away); document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', esc); };
  }, [open]);

  const n = data?.count ?? 0;
  return (
    <div className="relative" ref={box}>
      <button type="button" onClick={() => { setOpen(o => !o); if (!open) load(); }} aria-expanded={open} aria-haspopup="dialog"
        aria-label={n > 0 ? `Alerts sent to you: ${n} need your action` : 'Alerts sent to you'} title="Alerts and emails sent to you"
        className="relative rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
        <Inbox className="h-4 w-4" />
        {n > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[var(--status-critical-solid)] px-1 text-[9.5px] font-bold leading-none text-white tabular-nums">
            {n > 99 ? '99+' : n}
          </span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Alerts sent to you"
          className="absolute right-0 top-full z-[120] mt-2 w-[380px] max-w-[calc(100vw-24px)] overflow-hidden rounded-xl border border-border bg-card shadow-lg">
          <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
            <span className="text-[13px] font-semibold text-foreground">Alerts for you</span>
            <Link to="/alerts" onClick={() => setOpen(false)} className="text-[11.5px] font-medium text-primary hover:underline">View all</Link>
          </div>
          <div className="custom-scrollbar max-h-[68vh] overflow-y-auto">
            {data && data.email === null && (
              <p className="px-3.5 py-4 text-[12px] text-muted-foreground">Your account has no email address, so Akasha cannot show what is sent to you. Ask an administrator to add it.</p>
            )}
            {data && data.email !== null && (
              <>
                <p className="px-3.5 pb-1 pt-2.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">Needs your action ({data.action.length})</p>
                {data.action.length === 0
                  ? <p className="px-3.5 pb-2 text-[12px] text-muted-foreground">Nothing is waiting for you.</p>
                  : <ul>{data.action.map(a => (
                    <li key={a.id}>
                      <Link to={`/alerts/${a.id}`} onClick={() => setOpen(false)}
                        className="flex items-start gap-2 px-3.5 py-2 transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none">
                        <LevelBadge level={a.level} />
                        <span className="min-w-0 flex-1 leading-snug">
                          <span className="block truncate text-[12.5px] font-medium text-foreground">{a.kind === 'approval' ? 'Approval: ' : ''}{a.template_name}</span>
                          <span className="block truncate text-[11.5px] text-muted-foreground">{a.project_name || 'Akasha'}{a.phase ? ` · ${a.phase}` : ''}{a.due_date ? ` · due ${a.due_date}` : ''}</span>
                        </span>
                      </Link>
                    </li>
                  ))}</ul>}
                <p className="border-t border-border-subtle px-3.5 pb-1 pt-2.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">Sent to you</p>
                {data.recent.length === 0
                  ? <p className="px-3.5 pb-3 text-[12px] text-muted-foreground">No emails to you in the last 30 days.</p>
                  : <ul className="pb-1.5">{data.recent.map(m => (
                    <li key={m.log_id}>
                      <Link to={m.alert_id ? `/alerts/${m.alert_id}` : `/mail/${m.log_id}`} onClick={() => setOpen(false)}
                        className="flex items-start gap-2 px-3.5 py-2 transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none">
                        <span className="mt-0.5 w-6 shrink-0 text-center text-[10px] font-semibold uppercase text-muted-foreground">{m.role}</span>
                        <span className="min-w-0 flex-1 leading-snug">
                          <span className="block truncate text-[12.5px] text-foreground" title={m.subject ?? ''}>{m.subject}</span>
                          <span className="block truncate text-[11.5px] text-muted-foreground">{fmtWhen(m.at)}{m.level ? ` · L${m.level}` : ''}</span>
                        </span>
                      </Link>
                    </li>
                  ))}</ul>}
              </>
            )}
            {!data && <p className="px-3.5 py-4 text-[12px] text-muted-foreground">Loading…</p>}
          </div>
        </div>
      )}
    </div>
  );
}
