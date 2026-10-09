import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, AlertTriangle, Battery, Sun, Wind, ArrowLeft, Presentation, ChevronRight, BarChart3, ShieldCheck } from 'lucide-react';
import { cx } from '../../components/ui/primitives';
import CPAGSlideViewer from '../projects/CPAGSlides';
import { useCPAGPack } from '../projects/useCPAGPack';

import { Loader as AkLoader } from '../../components/ui/primitives';
type ViewState = 'directory' | 'portfolio_select' | 'region_select' | 'viewer';
type Scope = 'solar' | 'wind' | 'bess' | null;

/* What each portfolio's pack covers today. Solar is the Rajasthan pack
   (routers/solar.py) and Wind the Mundra North pack (routers/wind.py); the
   other regions are named so it is clear they are coming, not missing. */
type Region = { name: string; live: boolean; detail?: string };
const REGIONS: Record<'bess' | 'solar' | 'wind', Region[]> = {
  bess: [{ name: '6 projects', live: true }],
  solar: [
    { name: 'Rajasthan', live: true, detail: 'Rajasthan solar projects' },
    { name: 'Khavda', live: false, detail: 'Pack in preparation' },
  ],
  wind: [
    { name: 'Mundra', live: true, detail: 'Mundra North wind project' },
    { name: 'Khavda', live: false, detail: 'Pack in preparation' },
    { name: 'Mandvi', live: false, detail: 'Pack in preparation' },
  ],
};
const SCOPE_NAME = { solar: 'Solar', wind: 'Wind', bess: 'BESS' } as const;

const RegionChips: React.FC<{ regions: Region[] }> = ({ regions }) => (
  <span className="mt-3 flex flex-wrap gap-1.5">
    {regions.map((r) => (
      <span key={r.name}
        className={cx('inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium',
          r.live ? 'border-status-healthy-border bg-status-healthy-bg text-status-healthy-fg'
            : 'border-border-subtle text-fg-tertiary')}>
        {r.live && <span className="h-1.5 w-1.5 rounded-full bg-status-healthy-solid" />}
        {r.name}{!r.live && ' · soon'}
      </span>
    ))}
  </span>
);

const ScopeCard: React.FC<{
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  title: string;
  detail: string;
  onClick?: () => void;
  disabled?: boolean;
  extraAction?: React.ReactNode;
  regions?: Region[];
}> = ({ icon: Icon, title, detail, onClick, disabled, extraAction, regions }) => (
  <button
    onClick={disabled ? undefined : onClick}
    disabled={disabled}
    className={cx(
      "group flex flex-col items-start gap-3 rounded-xl border p-5 text-left transition-colors duration-200",
      disabled
        ? "cursor-not-allowed border-border-subtle bg-surface-sunken/60"
        : "border-border-subtle bg-surface-1 hover:border-brand-blue/50 hover:bg-surface-sunken/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue"
    )}>
    <span className={cx("rounded-lg p-2.5", disabled ? "bg-surface-sunken" : "bg-brand-blue/10")}>
      <Icon className={cx("h-5 w-5", disabled ? "text-fg-disabled" : "text-brand-blue")} strokeWidth={1.5} />
    </span>
    <span>
      <span className="flex items-center gap-2 text-[15px] font-semibold text-fg-primary">
        {title}
        {disabled && <span className="rounded border border-border-subtle px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-fg-tertiary">Soon</span>}
      </span>
      <span className="mt-1 block text-[13px] leading-relaxed text-fg-secondary">{detail}</span>
      {regions && <RegionChips regions={regions} />}
      {extraAction && (
        <div className="mt-4" onClick={(e) => e.stopPropagation()}>
          {extraAction}
        </div>
      )}
    </span>
  </button>
);

