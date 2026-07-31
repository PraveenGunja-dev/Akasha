# Chatbot Question Coverage and Verified Answers

Status date: 31 July 2026

## Purpose

This file translates `Qns_AKASHA.xlsx` into an implementation and verification backlog. It records which question families can be answered from the current project database, which shared service/tool should answer them, and which requests are blocked by missing source data.

The workbook contains 132 non-empty question rows: 72 execution questions and 60 planning questions. The workbook is a coverage specification, not a source of answers. All answers below were calculated from the live database through the shared backend services and chatbot tool adapters.

The complete row-by-row audit and grounded answer catalogue is in [CHATBOT_132_QUESTION_ANSWER_CATALOG.md](./CHATBOT_132_QUESTION_ANSWER_CATALOG.md). Its verified totals are:

| Coverage classification | Rows | Current chatbot status |
|---|---:|---|
| Fully database-answerable | 36 | Tool-addressable |
| Partially database-answerable and tool-addressable | 23 | Returns a qualified partial answer |
| Partially database-answerable but still missing a calculation/route | 32 | Not yet reliably chatbot-ready |
| Blocked by missing authoritative source data | 41 | Must return a structured missing-source result |
| **Total** | **132** | **59 currently tool-addressable; 91 database-answerable at least partially** |

Therefore, **91 is a data-coverage number, not yet a proven chatbot-coverage number**. The conservative current chatbot figure is 59 tool-addressable rows, pending an end-to-end evaluation case for each route.

## Source Coverage Found in the Database

| Source domain | Current live coverage | Important limitation |
|---|---:|---|
| Project catalog | 63 non-demo mapped projects | Some mapping-only projects have no P6 row. |
| P6 schedule | 55 projects, 108,685 activities, 13,325 WBS nodes | Only the latest schedule is stored; historical daily project/activity percentage snapshots are absent. |
| P6 resources | 241,206 assignments | Values are P6 planned/actual assignment units, not a daily DPR manpower-deployment log. |
| P6 activity risks | 0 rows | Risk-reason and dependency questions cannot use a populated P6 risk register. |
| SAP procurement | 230 PO rows, 4,102 inventory rows, 515 material-document rows | No cash-flow, payment, LC/BG/WC approval, or unified currency-normalized CAPEX ledger is present. |
| Capacity milestones | P6/MT milestone inputs available through the shared capacity service | Availability varies by project. |
| Transmission | 231 project entries, 323 line rows, 56 nodes | Readiness is a deterministic physical-line classification, not an independent manually maintained readiness flag. |
| Quality | 679 NC rows and 45,271 RFI rows | Project association may be unavailable or ambiguous for some records. |
| DPR history/issues | No persisted DPR daily snapshot or DPR issue table | True daily duration-progress history, yesterday's DPR narrative, site issues, and zero-progress-site reporting are unavailable. |
| Machinery/weather/land | No authoritative project tables | These questions must return an explicit missing-source result until those sources are integrated. |

## Implemented Question Capabilities

| Workbook question family | Status | Authoritative capability |
|---|---|---|
| Current project progress and schedule status | Supported | `p6_get_project_summary` / `ScheduleMetricsService` |
| Transmission readiness and line status | Supported | `tc_get_project_lines` / `transmission_service` |
| Highest or lowest block progress for last month/current month/last N days | Supported with disclosed proxy | `p6_get_block_period_progress`; ranks dated activity-completion events because historical percentage snapshots are absent. |
| Daily progress trend for last N days | Supported with disclosed proxy | `p6_get_daily_completion_trend`; returns daily actual-finish events and cumulative activity-finish ratio, never historical duration percent. |
| Critical activities and delayed activities | Supported | P6 critical/delay tools through `ScheduleMetricsService` |
| Expected completion versus baseline | Supported | P6 summary and forecast services |
| Portfolio ahead/behind schedule | Supported | Canonical project catalog plus schedule metrics |
| Project progress comparison | Supported compositionally | Resolve each project, call the same P6 summary service, and calculate percentage-point difference. |
| Project/portfolio progress reports | Supported | Shared report dataset and report tools |
| Capacity, quality, named dashboard risks | Supported | Shared capacity, quality, and risk services/tools |
| PO fulfillment, material gaps, vendors, inventory, consumption | Supported where mapped SAP rows exist | Shared SAP project-data service and SAP tools |
| Duration/productivity/manpower what-if planning | Partially supported | Existing simulation tools use completed activities and P6 resource assignments; they do not represent current DPR headcount. |
| Planned progress percentage for a historical period | Blocked by missing source | A time-phased planned-progress curve is not stored. Baseline/forecast dates remain available. |
| DPR issues, daily site updates, current manpower, machinery | Blocked by missing source | Requires DPR ingestion tables and source contracts. |
| Cash flow, vendor payments, financial approvals | Blocked by missing source | Requires finance/payment/approval data beyond current PO and P6 cost summaries. |
| Land capacity, terrain, rainfall, waterlogging | Blocked by missing source | Requires GIS/land and weather sources plus approved calculation rules. |

## Verified Questions and Answers

These are reproducible examples with real project names. Dates are anchored to each project's P6 `data_date`, not the server clock.

### 1. Current project progress

**Question:** What is the current progress of `AGE26AL_A16_FT_50MW_PPA_Commissioned`?

**Answer:** The project is **94.9% complete** using the dashboard-aligned P6 duration-progress formula. P6 reports 648 completed activities out of 683, with 35 not started. The schedule is classified **Delayed** because the forecast finish is later than the approved baseline while progress remains below 100%. Data is as of **4 July 2026**.

