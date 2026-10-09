/* ── Module Deliveries Types ────────────────────────────────────────────── */

/** The LTA rule, evaluated server-side: a PPA project's LTA must not cross its
 *  SCOD, any other project's must not cross its AOP. `contract` is read from
 *  the P6 name's _PPA/_MERCHANT/_GROUP token and is null where the name has
 *  none — in that case the AOP basis is a default, not a reading, and the UI
 *  says so. `days_late` is null when the basis date is missing (no signal,
 *  not a pass) and positive when the LTA lands after it. */
export interface LtaRisk {
  contract: 'PPA' | 'MERCHANT' | 'GROUP' | null;
  is_ppa: boolean;
  basis: 'SCOD' | 'AOP';
  basis_date: string;
  days_late: number | null;
  breached: boolean;
}

/** One phase's share of a single month's order. */
export interface MonthPhase {
  phase_label: string;
  /** MWp of this phase ordered in this month. */
  mwp: number;
  /** The phase's own AC capacity, as stated in its P6 milestone name. */
  mw_ac: number;
  /** The plan of record, from the phase's P6 FTC milestone and the order/TC
   *  dates backward-scheduled from it. These are NOT recomputed when the order
   *  slips — a recalculated FTC would be our inference dressed as a
   *  commitment, and the commitment is the one in P6. */
  order_date: string;
  tc_date: string;
  ftc_date: string;
  /** The month the order actually lands in. */
  order_month: string;
  /** Months later than planned that the order can be placed. 0 = on plan. */
  delay_months: number;
  /** Can the P6 FTC still be met from that month? An order needs its full
   *  lead time plus the 45-day install before FTC. */
  ftc_reachable: boolean;
  /** How many days short, when it cannot. */
  ftc_short_days: number;
  /** Where TC and FTC actually land if the order goes in this late — the
   *  mechanical result of the same lead time and 45-day install run from the
   *  month the order can really be placed. Not a new commitment (the P6 dates
   *  above stay as they are); this is what follows FROM a delay, shown only
   *  where delay_months > 0. Equal to tc_date/ftc_date when delay_months is 0. */
  next_tc_date: string;
  next_ftc_date: string;
  /** The ordering window has already closed — this is a catch-up order. */
  overdue: boolean;
  /** 'site': timed by when the structure will be ready (P6 speed);
   *  'ftc': backward-scheduled from the FTC date. */
  basis?: 'site' | 'ftc';
  /** What an FTC-only plan would have used as the order date. */
  ftc_order_date?: string;
  /** Vendor quota moved it out of its target month. */
  shifted: boolean;
}

