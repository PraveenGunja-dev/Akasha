import React, { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';

/* ═══════════════════════════════════════════════════════════════════════════
   DRAWER — one right-side panel shared by insight detail, project drill-down,
   actions and Ask AI, so those four never drift into four different shells.

   Carries the accessibility the brief asks for: role="dialog", labelled by its
   own heading, Escape to close, focus moved in on open and returned to the
   trigger on close, and a focus trap so Tab cannot wander behind the overlay.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function Drawer({
  open, onClose, title, subtitle, width = 'max-w-xl', children, footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: React.ReactNode;
  width?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreTo = useRef<HTMLElement | null>(null);
  /* useId, not a ref: a ref read during render is both a lint error and a
     correctness hazard, and Math.random() in render is impure. */
  const headingId = useId();

  useEffect(() => {
    if (!open) return;
    restoreTo.current = document.activeElement as HTMLElement;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose(); return; }
      if (e.key !== 'Tab' || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };

    document.addEventListener('keydown', onKey);
    const t = window.setTimeout(() => {
      panelRef.current?.querySelector<HTMLElement>('button, [href], input, textarea')?.focus();
    }, 60);

    return () => {
      document.removeEventListener('keydown', onKey);
      window.clearTimeout(t);
      restoreTo.current?.focus?.();
    };
  }, [open, onClose]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[120]">
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="absolute inset-0 bg-black/35 backdrop-blur-[2px]"
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={headingId}
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'tween', ease: [0.4, 0, 0.2, 1], duration: 0.28 }}
            className={`absolute inset-y-0 right-0 flex w-full ${width} flex-col border-l border-border bg-card shadow-2xl`}
          >
            <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-5 py-4">
              <div className="min-w-0">
                <h2 id={headingId} className="text-[15px] font-bold leading-tight text-foreground">
                  {title}
                </h2>
                {subtitle && <div className="mt-1 text-[11px] text-fg-tertiary">{subtitle}</div>}
              </div>
              <button
                onClick={onClose}
                aria-label="Close panel"
                className="shrink-0 rounded-lg p-1.5 text-fg-tertiary transition-colors hover:bg-muted hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </header>

            <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>

            {footer && (
              <footer className="shrink-0 border-t border-border bg-muted/30 px-5 py-3">{footer}</footer>
            )}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
