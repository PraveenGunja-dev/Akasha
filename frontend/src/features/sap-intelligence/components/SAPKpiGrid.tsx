import React from 'react';
import { FileText, Users, Layers, Package, IndianRupee, CheckCircle2, Truck, Percent } from 'lucide-react';
import { KPITile, type KPIDelta } from '../../../components/ui/primitives';
import { useOverview } from '../hooks';
import { useSAPStore } from '../store';
import { fmtCr, fmtNum, fmtPct } from '../format';
import type { KpiId } from '../types';

/* Two rows, two weights. Counts describe the dataset; money describes the
   position, so money is the larger tier. No tile carries a colour unless it
   encodes a state — none of these do.

   "vs previous period" is computed on document_date and only exists on the
   figures that have one. The tile says which population it describes. */
export const SAPKpiGrid = () => {
  const { data, loading, error, refetch } = useOverview();
  const openKpi = useSAPStore(s => s.openKpi);
  const top = useSAPStore(s => s.drawers[s.drawers.length - 1]);
  const sel = (id: KpiId) => top?.kind === 'kpi' && top.id === id;

  const k = data?.kpis; const p = data?.period;
  const delta = (d?: { pct: number | null; previous: number }, unit = ''): KPIDelta | undefined => {
    if (!d || d.pct == null) return undefined;
    return { value: `${d.pct > 0 ? '+' : ''}${d.pct.toFixed(0)}%${unit}`, direction: d.pct > 0 ? 'up' : d.pct < 0 ? 'down' : 'flat', label: 'vs previous period' };
  };
  const periodNote = p ? `Period: ${p.current[0]} → ${p.current[1]} vs ${p.previous[0]} → ${p.previous[1]}. Based on PO document date, present on ${p.dated_share.toFixed(0)}% of lines.` : undefined;
  const common = { loading: loading && !data, error: error ? 'Unavailable' : undefined, onRetry: refetch, source: 'SAP' as const };

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
      <KPITile {...common} size="supporting" icon={FileText} label="Total POs" value={fmtNum(k?.pos)} delta={delta(p?.pos)} polarity="neutral" info={periodNote}
        onClick={() => openKpi('pos')} selected={sel('pos')} className="xl:col-span-2" />
      <KPITile {...common} size="supporting" icon={Users} label="Vendors" value={fmtNum(k?.vendors)} delta={delta(p?.vendors)} polarity="neutral" info="Distinct vendor names on PO lines. Lines with no vendor recorded are excluded from the count."
        onClick={() => openKpi('vendors')} selected={sel('vendors')} className="xl:col-span-2" />
      <KPITile {...common} size="supporting" icon={Layers} label="Materials" value={fmtNum(k?.materials)} info="Distinct material codes. 46% of PO value carries no material code and is not counted here."
        onClick={() => openKpi('materials')} selected={sel('materials')} className="xl:col-span-2" />
      <KPITile {...common} size="supporting" icon={Package} label="Inventory on hand" value={fmtCr(k?.inventory_value_cr)}
        subtext={k ? `${fmtNum(Math.round(k.inventory_qty))} units · MB52 snapshot` : undefined}
        info="MB52 stock value. MB52 has no history, so there is no period comparison."
        onClick={() => openKpi('inventory')} selected={sel('inventory')} className="xl:col-span-2" />

      <KPITile {...common} size="primary" icon={IndianRupee} label="PO amount" value={fmtCr(k?.ordered_cr)} delta={delta(p?.ordered_cr)} polarity="neutral" info={periodNote}
        onClick={() => openKpi('ordered')} selected={sel('ordered')} className="xl:col-span-2" />
      <KPITile {...common} size="primary" icon={CheckCircle2} label="Delivered" value={fmtCr(k?.delivered_cr)}
        proportion={k ? { pct: k.delivered_pct, nowLabel: `${fmtPct(k.delivered_pct)} of PO amount` } : undefined}
        info="Delivered value as recorded in ZSPS. Was previously labelled “Utilised” and sourced from MB51 site consumption — a different system."
        onClick={() => openKpi('delivered')} selected={sel('delivered')} className="xl:col-span-2" />
      <KPITile {...common} size="primary" icon={Truck} label="Still to deliver" value={fmtCr(k?.outstanding_cr)}
        proportion={k ? { pct: 100 - k.delivered_pct, nowLabel: `${fmtPct(100 - k.delivered_pct)} of PO amount` } : undefined}
        info="PO amount minus delivered. Reconciles exactly against ZSPS."
        onClick={() => openKpi('outstanding')} selected={sel('outstanding')} className="xl:col-span-2" />
      <KPITile {...common} size="primary" icon={Percent} label="% delivered" value={k ? k.delivered_pct.toFixed(1) : '—'} unit="%"
        stats={k ? [{ label: 'Consumed on site', value: fmtCr(k.consumed_value_cr) }, { label: 'MB51', value: 'goods issued' }] : undefined}
        info="Delivered ÷ PO amount. “Consumed on site” is MB51 goods issued — shown beside the PO figures, never subtracted from them."
        onClick={() => openKpi('pct')} selected={sel('pct')} className="xl:col-span-2" />
    </div>
  );
};
