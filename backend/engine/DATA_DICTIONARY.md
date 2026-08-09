# Akasha Data Dictionary — P6 / SAP / Transmission (TC)

Purpose: single source of truth for what every column *means*, what it's used for,
what can be derived from it, and how it carries risk signal. This is grounding
metadata for the LLM agent (`engine/agent.py`) — it should be handed to the model
as context/tool-schema, not re-implemented as keyword lists. Do not duplicate this
information as hardcoded Python heuristics; compute derived metrics in code, but
keep the *meaning* mapping here as the one place it's maintained.

Status: grounded in the actual SQLAlchemy models in `models.py` and the real
ingestion logic in `scripts/ingest_sap_data.py` / `scripts/ingest_mapping.py`
(2026-07-22). Update this file whenever a model or ingestion script changes —
it will silently go stale otherwise.

---

## 0. Cross-source join keys (the "controlled retrieval" resolver)

This already exists — it's `project_mapping`. Every cross-domain question must
resolve through it before touching P6/SAP/TC tables directly.

| Column | Resolves to | Notes |
|---|---|---|
| `project_mapping.project_id` | P6 join key | Matches `p6_project.project_id`. |
| `sap_project_scope` | Authoritative project-to-SAP rules | Stores one normalized `wbs_prefix` or `plant_code` rule per SPV/AGEL/AGE6L value, including allocation weights for shared scopes. |
| `project_mapping.spv_plant_code` | Legacy/display plant code | Retained for compatibility; it is not authoritative when `sap_project_scope` contains imported master rules. |
| `project_mapping.module_wbs` | Legacy WBS mapping | Used only when the database has no normalized SAP master scopes. |
| `project_mapping.id` | TC join key | Matches `tc_project_entry.mapping_id` and `tc_network_edge.mapping_id` (FK). |
| `project_mapping.tc_progress` (JSON) | Pre-joined TC snapshot | Already cached onto the mapping row — cheap to read, may go stale; check against `tc_network_edge` directly for anything time-sensitive. |
| `project_mapping.capacity_mwac` / `capacity_mwdc` | Nameplate capacity | Denominator for any MW-based (rather than duration-based) percent-complete metric. |
| `project_mapping.cluster` / `subcluster` | Portfolio grouping | Region/EPC rollups. |

**Retrieval rule:** never query `mt_inventory`/`mt_poamount`/`mt_materialdocument`/`tc_*`
by project name directly. Resolve the project through `project_mapping` first, then
query through `sap_project_scope` (SAP) or by `mapping_id` (TC). Fuzzy-matching
project names against SAP/TC tables directly is exactly the kind of ungrounded
guess that produces wrong answers with false confidence.

---

## 1. P6 (Primavera schedule) — `p6_project`, `p6_activity`, `p6_wbs_node`, `p6_baseline_project`, `p6_resource_assignment`, `p6_activity_risk`

### `p6_project` (project-level rollups)

