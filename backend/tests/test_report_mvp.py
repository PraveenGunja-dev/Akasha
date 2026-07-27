import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.report_mvp_service import create_preview_token, generate_narrative, validate_preview_token
from services.report_renderers import render_project_progress_docx, render_project_progress_pdf


def report_dataset():
    return {
        "metadata": {
            "project_name": "Test Project",
            "source_freshness": {"P6": "2026-07-22", "SAP": None, "TC": None, "Pulse": None},
            "missing_sources": ["SAP", "TC", "Pulse"],
        },
        "executive_summary": "Test Project is 23.1% complete. SPI is unavailable.",
        "project_summary": {
            "status": "Active",
            "scheduled_finish": "2027-10-01",
            "data_date": "2026-07-18",
            "last_synced_at": "2026-07-22",
        },
        "schedule": {
            "progress_pct": 23.1,
            "completed_activities": 486,
            "in_progress_activities": 84,
            "not_started_activities": 1730,
            "spi": None,
            "cpi": None,
        },
        "procurement": {"has_data": False, "reason": "No mapped data"},
        "transmission": {"has_data": False, "reason": "No mapped data"},
        "quality": {"has_data": False, "non_conformances": 0, "rfis": 0},
        "in_progress_activities": {
            "activities": [{"activity_id": "A-1", "name": "Foundation", "percent_complete": 75.0}],
        },
    }


class ReportMvpTests(unittest.TestCase):
    def test_preview_token_is_bound_to_session_and_project(self):
        token = create_preview_token("session-a", "FY26-P18")
        validate_preview_token(token, "session-a", "FY26-P18")
        with self.assertRaises(ValueError):
            validate_preview_token(token, "session-b", "FY26-P18")
        with self.assertRaises(ValueError):
            validate_preview_token(token, "session-a", "FY26-P19")

    def test_pdf_and_docx_render_from_same_dataset(self):
        with TemporaryDirectory() as directory:
            pdf = Path(directory) / "report.pdf"
            docx = Path(directory) / "report.docx"
            dataset = report_dataset()
            render_project_progress_pdf(dataset, pdf)
            render_project_progress_docx(dataset, docx)
            self.assertGreater(pdf.stat().st_size, 1_000)
            self.assertGreater(docx.stat().st_size, 10_000)
            self.assertEqual(pdf.read_bytes()[:4], b"%PDF")
            self.assertEqual(docx.read_bytes()[:2], b"PK")

    def test_valid_structured_narrative_is_used(self):
        expected = (
            "Test Project remains active with P6 duration progress at 23.1%. "
            "SPI and CPI are unavailable, so no schedule-performance classification is made. "
            "SAP, TC, and Pulse data are not mapped and remain unassessed."
        )
        provider = SimpleNamespace(invoke=lambda *_args, **_kwargs: SimpleNamespace(
            content='{"executive_summary": ' + __import__("json").dumps(expected) + '}'
        ))
        with patch("services.report_mvp_service.get_model_provider", return_value=provider):
            self.assertEqual(generate_narrative(report_dataset()), expected)

    def test_reasoning_leak_falls_back_to_clean_deterministic_summary(self):
        leaked = (
            "The user wants a concise paragraph. I need to analyze the supplied JSON facts. "
            "Let me draft the report after reviewing the constraints and available metrics."
        )
        provider = SimpleNamespace(invoke=lambda *_args, **_kwargs: SimpleNamespace(
            content='{"executive_summary": ' + __import__("json").dumps(leaked) + '}'
        ))
        with patch("services.report_mvp_service.get_model_provider", return_value=provider):
            result = generate_narrative(report_dataset())
        self.assertNotIn("user wants", result.lower())
        self.assertNotIn("i need to", result.lower())
        self.assertIn("23.1%", result)
        self.assertIn("No mapped data is available from SAP, TC, Pulse", result)


if __name__ == "__main__":
    unittest.main()
