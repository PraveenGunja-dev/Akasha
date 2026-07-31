# Dashboard and Chatbot Data Alignment Plan

## 1. Purpose

This plan defines a phased refactor that makes the Akasha dashboard and chatbot use the same authoritative backend calculations.

The dashboard is the approved behavioral baseline for source-backed business metrics. The refactor will preserve existing dashboard results unless a metric is explicitly marked for later business review. The chatbot will access those calculations through shared backend services rather than duplicating dashboard logic or reading values from the frontend.

The intended architecture is:

```text
Database
   |
   v
Shared Authoritative Services
   |
   +--> Existing Dashboard APIs
   |
   +--> Chatbot Tools
   |
   +--> Reports and Chart Builders
```

## 2. Goals

- Make equivalent dashboard and chatbot questions return the same facts from the same database snapshot.
- Preserve current API URLs and response fields wherever they are correct.
- Preserve approved dashboard calculations during extraction.
- Remove duplicated filtering, mapping, joining, and calculation logic.
- Ensure missing, stale, or unavailable data is represented explicitly.
- Attach source, unit, formula, and freshness metadata to operational facts.
- Add automated parity tests that prevent future dashboard-chatbot divergence.
- Keep the LLM responsible for explanation and presentation, not business calculations.

## 3. Non-Goals

- The chatbot will not scrape or read values from the rendered dashboard UI.
- Production values will not be hardcoded into chatbot prompts or tools.
- Existing endpoint URLs will not be renamed as part of this refactor.
- The frontend will not become the shared calculation layer.
- This refactor will not attempt to repair source-system data.
- This refactor will not guarantee correct answers when the underlying source data is incorrect or stale.
- Business metric definitions will not be redesigned unless explicitly approved.

## 4. Confirmed Business Decisions

| Area | Confirmed decision |
|---|---|
| Authoritative behavior | Source-backed dashboard calculations are the initial baseline. |
| Runtime data | All values continue to be queried dynamically from the database. |
| Total project population | Use non-demo `ProjectMapping` records. |
| Overall progress | Preserve the dashboard's current progress calculation during extraction. |
| Delayed project | Preserve the dashboard's current delay calculation and thresholds. |
| PO value | Preserve the value and interpretation currently displayed by the relevant dashboard view. |
| Material availability | Preserve the dashboard's current inventory and in-transit calculation. |
| Transmission records | Use the approved latest-record behavior and the dashboard's project-association rules. |
| COD and Trial Run | Preserve dashboard behavior, including COD taking precedence over Trial Run where currently applied. |
| Risk score | Use the same calculation as the corresponding dashboard risk view. |
| Projects without P6 records | Keep them in the portfolio and answer from every non-P6 domain for which matched data exists. Missing P6 must not make the entire project unavailable. |
| Existing APIs | Keep current URLs and preserve response compatibility wherever possible. |
| New metadata | Add source and freshness fields additively before considering any breaking contract change. |

## 5. Missing-P6 Compatibility Decision

### Missing P6 Schedule Status

The general behavior for a mapped project without a corresponding `P6Project` record is now confirmed:

- Keep the project in the authoritative portfolio population.
- Return project identity, mapping metadata, portfolio classification, and mapped capacity.
- Query SAP, transmission, quality, and other non-P6 domains independently.
- Return facts from each domain for which matched records exist.
- Mark only the unavailable domain or metric as unavailable.
- Do not treat missing P6 data as meaning the entire project has no data.
- Do not infer P6 schedule facts from mapping or unrelated source data.

The existing dashboard schedule surface preserves its current compatibility behavior when P6 data is absent:

- Display `On Track`.
- Expose compatibility progress `0`.
- Include the project in the dashboard on-track aggregate.

This fallback is not an authoritative P6 fact and does not change the partial-source policy:

- Mapping-only projects remain part of the authoritative portfolio population.
- Mapping and capacity facts remain available.
- SAP, transmission, and quality services independently return matched data when it exists.
- P6-derived fields remain nullable and carry a `p6_available` or equivalent availability indicator.
- No shared service should infer schedule health from absent P6 data.
- The fallback remains isolated in the dashboard compatibility adapter and must not be emitted as chatbot evidence.

Example answer behavior:

> AGE25CL is a mapped Wind portfolio project with 254.8 MW capacity. P6 schedule data is unavailable, and no matched SAP or transmission records were found.

The example values illustrate current database coverage and must not be hardcoded into runtime chatbot logic.

Questions that remain answerable without P6 include:

- Whether a project exists in the portfolio.
- Project name, ID, cluster, category, SPV, plant, plot, subcluster, priority, WBS mapping, and mapped capacity where populated.
- Portfolio lists, counts, classifications, and capacity aggregates.
- SAP procurement, inventory, logistics, and consumption questions when matched SAP records exist.
- Transmission questions when matched TC records exist.
- Quality questions when matched Pulse records exist.
- Source-availability questions, including which domains have data for a project.

