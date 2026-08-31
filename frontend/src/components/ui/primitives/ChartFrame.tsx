import React from 'react';
import { motion } from 'framer-motion';
import { Card, CardHeader, type CardHeaderProps } from './Card';
import { itemVariants } from './motion';
import { cx } from './cx';

/* ═══════════════════════════════════════════════════════════════════════════
   CHART FRAME
   Every chart on a screen gets the same frame: same header weight, same
   padding, same body height contract. Charts previously each declared their
   own card markup, so no two lined up.

   `height` sets the plot area, not the card — the header sits above it, so
   two frames side by side stay flush regardless of header wrapping.
   ═══════════════════════════════════════════════════════════════════════════ */

export interface ChartFrameProps extends CardHeaderProps {
  /** Plot-area height in px. Omit to fill the parent (flex-1). */
  height?: number;
  children: React.ReactNode;
  className?: string;
}

export const ChartFrame = ({ height, children, className, ...header }: ChartFrameProps) => (
  <motion.div variants={itemVariants} className={cx('flex', className)}>
    <Card pad="md" className="flex w-full flex-col">
      <CardHeader {...header} />
      <div
        className={cx('w-full min-w-0', height ? '' : 'min-h-[250px] flex-1')}
        style={height ? { height } : undefined}
      >
        {children}
      </div>
    </Card>
  </motion.div>
);
