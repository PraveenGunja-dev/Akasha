import React from 'react';

/* The Executive dashboard's hero banner, shared so every screen opens the same
   way: the hero image fading in from the right, a two-part title whose second
   part carries the brand blue→purple gradient, and the brand gradient border
   that lights on hover. Markup and gradients match CEODashboard's banner. */
export default function HeroBanner({ part1, part2, sub, children, compact = false }: {
  part1: React.ReactNode;
  part2: React.ReactNode;
  sub?: React.ReactNode;
  /** Extra line under the subtitle (chips, facts). */
  children?: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <div className="group relative w-full cursor-default">
      <div className="absolute -inset-1 rounded-[20px] bg-gradient-to-r from-brand-blue via-brand-purple to-brand-pink opacity-0 blur transition duration-1000 group-hover:opacity-40 group-hover:duration-300" />
      <div className="relative rounded-2xl bg-border p-px transition-colors duration-300 group-hover:bg-gradient-to-r group-hover:from-brand-blue group-hover:via-brand-purple group-hover:to-brand-pink">
        <div className={`relative flex w-full shrink-0 items-center overflow-hidden rounded-[15px] bg-background shadow-sm ${compact ? 'min-h-28 sm:min-h-32' : 'min-h-36 sm:min-h-40'}`}>
          <img src="/akasha/hero1.png" alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover object-center" />
          <div className="pointer-events-none absolute inset-0"
            style={{ background: 'linear-gradient(90deg, var(--background) 0%, color-mix(in srgb, var(--background) 85%, transparent) 22%, color-mix(in srgb, var(--background) 45%, transparent) 38%, color-mix(in srgb, var(--background) 10%, transparent) 55%, transparent 70%)' }} />
          <div className="relative z-10 max-w-3xl px-6 py-5 drop-shadow-sm sm:px-10">
            <h1 className={`flex flex-wrap items-center gap-x-3 font-black leading-none tracking-tight transition-all duration-500 group-hover:drop-shadow-[0_0_15px_rgba(118,72,157,0.5)] ${compact ? 'mb-2 text-2xl sm:text-[34px]' : 'mb-3 text-3xl sm:text-[42px]'}`}>
              <span className="text-foreground transition-all duration-500 group-hover:text-brand-blue">{part1}</span>
              <span className="bg-gradient-to-r from-brand-blue to-brand-purple bg-clip-text text-transparent">{part2}</span>
            </h1>
            {sub && <p className="max-w-lg text-sm font-medium leading-relaxed text-muted-foreground sm:text-base">{sub}</p>}
            {children && <div className="mt-3">{children}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