Questions that require P6 and must not be inferred when P6 is unavailable include:

- Overall P6 schedule progress.
- Planned, scheduled, or forecast finish dates.
- SPI, CPI, float, and finish-date variance.
- Delayed or on-track schedule classification.
- Critical path and critical activities.
- P6 activity counts and status breakdowns.
- P6-derived COD or Trial Run milestones.

Required partial-source response policy:

```text
Include the project in the portfolio.
Answer every domain for which matched data exists.
Mark only unavailable domains as unavailable.
Never treat missing P6 as meaning the entire project has no data.
```

## 6. Current-State Summary

The dashboard and chatbot use the same database but frequently use different backend functions.

Current differences include:

- Project population and portfolio filtering are implemented in multiple routes and tools.
- Overview, Project 360, PMAG, and chatbot tools do not all calculate progress identically.
- SAP project matching varies between exact WBS, substring WBS, bounded WBS hierarchy, and plant fallback.
- Transmission consumers use different association and deduplication rules.
- Capacity calculations exist in dashboard routes and Project 360 with different supporting rules.
- Quality project matching is separate from the canonical project mapping.
- Risk labels refer to different calculations in different dashboard sections.
- Dashboard responses can use five-minute process caches while chatbot tools query the database directly.
- Source freshness is returned inconsistently and is not fully persisted in chatbot response metadata.

The project-total mismatch has already been corrected: both the Overview and chatbot portfolio list now use non-demo project mappings.

## 7. Design Principles

### 7.1 Shared Services, Thin Adapters

Business calculations belong in backend services. Dashboard routes and chatbot tools should validate inputs, invoke a service, and serialize the result.

### 7.2 Preserve Behavior Before Improving It

Each dashboard calculation must first be characterized with tests. The initial extraction should preserve its approved result. Corrections can be proposed separately with business evidence and explicit approval.

### 7.3 One Canonical Project Scope

Every domain must resolve portfolio and project scope through the same project catalog and identity rules.

### 7.4 Typed Facts Before Natural Language

The shared layer returns typed facts. The chatbot may explain those facts but must not replace, reinterpret, or silently recalculate them.

### 7.5 Explicit Missing Data

Missing values must remain null or unavailable. A missing source must not silently become zero, healthy, completed, or on track.

### 7.6 Provenance and Freshness

Every operational result should identify its source system, data cutoff, synchronization time, unit, and calculation version where applicable.

### 7.7 Compatibility First

Existing dashboard frontend consumers are external consumers of the backend contracts. Shared-service extraction should not require a simultaneous frontend rewrite unless a calculation currently exists only in the frontend.

## 8. Target Service Boundaries

| Service | Responsibility |
|---|---|
| `ProjectCatalogService` | Project population, demo filtering, portfolio scope, identifiers, aliases, and deterministic resolution. |
| `ScheduleMetricsService` | P6 progress, dates, activity counts, variance, delay, SPI/CPI, and critical activities. |
| `SapProjectDataService` | PO totals, delivery, pending quantity, inventory, consumption, vendor metrics, and approved WBS/plant matching. |
| `TransmissionService` | Latest records, project association, phase/KPS mapping, deduplication, statuses, progress, and delay. |
| `CapacityMilestoneService` | Project capacity, blocks/WTGs, COD, Trial Run, remaining capacity, and trends. |
| `QualityAnalyticsService` | Pulse project association, NC/RFI totals, closure, aging, trends, and contractor metrics. |
| `RiskAnalyticsService` | Named dashboard risk calculations built from the preceding services. |
| `FreshnessService` | Per-source data cutoff, sync timestamps, staleness evaluation, and cache versioning. |
| `ChartSpecService` | Charts generated only from authoritative service results. |
| `ProjectProgressReportService` | Report datasets generated from authoritative service results. |

Service names may be adjusted to match repository conventions during implementation. Responsibilities should remain separated by domain.

## 9. Metric Contract

Shared services should return domain DTOs with a common evidence envelope.

Example:

```json
{
  "metric_id": "project.progress",
  "scope": {
    "project_id": "FY26-P18"
  },
  "value": 23.1,
  "unit": "percent",
  "formula_version": "dashboard-progress-v1",
  "source_system": "P6",
  "source_tables": ["p6_project"],
  "data_as_of": "2026-07-18T00:00:00Z",
  "last_synced_at": "2026-07-22T05:07:00Z",
  "warnings": []
}
```

Required semantics:

- Counts and identifiers use exact values.
- Percentages declare whether they are represented as `0-1` or `0-100`; the preferred API representation is `0-100`.
- Durations and variances declare their unit.
- Currency values declare currency and scale.
- Missing values remain `null` and include a warning or availability field.
- Rounding occurs once in the shared service or serializer, not independently in each consumer.
- `data_as_of` represents the business-data cutoff.
- `last_synced_at` represents ingestion time.
- Formula versions change only when business semantics change.

