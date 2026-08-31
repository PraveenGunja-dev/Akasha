import React from 'react';
import { cx } from './cx';
import type { Tone } from './Card';

/* ═══════════════════════════════════════════════════════════════════════════
   STATUS
   Five states plus one AI accent, all resolved from the status triads in
   index.css. Nothing here accepts a raw colour — that is the point. Roughly
   500 hardcoded hex values across the app exist because this primitive didn't.
   ═══════════════════════════════════════════════════════════════════════════ */

const PILL: Record<Tone, string> = {
  neutral: 'source-tag',
  critical: 'status-pill-critical',
  risk: 'status-pill-risk',
  watch: 'status-pill-watch',
  healthy: 'status-pill-healthy',
  done: 'status-pill-done',
  ai: 'status-pill-ai',
};

const DOT: Record<Tone, string> = {
  neutral: 'status-dot bg-fg-disabled',
  critical: 'status-dot-critical',
  risk: 'status-dot-warning',
  watch: 'status-dot-watch',
  healthy: 'status-dot-healthy',
  done: 'status-dot-done',
  ai: 'status-dot bg-status-ai',
};

export const StatusPill = ({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
}) => <span className={cx(PILL[tone], className)}>{children}</span>;

export const StatusDot = ({ tone = 'neutral', className }: { tone?: Tone; className?: string }) => (
  <span className={cx(DOT[tone], className)} />
);

/* Legend entries read from the same tone tokens the chart series do, so a
   legend can no longer drift out of sync with the marks it describes. */
export const LegendItem = ({ tone, label }: { tone: Tone; label: React.ReactNode }) => (
  <span className="flex items-center gap-1.5 whitespace-nowrap text-[11px] font-medium text-fg-secondary">
    <StatusDot tone={tone} />
    {label}
  </span>
);

export const Legend = ({
  items,
  className,
}: {
  items: Array<{ tone: Tone; label: React.ReactNode }>;
  className?: string;
}) => (
  <div className={cx('flex flex-wrap items-center gap-x-4 gap-y-1.5', className)}>
    {items.map((it, i) => (
      <LegendItem key={i} {...it} />
    ))}
  </div>
);

/* Provenance, not status: which source system a figure came from. Neutral by
   design so it never competes with a state colour. */
export type SourceSystem = 'P6' | 'SAP' | 'TC' | 'Pulse' | 'SharePoint';

export const SourceTag = ({ system, stamp }: { system: SourceSystem; stamp?: React.ReactNode }) => (
  <span className="source-tag">
    {system}
    {stamp ? <span className="font-normal opacity-70">· {stamp}</span> : null}
  </span>
);
