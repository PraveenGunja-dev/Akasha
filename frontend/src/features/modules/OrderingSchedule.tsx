/* The Ordering Schedule with its "Advanced AI planning" switch. Off (the
   default): the standard schedule. On: the same schedule with the
   site-driven columns added and the site-driven figure beside the standard
   one (AdvancedColumns), tinted as AI. The weather switch, available with
   Advanced on, adds in blue the days the site's weather adds or saves.
   Both are kept in the address (?advanced=1&weather=1) so a link opens the
   same view. */
import { useSearchParams } from 'react-router-dom';
import { CloudRain, Sparkles } from 'lucide-react';
import { cx } from '../../components/ui/primitives';
import ModuleDeliveriesPage from './ModuleDeliveriesPage';

function Switch({ on, onClick, icon: Icon, label, tone }: {
  on: boolean; onClick: () => void; icon: typeof Sparkles; label: string; tone: 'ai' | 'blue';
}) {
  const onCls = tone === 'ai'
    ? 'border-status-ai-border bg-status-ai-bg text-status-ai-fg'
    : 'border-brand-blue/40 bg-brand-blue/10 text-brand-blue';
  const track = tone === 'ai' ? 'bg-status-ai-solid' : 'bg-brand-blue';
  return (
    <button type="button" role="switch" aria-checked={on} onClick={onClick}
      className={cx('inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-[12px] font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50',
        on ? onCls : 'border-border-subtle bg-surface-1 text-fg-secondary hover:text-fg-primary')}>
      <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
      {label}
      <span className={cx('relative h-4 w-7 rounded-full transition-colors', on ? track : 'bg-border-strong')} aria-hidden>
        <span className={cx('absolute top-0.5 h-3 w-3 rounded-full bg-surface-1 shadow-sm transition-[left]', on ? 'left-3.5' : 'left-0.5')} />
      </span>
    </button>
  );
}

export default function OrderingSchedule() {
  const [params, setParams] = useSearchParams();
  const advanced = params.get('advanced') === '1';
  const weather = advanced && params.get('weather') === '1';
  const flip = (key: string, on: boolean) => setParams(p => {
    if (on) p.delete(key); else p.set(key, '1');
    if (key === 'advanced' && on) p.delete('weather');
    return p;
  }, { replace: true });

  return (
    <div className="flex w-full flex-col gap-3">
      <div className="flex flex-wrap items-center justify-end gap-3">
        {advanced && (
          <span className="text-[12px] text-fg-secondary">
            <span className="font-semibold text-status-ai-fg">✦ Purple = new, site-driven</span> - from each block's progress in P6.
            Click a purple cell for the detail.
            {weather && <span className="ml-1 font-semibold text-brand-blue">Blue = days the site's weather adds.</span>}
          </span>
        )}
        {advanced && <Switch on={weather} onClick={() => flip('weather', weather)} icon={CloudRain} label="Weather impact" tone="blue" />}
        <Switch on={advanced} onClick={() => flip('advanced', advanced)} icon={Sparkles} label="Advanced AI planning" tone="ai" />
      </div>
      <ModuleDeliveriesPage advanced={advanced} weather={weather} />
    </div>
  );
}