## 10. Phased Implementation

### Phase 0: Baseline and Decision Register

Objective: freeze the approved current behavior before moving calculations.

Work:

- Record the confirmed decisions from this plan in a metric register.
- Record the approved missing-P6 dashboard compatibility behavior.
- Inventory each dashboard KPI, its current code path, source tables, filters, formula, unit, and rounding.
- Distinguish metrics with similar labels, especially risk and progress.
- Capture a sanitized or synthetic database fixture representing all source domains.
- Capture current dashboard API outputs with cache bypass where supported.
- Identify frontend-only calculations that must move into backend services.

Deliverables:

- Approved metric register.
- Dashboard endpoint-to-metric map.
- Frozen cross-domain test fixture.
- Baseline API response snapshots.
- Explicit decision register.

Exit criteria:

- Every in-scope metric has a named dashboard authority.
- Units, rounding, filters, and scope are documented.
- The missing-P6 dashboard fallback is isolated from canonical schedule facts.

### Phase 1: Parity Test Harness

Objective: create tests that detect changes before shared services are introduced.

Work:

- Add dashboard contract tests for current endpoint fields and null behavior.
- Add a dashboard-chat parity test framework.
- Compare structured facts rather than generated chatbot prose.
- Freeze time in tests involving delays, aging, forecasts, or fiscal periods.
- Add exact comparison for counts, identifiers, statuses, and dates.
- Add documented tolerance only where dashboard rounding requires it.
- Add unit and variance-sign assertions.

Initial parity matrix:

| Dashboard fact | Chatbot fact |
|---|---|
| Total projects | Portfolio project-list total |
| Project progress | P6 project summary progress |
| Delayed/on-track status | Schedule status result |
| PO quantity and value | SAP PO summary |
| Inventory and in-transit quantity | SAP inventory/logistics summary |
| TC lines and statuses | TC project lines |
| COD and Trial Run MW | Capacity status tool |
| Open NC/RFI counts | Quality project summary tool |
| Risk score | Corresponding named dashboard risk metric |
| Data cutoff and sync time | Tool evidence metadata |

Deliverables:

- `backend/tests/test_dashboard_contract.py`
- `backend/tests/test_dashboard_chat_parity.py`
- Shared test fixture builders.
- Baseline mismatch report.

Exit criteria:

- Tests reproduce known current differences.
- Existing dashboard behavior is protected before extraction.

### Phase 2: Project Catalog and Scope Foundation

Objective: make all domains select the same projects.

Work:

- Extract non-demo project population logic from dashboard and chatbot paths.
- Centralize portfolio normalization and filtering.
- Centralize mapping identifiers for P6, SAP, TC, Pulse, and capacity data.
- Implement deterministic project resolution and explicit ambiguity results.
- Preserve current role and project-scope authorization checks.
- Migrate portfolio counts and project lists first.

Affected areas:

- `backend/routers/dashboard.py`
- `backend/routers/projects.py`
- `backend/routers/pmag.py`
- `backend/engine/tools/portfolio_tools.py`
- `backend/engine/tools/p6_tools.py`
- Report project resolution.

Deliverables:

- Shared project catalog/scope service.
- Dashboard and chatbot adapters using the service.
- Project count, filtering, and resolution parity tests.

Exit criteria:

- The same scope returns the same project IDs in every consumer.
- Demo exclusion and portfolio filtering are consistent.
- Ambiguous names do not silently select an arbitrary project.

### Phase 3: Schedule and Progress Alignment

Objective: share the dashboard's approved P6 calculations.

Work:

- Extract progress normalization and calculation.
- Extract schedule dates, variance, delay, and activity counts.
- Standardize variance and duration units.
- Preserve dashboard progress and delay behavior approved in this plan.
- Keep different progress concepts explicitly named when the dashboard exposes more than one.
- Preserve native versus calculated SPI/CPI as separately named facts if both are needed.
- Add missing-P6 availability metadata while preserving the approved dashboard compatibility fallback.
- Migrate Overview, Project 360, PMAG, chatbot P6 tools, and report schedule facts.

Deliverables:

- Shared schedule metrics service.
- P6 DTOs with units and freshness.
- Progress, variance, delay, and activity parity tests.

Exit criteria:

- Dashboard and chatbot return the same approved progress for the same project.
- Delay status and variance sign match.
- Missing P6 values are not fabricated by the shared service.

### Phase 4: SAP, Procurement, and Logistics Alignment

Objective: make all consumers use the same SAP project population and aggregates.

Work:

- Extract the dashboard's approved WBS hierarchy and plant fallback behavior.
- Centralize PO, delivered, pending, inventory, in-transit, and consumption calculations.
- Preserve the current dashboard interpretation of PO value and material availability.
- Distinguish PO row count from distinct PO count.
- Normalize movement-type handling and material units where the source permits it.
- Migrate Overview, Project 360, financials, logistics, chatbot SAP tools, reports, and chart builders.

