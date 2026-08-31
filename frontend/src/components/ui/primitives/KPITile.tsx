import React from 'react';
import { motion } from 'framer-motion';
import { Card, type Tone } from './Card';
import {
  Metric, StatRow, Delta,
  type MetricSize, type StatItem, type DeltaDirection, type Polarity,
} from './Metric';
import { Sparkline, MIN_SERIES_POINTS } from './Sparkline';
import { Meter } from './Meter';
import { InfoTip, type TipAlign } from './InfoTip';
import { SourceTag, type SourceSystem } from './Status';
import { itemVariants } from './motion';
import { cx } from './cx';

/* ═══════════════════════════════════════════════════════════════════════════
   KPI TILE — "Signal"
   The single KPI surface for the platform. Replaces six separate inline
   implementations that disagreed on radius, weight, number scale, and on
   whether colour meant anything at all.

   Two ideas carry it:

   1. TRAJECTORY. A figure alone does not say whether things are improving.
      The foot of the tile is a slot that resolves down a ladder —
        A  sparkline   when a real series exists
        B  proportion  when there is no history but there is a denominator
        C  nothing     when there is neither
      It never fabricates a series: a flat invented line is a claim that the
      figure is stable.

   2. HIERARCHY. Three weights, not one. A band of seven identical tiles gives
      the reader no entry point; one hero plus primaries plus supporting tiles
      tells the eye where to land first.

   Only tones that demand attention draw an accent rail — a healthy portfolio
   should render as a quiet screen, not a green one.
   ═══════════════════════════════════════════════════════════════════════════ */

export type KPISize = 'hero' | 'primary' | 'supporting';

/* Density note. The body is deliberately NOT flex-1 and NOT justify-between.
   A row stretches every tile to the tallest one, so a growing body with its
   content pushed to both edges turns that surplus into a hole in the middle
   of the shorter tiles — roughly 90px of nothing under "42". Instead the body
   is content-sized and the trajectory slot flexes, so leftover height makes
   the plot taller rather than making the tile emptier. */
const WEIGHT: Record<KPISize, {
  metric: MetricSize;
  body: string;
  /** Bottom padding applied only when there is no slot beneath the body. */
  bodyOnly: string;
  /** viewBox reference height, and the floor the plot may not shrink below. */
  plot: number;
}> = {
  hero:       { metric: 'xl', body: 'px-4 pt-3',   bodyOnly: 'pb-3.5', plot: 34 },
  primary:    { metric: 'lg', body: 'px-3.5 pt-3', bodyOnly: 'pb-3.5', plot: 30 },
  supporting: { metric: 'md', body: 'px-3 pt-2.5', bodyOnly: 'pb-3',   plot: 26 },
};

/** Slot padding, matched to the body so meter captions line up with the label. */
const SLOT_PAD: Record<KPISize, string> = {
  hero: 'px-4 pb-3',
  primary: 'px-3.5 pb-3',
  supporting: 'px-3 pb-2.5',
};

/** Attention states get an edge; settled states do not. */
const RAIL_TONES: Tone[] = ['critical', 'risk'];

const ICON_TINT: Record<Tone, string> = {
  neutral: 'text-fg-tertiary',
  critical: 'text-status-critical',
  risk: 'text-status-risk',
  watch: 'text-status-watch',
  healthy: 'text-status-healthy',
  done: 'text-status-done',
  ai: 'text-status-ai',
};

/** Mode A — a real measured series, oldest to newest. */
export interface Trajectory {
  series: number[];
  /** Window the series covers, e.g. "12 months". Labels the delta. */
  period?: string;
}

/** Mode B — the figure expressed against its total or target. */
export interface Proportion {
  pct: number;
  target?: number;
  nowLabel?: React.ReactNode;
  capLabel?: React.ReactNode;
}

/** A change over a stated period. NOT a component of the total — that is `stats`. */
export interface KPIDelta {
  value: React.ReactNode;
  direction: DeltaDirection;
  label?: React.ReactNode;
}

