import os
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import Base, get_db
from engine.tools.portfolio_tools import portfolio_get_riskiest_projects
from engine.tools.risk_tools import risk_get_metric
from routers import risk
from services.risk_analytics_service import (
    COMMAND_CENTER_SCHEDULE_COUNT,
    KPI_PORTFOLIO_PROJECT_EXPOSURE,
    PMAG_SCHEDULE_RAG,
    PROJECT360_STATUS_TIER_COUNTS,
    RiskMetric,
    RiskAnalyticsService,
)
import models


class RiskFormulaTests(unittest.TestCase):
    def test_metric_is_deeply_immutable_and_serializable(self):
        metric = RiskAnalyticsService.pmag_schedule_rag(-2)
        with self.assertRaises(FrozenInstanceError):
            metric.value = "red"
        with self.assertRaises(TypeError):
            metric.components["finish_date_variance"] = -20
        self.assertEqual(metric.to_dict()["components"]["variance_unit"], "days")

    def test_pmag_rag_boundaries_null_and_delay_direction(self):
        cases = [(None, "grey", False), (1, "green", True), (0, "green", True), (-1, "amber", True), (-7, "amber", True), (-7.01, "red", True)]
        for variance, expected, available in cases:
            with self.subTest(variance=variance):
                metric = RiskAnalyticsService.pmag_schedule_rag(variance)
                self.assertEqual(metric.classification, expected)
                self.assertEqual(metric.availability, available)

    def test_project360_inputs_do_not_fabricate_schedule_values_without_p6(self):
        schedule = SimpleNamespace(
            p6_available=False,
            progress_pct=None,
            finish_date_variance=None,
        )
        sap = {
            "totals": {
                "purchase_orders": {"ordered_quantity": 10, "pending_quantity": 4, "order_value": 100},
                "inventory": {"quantity": 2},
                "consumption": {"net_value": 20},
            }
        }

        inputs = RiskAnalyticsService.project360_inputs(None, schedule, sap)

        self.assertIsNone(inputs["progress_pct"])
        self.assertIsNone(inputs["schedule_variance_days"])
        self.assertIsNone(inputs["spi"])
        self.assertIsNone(inputs["cpi"])

    def test_command_center_counts_use_strict_boundaries_and_skip_nulls(self):
        schedule = RiskAnalyticsService.command_center_schedule_count([
            {"name": "null", "finishDateVariance": None},
            {"name": "ahead", "finishDateVariance": 40},
            {"name": "boundary", "finishDateVariance": -30},
            {"name": "risk", "finishDateVariance": -30.01},
        ])
        financial = RiskAnalyticsService.command_center_financial_count([
            {"po_quantities_mw": None}, {"po_quantities_mw": 500}, {"po_quantities_mw": 500.01},
        ])
        self.assertEqual(schedule.value, 1)
        self.assertEqual(financial.value, 1)
        self.assertEqual(schedule.evidence[0]["name"], "risk")

    def test_command_center_overall_caps_without_merging_other_metrics(self):
        metric = RiskAnalyticsService.command_center_overall_score(19, 2)
        capped = RiskAnalyticsService.command_center_overall_score(20, 99)
        self.assertEqual(metric.value, 99)
        self.assertEqual(capped.value, 100)
        self.assertEqual(set(metric.components), {"schedule_risk_count", "financial_risk_count", "uncapped_score"})

    def test_heatmap_is_explicitly_heuristic(self):
        metric = RiskAnalyticsService.command_center_heatmap([
            {"name": "A", "finish_date_variance": -31},
        ])
        self.assertTrue(metric.heuristic)
        self.assertEqual(metric.classification, "heuristic")
        self.assertIn("not calibrated", metric.warnings[0])

    def test_project360_flag_boundaries_units_and_direction(self):
        boundary = RiskAnalyticsService.project360_risk_flags(
            material_availability_pct=80, po_volume=1, schedule_variance_days=-10,
            spi=0.95, in_transit_volume=1, cost_variance_inr=-1_000_000,
            progress_pct=50,
        )
        risk = RiskAnalyticsService.project360_risk_flags(
            material_availability_pct=79.9, po_volume=1, schedule_variance_days=-10.1,
            spi=1, in_transit_volume=0, cost_variance_inr=-1_000_001,
            progress_pct=49.9,
        )
        self.assertFalse(any(boundary.value.values()))
        self.assertTrue(risk.value["material_risk"])
        self.assertTrue(risk.value["schedule_risk"])
        self.assertTrue(risk.value["vendor_risk"])
        self.assertTrue(risk.value["financial_risk"])
        self.assertFalse(risk.value["procurement_risk"])
        no_po = RiskAnalyticsService.project360_risk_flags(
            material_availability_pct=None, po_volume=0, schedule_variance_days=None,
            spi=None, in_transit_volume=None, cost_variance_inr=None, progress_pct=49.9,
        )
        self.assertTrue(no_po.value["procurement_risk"])
        self.assertEqual(risk.components["progress_pct"], 49.9)

    def test_project360_cod_and_status_boundaries(self):
        self.assertFalse(RiskAnalyticsService.project360_cod_risk(
            schedule_variance_days=-14.49, material_risk=False,
            material_availability_pct=None, vendor_risk=False,
        ).value)
        self.assertTrue(RiskAnalyticsService.project360_cod_risk(
            schedule_variance_days=-14.51, material_risk=False,
            material_availability_pct=None, vendor_risk=False,
        ).value)
        base = dict(schedule_variance_days=0, spi=1, material_availability_pct=100, ordered_quantity=1, vendor_risk=False)
        self.assertEqual(RiskAnalyticsService.project360_status_tier(progress_pct=99, **base).value, "Completed")
        self.assertEqual(RiskAnalyticsService.project360_status_tier(progress_pct=100, **base).value, "Completed")
        self.assertEqual(RiskAnalyticsService.project360_status_tier(progress_pct=None, schedule_variance_days=-30, spi=0.79, material_availability_pct=100, ordered_quantity=1, vendor_risk=False).value, "High Risk")
        self.assertEqual(RiskAnalyticsService.project360_status_tier(progress_pct=None, schedule_variance_days=-30.01, spi=0.79, material_availability_pct=100, ordered_quantity=1, vendor_risk=False).value, "Critical")

    def test_project360_status_tier_counts_use_assigned_dashboard_tiers(self):
        metric = RiskAnalyticsService.project360_status_tier_counts([
            {"projectId": "P-1", "projectName": "One", "statusTier": "Critical"},
            {"projectId": "P-2", "projectName": "Two", "statusTier": "High Risk"},
            {"projectId": "P-3", "projectName": "Three", "statusTier": "Healthy"},
            {"projectId": "P-4", "projectName": "Four", "statusTier": "Healthy"},
        ])

        self.assertEqual(metric.metric_id, PROJECT360_STATUS_TIER_COUNTS)
        self.assertEqual(metric.value, {
            "Critical": 1,
            "High Risk": 1,
            "Watchlist": 0,
            "Healthy": 2,
            "Completed": 0,
        })
        self.assertEqual(metric.components["projects_evaluated"], 4)
        self.assertFalse(metric.heuristic)

    def test_predictive_formula_preserves_direction_multipliers_and_label(self):
        metric = RiskAnalyticsService.predictive_portfolio_slippage([
            SimpleNamespace(status="Active", finish_date_variance=-10),
            SimpleNamespace(status="Active", finish_date_variance=20),
            SimpleNamespace(status="Inactive", finish_date_variance=-20),
            SimpleNamespace(status="Active", finish_date_variance=None),
        ])
        self.assertEqual(metric.value["current"], 10)
        self.assertEqual(metric.value["30_days"], 12)
        self.assertEqual(metric.value["60_days"], 15)
        self.assertEqual(metric.value["90_days"], 19)
        self.assertEqual(metric.components["confidence_pct"], 87)
        self.assertTrue(metric.heuristic)

    def test_project360_consumes_shared_schedule_and_sap_services(self):
        schedule = SimpleNamespace(
            p6_available=True,
            finish_date_variance=-12,
            spi=0.9,
            progress_pct=40,
        )
        sap = {
            "has_data": True,
            "totals": {
                "purchase_orders": {
                    "ordered_quantity": 100,
                    "pending_quantity": 20,
                    "order_value": 0,
                },
                "inventory": {"quantity": 30},
                "consumption": {"net_value": 0},
            },
        }
        p6 = SimpleNamespace(
            planned_cost=0,
            actual_total_cost=0,
            total_cost_variance=0,
            baseline_start_date=None,
            start_date=None,
            baseline_finish_date=None,
            scheduled_finish_date=None,
            finish_date=None,
        )
        query = MagicMock()
        query.filter.return_value.first.return_value = p6
        db = SimpleNamespace(query=MagicMock(return_value=query))
        with patch(
            "services.risk_analytics_service.ScheduleMetricsService.get_by_project_id",
            return_value=schedule,
        ) as schedule_service, patch(
            "services.risk_analytics_service.get_sap_project_data",
            return_value=sap,
        ) as sap_service:
            flags, cod, status = RiskAnalyticsService.project360(db, "P-1")

        schedule_service.assert_called_once_with(db, "P-1")
        sap_service.assert_called_once_with(db, "P-1")
        self.assertEqual(flags.components["material_availability_pct"], 50)
        self.assertEqual(flags.components["progress_pct"], 40)
        self.assertFalse(cod.value)
        self.assertEqual(status.value, "Watchlist")

    def test_portfolio_exposures_are_explicit_named_metric_envelopes(self):
        exposure = {"project_id": "P-1", "overall_risk": {"overall_risk_pct": 42}}
        with patch("engine.kpi_engine.compute_portfolio_kpis", return_value=[exposure]):
            metrics = RiskAnalyticsService.portfolio_project_exposures(object())

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].metric_id, KPI_PORTFOLIO_PROJECT_EXPOSURE)
        self.assertEqual(metrics[0].scope, "P-1")
        self.assertEqual(metrics[0].to_dict()["value"], exposure)


class RiskToolTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_dispatch_requires_named_metric_and_returns_one_metric(self):
        db = self.Session()
        db.add(models.P6Project(p6_object_id=1, project_id="P-1", finish_date_variance=-31))
        db.add(models.ProjectMapping(project_id="P-1", project="Project 1"))
        db.commit()
        with self.assertRaises(ValueError):
            risk_get_metric(db, "")
        result = risk_get_metric(db, PMAG_SCHEDULE_RAG, project_id="P-1")
        count = risk_get_metric(db, COMMAND_CENTER_SCHEDULE_COUNT)
        db.close()
        self.assertEqual(result["metric_id"], PMAG_SCHEDULE_RAG)
        self.assertEqual(result["classification"], "red")
        self.assertEqual(count["value"], 1)

    def test_command_center_keeps_summary_fallback_and_dashboard_po_limit(self):
        db = self.Session()
        db.add(models.ProjectMapping(project_id="P-1", project="Project 1"))
        db.add(models.P6Project(
            p6_object_id=1,
            project_id="P-1",
            baseline_finish_date=datetime(2026, 1, 1),
            scheduled_finish_date=datetime(2026, 2, 2),
        ))
        for index in range(101):
            db.add(models.MTPOAmount(
                purchasing_document=f"PO-{index}",
                po_quantities_mw=501,
            ))
        db.commit()

        metrics = {metric.metric_id: metric for metric in RiskAnalyticsService.command_center(db)}
        db.close()

        self.assertEqual(metrics[COMMAND_CENTER_SCHEDULE_COUNT].value, 1)
        self.assertEqual(metrics[COMMAND_CENTER_SCHEDULE_COUNT].evidence[0]["finish_date_variance"], -32)
        self.assertEqual(metrics["command_center.financial_risk_count"].value, 100)

    def test_pmag_metric_uses_shared_schedule_lookup(self):
        db = object()
        schedule = SimpleNamespace(finish_date_variance=-8)
        with patch.object(
            RiskAnalyticsService,
            "pmag_schedule_rag",
            wraps=RiskAnalyticsService.pmag_schedule_rag,
        ), patch(
            "engine.tools.risk_tools.ScheduleMetricsService.get_by_project_id",
            return_value=schedule,
        ) as lookup:
            result = risk_get_metric(db, PMAG_SCHEDULE_RAG, project_id="P-8")

        lookup.assert_called_once_with(db, "P-8")
        self.assertEqual(result["classification"], "red")

    def test_riskiest_projects_unwraps_named_service_metrics_and_preserves_contract(self):
        exposure = {
            "project_id": "P-1",
            "project_name": "Project 1",
            "schedule": {
                "spi": 0.8,
                "cpi": 0.9,
                "progress_pct": 40,
                "schedule_status": "BEHIND",
                "activities_behind": 3,
                "critical_activities": 2,
            },
            "procurement": {"procurement_risk_pct": 25},
            "execution": {"execution_risk_pct": 10},
            "overall_risk": {"overall_risk_pct": 55, "components": ["schedule"]},
        }
        metric = RiskMetric(
            metric_id=KPI_PORTFOLIO_PROJECT_EXPOSURE,
            name="Portfolio exposure",
            formula_version="test-v1",
            scope="P-1",
            value=exposure,
            unit="KPI exposure bundle",
            classification=None,
            components={},
            formula="test",
            availability=True,
            heuristic=False,
            evidence=(),
            warnings=(),
        )
        db = object()
        with patch.object(
            RiskAnalyticsService,
            "portfolio_project_exposures",
            return_value=(metric,),
        ) as service:
            result = portfolio_get_riskiest_projects(db, top_n=1)

        service.assert_called_once_with(db)
        self.assertEqual(result["total_portfolio_projects"], 1)
        self.assertEqual(result["showing_top_n"], 1)
        self.assertEqual(result["riskiest_projects"][0], {
            "project_id": "P-1",
            "project_name": "Project 1",
            "risk_score": 55,
            "spi": 0.8,
            "cpi": 0.9,
            "progress_pct": 40,
            "schedule_status": "BEHIND",
            "activities_behind": 3,
            "critical_activities": 2,
            "procurement_risk_pct": 25,
            "execution_risk_pct": 10,
            "risk_drivers": ["schedule"],
        })


class RiskRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(risk.router)
        app.dependency_overrides[get_db] = lambda: object()
        cls.client = TestClient(app)

    def test_portfolio_routes_return_metric_keyed_envelopes(self):
        command_metrics = RiskAnalyticsService.command_center_schedule_count([]),
        predictive_metric = RiskAnalyticsService.predictive_portfolio_slippage([])
        with patch.object(RiskAnalyticsService, "command_center", return_value=command_metrics), patch.object(
            RiskAnalyticsService, "predictive", return_value=predictive_metric
        ):
            command = self.client.get("/api/risk/command-center")
            predictive = self.client.get("/api/risk/predictive")

        self.assertEqual(command.status_code, 200)
        self.assertEqual(
            command.json()["metrics"][COMMAND_CENTER_SCHEDULE_COUNT]["metric_id"],
            COMMAND_CENTER_SCHEDULE_COUNT,
        )
        self.assertEqual(predictive.status_code, 200)
        self.assertIn("predictive.portfolio_slippage", predictive.json()["metrics"])

    def test_project_route_filters_to_requested_named_metric(self):
        metrics = RiskAnalyticsService.project360_risk_flags(
            material_availability_pct=100,
            po_volume=1,
            schedule_variance_days=0,
            spi=1,
            in_transit_volume=1,
            cost_variance_inr=0,
            progress_pct=50,
        ), RiskAnalyticsService.project360_cod_risk(
            schedule_variance_days=0,
            material_risk=False,
            material_availability_pct=100,
            vendor_risk=False,
        )
        with patch.object(RiskAnalyticsService, "project360", return_value=metrics):
            response = self.client.get(
                "/api/risk/project/P-1",
                params={"metric_id": "project360.cod_risk"},
            )
            missing = self.client.get(
                "/api/risk/project/P-1",
                params={"metric_id": "project360.unknown"},
            )

        self.assertEqual(list(response.json()["metrics"]), ["project360.cod_risk"])
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
