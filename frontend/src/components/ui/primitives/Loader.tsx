import { cx } from './cx';

export type LoaderSize = 'sm' | 'md' | 'lg';

/* The app's one loading indicator: five bars that rise and fall while a ball
   climbs them (styles: .ak-loader in index.css, theme-aware, still under
   reduced motion). Use it for a page or section that is waiting on data;
   a button's own busy state keeps its small inline spinner.

   `label` is the line under it ("Loading EAC…"); `detail` a smaller second
   line. Both are optional - without a label the loader is announced as
   "Loading" to screen readers. */
export function Loader({
  size = 'md', label, detail, className, inline = false, invert = false,
}: {
  size?: LoaderSize; label?: React.ReactNode; detail?: React.ReactNode;
  className?: string;
  /** Light bars for a dark surface that ignores the theme (the slide viewer). */
  invert?: boolean;
  /** Sit in a row with text instead of centring in a block. */
  inline?: boolean;
}) {
  const mark = (
    <span className={cx('ak-loader', `ak-loader--${size}`, invert && 'ak-loader--invert')} aria-hidden="true">
      <span className="ak-loader__inner">
        <span className="ak-loader__bar" /><span className="ak-loader__bar" /><span className="ak-loader__bar" />
        <span className="ak-loader__bar" /><span className="ak-loader__bar" /><span className="ak-loader__ball" />
      </span>
    </span>
  );
  if (inline) {
    return (
      <span role="status" className={cx('inline-flex items-center gap-2.5', className)}>
        {mark}
        {label ? <span className="text-[13px] text-fg-secondary">{label}</span> : <span className="sr-only">Loading</span>}
      </span>
    );
  }
  return (
    <div role="status" className={cx('flex flex-col items-center justify-center gap-4 text-center', className)}>
      {mark}
      {label ? <p className="text-[14px] font-medium text-fg-primary">{label}</p> : <span className="sr-only">Loading</span>}
      {detail && <p className="-mt-2 max-w-sm text-[12px] leading-relaxed text-fg-tertiary">{detail}</p>}
    </div>
  );
}

export default Loader;
