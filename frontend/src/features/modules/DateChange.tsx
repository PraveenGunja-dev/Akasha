/* LTA / SCOD change history in the Ordering Schedule (backend:
   services/date_history.py, sent on each row as `date_history`).

   A date that changed today is marked in brand blue - a change is news, not a
   problem, so it stays out of the reserved status colours (an LTA breach keeps
   its red). The history button opens every change: from what to what, by how
   many days, where it came from (transmission portal sync or an edit in
   Akasha), who, and when. Ordering is planned against these dates, so a move
   is never silent. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { History } from 'lucide-react';

export interface DateChangeEntry {
  from: string; to: string; days: number | null; source: string; by: string; at: string; at_ist: string; remarks?: string;
}
export interface DateHistory {
  lta: DateChangeEntry[]; scod: DateChangeEntry[];
  lta_changed_today: boolean; scod_changed_today: boolean;
}
type Field = 'lta' | 'scod';
const LABEL: Record<Field, string> = { lta: 'LTA', scod: 'SCOD' };

/** Classes for the date cell when the date changed today. */
export const changedTodayCell = 'bg-[color-mix(in_srgb,var(--brand-blue)_9%,transparent)] shadow-[inset_2px_0_0_var(--brand-blue)]';

export function changedToday(h: DateHistory | undefined, field: Field): boolean {
  return !!h?.[`${field}_changed_today` as const];
}

export function DateHistoryButton({ history, field, projectName }: { history?: DateHistory; field: Field; projectName: string }) {
  const entries = history?.[field] ?? [];
  const today = changedToday(history, field);
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  if (entries.length === 0) return null;
  return (
    <>
      <button ref={btn} type="button" onClick={e => { e.stopPropagation(); setOpen(o => !o); }}
        aria-haspopup="dialog" aria-expanded={open}
        aria-label={`${LABEL[field]} history for ${projectName}${today ? ' - changed today' : ''}`}
        title={today ? `${LABEL[field]} changed today - click for the history` : `${LABEL[field]} history`}
        className={`relative inline-flex shrink-0 items-center rounded p-0.5 transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-[var(--brand-blue)]
          ${today ? 'text-[var(--brand-blue)] hover:bg-[color-mix(in_srgb,var(--brand-blue)_14%,transparent)]' : 'text-fg-tertiary opacity-70 hover:opacity-100 hover:text-foreground'}`}>
        <History className="h-3 w-3" />
        {today && <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-[var(--brand-blue)]" aria-hidden />}
      </button>
      {open && btn.current && (
        <HistoryPopover anchor={btn.current} field={field} entries={entries} projectName={projectName} onClose={() => setOpen(false)} />
      )}
    </>
  );
}

function HistoryPopover({ anchor, field, entries, projectName, onClose }: {
  anchor: HTMLElement; field: Field; entries: DateChangeEntry[]; projectName: string; onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  useLayoutEffect(() => {
    const r = anchor.getBoundingClientRect();
    const w = 340, h = ref.current?.offsetHeight ?? 240;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    setPos({ left, top: r.bottom + 6 + h > window.innerHeight - 8 ? Math.max(8, r.top - h - 6) : r.bottom + 6 });
  }, [anchor]);
  useEffect(() => {
    const down = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node) && !anchor.contains(e.target as Node)) onClose(); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { onClose(); anchor.focus(); } };
    const scroll = (e: Event) => { if (!ref.current?.contains(e.target as Node)) onClose(); };
    document.addEventListener('mousedown', down);
    document.addEventListener('keydown', key);
    window.addEventListener('scroll', scroll, true);
    return () => {
      document.removeEventListener('mousedown', down);
      document.removeEventListener('keydown', key);
      window.removeEventListener('scroll', scroll, true);
    };
  }, [anchor, onClose]);

  return createPortal(
    <div ref={ref} role="dialog" aria-label={`${LABEL[field]} history`}
      style={{ position: 'fixed', top: pos?.top ?? -9999, left: pos?.left ?? -9999, width: 340 }}
      className="z-[200] rounded-lg border border-border bg-card p-3 text-left shadow-lg" onClick={e => e.stopPropagation()}>
      <div className="mb-2">
        <div className="text-[12px] font-semibold text-fg-primary">{LABEL[field]} history</div>
        <div className="truncate text-[10.5px] text-fg-tertiary" title={projectName}>{projectName}</div>
      </div>
      <ol className="max-h-[260px] space-y-2 overflow-auto pr-1">
        {entries.map((e, i) => (
          <li key={`${e.at}-${i}`} className="border-l-2 pl-2.5" style={{ borderColor: i === 0 ? 'var(--brand-blue)' : 'var(--border-subtle)' }}>
            <div className="flex items-baseline justify-between gap-2 text-[11.5px]">
              <span className="tabular-nums text-fg-primary">
                <span className="text-fg-tertiary">{e.from || 'none'}</span> → <b>{e.to || 'removed'}</b>
              </span>
              {e.days != null && e.days !== 0 && (
                <span className={`shrink-0 text-[10.5px] font-semibold tabular-nums ${e.days > 0 ? 'text-[var(--status-risk-fg)]' : 'text-[var(--status-healthy-fg)]'}`}>
                  {e.days > 0 ? '+' : ''}{e.days} d
                </span>
              )}
            </div>
            <div className="mt-0.5 text-[10.5px] text-fg-tertiary">{e.source}{e.by && e.by !== 'sync' ? ` · ${e.by}` : ''} · {e.at_ist}</div>
            {e.remarks && <div className="mt-0.5 text-[10.5px] italic text-fg-secondary">“{e.remarks}”</div>}
          </li>
        ))}
      </ol>
      <p className="mt-2 border-t border-border-subtle pt-2 text-[10px] leading-snug text-fg-tertiary">
        {field === 'lta' ? 'LTA is the latest ECOD across the project’s blocks in the transmission portal (Project Blocks).'
          : 'SCOD is the latest SCOD across the project’s blocks in the transmission portal (Project Blocks).'} It is refreshed on every transmission sync.
      </p>
    </div>,
    document.body,
  );
}
