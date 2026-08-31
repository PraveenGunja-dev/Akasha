import React, { useEffect, useRef, useState } from 'react';
import { Info } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { cx } from './cx';

/* ═══════════════════════════════════════════════════════════════════════════
   INFO TIP
   Explains what a figure means, for an executive who did not build it.

   Rebuilt onto tokens: the previous version was a frosted `bg-white/95
   backdrop-blur-xl` panel with a 32px custom drop shadow and hardcoded
   gray-200/gray-700 borders — glassmorphism the design brief explicitly bans,
   and a surface that read differently in dark mode from every other popover.
   It is now the standard raised surface.
   ═══════════════════════════════════════════════════════════════════════════ */

export type TipAlign = 'left' | 'center' | 'right';

const PANEL_ALIGN: Record<TipAlign, string> = {
  left: 'left-0 -translate-x-2',
  center: 'left-1/2 -translate-x-1/2',
  right: 'right-0 translate-x-2',
};

const ARROW_ALIGN: Record<TipAlign, string> = {
  left: 'left-4',
  center: 'left-1/2 -translate-x-1/2',
  right: 'right-4',
};

export const InfoTip = ({ info, align = 'center' }: { info: React.ReactNode; align?: TipAlign }) => {
  const [isOpen, setIsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const onPointerDown = (e: MouseEvent) => {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        triggerRef.current && !triggerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [isOpen]);

  return (
    <div className="relative" style={{ zIndex: isOpen ? 50 : 1 }}>
      <button
        ref={triggerRef}
        type="button"
        aria-label="What this measures"
        onClick={(e) => { e.stopPropagation(); setIsOpen((v) => !v); }}
        onMouseEnter={() => setIsOpen(true)}
        onMouseLeave={() => setIsOpen(false)}
        className="rounded-full p-0.5 transition-colors hover:bg-primary/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Info className="h-3 w-3 text-fg-tertiary transition-colors hover:text-primary" strokeWidth={1.5} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            ref={panelRef}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12, ease: [0.2, 0, 0, 1] }}
            style={{ zIndex: 9999 }}
            className={cx(
              'surface-raised absolute top-full mt-2 w-64 p-3 text-left pointer-events-auto',
              PANEL_ALIGN[align]
            )}
          >
            <div
              className={cx(
                'absolute -top-1.5 h-3 w-3 rotate-45 border-l border-t border-border-subtle bg-surface-2',
                ARROW_ALIGN[align]
              )}
            />
            <div className="relative z-10 text-[11px] font-normal normal-case leading-relaxed tracking-normal text-fg-secondary">
              {info}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
