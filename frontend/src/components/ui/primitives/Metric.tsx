import React from 'react';
import { cx } from './cx';

/* ═══════════════════════════════════════════════════════════════════════════
   METRIC
   Numbers are the design. Every figure in the product renders through this so
   it gets tabular lining figures, the right optical size, and a unit that
   rides alongside at reduced weight instead of being baked into the string.

   The scale is declared once in index.css (.metric-hero … .metric-sm); this
   is the only thing that should reference those classes.
   ═══════════════════════════════════════════════════════════════════════════ */

export type MetricSize = 'hero' | 'xl' | 'lg' | 'md' | 'sm';

const SIZE: Record<MetricSize, string> = {
  hero: 'metric-hero',
  xl: 'metric-xl',
  lg: 'metric-lg',
  md: 'metric-md',
  sm: 'metric-sm',
};

/* Some KPIs answer with a phrase, not a figure — "Primary Bottleneck:
   Material Delivery". Tabular figures and -0.03em tracking are wrong for
   words, and the numeric scale is far too large for them, so text values get
   their own step-down. */
const PLAIN_SIZE: Record<MetricSize, string> = {
  hero: 'text-[24px]',
  xl: 'text-[22px]',
  lg: 'text-[19px]',
  md: 'text-[16px]',
  sm: 'text-[14px]',
};

export interface MetricProps {
  value: React.ReactNode;
  unit?: React.ReactNode;
  /** Renders after the value at half size — "/100" on a score. */
  denominator?: React.ReactNode;
  /** Value is prose, not a figure: drops tabular figures and the numeric scale. */
  plain?: boolean;
  size?: MetricSize;
  className?: string;
}

export const Metric = ({ value, unit, denominator, plain, size = 'lg', className }: MetricProps) => (
  <div
    className={cx(
      plain
        ? cx(
            'font-semibold leading-tight tracking-[-0.015em] text-fg-primary',
            PLAIN_SIZE[size]
          )
        : SIZE[size],
      className
    )}
  >
    <span>{value}</span>
    {denominator ? <span className="metric-denominator">{denominator}</span> : null}
    {unit ? <span className="metric-unit">{unit}</span> : null}
  </div>
);

/* ── Delta ──
   Direction is carried by a glyph as well as by colour, so the value survives
   a board projector and a colour-blind reader.

   Colour comes from POLARITY, not from direction. "Delayed Projects ▲ 3" is
   bad news and must read red; "Completed ▲ 3" is good news and must read
   green. The previous version hardcoded up→green, which coloured a worsening
   portfolio as an improving one. */

export type DeltaDirection = 'up' | 'down' | 'flat';

/** Which direction is the good one for this measure. */
export type Polarity = 'up-good' | 'down-good' | 'neutral';

const GLYPH: Record<DeltaDirection, string> = { up: '▲', down: '▼', flat: '●' };

function deltaClass(direction: DeltaDirection, polarity: Polarity): string {
  if (direction === 'flat' || polarity === 'neutral') return 'delta-flat';
  const isGood = polarity === 'down-good' ? direction === 'down' : direction === 'up';
  return isGood ? 'delta-up' : 'delta-down';
}

export interface DeltaProps {
  direction: DeltaDirection;
  value: React.ReactNode;
  label?: React.ReactNode;
  /** Default 'up-good' — matches the previous behaviour for existing call sites. */
  polarity?: Polarity;
  className?: string;
}

export const Delta = ({ direction, value, label, polarity = 'up-good', className }: DeltaProps) => (
  <div className={cx('flex items-center gap-1.5', className)}>
    <span className={cx('delta', deltaClass(direction, polarity))}>
      {GLYPH[direction]} {value}
    </span>
    {label ? <span className="text-[10px] font-medium text-fg-tertiary">{label}</span> : null}
  </div>
);

/* ── Supporting figures ──
   A row of secondary numbers sharing a tile, rather than each claiming one.
   Separated from the headline by a hairline, never by a second card. */

export interface StatItem {
  label: React.ReactNode;
  value: React.ReactNode;
  unit?: React.ReactNode;
}

export const StatRow = ({ stats, className }: { stats: StatItem[]; className?: string }) => (
  <div className={cx('mt-3 flex items-center gap-5 border-t border-border-subtle pt-2.5', className)}>
    {stats.map((s, i) => (
      <div key={i} className="min-w-0">
        <div className="section-label">{s.label}</div>
        <Metric size="sm" value={s.value} unit={s.unit} className="mt-0.5" />
      </div>
    ))}
  </div>
);
