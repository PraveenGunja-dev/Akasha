import React from 'react';
import { Trash2, ListChecks } from 'lucide-react';
import Drawer from './Drawer';
import { useCapacityActions } from './useCapacityActions';
import type { ActionStatus } from './types';
import { cx } from '../../components/ui/primitives/cx';

/* ═══════════════════════════════════════════════════════════════════════════
   TRACKED ACTIONS — what "Take action" / "Track" actually produced.

   Status is a real transition, persisted, and reflected everywhere the store
   is read. Without this drawer those buttons would have nowhere to lead, which
   is the definition of the fake interaction this rebuild set out to remove.
   ═══════════════════════════════════════════════════════════════════════════ */

const STATUSES: ActionStatus[] = ['Open', 'In Progress', 'Blocked', 'Completed', 'Dismissed'];

const STATUS_CHIP: Record<ActionStatus, string> = {
  Open: 'bg-status-done-bg text-status-done-fg border-status-done-border',
  'In Progress': 'bg-status-watch-bg text-status-watch-fg border-status-watch-border',
  Blocked: 'bg-status-critical-bg text-status-critical-fg border-status-critical-border',
  Completed: 'bg-status-healthy-bg text-status-healthy-fg border-status-healthy-border',
  Dismissed: 'bg-muted text-fg-tertiary border-border',
};

const PRIORITY_CHIP: Record<string, string> = {
  High: 'text-status-critical-fg',
  Medium: 'text-status-watch-fg',
  Low: 'text-fg-tertiary',
};

export default function ActionsDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { actions, setStatus, removeAction } = useCapacityActions();
  const live = actions.filter((a) => a.status !== 'Dismissed');

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="max-w-2xl"
      title="Tracked actions"
      subtitle={`${live.length} active · ${actions.length} total`}
    >
      {actions.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border py-14 text-center">
          <ListChecks className="mx-auto mb-2 h-6 w-6 text-fg-tertiary" />
          <p className="text-[12px] font-semibold text-fg-secondary">No actions tracked yet</p>
          <p className="mx-auto mt-1 max-w-xs text-[11px] leading-relaxed text-fg-tertiary">
            Use <strong>Take action</strong> on a risk, or <strong>Create action</strong> from an insight, and
            it will appear here with an owner and a due date.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {actions.map((a) => (
            <li key={a.id} className="rounded-xl border border-border bg-card p-3">
              <div className="mb-1.5 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[12.5px] font-bold leading-snug text-foreground">{a.title}</p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-fg-tertiary">{a.description}</p>
                </div>
                <button
                  onClick={() => removeAction(a.id)}
                  aria-label={`Delete action: ${a.title}`}
                  className="shrink-0 rounded-md p-1 text-fg-tertiary transition-colors hover:bg-status-critical-bg hover:text-status-critical-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-fg-tertiary">
                <span className={cx('font-bold', PRIORITY_CHIP[a.priority])}>{a.priority} priority</span>
                <span>Owner: <strong className="text-fg-secondary">{a.owner}</strong></span>
                <span>Due {a.dueDate}</span>
                {a.affectedMW > 0 && <span>{a.affectedMW.toFixed(1)} MW affected</span>}
                {a.affectedProjects.length > 0 && <span>{a.affectedProjects.length} projects</span>}
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                {STATUSES.map((s) => (
                  <button
                    key={s}
                    onClick={() => setStatus(a.id, s)}
                    aria-pressed={a.status === s}
                    className={cx(
                      'rounded-full border px-2 py-0.5 text-[10px] font-semibold transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                      a.status === s
                        ? STATUS_CHIP[s] + ' ring-1 ring-inset ring-current/20'
                        : 'border-border text-fg-tertiary hover:bg-muted',
                    )}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Drawer>
  );
}
