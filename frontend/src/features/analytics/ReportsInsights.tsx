import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, AlertTriangle, Battery, Sun, Wind, ArrowLeft, Presentation, ChevronRight, FileText, BarChart3, ShieldCheck } from 'lucide-react';
import { cx } from '../../components/ui/primitives';
import CPAGSlideViewer, { buildSlides, type Slide } from '../projects/CPAGSlides';

type ViewState = 'directory' | 'portfolio_select' | 'viewer';
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
      "group flex flex-col items-start gap-3 rounded-xl border p-5 text-left transition-all duration-200",
      disabled 
        ? "opacity-50 cursor-not-allowed bg-slate-50 border-slate-200" 
        : "bg-white border-slate-200 hover:border-[#0B74B1]/50 hover:shadow-md hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0B74B1]"
    )}>
    <span className={cx("rounded-lg p-2.5", disabled ? "bg-slate-100" : "bg-[#0B74B1]/10")}>
      <Icon className={cx("h-5 w-5", disabled ? "text-slate-400" : "text-[#0B74B1]")} strokeWidth={1.5} />
    </span>
    <span>
      <span className="block text-[15px] font-bold text-slate-900">{title}</span>
      <span className="mt-1 block text-[13px] leading-relaxed text-slate-500">{detail}</span>
    </span>
  </button>
);

