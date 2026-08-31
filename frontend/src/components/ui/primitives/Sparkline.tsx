import React from 'react';
import { cx } from './cx';
import type { Tone } from './Card';

/* ═══════════════════════════════════════════════════════════════════════════
   SPARKLINE
   Mode A of the KPI trajectory slot. Bleeds edge to edge at the foot of a
   tile so direction is read from the shape, not only from the delta chip.

   The stroke carries the tile's tone: neutral resolves to brand blue, so a
   healthy band shows blue lines and only a genuine problem shows red. Never
   render this with a synthesised series — a flat line is a claim that the
   figure is stable.
   ═══════════════════════════════════════════════════════════════════════════ */

const STROKE: Record<Tone, string> = {
  neutral: 'var(--primary)',
  critical: 'var(--status-critical-solid)',
  risk: 'var(--status-risk-solid)',
  watch: 'var(--status-watch-solid)',
  healthy: 'var(--status-healthy-solid)',
  done: 'var(--status-done-solid)',
  ai: 'var(--status-ai-solid)',
};

/** Below this the shape is noise rather than a trend — the slot falls to mode B/C. */
export const MIN_SERIES_POINTS = 4;

export interface SparklineProps {
  series: number[];
  tone?: Tone;
  /** Reference height for the viewBox only — the rendered height comes from
   *  the parent, so the plot can stretch to absorb leftover row height. */
  height?: number;
  className?: string;
}

export const Sparkline = ({ series, tone = 'neutral', height = 32, className }: SparklineProps) => {
  if (!series || series.length < MIN_SERIES_POINTS) return null;

  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = max - min || 1;
  const pad = 4;

  const pts = series.map((v, i) => [
    (i / (series.length - 1)) * 100,
    pad + (1 - (v - min) / range) * (height - pad * 2),
  ]);

  const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`).join(' ');
  const area = `${line} L100 ${height} L0 ${height} Z`;
  const [lx, ly] = pts[pts.length - 1];
  const c = STROKE[tone];

  return (
    /* preserveAspectRatio="none" lets the plot stretch to whatever box the
       parent gives it, in both axes; the stroke is held at 1.6px by
       vector-effect so it never distorts with it. No height attribute — the
       parent owns the height, which is what lets the plot soak up leftover
       space instead of leaving a hole above it. */
    <svg
      className={cx('block h-full w-full', className)}
      viewBox={`0 0 100 ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d={area}
        fill={c}
        className="opacity-[0.13] transition-opacity duration-base group-hover:opacity-25"
      />
      <path
        d={line}
        fill="none"
        stroke={c}
        strokeWidth={1.6}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle
        cx={lx}
        cy={ly}
        r={2.4}
        fill={c}
        stroke="var(--surface-1)"
        strokeWidth={1.4}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
};
