import React from 'react';
import { cx } from './cx';
import type { Tone } from './Card';

/* ═══════════════════════════════════════════════════════════════════════════
   METER
   Mode B of the KPI trajectory slot, and the general progress/utilisation bar.

   Most portfolio figures are only meaningful against a total: "7 delayed" is
   noise, "7 of 42" is a number you can act on. Where no history exists to draw
   a sparkline, a proportion is the honest alternative — it adds context
   without inventing data.
   ═══════════════════════════════════════════════════════════════════════════ */

const FILL: Record<Tone, string> = {
  neutral: 'bg-primary',
  critical: 'bg-status-critical',
  risk: 'bg-status-risk',
  watch: 'bg-status-watch',
  healthy: 'bg-status-healthy',
  done: 'bg-status-done',
  ai: 'bg-status-ai',
};

const clamp = (n: number) => Math.max(0, Math.min(100, Number.isFinite(n) ? n : 0));

export interface MeterProps {
  /** 0–100. Values outside the range are clamped rather than overflowing. */
  pct: number;
  /** 0–100. Draws a target tick above the track. */
  target?: number;
  tone?: Tone;
  /** Left caption — what the fill represents ("23 open"). */
  nowLabel?: React.ReactNode;
  /** Right caption — what it is measured against ("68 raised"). */
  capLabel?: React.ReactNode;
  className?: string;
}

/** Track only. For table cells and anywhere the captions would be redundant. */
export const MiniMeter = ({
  pct,
  target,
  tone = 'neutral',
  className,
}: Omit<MeterProps, 'nowLabel' | 'capLabel'>) => (
  <div
    className={cx(
      'relative h-[5px] w-full rounded-sm border border-border-subtle bg-surface-sunken',
      className
    )}
    role="presentation"
  >
    <div
      className={cx('absolute inset-y-0 left-0 rounded-l-sm transition-[width] duration-slow', FILL[tone])}
      style={{ width: `${clamp(pct)}%` }}
    />
    {target != null && (
      <div
        className="absolute -top-[3px] -bottom-[3px] w-0.5 rounded-sm bg-fg-secondary"
        style={{ left: `${clamp(target)}%` }}
      />
    )}
  </div>
);

export const Meter = ({ pct, target, tone = 'neutral', nowLabel, capLabel, className }: MeterProps) => (
  <div className={cx('flex flex-col gap-1.5', className)}>
    <MiniMeter pct={pct} target={target} tone={tone} />
    {(nowLabel || capLabel) && (
      <div className="flex items-baseline justify-between gap-2.5 text-[9.5px] font-medium text-fg-tertiary">
        <span className="truncate">{nowLabel}</span>
        <span className="shrink-0">{capLabel}</span>
      </div>
    )}
  </div>
);
