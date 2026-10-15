import React from 'react';
import { ArrowRight } from 'lucide-react';
import type { AribaDeliveryEvent, ModuleProcurement } from './types';

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

/** Dispatched with no GRN for longer than this is flagged for follow-up. */
const STALE_TRANSIT_DAYS = 30;

function Milestone({ label, value, sub, subTone, note }: {
  label: string; value: string; sub?: string; subTone?: 'risk' | 'muted'; note?: string;
}) {
  return (
    <div className="min-w-[92px]" title={note}>
      <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
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
    <span title={title} className={e.checklist_created < e.rows ? 'text-[var(--status-watch-fg)]' : 'text-foreground'}>
      {e.checklist_created < e.rows ? `${e.checklist_created} of ${e.rows}` : `${e.checklist_numbers.length} raised`}
      <span className="text-muted-foreground"> · {fmtIsoDate(e.checklist_date)}</span>
    </span>
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
            <Milestone label="Received · Ariba GRN" value="No Ariba record"
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
            <span className="text-[9px] text-muted-foreground" title="These POs are booked to a WBS element shared with other projects; SAP cannot tell them apart, so each project carries its capacity share">
              (this project's {sharePct}% capacity share of a shared WBS)
            </span>
          )}
          {proc.pos.map(p => (
            <span key={p.po} className="rounded border border-border bg-card px-1.5 py-0.5 tabular-nums">
              <span className="font-mono font-medium text-foreground">{p.po}</span>
              <span className="text-muted-foreground"> · {p.vendor || 'Vendor n/a'} · {fmtIsoDate(p.po_date)} · {fmtMw(p.ordered_mwp)} MWp</span>
            </span>
          ))}
        </div>
      )}

      {/* Every delivery event on its own row */}
      {events.length === 0 ? (
        <p className="text-[10px] text-muted-foreground">
          {proc.pos.length
            ? `None of this project's ${proc.pos.length} module PO${proc.pos.length > 1 ? 's' : ''} appear in the Ariba extract, so no dispatch or receipt can be shown.`
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
                  <td className="max-w-[220px] truncate" title={e.vendor}>{e.vendor || '—'}</td>
                  <td className="text-right whitespace-nowrap">
                    {fmtQty(e.qty)} <span className="text-muted-foreground">{e.uom === 'EA' ? 'pcs' : e.uom}</span>
                    {e.rejected_qty > 0 && <span className="text-[var(--status-risk-fg)]"> · {fmtQty(e.rejected_qty)} rej.</span>}
                  </td>
                  <td className="text-right font-medium">{e.mwp_known ? fmtMw(e.mwp) : '—'}</td>
                  <td className="whitespace-nowrap"><EventStatus e={e} /></td>
                  <td className="whitespace-nowrap"><EventChecklist e={e} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[9px] leading-snug text-muted-foreground">
        Each row is one consignment: a PO's deliveries that share a dispatch and a receipt date. Rows are matched to this project through the PO line's WBS in SAP.
        {(proc.shared || sharePct != null) && ' Quantities on a WBS shared with other projects are this project’s capacity share, so the same PO also appears, in proportion, under those projects.'}
        {' '}Awaiting GRN counts dispatches with no GR posting. A shipment received in part cannot be split further, because the extract carries no IBD number.
        {anyUnknownMw && ' Some lines have no readable module wattage, so their MWp is not shown.'}
      </p>
    </div>
  );
}
