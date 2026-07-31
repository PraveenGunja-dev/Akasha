# Chatbot Data Alignment — Chat Handoff

Last updated: 1 August 2026

## Purpose

This document summarizes the dashboard/chatbot data-alignment work completed in this chat and records what should happen next. It is intended to be supplied to a future Codex/chat session together with the repository.

## Original goal

The source question catalogue is `Qns_AKASHA.xlsx`, containing 132 non-empty rows:

- 72 Execution questions
- 60 Planning questions

The objective is for the chatbot to answer as many of these questions as the database supports while preserving its existing general project-question capabilities. Dashboard and chatbot calculations should use the same shared backend services so that the two surfaces do not produce conflicting metrics.

## What was reviewed

- `DASHBOARD_CHATBOT_DATA_ALIGNMENT_PLAN.md`
- `Qns_AKASHA.xlsx`
- Existing chatbot routing, tool registration, orchestration, and shared services
- Live project, P6, SAP, transmission, capacity, quality, and risk data
- Existing and newly added backend tests

## Database coverage found

The live database audit found:

- 63 mapped non-demo projects
- 55 projects with P6 data
- 108,685 P6 activities and 13,325 WBS nodes
- 241,206 P6 resource assignments
- 230 SAP PO rows, 4,102 inventory rows, and 515 material-document rows
- 231 transmission project entries, 323 transmission edges, and 56 nodes
- 679 quality NC rows and 45,271 RFI rows

Important missing sources include historical DPR snapshots, daily site issues, current manpower/headcount, machinery deployment, finance/payment/cash-flow facts, P6 predecessor relationships, authoritative land/GIS data, and weather/waterlogging facts.

## Workbook coverage result

Every workbook row was classified and documented in `CHATBOT_132_QUESTION_ANSWER_CATALOG.md`.

| Classification | Rows | Meaning |
|---|---:|---|
| Fully answerable and tool-addressable | 36 | Current data and chatbot tools can provide a full answer. |
| Partially answerable and tool-addressable | 23 | Chatbot can return a useful answer with explicit limitations. |
| Partially database-answerable but needing tool/routing work | 32 | Data supports part of the answer, but no reliable chatbot calculation/route exists yet. |
| Blocked by missing authoritative source data | 41 | Requires new source integration. |
| **Total** | **132** | **91 database-answerable at least partially; 59 conservatively tool-addressable.** |

The number **91 must not be described as 91 production-verified chatbot questions**. It is the data-coverage total: 36 full plus 55 partial. Only 59 currently have a conservative tool path, and those 59 still need individual end-to-end natural-language evaluation cases.

## Implementation completed in this chat

### Shared schedule calculations

The chatbot received P6 tools backed by the shared schedule service for:

- Daily completion trends over a requested rolling period
- Highest/lowest block progress over last month/current month/last N days

Because historical daily duration-progress snapshots are not persisted, these tools deliberately use dated activity actual-finish events. They label the result as an event-based proxy and do not pretend it is historical duration-percent progress.

### Transmission readiness

A dedicated project transmission tool and shared readiness calculation are present:

- `tc_get_project_lines`
- Readiness percentage = completed associated physical lines / total associated physical lines
- Status values include Ready, In Progress, Not Ready, At Risk, Unknown, and Unavailable
- A delayed associated line forces At Risk

### Additional shared domains

Chatbot tools/services were connected or aligned for:

- Capacity milestones
- Quality analytics
- Dashboard risk metrics
- SAP PO fulfillment, material gaps, inventory, vendors, and consumption
- P6 summaries, delayed/critical activities, forecasts, reports, and portfolio status

### Reporting and visualization implementation update

- Project and portfolio progress reports now share preview/confirmation controls and produce
  both PDF and DOCX from deterministic canonical datasets.
- “Current period” is the current calendar month through the latest synchronized cutoff.
- Reports embed compact chart panels plus KPI and detail tables; project reports include daily
  completion and block progress, while portfolio reports include progress comparison and
  schedule-status distribution.
- Chat visualizations use a versioned ECharts contract, responsive multi-chart cards,
  accessibility descriptions, source freshness, table fallbacks, and full-screen viewing.
- Trend, comparison, distribution, ranking, and block-snapshot intents can trigger charts
  automatically; ordinary factual answers remain text-first and a response is capped at four
  charts.
- Planned-versus-actual curves are deliberately pinned as source-blocked until authoritative
  dated DPR/P6 snapshots are available.
- Current catalog totals are 37 Ready-full, 23 Ready-partial, 31 Tool-gap-partial, and 41
  Source-blocked (60 conservatively tool-addressable rows).

### Routing and tests

Routing tests were added/updated for the new schedule and transmission question families. After the alias, location-disambiguation, and schedule-semantics fixes, the full backend suite passed **293 tests**. This is a historical verification result and should be rerun after subsequent changes.

## Verified example answers

### `AGE26AL_A16_FT_50MW_PPA_Commissioned`

- P6 duration progress: 94.9%
- 648 of 683 activities completed
- Schedule status: Delayed
- Data date: 4 July 2026
- Transmission: Ready, 100%; one associated physical line completed
- SAP quantities: 110,520 ordered, 110,520 delivered, 0 pending; source UOM unavailable
- Capacity: 50 MW, four blocks, all four at COD

### `ARE57L_A12_HSAT_350MW_PPA`