export default function ReportsInsights(props: any) {
  const [view, setView] = useState<ViewState>('directory');
  const [scope, setScope] = useState<Scope>(null);
  
  const [portfolio, setPortfolio] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch BESS data when we hit 'viewer' and scope is 'bess'
  useEffect(() => {
    if (view !== 'viewer') return;
    if (scope !== 'bess') return;
    if (portfolio) return;

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
  }, [view, scope, portfolio]);

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

  return (
    <div className={cx(
      "flex flex-col mx-auto animate-in fade-in duration-500 pb-6 pt-2 h-full min-h-[calc(100vh-100px)]",
      view === 'viewer' ? "w-full" : "max-w-[1100px] gap-6"
    )}>
      
      {/* ── Top Executive Action Bar ── */}
      {view !== 'viewer' && (
        <div className="flex items-center justify-between bg-white border border-slate-200 rounded-xl p-4 shadow-sm shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-[#0B74B1]/10 flex items-center justify-center border border-[#0B74B1]/20">
              <FileText className="w-5 h-5 text-[#0B74B1]" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-900 tracking-tight font-['Adani',sans-serif]">
                Executive Reports & Briefings
              </h2>
              <p className="text-xs text-slate-500">
                Corporate Reporting Standard • Automated Multi-System Telemetry
              </p>
            </div>
          </div>
        </div>
      )}

      <AnimatePresence mode="wait">
        {view === 'directory' && (
          <motion.div
            key="directory"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="flex-1"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              
              {/* CPAG Card */}
              <div 
                onClick={() => setView('portfolio_select')}
                className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm hover:shadow-lg hover:border-[#0B74B1]/40 transition-all duration-300 cursor-pointer group flex flex-col h-full relative overflow-hidden"
              >
                <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-[#0B74B1]/5 to-transparent rounded-bl-full pointer-events-none group-hover:scale-110 transition-transform"></div>
                
                <div className="w-12 h-12 rounded-xl bg-[#0B74B1]/10 flex items-center justify-center mb-5 group-hover:bg-[#0B74B1] transition-colors duration-300">
                  <Presentation className="w-6 h-6 text-[#0B74B1] group-hover:text-white transition-colors" strokeWidth={1.5} />
                </div>
                
                <h3 className="text-lg font-bold text-slate-900 mb-2 font-['Adani',sans-serif]">CPAG Review Pack</h3>
                <p className="text-sm text-slate-500 leading-relaxed mb-6 flex-1">
                  Interactive presentation slides directly generated from P6, SAP, and Pulse data. Used for executive governance and steering committee reviews.
                </p>
                
                <div className="flex items-center text-[#0B74B1] text-sm font-semibold mt-auto group-hover:translate-x-1 transition-transform">
                  Access Reports <ChevronRight className="w-4 h-4 ml-1" />
                </div>
              </div>

              {/* Placeholder Card 1 */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm opacity-60 cursor-not-allowed flex flex-col h-full">
                <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center mb-5">
                  <BarChart3 className="w-6 h-6 text-slate-400" strokeWidth={1.5} />
                </div>
                <h3 className="text-lg font-bold text-slate-900 mb-2 font-['Adani',sans-serif]">Financial Summary (Coming Soon)</h3>
                <p className="text-sm text-slate-500 leading-relaxed mb-6 flex-1">
                  Comprehensive breakdown of capital expenditure, budget variance, and projected cash flow requirements across all clusters.
                </p>
              </div>

              {/* Placeholder Card 2 */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm opacity-60 cursor-not-allowed flex flex-col h-full">
                <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center mb-5">
                  <ShieldCheck className="w-6 h-6 text-slate-400" strokeWidth={1.5} />
                </div>
                <h3 className="text-lg font-bold text-slate-900 mb-2 font-['Adani',sans-serif]">HSE & Quality Audit (Coming Soon)</h3>
                <p className="text-sm text-slate-500 leading-relaxed mb-6 flex-1">
                  Aggregated safety metrics, incident reports, and quality non-conformance tracking for active construction sites.
                </p>
              </div>

            </div>
          </motion.div>
        )}

        {view === 'portfolio_select' && (
          <motion.div
            key="portfolio_select"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2 }}
            className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden flex-1 flex flex-col"
          >
            <div className="px-6 py-6 border-b border-slate-100 bg-slate-50/50">
              <button
                onClick={() => setView('directory')}
                className="flex items-center gap-1.5 text-sm font-semibold text-slate-500 hover:text-[#0B74B1] transition-colors mb-4"
              >
                <ArrowLeft className="w-4 h-4" /> Back to Directory
              </button>
              
              <div>
                <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#0B74B1] mb-1">
                  CPAG review pack
                </p>
                <h3 className="text-xl font-black text-slate-900 tracking-tight font-['Adani',sans-serif]">
                  Select Portfolio
                </h3>
                <p className="mt-1 text-sm text-slate-500">
                  Choose a portfolio to view its complete CPAG pack, generated live from execution telemetry.
                </p>
              </div>
            </div>
            
            <div className="p-6 grid grid-cols-1 gap-5 sm:grid-cols-3">
              <ScopeCard
                icon={Sun}
                title="Solar Portfolio"
                detail="CPAG packs for solar projects are currently being integrated into the data pipeline."
                disabled={true}
                onClick={() => {
                  setScope('solar');
                  setView('viewer');
                }} 
              />
              <ScopeCard
                icon={Wind}
                title="Wind Portfolio"
                detail="CPAG packs for wind projects are currently being integrated into the data pipeline."
                disabled={true}
                onClick={() => {
                  setScope('wind');
                  setView('viewer');
                }} 
              />
              <ScopeCard
                icon={Battery}
                title="BESS Portfolio"
                detail="The whole pack across all BESS projects, plus the combined corporate order book."
                onClick={() => {
                  setScope('bess');
                  setView('viewer');
                }} 
              />
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
            className="flex flex-col flex-1 min-h-0 bg-white rounded-2xl shadow-xl overflow-hidden border border-slate-200"
          >
            {loading && (
              <div className="flex flex-col items-center justify-center gap-4 h-full text-slate-500 p-20">
                <Loader2 className="h-8 w-8 animate-spin text-[#0B74B1]" strokeWidth={2} />
                <span className="text-sm font-medium tracking-wide text-slate-600">
                  Building the {scope?.toUpperCase()} portfolio pack from P6, SAP and Pulse…
                </span>
              </div>
            )}

            {!loading && error && (
              <div className="flex flex-col items-center justify-center gap-4 h-full text-center p-20">
                <AlertTriangle className="h-8 w-8 text-rose-500" strokeWidth={1.5} />
                <p className="text-base font-medium text-slate-700">{error}</p>
                <div className="flex gap-3 mt-2">
                  <button onClick={retry}
                    className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 shadow-sm">
                    Retry
                  </button>
                  <button onClick={() => {
                      setScope(null);
                      setView('portfolio_select');
                    }}
                    className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 shadow-sm">
                    Change portfolio
                  </button>
                </div>
              </div>
            )}

            {!loading && !error && slides.length > 0 && (
              <div className="flex min-h-0 flex-1 flex-col">
                <div className="flex shrink-0 items-center justify-between px-5 pt-4 pb-2 border-b border-slate-100">
                  <button
                    onClick={() => {
                      setScope(null);
                      setView('portfolio_select');
                    }}
                    className="flex items-center gap-1.5 text-[13px] font-semibold text-slate-500 transition-colors hover:text-[#0B74B1]"
                  >
                    <ArrowLeft className="h-4 w-4" strokeWidth={1.5} /> Back to Portfolio Selection
                  </button>
                </div>
                <div className="min-h-0 flex-1 p-0">
                  <CPAGSlideViewer
                    slides={slides}
                    deckTitle={deckTitle}
                    downloadHref={downloadHref}
                    onClose={() => {
                      setScope(null);
                      setView('directory');
                    }}
                  />
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
