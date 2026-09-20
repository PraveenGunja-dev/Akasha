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
  scod_source: 'manual' | 'trial_run' | 'tc' | null;
  aop_plan: string;
  ftc_date: string;
  tc_date: string;
  module_date: string;
  ordered_mwp: number;
  balance_ordering_mwp: number;
  total_receipt_mwp: number;
  erection_done_mwp: number;
  module_inventory_mwp: number;
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