- P6 duration progress: 48.3%
- Forecast finish: 6 October 2026
- Baseline finish: 10 September 2026
- Direct finish-date variance: 26 calendar days late
- Capacity: 350 MW, 28 blocks, no blocks at COD in the audited snapshot
- Material availability risk signal: 18.0%
- Material, schedule, and vendor risk flags active

### `AGE27AL_PSS09`

- Canonical project ID: `AGE27AL_PSS09_FINAL`
- P6 duration progress: 29.3%
- Last audited 30-day period: 150 activity actual-finish events
- Highest event-based block: BLOCK-02, 36 events / 10.32%
- Lowest: BLOCK-06, BLOCK-08, and BLOCK-09 tied at 6 events / 1.72%

## Known transmission chatbot failure

The question “What is its transmission readiness status?” for `AGE27AL_PSS09` produced an inaccurate explanation claiming there was no transmission tool and no project mapping.

Manual verification showed:

- `AGE27AL_PSS09` resolves to `AGE27AL_PSS09_FINAL`.
- Project mapping ID 74 exists.
- That mapping currently has zero transmission project entries and zero associated physical-line records.
- The correct readiness result is therefore **Unavailable**, with no calculable percentage.
- The dedicated transmission tool does exist.

So the chatbot happened to return the correct final availability status but gave the wrong reason.

The routing defect was subsequently fixed in `backend/engine/graph/tool_router.py`. Generic project-status questions are now operational, and pronoun follow-ups preserve the project/domain context. A genuine definition such as “What is transmission readiness?” still receives no database tools.

The catalogue resolver now supports meaningful exact-token aliases embedded in project IDs and P6 names. `BAIYA` resolves to `FY25-BAIYA_600MW`; if the alias belongs to multiple canonical IDs, the resolver returns an explicit ambiguous candidate list. Generic/capacity-only values such as `solar project` or `100MW` are not accepted as aliases.

Location/portfolio fields now participate in alias matching as well. A bare `KHAVDA` query returns all 46 current `Solar Khavda` project candidates instead of silently selecting `NHPC EPC 600 MW Khavda-I`. The chatbot must ask the user to choose a project, plot, capacity, or project ID.

P6 project summaries now expose `forecast_finish`, `delay_reference_finish`, and `forecast_vs_reference_days` explicitly. They also state that planned, actual, and remaining duration are independent native P6 duration fields—not earned hours and not inputs for reconstructing `progress_pct`.

Expected answer:

> Transmission readiness for `AGE27AL_PSS09` is currently Unavailable. The project resolves to canonical ID `AGE27AL_PSS09_FINAL`, but the latest transmission dataset contains no associated physical transmission lines, so a readiness percentage cannot be calculated.

## Important metric rules

- Do not equate activity-completion events with historical duration-percent progress.
- Do not call P6 labor-resource assignment units current manpower or headcount.
- Do not invent an SAP quantity UOM when the source row lacks one.
- Do not sum mixed-currency PO values as one currency total.
- Do not claim rainfall causality from a July–September duration correlation.
- When a source is missing, return a structured missing-data explanation instead of substituting an unrelated metric.

## Recommended next steps

1. Ensure every project-scoped tool receives the canonical project ID returned by `portfolio_resolve_project_id`, not the display/P6 name.
2. Add response-grounding rules so the model cannot say a routed/registered tool does not exist.
3. Convert the 60 currently tool-addressable workbook rows into end-to-end evaluation cases with expected tools, facts, caveats, and freshness assertions.
4. Implement calculation contracts and routing for the remaining 31 partially answerable rows.
5. Integrate new authoritative sources for the 41 source-blocked rows.
6. Rerun the full backend tests and workbook evaluation after each routing/tool expansion.

## Key files

- `DASHBOARD_CHATBOT_DATA_ALIGNMENT_PLAN.md` — overall refactor and phase history
- `CHATBOT_QUESTION_COVERAGE_AND_VERIFIED_ANSWERS.md` — coverage summary and representative verified answers
- `CHATBOT_132_QUESTION_ANSWER_CATALOG.md` — all 132 workbook rows, answers, limitations, and readiness status
- `Qns_AKASHA.xlsx` — source question catalogue
- `backend/services/schedule_metrics_service.py` — shared P6 calculations
- `backend/services/transmission_service.py` — canonical transmission calculations
- `backend/engine/tools/p6_tools.py` — chatbot P6 tools
- `backend/engine/tools/tc_tools.py` — chatbot transmission tools
- `backend/engine/graph/tool_router.py` — deterministic domain/tool routing
- `backend/tests/test_tool_router.py` — routing regression tests
- `backend/tests/test_transmission_service.py` — transmission calculation tests

## Future-chat starter prompt

Use this prompt in a new chat:

> Read `CHATBOT_DATA_ALIGNMENT_HANDOFF.md`, `DASHBOARD_CHATBOT_DATA_ALIGNMENT_PLAN.md`, and `CHATBOT_132_QUESTION_ANSWER_CATALOG.md`. Continue the chatbot data-alignment implementation from the recorded state. Verify canonical project IDs are propagated after alias resolution, then proceed with the remaining tool-gap questions without changing existing dashboard metric semantics.

## Working-tree caution

The repository contained many uncommitted changes during this work, including user changes and the broader dashboard/chatbot refactor. Inspect `git status` and the relevant diffs before editing. Do not discard or reset unrelated work.
