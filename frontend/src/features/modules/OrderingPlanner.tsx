/* The Ordering Schedule page with its two plans side by side while the
   block-level method is being compared: the current schedule (ordered against
   each phase's FTC milestone) and the new block plan. The choice is kept in
   the address (?plan=block) so a link opens the same view. */
import { useSearchParams } from 'react-router-dom';
import { cx } from '../../components/ui/primitives';
import ModuleDeliveriesPage from './ModuleDeliveriesPage';
import BlockPlanView from './BlockPlanView';

export default function OrderingPlanner() {
  const [params, setParams] = useSearchParams();
  const view = params.get('plan') === 'block' ? 'block' : 'current';
  const choose = (v: 'current' | 'block') => setParams((p) => {
    if (v === 'block') p.set('plan', 'block'); else p.delete('plan');
    return p;
  }, { replace: true });

  const tab = (v: 'current' | 'block', label: string, hint: string) => (
    <button type="button" role="tab" aria-selected={view === v} onClick={() => choose(v)}
      className={cx('flex flex-col items-start rounded-lg px-3.5 py-2 text-left transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50',
        view === v ? 'bg-surface-1 shadow-sm ring-1 ring-border-subtle' : 'hover:bg-surface-1/60')}>
      <span className={cx('text-[13px] font-semibold', view === v ? 'text-fg-primary' : 'text-fg-secondary')}>{label}</span>
      <span className="text-[11px] text-fg-tertiary">{hint}</span>
    </button>
  );

  return (
    <div className="flex w-full flex-col gap-4">
      <div role="tablist" aria-label="Ordering plan" className="inline-flex w-fit gap-1 rounded-xl border border-border-subtle bg-surface-sunken p-1">
        {tab('current', 'Current schedule', 'Ordered for each phase’s charging date')}
        {tab('block', 'Block plan · new', 'Ordered block by block as the site builds')}
      </div>
      {view === 'block' ? <BlockPlanView /> : <ModuleDeliveriesPage />}
    </div>
  );
}
