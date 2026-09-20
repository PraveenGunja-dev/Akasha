/* ── Module Deliveries Types ────────────────────────────────────────────── */

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
  /** SAP figures are this project's capacity share of a WBS element shared
   *  with other projects, not a measured per-project number. */
  po_apportioned: boolean;
  po_share_pct: number | null;
  cluster: string;
  is_commissioned: boolean;
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
}
