/* ── CPAG pack viewer ──
   Shows the pages of the downloadable deck as the backend renders them from
   the approved template, so the screen and the file are the same pack. */
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle, ChevronLeft, ChevronRight, CheckCircle2, Download, Info, List,
  Loader2, Maximize2, Minimize2, Upload, X,
} from 'lucide-react';
import { cx } from '../../components/ui/primitives';
import type { CPAGPack } from './useCPAGPack';

const fmtDate = (iso?: string | null) => (iso
  ? new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' })
  : '—');

interface CpagUploader {
  endpoint: string;
  label: string;
  matches: (title: string) => boolean;
  success: (data: any, filename: string) => string;
}

/* Pages with no connected-system source for (some of) their columns: each is
   whatever file the team most recently uploaded here, never a stored copy. */
const UPLOADERS: CpagUploader[] = [
  {
    endpoint: 'engineering/upload', label: 'Upload MDL',
    matches: (t) => t.includes('Engineering Progress'),
    success: (data, name) => `Loaded ${data.projects.length} projects from "${name}".`,
  },
  {
    endpoint: 'procurement/upload', label: 'Upload WBS mapping',
    matches: (t) => t.startsWith('Procurement & Monthly Rolling Plan'),
    success: (data, name) =>
      `Stored ${data.poLines} PO lines, ${data.packages} packages across ${data.projects.length} projects, from "${name}".`,
  },
];