export interface ModuleProject {
  sr: number;
  id: number;
  project_name: string;
  spv: string;
  plot: string;
  category: string;
  type: string;             // ALMM / China / SEA / DCR / ALCM
  mms_type: string;         // HSAT / FT
  epc: string;
  ol: number;
  capacity_mwac: number;
  capacity_mwp: number;
  connectivity_phase: string;
  lta: string;
  /** Whether the LTA date itself misses the project's delivery commitment —
   *  SCOD for a PPA project, AOP (Plan) for every other. Server-computed from
   *  the real dates; null where the project has no LTA at all. */
  lta_risk?: LtaRisk | null;
  scod: string;
  scod_lta_diff_days?: number | null;
  scod_source: 'manual' | 'manual_lta' | 'trial_run' | 'tc' | null;
  aop_plan: string;
  ftc_date: string;
  /** True when every FTC phase is already charged — distinct from P6 simply having no FTC milestone. */
  ftc_all_charged: boolean;
  tc_date: string;
  module_date: string;
  ordered_mwp: number;
  balance_ordering_mwp: number;
  total_receipt_mwp: number;
  erection_done_mwp: number;
  /** Total receipt − erection. Can be negative where SAP's delivered qty is
   *  short of what P6 reports erected (every commissioned project, whose old
   *  POs predate the ZSPS extract) — surfaced, not floored. */
  module_inventory_mwp: number;
  module_inventory_negative: boolean;
  /** Measured MB52 stock on hand, for reconciling against the derived figure. */
  module_inventory_sap_mwp: number;
  under_transit_mwp: number;
<<<<<<< Updated upstream
=======
  /** Plan vs actual for the module supply chain, with Ariba as the proof of
   *  dispatch, receipt and finance handover. */
  procurement?: ModuleProcurement;
  /** Site progress from P6 block activities; null when P6 has no block data. */
  site?: SiteProductivity | null;
  /** What the site's pace means for module ordering. */
  ordering_signal?: OrderingSignal;
>>>>>>> Stashed changes
  balance_dispatch_mwp: number;
  completed_ftc_mwp: number;
  status: 'pending' | 'ordered' | 'in_progress' | 'delivered' | 'needs_ordering';
  p6_name: string;
  remarks: string;
  ai_suggestion?: string;
  priority?: 'P1' | 'P2' | 'standard';
  perspectives?: {
    commercial: string;
    supply_chain: string;
    site_execution: string;
    grid_transmission: string;
  };
  month_mwp?: Record<string, number>;
  /** The phases that make up each month's order, in the sequence they must be
   *  placed. The planner fills one phase in full before starting the next, so
   *  a month shows only the phases its MWp actually covers — not the whole
   *  project's phase list. */
  month_phases?: Record<string, MonthPhase[]>;
  /** How much of each month's planned MWp came from a phase whose ordering
   *  date had already passed. Same units as month_mwp and never larger than
   *  it — it marks a cell as overdue without changing the figure shown. */
  month_overdue_mwp?: Record<string, number>;
  planning_flags?: string[];
  /** How the monthly plan was timed: by site speed, or by the FTC date. */
  allocation_basis?: 'site' | 'ftc';
  /** Plain explanation of the basis (or why the site could not set it). */
  allocation_basis_note?: string;
  /** MWp needed only after the forecast window at the site's speed. */
  beyond_window_mwp?: number;
  /** MWp needing an immediate exception order, outside the monthly plan,
   *  because its module date already passed — authoritative from the
   *  planning engine, not re-derived from the date string on this side. */
  excluded_module_date_mwp?: number;
  /** MWp whose P6 FTC cannot be reached from the month its order can be
   *  placed. Decided by the planner, not by the view. */
  ftc_at_risk_mwp?: number;
  /** Worst shortfall in days across those phases. */
  ftc_max_short_days?: number;
  /** MWp whose FTC lands after the LTA — reachable, but past the
   *  transmission window, so transmission becomes the binding constraint. */
  ftc_past_lta_mwp?: number;
  /** SAP figures are this project's capacity share of a WBS element shared
   *  with other projects, not a measured per-project number. */
  po_apportioned: boolean;
  po_share_pct: number | null;
  cluster: string;
  is_commissioned: boolean;
  is_tracked: boolean;
}

<<<<<<< Updated upstream
=======
/** One Ariba delivery event: a PO's consignment that left and landed on the
 *  same days. A different dispatch or receipt date is a separate event. */
export interface AribaDeliveryEvent {
  po: string;
  vendor: string;
  /** IBD creation date (ISO). */
  dispatch_date: string | null;
  /** GR posting date (ISO); null while awaiting GRN. */
  receipt_date: string | null;
  transit_days: number | null;
  /** Days since dispatch, for events still awaiting GRN. */
  age_days: number | null;
  status: 'received' | 'awaiting_grn';
  /** Received GRN qty, or the dispatched IBD qty while awaiting GRN. */
  qty: number;
  mwp: number;
  /** False when a line's module wattage could not be read — MWp understated. */
  mwp_known: boolean;
  rejected_qty: number;
  uom: string;
  rows: number;
  checklist_created: number;
  checklist_numbers: string[];
  checklist_date: string | null;
  /** This project's capacity share of the WBS the line is booked to (1 = sole). */
  share: number;
  lines: string[];
  /** Ariba plant(s) of the lot, e.g. '51Y9'. */
  plant: string;
  /** How the lot was placed on this project: 'plant' (the plant is this
   *  project's alone) or 'po' (plant shared; the PO line's WBS decided). */
  basis: 'plant' | 'po' | null;
  /** The rule spelled out, e.g. 'Plant 51Y9 shared - PO line WBS H-51YA-01-01'. */
  match: string;
}

export interface ModuleProcurement {
  /** Earliest pending order-by date: FTC − 45d − lead time. Inferred, not measured. */
  order_by: string | null;
  /** Earliest module PO document date in SAP. */
  po_first_date: string | null;
  /** po_first_date − order_by in days; positive = ordered after the plan date. */
  order_variance_days: number | null;
  pos: { po: string; vendor: string; po_date: string | null; ordered_mwp: number }[];
  events: AribaDeliveryEvent[];
  lots: number;
  first_dispatch: string | null;
  last_dispatch: string | null;
  last_receipt: string | null;
  received_mwp: number;
  /** Dispatched with no GR posting yet. A lower bound — see the ledger note. */
  awaiting_grn_mwp: number;
  awaiting_grn_lots: number;
  oldest_awaiting_days: number | null;
  checklist_created: number;
  checklist_due: number;
  median_transit_days: number | null;
  shared: boolean;
  /** Module POs (from SAP) that do / do not appear in the Ariba extract. */
  pos_in_ariba: string[];
  pos_not_in_ariba: string[];
  /** proven: Ariba deliveries found · not_in_ariba: SAP has module POs, Ariba
   *  has none of them · no_po: no module PO mapped. */
  ariba_state: 'proven' | 'not_in_ariba' | 'no_po';
  plants: string[];
  /** Received MWp placed by plant vs by PO line WBS (plant shared). */
  matched_by_plant_mwp: number;
  matched_by_po_mwp: number;
}

