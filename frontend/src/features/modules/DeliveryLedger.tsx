import React from 'react';
import { ArrowRight } from 'lucide-react';
import type { AribaDeliveryEvent, ModuleProcurement } from './types';
import { HelpCard, Tip } from './ModuleTip';

/* Plan-vs-actual ledger for one project's modules, opened under its table row.
   SAP gives the order; Ariba is the proof of what followed it — each dispatch,
   receipt and finance checklist on its own dates, never rolled into a total. */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** '2025-07-04' -> '04-Jul-25', the tracker's date format. */
export function fmtIsoDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${d}-${MONTHS[Number(m) - 1]}-${y.slice(2)}`;
}

const fmtQty = (n: number) => n.toLocaleString('en-IN', { maximumFractionDigits: n < 10 ? 1 : 0 });
const fmtMw = (n: number) => { const d = Math.abs(n) < 1 && n !== 0 ? 2 : 1; return n.toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }); };

/** How Ariba deliveries reached this project, in one short phrase, for the
    table cell and the export (the full rule is on each ledger lot). */
export function aribaMatch(proc: ModuleProcurement | undefined): { text: string; detail: string } {
  if (!proc || proc.ariba_state === 'no_po') return { text: '', detail: 'No module PO is mapped to this project' };
  const of = `${proc.pos_in_ariba.length}/${proc.pos.length} POs`;
  if (proc.ariba_state === 'not_in_ariba') {
    return {
      text: `Not in Ariba · ${of}`,
      detail: `None of this project's module orders (${proc.pos_not_in_ariba.join(', ')}) appear in the Ariba extract, so deliveries cannot be proven yet. Ask for them to be added to the extract.`,
    };
  }
  const plants = proc.plants.join(', ');
  const byPlant = proc.matched_by_plant_mwp > 0;
  const byPo = proc.matched_by_po_mwp > 0;
  const how = byPlant && byPo ? 'Plant + PO' : byPo ? 'PO' : 'Plant';
  const missing = proc.pos_not_in_ariba.length ? ` Orders not in Ariba yet: ${proc.pos_not_in_ariba.join(', ')}.` : '';
  return {
    text: `${how} ${plants} · ${of}`,
    detail: (byPo
      ? `Ariba plant ${plants} serves several projects, so each delivery is matched to this project through its purchase order line in SAP.`
      : `Ariba plant ${plants} belongs to this project only, so its deliveries are this project's.`) + missing,
  };
}

/** Dispatched with no GRN for longer than this is flagged for follow-up. */
const STALE_TRANSIT_DAYS = 30;

function Milestone({ label, value, sub, subTone, note }: {
  label: string; value: string; sub?: string; subTone?: 'risk' | 'muted'; note?: string;
}) {
  return (
    <div className="min-w-[92px]">
      <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
        {note ? <Tip width={280} content={<HelpCard title={label}>{note}</HelpCard>}><span className="underline decoration-dotted underline-offset-2">{label}</span></Tip> : label}
      </div>
      <div className="text-[11px] font-semibold tabular-nums text-foreground">{value}</div>
      {sub && (
        <div className={`text-[9px] tabular-nums ${subTone === 'risk' ? 'text-[var(--status-risk-fg)]' : 'text-muted-foreground'}`}>{sub}</div>
      )}
    </div>
  );
}

const Arrow = () => <ArrowRight className="h-3 w-3 shrink-0 self-center text-muted-foreground/60" aria-hidden />;

function EventStatus({ e }: { e: AribaDeliveryEvent }) {
  if (e.status === 'received') return <span className="text-[var(--status-healthy-fg)]">Received</span>;
  const stale = (e.age_days ?? 0) > STALE_TRANSIT_DAYS;
  return (
    <span className={stale ? 'status-pill-risk' : 'status-pill-watch'}>
      Awaiting GRN{e.age_days != null ? ` · ${e.age_days}d` : ''}
    </span>
  );
}

function EventChecklist({ e }: { e: AribaDeliveryEvent }) {
  if (e.status !== 'received') return <span className="text-muted-foreground">—</span>;
  const title = e.checklist_numbers.length ? `Checklist no. ${e.checklist_numbers.join(', ')}` : undefined;
  if (e.checklist_created === 0) return <span className="text-[var(--status-risk-fg)]">Not raised</span>;
  return (
    <Tip width={260} content={title ? <HelpCard title="Finance checklist">{title}</HelpCard> : undefined}>
    <span className={e.checklist_created < e.rows ? 'text-[var(--status-watch-fg)]' : 'text-foreground'}>
      {e.checklist_created < e.rows ? `${e.checklist_created} of ${e.rows}` : `${e.checklist_numbers.length} raised`}
      <span className="text-muted-foreground"> · {fmtIsoDate(e.checklist_date)}</span>
    </span>
    </Tip>
  );
}

