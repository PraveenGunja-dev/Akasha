import os
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from services.freshness_service import (
    build_answer_provenance,
    extract_tool_evidence,
    get_sync_versions,
    SourceEvidence,
    SourceFreshness,
    get_source_freshness,
    make_freshness_envelope,
    mark_source_sync_succeeded,
)
import models


class FreshnessServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.db = self.Session()
        self.db.execute(models.SourceSyncState.__table__.delete())
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_dtos_are_immutable_and_keep_timestamp_semantics_distinct(self):
        cutoff = datetime(2026, 7, 1)
        synced = datetime(2026, 7, 2, 9)
        generated = datetime(2026, 7, 2, 9, 0, 1)
        freshness = SourceFreshness("P6", cutoff, synced, 3)
        evidence = SourceEvidence("project-1", "p6_project", freshness, ["FY26-P18"])
        envelope = make_freshness_envelope([freshness], answer_generated_at=generated)

        self.assertEqual(evidence.source_system, "P6")
        self.assertEqual(evidence.record_ids, ("FY26-P18",))
        self.assertEqual(evidence.data_as_of, cutoff)
        self.assertEqual(evidence.last_synced_at, synced)
        self.assertEqual(envelope.sources[0].data_as_of, cutoff)
        self.assertEqual(envelope.sources[0].last_synced_at, synced)
        self.assertEqual(envelope.answer_generated_at, generated)
        with self.assertRaises(FrozenInstanceError):
            freshness.sync_version = 4

    def test_successes_increment_version_and_replace_freshness(self):
        first = mark_source_sync_succeeded(
            self.db,
            "P6",
            data_as_of=datetime(2026, 7, 1),
            last_synced_at=datetime(2026, 7, 2),
        )
        second = mark_source_sync_succeeded(
            self.db,
            "P6",
            data_as_of=datetime(2026, 7, 3),
            last_synced_at=datetime(2026, 7, 4),
        )

        self.assertEqual(first.sync_version, 1)
        self.assertEqual(second.sync_version, 2)
        self.assertEqual(get_source_freshness(self.db, "P6"), second)

    def test_rolled_back_work_does_not_increment_version(self):
        mark_source_sync_succeeded(self.db, "Pulse", last_synced_at=datetime(2026, 7, 1))

        with patch.object(self.db, "execute", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                mark_source_sync_succeeded(
                    self.db,
                    "Pulse",
                    last_synced_at=datetime(2026, 7, 2),
                )

        self.assertEqual(get_source_freshness(self.db, "Pulse").sync_version, 1)

    def test_empty_source_name_is_rejected_without_writing(self):
        with self.assertRaises(ValueError):
            mark_source_sync_succeeded(self.db, "  ")

        self.assertEqual(self.db.query(models.SourceSyncState).count(), 0)

    def test_answer_provenance_keeps_per_source_cutoff_and_sync_times(self):
        mark_source_sync_succeeded(
            self.db, "P6", data_as_of=datetime(2026, 7, 1),
            last_synced_at=datetime(2026, 7, 2),
        )
        mark_source_sync_succeeded(
            self.db, "SAP", data_as_of=datetime(2026, 6, 30),
            last_synced_at=datetime(2026, 7, 3),
        )

        provenance = build_answer_provenance(
            self.db,
            ["p6_get_project_summary", "sap_get_po_summary"],
            evidence=[
                {
                    "evidence_id": "p6-1", "tool_name": "p6_get_project_summary",
                    "status": "ok", "source_system": "P6", "source_entity": "p6_project",
                    "project_id": "P-1", "record_ids": [], "data_as_of": None,
                    "last_synced_at": None,
                },
                {
                    "evidence_id": "sap-1", "tool_name": "sap_get_po_summary",
                    "status": "ok", "source_system": "SAP", "source_entity": "mt_poamount",
                    "project_id": "P-1", "record_ids": [], "data_as_of": None,
                    "last_synced_at": None,
                },
            ],
            answer_generated_at=datetime(2026, 7, 4),
        )

        self.assertEqual(provenance["data_as_of"], "2026-06-30T00:00:00")
        self.assertEqual(provenance["last_synced_at"], "2026-07-03T00:00:00")
        self.assertEqual(provenance["answer_generated_at"], "2026-07-04T00:00:00")
        self.assertIn("p6_project", provenance["tables"])
        self.assertIn("mt_poamount", provenance["tables"])
        self.assertEqual(len(provenance["evidence"]), 2)
        self.assertEqual(get_sync_versions(self.db)["P6"], 1)

    def test_tool_evidence_uses_explicit_result_sources_not_tool_name_prefixes(self):
        evidence = extract_tool_evidence(
            {
                "project_id": "P-1",
                "activities": [{"activity_id": "A-1"}],
                "_source_table": "p6_activity",
                "data_as_of": "2026-07-01T00:00:00",
            },
            tool_name="misleading_tool_name",
            status="ok",
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["source_system"], "P6")
        self.assertEqual(evidence[0]["source_entity"], "p6_activity")
        self.assertEqual(evidence[0]["record_ids"], ["A-1"])
        self.assertEqual(
            extract_tool_evidence({}, tool_name="p6_fake", status="ok"),
            (),
        )

    def test_nested_sources_exclude_unavailable_p6_rows(self):
        evidence = extract_tool_evidence(
            {
                "projects": [
                    {"project_id": "M-1", "p6_available": False, "_source_table": "project_mapping+p6_project"},
                    {"project_id": "P-1", "p6_available": True, "_source_table": "project_mapping+p6_project"},
                ]
            },
            tool_name="p6_list_all_projects",
            status="ok",
        )
        self.assertEqual(
            {item["source_entity"] for item in evidence},
            {"project_mapping", "p6_project"},
        )

        mapping_only = extract_tool_evidence(
            {"project_id": "M-1", "p6_available": False},
            tool_name="capacity_get_project_status",
            status="ok",
        )
        self.assertEqual([item["source_entity"] for item in mapping_only], ["project_mapping"])

        unavailable_risk = extract_tool_evidence(
            {"metric_id": "pmag.schedule_rag", "availability": False},
            tool_name="risk_get_metric",
            status="no_data",
        )
        self.assertEqual(unavailable_risk, ())


if __name__ == "__main__":
    unittest.main()
