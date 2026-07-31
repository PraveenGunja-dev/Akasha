# Chatbot Workbook Question-and-Answer Catalogue

Status date: 31 July 2026

This catalogue covers every one of the 132 non-empty rows in `Qns_AKASHA.xlsx`: 72 Execution rows and 60 Planning rows. Placeholder questions have been grounded with representative live projects. Answers are based on the latest database snapshot and the shared backend services.

## How to read the status

| Status | Meaning |
|---|---|
| `Ready-full` | The current chatbot has an applicable tool/route and the available source can answer the row fully. |
| `Ready-partial` | The current chatbot can return a useful, explicitly qualified partial answer. |
| `Tool-gap-partial` | The database supports a partial answer, but a dedicated calculation, argument contract, or router path is still required before claiming reliable chatbot support. |
| `Source-blocked` | The authoritative facts are not in the current database. The chatbot must return a structured missing-source response. |

Totals: **37 Ready-full**, **23 Ready-partial**, **31 Tool-gap-partial**, and **41 Source-blocked**. Thus **91/132 rows are database-answerable at least partially**, and **60/132 are conservatively tool-addressable today**. “Tool-addressable” is not the same as having passed 60 end-to-end natural-language evaluation cases; that is the next verification gate.

Metric cautions used throughout:

- P6 “progress” means the dashboard-aligned duration-progress calculation.
- A rolling trend means dated activity actual-finish events because historical daily duration-percent snapshots are absent.
- P6 labor-resource assignment units are not current DPR worker headcount.
- SAP quantities are reported as generic units where the PO rows have no quantity UOM.
- Monsoon factors are historical duration ratios for activities starting in July–September, not proof of rainfall causation.

## Execution questions (72)

