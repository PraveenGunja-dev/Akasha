# Phase 10 Golden Evaluation Report

> Synthetic expected facts. Pending business validation. This is not a production accuracy claim.

- Dataset: `phase10-golden-v1` (schema `2.0`)
- Result: **PASS**
- Cases: 23/23 passed (100.0%)
- Structured checks: 240/240 (100.0%)
- Unsupported claims: 0
- Missing responses: 0

## Quality Gates

| Gate | Actual | Threshold | Result |
|---|---:|---:|---|
| `minimum_overall_score` | 1.0 | 1.0 | PASS |
| `minimum_case_pass_rate` | 1.0 | 1.0 | PASS |
| `maximum_unsupported_claims` | 0 | 0 | PASS |
| `require_response_for_every_case` | True | True | PASS |

## Cases

| Case | Category | Checks | Score | Result |
|---|---|---:|---:|---|
| `total-project-count-001` | total_scope | 8/8 | 100.0% | PASS |
| `total-portfolio-progress-001` | total_scope | 8/8 | 100.0% | PASS |
| `project-current-progress-001` | project_progress | 12/12 | 100.0% | PASS |
| `project-plan-variance-001` | project_progress | 16/16 | 100.0% | PASS |
| `delay-completion-baseline-001` | delay | 16/16 | 100.0% | PASS |
| `delay-portfolio-projects-001` | delay | 12/12 | 100.0% | PASS |
| `sap-capex-utilization-001` | sap | 12/12 | 100.0% | PASS |
| `sap-delayed-pos-001` | sap | 8/8 | 100.0% | PASS |
| `sap-material-availability-001` | sap | 8/8 | 100.0% | PASS |
| `tc-readiness-001` | tc | 12/12 | 100.0% | PASS |
| `tc-connectivity-alignment-001` | tc | 12/12 | 100.0% | PASS |
| `capacity-portfolio-001` | capacity | 12/12 | 100.0% | PASS |
| `capacity-project-remaining-001` | capacity | 8/8 | 100.0% | PASS |
| `quality-open-ncr-001` | quality | 8/8 | 100.0% | PASS |
| `quality-contractor-rate-001` | quality | 8/8 | 100.0% | PASS |
| `risk-named-001` | named_risk | 16/16 | 100.0% | PASS |
| `risk-project-current-001` | named_risk | 8/8 | 100.0% | PASS |
| `freshness-stale-progress-001` | stale_data | 12/12 | 100.0% | PASS |
| `missing-capex-data-001` | missing_data | 8/8 | 100.0% | PASS |
| `missing-forecast-date-001` | missing_data | 8/8 | 100.0% | PASS |
| `ambiguous-project-name-001` | ambiguity | 8/8 | 100.0% | PASS |
| `unsupported-machinery-source-001` | unsupported_source | 8/8 | 100.0% | PASS |
| `project-comparison-scope-001` | project_scope | 12/12 | 100.0% | PASS |
