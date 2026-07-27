import os
import sys
from datetime import datetime
from pathlib import Path
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from engine.graph.tools import model_tool_schemas
from engine.tools.tc_tools import tc_search_lines
import models


class TransmissionRegionSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=engine)
        cls.Session = sessionmaker(bind=engine)

    def setUp(self):
        self.db = self.Session()
        for table in reversed(Base.metadata.sorted_tables):
            self.db.execute(table.delete())
        self.db.add_all([
            models.TcNetworkEdge(
                region="Rajasthan",
                edge_id="RJ-1",
                from_label="Bhadla",
                to_label="Bikaner",
                status="Not Started",
                normalized_status="Not Started",
                foundation="0%",
                erection="0%",
                stringing="0%",
                is_delayed=False,
                upload_time=datetime(2026, 7, 1),
            ),
            models.TcNetworkEdge(
                region="Rajasthan",
                edge_id="RJ-1",
                from_label="Bhadla",
                to_label="Bikaner",
                status="In Progress",
                normalized_status="In Progress",
                foundation="60%",
                erection="40%",
                stringing="20%",
                is_delayed=False,
                upload_time=datetime(2026, 7, 15),
            ),
            models.TcNetworkEdge(
                region="Rajasthan",
                edge_id="RJ-2",
                from_label="Fatehgarh",
                to_label="Bhadla",
                status="Completed",
                normalized_status="Completed",
                foundation="100%",
                erection="100%",
                stringing="100%",
                expected_date="Mar-27",
                scd="Jan-27",
                is_delayed=True,
                upload_time=datetime(2026, 7, 14),
            ),
            models.TcNetworkEdge(
                region="Gujarat",
                edge_id="GJ-1",
                from_label="Khavda",
                to_label="Bhuj",
                status="In Progress",
                normalized_status="In Progress",
                is_delayed=True,
                upload_time=datetime(2026, 7, 16),
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_search_is_case_insensitive_and_uses_latest_line_records(self):
        result = tc_search_lines(self.db, "rajasthan")

        self.assertTrue(result["has_data"])
        self.assertEqual(result["region"], "Rajasthan")
        self.assertEqual(result["total_matching"], 2)
        self.assertEqual([line["edge_id"] for line in result["lines"]], ["RJ-1", "RJ-2"])
        self.assertEqual(result["lines"][0]["avg_progress"], 40.0)
        self.assertEqual(result["status_breakdown_for_returned_lines"], {
            "completed": 1,
            "in_progress": 1,
            "not_started": 0,
            "unknown": 0,
            "delayed": 1,
        })
        self.assertEqual(result["_synced_at"], "2026-07-15T00:00:00")

    def test_search_can_return_only_delayed_lines(self):
        result = tc_search_lines(self.db, "Rajasthan", delayed_only=True, limit=1)

        self.assertEqual(result["total_matching"], 1)
        self.assertEqual(result["returned"], 1)
        self.assertEqual(result["lines"][0]["edge_id"], "RJ-2")

    def test_region_search_is_exposed_with_a_required_region(self):
        schemas = {
            item["function"]["name"]: item["function"]
            for item in model_tool_schemas()
        }
        parameters = schemas["tc_search_lines"]["parameters"]

        self.assertIn("region", parameters["required"])
        self.assertIn("delayed_only", parameters["properties"])
        self.assertIn("limit", parameters["properties"])


if __name__ == "__main__":
    unittest.main()