| ID | Grounded question | Status | Verified answer or required limitation |
|---|---|---|---|
| E01 | What is the current progress of `AGE26AL_A16_FT_50MW_PPA_Commissioned`? | Ready-full | **94.9%**, with 648/683 activities complete; status **Delayed**, data date 4 Jul 2026. |
| E02 | How does its current progress compare with planned progress for the last month? | Ready-partial | Current progress is **94.9%**. The database has baseline/forecast dates but no time-phased planned-percent curve, so a planned-versus-actual percentage for that month cannot be calculated. |
| E03 | What is its transmission readiness status? | Ready-full | **Ready, 100%**: its one associated 765 kV physical line is charged/completed and none is delayed. |
| E04 | Compare `AGE26AL_A16_FT_50MW_PPA_Commissioned` with `ARE57L_A12_HSAT_350MW_PPA`. | Ready-full | **94.9% vs 48.3%**; the first is ahead by **46.6 percentage points**. Both are delayed against baseline. |
| E05 | What is the current progress of `ARE57L_A12_HSAT_350MW_PPA` as of its latest update? | Ready-full | **48.3%**, with 1,273 completed, 85 in-progress, and 1,381 not-started activities; data date 11 Jul 2026. |
| E06 | Which block in `AGE27AL_PSS09` had the highest progress in the last 30 days? | Ready-full | **BLOCK-02**, with 36 completion events (**10.32%** of its tracked activities) from 14 Jun–13 Jul 2026. |
| E07 | Which block in `AGE27AL_PSS09` had the least progress in the last 30 days? | Ready-full | **BLOCK-06, BLOCK-08, and BLOCK-09 tied**, each with 6 events (**1.72%**). |
| E08 | Show the daily progress trend for `AGE27AL_PSS09` over the last 30 days. | Ready-partial | **150 actual-finish events**; peak was **20 on 9 Jul 2026**. This is an event trend, not historical duration-percent progress. |
| E09 | What is the current status of Phase 2 in `ARE57L_A12_HSAT_350MW_PPA`? | Tool-gap-partial | The project is 48.3% and delayed, but “Phase 2” needs an approved phase-to-WBS mapping and a phase-filtered aggregation tool. |
| E10 | Show phase-wise progress for all solar projects. | Tool-gap-partial | WBS/activity data exists for 55 projects, but no canonical phase taxonomy and portfolio phase aggregator exists yet. |
| E11 | What was yesterday’s DPR update for `AGE27AL_PSS09`? | Source-blocked | No persisted DPR daily snapshot or narrative table exists. |
| E12 | What issues were reported at `AGE27AL_PSS09` today? | Source-blocked | No authoritative daily site-issue/DPR issue table exists. |
| E13 | Which sites reported zero progress today? | Source-blocked | Daily site progress snapshots are not persisted, so zero-progress sites cannot be identified. |
| E14 | What is actual-versus-baseline variance for `ARE57L_A12_HSAT_350MW_PPA`? | Ready-full | Forecast finish **6 Oct 2026** versus baseline **10 Sep 2026**: **26 calendar days late**. |
| E15 | List the top five reasons for its schedule variance. | Tool-gap-partial | Delayed/critical activities can be ranked, but causal “reasons” are not stored in a populated risk/reason register; the chatbot must label activity evidence as indicators, not causes. |
| E16 | Which activities are on its critical path? | Ready-full | Leading critical/negative-float items include Inverter Structure Ordering, Module Ordering, Control Box delivery, AC/DC material delivery, Inverter Structure delivery, Module delivery, and WMS delivery. |
| E17 | Which dependencies are causing maximum delay? | Source-blocked | P6 predecessor/dependency relationships are not available through the current source model. |
| E18 | What is its expected completion date versus baseline? | Ready-full | **6 Oct 2026** forecast versus **10 Sep 2026** baseline, **26 days late**. |
| E19 | Which portfolio projects are ahead or behind schedule? | Ready-full | Of 63 mapped projects, 55 have P6 data: **35 delayed**, **20 on track**, and 8 unclassified because P6 data is absent. |
| E20 | Which blocks contribute most to delay in `ARE57L_A12_HSAT_350MW_PPA`? | Tool-gap-partial | Delayed activities identify Blocks 42, 46, 47, and 48 with roughly 148–149-day drift, but a deterministic block-delay contribution aggregator is still needed. |
| E21 | Generate a management progress report for `AGE26AL_A16_FT_50MW_PPA_Commissioned`. | Ready-full | The confirmed report flow generates chart-rich PDF and DOCX files from one current schedule/material/capacity/transmission dataset; historical planned-versus-actual comparison remains unavailable. |
| E22 | Provide a progress snapshot of all blocks in `AGE27AL_PSS09`. | Ready-full | Block snapshot data and a current-month horizontal progress visualization are available; current average activity completion includes BLOCK-01 **46.59%**, BLOCK-02 **44.01%**, and BLOCK-03 **36.65%**. |
| E23 | Generate a portfolio-level progress report for the current period. | Ready-full | The confirmed portfolio report flow generates PDF and DOCX with KPI counts, project comparison and schedule-status charts, and project detail. Current period means the current calendar month through the latest synchronized cutoff. |
| E24 | Show planned-versus-actual progress chart for `ARE57L_A12_HSAT_350MW_PPA`. | Source-blocked | A historical planned/actual progress curve is not stored. Current point and finish-date variance alone are insufficient for this chart. |
| E25 | Which projects risk missing planned milestones this month? | Ready-full | The milestone-risk tool checks incomplete milestones due in the current data month and flags due/past-due dates, nonpositive float, or baseline slip. It is a transparent rule-based snapshot, not a probabilistic forecast. |
| E26 | Highlight risks that could impact the critical path of `ARE57L_A12_HSAT_350MW_PPA`. | Ready-partial | Material and schedule flags are active; the project has **18.0% material availability**, **48.3% progress**, and negative-float procurement/delivery activities. Causality is not proven. |
| E27 | What are its major deviations from plan? | Ready-full | It is **26 days late by finish-date comparison**, at 48.3%, with multiple negative-float procurement/delivery activities and Blocks 42/46/47/48 showing large activity drift. |
| E28 | Suggest actions to avoid delay in `ARE57L_A12_HSAT_350MW_PPA`. | Ready-partial | Prioritize negative-float module/inverter/control-box deliveries, validate the low material-availability signal, and recover Block-42/46/47/48 cable/module work. Recommendations require site validation. |
| E29 | Which projects are likely to miss deadlines? | Ready-full | Current schedule status identifies **35 delayed projects** among the 55 with P6 data; the risk service can rank them by severity. |
| E30 | What is the impact of delayed module delivery on `ARE57L_A12_HSAT_350MW_PPA`? | Tool-gap-partial | Module delivery is on the negative-float critical list, so it is a schedule risk, but no approved material-to-activity causal-delay model currently quantifies days of impact. |
| E31 | Recommend priority actions for today on `ARE57L_A12_HSAT_350MW_PPA`. | Ready-partial | Address negative-float procurement/delivery, reconcile material availability, and recover delayed Blocks 42/46/47/48 first; this is a rule-based recommendation, not a site directive. |
| E32 | What are its current execution risks? | Ready-full | **Material, schedule, and vendor risks are flagged**; financial and procurement flags are not. COD is classified **Critical/at risk**. |
| E33 | Which blocks are at risk due to low progress in `AGE27AL_PSS09`? | Ready-full | Rolling-period laggards are BLOCK-06/08/09 at **1.72% event progress** each; current averages are **18.56%, 20.72%, and 21.98%**. |
| E34 | Are dependencies likely to delay commissioning? | Source-blocked | Dependency links are unavailable, so the chatbot cannot make a defensible dependency-to-commissioning claim. |
| E35 | Which logistics delays may affect upcoming installation in `ARE57L_A12_HSAT_350MW_PPA`? | Ready-full | SAP gaps and critical P6 delivery activities can be returned; module, inverter-structure, control-box, AC/DC material, and WMS deliveries require attention. |
| E36 | Are connectivity milestones aligned with execution progress for `AGE26AL_A16_FT_50MW_PPA_Commissioned`? | Ready-full | Transmission is **100% Ready** while execution is **94.9%**; connectivity is not lagging execution. Denominators differ and must not be directly subtracted. |
| E37 | What is the expected completion month for `ARE57L_A12_HSAT_350MW_PPA`? | Ready-full | **October 2026**, based on forecast finish 6 Oct 2026. |
| E38 | Which milestones are likely to slip if current trends continue? | Ready-full | Negative-float critical activities and forecast milestones can be ranked; current evidence emphasizes material procurement/delivery and Block-42 commissioning work. |
| E39 | How does forecast completion compare with baseline? | Ready-full | For `ARE57L_A12_HSAT_350MW_PPA`, forecast is **26 calendar days later** than baseline. |
| E40 | Will it be ready for commissioning as scheduled? | Ready-full | Current evidence says **at risk**: COD risk is true, tier Critical, and forecast finish is later than baseline. |
| E41 | Is evacuation readiness aligned with execution completion? | Ready-full | For the 50 MW commissioned project, yes: evacuation is Ready/100% and execution is 94.9%. |
| E42 | What is current CAPEX utilization for `ARE57L_A12_HSAT_350MW_PPA`? | Tool-gap-partial | P6 cost fields and PO values exist, but there is no approved, currency-normalized CAPEX budget-versus-actual definition. |
| E43 | Which POs are delayed or amended recently? | Ready-partial | Material gaps can identify pending POs, but amendment history is absent. For the 50 MW project, 5 mapped rows across 2 POs show no pending quantity. |
| E44 | What is its cash-flow status? | Source-blocked | No authoritative cash-flow fact table exists. |
| E45 | Are LC, BG, or WC financial approvals pending? | Source-blocked | Approval workflow/status data is absent. |
| E46 | Which vendors have pending payments? | Source-blocked | PO fulfillment is present, but invoice/payment status is not. |
| E47 | What is budget-versus-actual cost variance? | Tool-gap-partial | Some P6/SAP values exist, but no approved budget, actual-cost, currency, and accounting-period contract supports this calculation. |
| E48 | Which activities show cost overruns? | Source-blocked | Activity-level approved budget and actual cost are not available with auditable semantics. |
| E49 | What are the top reasons for cost deviations? | Source-blocked | Cost deviations and causal reason codes are absent. |
| E50 | Which delays are affecting cash flow? | Source-blocked | Joining schedule delay to cash-flow facts is impossible because cash-flow facts are absent. |
| E51 | How much cash outflow is expected next month? | Source-blocked | No payment/cash-flow forecast exists. |
| E52 | Which delayed activities affect the cash forecast? | Source-blocked | Delayed activities exist, but there is no cash forecast to join to them. |
| E53 | How much manpower was deployed in a plot last month? | Source-blocked | P6 resource units are not a daily plot-level deployed-headcount log. |
| E54 | Map manpower trend for the last month. | Source-blocked | No historical DPR manpower series exists. |
| E55 | What was monthly manpower-supply variance? | Source-blocked | Planned-versus-actual monthly headcount is not stored. |
| E56 | What is manpower utilization across sites? | Ready-partial | P6 actual labor assignment units can be summarized, but must be called **resource units**, not worker headcount or site utilization. |
| E57 | What is current manpower deployed at `ARE57L_A12_HSAT_350MW_PPA`? | Source-blocked | Current deployed headcount is not available. |
| E58 | How does actual manpower compare to planned manpower? | Ready-partial | P6 planned/actual assignment units permit a resource-unit comparison, not a current headcount comparison. |
| E59 | Which blocks are under- or over-staffed? | Tool-gap-partial | Block/WBS resource assignments exist, but an approved staffing baseline and block-level aggregator are required. |
| E60 | Is manpower productivity aligned with planned progress? | Ready-partial | Completed-activity duration and labor assignment units can indicate productivity; they cannot validate DPR headcount productivity against a time-phased planned curve. |
| E61 | Which sites had lower productivity last month? | Tool-gap-partial | Per-project productivity can be computed, but portfolio comparison, period filtering, and normalized activity units need a dedicated tool. |
| E62 | What is current material availability for `ARE57L_A12_HSAT_350MW_PPA`? | Ready-full | The risk snapshot reports **18.0% material availability**; the answer must show source freshness and distinguish inventory from PO fulfillment. |
| E63 | Which materials are pending delivery? | Ready-full | The SAP material-gap tool returns ordered, delivered, pending, PO, vendor, and project mapping where quantity semantics exist. |
| E64 | What is the ETA of modules for a block? | Tool-gap-partial | PO/material rows exist, but a reliable block allocation plus manufacturing/dispatch/ETA milestone contract is missing. |
| E65 | Are material delays affecting installation schedules? | Ready-full | Material bottleneck analysis can flag overlap between shortages and scheduled work; for the 350 MW project, material risk is active and module delivery is negative-float. |
| E66 | Which logistics delays can affect upcoming milestones? | Ready-full | The tool can combine SAP gaps with P6 critical/forecast activities; it must present correlation as risk evidence, not proven causation. |
| E67 | Show materials delivered versus pending for the 50 MW project. | Ready-full | **110,520 ordered, 110,520 delivered, 0 pending; 100% fulfillment.** Quantity UOM is absent, so report generic units. |
| E68 | What machinery is currently deployed at the project? | Source-blocked | No authoritative machinery-deployment table exists. |
| E69 | Is machinery utilization aligned with execution needs? | Source-blocked | Deployment, availability, utilization, and demand facts are absent. |
| E70 | Which sites face machinery shortages? | Source-blocked | No site machinery inventory/shortage source exists. |
| E71 | Are machinery constraints affecting progress? | Source-blocked | Machinery constraints cannot be joined to progress because the source is absent. |
| E72 | Which activities are affected by equipment unavailability? | Source-blocked | Equipment availability and activity-impact mapping are absent. |