| Column | Business meaning | Used for | Derived metric | Risk relevance |
|---|---|---|---|---|
| `project_id` | P6 "Id" field, the project's canonical identifier | Join key to everything | — | Primary key for all cross-domain queries |
| `duration_percent_complete` | Duration-weighted % of activities complete | Progress | `progress_variance = duration_percent_complete - (spi * 100)` | Large gap vs SPI-implied completion = inconsistent progress reporting |
| `schedule_performance_index` (SPI) | Earned value schedule efficiency ratio | Schedule / status | SPI < 0.9 → "significantly delayed"; 0.9–1.0 → "slightly behind"; ≥1.0 → "on/ahead of schedule" | Primary schedule risk signal |
| `cost_performance_index` (CPI) | Earned value cost efficiency ratio | Financial / status | CPI < 0.9 → over budget; expected spend % = `1/CPI * 100`, compare to actual spend % | Primary cost risk signal |
| `total_float` | Schedule buffer in days on the driving path | Risk / critical path | ≤0 → critical (no buffer); ≤7 → tight; ≤30 → moderate; >30 → comfortable | Direct critical-path risk |
| `finish_date_variance` / `start_date_variance` | Days deviation from baseline dates | Schedule / delay | Positive = late | Combine with `total_float`: **delayed but not critical is inconsistent and should be flagged**, not silently accepted |
| `must_finish_by_date` | Contractual deadline (independent of P6's own schedule) | Risk | `contractual_slack = must_finish_by_date - scheduled_finish_date` | Negative slack = contractual breach risk even if SPI looks fine |
| `actual_total_cost` / `planned_cost` | Spend to date vs budget | Financial | `spent_pct`, `remaining_budget = planned_cost - actual_total_cost` | Overspend at low completion % is a compounding risk |
| `baseline_start_date` / `baseline_finish_date` / `baseline_duration` / `baseline_total_cost` | Original approved plan | Schedule/cost drift | `start_variance_days`, `finish_variance_days` vs current | Drift magnitude and direction (early vs late) |
| `activity_count`, `completed_activity_count`, `in_progress_activity_count`, `not_started_activity_count` | Activity status rollup | Progress | `completion_pct = completed / total` | Large `not_started` bucket late in schedule = risk |
| `status` | Active / Planned / Inactive | Status filter | — | Determines whether other metrics are even meaningful |
| `data_date` / `last_synced_at` | Schedule cutoff date / last sync | Data freshness | `days_stale = now - data_date` | Feed directly into confidence — never invent a freshness score, just report the delta |

### `p6_activity` (activity-level detail)

| Column | Business meaning | Used for | Derived metric | Risk relevance |
|---|---|---|---|---|
| `activity_id`, `name`, `status` | Task identity and state (Completed/In Progress/Not Started) | Progress detail, drill-down | Roll up to project-level completion_pct | — |
| `wbs_code` / `wbs_name` / `wbs_object_id` | Links activity to its WBS node | Structural join to `p6_wbs_node`, and (by code convention) to SAP `wbs_element` | — | Enables activity-level cross-domain matching, not just project-level |
| `total_float`, `is_critical` | Per-activity float / critical-path flag | Risk | Count/percentage of critical activities | `critical_pct = critical_activities / total` — rising trend is a leading indicator before project-level SPI moves |
| `percent_complete` | Activity completion | Progress | — | Compare against planned pace for pace-based risk (not just binary critical/not) |
| `planned_start_date`/`finish_date` vs `actual_start_date`/`finish_date` vs `baseline_start_date`/`finish_date` | Three-way date comparison | Schedule / delay | Slippage at activity level, before it aggregates into project-level variance | Early warning — activity-level slip is detectable before project SPI reacts |

### `p6_wbs_node`

| Column | Business meaning | Used for | Notes |
|---|---|---|---|
| `wbs_code`, `wbs_name`, `parent_object_id` | WBS hierarchy | Structural rollups, drill-down | Tree via `parent_object_id` |
| `is_block`, `block_number` | Flags a WBS node as a physical construction "block" (site sub-area) | Cross-domain join candidate | SAP's `wbs_element` and TC's `block` field are describing the same physical block — this is a join key worth validating, not assuming |

### `p6_baseline_project`, `p6_resource_assignment`, `p6_activity_risk`

| Table | Business meaning | Used for | Notes |
|---|---|---|---|
| `p6_baseline_project` | Snapshot of the plan at baselining time | Schedule/cost drift over the life of the project | One row per baseline type; compare current `p6_project` to this, not just to itself |
| `p6_resource_assignment` | Planned vs actual labor/nonlabor/material units per activity | Progress by units, not just duration | Units-based completion can diverge from duration-based completion — a real accuracy gap the current engine ignores entirely |
| `p6_activity_risk` | **Explicit risk register entries** tied to an activity | Risk | This is directly authored risk data — a "what's risky" question should check this table *first*, before inferring risk from float/SPI heuristics |

---

## 2. SAP — `mt_inventory` (← MB52), `mt_poamount` (← ME2J), `mt_materialdocument` (← MB51), `mt_requirement`, `mt_trialrun`

### `mt_inventory` — source: MB52 "Live Inventory" report

| Column | Business meaning | Used for | Derived metric | Risk relevance |
|---|---|---|---|---|
| `material_code`, `material_name`, `material_description` | Material identity | Lookup | — | — |
| `plant_code`, `wbs_element` | SAP join keys | Resolve to project via `project_mapping` | — | — |
| `unrestricted_qty` (aliased `quantity_inv`) | Stock on hand, usable | Logistics | `stock_coverage = unrestricted_qty / consumption_rate` (needs `mt_materialdocument`) | Low stock + open pending PO qty = supply risk |
| `value_unrestricted` | Value of on-hand stock | Financial | — | Working-capital tied up in unused stock |
| `quantity_mw` (`Inv_Quantity_MW`, via `mw_multiplication_factor`) | Inventory expressed in MW-equivalent | Cross-domain comparability | Directly comparable to P6/TC MW figures — this is the unit that lets you say "X MW of modules in stock vs Y MW required" | — |
| `storage_location_mapping` | Physical storage location | Logistics detail | — | — |
| `special_stock`, `material_type`, `material_group` | SAP stock classification | Filtering/segmentation | — | — |

Note: ingestion (`ingest_sap_data.py`) only loads rows where `unrestricted_qty > 0` and drops "Total" rows — zero-stock materials are **not represented** in this table. A "how much X is in stock" query that finds no row must not report "zero" without checking whether the material was filtered out vs never existed.

### `mt_poamount` — source: ME2J "Purchase Order line items" (statistical POs excluded)

| Column | Business meaning | Used for | Derived metric | Risk relevance |
|---|---|---|---|---|
| `purchasing_document`, `vendor_name`, `buyer_name` | PO identity and accountability | Procurement tracking | — | — |
| `plant_code`, `wbs_element` | SAP join keys | Resolve to project | — | — |
| `order_quantity` | Total ordered qty | Procurement | — | — |
| `still_to_deliver_qty` / `still_to_deliver_inr` | **Pending qty / value not yet delivered** | Logistics / delay | This is the core "pending" signal the business asks about | High pending qty close to a required-by date (from `mt_requirement`) = delivery risk |
| `delivered_qty` / `delivered_value_inr_cr` | Fulfilled to date | Procurement | `fulfillment_pct = delivered_qty / order_quantity` | Low fulfillment_pct late in project schedule = risk |
| `delivery_date`, `delivery_completed_flag` | Expected/actual delivery status | Delay detection | `is_overdue = still_to_deliver_qty > 0 and delivery_date < today` | Direct delay flag |
| `document_date` | PO creation date | Aging | `po_age_days` | Very old open POs with nonzero `still_to_deliver_qty` are a distinct risk pattern from recently placed ones |

### `mt_materialdocument` — source: MB51 "Material consumption/movement" (filtered to movement types 221/222/261/262)

| Column | Business meaning | Used for | Derived metric | Risk relevance |
|---|---|---|---|---|
| `movement_type` | Standard SAP movement type — **221** goods issue to WBS/network (consumption), **222** reversal of 221, **261** goods issue against an order/reservation, **262** reversal of 261 (verify exact meaning against your MM config; these are the SAP-standard defaults) | Distinguishes real consumption from reversed/corrected entries | `net_consumption = sum(221) - sum(222)` (and similarly for 261/262) — **never sum quantity across all movement types without netting reversals**, that double-counts | Consumption pace vs delivered stock reveals pace mismatches or possible diversion/wastage |
| `quantity`, `amount_in_lc` | Volume/value of the movement | Financial + logistics | Net consumption rate over time | — |
| `wbs_element`, `plant_code` | SAP join keys | Resolve to project | — | — |
| `posting_date` | When the movement was recorded | Trend/pace analysis | Consumption rate over a rolling window | — |

### `mt_requirement` — planned material/MW demand (not a raw SAP extract; a planning register keyed to P6)

| Column | Business meaning | Used for | Derived metric | Risk relevance |
|---|---|---|---|---|
| `activity_id`, `activity_name`, `project_name_p6` | Links the requirement to a specific P6 activity | Cross-domain join (P6 ↔ material demand) | — | This is the actual baseline demand row — inventory/PO fulfillment should be measured against *this*, not against an arbitrary assumption |
| `budgeted_units_mw` (`Req_Quantity_MW`) | Planned MW requirement for that activity | Demand baseline | `fulfillment_vs_requirement = (mt_inventory.quantity_mw + delivered via mt_poamount) / budgeted_units_mw` | Requirement far exceeding available/delivered MW, close to the activity's planned date, is the clearest "why is this delayed" signal available |
| `spv_plant_code` | SAP join key | Resolve to project | — | — |

### `mt_trialrun` — commissioning/trial-run tracking

| Column | Business meaning | Used for | Derived metric | Risk relevance |
|---|---|---|---|---|
| `trial_run_start` / `trial_run_finish` | Commissioning milestone window | Progress toward COD | Duration vs plan | Slipping trial-run dates are a late-stage leading indicator for COD risk |
| `tr_quantity_mw` | MW commissioned in the trial run | Progress | Cumulative vs `capacity_mwac`/`capacity_mwdc` from `project_mapping` | — |
| `is_start_before_upload` | Data-quality sanity flag — trial run start predates the data upload | Data quality | — | Treat as a hard data-quality warning, not a real anomaly to report to the user |

---

## 3. Transmission (TC) — `tc_project_entry`, `tc_network_node`, `tc_network_edge`

### `tc_network_edge` (transmission line segments — the highest-value TC table)

| Column | Business meaning | Used for | Derived metric | Risk relevance |
|---|---|---|---|---|
| `edge_id`, `from_node`/`from_label`, `to_node`/`to_label` | Identifies the physical line segment and its two substations | Topology | — | — |
| `contractor`, `voltage`, `length` | Line attributes | Context | — | — |
| `erection`, `foundation`, `stringing` | **Stage-gate construction progress fields** | Progress | Map stage completion to a % (e.g. foundation done ≈25%, erection ≈50%, stringing ≈75%, charged ≈100%) — a real progress metric that currently isn't computed anywhere | The furthest-behind stage on the line blocking evacuation is the actual bottleneck to surface |
| `expected_date`, `scd` (schedule commissioning date?), `charged_date` | Planned vs actual energization dates | Schedule | Variance vs expected | — |
| `status`, `normalized_status` | Raw and normalized line status | Status | — | — |
| `is_delayed` | **Already precomputed delay flag** | Risk | — | Use this directly — don't re-derive delay status heuristically when the ingestion pipeline already computed it |
| `projects` | JSON list of projects served by this line (a line can serve multiple projects) | Cross-domain join | — | A single delayed edge can be the true root cause behind several projects' "why is this delayed" answers simultaneously — this is the clearest case for the cross-domain synthesis the business wants |
| `mapping_id` | FK to `project_mapping` | Join key | — | Note: edges often span multiple projects, so `mapping_id` alone may be a primary/representative link, not exhaustive — check `projects` (JSON) too |

### `tc_project_entry`

| Column | Business meaning | Used for | Notes |
|---|---|---|---|
| `region`, `project`, `phase`, `kps`, `pss`, `block`, `mw` | Project/phase-level transmission scope and capacity | Portfolio rollups | `block` here is a likely (unverified) join candidate to `p6_wbs_node.block_number` — worth validating, not assuming |
| `mapping_id` | FK to `project_mapping` | Join key | — |

### `tc_network_node`

| Column | Business meaning | Used for |
|---|---|---|
| `node_id`, `label`, `type`, `status` | Substation/node identity and state | Topology, map rendering (`x`,`y`) |

---

## 4. Adjacent domain not in scope of this request (flagged for later)

`pulse_nc` (non-conformance) and `pulse_rfi` (inspection requests) exist in the schema
and carry real quality-driven risk signal (`category` = Critical/Non Critical, `debit`
financial penalties, work-breakdown linking to package/activity). Not mapped here
since the request was P6/SAP/TC-scoped, but note it before calling any "risk" answer
complete — a project can look schedule/cost healthy and still be quality-critical.

---

## 5. How this dictionary should be used

1. **Not as a keyword-matching layer.** Feed this file's meaning/join-key content to
   the LLM as system context or per-tool docstrings. Let the model do the natural
   language understanding — that's what it's for. Do not reimplement "semantic
   understanding" as a Python synonym dictionary (see `accuracy_engines.py`'s
   `SemanticUnderstandingEngine` for the anti-pattern to avoid).
2. **Derived metrics belong in code, not in the model's head.** Every "Derived
   metric" cell above should become a small, tested Python function the agent calls
   as a tool — never a number the LLM computes or estimates itself.
3. **Cross-domain answers come from handing the model multiple tool outputs
   together**, not from a hand-written `CrossSourceValidator` trying to enumerate
   every possible P6/SAP/TC combination in advance. Enumerating combinations doesn't
   scale; giving the model grounded facts from all three domains and letting it
   reason does.
4. **Confidence = reported facts, not an invented formula.** Freshness
   (`data_date`/`last_synced_at`/`posting_date` deltas), completeness (fields
   populated vs expected), and join success (did `project_mapping` resolution
   actually find a match) are real, measurable signals. Report them as-is rather
   than blending them into an opaque weighted score presented as false precision.
