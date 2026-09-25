/* ── CPAG pack, opened from the project page ──
   A modal rather than a tab: the pack is a document someone opens, reads and
   closes, not a working surface they keep switching back to.

   The pack is one deck across all six BESS projects, exactly as the approved
   template is - never a single-project cut - and the pages shown are the
   downloadable deck itself. */
import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Loader2, AlertTriangle } from 'lucide-react';
import CPAGSlideViewer from './CPAGSlides';
import { useCPAGPack } from './useCPAGPack';

export const PackStatus: React.FC<{
  pack: ReturnType<typeof useCPAGPack>; onClose: () => void;
}> = ({ pack, onClose }) => (
  <>
    {pack.loading && (
      <div className="flex flex-col items-center justify-center gap-3 py-32 text-white/60">
        <Loader2 className="h-5 w-5 animate-spin" strokeWidth={1.5} />
        <span className="text-sm">Building the CPAG pack from P6, SAP and Pulse…</span>
        <span className="text-xs text-white/40">The first build after a data change takes about a minute.</span>
      </div>
    )}
    {!pack.loading && pack.error && (
      <div className="flex flex-col items-center gap-3 py-32 text-center">
        <AlertTriangle className="h-6 w-6 text-status-risk-fg" strokeWidth={1.5} />
        <p className="text-sm text-white/70">{pack.error}</p>
        <div className="flex gap-2">
          <button onClick={pack.retry}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-[13px] font-medium text-white/80
                       transition-colors hover:bg-white/10">
            Retry
          </button>
          <button onClick={onClose}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-[13px] font-medium text-white/80
                       transition-colors hover:bg-white/10">
            Close
          </button>
        </div>
      </div>
    )}
  </>
);

export const CPAGModal: React.FC<{
  open: boolean;
  projectId?: string;
  projectLabel?: string;
  onClose: () => void;
}> = ({ open, onClose }) => {
  const pack = useCPAGPack(open);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  if (!open) return null;

  return createPortal(
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
          <PackStatus pack={pack} onClose={onClose} />
          {!pack.loading && !pack.error && pack.pages.length > 0 && (
            <div className="min-h-0 flex-1 p-3">
              <CPAGSlideViewer pack={pack} deckTitle="BESS · CPAG pack · all projects" onClose={onClose} />
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body,
  );
};

export default CPAGModal;
