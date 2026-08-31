import React from 'react';
import { cx } from './cx';

/* ═══════════════════════════════════════════════════════════════════════════
   PAGE HEADER
   A screen that opens straight onto a KPI grid gives the reader no anchor —
   no name for what they are looking at, and no statement of how fresh it is.
   On a surface that drives capital decisions, provenance is part of the
   design, so the source systems and their stamp live here in the header.
   ═══════════════════════════════════════════════════════════════════════════ */

export interface PageHeaderProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Source tags, freshness stamp, actions. */
  right?: React.ReactNode;
  className?: string;
}

export const PageHeader = ({ title, subtitle, right, className }: PageHeaderProps) => (
  <div className={cx('flex flex-wrap items-end justify-between gap-x-6 gap-y-3', className)}>
    <div className="min-w-0">
      <h1 className="font-heading text-[20px] font-semibold leading-tight tracking-[-0.015em] text-fg-primary">
        {title}
      </h1>
      {subtitle && <p className="mt-1 text-[12px] text-fg-tertiary">{subtitle}</p>}
    </div>
    {right && <div className="flex shrink-0 flex-wrap items-center gap-2">{right}</div>}
  </div>
);