### 2. Transmission readiness

**Question:** What is the transmission readiness status for `AGE26AL_A16_FT_50MW_PPA_Commissioned`?

**Answer:** Transmission readiness is **Ready (100.0%)**. The one associated 765 kV Bhuj-I to KPS-I physical line is charged/completed, and no associated line is delayed. Transmission data was last synchronized on **26 July 2026**.

Readiness formula: completed associated physical lines / total associated physical lines. A delayed associated line forces the classification to `At Risk` even if some lines are complete.

### 3. Daily progress trend for the user's example project

**Question:** Show the daily progress trend for `AGE26AL_A16_FT_50MW_PPA_Commissioned` over the last 30 days.

**Answer:** For the 30-day period ending on the project's P6 data date of **4 July 2026**, there were **0 activity actual-finish events**. The event-based trend is therefore flat for that period. Current project duration progress is still **94.9%**, but the database cannot reconstruct day-by-day duration progress because historical P6/DPR percentage snapshots are not persisted.

### 4. Daily progress trend with recorded activity events

**Question:** Show the daily progress trend for `AGE27AL_PSS09` over the last 30 days.

**Answer:** From **14 June through 13 July 2026**, **150 activities** recorded actual finishes. The strongest day in the returned trend was **9 July 2026**, with **20 activity completions**; by that day, 976 activities had an actual finish, equal to **28.17%** of project activities. This is an activity-completion event trend, not a historical duration-progress curve.

### 5. Highest-progress block over a rolling period

**Question:** Which block in `AGE27AL_PSS09` had the highest progress in the last 30 days?

**Answer:** **BLOCK-02** ranked highest from **14 June through 13 July 2026**, with 36 activity completions, equal to **10.32%** of its tracked block activities. Its current average activity completion was **44.01%** at the latest snapshot.

### 6. Lowest-progress block over a rolling period

**Question:** Which block in `AGE27AL_PSS09` had the least progress in the last 30 days?

**Answer:** **BLOCK-06, BLOCK-08, and BLOCK-09 tied** for the lowest event-based progress. Each recorded 6 activity completions, equal to **1.72%** of its tracked block activities. Ties are preserved rather than selecting an arbitrary block.

### 7. Compare project progress

**Question:** Compare progress of `AGE26AL_A16_FT_50MW_PPA_Commissioned` and `ARE57L_A12_HSAT_350MW_PPA`.

**Answer:** `AGE26AL_A16_FT_50MW_PPA_Commissioned` is **94.9%** complete, while `ARE57L_A12_HSAT_350MW_PPA` is **48.3%** complete. The first project is ahead by **46.6 percentage points**. Both are classified delayed against their approved baseline comparisons.

### 8. Expected completion versus baseline

**Question:** What is the expected completion date versus baseline for `ARE57L_A12_HSAT_350MW_PPA`?

**Answer:** The current P6 forecast finish is **6 October 2026**, compared with a baseline finish of **10 September 2026**: **26 calendar days late**. Current progress is **48.3%**, with data as of **11 July 2026**.

### 9. Portfolio schedule status

**Question:** Which projects are ahead or behind schedule in the portfolio today?

**Answer:** Of 63 mapped non-demo projects, **55 have P6 data**. Under the dashboard-aligned delay rule, **35 are delayed** and **20 are on track** at their respective latest P6 data dates. Eight mapped projects have no P6 row and must be reported separately rather than classified.

### 10. Material delivery status

**Question:** Show materials delivered versus pending for `AGE26AL_A16_FT_50MW_PPA_Commissioned`.

**Answer:** The mapped SAP PO rows contain **110,520 ordered units**, **110,520 delivered units**, and **0 pending units**, for **100.0% fulfillment**. The source PO table does not provide a quantity UOM for these rows, so the answer must say `units` rather than inventing modules, MW, or another UOM.

### 11. Connectivity versus execution

**Question:** Is evacuation readiness aligned with execution completion for `AGE26AL_A16_FT_50MW_PPA_Commissioned`?

**Answer:** Transmission is **Ready at 100.0%**, while P6 duration progress is **94.9%**. Evacuation is therefore not lagging execution in the current snapshots. The two percentages have different denominators—physical transmission lines versus P6 duration progress—and must not be subtracted as if they were the same metric.

### 12. Example of an explicit missing-source answer

**Question:** What machinery is currently deployed at `AGE26AL_A16_FT_50MW_PPA_Commissioned`?

**Answer:** **Unavailable from the current project database.** There is no authoritative DPR machinery-deployment table or equivalent source. P6 non-labor resource assignments cannot be relabeled as current on-site machinery without an approved mapping and daily deployment semantics.

## Required Source Additions for Full Workbook Coverage

1. Persist immutable P6/DPR daily snapshots with project, block, activity, planned progress, actual progress, data date, and source batch ID.
2. Ingest DPR daily issue, zero-progress, manpower, productivity, and machinery tables with canonical project/block identity.
3. Add P6 predecessor/dependency relationships and populate activity-risk records.
4. Add finance facts for approved budget, commitments, actuals, cash-flow forecast, invoices/payments, and LC/BG/WC approvals with currency semantics.
5. Add material manufacturing/dispatch/in-transit milestones with ETA and quantity UOM.
6. Add land/GIS, weather, rainfall, and waterlogging sources before enabling Khavda terrain/monsoon calculations.

Until those sources exist, the chatbot should return structured `missing_data` or `unsupported_source` results for affected questions. It should not refuse generically, invent a number, or substitute a superficially similar metric.