## Planning questions (60)

The planning examples use `ARE57L_A12_HSAT_350MW_PPA`, `AGE27AL_PSS09`, and `FY25-BANDHA` where each has useful P6/SAP evidence. A project-specific answer must always resolve the user’s actual project first.

| ID | Grounded question | Status | Verified answer or required limitation |
|---|---|---|---|
| P01 | What is the expected execution duration of `ARE57L_A12_HSAT_350MW_PPA` from current productivity? | Tool-gap-partial | P6 forecasts completion on **6 Oct 2026**, but a generic MW-to-duration model needs normalized scope and activity productivity inputs. |
| P02 | What is its minimum achievable duration under optimal conditions? | Tool-gap-partial | What-if calculations can scale selected activity productivity, but “optimal” conditions and safe acceleration limits are not defined. |
| P03 | How many days are required per 1 MW, 10 MW, and 80 MW? | Tool-gap-partial | Capacity and completed-activity durations exist, but a validated MW-normalized production model is still needed; simple linear scaling would be misleading. |
| P04 | Based on current site conditions, what is the fastest possible completion time? | Tool-gap-partial | Current forecast and productivity exist, but site constraints and safe maximum productivity are incomplete. |
| P05 | How does block-wise execution compare with parallel blocks? | Tool-gap-partial | Block schedules exist; a dependency/resource-constrained parallel-scenario engine does not. |
| P06 | Which activity dictates overall project duration? | Tool-gap-partial | Negative-float activities can be ranked, but without full predecessor logic the chatbot cannot prove the controlling activity. |
| P07 | Manpower requirement and duration coupling. | Tool-gap-partial | P6 labor resource units and completed-activity durations support an indicative relationship, not a worker-headcount production curve. |
| P08 | What minimum manpower is required for a target completion date? | Tool-gap-partial | The database lacks current headcount and approved productivity norms needed to solve this reliably. |
| P09 | If manpower increases 10%/20%, how much can duration reduce? | Ready-partial | The what-if tool can scale selected activity labor productivity and report an indicative duration delta; it assumes proportionality and is not a committed forecast. |
| P10 | Show the manpower-versus-duration curve. | Ready-partial | Multiple what-if runs can produce a resource-unit scaling curve; label the x-axis as P6 labor-resource scaling, not workers. |
| P11 | Which activity remains the bottleneck after manpower increases? | Tool-gap-partial | Productivity and critical activities exist, but an integrated post-scenario critical-path recalculation is missing. |
| P12 | Which activity remains the bottleneck after manpower increases? | Tool-gap-partial | Duplicate of P11 in the workbook; same limitation applies. |
| P13 | Quantity and area-based scope estimation. | Source-blocked | No authoritative land/GIS area facts or approved area-to-capacity norms exist. |
| P14 | How many blocks fit within the project area? | Source-blocked | Project geometry, usable area, setbacks, and density rules are absent. |
| P15 | For a project MW, how many modules, tables, MMS structures, and strings are required? | Source-blocked | No approved engineering design ratios/module-rating configuration is stored for generic estimation. |
| P16 | What quantity remains for each construction component? | Tool-gap-partial | Remaining P6 activities and SAP quantities exist, but they are not normalized into one component-level installed-versus-scope model. |
| P17 | How much work remains per hectare/per block? | Source-blocked | Block work may be inferred from P6, but hectare geometry is absent. |
| P18 | How many modules are required for an 80 MW block? | Source-blocked | Current module wattage, DC/AC ratio, losses, and approved design quantity are missing. |
| P19 | How many days are required to install 80 MW with current manpower? | Ready-partial | Completed-activity productivity can provide an indicative duration after selecting comparable activity scope; current manpower headcount is unavailable. |
| P20 | What manpower completes 80 MW in 60/90/120 days? | Tool-gap-partial | A solver needs current headcount, normalized MW productivity, and safe staffing limits; current P6 resource units are insufficient. |
| P21 | What daily installation target is needed to meet schedule? | Tool-gap-partial | Remaining days are available, but installed/remaining physical quantities and UOM mappings are incomplete. |
| P22 | How many installation teams must run in parallel? | Tool-gap-partial | Team composition, crew productivity, work fronts, and dependencies are not modeled. |
| P23 | Construction activity sequencing and impact. | Tool-gap-partial | Activity dates/statuses support a schedule narrative, but predecessor relationships are absent. |
| P24 | Which activities must finish before module installation starts? | Source-blocked | P6 predecessor/dependency links are not available. |
| P25 | What happens if MMS completion is delayed? | Tool-gap-partial | MMS duration/productivity can be measured, but propagating a delay to successor dates requires dependencies. |
| P26 | Can module installation start before full MMS completion? | Tool-gap-partial | Actual overlap may be observed, but safe/approved partial-start logic and dependency rules are absent. |
| P27 | Which activities can be parallelized safely? | Source-blocked | Safety constraints and predecessor logic are not stored. |
| P28 | Which sequence deviation causes maximum delay? | Source-blocked | Baseline-versus-actual sequence and dependency causality cannot be reconstructed reliably. |
| P29 | How many days are needed to install the remaining modules? | Ready-partial | Module activity productivity exists; the answer is indicative until remaining module quantity and UOM mapping are validated. |
| P30 | Is material availability sufficient for planned manpower productivity? | Ready-full | The material-bottleneck tool compares available/pending material with relevant P6 work; the 350 MW project is flagged at **18.0% material availability**. |
| P31 | What happens if module supply falls by 20%? | Tool-gap-partial | Current supply and productivity evidence exists, but no parameterized supply-reduction scenario propagates quantity loss to activity dates. |
| P32 | Which blocks are affected first by material shortage? | Ready-partial | Upcoming/critical block activities can be cross-checked against SAP gaps; block allocation quality must be disclosed. |
| P33 | Is installation faster or slower than material supply? | Ready-partial | Construction activity productivity and SAP delivery/consumption can be compared when UOMs align; otherwise the tool must return an incompatibility warning. |
| P34 | Manufacturing, lead time, and supply productivity. | Source-blocked | Manufacturing start/finish, dispatch, in-transit, and promised-date milestones are not stored consistently. |
| P35 | Is manufacturing output aligned with required daily installation? | Source-blocked | Manufacturing output time series and compatible installation quantities are absent. |
| P36 | How many days of site work does module inventory support? | Ready-partial | Inventory and installation productivity can yield days-of-cover only where module UOM and project mapping align; otherwise it must remain unavailable. |
| P37 | What if module delivery is delayed 15 days? | Tool-gap-partial | A delivery offset can be stated, but schedule propagation needs material-to-activity links and dependencies. |
| P38 | Which blocks remain idle due to supply constraints? | Source-blocked | Daily idle-state/block-cause facts are absent. |
| P39 | Is supply productivity above or below construction productivity? | Source-blocked | No reliable manufacturing/supply output time series with compatible UOM exists. |
| P40 | What is the land area and MW capacity of Khavda Plot X? | Source-blocked | No authoritative GIS/land source is present. |
| P41 | How many Khavda blocks can execute in parallel? | Tool-gap-partial | P6 block schedules show planned overlap, but land access, crews, machinery, and dependencies needed for feasible concurrency are incomplete. |
| P42 | What is realistic execution pace at Khavda versus other sites? | Ready-full | Comparable completed activities can be benchmarked. Example P6 averages: FY26-P04 piling **52.28 days/activity** versus FY25-BANDHA **34.43**; scope differences must be disclosed. |
| P43 | Which Khavda blocks are most operationally constrained? | Ready-full | Low progress, delay, critical activities, and material/transmission risks can rank blocks; constraints are evidence-based signals, not site-observed causes. |
| P44 | How does Khavda terrain affect manpower deployment? | Source-blocked | Terrain/GIS and deployed-manpower data are absent. |
| P45 | Monsoon, rainfall, and water-logging impact. | Ready-partial | Historical Jul–Sep duration ratios are available. For FY25-BANDHA, foundation averaged **1.13× baseline** across 169 instances; this is seasonal correlation, not rainfall causality. |
| P46 | With 1,000 mm rain over X hectares, how much water accumulates? | Source-blocked | A raw volume formula is possible, but runoff, infiltration, drainage, elevation, and authoritative site area are absent; an operational answer would be unsafe. |
| P47 | How many days will land remain unworkable from water-logging? | Source-blocked | Weather, soil, drainage, elevation, and daily workability data are absent. |
| P48 | Which activities stop completely during monsoon? | Source-blocked | No approved weather-to-activity shutdown rules or daily cause codes exist. |
| P49 | Which activities continue at reduced productivity? | Source-blocked | Seasonal ratios exist, but they do not prove rain-caused reduction or define safe operating rules. |
| P50 | What schedule slippage is expected due to monsoon? | Ready-partial | Seasonal activity multipliers can estimate an indicative range; it must be labeled scenario output, not weather forecast or causal attribution. |
| P51 | Productivity loss and recovery planning. | Ready-partial | Seasonal ratios and productivity what-if tools can frame a recovery scenario, with explicit assumptions. |
| P52 | What additional manpower is needed to recover lost days? | Ready-partial | The labor-resource what-if can estimate proportional scaling for selected activities; it cannot prescribe worker headcount. |
| P53 | How many extra shifts are needed for recovery? | Tool-gap-partial | Duration gaps exist, but shift length, crew composition, productivity decay, safety, and labor constraints are not modeled. |
| P54 | What is the fastest recovery strategy without compromising safety? | Ready-partial | Tools can prioritize negative-float activities and simulate bounded productivity improvement; site leadership must validate safety and feasibility. |
| P55 | Which blocks should be prioritized after monsoon? | Ready-full | Rank low-progress/high-delay blocks with critical work and material readiness; for AGE27AL, BLOCK-06/08/09 are rolling-period laggards. |
| P56 | What work remains? | Ready-full | For the 350 MW project: **85 activities in progress and 1,381 not started**; capacity service shows **350 MW/28 blocks remaining before COD**. |
| P57 | How many days are needed to complete remaining work? | Ready-partial | Latest forecast gives the schedule answer; productivity simulation can provide an indicative alternative, subject to data-date and scenario assumptions. |
| P58 | What is the earliest achievable completion date? | Ready-full | The current deterministic P6 forecast for the 350 MW project is **6 Oct 2026**; “earliest under acceleration” requires an explicit scenario. |
| P59 | Which blocks should finish first to minimize delay? | Ready-full | Prioritize blocks containing negative-float/commissioning-path activities; current evidence highlights Blocks 42, 46, 47, and 48. |
| P60 | What strategy minimizes manpower while meeting schedule? | Ready-partial | Compare bounded labor-resource scenarios and prioritize critical activities; this optimizes P6 resource units, not actual crew rosters. |

## Implementation conclusion

The correct present-tense statement is:

> The database can provide a full or qualified partial answer for 91 of the 132 workbook rows. The chatbot currently has a conservative tool path for 59 of those rows. The other 32 answerable rows need additional calculation contracts or routing, and 41 rows need new authoritative source data.

Before claiming production support, each of the 59 tool-addressable rows should be converted into an end-to-end evaluation case using the exact grounded question, expected tools, required caveats, and a freshness assertion.
