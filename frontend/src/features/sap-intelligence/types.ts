/* SAP Intelligence — shared types. Mirrors backend/routers/sap.py. */

export type POStatus = 'pending' | 'partial' | 'delivered' | 'cancelled';
export type Granularity = 'month' | 'quarter' | 'year';
export type Severity = 'info' | 'success' | 'warning' | 'critical';
export type InsightCategory = 'procurement' | 'inventory' | 'vendor' | 'material' | 'financial' | 'risk' | 'data-quality';

export interface SAPFilters {
  portfolio: string | null;
  project: string | null;
  state: string | null;
  cluster: string | null;
  dateFrom: string | null; // YYYY-MM-DD
  dateTo: string | null;
  vendor: string | null;
  material: string | null;
  status: POStatus | null;
  search: string;
  codes: string[]; // company scope (SPV / AGEL / AGE6L plant codes)
}

export interface Delta { current: number; previous: number; pct: number | null }

export interface Overview {
  kpis: {
    pos: number; vendors: number; materials: number;
    ordered_cr: number; delivered_cr: number; outstanding_cr: number; delivered_pct: number;
    lines: number; dated_lines: number;
    volume_qty: null; inventory_qty: number; inventory_value_cr: number; consumed_value_cr: number;
  };
  period: {
    current: [string, string]; previous: [string, string]; basis: string; dated_share: number;
    pos: Delta; ordered_cr: Delta; vendors: Delta;
  };
  status_mix: Partial<Record<POStatus, number>>;
  synced_at: string | null;
  source: Record<string, string>;
}

export interface TrendBucket {
  bucket: string; ordered_cr: number; pos: number; delivered_cr: number;
  consumed_cr: number; consumed_qty: number; reversal_qty: number; inventory_qty: number;
  utilisation_pct: number; ordered_change_pct: number | null;
}
export interface TrendEvent {
  bucket: string; series: keyof TrendBucket; kind: 'up' | 'down'; label: string;
  value: number; baseline: number; z: number; source: 'rules';
}
export interface Trends { granularity: Granularity; series: TrendBucket[]; events: TrendEvent[]; inventory_total_qty: number }

export interface VendorRow {
  name: string; ordered_cr: number; delivered_cr: number; outstanding_cr: number; delivered_pct: number;
  pos: number; materials: number; last_po: string | null; share_pct: number; outstanding_share_pct: number;
}
export interface VendorDetail extends Omit<VendorRow, 'share_pct' | 'outstanding_share_pct' | 'last_po'> {
  lines: number; dated_lines: number;
  top_materials: { code: string; name: string; ordered_cr: number; delivered_cr: number }[];
  projects: { project: string; ordered_cr: number }[];
  recent_pos: { po: string; date: string | null; ordered_cr: number; delivered_cr: number; lines: number }[];
  trend: TrendBucket[];
  not_available: string[];
}

export interface MaterialRow {
  code: string; name: string; ordered_cr: number; delivered_cr: number; outstanding_cr: number; delivered_pct: number;
  pos: number; vendors: number; consumed_cr: number; inventory_qty: number; inventory_value_cr: number;
}
export interface MaterialDetail {
  code: string; name: string; pos: number; vendors: number; materials: number;
  ordered_cr: number; delivered_cr: number; outstanding_cr: number; delivered_pct: number;
  suppliers: { name: string; ordered_cr: number; delivered_cr: number; pos: number }[];
  consumption: { month: string; value_cr: number; qty: number }[];
  inventory: { qty: number; value_cr: number; unit: string | null };
  projects: { project: string; ordered_cr: number }[];
  unit_prices: { date: string | null; unit_price: number }[];
}

export interface GeoRow { state: string; ordered_cr: number; delivered_cr: number; outstanding_cr: number; delivered_pct: number; pos: number }
export interface Geography {
  states: GeoRow[];
  clusters: (Omit<GeoRow, 'state'> & { cluster: string; state: string | null; lat: number | null; lng: number | null; site: string | null; change_pct: number | null; change_basis: string })[];
  unattributed: { ordered_cr: number; pos: number; reason: Record<string, number> };
  basis: string;
}

export interface POLine {
  id: number; po: string; buyer: string | null; vendor: string | null; material_code: string | null; material: string | null;
  short_text: string | null; date: string | null; delivery_date: null; status: POStatus;
  ordered_cr: number; delivered_cr: number; outstanding_cr: number; qty: number | null; delivered_qty: number | null;
  wbs: string | null; plant: string | null; storage: string | null;
}
export interface PODetail {
  po: string; buyer: string | null; vendor: string | null; date: string | null; status: POStatus;
  ordered_cr: number; delivered_cr: number; outstanding_cr: number; delivered_pct: number; consumed_cr: number;
  projects: string[]; lines: POLine[]; materials: string[]; not_available: string[];
}
export interface LedgerPage { rows: POLine[]; total: number; page: number; size: number }

export interface Insight {
  id: string; category: InsightCategory; severity: Severity; title: string; summary: string;
  metric: string | null; currentValue: number | null; previousValue: number | null; impact: string | null;
  affectedVendors: string[]; affectedMaterials: string[]; affectedPOs: string[];
  recommendation: string | null; evidence: Record<string, unknown>; createdAt: string; source: 'rules';
  aiNote?: string; aiSource?: string;
}

export interface SearchResult { type: 'po' | 'vendor' | 'material' | 'buyer' | 'project'; id: string; label: string }

export interface FilterOptions {
  portfolios: string[]; states: string[]; projects: { id: string; name: string }[]; vendors: string[];
  statuses: POStatus[]; date_min: string | null; date_max: string | null;
}

/** The slice of an ECharts callback param this module reads. */
export interface ChartParam { dataIndex: number; name: string; value?: unknown; componentType?: string; data?: { __event?: TrendEvent } & Record<string, unknown> }

export type WatchKind = 'po' | 'vendor' | 'material' | 'insight';
export interface WatchItem { kind: WatchKind; id: string; label: string; addedAt: string }

export type DrawerState =
  | { kind: 'none' }
  | { kind: 'po'; id: string }
  | { kind: 'vendor'; id: string }
  | { kind: 'material'; id: string }
  | { kind: 'insight'; id: string }
  | { kind: 'kpi'; id: KpiId }
  | { kind: 'ask' }
  | { kind: 'watchlist' }
  | { kind: 'filters' };

export type KpiId = 'pos' | 'vendors' | 'materials' | 'inventory' | 'ordered' | 'delivered' | 'outstanding' | 'pct';

export type LedgerColumn = 'po' | 'buyer' | 'vendor' | 'material_code' | 'material' | 'date' | 'status' | 'ordered_cr' | 'delivered_cr' | 'outstanding_cr' | 'wbs';
