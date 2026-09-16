import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SAPHeader } from './components/SAPHeader';
import { SAPFilters } from './components/SAPFilters';
import { SAPKpiGrid } from './components/SAPKpiGrid';
import { ConsumptionTrend } from './components/ConsumptionTrend';
import { InsightsPanel } from './components/InsightsPanel';
import { VendorSupply } from './components/VendorSupply';
import { LocationMap } from './components/LocationMap';
import { MaterialAnalytics } from './components/MaterialAnalytics';
import { ProcurementLedger } from './components/ProcurementLedger';
import { DrawerHost } from './components/drawers';
import { Drawer, Stat, Btn } from './components/Drawer';
import { useSAPStore, filtersToParams, paramsToFilters, drawerToParam, paramToDrawer, DRAWER_KEY } from './store';
import { exportCSV, exportName, fetchAllLines } from './export';
import { fmtCr, fmtNum } from './format';
import type { SAPFilters as FilterSet, TrendBucket, TrendEvent } from './types';

/* ═══════════════════════════════════════════════════════════════════════════
   SAP INTELLIGENCE
   Order on the page is the order of the questions:
     what is happening      → KPI row
     why / what changed     → consumption trend + insights
     where is the exposure  → vendors + map
     what carries it        → materials
     which records          → ledger
   Drawers answer "what can I do about it" without leaving the view.

   Filters and the open drawer are mirrored to the URL so a view can be
   shared and the browser back button behaves.
   ═══════════════════════════════════════════════════════════════════════════ */

// Key-order-independent identity for a filter set.
const sig = (f: FilterSet) => JSON.stringify(f, Object.keys(f).sort());

const useUrlSync = () => {
  const [params, setParams] = useSearchParams();
  const filters = useSAPStore(s => s.filters); const setFilters = useSAPStore(s => s.setFilters);
  const drawers = useSAPStore(s => s.drawers); const openDrawer = useSAPStore(s => s.openDrawer); const closeAll = useSAPStore(s => s.closeAllDrawers);
  const hydrated = useRef(false);
  // Filters last pushed into the store *from* the URL. The store→URL effect
  // fires in the same commit with the pre-update filters in its closure; if it
  // wrote those back it would strip the header's portfolio/phase from the URL,
  // the URL effect would then clear the store, and the two would ping-pong.
  // While the store still lags that push, the write-back is skipped.
  const pendingFromUrl = useRef<string | null>(null);

  // URL → store, on mount and on back/forward.
  useEffect(() => {
    const f = paramsToFilters(params);
    const same = sig(f) === sig(filters);
    if (!same) { pendingFromUrl.current = sig(f); setFilters(f); }
    const d = paramToDrawer(params.get(DRAWER_KEY));
    const top = drawers[drawers.length - 1];
    if (d && (!top || drawerToParam(top) !== drawerToParam(d))) openDrawer(d);
    if (!d && top && hydrated.current) closeAll();
    hydrated.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // store → URL, replace (filters) or push (drawer open) so back closes a drawer.
  useEffect(() => {
    if (!hydrated.current) return;
    if (pendingFromUrl.current !== null) {
      if (sig(filters) !== pendingFromUrl.current) return;   // store has not caught up with the URL yet
      pendingFromUrl.current = null;
    }
    const next = filtersToParams(filters, params);
    const dp = drawerToParam(drawers[drawers.length - 1]);
    if (dp) next.set(DRAWER_KEY, dp); else next.delete(DRAWER_KEY);
    if (next.toString() !== params.toString()) setParams(next, { replace: !dp || params.get(DRAWER_KEY) === dp });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, drawers]);
};

export default function SAPIntelligencePage() {
  useUrlSync();
  const filters = useSAPStore(s => s.filters); const ledger = useSAPStore(s => s.ledger); const cols = useSAPStore(s => s.ledger.columns);
  const [event, setEvent] = useState<{ e: TrendEvent; b: TrendBucket } | null>(null);
  const [exporting, setExporting] = useState<number | null>(null);

  const exportAll = useCallback(async () => {
    try { setExporting(0); const rows = await fetchAllLines(filters, ledger.sort, ledger.order, 20_000, setExporting); exportCSV(rows, cols, exportName('all', 'csv')); }
    finally { setExporting(null); }
  }, [filters, ledger.sort, ledger.order, cols]);

  return (
    <div className="mx-auto flex w-full max-w-[1800px] flex-col gap-4 px-4 pb-10 pt-4 md:px-6">
      <SAPHeader onExport={exportAll} />
      {exporting != null && <div className="text-[12px] text-fg-tertiary" aria-live="polite">Preparing export… {exporting > 0 && `${fmtNum(exporting)} lines`}</div>}
      <SAPFilters />
      <SAPKpiGrid />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <div className="min-h-[380px] xl:col-span-8"><ConsumptionTrend onEvent={(e, b) => setEvent({ e, b })} /></div>
        <div className="max-h-[560px] xl:col-span-4"><InsightsPanel /></div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <div className="h-[460px] xl:col-span-7"><VendorSupply /></div>
        <div className="h-[460px] xl:col-span-5"><LocationMap /></div>
      </div>

      <MaterialAnalytics />
      <ProcurementLedger />

      <DrawerHost />

      {event && (
        <Drawer open onClose={() => setEvent(null)} eyebrow="Detected event" title={`${event.e.label} · ${event.b.bucket}`} width="md" depth={10}
          actions={<Btn variant="primary" onClick={() => setEvent(null)}>Close</Btn>}>
          <p className="text-[13px] text-fg-secondary">Flagged by the rule engine: this period's {event.e.series.replace('_cr', ' value').replace('_qty', ' quantity').replace('_', ' ')} sits {event.e.z}σ {event.e.kind === 'up' ? 'above' : 'below'} the trailing six-period mean. Rule-based, not a model.</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Stat label="This period" value={event.e.series.endsWith('_cr') ? fmtCr(event.e.value) : fmtNum(Math.round(event.e.value))} />
            <Stat label="Trailing baseline" value={event.e.series.endsWith('_cr') ? fmtCr(event.e.baseline) : fmtNum(Math.round(event.e.baseline))} sub="mean of previous 6" />
            <Stat label="PO value ordered" value={fmtCr(event.b.ordered_cr)} sub={`${fmtNum(event.b.pos)} POs`} />
            <Stat label="Delivered" value={fmtCr(event.b.delivered_cr)} />
            <Stat label="Consumed on site" value={fmtCr(event.b.consumed_cr)} sub="MB51" />
            <Stat label="Reversals" value={fmtNum(Math.round(event.b.reversal_qty))} sub="units, MB51" />
          </div>
          <p className="mt-3 text-[12px] text-fg-tertiary">To see the lines behind it, set the date range to {event.b.bucket} in the filter bar.</p>
        </Drawer>
      )}
    </div>
  );
}
