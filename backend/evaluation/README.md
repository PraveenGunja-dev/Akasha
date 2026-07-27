# Phase 0 Tests and Provisional Evaluation

This scaffold is isolated from the application entry point. It does not import
`backend/main.py`, connect to a database, or call an LLM/provider. It uses only
the Python standard library.

## Automated tests

From the repository root:

```powershell
python -m unittest discover -s backend/tests -v
```

The tests cover conservative request-ID acceptance and UUID fallback, correlated
single-frame SSE JSON, Phase 0 event shapes, payload-free operational logs,
import safety, versioned evaluation input validation, deterministic fact and
evidence scoring, status cohorts, and failing quality gates.

## Provisional baseline

Run the versioned baseline from the repository root:

```powershell
python backend/evaluation/evaluate.py
```

Human-readable output is written to stderr. Machine-readable JSON is written to
stdout. A passing run exits `0`, failed quality gates exit `1`, and invalid input
exits `2`. Custom versioned inputs can be selected with:

```powershell
python backend/evaluation/evaluate.py --cases path/to/cases.json --responses path/to/responses.json
```

Scoring is deliberately deterministic. An expected fact passes when its
normalized phrase occurs in the response. A grounded claim passes only when its
phrase occurs and all `required_evidence_ids` are attached to the response.
Configured gates are stored in `cases.v1.json`. Gate configuration is fail-closed:
it must be non-empty, use only documented names, include at least one minimum
score from greater than `0` through `1`, and use literal `true` for
`require_response_for_every_case` when that gate is present. Invalid
configuration exits `2` without producing a PASS summary.

To demonstrate the nonzero gate behavior without leaving a repository file,
run this PowerShell block from the repository root. Exit `1` is the expected
evaluator result; the block removes its temporary response document.

```powershell
$temp = Join-Path ([System.IO.Path]::GetTempPath()) "akasha-p0f-intentional-fail.json"
try {
    $json = '{"schema_version":"1.0","dataset_version":"phase0-provisional-v1","responses":[]}'
    [System.IO.File]::WriteAllText($temp, $json, [System.Text.UTF8Encoding]::new($false))
    python backend/evaluation/evaluate.py --responses $temp
    if ($LASTEXITCODE -ne 1) { throw "Expected evaluator exit 1, got $LASTEXITCODE" }
} finally {
    Remove-Item -LiteralPath $temp -ErrorAction SilentlyContinue
}
```

Check changed-file whitespace with:

```powershell
git diff --check -- backend/tests backend/evaluation CHATBOT_IMPLEMENTATION_PLAN.md
```

## Interpretation limits

This is executable evaluation scaffolding, not a chatbot accuracy measurement.
The three questions were read from the `Execution` sheet of `Qns_AKASHA.xlsx`.
Only question text was used. Expected values, evidence IDs, and example responses
are explicitly synthetic; no workbook answer or production record was imported.

Cases and responses carry `validated`, `provisional`, `generated`, or
`pending_validation` status as applicable. Reports show validated results
separately from provisional/non-validated results. The seed has no validated
cases, so its validated score is reported as `no cases`, never inferred from the
provisional score.

Importing workbook/database answers, establishing business-owned ground truth,
and measuring the real chatbot against a representative benchmark are deferred
to Phase 4.