export default function ReportsInsights(props: any) {
  /* `allowedScopes`: the CPAG packs this user may open (portfolio-scoped
     dashboards pass the user's own). Omitted = every pack, as on Executive.
     The server refuses the others regardless. */
  const allowed: string[] | undefined = props.allowedScopes;
  const canOpen = (sc: 'solar' | 'wind' | 'bess') => !allowed || allowed.includes(sc);
  const [view, setView] = useState<ViewState>('directory');
  const [scope, setScope] = useState<Scope>(null);
  const [region, setRegion] = useState<string | null>(null);
  // A portfolio with more than one region asks which pack to open first;
  // one with a single pack (BESS) opens straight away.
  const choosePortfolio = (sc: Exclude<Scope, null>) => {
    setScope(sc);
    const rs = REGIONS[sc];
    if (rs.length > 1) { setRegion(null); setView('region_select'); }
    else { setRegion(rs[0].name); setView('viewer'); }
  };

  /* The pack is the downloadable deck's own pages, rendered by the
     backend from the approved template. */
  const pack = useCPAGPack(view === 'viewer' && (scope === 'bess' || scope === 'wind' || scope === 'solar'), scope);
  const { loading, error, retry } = pack;

  // Seconds the pack has been building, so a long render reads as progress,
  // not a frozen screen; past 3 minutes the server is likely stuck.
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!loading) { setElapsed(0); return; }
    const t0 = Date.now();
    const id = window.setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [loading]);
  const mmss = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;

  return (
    <div className={cx(
      "flex flex-col mx-auto animate-in fade-in duration-500 pb-6 pt-2 h-full min-h-[calc(100vh-100px)]",
      view === 'viewer' ? "w-full" : "w-full gap-6"
    )}>

      <AnimatePresence mode="wait">
        {view === 'directory' && (
          <motion.div
            key="directory"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]"
          >
            {/* The one live report leads, with the deck's own cover as its image;
                what is still being built sits below as a quiet list rather than
                as greyed-out cards that look broken. */}
            <button
              type="button"
              onClick={() => setView('portfolio_select')}
              className="bento-card group grid w-full overflow-hidden text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]"
            >
              <div className="relative h-44 overflow-hidden border-b border-border-subtle bg-surface-sunken md:h-full md:min-h-[240px] md:border-b-0 md:border-r">
                <img
                  src="/akasha/cpag/cover-photo.jpg"
                  alt="Cover of the CPAG review pack"
                  loading="lazy"
                  className="absolute inset-0 h-full w-full object-cover object-bottom transition-transform duration-500 group-hover:scale-[1.03]"
                />
                <span className="absolute left-3 top-3 inline-flex items-center gap-1.5 rounded-md bg-black/55 px-2 py-1 text-[11px] font-semibold text-white backdrop-blur-sm">
                  <span className="h-1.5 w-1.5 rounded-full bg-status-healthy-solid" /> Live · {(['bess', 'solar', 'wind'] as const).filter(canOpen).map(sc => SCOPE_NAME[sc]).join(' · ') || 'No pack for your portfolios'}
                </span>
              </div>

              <div className="flex flex-col p-6">
                <p className="section-label text-brand-blue">Governance deck</p>
                <h3 className="mt-1.5 text-xl font-semibold tracking-tight text-fg-primary">CPAG Review Pack</h3>
                <p className="mt-2 text-sm leading-relaxed text-fg-secondary">
                  The steering-committee deck, built page for page from live data. Review it on
                  screen, then download the same file as PowerPoint.
                </p>

                <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-border-subtle pt-4 text-[13px]">
                  <div>
                    <dt className="text-[11px] font-medium uppercase tracking-wide text-fg-tertiary">Sources</dt>
                    <dd className="mt-0.5 font-medium text-fg-primary">P6 · SAP · Pulse</dd>
                  </div>
                  <div>
                    <dt className="text-[11px] font-medium uppercase tracking-wide text-fg-tertiary">Portfolios</dt>
                    <dd className="mt-1 space-y-0.5 text-fg-primary">
                      {([['BESS', REGIONS.bess, 'bess'], ['Solar', REGIONS.solar, 'solar'], ['Wind', REGIONS.wind, 'wind']] as [string, Region[], 'bess' | 'solar' | 'wind'][])
                        .filter(([, , sc]) => canOpen(sc)).map(([name, rs]) => (
                        <div key={name} className="flex flex-wrap items-baseline gap-x-1.5">
                          <span className="w-11 shrink-0 font-medium">{name}</span>
                          <span className="text-fg-secondary">{rs.filter((r) => r.live).map((r) => r.name).join(', ')}</span>
                          {rs.some((r) => !r.live) && (
                            <span className="text-fg-tertiary">· {rs.filter((r) => !r.live).map((r) => r.name).join(', ')} soon</span>
                          )}
                        </div>
                      ))}
                    </dd>
                  </div>
                </dl>

                <span className="mt-6 inline-flex w-fit items-center gap-1.5 rounded-lg bg-brand-blue px-4 py-2 text-sm font-semibold text-white transition-colors group-hover:bg-brand-blue/90">
                  <Presentation className="h-4 w-4" strokeWidth={1.75} /> Open review pack
                  <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </span>
              </div>
            </button>

            <section>
              <h4 className="section-label mb-2 text-fg-tertiary">In preparation</h4>
              <ul className="bento-card divide-y divide-border-subtle">
                {[
                  { icon: BarChart3, title: 'Financial Summary', detail: 'Capital expenditure, budget variance and cash-flow requirement across clusters.' },
                  { icon: ShieldCheck, title: 'HSE & Quality Audit', detail: 'Safety metrics, incidents and quality non-conformances for active sites.' },
                ].map(({ icon: Icon, title, detail }) => (
                  <li key={title} className="flex items-start gap-4 px-5 py-3.5">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-sunken">
                      <Icon className="h-[18px] w-[18px] text-fg-tertiary" strokeWidth={1.5} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-fg-primary">{title}</p>
                      <p className="text-[13px] leading-snug text-fg-secondary">{detail}</p>
                    </div>
                    <span className="shrink-0 rounded border border-border-subtle px-2 py-0.5 text-[11px] font-medium text-fg-tertiary">Coming soon</span>
                  </li>
                ))}
              </ul>
            </section>
          </motion.div>
        )}

        {view === 'portfolio_select' && (
          <motion.div
            key="portfolio_select"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2 }}
            className="bento-card overflow-hidden flex flex-col"
          >
            <div className="px-6 py-6 border-b border-border-subtle bg-surface-sunken/40">
              <button
                onClick={() => setView('directory')}
                className="flex items-center gap-1.5 text-sm font-semibold text-fg-secondary hover:text-brand-blue transition-colors mb-4"
              >
                <ArrowLeft className="w-4 h-4" /> Back to Directory
              </button>

              <div>
                <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand-blue mb-1">
                  CPAG review pack
                </p>
                <h3 className="text-xl font-semibold text-fg-primary tracking-tight">
                  Select Portfolio
                </h3>
                <p className="mt-1 text-sm text-fg-secondary">
                  Choose a portfolio to view its complete CPAG pack, generated live from execution telemetry.
                </p>
              </div>
            </div>

            <div className="p-6 grid grid-cols-1 gap-5 sm:grid-cols-3">
              {allowed && allowed.length === 0 && (
                <p className="text-sm text-fg-secondary sm:col-span-3">
                  No CPAG pack covers your portfolios yet. Packs exist for Solar Rajasthan, Wind (Mundra North) and BESS.
                </p>
              )}
              {canOpen('solar') && <ScopeCard
                icon={Sun}
                title="Solar Portfolio"
                detail="The Rajasthan solar pack, built from P6, SAP and Pulse."
                regions={REGIONS.solar}
                onClick={() => choosePortfolio('solar')}
              />}
              {canOpen('wind') && <ScopeCard
                icon={Wind}
                title="Wind Portfolio"
                detail="The Mundra North wind pack, built from P6, SAP and Pulse."
                regions={REGIONS.wind}
                onClick={() => choosePortfolio('wind')}
              />}
              {canOpen('bess') && <ScopeCard
                icon={Battery}
                title="BESS Portfolio"
                detail="The whole pack across all six BESS projects, plus the combined corporate order book."
                regions={REGIONS.bess}
                onClick={() => choosePortfolio('bess')}
              />}
            </div>
          </motion.div>
        )}

        {view === 'region_select' && scope && (
          <motion.div
            key="region_select"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2 }}
            className="bento-card overflow-hidden flex flex-col"
          >
            <div className="px-6 py-6 border-b border-border-subtle bg-surface-sunken/40">
              <button
                onClick={() => { setScope(null); setView('portfolio_select'); }}
                className="flex items-center gap-1.5 text-sm font-semibold text-fg-secondary hover:text-brand-blue transition-colors mb-4"
              >
                <ArrowLeft className="w-4 h-4" /> Back to portfolios
              </button>
              <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand-blue mb-1">
                CPAG review pack · {SCOPE_NAME[scope]}
              </p>
              <h3 className="text-xl font-semibold text-fg-primary tracking-tight">Select region</h3>
              <p className="mt-1 text-sm text-fg-secondary">
                Each region has its own pack. Choose the one to review.
              </p>
            </div>
            <div className="p-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
              {REGIONS[scope].map((r) => (
                <button key={r.name} type="button" disabled={!r.live}
                  onClick={() => { setRegion(r.name); setView('viewer'); }}
                  className={cx(
                    'group flex items-center justify-between gap-3 rounded-xl border p-4 text-left transition-colors',
                    r.live
                      ? 'border-border-subtle bg-surface-1 hover:border-brand-blue/50 hover:bg-surface-sunken/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue'
                      : 'cursor-not-allowed border-border-subtle bg-surface-sunken/60')}>
                  <span>
                    <span className="flex items-center gap-2 text-[15px] font-semibold text-fg-primary">
                      {r.name}
                      {r.live
                        ? <span className="inline-flex items-center gap-1 rounded border border-status-healthy-border bg-status-healthy-bg px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-status-healthy-fg">
                            <span className="h-1.5 w-1.5 rounded-full bg-status-healthy-solid" />Live</span>
                        : <span className="rounded border border-border-subtle px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-fg-tertiary">Soon</span>}
                    </span>
                    {r.detail && <span className="mt-1 block text-[13px] text-fg-secondary">{r.detail}</span>}
                  </span>
                  {r.live && <ChevronRight className="h-4 w-4 shrink-0 text-fg-tertiary transition-transform group-hover:translate-x-0.5 group-hover:text-brand-blue" />}
                </button>
              ))}
            </div>
          </motion.div>
        )}

        {view === 'viewer' && (
          <motion.div
            key="viewer"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2 }}
            className={cx("flex flex-col flex-1 min-h-0", (loading || error) && "bento-card overflow-hidden")}
          >
            {loading && (
              <div className="flex flex-col items-center justify-center gap-4 h-full text-fg-secondary p-20">
                <AkLoader size="lg" />
                <span className="text-sm font-medium tracking-wide text-fg-primary">
                  Building the {scope?.toUpperCase()} portfolio pack from P6, SAP and Pulse…
                </span>
                <span className="text-xs tabular-nums text-fg-tertiary">
                  {mmss} elapsed · the first build after a data change takes about a minute
                </span>
                {elapsed >= 180 && (
                  <div className="mt-2 flex max-w-md flex-col items-center gap-3 rounded-lg border border-status-watch-border bg-status-watch-bg px-4 py-3 text-center">
                    <span className="text-[13px] text-status-watch-fg">
                      This is taking longer than usual. The server renders the slides through PowerPoint; it may be busy or stuck.
                    </span>
                    <button onClick={retry}
                      className="rounded-lg border border-border-default bg-surface-1 px-3 py-1.5 text-[12px] font-medium text-fg-primary hover:bg-surface-sunken">
                      Try again
                    </button>
                  </div>
                )}
              </div>
            )}

            {!loading && error && (
              <div className="flex flex-col items-center justify-center gap-4 h-full text-center p-20">
                <AlertTriangle className="h-8 w-8 text-status-critical-fg" strokeWidth={1.5} />
                <p className="text-base font-medium text-fg-primary">{error}</p>
                <div className="flex gap-3 mt-2">
                  <button onClick={retry}
                    className="rounded-lg border border-border-default bg-surface-1 px-4 py-2 text-sm font-medium text-fg-primary transition-colors hover:bg-surface-sunken">
                    Retry
                  </button>
                  <button onClick={() => {
                    if (scope && REGIONS[scope].length > 1) setView('region_select');
                    else { setScope(null); setView('portfolio_select'); }
                  }}
                    className="rounded-lg border border-border-default bg-surface-1 px-4 py-2 text-sm font-medium text-fg-primary transition-colors hover:bg-surface-sunken">
                    Change portfolio
                  </button>
                </div>
              </div>
            )}

            {!loading && !error && pack.pages?.length > 0 && (
              /* Opens over the whole window; closing it (X or Esc) returns to
                 the portfolio choice, minimising keeps it on the page. */
              <CPAGSlideViewer
                pack={pack}
                deckTitle={scope === 'bess' ? 'BESS · CPAG pack · all projects'
                  : `${scope ? SCOPE_NAME[scope] : ''} · CPAG pack · ${region ?? ''}`}
                initialFull
                onClose={() => {
                  if (scope && REGIONS[scope].length > 1) setView('region_select');
                  else { setScope(null); setView('portfolio_select'); }
                }}
              />
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