>>>>>>> Stashed changes
export interface ModuleTotals {
  total_mwac: number;
  total_mwp: number;
  ordered_mwp: number;
  balance_ordering_mwp: number;
  received_mwp: number;
  erection_mwp: number;
  inventory_mwp: number;
  under_transit_mwp: number;
  balance_dispatch_mwp: number;
  completed_ftc_mwp: number;
}

export interface TypeBreakdown {
  mwac: number;
  mwp: number;
  ordered: number;
  received: number;
}

export interface DataCoverage {
  total_projects: number;
  with_sap_data: number;
  with_scod: number;
  with_epc: number;
}

export interface ModuleDeliveriesSummary {
  generated_at: string;
  totals: ModuleTotals;
  projects: ModuleProject[];
  type_breakdowns: Record<string, TypeBreakdown>;
  data_coverage: DataCoverage;
  forecast_months?: string[];
  capacity_summary?: Record<string, {
    monthly_cap_mwp: number;
    monthly_cap_mwac: number;
    lead_time_days: number;
    allocated_by_month: number[];
    allocated_by_month_mwac: number[];
    utilization_pct_by_month: number[];
    peak_month: string;
    peak_mwp: number;
    peak_mwac: number;
  }>;
  strategic_briefing?: {
    scenario_version?: string;
    total_balance_ordering_mwp: number;
    critical_ordering_projects_count: number;
    proactively_leveled_projects_count: number;
    p1_projects_count?: number;
    forecast_months: string[];
    executive_takeaways: string[];
  };
}

/** One P6 block activity type (e.g. "MMS Erection - Purlin") summed over the
 *  project's blocks, with the site norm for its MMS type. */
export interface SiteActivity {
  key: string;
  /** Norm sheet code, e.g. "06". */
  code: string;
  label: string;
  area: 'piling' | 'tracker' | 'module';
  uom: string;
  blocks: number;
  blocks_done: number;
  planned: number;
  done: number;
  pct: number;
  /** What the P6 baseline expected done by the data date, and the gap (points). */
  plan_pct: number | null;
  behind_pts: number | null;
  /** Average since the first actual start, to the P6 data date. */
  pace_per_day: number;
  pace_days: number | null;
  /** To finish by the final pending FTC. */
  required_per_day: number | null;
  days_to_finish: number | null;
  norm_units_per_manday: number | null;
  norm_mandays_per_mwac: number | null;
  mandays_left: number | null;
  manpower_needed_per_day: number | null;
}

export interface SiteArea {
  label: string;
  /** Weighted by the norm effort weights. */
  pct: number;
  /** What the P6 baseline expected done by the data date, and the gap (points). */
  plan_pct: number | null;
  behind_pts: number | null;
  /** When P6's current schedule finishes this stage, and how late the
   *  site's speed runs against it (days; estimate). */
  p6_finish: string | null;
  late_days: number | null;
  blocks: number;
  blocks_done: number;
  done_mwdc: number;
  pace_mwdc_per_day: number;
  pace_days: number | null;
  required_mwdc_per_day: number | null;
  /** At the average pace. Inference. */
  predicted_finish: string | null;
  mandays_left: number | null;
  manpower_needed_per_day: number | null;
}

export interface SiteProductivity {
  data_date: string;
  data_age_days: number;
  mms_kind: 'HSAT' | 'FT' | null;
  mms_source: string | null;
  final_ftc: string | null;
  days_to_ftc: number | null;
  blocks: number;
  module_scope_mwdc: number;
  /** Blocks with the tracker complete (purlin done) whose modules are not yet erected. */
  front_ready_mwdc: number;
  /** P6 FTC moved by how late the slowest moving stage runs. Estimate. */
  ftc_forecast: string | null;
  ftc_delay_days: number | null;
  ftc_driver: string | null;
  /** Set instead of a date when the speed is too low to forecast. */
  ftc_note: string | null;
  areas: Partial<Record<'piling' | 'tracker' | 'module', SiteArea>>;
  activities: SiteActivity[];
}

export type OrderingState = 'modules_short' | 'order_now' | 'stock_building' | 'records_conflict'
  | 'complete' | 'not_started' | 'piling_only' | 'on_track' | 'no_progress';

export interface OrderingSignal {
  state: OrderingState;
  text: string;
  detail: string;
  /** Plain next step for the user. */
  action?: string;
}
