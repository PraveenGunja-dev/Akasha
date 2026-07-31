# Dashboard and Chatbot Baseline Manifest

This Phase 0 manifest defines how a frozen cross-domain fixture and response snapshot set is identified. This document contains no credentials, access tokens, production URLs, or production-derived values. Synthetic fixture rows are stored separately under `backend/tests/fixtures/dashboard_alignment/`.

## Implemented Phase 0 Baseline

The first checked-in baseline covers the authoritative project-catalog and portfolio-count slice:

| Field | Value |
|---|---|
| Baseline ID | `alignment-project-catalog-v1` |
| Fixture kind | Fully synthetic |
| Fixture path | `backend/tests/fixtures/dashboard_alignment/catalog_baseline.v1.json` |
| Fixture SHA-256 | `a266f9b1f6a5b6b0514226a2e292655ce9cf9c7c5f917ed41edfa2bab03471f8` |
| Frozen clock | `2026-07-15T12:00:00Z` |
| Test database | SQLite in-memory with selected production metadata tables |
| Cache policy | Dashboard caches cleared; summary invoked with `nocache=true` |
| Expected facts | Stored in the fixture's `expected` object |
| Runtime consumers | `test_dashboard_contract.py`, `test_dashboard_chat_parity.py`, `test_project_catalog.py` |
| Review status | Implementation baseline; business review pending |

This initial fixture intentionally covers project population, demo exclusion, mapping-only inclusion, unmapped-P6 exclusion, P6 availability, and portfolio filtering. Later domain phases extend the fixture rather than replacing this baseline in place.

## Baseline Identity

Each frozen baseline gets one immutable ID:

```text
alignment-baseline-<YYYYMMDD>-<short-git-sha>-v<sequence>
```

Example shape only: `alignment-baseline-YYYYMMDD-abcdef1-v1`.

The checked-in manifest accompanying a future sanitized/synthetic fixture should contain:

```yaml
manifest_version: 1
baseline_id: alignment-baseline-YYYYMMDD-abcdef1-v1
repository_commit: <full-git-sha>
fixture_kind: synthetic  # or sanitized; synthetic is preferred
fixture_schema_version: <explicit-version>
fixture_archive: <relative-path>
fixture_sha256: <sha256>
snapshot_archive: <relative-path>
snapshot_sha256: <sha256>
clock_utc: <frozen-ISO-8601-timestamp>
timezone: UTC
database_engine: <name-and-major-version>
cache_policy: bypassed
generator_version: <script-or-procedure-version>
review_status: pending
approved_by_role: <role-not-person>
```

The `baseline_id` plus both SHA-256 values uniquely identifies the database state and expected API outputs. A changed fixture or snapshot requires a new baseline ID; do not overwrite an approved baseline in place.

## Required Synthetic Coverage

Use invented identifiers, names, vendors, values, and dates. Include the smallest deterministic set that exercises:

| Domain | Required cases | Tables represented |
|---|---|---|
| Project catalog | Non-demo mapped Solar and Wind projects; portfolio/category/cluster filters; one demo excluded; duplicate/ambiguous display names; mapping with no P6 | `project_mapping` |
| P6 schedule | Unit-based progress branch; construction-percent fallback; duration-percent fallback; delayed by negative variance; delayed by baseline/scheduled date; on-track; null fields; activity statuses and critical float | `p6_project`, `p6_activity`, `p6_wbs_node`; baseline/resource tables only if an endpoint uses them |
| SAP | Exact WBS, bounded child WBS, misleading raw-prefix WBS, no-WBS plant fallback, shared plant allocation, PO ordered/delivered/pending/value, positive inventory, movement type 222 return, mixed units/currency where supported | `mt_poamount`, `mt_inventory`, `mt_materialdocument`, `mt_requirement` |
| Transmission | Khavda and Rajasthan; direct mapping; phase/KPS association; duplicate historical `(region, edge_id)` rows; same-timestamp tie; completed/in-progress/not-started/unknown; delayed and non-delayed | `tc_project_entry`, `tc_network_edge`, `tc_network_node` |
| Capacity | Solar blocks and Wind WTGs; project-specific/default MW per WTG; Trial Run only; COD only; both on one block to prove COD precedence; incomplete/undated milestone; unmatched P6 mapping | `project_mapping`, `p6_project`, `p6_activity` |
| Quality | Open/completed/rejected and Critical NCs; RFI complete/open; project/SPV association; contractor scores; resolution dates; aging bucket boundaries; debit and null debit | `pulse_nc`, `pulse_rfi` |
| Risk | Enough P6 variance and PO MW rows to exercise frontend thresholds; enough P6/SAP/TC rows to exercise chatbot exposure with all components and with one unavailable component | Inputs above; no fabricated risk table |
| Freshness | Distinct business cutoffs and ingestion timestamps by source, including a deliberately stale source | Source `data_date`, `last_synced_at`, and `upload_time` columns |

