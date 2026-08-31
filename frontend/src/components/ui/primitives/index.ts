/* Akasha primitive layer.
   Import from here, never from the individual files — the barrel is what makes
   a future change to the system land everywhere at once. */
export { cx } from './cx';
export { Card, CardHeader } from './Card';
export type { Tone, CardProps, CardHeaderProps } from './Card';
export { Metric, Delta, StatRow } from './Metric';
export type { MetricSize, MetricProps, DeltaDirection, Polarity, StatItem } from './Metric';
export { StatusPill, StatusDot, Legend, LegendItem, SourceTag } from './Status';
export type { SourceSystem } from './Status';
export { InfoTip } from './InfoTip';
export type { TipAlign } from './InfoTip';
export { KPITile } from './KPITile';
export type { KPISize, KPITileProps, Trajectory, Proportion, KPIDelta } from './KPITile';
export { Sparkline, MIN_SERIES_POINTS } from './Sparkline';
export type { SparklineProps } from './Sparkline';
export { Meter, MiniMeter } from './Meter';
export type { MeterProps } from './Meter';
export { ChartFrame } from './ChartFrame';
export type { ChartFrameProps } from './ChartFrame';
export { PageHeader } from './PageHeader';
export { containerVariants, itemVariants } from './motion';

/* NOT YET WRITTEN — exported here before the module existed, which broke
   `tsc -b` for the whole app. Re-add the export in the same move that adds the
   file, so the barrel never again references something that isn't there:
     · HeroBand (+ HeroBandTop, HeroStatement, HeroSubline, HeroStats, HeroStat) */
