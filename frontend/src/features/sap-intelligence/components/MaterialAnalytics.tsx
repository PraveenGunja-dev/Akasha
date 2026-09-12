import React, { useState } from 'react';
import { Layers, ChevronRight } from 'lucide-react';
import { Card, CardHeader, SourceTag, cx } from '../../../components/ui/primitives';
import { useMaterials } from '../hooks';
import { useSAPStore } from '../store';
import { fmtCr, fmtNum, fmtPct } from '../format';
import { Skeleton, ErrorBox, Empty } from './Drawer';

type By = 'value' | 'outstanding' | 'consumption' | 'inventory';
const TABS: [By, string, string][] = [
  ['value', 'By PO value', 'ordered'],
  ['outstanding', 'Still to deliver', 'outstanding'],
  ['consumption', 'Site consumption', 'MB51 issued'],
  ['inventory', 'Inventory on hand', 'MB52 value'],
];

/* Materials as a ranked list rather than a chart: the reader wants names and
   figures, and a bar per material adds nothing the number does not say.
   The "(no material code)" bucket — 46% of PO value — is called out above
   the list rather than hidden or ranked as if it were a material. */
export const MaterialAnalytics = () => {
  const [by, setBy] = useState<By>('outstanding');
  const { data, loading, error, refetch } = useMaterials(by, 8);
  const openMaterial = useSAPStore(s => s.openMaterial);
  const rows = data?.materials ?? [];
  const keyf = { value: 'ordered_cr', outstanding: 'outstanding_cr', consumption: 'consumed_cr', inventory: 'inventory_value_cr' }[by] as 'ordered_cr' | 'outstanding_cr' | 'consumed_cr' | 'inventory_value_cr';
  const max = Math.max(1, ...rows.map(r => r[keyf]));
  const nomat = data?.no_material_code;

  return (
    <Card pad="md" className="flex h-full flex-col">
      <CardHeader icon={Layers} eyebrow="Materials" title="Which materials carry the exposure"
        right={<>{data && <span className="hidden text-[12px] text-fg-tertiary lg:inline">{fmtNum(data.material_count)} coded materials</span>}<SourceTag system="SAP" stamp={by === 'consumption' ? 'MB51' : by === 'inventory' ? 'MB52' : 'ZSPS'} /></>} />
      <div role="tablist" className="mb-3 inline-flex self-start rounded-md border border-border-default bg-surface-1 p-0.5">
        {TABS.map(([v, l]) => (
          <button key={v} type="button" role="tab" aria-selected={by === v} onClick={() => setBy(v)}
            className={cx('h-6 rounded px-2 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', by === v ? 'bg-surface-sunken font-medium text-fg-primary' : 'text-fg-tertiary hover:text-fg-primary')}>{l}</button>))}
      </div>
      {nomat && nomat.ordered_cr > 0 && (by === 'value' || by === 'outstanding') && (
        <div className="mb-2 rounded-md border border-dashed border-border-default px-3 py-1.5 text-[12px] text-fg-tertiary">
          <span className="font-medium text-fg-secondary">{fmtCr(by === 'value' ? nomat.ordered_cr : nomat.outstanding_cr)}</span> across {fmtNum(nomat.pos)} POs has no material code and is not ranked below.
        </div>)}
      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
        {error ? <ErrorBox message={error} onRetry={refetch} />
          : loading && !data ? <div className="space-y-2">{[0, 1, 2, 3, 4].map(i => <Skeleton key={i} className="h-11" />)}</div>
            : rows.length === 0 ? <Empty message="No coded materials in this scope." />
              : <ul className="divide-y divide-border-subtle">
                {rows.map(m => (
                  <li key={m.code}>
                    <button type="button" onClick={() => openMaterial(m.code)} className="group flex w-full items-center gap-3 py-2 text-left hover:bg-surface-sunken/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md px-1">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="truncate text-[13px] font-medium text-fg-primary" title={m.name}>{m.name}</span>
                          <span className="shrink-0 text-[13px] font-semibold tabular-nums text-fg-primary">{fmtCr(m[keyf])}</span>
                        </div>
                        <div className="mt-1 h-1 overflow-hidden rounded-sm bg-surface-sunken"><div className="h-full bg-primary" style={{ width: `${(m[keyf] / max) * 100}%` }} /></div>
                        <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-fg-tertiary">
                          <span className="font-mono">{m.code}</span>
                          <span>{fmtPct(m.delivered_pct, 0)} delivered</span>
                          <span>{fmtNum(m.pos)} POs · {fmtNum(m.vendors)} vendors</span>
                          {m.inventory_qty > 0 && <span>{fmtNum(Math.round(m.inventory_qty))} in stock</span>}
                        </div>
                      </div>
                      <ChevronRight className="h-4 w-4 shrink-0 text-fg-tertiary opacity-0 group-hover:opacity-100" />
                    </button>
                  </li>))}
              </ul>}
      </div>
    </Card>
  );
};