export function DeliveryLedger({ proc, sapReceivedMwp, sharePct }: {
  proc: ModuleProcurement; sapReceivedMwp: number;
  /** This project's capacity share of a WBS shared with other projects; null when sole. */
  sharePct?: number | null;
}) {
  // Open consignments first (they need action), then receipts newest first.
  const events = [...proc.events].sort((a, b) =>
    a.status !== b.status ? (a.status === 'awaiting_grn' ? -1 : 1)
      : (b.receipt_date ?? b.dispatch_date ?? '').localeCompare(a.receipt_date ?? a.dispatch_date ?? ''));
  const coverage = sapReceivedMwp > 0 ? proc.received_mwp / sapReceivedMwp : null;
  const variance = proc.order_variance_days;
  const checklistPending = proc.checklist_due - proc.checklist_created;
  const anyUnknownMw = proc.events.some(e => !e.mwp_known);
  const hasAriba = proc.lots > 0;

  return (
    <div className="flex flex-col gap-2.5 px-3 py-2.5">
      {/* Plan → actual chain */}
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <Milestone label="Order by · plan" value={fmtIsoDate(proc.order_by)}
          sub={proc.order_by ? 'FTC − 45d − lead time' : 'No pending phase'} subTone="muted"
          note="Inferred: back-scheduled from the earliest pending FTC, not a recorded date" />
        <Arrow />
        <Milestone label="PO placed · SAP" value={fmtIsoDate(proc.po_first_date)}
          sub={variance == null ? undefined : variance > 0 ? `${variance}d after plan` : `${-variance}d before plan`}
          subTone={variance != null && variance > 0 ? 'risk' : 'muted'} />
        <Arrow />
        <Milestone label="First dispatch · Ariba" value={fmtIsoDate(proc.first_dispatch)} />
        <Arrow />
        <Milestone label="Last receipt · Ariba" value={fmtIsoDate(proc.last_receipt)}
          sub={proc.median_transit_days != null ? `median transit ${proc.median_transit_days}d` : undefined} subTone="muted" />
        <Arrow />
        <Milestone label="Finance checklist" value={proc.checklist_due ? `${proc.checklist_created} / ${proc.checklist_due}` : '—'}
          sub={checklistPending > 0 ? `${checklistPending} receipt${checklistPending > 1 ? 's' : ''} without checklist` : proc.checklist_due ? 'All raised' : undefined}
          subTone={checklistPending > 0 ? 'risk' : 'muted'} />

        <div className="ml-auto flex gap-5 border-l border-border pl-4">
          {hasAriba ? <>
            <Milestone label="Received · Ariba GRN" value={`${fmtMw(proc.received_mwp)} MWp`}
              sub={coverage != null ? `${Math.round(coverage * 100)}% of SAP ${fmtMw(sapReceivedMwp)} MWp` : undefined} subTone="muted"
              note="Ariba GRN against SAP's received MWp for the same project — the share of receipts Ariba can prove" />
            <Milestone label="Awaiting GRN" value={`${fmtMw(proc.awaiting_grn_mwp)} MWp`}
              sub={proc.awaiting_grn_lots ? `${proc.awaiting_grn_lots} lot${proc.awaiting_grn_lots > 1 ? 's' : ''}, oldest ${proc.oldest_awaiting_days}d` : 'None open'}
              subTone={(proc.oldest_awaiting_days ?? 0) > STALE_TRANSIT_DAYS ? 'risk' : 'muted'} />
          </> : (
            <Milestone label="Received · Ariba GRN" value="Not in Ariba"
              sub={sapReceivedMwp > 0 ? `SAP shows ${fmtMw(sapReceivedMwp)} MWp received, unproven` : undefined}
              subTone={sapReceivedMwp > 0 ? 'risk' : 'muted'} />
          )}
        </div>
      </div>

      {/* The orders */}
      {proc.pos.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
          <span className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">Module POs</span>
          {sharePct != null && (
            <Tip width={300} content={<HelpCard title="Shared purchase orders">These orders are booked in SAP to a project code shared with other projects, and SAP cannot split them. Each project carries its share by capacity, so this project counts {sharePct}% of them.</HelpCard>}>
              <span className="text-[9px] text-muted-foreground underline decoration-dotted underline-offset-2">(this project's {sharePct}% capacity share of a shared WBS)</span>
            </Tip>
          )}
          {proc.pos.map(p => {
            const inAriba = proc.pos_in_ariba.includes(p.po);
            return (
              <Tip key={p.po} width={280} content={<HelpCard title={`PO ${p.po}`}
                  facts={[['Vendor', p.vendor || 'n/a'], ['PO date', fmtIsoDate(p.po_date)], ['Ordered', `${fmtMw(p.ordered_mwp)} MWp`]]}
                  action={inAriba ? undefined : 'Ask for this PO to be included in the Ariba (ZIBDSESREP) extract.'}
                  source="SAP purchase order; Ariba ZIBDSESREP">
                  {inAriba ? 'Deliveries for this order are in Ariba and listed below.' : 'This order does not appear in the Ariba extract, so its deliveries cannot be shown.'}
                </HelpCard>}>
              <span
                className={`inline-block rounded border px-1.5 py-0.5 tabular-nums ${inAriba ? 'border-border bg-card' : 'border-dashed border-border bg-transparent'}`}>
                <span className="font-mono font-medium text-foreground">{p.po}</span>
                <span className="text-muted-foreground"> · {p.vendor || 'Vendor n/a'} · {fmtIsoDate(p.po_date)} · {fmtMw(p.ordered_mwp)} MWp</span>
                {!inAriba && <span className="text-[var(--status-watch-fg)]"> · not in Ariba</span>}
              </span>
              </Tip>
            );
          })}
        </div>
      )}

      {/* Every delivery event on its own row */}
      {events.length === 0 ? (
        <p className="text-[10px] text-muted-foreground">
          {proc.pos.length
            ? `None of this project's ${proc.pos.length} module PO${proc.pos.length > 1 ? 's' : ''} appear in the Ariba extract, and no Ariba delivery is on its plant codes, so no dispatch or receipt can be shown.`
            : 'No module PO is mapped to this project.'}
        </p>
      ) : (
        <div className="max-h-[320px] overflow-auto rounded border border-border bg-card custom-scrollbar">
          <table className="w-full text-[10px] tabular-nums">
            <thead className="sticky top-0 z-10 bg-[var(--neutral-100)] text-[9px] uppercase tracking-wider text-muted-foreground">
              <tr className="[&>th]:px-2 [&>th]:py-1 [&>th]:font-semibold [&>th]:border-b [&>th]:border-border">
                <th className="text-left">Dispatched</th>
                <th className="text-left">Received</th>
                <th className="text-right">Transit</th>
                <th className="text-left">PO · line</th>
                <th className="text-left">Vendor</th>
                <th className="text-right">Qty</th>
                <th className="text-right">MWp</th>
                <th className="text-left">Status</th>
                <th className="text-left">Checklist</th>
                <th className="text-left">Matched by</th>
              </tr>
            </thead>
            <tbody>
              {events.map(e => (
                <tr key={`${e.po}|${e.dispatch_date}|${e.receipt_date}`}
                  className="[&>td]:px-2 [&>td]:py-[3px] [&>td]:border-b [&>td]:border-[var(--border-subtle)] hover:bg-[var(--surface-sunken)]">
                  <td className="whitespace-nowrap">{fmtIsoDate(e.dispatch_date)}</td>
                  <td className="whitespace-nowrap">{fmtIsoDate(e.receipt_date)}</td>
                  <td className="text-right text-muted-foreground">{e.transit_days != null ? `${e.transit_days}d` : '—'}</td>
                  <td className="whitespace-nowrap font-mono">{e.po}<span className="text-muted-foreground"> · {e.lines.join(', ')}</span></td>
                  <td className="max-w-[220px] truncate">{e.vendor || '—'}</td>
                  <td className="text-right whitespace-nowrap">
                    {fmtQty(e.qty)} <span className="text-muted-foreground">{e.uom === 'EA' ? 'pcs' : e.uom}</span>
                    {e.rejected_qty > 0 && <span className="text-[var(--status-risk-fg)]"> · {fmtQty(e.rejected_qty)} rej.</span>}
                  </td>
                  <td className="text-right font-medium">{e.mwp_known ? fmtMw(e.mwp) : '—'}</td>
                  <td className="whitespace-nowrap"><EventStatus e={e} /></td>
                  <td className="whitespace-nowrap"><EventChecklist e={e} /></td>
                  <td className="whitespace-nowrap">
                    <Tip width={300} content={<HelpCard title="How this delivery was matched" source="Ariba plant and SAP purchase order line">{e.basis === 'plant'
                      ? `Ariba plant ${e.plant} belongs to this project only, so the delivery is this project's.`
                      : `Ariba plant ${e.plant} serves several projects, so the delivery is matched to this project through its purchase order line in SAP.${e.share < 0.999 ? ` That order line is shared with other projects, so this project carries ${Math.round(e.share * 100)}% of it.` : ''}`}</HelpCard>}>
                    {e.basis === 'plant' ? <>Plant <span className="font-mono">{e.plant}</span></>
                      : <>PO WBS <span className="text-muted-foreground">· plant <span className="font-mono">{e.plant}</span> shared</span></>}
                    {e.share < 0.999 && <span className="text-muted-foreground"> · {Math.round(e.share * 100)}%</span>}
                    </Tip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[9px] leading-snug text-muted-foreground">
        Each row is one consignment: a PO's deliveries that share a dispatch and a receipt date. Rows are matched plant first: an Ariba plant that belongs to this project alone places the lot here; a plant shared by several projects is resolved by the WBS SAP books the PO line to.
        {(proc.shared || sharePct != null) && ' Quantities on a WBS shared with other projects are this project’s capacity share, so the same PO also appears, in proportion, under those projects.'}
        {' '}Awaiting GRN counts dispatches with no GR posting. A shipment received in part cannot be split further, because the extract carries no IBD number.
        {anyUnknownMw && ' Some lines have no readable module wattage, so their MWp is not shown.'}
      </p>
    </div>
  );
}
