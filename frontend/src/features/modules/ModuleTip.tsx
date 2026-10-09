import React, { useEffect, useState } from 'react';

/* The module tracker's tooltip: a card that opens on click (so it can be read
   and its figures copied), shared by the table, the site-progress panel and
   the delivery ledger so none of them falls back to the browser's title box.
   HelpCard is the layout for explanatory tooltips. */

/* ── Rich Tooltip Content Formatter with Vibrant Date & Days Styling ────── */
export function renderHighlightedText(rawText: string) {
  if (!rawText) return null;

  // Split into the remark vs its suggested action (both rule-based, written by the planning engine)
  const parts = rawText.split(/(?=💡 Suggested action:)/g);

  return (
    <div className="space-y-2">
      {parts.map((part, pIdx) => {
        const isSuggestion = part.trim().startsWith('💡 Suggested action:');
        const contentText = isSuggestion ? part.replace('💡 Suggested action:', '').trim() : part.trim();

        // Match exact DD-Mon-YY, Mon-YY, X days overdue, X days remaining, due today, gain X days, lead times, and plain days
        const regex = /(\b\d{1,2}-[A-Za-z]{3}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}\b|\b\d+\s*days?\s*(?:overdue|remaining)\b|\bdue\s*today\b|\bgain\s*\d+\s*days\b|\b\d+d\b|\b\d+\s*days\b)/gi;
        const tokens = contentText.split(regex);

        const renderedTokens = tokens.map((tok, tIdx) => {
          if (!tok) return null;
          // Exact date DD-Mon-YY (e.g. 20-Sep-26, 30-Apr-26)
          if (/^\d{1,2}-[A-Za-z]{3}-\d{2}$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-mono font-bold text-status-risk-fg bg-status-risk-bg border border-status-risk-border">
                {tok}
              </span>
            );
          }
          // Month-Year (e.g. Sep-26, May-26)
          if (/^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-mono font-bold text-status-healthy-fg bg-status-healthy-bg border border-status-healthy-border">
                {tok}
              </span>
            );
          }
          // X days overdue
          if (/days?\s*overdue/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-bold text-status-critical-fg bg-status-critical-bg border border-status-critical-border shadow-sm">
                ⚠️ {tok}
              </span>
            );
          }
          // X days remaining / due today
          if (/days?\s*remaining|due\s*today/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-bold text-cyan-300 bg-cyan-500/20 border border-cyan-500/40">
                ⏱️ {tok}
              </span>
            );
          }
          // gain X days
          if (/gain\s*\d+\s*days/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-bold text-status-healthy-fg bg-status-healthy-bg border border-status-healthy-border">
                ⚡ {tok}
              </span>
            );
          }
          // Lead time (e.g. 98d, 136d, 45d)
          if (/^\d+d$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1.5 py-0.5 mx-0.5 rounded font-mono font-bold text-status-ai-fg bg-status-ai-bg border border-status-ai-border">
                {tok}
              </span>
            );
          }
          // General days mention (e.g. 30 days, 45 days)
          if (/^\d+\s*days$/i.test(tok)) {
            return (
              <span key={tIdx} className="inline-block px-1 py-0.5 mx-0.5 rounded font-medium text-status-risk-fg bg-status-risk-bg border border-status-risk-border">
                {tok}
              </span>
            );
          }
          return <span key={tIdx}>{tok}</span>;
        });

        if (isSuggestion) {
          return (
            <div key={pIdx} className="mt-2.5 pt-2 border-t border-border-default bg-primary/10 -mx-1 px-3 py-2 rounded-lg border border-primary/30">
              <div className="flex items-center gap-1.5 text-[11px] font-bold text-status-risk-fg mb-1">
                <span>💡 Suggested action</span>
              </div>
              <div className="text-[11px] leading-relaxed text-fg-primary font-normal">
                {renderedTokens}
              </div>
            </div>
          );
        }

        return (
          <div key={pIdx} className="text-[11px] leading-relaxed text-fg-primary font-normal">
            {renderedTokens}
          </div>
        );
      })}
    </div>
  );
}

