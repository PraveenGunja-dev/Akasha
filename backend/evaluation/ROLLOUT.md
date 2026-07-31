# Phase 10 Controlled Rollout

Runtime controls are server-owned and evaluated by
`services.alignment_rollout_service.select_alignment_cohort`:

- `AKASHA_ALIGNMENT_MODE=legacy|shadow|canary|aligned`
- `AKASHA_ALIGNMENT_ROLLOUT_PERCENT=0..100`
- `AKASHA_ALIGNMENT_DOMAINS=schedule,sap,tc,capacity,quality,risk`

The default is `aligned` because the shared services are the current application
path. Set `legacy` as the immediate alignment kill switch where a retained
compatibility adapter exists. Domain omission is the per-domain kill switch.

## Release Checklist

- Freeze and identify the source snapshot used to create expected facts.
- Obtain named business-owner approval for every case promoted to `business_validated`.
- Run unit tests and archive both generated report formats as release evidence.
- Require 100% project-resolution accuracy for approved cases.
- Require zero unsupported claims and zero deterministic metric mismatches.
- Confirm stale, missing, ambiguous, and unsupported-source policies with owners.
- Shadow the candidate implementation against the current implementation before user exposure.
- Record candidate version, prompt version, tool versions, dataset version, and release owner.

## Cohorts

1. Internal engineering shadow traffic with no user-visible candidate response.
2. Named business reviewers with candidate results visible beside the current result.
3. Small opt-in operational cohort after business approval.
4. Incremental domain enablement: progress/delay, SAP, TC, capacity, quality, then risk.
5. General availability only after all release gates remain healthy for the agreed observation window.

Synthetic cases may test evaluator behavior but cannot authorize a production
cohort. Promotion requires a new, reviewed dataset version.

## Monitoring

Track by domain and cohort:

- Structured fact mismatch rate and project-resolution mismatch rate.
- Unsupported-claim and missing-evidence rates.
- Stale-data warning, missing-data abstention, and ambiguity clarification rates.
- Tool error and timeout rates.
- P50, P95, and P99 latency.
- User feedback, including wrong number, wrong project, stale, and unsupported claim.

Alert on any unsupported material claim, any approved-case resolution mismatch,
or a sustained regression beyond the release thresholds. Preserve case IDs and
source IDs in evidence without storing response prose in evaluation reports.

## Rollback

1. Disable the candidate cohort or affected domain feature flag; do not alter Phase 8 reports/charts or Phase 9 freshness behavior.
2. Route traffic to the last approved implementation and verify the active version.
3. Stop cohort expansion and preserve failing reports, run IDs, tool evidence, and metrics.
4. Classify the failure as resolution, value/unit, source, warning policy, tool error, or latency.
5. Correct the implementation or create a newly reviewed dataset version; never weaken a gate to make a release pass.
6. Re-run shadow evaluation and obtain renewed approval before re-enabling the domain.

Rollback is domain-scoped where possible. If resolution or shared evidence is
affected, roll back the entire candidate implementation.