Deliverables:

- Shared SAP project data service.
- SAP DTOs with currency, quantity units, scope, and freshness.
- PO, inventory, logistics, consumption, and vendor parity tests.

Exit criteria:

- Dashboard and chatbot select the same SAP records for a project.
- Aggregates match within documented rounding.
- Currency and quantity units are explicit.

### Phase 5: Transmission Alignment

Objective: make dashboard and chatbot transmission answers use the same line snapshot and association rules.

Work:

- Centralize latest-record selection and deduplication.
- Centralize direct mapping plus approved phase/KPS association.
- Normalize status, progress, region, and date parsing.
- Preserve the approved dashboard project-association behavior.
- Migrate Overview, Project 360, TC routes, chatbot TC tools, risk inputs, and reports.

Deliverables:

- Shared transmission service.
- TC DTOs with snapshot and freshness metadata.
- Project-line, network-summary, delayed-line, and region parity tests.

Exit criteria:

- The same project returns the same TC line IDs and statuses everywhere.
- Historical duplicates do not inflate counts.
- Region and date handling are consistent.

### Phase 6: Capacity and Quality Alignment

Objective: expose dashboard capacity and quality facts to the chatbot through shared services.

Capacity work:

- Extract dashboard block/WTG identification.
- Extract total capacity, COD, Trial Run, remaining capacity, and trend calculations.
- Preserve COD precedence and current dashboard allocation behavior.
- Centralize wind MW-per-WTG and solar block rules currently embedded in code.
- Migrate Capacity Overview, Project 360, reports, and new chatbot capacity tools.

Quality work:

- Centralize Pulse-to-project association.
- Extract NC/RFI totals, closure, aging, trends, and contractor metrics.
- Apply canonical project and portfolio scope.
- Migrate quality routes, dashboard summary quality facts, reports, and new chatbot quality tools.

Deliverables:

- Shared capacity milestone service.
- Shared quality analytics service.
- Chatbot capacity and quality tools.
- Capacity and quality parity tests.

Exit criteria:

- Chatbot COD, Trial Run, and quality answers match the corresponding dashboard view.
- Quality queries use the same project identity as other domains.

### Phase 7: Risk Alignment

Objective: make chatbot risk answers use the same calculation as the relevant dashboard risk view.

The dashboard contains multiple risk-like concepts. They must remain explicitly named rather than merged into one ambiguous score:

- Portfolio Risk Command Center score.
- Project 360 risk flags or health classification.
- PMAG schedule RAG.
- Predictive or forecast indicators.

Work:

- Move frontend-only risk calculations into the backend without changing approved results.
- Give each risk metric a unique identifier and formula version.
- Build risk calculations from shared schedule, SAP, TC, capacity, and quality services.
- Route chatbot questions to the matching named risk metric.
- Prevent the LLM from combining different risk metrics into a new unsupported score.
- Keep predictive or heuristic values clearly labelled as such.

Deliverables:

- Shared risk analytics service.
- Backend endpoint support for currently frontend-only risk values.
- Chatbot risk tools using named dashboard metrics.
- Risk formula and parity tests.

Exit criteria:

- A risk answer identifies which dashboard risk metric it represents.
- The numeric value and classification match that dashboard metric.
- No unsupported composite score is generated by the LLM.

### Phase 8: Dashboard, Chatbot, Report, and Chart Adapters

Objective: complete migration so all operational consumers use shared services.

Work:

- Keep existing dashboard URLs and response fields stable.
- Add evidence and freshness fields additively.
- Convert chatbot tools into thin authenticated adapters.
- Update tool descriptions to state authoritative metric semantics.
- Update report dataset builders to use shared services.
- Update chart builders to consume service DTOs instead of independently querying tables.
- Remove duplicated calculations only after parity tests pass.
- Remove inactive duplicate service profiles after confirming they have no runtime consumers.

Deliverables:

- Thin dashboard route adapters.
- Thin chatbot tool adapters.
- Shared report and chart inputs.
- Inventory of safely removed duplicate logic.

Exit criteria:

- In-scope routes and tools no longer maintain separate business formulas.
- Existing frontend behavior remains compatible.
- Reports and charts agree with dashboard and chatbot facts.

### Phase 9: Freshness, Cache, and Provenance Alignment

Objective: ensure dashboard and chatbot compare the same data version.

Work:

- Define `data_as_of`, `last_synced_at`, and `answer_generated_at` consistently.
- Return per-source freshness rather than one ambiguous timestamp.
- Invalidate dependent caches only after successful sync completion.
- Replace or version process-local caches where multi-worker consistency is required.
- Persist actual source systems/tables and timestamps in chat metadata.
- Display freshness and warnings in chatbot responses where appropriate.
- Add stale-data thresholds by source system after business approval.

Deliverables:

- Shared freshness service and evidence envelope.
- Sync-to-cache invalidation hooks.
- Chat response provenance persistence.
- Freshness and cache-coherency tests.

Exit criteria:

- Dashboard and chatbot do not differ because one is using stale process cache data.
- Every source-backed chatbot answer carries usable provenance.

### Phase 10: Evaluation and Controlled Rollout

Objective: prove alignment before enabling the refactor for all users.

Work:

- Select at least 20 high-value questions from operational usage and `Qns_AKASHA.xlsx`.
- Store expected structured facts, not only expected prose.
- Include total, project progress, delay, SAP, TC, capacity, quality, risk, stale data, missing data, and ambiguous project cases.
- Run shadow comparisons against the existing implementation.
- Roll out by controlled cohort.
- Monitor mismatch, unsupported-claim, tool-error, latency, and user-feedback rates.
- Retain a deployment rollback path for each migrated domain.

Deliverables:

- Business-reviewable golden question set.
- Automated parity report.
- Rollout dashboard and release checklist.
- Rollback procedure.

Exit criteria:

- Deterministic dashboard-chat metric mismatch rate is zero for approved test cases.
- No material numeric or date claim is unsupported by tool evidence.
- Project resolution is correct for all approved cases.
- Missing and stale data behavior follows approved policy.
- Business reviewers approve production rollout.

## 11. API Compatibility Strategy

The refactor is internal-first.

Existing endpoints remain in place, including:

- `/api/dashboard/summary`
- `/api/project-360`
- `/api/project-360/{project_id}/detail`
- `/api/summary`
- `/api/financials`
- `/api/logistics`
- `/api/dashboard/capacity-overview`
- `/api/quality/*`

Compatibility rules:

- Preserve existing fields and types during initial service extraction.
- Add metadata fields without removing current fields.
- Use compatibility serializers where internal DTOs are richer than current API responses.
- Change an existing field's meaning only after explicit business approval.
- Update the frontend and contract tests in the same change when a semantic correction is approved.
- Version an API only if a necessary breaking change cannot be represented safely through additive fields.

## 12. Verification Strategy

### Contract Tests

- Validate endpoint status, schema, units, null behavior, and rounding.
- Validate strict chatbot tool envelopes.
- Validate source and freshness metadata.
- Validate API compatibility for existing frontend consumers.

### Parity Tests

- Use one transaction and one frozen clock.
- Call the dashboard service/API with cache bypass.
- Call the corresponding chatbot tool.
- Compare canonical structured facts.
- Do not use LLM prose as the source of truth.

### Golden Questions

Each case should record:

- User question.
- User role and selected scope.
- Expected project resolution.
- Expected tool or authoritative service.
- Expected structured facts.
- Units and rounding tolerance.
- Expected source systems and timestamps.
- Required missing/stale-data warning.
- Business validation status.

### Runtime Safeguards

- Operational claims require tools.
- Numeric and date claims must be traceable to tool output.
- The chatbot must not calculate an unapproved replacement metric.
- Large collections must use explicit pagination or bounded summaries.
- Tool errors and unavailable data must not be rewritten as successful values.

## 13. Success Metrics

Release-blocking metrics:

- Dashboard-chat deterministic mismatch rate.
- Project-resolution correctness.
- Numeric/date exactness within approved tolerance.
- Unit and variance-sign correctness.
- Unsupported material claim rate.
- Evidence coverage rate.
- Missing/stale-data handling correctness.

Operational metrics:

- Tool error and no-data rate.
- Source synchronization lag.
- Post-sync cache mismatch rate.
- Chat response latency.
- User feedback by issue category.
- Mismatch rate by domain, metric version, and source system.

## 14. Principal Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Extraction changes a dashboard value | Characterization tests and old-versus-new parity before migration. |
| Existing API consumers break | Preserve contracts and use compatibility serializers. |
| A dashboard metric has multiple meanings | Assign explicit metric IDs and keep concepts separate. |
| Source data is wrong or incomplete | Return provenance and warnings; do not repair source data silently. |
| Missing-P6 schedule-status decision blocks unrelated work | Apply the confirmed partial-source policy and defer only affected schedule display behavior. |
| Dashboard cache and chatbot live query disagree | Shared freshness and sync-triggered cache invalidation. |
| LLM changes a correct value | Evidence-bound answer validation and deterministic tools. |
| Refactor is too large to verify | Migrate one domain at a time with independent rollback. |
| Frontend-only calculation cannot be shared | Move it unchanged to a backend service, then update the frontend adapter. |

## 15. Recommended Execution Order

The recommended order is:

1. Baseline and metric register.
2. Parity test harness.
3. Project catalog and scope.
4. Schedule and progress.
5. SAP, procurement, and logistics.
6. Transmission.
7. Capacity and quality.
8. Risk.
9. Remaining adapters, reports, and charts.
10. Freshness and cache alignment.
11. Evaluation and controlled rollout.

