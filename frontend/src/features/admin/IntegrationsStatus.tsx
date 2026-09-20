import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, Radio, Wifi, WifiOff, Loader2, Play, Clock, ChevronDown, CalendarClock, AlertTriangle, CheckCircle2, PauseCircle } from 'lucide-react';
import { Card, CardHeader, StatusDot, StatusPill, type Tone, cx } from '../../components/ui/primitives';
import { Btn } from '../sap-intelligence/components/Drawer';
import { formatDateTime } from '../../lib/utils';

/* Integrations control panel. Every feed refreshes itself on a schedule the
   user sets here; this screen shows that as the normal state and gives the
   controls for it.

   Three independent signals, kept visually separate:
   1. SCHEDULE  — sync_schedule: interval, next run, on/off. Editable inline.
   2. OUTCOME   — sync_log: what the last run actually did (scheduled or
                  manual), with the real error when it failed. Polled while
                  the panel is open, faster while something is running.
   3. LIVE      — "Check connections" probes each source right this second
                  and shows the real error if one fails. On demand only: P6
                  performs a genuine login per call and repeated automatic
                  hits risk the account lockout the app already guards
                  against. */

type FeedStatus = 'running' | 'down' | 'idle' | 'paused';

interface Schedule {
  source: string; enabled: boolean; interval_minutes: number | null;
  next_run_at: string | null; last_run_at: string | null; last_duration_s: number | null; in_progress: boolean;
  window_start_hour: number | null; window_end_hour: number | null;
}
interface Feed {
  key: string; label: string; status: FeedStatus; detail: string;
  last_attempt_at: string | null; last_status: string | null; last_success_at: string | null; data_as_of: string | null;
  schedule: Schedule;
}
interface StatusResponse {
  feeds: Feed[];
  summary: { running: number; down: number; idle: number; paused: number; total: number; next_run_at: string | null; scheduler_enabled: boolean };
}
interface LiveCheck { key: string; ok: boolean; detail: string; checked_at: string }

const INTERVALS: { value: number; label: string }[] = [
  { value: 15, label: 'Every 15 min' }, { value: 30, label: 'Every 30 min' }, { value: 60, label: 'Hourly' },
  { value: 120, label: 'Every 2 h' }, { value: 240, label: 'Every 4 h' }, { value: 360, label: 'Every 6 h' },
  { value: 720, label: 'Every 12 h' }, { value: 1440, label: 'Daily' }, { value: 10080, label: 'Weekly' },
];

// Automatic-run window presets (IST hour-of-day). "Run now" always ignores
// this — it only gates when a due feed is allowed to fire on its own.
const WINDOWS: { key: string; label: string; start: number | null; end: number | null }[] = [
  { key: 'any', label: 'Anytime', start: null, end: null },
  { key: '1-5', label: 'Night · 1–5 AM', start: 1, end: 5 },
  { key: '23-6', label: 'Night · 11 PM–6 AM', start: 23, end: 6 },
  { key: '22-6', label: 'Off-hours · 10 PM–6 AM', start: 22, end: 6 },
];
const windowKey = (start: number | null, end: number | null) =>
  WINDOWS.find(w => w.start === start && w.end === end)?.key ?? 'any';

const relative = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const ms = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(ms), past = ms < 0;
  const n = abs < 3.6e6 ? `${Math.max(1, Math.round(abs / 6e4))} min` : abs < 8.64e7 ? `${Math.round(abs / 3.6e6)} h` : `${Math.round(abs / 8.64e7)} d`;
  return past ? `${n} ago` : `in ${n}`;
};
const duration = (s: number | null | undefined) => s == null ? '' : s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;

const PILL: Record<FeedStatus | 'live', { tone: Tone; label: string }> = {
  running: { tone: 'healthy', label: 'Scheduled' },
  down: { tone: 'critical', label: 'Failed' },
  idle: { tone: 'neutral', label: 'Not run yet' },
  paused: { tone: 'neutral', label: 'Paused' },
  live: { tone: 'ai', label: 'Running' },
};

/* Accessible on/off switch on the design tokens; no switch primitive exists yet. */
const Switch = ({ on, onChange, disabled, label }: { on: boolean; onChange: (v: boolean) => void; disabled?: boolean; label: string }) => (
  <button
    type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled}
    onClick={() => onChange(!on)}
    className={cx('relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50',
      on ? 'border-primary bg-primary' : 'border-border-default bg-surface-sunken')}
  >
    <span className={cx('absolute h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform', on ? 'translate-x-[18px]' : 'translate-x-[3px]')} />
  </button>
);

