/* Advanced AI planning - shape of GET /api/module-deliveries/advanced-plan
   (backend/services/advanced_planning.py). */

export type StageKey = 'piling' | 'capping' | 'torque_tube' | 'bracing' | 'purlin' | 'module';
export type PlanStatus = 'late' | 'order_now' | 'hold' | 'covered' | 'installed' | 'no_dates';

export interface BlockStage {
  key: StageKey;
  label: string;
  missing?: boolean;
  pct?: number;
  done?: boolean;
  started?: boolean;
  forecast_start?: string | null;
  forecast_finish?: string | null;
  /** How the forecast was made - an estimate, shown as such. */
  basis?: string;
  baseline_finish?: string | null;
  /** Forecast finish minus the assigned-baseline finish; null without a baseline. */
  delay_days?: number | null;
  /** Same forecast with the site's weather (live 16-day forecast, then season). */
  forecast_finish_wx?: string | null;
  /** Days weather adds (negative = a dry stretch saves days). */
  weather_days?: number | null;
}

export interface BlockPlan {
  block: string;
  phase: number | null;
  mwp: number;
  installed_mwp: number;
  remaining_mwp: number;
  stages: BlockStage[];
  need_by: string | null;
  ftc_planned: string | null;
  ftc_actual: string | null;
  status: PlanStatus;
  covered_mwp?: number;
  short_mwp?: number;
  order_by: string | null;
  reason?: string;
  /** Modules land on site: the need date if ordered by order_by, else a lead time from today. */
  arrival?: string;
  arrival_late_days?: number;
  ftc_forecast?: string | null;
  ftc_forecast_wx?: string | null;
  /** Where the order lands after the vendor monthly limit (services.advanced_planning._level_vendor_quota). */
  allocations?: { month: string; mwp: number; mwac: number }[];
  order_by_leveled?: string | null;
  quota?: 'on_time' | 'early' | 'delayed';
  quota_shift_days?: number;
  quota_reason?: string | null;
  /** What sets the block's FTC: site-ready date, install time, charging gap. */
  ftc_parts?: {
    site_done: string; site_done_wx?: string | null; install_days: number; charge_gap_days: number;
    modules_done?: string; held_by?: 'site progress' | 'modules arriving late';
  } | null;
}

export interface StageSummary {
  key: StageKey;
  label: string;
  blocks: number;
  blocks_done: number;
  pct: number;
  done_last_30d: number;
  duration_factor: number;
  factor_basis: string;
  worst_delay_days: number | null;
  forecast_finish: string | null;
}

export interface PhasePlan {
  index: number;
  name: string;
  ftc: string | null;
  charged: boolean;
  blocks: string[];
  mwp: number;
  modules_complete_forecast: string | null;
  at_risk: boolean;
  late_blocks: { block: string; modules_done: string; holding_stage: string | null }[];
  ftc_forecast?: string | null;
  ftc_forecast_wx?: string | null;
  slip_days?: number | null;
}

export interface SiteWeather {
  station: string | null;
  source: string;
  live_until?: string | null;
  heavy_rain_ahead?: string[];
  monsoon_months?: number[];
}

/** The AI prediction service's answer for a project (services/ai_prediction.py). */
export interface AiPrediction {
  order_by: string | null;
  tc: string | null;
  tc_p90?: string | null;
  ftc: string | null;
  confidence?: number | null;
  risk?: string | null;
  deadline_breach_days?: number | null;
  summary?: string | null;
  drivers?: string[];
  actions?: string[];
}

/** The dates shown as the plan: AI where it answered, else the measured engine. */
export interface PlanDecision {
  phase: string | null;
  order_by: string | null; order_by_source: 'ai' | 'engine';
  tc: string | null; tc_source: 'ai' | 'engine';
  ftc: string | null; ftc_source: 'ai' | 'engine';
  source: string;
  confidence?: number | null;
  risk?: string | null;
  engine: { order_by: string | null; tc: string | null; ftc: string | null };
}

export interface ProjectPlan {
  project_id: string;
  ids: number[];
  project_name: string;
  p6_name?: string;
  origin?: string;
  priority?: string;
  plannable: boolean;
  reason?: string;
  data_date?: string;
  baseline?: string | null;
  has_baseline?: boolean;
  lead_days?: number;
  supply?: {
    ordered_mwp: number; received_mwp: number; erected_mwp: number; stock_mwp: number;
    in_transit_mwp: number; on_order_mwp: number; available_mwp: number; need_mwp: number; short_mwp: number;
  };
  stages?: StageSummary[];
  phases?: PhasePlan[];
  phase_basis?: string;
  blocks?: BlockPlan[];
  first_order_by?: string | null;
  no_po?: boolean;
  order_months?: Record<string, number>;
  status?: PlanStatus;
  completion_forecast?: string | null;
  completion_forecast_wx?: string | null;
  weather?: SiteWeather;
  ai?: AiPrediction | null;
  decision?: PlanDecision;
  quota_source?: string;
  quota_flags?: { early: number; delayed: number };
}

export interface QuotaUse {
  limits_mwac: Record<string, number>;
  used_mwac: Record<string, Record<string, number>>;
  months: string[];
  rule: string;
}

export interface AdvancedPlan {
  as_of: string;
  buffer_days: number;
  projects: ProjectPlan[];
  order_months: Record<string, number>;
  basis: string;
  ai_status?: string;
  quota?: QuotaUse;
}