This order addresses shared identity first, then the highest-use operational domains, and leaves cross-domain risk until its inputs are authoritative.

## 16. Definition of Done

The refactor is complete when:

- Dashboard and chatbot use the same project population and scope rules.
- Equivalent questions return identical structured facts from the same database snapshot.
- Dashboard routes and chatbot tools call shared authoritative services.
- Existing dashboard APIs remain compatible unless a separately approved correction requires a coordinated change.
- Progress, delay, SAP, TC, capacity, quality, and risk semantics are documented and versioned.
- Missing values are not silently converted into healthy or zero values.
- Per-source freshness and provenance are available to both surfaces.
- Successful source synchronization invalidates dependent caches.
- Reports and charts use the same authoritative facts.
- Parity, contract, and golden-question suites pass.
- Business reviewers approve production rollout.

## 17. Review Checklist

Before implementation begins, reviewers should confirm:

- The dashboard remains the initial behavioral baseline.
- The confirmed decisions in Section 4 are accurate.
- Missing-P6 schedule-status fallback and partial-source availability are confirmed.
- Risk metrics should preserve the corresponding dashboard calculation and remain separately named.
- Existing API compatibility is required.
- The proposed phase order is acceptable.
- The initial 20 golden questions and business reviewers can be identified during Phase 0.

## 18. Implementation Progress

Status date: 31 July 2026.

### Phase 0: Foundation Baseline Completed

Delivered:

- `DASHBOARD_CHATBOT_METRIC_REGISTER.md` with approved decisions, metric authorities, formulas, filters, units, freshness, counterparts, and parity state.
- `DASHBOARD_ENDPOINT_METRIC_MAP.md` with dashboard endpoint and frontend-derived metric ownership.
- `DASHBOARD_CHATBOT_BASELINE_MANIFEST.md` with fixture identity, safety, snapshot, and change-control rules.
- `backend/tests/fixtures/dashboard_alignment/catalog_baseline.v1.json`, a checked-in synthetic project-catalog baseline with expected canonical facts.
- Explicit isolation of the approved missing-P6 dashboard fallback from canonical schedule facts.

Phase 0 scope note:

- The cross-domain metric and endpoint inventory is complete. The executable fixture currently covers project population and scope; response snapshots and rows for schedule, SAP, TC, capacity, quality, risk, and freshness are intentionally added when those domain services are characterized in their respective phases.

### Phase 1: Completed For The Project-Catalog Slice

Delivered:

- `backend/tests/dashboard_fixtures.py` with selected-table SQLite setup, deterministic fixture loading, dashboard cache isolation, and capacity isolation for project-population contracts.
- `backend/tests/test_dashboard_contract.py` covering mapping authority, demo exclusion, mapping-only inclusion, unmapped-P6 exclusion, portfolio tokenization, and the all-portfolios sentinel.
- `backend/tests/test_dashboard_chat_parity.py` covering unfiltered and filtered dashboard/chat population parity plus P6 availability.
- `backend/tests/test_project_catalog.py` covering catalog identity, duplicate mapping records, null IDs, demo preference, deterministic resolution, ambiguity, portfolio scope, and graph authorization compatibility.

Phase 1 scope note:

- The parity harness is established and executable. Metric-specific parity cases will be added as each later domain service is extracted.

### Phase 2: Completed

Delivered:

- `backend/services/project_catalog_service.py` as the authoritative non-demo mapping population and deterministic identity resolver.
- Dashboard-compatible tokenized portfolio filtering, including `+` normalization.
- Mapping-record population semantics without deduplicating portfolio counts by P6 ID.
- Explicit ambiguous-resolution results rather than arbitrary first-row selection.
- HTTP 409 responses for ambiguous single-project dashboard filters instead of silent multi-project aggregation.
- Selected-project authorization filtering for ambiguous chatbot candidates, preventing cross-scope metadata disclosure.
- Clarification context for ambiguous legacy-chat requests instead of portfolio fallback.
- Separate graph existence validation preserving mapped and unmapped-P6 compatibility without weakening selected-project scope.
- Optional shared portfolio filtering for `p6_list_all_projects`.

Migrated consumers:

- Dashboard Summary.
- Dashboard Knowledge Graph project population.
- Capacity Overview project population.
- Project 360 project population.
- PMAG project population.
- Master project list and P6 summary scope/resolution.
- Financial and logistics project/portfolio scope selection, without changing their SAP formulas.
- Chatbot portfolio project list and project resolver.
- P6 portfolio list.
- Legacy portfolio facts and project context resolution.
- Portfolio KPI project population.
- Variance project resolution.
- LangGraph project existence validation.

Intentionally deferred to later phases:

- P6 schedule formulas and missing-P6 schedule display semantics.
- SAP WBS aggregation and fallback calculations.
- Transmission association and latest-record rules.
- Capacity milestone formulas.
- Pulse quality association.
- Risk calculations.
- Unified freshness and cache invalidation.

