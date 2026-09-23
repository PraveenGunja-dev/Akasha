/* ── CPAG pack, opened from the project page ──
   A modal rather than a tab: the pack is a document someone opens, reads and
   closes, not a working surface they keep switching back to.

   The scope choice comes first because the two answer different questions —
   "how is this project doing" and "how do the six compare" — and neither is the
   obvious default from inside a project page. */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Loader2, AlertTriangle, Battery, Layers, X, ArrowLeft } from 'lucide-react';
import { cx } from '../../components/ui/primitives';
import CPAGSlideViewer, { buildSlides, type Slide } from './CPAGSlides';

type Scope = 'project' | 'portfolio';

const ScopeCard: React.FC<{
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  title: string; detail: string; onClick: () => void;
}> = ({ icon: Icon, title, detail, onClick }) => (
  <button
    onClick={onClick}
    className="group flex flex-col items-start gap-3 rounded-xl border border-white/10 bg-white/[0.04]
               p-5 text-left transition-colors hover:border-primary/50 hover:bg-white/[0.07]
               focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
    <span className="rounded-lg bg-primary/20 p-2.5">
      <Icon className="h-5 w-5 text-primary" strokeWidth={1.5} />
    </span>
    <span>
      <span className="block text-[15px] font-semibold text-white">{title}</span>
      <span className="mt-1 block text-[13px] leading-relaxed text-white/50">{detail}</span>
    </span>
  </button>
);

export const CPAGModal: React.FC<{
  open: boolean;
  projectId: string;
  projectLabel?: string;
  onClose: () => void;
}> = ({ open, projectId, projectLabel, onClose }) => {
  const [scope, setScope] = useState<Scope | null>(null);
  const [project, setProject] = useState<any>(null);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  /* Each scope is fetched once and kept, so switching back and forth does not
     re-run what is a wide query on either side. */
  useEffect(() => {
    if (!open || !scope) return;
    if (scope === 'project' && project) return;
    if (scope === 'portfolio' && portfolio) return;

    let live = true;
    setLoading(true);
    setError(null);
    const url = scope === 'project'
      ? `/akasha/api/bess/${encodeURIComponent(projectId)}/cpag`
      : '/akasha/api/bess/portfolio/cpag';

    fetch(url)
      .then(async (r) => {
        if (!r.ok) throw new Error(`CPAG pack unavailable (${r.status})`);
        return r.json();
      })
      .then((json) => {
        if (!live) return;
        if (scope === 'project') setProject(json);
        else setPortfolio(json);
      })
      .catch((e: Error) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [open, scope, projectId, project, portfolio]);

  const retry = useCallback(() => {
    setError(null);
    if (scope === 'project') setProject(null);
    else setPortfolio(null);
  }, [scope]);

  /* A single-project pack is titled by that project, not by the portfolio. */
  const { slides, deckTitle, downloadHref } = useMemo((): {
    slides: Slide[]; deckTitle: string; downloadHref: string;
  } => {
    if (scope === 'project' && project) {
      const m = project.meta;
      const d = m.declared;
      const plan = (project.progress.buckets ?? [])
        .reduce((a: number, b: any) => a + (b.planToDatePct ?? 0), 0);
      const one = {
        pss: m.pss, spv: m.spv, plot: m.plot,
        powerMw: d.powerMw, energyMwh: d.energyMwh,
        dispatchableMwh: d.dispatchableMwh, containers: d.containers,
        landAcres: d.landAcres, batteryOem: d.batteryOem,
        planToDatePct: plan, actualPct: project.progress.totalEarnedPct ?? 0,
        buckets: project.progress.buckets,
        sCurve: project.sCurve.series,
        packages: project.procurement.packages,
        sap: project.procurement.sap,
        sapNote: project.procurement.sapNote,
        approvals: project.approvals.items,
        approvalsDone: project.approvals.completed,
        approvalsTotal: project.approvals.total,
        orderCr: project.commercial.orderCr,
        deliveredCr: project.commercial.deliveredCr,
        sapAvailable: project.procurement.sapAvailable,
        contractors: project.contractors.items,
        engineering: project.engineering,
        construction: project.construction,
        electrical: project.electrical,
        commissioning: project.commissioning,
        quality: project.quality,
      };
      return {
        slides: buildSlides({
          projects: [one],
          meta: {
            powerMw: d.powerMw, energyMwh: d.energyMwh,
            dispatchableMwh: d.dispatchableMwh, containers: d.containers,
            lastActualMonth: project.sCurve.lastActualMonth,
            declaredSource: d.source,
          },
          commercial: project.commercial,
          manpower: project.manpower,
          single: true,
        }),
        deckTitle: `${m.pss} — ${m.spv} · CPAG pack`,
        downloadHref: `/akasha/api/bess/${encodeURIComponent(projectId)}/cpag.pptx`,
      };
    }
    if (scope === 'portfolio' && portfolio) {
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
  }, [scope, project, portfolio, projectId]);

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
                    What do you want to see?
                  </h3>
                  <p className="mt-1 text-[13px] text-white/50">
                    Rebuilt from P6, SAP and Pulse — not the circulated PowerPoint.
                  </p>
                </div>
                <button
                  onClick={onClose} aria-label="Close"
                  className="rounded-lg p-1.5 text-white/50 transition-colors hover:bg-white/10 hover:text-white
                             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40">
                  <X className="h-5 w-5" strokeWidth={1.5} />
                </button>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <ScopeCard
                  icon={Battery}
                  title={projectLabel ? `${projectLabel} only` : 'This project only'}
                  detail="The full pack for this project — S-curve, procurement, approvals, mandays and contractors."
                  onClick={() => setScope('project')} />
                <ScopeCard
                  icon={Layers}
                  title="All BESS projects"
                  detail="The whole pack across all six, each project with its own slides, plus the combined order book."
                  onClick={() => setScope('portfolio')} />
              </div>
            </div>
          )}

          {scope && loading && (
            <div className="flex flex-col items-center justify-center gap-3 py-32 text-white/60">
              <Loader2 className="h-5 w-5 animate-spin" strokeWidth={1.5} />
              <span className="text-sm">
                Building the {scope === 'portfolio' ? 'portfolio pack' : 'pack'} from P6, SAP and Pulse…
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
                  Change scope
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
                <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} /> Change scope
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

export default CPAGModal;
