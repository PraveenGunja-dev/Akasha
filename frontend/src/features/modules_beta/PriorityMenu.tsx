/* BETA: the menu behind a Priority (AI) pill. Shows what the AI decided and
   lets the user set the priority used for vendor allocation (P1 / P2 /
   Standard), or go back to the AI's. Changing it re-levels the grid in place
   (vendorLeveling.ts) - nothing is reloaded. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, RotateCcw, Sparkles } from 'lucide-react';
import { cx } from '../../components/ui/primitives';

export type PlanPriority = 'P1' | 'P2' | 'standard';

const OPTIONS: { value: PlanPriority; label: string; hint: string; dot: string }[] = [
  { value: 'P1', label: 'P1', hint: 'First claim on a full vendor month', dot: 'bg-status-critical-solid' },
  { value: 'P2', label: 'P2', hint: 'After P1', dot: 'bg-status-risk-solid' },
  { value: 'standard', label: 'Standard', hint: 'After P1 and P2', dot: 'bg-brand-blue' },
];

export default function PriorityMenu({ anchor, projectName, current, aiClass, aiDetail, overridden, onPick, onReset, onDetails, onClose }: {
  anchor: HTMLElement;
  projectName: string;
  current: PlanPriority;
  /** The AI's class, '' when the AI did not score this row. */
  aiClass: string;
  /** One line on the AI's call (score or confidence). */
  aiDetail?: string;
  overridden: boolean;
  onPick: (p: PlanPriority) => void;
  onReset: () => void;
  onDetails?: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  // Below the pill, kept inside the viewport.
  useLayoutEffect(() => {
    const r = anchor.getBoundingClientRect();
    const w = 248, h = ref.current?.offsetHeight ?? 260;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    const below = r.bottom + 6;
    setPos({ left, top: below + h > window.innerHeight - 8 ? Math.max(8, r.top - h - 6) : below });
  }, [anchor]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node) && !anchor.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { onClose(); anchor.focus(); } };
    const onScroll = (e: Event) => { if (!ref.current?.contains(e.target as Node)) onClose(); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onClose);
    ref.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus();
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onClose);
    };
  }, [anchor, onClose]);

  return createPortal(
    <div ref={ref} role="dialog" aria-label={`Priority for ${projectName}`}
      style={{ position: 'fixed', top: pos?.top ?? -9999, left: pos?.left ?? -9999, width: 248 }}
      className="z-[200] rounded-lg border border-border bg-card p-2 text-left shadow-lg">
      <div className="px-1.5 pb-1.5">
        <div className="text-[11px] font-semibold text-fg-primary">Priority for vendor allocation</div>
        <div className="truncate text-[10px] text-fg-tertiary" title={projectName}>{projectName}</div>
      </div>

      <div className="mb-1.5 flex items-start gap-1.5 rounded-md bg-[var(--status-ai-bg)] px-2 py-1.5 text-[10px] text-status-ai-fg">
        <Sparkles className="mt-px h-3 w-3 shrink-0" />
        <span>
          {aiClass ? <>AI priority <b>{aiClass}</b>{aiDetail ? ` · ${aiDetail}` : ''}</> : 'Not scored by the AI'}
          {onDetails && aiClass && (
            <button type="button" onClick={() => { onClose(); onDetails(); }}
              className="ml-1 font-semibold underline underline-offset-2 hover:no-underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--status-ai-solid)]">
              Why?
            </button>
          )}
        </span>
      </div>

      <div role="radiogroup" aria-label="Priority" className="space-y-0.5">
        {OPTIONS.map(o => {
          const on = o.value === current;
          return (
            <button key={o.value} type="button" role="radio" aria-checked={on}
              onClick={() => { if (!on) onPick(o.value); onClose(); }}
              className={cx('flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50',
                on ? 'bg-muted' : 'hover:bg-muted/60')}>
              <span className={cx('h-2 w-2 shrink-0 rounded-full', o.dot)} />
              <span className="flex-1">
                <span className="block text-[11px] font-semibold text-fg-primary">{o.label}</span>
                <span className="block text-[10px] text-fg-tertiary">{o.hint}</span>
              </span>
              {on && <Check className="h-3.5 w-3.5 text-fg-secondary" />}
            </button>
          );
        })}
      </div>

      {overridden && (
        <button type="button" onClick={() => { onReset(); onClose(); }}
          className="mt-1.5 flex w-full items-center gap-1.5 border-t border-border-subtle px-2 pt-1.5 text-[10px] font-semibold text-fg-secondary hover:text-fg-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-blue/50">
          <RotateCcw className="h-3 w-3" />
          {aiClass ? `Back to the AI's ${aiClass}` : 'Back to the plan default'}
        </button>
      )}
      <p className="mt-1.5 px-1 text-[9.5px] leading-snug text-fg-tertiary">
        Decides who keeps a month when the vendor's monthly allocation is full. The table re-plans at once.
      </p>
    </div>,
    document.body,
  );
}
