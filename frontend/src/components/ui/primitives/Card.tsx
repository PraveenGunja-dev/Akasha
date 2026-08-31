import React from 'react';
import { cx } from './cx';

/* ═══════════════════════════════════════════════════════════════════════════
   CARD
   The single surface primitive. One hairline border, one elevation step, an
   8px radius. Every panel on a data screen is this — no local variations.

   Tone drives a 3px left accent rail and nothing else: colour on a card edge
   is a state signal, never decoration. `neutral` (the default) draws no rail,
   so a screen only carries as many coloured edges as it has problems.
   ═══════════════════════════════════════════════════════════════════════════ */

export type Tone = 'neutral' | 'critical' | 'risk' | 'watch' | 'healthy' | 'done' | 'ai';

const ACCENT_RAIL: Record<Tone, string> = {
  neutral: '',
  critical: 'intelligence-card-critical',
  risk: 'intelligence-card-warning',
  watch: 'intelligence-card-watch',
  healthy: 'intelligence-card-healthy',
  done: 'intelligence-card-done',
  ai: '',
};

const PAD = {
  none: '',
  sm: 'px-3.5 py-3',
  md: 'px-4 py-3.5',
  lg: 'px-5 py-4',
} as const;

export interface CardProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'onClick'> {
  tone?: Tone;
  pad?: keyof typeof PAD;
  /** Adds pointer affordance + Enter/Space activation. Use with onClick. */
  interactive?: boolean;
  onClick?: () => void;
  children?: React.ReactNode;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(function Card(
  { tone = 'neutral', pad = 'md', interactive, onClick, className, children, ...rest },
  ref
) {
  const activation = interactive
    ? {
        role: 'button' as const,
        tabIndex: 0,
        onKeyDown: (e: React.KeyboardEvent) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onClick?.();
          }
        },
      }
    : {};

  return (
    <div
      ref={ref}
      onClick={onClick}
      className={cx(
        'bento-card',
        ACCENT_RAIL[tone],
        PAD[pad],
        interactive && 'cursor-pointer group',
        className
      )}
      {...activation}
      {...rest}
    >
      {children}
    </div>
  );
});

/* ── Card header ──
   Title carries the weight; the icon is tertiary and quiet. Icons used to be
   `text-primary` on every card, which spent brand blue on decoration and left
   nothing to signal an actual primary action. */

export interface CardHeaderProps {
  title: React.ReactNode;
  icon?: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  /** Small uppercase kicker above the title. */
  eyebrow?: React.ReactNode;
  /** Right-hand slot: legend, filter, count, source tag. */
  right?: React.ReactNode;
  className?: string;
}

export const CardHeader = ({ title, icon: Icon, eyebrow, right, className }: CardHeaderProps) => (
  <div className={cx('flex items-start justify-between gap-4 mb-3', className)}>
    <div className="min-w-0">
      {eyebrow && <div className="section-label mb-1">{eyebrow}</div>}
      <h3 className="flex items-center gap-2 text-[13px] font-semibold leading-tight text-fg-primary">
        {Icon && <Icon className="w-4 h-4 shrink-0 text-fg-tertiary" strokeWidth={1.5} />}
        <span className="truncate">{title}</span>
      </h3>
    </div>
    {right && <div className="flex shrink-0 items-center gap-3">{right}</div>}
  </div>
);