export default function IntegrationsStatus() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState<Record<string, LiveCheck>>({});
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const timer = useRef<number | null>(null);

  const load = useCallback((quiet = false) => {
    if (!quiet) setLoading(true);
    fetch('/akasha/api/integrations/status')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: StatusResponse) => { setData(d); setError(null); })
      .catch(e => setError(e.message || 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  const anyRunning = !!data?.feeds.some(f => f.schedule.in_progress);

  // Poll: 20 s normally, 5 s while any feed is mid-run so progress is visible.
  useEffect(() => {
    load();
    const tick = () => {
      timer.current = window.setTimeout(() => { load(true); tick(); }, anyRunning ? 5000 : 20000);
    };
    tick();
    return () => { if (timer.current) window.clearTimeout(timer.current); };
  }, [load, anyRunning]);

  const patch = async (key: string, body: { enabled?: boolean; interval_minutes?: number; window_start_hour?: number; window_end_hour?: number; clear_window?: boolean }) => {
    setBusy(b => ({ ...b, [key]: true }));
    try {
      const r = await fetch(`/akasha/api/integrations/schedules/${key}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
      load(true);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(b => ({ ...b, [key]: false })); }
  };

  const runNow = async (key: string) => {
    setBusy(b => ({ ...b, [key]: true }));
    try {
      await fetch(`/akasha/api/integrations/schedules/${key}/run`, { method: 'POST' });
      setTimeout(() => load(true), 800);
    } finally { setBusy(b => ({ ...b, [key]: false })); }
  };

  const runCheck = () => {
    setChecking(true); setCheckError(null);
    fetch('/akasha/api/integrations/health-check')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: { checked: LiveCheck[] }) => setLive(Object.fromEntries(d.checked.map(c => [c.key, c]))))
      .catch(e => setCheckError(e.message || 'Check failed'))
      .finally(() => setChecking(false));
  };

  const s = data?.summary;

  return (
    <Card pad="md">
      <CardHeader
        icon={Radio}
        title="Integrations"
        eyebrow="System health · automatic sync"
        right={
          <div className="flex items-center gap-2">
            <Btn variant="secondary" onClick={runCheck} disabled={checking} title="Probe every source right now and show the real error if one fails">
              {checking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wifi className="h-3.5 w-3.5" />}
              {checking ? 'Checking…' : 'Check connections'}
            </Btn>
            <button onClick={() => load(true)} disabled={loading} aria-label="Refresh"
              className="rounded-md p-1.5 text-fg-tertiary transition-colors hover:bg-surface-sunken hover:text-fg-primary disabled:opacity-50">
              <RefreshCw className={cx('h-3.5 w-3.5', loading && 'animate-spin')} />
            </button>
          </div>
        }
      />

      {s && (
        <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-md border border-border-subtle bg-surface-sunken/60 px-3.5 py-2.5 text-[12px]">
          <span className="inline-flex items-center gap-1.5 text-fg-secondary"><CheckCircle2 className="h-3.5 w-3.5 text-status-healthy-fg" /><span className="font-semibold tabular-nums text-fg-primary">{s.running}</span> healthy</span>
          <span className={cx('inline-flex items-center gap-1.5', s.down ? 'text-status-critical-fg' : 'text-fg-tertiary')}><AlertTriangle className="h-3.5 w-3.5" /><span className="font-semibold tabular-nums">{s.down}</span> failed</span>
          <span className="inline-flex items-center gap-1.5 text-fg-tertiary"><PauseCircle className="h-3.5 w-3.5" /><span className="font-semibold tabular-nums">{s.paused}</span> paused</span>
          {s.idle > 0 && <span className="inline-flex items-center gap-1.5 text-fg-tertiary"><Clock className="h-3.5 w-3.5" /><span className="font-semibold tabular-nums">{s.idle}</span> awaiting first run</span>}
          <span className="ml-auto inline-flex items-center gap-1.5 text-fg-tertiary">
            <CalendarClock className="h-3.5 w-3.5" />
            {s.scheduler_enabled
              ? <>Next sync <span className="font-medium text-fg-secondary">{relative(s.next_run_at)}</span></>
              : <span className="text-status-critical-fg">Scheduler is off on this server (AKASHA_SCHEDULER=0)</span>}
          </span>
        </div>
      )}

      {error && <p className="mb-3 text-[12px] text-status-critical-fg">{error}</p>}
      {checkError && <p className="mb-3 text-[12px] text-status-critical-fg">Connection check failed to run: {checkError}</p>}
      {!data && loading && <div className="py-8 text-center text-[12px] text-fg-tertiary">Loading…</div>}

      {data && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] border-collapse text-[12px]">
            <thead>
              <tr className="text-[10.5px] uppercase tracking-wider text-fg-tertiary">
                <th className="pb-2 pr-3 text-left font-semibold">Feed</th>
                <th className="px-3 pb-2 text-left font-semibold">Schedule</th>
                <th className="px-3 pb-2 text-left font-semibold">Last run</th>
                <th className="px-3 pb-2 text-left font-semibold">Next run</th>
                <th className="px-3 pb-2 text-left font-semibold">Status</th>
                <th className="pb-2 pl-3 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.feeds.map(f => {
                const sc = f.schedule;
                const inFlight = sc.in_progress;
                const pill = inFlight ? PILL.live : PILL[f.status];
                const lc = live[f.key];
                const failed = f.status === 'down';
                const isBusy = !!busy[f.key];
                return (
                  <tr key={f.key} className="align-top">
                    <td className="py-3 pr-3">
                      <div className="flex items-start gap-2.5">
                        <StatusDot tone={pill.tone} className="mt-1.5" />
                        <div className="min-w-0">
                          <div className="text-[13px] font-medium text-fg-primary">{f.label}</div>
                          <div className={cx('mt-0.5 max-w-[360px] truncate text-[11px]', failed ? 'text-status-critical-fg' : 'text-fg-tertiary')} title={f.detail}>{f.detail}</div>
                          {lc && (
                            <div className={cx('mt-1 flex items-center gap-1 text-[11px]', lc.ok ? 'text-status-healthy-fg' : 'text-status-critical-fg')} title={lc.detail}>
                              {lc.ok ? <Wifi className="h-3 w-3 shrink-0" /> : <WifiOff className="h-3 w-3 shrink-0" />}
                              <span className="max-w-[360px] truncate">Connection {lc.ok ? 'OK' : 'failed'} · {lc.detail}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>

                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <Switch on={sc.enabled} disabled={isBusy} label={`${f.label} automatic sync`} onChange={v => patch(f.key, { enabled: v })} />
                        <label className="relative inline-flex items-center">
                          <span className="sr-only">Interval for {f.label}</span>
                          <select
                            value={sc.interval_minutes ?? ''} disabled={isBusy || !sc.enabled}
                            onChange={e => patch(f.key, { interval_minutes: Number(e.target.value) })}
                            className="h-7 appearance-none rounded-md border border-border-default bg-surface-1 pl-2.5 pr-7 text-[12px] text-fg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                          >
                            {INTERVALS.map(i => <option key={i.value} value={i.value}>{i.label}</option>)}
                          </select>
                          <ChevronDown className="pointer-events-none absolute right-2 h-3.5 w-3.5 text-fg-tertiary" />
                        </label>
                      </div>
                      <label className="relative mt-1.5 inline-flex items-center" title="When this feed is allowed to fire on its own. &quot;Run now&quot; always works regardless.">
                        <span className="sr-only">Run window for {f.label}</span>
                        <select
                          value={windowKey(sc.window_start_hour, sc.window_end_hour)} disabled={isBusy || !sc.enabled}
                          onChange={e => {
                            const w = WINDOWS.find(x => x.key === e.target.value)!;
                            patch(f.key, w.start === null ? { clear_window: true } : { window_start_hour: w.start, window_end_hour: w.end! });
                          }}
                          className="h-6 appearance-none rounded-md border border-border-subtle bg-surface-sunken pl-2 pr-6 text-[11px] text-fg-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                        >
                          {WINDOWS.map(w => <option key={w.key} value={w.key}>{w.label}</option>)}
                        </select>
                        <ChevronDown className="pointer-events-none absolute right-1.5 h-3 w-3 text-fg-tertiary" />
                      </label>
                      {f.key === 'sap' && <div className="mt-1 text-[10.5px] text-fg-tertiary">Checks SharePoint; ingests only when a newer extract exists.</div>}
                    </td>

                    <td className="whitespace-nowrap px-3 py-3">
                      {sc.last_run_at || f.last_attempt_at ? (
                        <>
                          <div className="text-fg-primary">{formatDateTime(sc.last_run_at ?? f.last_attempt_at)}</div>
                          <div className="text-[11px] text-fg-tertiary">
                            {relative(sc.last_run_at ?? f.last_attempt_at)}{sc.last_duration_s != null && ` · ${duration(sc.last_duration_s)}`}
                          </div>
                        </>
                      ) : <span className="text-fg-tertiary">—</span>}
                    </td>

                    <td className="whitespace-nowrap px-3 py-3">
                      {inFlight ? <span className="inline-flex items-center gap-1.5 text-fg-secondary"><Loader2 className="h-3 w-3 animate-spin" />In progress</span>
                        : !sc.enabled ? <span className="text-fg-tertiary">Paused</span>
                        : sc.next_run_at ? (<><div className="text-fg-primary">{relative(sc.next_run_at)}</div><div className="text-[11px] text-fg-tertiary">{formatDateTime(sc.next_run_at)}</div></>)
                        : <span className="text-fg-tertiary">—</span>}
                    </td>

                    <td className="whitespace-nowrap px-3 py-3"><StatusPill tone={pill.tone}>{pill.label}</StatusPill></td>

                    <td className="whitespace-nowrap py-3 pl-3 text-right">
                      <Btn variant="ghost" className="h-7 px-2.5 text-[12px]" disabled={inFlight || isBusy} onClick={() => runNow(f.key)} title="Run this sync now">
                        {inFlight ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Run now
                      </Btn>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
