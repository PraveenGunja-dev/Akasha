import React from 'react';
import { HelpCard } from './ModuleTip';

/* Header help for the Ariba and site-progress columns, written for someone
   who has not seen the tracker before: what the column is, how to read it,
   and where the number comes from. */

export const COLUMN_HELP: Record<string, React.ReactNode> = {
  ariba_match: (
    <HelpCard title="Ariba matched by"
      source="Ariba ZIBDSESREP extract, matched to SAP purchase orders">
      How this project's module deliveries were found in Ariba. <b>Plant</b>: the Ariba plant belongs to this
      project only. <b>PO</b>: the plant serves several projects, so each delivery is matched through its purchase
      order line in SAP. <b>3/3 POs</b> means all three of the project's module orders appear in Ariba;
      <b> Not in Ariba</b> means none do yet.
    </HelpCard>
  ),
  ariba_grn: (
    <HelpCard title="Received · Ariba (MWp)" source="Ariba goods receipts (GRN) on this project's module orders">
      Modules booked as received at site in Ariba. This is the proof of delivery. The % beside it compares it
      with SAP's Total Receipt; a low % means part of what SAP shows as received has no Ariba receipt behind it.
    </HelpCard>
  ),
  last_grn: (
    <HelpCard title="Last receipt (GRN date)" source="Ariba goods receipts">
      The date modules were last received at site for this project. A date weeks old on a project still
      mounting modules means deliveries have stopped.
    </HelpCard>
  ),
  awaiting_grn: (
    <HelpCard title="Dispatched, no GRN (MWp)" source="Ariba inbound deliveries without a goods receipt">
      Modules the vendor has dispatched that are not yet booked as received at site. They are either still on
      the road, or have arrived and are waiting to be booked. Red when the oldest has waited more than 30 days.
    </HelpCard>
  ),
  checklist_status: (
    <HelpCard title="Finance checklist (raised / due)" source="Ariba checklist on each receipt">
      After every receipt, a finance checklist is raised so the vendor can be paid. <b>37/37</b> means every
      receipt has its checklist; a lower first number means some receipts are still waiting for one.
    </HelpCard>
  ),
  deliveries: (
    <HelpCard title="Deliveries (lots)">
      Click to open this project's detail: how far the site has got (piles, structure, modules) and every
      module delivery on its own dispatch and receipt dates.
    </HelpCard>
  ),
  site_piling: (
    <HelpCard title="Piles installed (%)" source="P6, block by block (latest schedule)">
      Piles are the posts driven into the ground that everything stands on. This is the share installed across
      all blocks: piles for the structure, for inverters and for robot docking stations. Click a value for its
      speed and expected finish.
    </HelpCard>
  ),
  site_tracker: (
    <HelpCard title="Structure built (tracker, %)" source="P6, block by block (latest schedule)">
      The steel frame on the piles that holds the panels (also called tracker or MMS). It is built in three
      steps: torque tube, bracing, then purlin. Panels can only be mounted once the purlin is done, so this
      column decides when modules are really needed.
    </HelpCard>
  ),
  site_module: (
    <HelpCard title="Modules mounted (%)" source="P6 module installation, block by block">
      Solar panels fixed onto the finished structure. Red when, at today's speed, mounting would finish after
      the project's FTC date.
    </HelpCard>
  ),
  behind_plan: (
    <HelpCard title="Behind plan (P6 baseline)" source="P6 baseline dates for every block activity">
      How far the site is behind what the P6 baseline planned by now, in percentage points, for the stage that
      is furthest behind (piles, structure or modules). <b>−26 pts</b> means 26% of the work should have been done
      by now and is not. <b>On plan</b> means every stage is where the baseline expected.
    </HelpCard>
  ),
  ftc_forecast: (
    <HelpCard title="FTC forecast (site speed)" source="P6 block progress compared with P6's own plan">
      When FTC is likely if the site keeps its current speed. It is the P6 FTC moved by how late the slowest
      moving stage runs. <b>+120d</b> means about 120 days after the P6 date. An estimate, not a commitment;
      <b> Too slow</b> means the stage is moving too slowly to forecast a sensible date.
    </HelpCard>
  ),
  front_ready: (
    <HelpCard title="Structure ready, no modules (MWdc)" source="P6: blocks with purlin done minus modules mounted">
      Structures that are finished but still have no panels. This is work the site can start the day modules
      arrive, so it should be covered by modules in the yard.
    </HelpCard>
  ),
  ordering_signal: (
    <HelpCard title="Module supply vs site"
      source="P6 site progress compared with SAP receipts and open orders">
      Are modules arriving at the right speed for the site?
      <span className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
        <b className="text-[var(--status-risk-fg)]">Modules short</b><span>Structures are ready, panels are missing.</span>
        <b className="text-[var(--status-critical-fg)]">Order now</b><span>The structures will finish before a new order could arrive.</span>
        <b className="text-[var(--status-watch-fg)]">Excess modules</b><span>Panels are arriving faster than structures to mount them on.</span>
        <b className="text-[var(--status-watch-fg)]">Data mismatch</b><span>SAP and P6 disagree; fix the records first.</span>
        <b className="text-[var(--status-healthy-fg)]">Supply matches site</b><span>No shortage, no excess.</span>
        <b>Piling in progress / Not started</b><span>Too early for modules.</span>
      </span>
      <span className="mt-1.5 block">Click a signal for the figures and what to do.</span>
    </HelpCard>
  ),
};