export interface KPITileProps {
  label: React.ReactNode;
  /** Pre-formatted by the caller: the tile never divides by a crore or guesses a locale. */
  value: React.ReactNode;
  /** Value is a phrase rather than a figure ("Material Delivery"). */
  isText?: boolean;
  unit?: React.ReactNode;
  denominator?: React.ReactNode;

  /** One caption line, or up to two supporting figures — not both. */
  subtext?: React.ReactNode;
  stats?: StatItem[];

  /* Trajectory slot. First match wins; omit both for mode C. */
  trajectory?: Trajectory;
  proportion?: Proportion;

  delta?: KPIDelta;
  /** Which direction is good. Default 'up-good'. */
  polarity?: Polarity;
  tone?: Tone;
  source?: SourceSystem | SourceSystem[];

  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  size?: KPISize;
  info?: React.ReactNode;
  infoAlign?: TipAlign;

  onClick?: () => void;
  /** Held true while this tile's drill-down is open. */
  selected?: boolean;
  loading?: boolean;
  /** Short reason. Replaces the value; the tile keeps its footprint. */
  error?: string;
  onRetry?: () => void;
  /** Grid span only, e.g. "lg:col-span-6". */
  className?: string;
}

export const KPITile = ({
  label, value, isText, unit, denominator,
  subtext, stats,
  trajectory, proportion,
  delta, polarity = 'up-good', tone = 'neutral', source,
  icon: Icon, size = 'primary', info, infoAlign,
  onClick, selected, loading, error, onRetry,
  className,
}: KPITileProps) => {
  const w = WEIGHT[size];

  if (import.meta.env?.DEV && subtext && stats && stats.length > 0) {
    console.warn(
      '[KPITile] received both subtext and stats. Together they push the ' +
      'value off optical centre — pick one.'
    );
  }

  /* Only the hero is wide enough to carry its stats on the same line. */
  const hasInlineStats = size === 'hero' && !!stats && stats.length > 0 && !isText;

  /* Resolve the trajectory slot once, so the body knows what follows it. */
  const hasSeries = !!trajectory && trajectory.series.length >= MIN_SERIES_POINTS;
  const slot =
    loading || error ? null
    : hasSeries ? (
        /* flex-1: the plot, not the whitespace, takes any leftover row height. */
        /* rounded-b-[7px] sits 1px inside the card's 8px radius, so the plot
           meets the corner cleanly with no sliver of fill outside the border. */
        <div
          className="relative mt-2 flex-1 overflow-hidden rounded-b-[7px]"
          style={{ minHeight: w.plot }}
        >
          <Sparkline
            series={trajectory.series}
            tone={tone}
            height={w.plot}
            className="absolute inset-0"
          />
        </div>
      )
    : proportion ? (
        /* mt-auto pins the meter to the foot of the card, so a stretched tile
           reads as a card with a footer rather than one with a gap. */
        <div className={cx('mt-auto', SLOT_PAD[size])}>
          <Meter
            pct={proportion.pct}
            target={proportion.target}
            nowLabel={proportion.nowLabel}
            capLabel={proportion.capLabel}
            tone={tone}
          />
        </div>
      )
    : null;

  /* A delta and a sparkline must describe the same window, or the tile tells
     two different stories about one figure. */
  const deltaLabel =
    delta?.label ?? (hasSeries && trajectory.period ? `vs ${trajectory.period} ago` : undefined);

  const sources = source ? (Array.isArray(source) ? source : [source]) : [];
  const showSubtext = !!subtext && !(stats && stats.length > 0);

  const accessibleName = [
    typeof label === 'string' ? label : null,
    typeof value === 'string' || typeof value === 'number' ? String(value) : null,
    typeof unit === 'string' ? unit : null,
  ].filter(Boolean).join(': ');

  return (
    <motion.div variants={itemVariants} className={cx('h-full', className)}>
      <Card
        tone={RAIL_TONES.includes(tone) ? tone : 'neutral'}
        pad="none"
        interactive={!!onClick}
        onClick={onClick}
        aria-label={accessibleName || undefined}
        aria-busy={loading || undefined}
        /* No overflow-hidden here. It was clipping the InfoTip popover to the
           tile, cutting the explanation off mid-word. Only the sparkline needs
           clipping, so that is done on the slot itself. */
        className={cx(
          'flex h-full flex-col',
          selected && 'border-primary ring-[3px] ring-primary/15'
        )}
      >
        {/* Body: content-sized. See the density note on WEIGHT. */}
        <div className={cx(w.body, !slot && w.bodyOnly)}>
          <div className="mb-2 flex items-start justify-between gap-2.5">
            <div className="flex min-w-0 items-center gap-1">
              <h4 className="section-label truncate leading-tight">{label}</h4>
              {info && <InfoTip info={info} align={infoAlign} />}
            </div>

            {/* Top-right holds one element. A delta outranks the icon. */}
            {loading ? null : delta ? (
              <Delta
                direction={delta.direction}
                value={delta.value}
                polarity={polarity}
                className="shrink-0"
              />
            ) : (
              <Icon
                className={cx(
                  'h-4 w-4 shrink-0 opacity-75 transition-opacity group-hover:opacity-100',
                  ICON_TINT[tone]
                )}
                strokeWidth={1.5}
              />
            )}
          </div>

          <div>
            {loading ? (
              <>
                <div className="h-5 w-14 animate-pulse rounded-sm bg-fg-tertiary/20" />
                <div className="mt-2 h-2 w-24 animate-pulse rounded-sm bg-fg-tertiary/20" />
              </>
            ) : error ? (
              <>
                <div className="text-[13px] font-semibold leading-tight text-status-critical-fg">
                  {error}
                </div>
                {onRetry && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onRetry(); }}
                    className="mt-1.5 text-[10.5px] font-medium text-fg-tertiary underline underline-offset-2 hover:text-fg-primary"
                  >
                    Retry
                  </button>
                )}
              </>
            ) : (
              <>
                {/* A hero spans half the grid, so its supporting figures sit
                    BESIDE the headline rather than under it. Stacking them was
                    what made the hero taller than everything in its row, and
                    that extra height was then inherited by every tile beside
                    it as empty space. */}
                <div
                  className={cx(
                    hasInlineStats && 'flex flex-wrap items-end justify-between gap-x-6 gap-y-2'
                  )}
                >
                  <Metric
                    size={w.metric}
                    value={value}
                    unit={unit}
                    denominator={denominator}
                    plain={isText}
                  />

                  {hasInlineStats && (
                    <div className="flex items-end gap-5">
                      {stats!.slice(0, 2).map((s, i) => (
                        <div key={i} className="min-w-0">
                          <div className="section-label">{s.label}</div>
                          <Metric size="sm" value={s.value} unit={s.unit} className="mt-0.5" />
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {delta && deltaLabel && (
                  <div className="mt-1.5 text-[10px] font-medium text-fg-tertiary">{deltaLabel}</div>
                )}

                {/* Provenance rides the caption line rather than claiming a
                    row of its own — a tag on its own line reads as a stray
                    chip floating between the value and the slot. */}
                {(showSubtext || sources.length > 0) && (
                  <div className="mt-1.5 flex items-center justify-between gap-2">
                    {showSubtext ? (
                      <span className="truncate text-[10px] font-medium text-fg-tertiary">{subtext}</span>
                    ) : <span />}
                    {sources.length > 0 && (
                      <span className="flex shrink-0 items-center gap-1">
                        {sources.map((s) => <SourceTag key={s} system={s} />)}
                      </span>
                    )}
                  </div>
                )}

                {stats && stats.length > 0 && !hasInlineStats && (
                  <StatRow stats={stats.slice(0, 2)} />
                )}
              </>
            )}
          </div>

        </div>

        {loading ? (
          <div className={SLOT_PAD[size]}>
            <div className="h-[5px] w-full animate-pulse rounded-sm bg-fg-tertiary/20" />
          </div>
        ) : slot}
      </Card>
    </motion.div>
  );
};
