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
  /** The ordering window has already closed — this is a catch-up order. */
  overdue: boolean;
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