### Phase 3: Completed

Delivered:

- `backend/services/schedule_metrics_service.py` with typed immutable schedule facts, approved units/construction/duration progress precedence, dashboard delay semantics, activity counts, native SPI/CPI, units, and P6 freshness.
- Explicit nullable `p6_available` facts for mapping-only projects; dashboard compatibility preserves the approved `On Track` and progress `0` fallback.
- Overview, Project 360 summary/detail, PMAG, P6 chatbot summaries/lists, project summary/detail APIs, and report inputs now consume the shared schedule calculation.
- Native and calculated SPI/CPI remain separately named where both surfaces need them.
- `backend/tests/test_schedule_metrics_service.py` and dashboard-chat schedule parity coverage.

### Phase 4: Completed

Delivered:

- `backend/services/sap_project_data_service.py` with bounded WBS hierarchy matching, no unsafe substring matching, SPV/AGEL plant fallback for mappings without WBS, and capacity-share allocation.
- Shared PO, delivered, pending, inventory, consumption, value, vendor, row-count, distinct-PO-count, unit-warning, and per-table freshness facts.
- Movement types 222 and 262 are consistently treated as reversals.
- Overview, Project 360 summary/detail, financials, logistics, chatbot SAP tools, report inputs, chart-tool inputs, and portfolio KPI inputs now use shared SAP selection.
- Existing response fields remain available; additive raw quantities, scope, units, warnings, freshness, and distinct counts support exact parity and evidence.
- `backend/tests/test_sap_project_data_service.py` and dashboard-chat SAP parity coverage.

### Phase 5: Completed

Delivered:

- `backend/services/transmission_service.py` with deterministic latest snapshots, normalized region identity, direct plus phase/KPS association, physical-line deduplication, status/progress/date normalization, and freshness.
- Mapping-specific latest selection preserves one physical line's association with multiple projects before project-level physical deduplication.
- Overview, Project 360 summary/detail, TC routes, chatbot TC tools, portfolio risk inputs, variance inputs, report inputs, and chart-tool inputs now consume the shared transmission snapshot.
- TC synchronization refreshes one consistent upload timestamp for inserted and updated records in each regional synchronization run.
- `backend/tests/test_transmission_service.py` and dashboard-chat transmission parity coverage.

### Phase 6: Completed

Delivered:

- `backend/services/capacity_milestone_service.py` as the authoritative Capacity Overview calculation, with immutable source facts, normalized block/WTG identity, Solar and Wind allocation rules, COD-over-Trial-Run precedence, independent event trends, FY boundaries, freshness, warnings, and mapping-only availability.
- `backend/services/quality_analytics_service.py` as the authoritative Pulse quality layer for portfolio/project NC and RFI facts, closure, aging, trends, contractor scores, project scores, deterministic catalog association, ambiguity handling, and provenance.
- Capacity Overview, Dashboard Summary, Knowledge Graph inputs, Project 360 summary/detail, legacy chatbot context, quality routes, Project Workspace quality inputs, reports, and PDF/DOCX report sections now consume shared capacity or quality facts.
- Registered authenticated chatbot tools for portfolio/project capacity, portfolio/project quality, and contractor quality scorecards.
- Successful Pulse synchronization now clears dependent dashboard caches.
- `backend/tests/test_capacity_milestone_service.py`, `backend/tests/test_quality_analytics_service.py`, `backend/tests/test_quality_routes.py`, and Phase 6 route/chat parity coverage.

### Phase 7: Completed

Delivered:

- `backend/services/risk_analytics_service.py` with immutable named metric envelopes containing metric ID, formula version, scope, value, unit, classification, components, evidence, availability, heuristic status, and warnings.
- Separate preserved metrics for PMAG schedule RAG, Portfolio Risk Command Center counts/score/heatmap, Project 360 flags/COD risk/status tier, predictive portfolio slippage, and KPI project exposure.
- Shared Project 360 risk-input construction now supplies both dashboard and chatbot metrics; distinct risk concepts are not merged.
- Added `/api/risk/command-center`, `/api/risk/predictive`, and `/api/risk/project/{project_id}` adapters and migrated the Risk Command Center, Predictive Analytics, and PMAG RAG consumers.
- Registered the strict `risk_get_metric` chatbot tool with an enumerated metric ID and conditional project-scope validation.
- Selected-project scope is preserved by risk frontend requests and both legacy and LangGraph tool authorization paths; project quality outputs redact unrelated catalog candidates.
- Reports now include authoritative capacity facts and explicitly named risk metrics.
- `backend/tests/test_risk_analytics_service.py` and Phase 7 route/chat/Project 360 parity coverage.

### Phase 3-5 Review Corrections

