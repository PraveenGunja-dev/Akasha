"""Stable configuration for the isolated golden evaluation runner."""

from pathlib import Path


EVALUATION_DIR = Path(__file__).resolve().parent
SCHEMA_VERSION = "2.0"
DEFAULT_CASES_PATH = EVALUATION_DIR / "golden_cases.v1.json"
DEFAULT_RESPONSES_PATH = EVALUATION_DIR / "sample_responses.v1.json"
DEFAULT_JSON_REPORT_PATH = EVALUATION_DIR / "reports" / "sample-report.v1.json"
DEFAULT_MARKDOWN_REPORT_PATH = EVALUATION_DIR / "reports" / "sample-report.v1.md"

CASE_STATUSES = {
    "pending_business_validation",
    "business_validated",
    "blocked_missing_source",
}
RESPONSE_STATUSES = {"sample_generated", "shadow_generated", "reviewed"}
RESOLUTION_STATUSES = {"resolved", "ambiguous", "not_applicable"}
FACT_TYPES = {"boolean", "date", "integer", "null", "number", "string"}
KNOWN_GATES = {
    "minimum_overall_score",
    "minimum_case_pass_rate",
    "maximum_unsupported_claims",
    "require_response_for_every_case",
}
