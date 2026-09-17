import React from 'react';
import { Database, Sparkles, Download, Bookmark } from 'lucide-react';
import { useOverview } from '../hooks';
import { useSAPStore } from '../store';
import { fmtDateTime, relativeAge } from '../format';
import { Btn } from './Drawer';
import { StatusDot } from '../../../components/ui/primitives';

/* Page header: what this is, whether the data is current, and the two
   actions that apply to the whole page. Connection state is derived from the
   data itself — the newest ZSPS upload_time — not from a flag. */
export const SAPHeader = ({ onExport }: { onExport: () => void }) => {
  const { data, error, loading } = useOverview();
  const openDrawer = useSAPStore(s => s.openDrawer);
  const watchCount = useSAPStore(s => s.watchlist.length);

  // A daily feed: judge freshness on the data's own date, and call it delayed
  // once a day has clearly been missed. Falls back to pull time before the
  // first logged sync.
  const asOn = data?.data_as_on ?? data?.synced_at;
  const age = relativeAge(asOn, 36);
  const failed = data?.sync?.last_status === 'failed';
  const state: { tone: 'healthy' | 'watch' | 'critical' | 'neutral'; label: string } =
    error ? { tone: 'critical', label: 'SAP unavailable' }
      : loading && !data ? { tone: 'neutral', label: 'Connecting…' }
        : failed ? { tone: 'critical', label: 'Last SharePoint sync failed' }
          : age.stale ? { tone: 'watch', label: 'SAP data delayed' }
            : { tone: 'healthy', label: 'SAP current' };

  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-1">
          <Database className="h-4 w-4 text-fg-tertiary" strokeWidth={1.5} />
        </div>
        <div>
          <h1 className="text-[20px] font-semibold leading-tight tracking-[-0.01em] text-fg-primary">SAP Intelligence</h1>
          <p className="mt-0.5 text-[13px] text-fg-secondary">End-to-end visibility of procurement, materials and inventory from SAP</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-fg-tertiary" aria-live="polite">
            <span className="inline-flex items-center gap-1.5"><StatusDot tone={state.tone} /> <span className="text-fg-secondary">{state.label}</span></span>
            {asOn && (
              <span title={data?.sync?.files?.length ? data.sync.files.map(f => `${f.name} · ${fmtDateTime(f.modified)}`).join(' | ') : undefined}>
                Data as on <span className="font-medium text-fg-secondary">{fmtDateTime(asOn)}</span> <span className="opacity-70">({age.label})</span>
              </span>
            )}
            {failed && data?.sync?.last_message && (
              <span className="text-status-critical-fg" title={data.sync.last_message}>
                {fmtDateTime(data.sync.last_attempt_at)}: {data.sync.last_message.length > 90 ? data.sync.last_message.slice(0, 90) + '…' : data.sync.last_message}
              </span>
            )}
            {error && <span className="text-status-critical-fg">Showing last successful data where available.</span>}
          </div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Btn variant="secondary" onClick={() => openDrawer({ kind: 'watchlist' })} aria-label={`Watchlist, ${watchCount} items`}>
          <Bookmark className="h-3.5 w-3.5" /> Watchlist{watchCount > 0 && <span className="ml-0.5 rounded-full bg-surface-sunken px-1.5 text-[11px] tabular-nums">{watchCount}</span>}
        </Btn>
        <Btn variant="secondary" onClick={onExport}><Download className="h-3.5 w-3.5" /> Export</Btn>
        <Btn variant="primary" onClick={() => openDrawer({ kind: 'ask' })}><Sparkles className="h-3.5 w-3.5" /> Ask Akasha</Btn>
      </div>
    </div>
  );
};
