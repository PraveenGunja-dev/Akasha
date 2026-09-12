import React, { useEffect, useRef } from 'react';
import { X, ChevronLeft } from 'lucide-react';
import { cx } from '../../../components/ui/primitives';

/* Slide-over. One implementation for every drill-down so they open, stack
   and close identically. Focus moves in on open and returns to the opener on
   close; Esc closes the top drawer only. */
export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  eyebrow?: React.ReactNode;
  /** Shown when another drawer sits beneath this one. */
  canGoBack?: boolean;
  width?: 'md' | 'lg' | 'xl';
  actions?: React.ReactNode;
  children: React.ReactNode;
  /** Stack depth, for offset and z-order. */
  depth?: number;
}

const W = { md: 'w-full sm:w-[480px]', lg: 'w-full sm:w-[640px]', xl: 'w-full sm:w-[800px]' };

export const Drawer = ({ open, onClose, title, eyebrow, canGoBack, width = 'lg', actions, children, depth = 0 }: DrawerProps) => {
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    const el = panel.current;
    const t = setTimeout(() => el?.querySelector<HTMLElement>('[data-autofocus]')?.focus() ?? el?.focus(), 30);
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } };
    el?.addEventListener('keydown', onKey);
    return () => { clearTimeout(t); el?.removeEventListener('keydown', onKey); (opener.current as HTMLElement | null)?.focus?.(); };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90]" style={{ zIndex: 90 + depth }} role="presentation">
      <div className="absolute inset-0 bg-neutral-950/30" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        tabIndex={-1}
        className={cx('absolute inset-y-0 right-0 flex max-w-full flex-col border-l border-border-subtle bg-surface-1 shadow-overlay outline-none', W[width], 'animate-in slide-in-from-right duration-200')}
        style={{ transform: depth ? `translateX(-${Math.min(depth, 2) * 12}px)` : undefined }}
      >
        <header className="flex shrink-0 items-start gap-3 border-b border-border-subtle px-5 py-4">
          {canGoBack && (
            <button type="button" onClick={onClose} className="mt-0.5 rounded-md p-1 text-fg-tertiary hover:bg-surface-sunken hover:text-fg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Back">
              <ChevronLeft className="h-4 w-4" />
            </button>
          )}
          <div className="min-w-0 flex-1">
            {eyebrow && <div className="section-label mb-1">{eyebrow}</div>}
            <h2 className="truncate text-[16px] font-semibold leading-snug text-fg-primary">{title}</h2>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-fg-tertiary hover:bg-surface-sunken hover:text-fg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {actions && <footer className="flex shrink-0 flex-wrap items-center gap-2 border-t border-border-subtle bg-surface-0 px-5 py-3">{actions}</footer>}
      </div>
    </div>
  );
};

/* ── Small building blocks shared by the drawers ── */

export const Btn = ({ variant = 'secondary', className, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger' }) => (
  <button
    type="button"
    className={cx(
      'inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
      variant === 'primary' && 'bg-primary text-primary-foreground hover:bg-primary-700',
      variant === 'secondary' && 'border border-border-default bg-surface-1 text-fg-primary hover:bg-surface-sunken',
      variant === 'ghost' && 'text-fg-secondary hover:bg-surface-sunken hover:text-fg-primary',
      variant === 'danger' && 'border border-status-critical-border bg-status-critical-bg text-status-critical-fg hover:brightness-95',
      className,
    )}
    {...rest}
  />
);

export const Stat = ({ label, value, sub, className }: { label: React.ReactNode; value: React.ReactNode; sub?: React.ReactNode; className?: string }) => (
  <div className={cx('rounded-md border border-border-subtle bg-surface-0 px-3 py-2.5', className)}>
    <div className="text-[12px] text-fg-tertiary">{label}</div>
    <div className="mt-0.5 text-[18px] font-semibold tabular-nums leading-tight text-fg-primary">{value}</div>
    {sub && <div className="mt-0.5 text-[12px] text-fg-secondary">{sub}</div>}
  </div>
);

export const Section = ({ title, right, children }: { title: React.ReactNode; right?: React.ReactNode; children: React.ReactNode }) => (
  <section className="mt-5 first:mt-0">
    <div className="mb-2 flex items-center justify-between">
      <h3 className="text-[13px] font-semibold text-fg-primary">{title}</h3>
      {right}
    </div>
    {children}
  </section>
);

export const NotAvailable = ({ what, why }: { what: string; why: string }) => (
  <div className="rounded-md border border-dashed border-border-default px-3 py-2 text-[12px] text-fg-tertiary">
    <span className="font-medium text-fg-secondary">{what}</span> — not available. {why}
  </div>
);

export const Skeleton = ({ className }: { className?: string }) => <div className={cx('animate-pulse rounded-md bg-surface-sunken', className)} aria-hidden />;

export const ErrorBox = ({ message, onRetry }: { message: string; onRetry?: () => void }) => (
  <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-status-critical-border bg-status-critical-bg px-3 py-2.5 text-[13px] text-status-critical-fg">
    <span>Unable to load SAP procurement data. <span className="opacity-80">{message}</span></span>
    {onRetry && <Btn variant="secondary" onClick={onRetry}>Retry</Btn>}
  </div>
);

export const Empty = ({ message, action }: { message: string; action?: React.ReactNode }) => (
  <div className="flex h-full min-h-[120px] flex-col items-center justify-center gap-2 text-center text-[13px] text-fg-tertiary">
    <span>{message}</span>{action}
  </div>
);
