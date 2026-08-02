import os
import sys
from pathlib import Path
import unittest


os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.response_quality import redact_sensitive_answer


class ResponseQualityTests(unittest.TestCase):
    def test_report_preview_token_is_removed_from_visible_answer(self):
        token = "eyJzIjoic2Vzc2lvbi1hIiwicCI6IlAtMSIsImUiOjF9." + ("a" * 64)
        answer = f"Report preview is ready.\npreview_token: `{token}`\nPlease confirm generation."

        visible = redact_sensitive_answer(answer)

        self.assertNotIn(token, visible)
        self.assertNotIn("preview_token", visible)
        self.assertEqual(visible, "Report preview is ready.\nPlease confirm generation.")

    def test_inline_report_token_is_redacted(self):
        token = "eyJzIjoic2Vzc2lvbi1hIiwicCI6IlAtMSIsImUiOjF9." + ("b" * 64)
        visible = redact_sensitive_answer(f"Keep this internal: {token}. Confirm when ready.")

        self.assertNotIn(token, visible)
        self.assertIn("[secure report confirmation]", visible)

    def test_token_only_answer_becomes_safe_confirmation_prompt(self):
        token = "eyJzIjoic2Vzc2lvbi1hIiwicCI6IlAtMSIsImUiOjF9." + ("c" * 64)

        visible = redact_sensitive_answer(f"preview_token: {token}")

        self.assertEqual(
            visible,
            "The report preview is ready. Please confirm when you want the report generated.",
        )


if __name__ == "__main__":
    unittest.main()