export function Tip({
  text,
  content,
  children,
  className = '',
  wide = false,
  width,
}: {
  text?: string | null;
  content?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  wide?: boolean;
  /** Card width in px; overrides the narrow / wide default. */
  width?: number;
}) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number; below: boolean }>({ x: 0, y: 0, below: false });
  const wrapRef = React.useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!show) return;
    const handleGlobalClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setShow(false);
      }
    };
    document.addEventListener('mousedown', handleGlobalClick);
    return () => document.removeEventListener('mousedown', handleGlobalClick);
  }, [show]);

  if (!text && !content) return <>{children}</>;

  const isDetailed = wide || (text && (text.length > 60 || text.includes('FTC') || text.includes('Suggested action')));
  const targetWidth = width ?? (isDetailed ? 900 : 260);

  const toggleTip = (e: React.MouseEvent) => {
    if (show) {
      setShow(false);
      return;
    }
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const vw = typeof window !== 'undefined' ? window.innerWidth : 1200;
    
    // Effective tooltip width clamped to available screen width
    const effectiveW = Math.min(targetWidth, vw - 32);
    const halfW = effectiveW / 2;

    // Ideal center over trigger element
    const idealX = rect.left + rect.width / 2;

    // Strictly clamp left position so [left - halfW, left + halfW] is fully within [16, vw - 16]
    const clampedX = Math.max(halfW + 16, Math.min(vw - halfW - 16, idealX));

    // Vertical placement: if element is near the top of viewport, render tooltip below.
    const clearanceThreshold = content ? 380 : (isDetailed ? 250 : 150);
    const showBelow = rect.top < clearanceThreshold;
    const targetY = showBelow ? rect.bottom + 8 : rect.top - 8;

    setPos({ x: clampedX, y: targetY, below: showBelow });
    setShow(true);
  };

  const vw = typeof window !== 'undefined' ? window.innerWidth : 1200;
  const renderWidth = Math.min(targetWidth, vw - 32);

  return (
    <span
      ref={wrapRef}
      className={`cursor-pointer ${className}`}
      onClick={toggleTip}
    >
      {children}
      {show && (
        <span
          style={{ left: pos.x, top: pos.y }}
          className={`fixed z-[9999] -translate-x-1/2 ${pos.below ? 'translate-y-0' : '-translate-y-full'} animate-[tipIn_150ms_ease-out]`}
          onClick={(e) => e.stopPropagation()}
        >
          <span
            style={{ width: 'max-content', maxWidth: `${renderWidth}px` }}
            className="block rounded-xl border border-border-default bg-popover/95 p-3.5 text-left text-[11px] font-medium leading-relaxed text-fg-primary shadow-lg shadow-black/10 backdrop-blur-md dark:shadow-black/40 whitespace-pre-line break-words cursor-auto"
          >
            {content ? content : text ? renderHighlightedText(text) : null}
          </span>
        </span>
      )}
    </span>
  );
}


/** Explanatory tooltip layout: what it is, the figures behind it, what to do,
    and where the data comes from. Every part but the title is optional. */
export function HelpCard({ title, children, facts, action, source }: {
  title: React.ReactNode;
  children?: React.ReactNode;
  facts?: [React.ReactNode, React.ReactNode][];
  action?: React.ReactNode;
  source?: React.ReactNode;
}) {
  return (
    <span className="flex flex-col gap-2 whitespace-normal">
      <span className="text-[12px] font-semibold leading-snug text-fg-primary">{title}</span>
      {children && <span className="text-[11px] font-normal leading-relaxed text-fg-secondary">{children}</span>}
      {facts && facts.length > 0 && (
        <span className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 rounded-lg bg-[var(--surface-sunken)] px-2.5 py-1.5 text-[10.5px]">
          {facts.map(([k, v], i) => (
            <React.Fragment key={i}>
              <span className="text-fg-secondary">{k}</span>
              <span className="text-right font-semibold tabular-nums text-fg-primary">{v}</span>
            </React.Fragment>
          ))}
        </span>
      )}
      {action && (
        <span className="rounded-lg border-l-2 border-primary bg-primary/5 px-2.5 py-1.5 text-[10.5px] font-normal leading-relaxed text-fg-primary">
          <span className="mr-1 font-semibold text-primary">What to do:</span>{action}
        </span>
      )}
      {source && <span className="text-[9.5px] font-normal leading-snug text-fg-tertiary">Source: {source}</span>}
    </span>
  );
}
