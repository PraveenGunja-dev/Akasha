import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Loader2, AlertTriangle, Battery, Layers, X, ArrowLeft, Sun, Wind, Presentation } from 'lucide-react';
import { cx } from '../../components/ui/primitives';
import CPAGSlideViewer, { buildSlides, type Slide } from './CPAGSlides';

type Scope = 'solar' | 'wind' | 'bess' | null;

const ScopeCard: React.FC<{
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  title: string;
  detail: string;
  onClick?: () => void;
  disabled?: boolean;
}> = ({ icon: Icon, title, detail, onClick, disabled }) => (
  <button
    onClick={disabled ? undefined : onClick}
    disabled={disabled}
    className={cx(
      "group flex flex-col items-start gap-3 rounded-xl border border-white/10 p-5 text-left transition-colors",
      disabled 
        ? "opacity-50 cursor-not-allowed bg-white/[0.02]" 
        : "bg-white/[0.04] hover:border-primary/50 hover:bg-white/[0.07] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    )}>
    <span className={cx("rounded-lg p-2.5", disabled ? "bg-white/10" : "bg-primary/20")}>
      <Icon className={cx("h-5 w-5", disabled ? "text-white/50" : "text-primary")} strokeWidth={1.5} />
    </span>
    <span>
      <span className="block text-[15px] font-semibold text-white">{title}</span>
      <span className="mt-1 block text-[13px] leading-relaxed text-white/50">{detail}</span>
    </span>
  </button>
);

export const GlobalCPAGModal: React.FC<{
  open: boolean;
  onClose: () => void;
}> = ({ open, onClose }) => {
  const [scope, setScope] = useState<Scope>(null);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  useEffect(() => {
    if (!open || !scope) return;
    if (scope === 'bess' && portfolio) return;

    if (scope !== 'bess') return; // Only BESS is supported for now

    let live = true;
    setLoading(true);
    setError(null);
    
    fetch('/akasha/api/bess/portfolio/cpag')
      .then(async (r) => {
        if (!r.ok) throw new Error(`CPAG pack unavailable (${r.status})`);
        return r.json();
      })
      .then((json) => {
        if (!live) return;
        setPortfolio(json);
      })
      .catch((e: Error) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [open, scope, portfolio]);

  const retry = useCallback(() => {
    setError(null);
    setPortfolio(null);
  }, []);

  const { slides, deckTitle, downloadHref } = useMemo((): {
    slides: Slide[]; deckTitle: string; downloadHref: string;
  } => {
    if (scope === 'bess' && portfolio) {
      return {
        slides: buildSlides({
          projects: portfolio.projects, meta: portfolio.meta,
          commercial: portfolio.commercial, manpower: portfolio.manpower,
          single: false,
        }),
        deckTitle: `BESS portfolio · ${portfolio.meta.projectCount} projects · CPAG pack`,
        downloadHref: '/akasha/api/bess/portfolio/cpag.pptx',
      };
    }
    return { slides: [], deckTitle: '', downloadHref: '' };
  }, [scope, portfolio]);

  if (!open) return null;

  const body = (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-[120] flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
        onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.97 }}
          transition={{ duration: 0.2 }}
          className="flex max-h-[94vh] w-full max-w-[1500px] flex-col overflow-hidden rounded-2xl
                     border border-white/10 bg-[#0b1020] shadow-2xl">

          {!scope && (
            <div className="px-10 py-12">
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">
                    CPAG review pack
                  </p>
                  <h3 className="mt-2 text-[20px] font-semibold text-white">
                    Select Portfolio
                  </h3>
                  <p className="mt-1 text-[13px] text-white/50">
                    Choose a portfolio to view its complete CPAG pack.
                  </p>
                </div>
                <button
                  onClick={onClose} aria-label="Close"
                  className="rounded-lg p-1.5 text-white/50 transition-colors hover:bg-white/10 hover:text-white
                             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40">
                  <X className="h-5 w-5" strokeWidth={1.5} />
                </button>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <ScopeCard
                  icon={Sun}
                  title="Solar Portfolio"
                  detail="CPAG packs for solar projects are currently being integrated."
                  disabled={true}
                  onClick={() => setScope('solar')} />
                <ScopeCard
                  icon={Wind}
                  title="Wind Portfolio"
                  detail="CPAG packs for wind projects are currently being integrated."
                  disabled={true}
                  onClick={() => setScope('wind')} />
                <ScopeCard
                  icon={Battery}
                  title="BESS Portfolio"
                  detail="The whole pack across all BESS projects, plus the combined order book."
                  onClick={() => setScope('bess')} />
              </div>
            </div>
          )}

          {scope && loading && (
            <div className="flex flex-col items-center justify-center gap-3 py-32 text-white/60">
              <Loader2 className="h-5 w-5 animate-spin" strokeWidth={1.5} />
              <span className="text-sm">
                Building the {scope.toUpperCase()} portfolio pack from P6, SAP and Pulse…
              </span>
            </div>
          )}

          {scope && !loading && error && (
            <div className="flex flex-col items-center gap-3 py-32 text-center">
              <AlertTriangle className="h-6 w-6 text-status-risk-fg" strokeWidth={1.5} />
              <p className="text-sm text-white/70">{error}</p>
              <div className="flex gap-2">
                <button onClick={retry}
                  className="rounded-lg border border-white/15 px-3 py-1.5 text-[13px] font-medium text-white/80
                             transition-colors hover:bg-white/10">
                  Retry
                </button>
                <button onClick={() => setScope(null)}
                  className="rounded-lg border border-white/15 px-3 py-1.5 text-[13px] font-medium text-white/80
                             transition-colors hover:bg-white/10">
                  Change portfolio
                </button>
              </div>
            </div>
          )}

          {scope && !loading && !error && slides.length > 0 && (
            <div className="flex min-h-0 flex-1 flex-col">
              <button
                onClick={() => setScope(null)}
                className="flex shrink-0 items-center gap-1.5 px-4 pt-3 text-[12px] font-medium text-white/45
                           transition-colors hover:text-white focus-visible:outline-none">
                <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} /> Change portfolio
              </button>
              <div className="min-h-0 flex-1 p-3 pt-2">
                <CPAGSlideViewer
                  slides={slides}
                  deckTitle={deckTitle}
                  downloadHref={downloadHref}
                  onClose={onClose}
                />
              </div>
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );

  return createPortal(body, document.body);
};

export default GlobalCPAGModal;
