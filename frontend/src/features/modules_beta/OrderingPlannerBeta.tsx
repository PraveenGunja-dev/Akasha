/* BETA copy of the Ordering Schedule (features/modules/OrderingPlanner.tsx).
   Everything in features/modules_beta is a standalone replica so changes can
   be trialled here without touching the live page; reached from the header's
   Beta button.

   Two views of the same schedule: the current one (ordered against each
   phase's FTC milestone) and Advanced AI planning (branch orderingpoc) - the
   same grid with site-driven columns from each block's P6 progress, and an
   optional weather impact. The choice is kept in the address
   (?plan=advanced&weather=1) so a link opens the same view. */
import { useSearchParams } from 'react-router-dom';
import { CloudRain } from 'lucide-react';
import { cx } from '../../components/ui/primitives';
import ModuleDeliveriesPage from './ModuleDeliveriesPage';

export default function OrderingPlannerBeta() {
  const [params, setParams] = useSearchParams();
  const view = params.get('plan') === 'advanced' ? 'advanced' : 'current';
  const weather = view === 'advanced' && params.get('weather') === '1';
  const choose = (v: 'current' | 'advanced') => setParams((p) => {
    if (v === 'advanced') p.set('plan', 'advanced'); else { p.delete('plan'); p.delete('weather'); }
    return p;
  }, { replace: true });
  const toggleWeather = () => setParams((p) => {
    if (weather) p.delete('weather'); else p.set('weather', '1');
    return p;
  }, { replace: true });

  const tab = (v: 'current' | 'advanced', label: string, hint: string) => (
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label="Ordering plan" className="inline-flex w-fit gap-1 rounded-xl border border-border-subtle bg-surface-sunken p-1">
          {tab('current', 'Current schedule', 'Ordered for each phase’s charging date')}
          {tab('advanced', 'Advanced AI planning', 'Site-driven, from each block’s progress in P6')}
        </div>
        {view === 'advanced' && (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[12px] text-fg-secondary">
              <span className="font-semibold text-status-ai-fg">✦ Purple = new, site-driven.</span> Click a purple cell for the detail.
              {weather && <span className="ml-1 font-semibold text-brand-blue">Blue = days the site's weather adds.</span>}
            </span>
            <button type="button" role="switch" aria-checked={weather} onClick={toggleWeather}
              className={cx('inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-[12px] font-medium transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50',
                weather ? 'border-brand-blue/40 bg-brand-blue/10 text-brand-blue' : 'border-border-subtle bg-surface-1 text-fg-secondary hover:text-fg-primary')}>
              <CloudRain className="h-3.5 w-3.5" strokeWidth={1.75} />
              Weather impact
              <span className={cx('relative h-4 w-7 rounded-full transition-colors', weather ? 'bg-brand-blue' : 'bg-border-strong')} aria-hidden>
                <span className={cx('absolute top-0.5 h-3 w-3 rounded-full bg-surface-1 shadow-sm transition-[left]', weather ? 'left-3.5' : 'left-0.5')} />
              </span>
            </button>
          </div>
        )}
      </div>
      <ModuleDeliveriesPage advanced={view === 'advanced'} weather={weather} />
    </div>
  );
}
