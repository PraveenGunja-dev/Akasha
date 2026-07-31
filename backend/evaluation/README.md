# Phase 10 Golden Evaluation

This directory contains an isolated, deterministic alignment evaluation. It does
not import the application, query a database, or call a model provider.

## Truth Status

`golden_cases.v1.json` is **pending business validation**. Its question wording
is drawn where suitable from `Qns_AKASHA.xlsx` and operational edge cases. All
expected facts, project IDs, dates, amounts, and source IDs are synthetic. No
workbook answer or production value was imported. Results are regression and
contract evidence, not a production accuracy claim.

The historical `cases.v1.json` and `responses.v1.json` files retain the Phase 0
schema for traceability. The Phase 10 CLI intentionally rejects that schema.

## Contents

- `golden_cases.v1.json`: 23 versioned questions and structured expectations.
- `sample_responses.v1.json`: a complete synthetic response set exercising all cases.
- `evaluate.py`: typed, standard-library-only validator, evaluator, and reporter.
- `config.py`: schema and default path configuration.
- `reports/sample-report.v1.json`: machine-readable sample run.
- `reports/sample-report.v1.md`: business-reviewable sample run.
- `ROLLOUT.md`: release, monitoring, approval, and rollback controls.

The corpus covers portfolio totals, project scope and progress, schedule delay,
SAP, TC, capacity, quality, named risk, stale data, missing data, ambiguous
project resolution, and unsupported sources.

## Run

From the repository root:

```powershell
python backend/evaluation/evaluate.py
python -m unittest backend.tests.test_evaluation -v
```

The evaluator writes the default JSON and Markdown reports under `reports/`,
prints JSON to stdout and Markdown to stderr, and returns:

- `0`: all configured gates pass.
- `1`: valid inputs with at least one failed gate.
- `2`: invalid input.

Custom files and output locations:

```powershell
python backend/evaluation/evaluate.py `
  --cases path/to/cases.json `
  --responses path/to/responses.json `
  --json-report path/to/report.json `
  --markdown-report path/to/report.md
```

## Comparison Rules

Each expected fact is compared by value type, value, unit, and exact source-ID
set. Numeric and integer values use the case tolerance. Null is a typed value,
not zero or an omitted fact. Each case also compares exact project resolution,
top-level source IDs, and warning-code sets. Additional response facts are
reported as unsupported claims and fail the configured zero-unsupported gate.

Before replacing synthetic facts, a business reviewer must verify the source
snapshot, project scope, unit, null policy, tolerance, warning policy, and
expected value. Only then should a new dataset version use
`business_validated` at the case level and update the dataset truth policy.