- Restored dashboard baseline-over-scheduled delay precedence and PMAG's distinct duration-progress concept.
- Corrected legacy variance-unit compatibility, SAP source-specific fallback/allocation, duplicate mapping handling, null-ID mapping support, TC negative-status normalization, and remaining raw TC route consumers.
- Removed the transmission-to-Project360 dependency inversion and added reusable bulk SAP/TC snapshots for portfolio consumers.
- Added regressions for bounded WBS selection, mixed SPV/AGEL coverage, duplicate mappings, null project IDs, latest TC records, PMAG grey status, and report/chart compatibility.

### Verification Evidence

- 52 focused catalog, dashboard contract, parity, P6, routing, ambiguity, and authorization tests pass.
- 250 complete backend tests pass.
- Focused service, route, authorization, report, and dashboard-chat parity suites pass for Phases 3-7.
- Scoped Python compilation passes for all modified backend modules.
- Frontend TypeScript compilation and production build pass.
- Live database verification returns 63 dashboard projects and 63 chatbot projects with identical dashboard project-name sets; 55 have P6 data and 8 do not.
- `git diff --check` passes with line-ending warnings only.

### Phase 8: Completed

Delivered:

- Dashboard, chatbot, Project 360, report, and chart consumers use the shared domain services through compatibility adapters while preserving existing URLs and fields.
- `backend/services/chart_spec_service.py` provides authoritative chart inputs; chart builders no longer query raw P6 rows or calculate an alternate portfolio risk score.
- Project progress reports now compose project catalog, schedule, SAP, transmission, capacity, quality, and named risk DTOs directly, including mapping-only projects.
- SAP PO fulfillment charts now consume the authoritative allocated PO quantities.
- Inactive `project_service_profile.py` and `project_service_profile2.py` duplicates were removed after confirming they had no runtime consumers.

### Phase 9: Completed

Delivered:

- `backend/services/freshness_service.py` defines immutable source freshness/evidence semantics and conservative multi-source answer provenance.
- `backend/migrations/phase9_source_sync_state.sql` creates the durable cache-version table before Phase 9 code is deployed.
- Durable `SourceSyncState` versions make dashboard, project, financial, logistics, and chatbot metric caches reject stale entries across workers.
- Successful P6, SAP, TC, Pulse, mapping, and capacity synchronization advances the relevant source version and invalidates dependent caches; failed synchronization does not.
- Completed chat responses persist tools, source systems, source tables, `data_as_of`, `last_synced_at`, and `answer_generated_at` additively in provenance metadata.
- SSE responses and reloaded chat sessions expose the same per-source freshness envelope.

### Phase 10: Evaluation And Rollout Foundation Completed

Delivered:

- `backend/evaluation/golden_cases.v1.json` contains 23 high-value structured questions spanning scope, progress, delay, SAP, TC, capacity, quality, named risk, stale data, missing data, ambiguity, and unsupported sources.
- Expected values are synthetic and explicitly pending business validation; workbook wording is used only as question provenance and workbook answers are not treated as truth.
- The typed evaluator compares resolution, values, units, tolerances, nulls, source evidence, warning policy, and unsupported claims, and emits JSON plus Markdown reports.
- The sample evaluation passes 23/23 cases and 240/240 structured checks with zero unsupported facts.
- `backend/services/alignment_rollout_service.py` provides deterministic server-owned shadow/canary/aligned cohorts and domain kill switches.
- `backend/evaluation/ROLLOUT.md` records release gates, monitoring measures, staged cohorts, and rollback steps.

Phase 10 approval note:

- The synthetic suite proves evaluator and policy behavior, not production answer accuracy. Production rollout still requires business owners to validate expected facts against an approved frozen source snapshot and approve the cohort promotion.

Latest verification:

- 266 complete backend tests pass.
- The 23-case Phase 10 golden sample passes all 240 structured checks.
- Frontend TypeScript compilation and production build pass.
- Scoped Python compilation and `git diff --check` pass; only repository line-ending warnings remain.

### Phase 11: Workbook Question Coverage In Progress

Initial delivery:

- Audited all 132 non-empty question rows in `Qns_AKASHA.xlsx` and recorded live-source coverage in `CHATBOT_QUESTION_COVERAGE_AND_VERIFIED_ANSWERS.md`.
- Added rolling `last_n_days` block rankings with explicit highest/lowest ties.
- Added a daily activity-completion trend tool anchored to P6 `data_date`; it explicitly prevents activity events from being presented as unavailable historical duration-percent snapshots.
- Added deterministic transmission readiness status and readiness percentage to the canonical transmission result.
- Extended deterministic tool routing for rolling block periods, daily trends, transmission readiness, and evacuation-readiness wording.
- Added focused service and routing tests for the new capabilities.

Phase 11 source constraint:

- True DPR/P6 daily percentage history, DPR issues, daily manpower/machinery deployment, financial approvals/payments/cash flow, land/GIS, and weather calculations remain blocked until authoritative sources are ingested. These question families must return explicit structured missing-data results rather than inferred substitutes.