The missing-P6 fixture case must retain mapping and non-P6 domain records. Its shared-service P6-derived facts are expected to be unavailable. The dashboard compatibility snapshot preserves `On Track`, progress `0`, and inclusion in the on-track aggregate as approved `legacy_surface_behavior`; these values are not P6 evidence.

## Safety Rules

- Prefer fully synthetic data. Sanitization is acceptable only when re-identification risk has been reviewed.
- Never include database URLs, usernames, passwords, tokens, cookies, authorization headers, private keys, production hostnames, or environment-file contents.
- Never copy free-text production descriptions, person names, vendor names, project codes, document numbers, or exact commercially sensitive values. Replace them deterministically with invented values.
- Preserve relationships and edge cases, not production cardinality or distributions.
- Use fixed surrogate IDs and timestamps; do not rely on sequence state, current time, locale, or random generation without a committed seed.
- Run snapshots against an isolated disposable database. The fixture loader must refuse non-test database targets when implementation is added in a later phase.
- Store snapshots as canonical structured JSON, not screenshots and not chatbot prose.

## Snapshot Protocol

1. Check out the recorded commit and create an isolated test database with the recorded engine major version.
2. Load the fixture from an empty schema and verify its SHA-256 before use.
3. Set the recorded UTC clock for all delay, aging, forecast, fiscal-period, and PMAG calculations.
4. Disable authentication only in the isolated test harness or use a synthetic test identity. Do not persist authorization headers.
5. Clear process-local caches. Call cache-aware endpoints with `nocache=true`: `/api/dashboard/summary`, `/api/summary`, `/api/project-360`, `/api/financials`, `/api/financials/details`, `/api/logistics`, and `/api/logistics/details` where supported.
6. Invoke endpoints in a fixed order and one database transaction/snapshot where the stack permits it. Record request path and non-secret query parameters.
7. Invoke chatbot tool functions directly and capture structured return values. Do not call an LLM and do not snapshot generated prose.
8. Calculate registered frontend-only metrics with a deterministic extractor over the captured API JSON. Record the frontend source file and formula version.
9. Canonicalize JSON: UTF-8, sorted object keys, stable array ordering by documented identifiers, ISO-8601 UTC timestamps, and no transport headers. Do not reorder arrays whose order is part of the contract.
10. Compare a second clean run byte-for-byte. Investigate all drift before assigning checksums and approval status.

## Snapshot Index Shape

The future snapshot index should use one entry per request/tool invocation:

```yaml
- snapshot_id: dashboard-summary-all
  consumer: dashboard_api
  invocation: GET /api/dashboard/summary?nocache=true
  scope: all_portfolios
  output_file: responses/dashboard-summary-all.json
  sha256: <sha256>
  authoritative_metrics:
    - portfolio.project_count
    - schedule.overall_progress
    - schedule.overview_health
  source_tables:
    - project_mapping
    - p6_project
  cache_bypassed: true
  clock_utc: <same-frozen-timestamp>
  notes: no secrets or production data
```

Required index metadata per entry:

- Snapshot ID, consumer type, exact invocation, scope, output path, and SHA-256.
- Registered metric IDs and current authority function/file.
- Source tables and source-domain availability.
- Frozen clock, cache-bypass state, and deterministic ordering rule.
- Expected unit, rounding, null behavior, and tolerance. Tolerance defaults to exact unless the metric register explicitly documents dashboard rounding.
- `data_as_of` and `last_synced_at` when the current surface exposes them; otherwise an explicit `not_exposed` marker rather than an invented timestamp.
- Classification as `approved_baseline`, `known_mismatch`, `frontend_only`, or `legacy_surface_behavior`.

## Review and Change Control

- Approval confirms that the snapshot accurately captures registered current behavior; it does not certify source-data correctness.
- Known dashboard/chatbot differences remain two separately named snapshots until parity work changes them.
- Regeneration requires a new baseline ID, checksums, mismatch report, and reviewer sign-off by role.
- A formula, filter, source association, unit, rounding rule, clock, database engine, or fixture row change invalidates affected snapshots.
- The main alignment plan owns phase status. This manifest only identifies baseline artifacts and must not be used to mark a phase complete.