export const CPAGSlideViewer: React.FC<{
  pack: CPAGPack;
  deckTitle: string;
  onClose?: () => void;
}> = ({ pack, deckTitle, onClose }) => {
  const { pages, pageSrc, downloadHref, asOf } = pack;
  const [index, setIndex] = useState(0);
  const [full, setFull] = useState(false);
  const [showIndex, setShowIndex] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploadNote, setUploadNote] = useState<{ ok: boolean; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingUpload = useRef<CpagUploader | null>(null);

  const total = pages.length;
  const next = useCallback(() => setIndex((i) => Math.min(i + 1, total - 1)), [total]);
  const prev = useCallback(() => setIndex((i) => Math.max(i - 1, 0)), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); next(); }
      if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); prev(); }
      if (e.key === 'Home') setIndex(0);
      if (e.key === 'End') setIndex(total - 1);
      if (e.key === 'Escape') { if (full) setFull(false); else onClose?.(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [next, prev, total, full, onClose]);

  /* Warm the next page so paging forward never shows a blank stage. */
  useEffect(() => {
    if (index + 1 < total) new Image().src = pageSrc(pages[index + 1].n);
  }, [index, total, pages, pageSrc]);

  /* Both pages below have no connected-system source for these columns - each
     is whatever file the team last uploaded here. No copy is kept beyond
     that upload, so re-uploading a newer one is how the page refreshes;
     nothing else in the pack is affected. */
  const handleUpload = useCallback(async (uploader: CpagUploader, file: File) => {
    setUploading(uploader.endpoint);
    setUploadNote(null);
    try {
      const body = new FormData();
      body.append('file', file);
      const res = await fetch(`/akasha/api/bess/cpag/manual/${uploader.endpoint}`, { method: 'POST', body });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `Upload failed (${res.status})`);
      setUploadNote({ ok: true, text: uploader.success(data, file.name) });
      pack.retry();
    } catch (e) {
      setUploadNote({ ok: false, text: e instanceof Error ? e.message : 'Upload failed.' });
    } finally {
      setUploading(null);
    }
  }, [pack]);

  const sections = useMemo(() => {
    const map: { section: string; items: { i: number; title: string }[] }[] = [];
    pages.forEach((p, i) => {
      const last = map[map.length - 1];
      if (!last || last.section !== p.section) map.push({ section: p.section, items: [] });
      map[map.length - 1].items.push({ i, title: p.title });
    });
    return map;
  }, [pages]);

  if (!total) return null;
  const page = pages[index];
  const uploader = UPLOADERS.find((u) => u.matches(page.title));

  return (
    <div className={cx('flex flex-col', full
      ? 'fixed inset-0 z-[130] bg-white'
      : 'h-full rounded-xl border border-slate-200 bg-white')}>
      <div className="flex shrink-0 items-center justify-between gap-3 rounded-t-xl border-b border-slate-200 bg-white px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-3">
          <button
            onClick={() => setShowIndex((v) => !v)}
            aria-label="Page index" aria-expanded={showIndex}
            className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400">
            <List className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </button>
          <span className="rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] font-semibold tabular-nums text-primary">
            {index + 1} / {total}
          </span>
          <p className="truncate text-[13px] font-medium text-slate-700">{deckTitle}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {uploader && (
            <>
              <input ref={fileInputRef} type="file" accept=".xlsx,.xls" className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f && pendingUpload.current) handleUpload(pendingUpload.current, f);
                  e.target.value = '';
                }} />
              <button
                onClick={() => { pendingUpload.current = uploader; fileInputRef.current?.click(); }}
                disabled={uploading !== null}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px]
                           font-medium text-slate-700 transition-colors hover:bg-slate-100 hover:text-slate-900
                           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400
                           disabled:pointer-events-none disabled:opacity-60">
                {uploading === uploader.endpoint
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
                  : <Upload className="h-3.5 w-3.5" strokeWidth={1.5} />}
                {uploader.label}
              </button>
            </>
          )}
          <button
            onClick={() => setShowInfo((v) => !v)}
            aria-expanded={showInfo} aria-controls="cpag-sources"
            className={cx('flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400',
              showInfo ? 'border-primary/40 bg-primary/10 text-primary'
                : 'border-slate-200 text-slate-700 hover:bg-slate-100 hover:text-slate-900')}>
            <Info className="h-3.5 w-3.5" strokeWidth={1.5} /> Data sources
          </button>
          <a
            href={downloadHref}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px]
                       font-medium text-slate-700 transition-colors hover:bg-slate-100 hover:text-slate-900
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400">
            <Download className="h-3.5 w-3.5" strokeWidth={1.5} /> .pptx
          </a>
          <button
            onClick={() => setFull((v) => !v)}
            aria-label={full ? 'Exit full screen' : 'Full screen'}
            className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400">
            {full ? <Minimize2 className="h-[18px] w-[18px]" strokeWidth={1.5} />
              : <Maximize2 className="h-[18px] w-[18px]" strokeWidth={1.5} />}
          </button>
          {onClose && (
            <button
              onClick={onClose} aria-label="Close"
              className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900
                         focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400">
              <X className="h-[18px] w-[18px]" strokeWidth={1.5} />
            </button>
          )}
        </div>
      </div>

      {uploadNote && (
        <div className={cx('flex shrink-0 items-center gap-2 border-b px-4 py-2 text-[12px] font-medium',
          uploadNote.ok ? 'border-status-healthy-border bg-status-healthy-bg text-status-healthy-fg'
            : 'border-status-critical-border bg-status-critical-bg text-status-critical-fg')}>
          {uploadNote.ok ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
            : <AlertCircle className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />}
          <span className="min-w-0 flex-1">{uploadNote.text}</span>
          <button onClick={() => setUploadNote(null)} aria-label="Dismiss" className="shrink-0 opacity-60 hover:opacity-100">
            <X className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <AnimatePresence initial={false}>
          {showIndex && (
            <motion.nav
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 280, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="custom-scrollbar shrink-0 overflow-y-auto border-r border-slate-200 bg-white">
              <div className="w-[280px] py-2">
                {sections.map((sec, si) => (
                  <div key={`${sec.section}-${si}`} className="mb-1">
                    <p className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      {sec.section}
                    </p>
                    {sec.items.map((it) => (
                      <button
                        key={it.i}
                        onClick={() => setIndex(it.i)}
                        className={cx('block w-full truncate px-3 py-1.5 text-left text-[12px] transition-colors',
                          it.i === index ? 'bg-primary/10 font-semibold text-primary'
                            : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900')}>
                        <span className="mr-2 tabular-nums text-slate-400">{it.i + 1}</span>
                        {it.title}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </motion.nav>
          )}
        </AnimatePresence>

        <div className={cx('relative min-w-0 flex-1 overflow-hidden bg-slate-100',
          full ? '' : 'h-[min(74vh,800px)]')}>
          <img
            key={page.n}
            src={pageSrc(page.n)}
            alt={page.title}
            className="absolute inset-0 m-auto h-full w-full object-contain p-3 drop-shadow-[0_4px_24px_rgba(0,0,0,0.18)]"
          />
          <button
            onClick={prev} disabled={index === 0} aria-label="Previous page"
            className="absolute left-3 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-2.5 text-white/80
                       transition hover:bg-black/70 hover:text-white focus-visible:outline-none
                       focus-visible:ring-2 focus-visible:ring-white disabled:pointer-events-none disabled:opacity-0">
            <ChevronLeft className="h-5 w-5" strokeWidth={1.75} />
          </button>
          <button
            onClick={next} disabled={index === total - 1} aria-label="Next page"
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-2.5 text-white/80
                       transition hover:bg-black/70 hover:text-white focus-visible:outline-none
                       focus-visible:ring-2 focus-visible:ring-white disabled:pointer-events-none disabled:opacity-0">
            <ChevronRight className="h-5 w-5" strokeWidth={1.75} />
          </button>
        </div>

        <AnimatePresence initial={false}>
          {showInfo && (
            <motion.aside
              id="cpag-sources"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 320, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.18 }}
              aria-label="Where this page's data comes from"
              className="custom-scrollbar shrink-0 overflow-y-auto border-l border-slate-200 bg-white">
              <div className="w-[320px] p-4">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Page {index + 1} · where the data comes from
                </p>
                <p className="mt-1 text-[13px] font-semibold leading-snug text-slate-800">{page.title}</p>
                <ul className="mt-3 space-y-2">
                  {page.source.map((line, i) => (
                    <li key={i} className="flex gap-2 text-[12px] leading-relaxed text-slate-600">
                      <span aria-hidden className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
                <dl className="mt-4 space-y-1 border-t border-slate-100 pt-3 text-[11px] text-slate-500">
                  <div className="flex justify-between gap-3">
                    <dt>P6 data date</dt>
                    <dd className="font-medium tabular-nums text-slate-700">{fmtDate(asOf?.p6)}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>SAP extract as on</dt>
                    <dd className="font-medium tabular-nums text-slate-700">{fmtDate(asOf?.sap)}</dd>
                  </div>
                </dl>
                <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
                  Layout, headings and page order are the approved CPAG template's. Manual-entry
                  values stay blank until entered - they are never carried over from an old pack.
                  Engineering Progress and Procurement's Packages-through-PO-Date columns instead
                  refresh from the upload button on those pages - never a stored copy.
                </p>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>

      <div className="shrink-0 rounded-b-xl border-t border-slate-200 bg-white px-4 py-2">
        <div className="flex items-center gap-3">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-primary transition-[width] duration-300"
              style={{ width: `${((index + 1) / total) * 100}%` }} />
          </div>
          <span className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <Info className="h-3 w-3" strokeWidth={1.5} />
            The downloaded .pptx is this exact deck · arrow keys to navigate
          </span>
        </div>
      </div>
    </div>
  );
};

export default CPAGSlideViewer;
