"""Authoritative business datasets consumed by chart renderers."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from services.project_catalog_service import ProjectCatalogService
from services.risk_analytics_service import PROJECT360_STATUS_TIER, RiskAnalyticsService
from services.sap_project_data_service import SapProjectDataService
from services.schedule_metrics_service import ScheduleMetricsService
from services import transmission_service


# Presentation encoding only; tier classification remains owned by RiskAnalyticsService.
RISK_TIER_ORDER = {
    "Healthy": 0,
    "Watchlist": 1,
    "High Risk": 2,
    "Critical": 3,
}


def _quantity(value: object | None, weight: float) -> float:
    return float(value or 0) * weight


def _final_quantity(value: float) -> int | float:
    rounded = round(value, 2)
    return int(rounded) if rounded.is_integer() else rounded


class ChartSpecService:
    """Build chart-ready business inputs from shared domain services."""

    @staticmethod
    def activity_status(db: Session, project_id: str) -> dict:
        project = ProjectCatalogService.get_by_project_id(db, project_id)
        schedule = ScheduleMetricsService.get_by_project_id(db, project_id)
        breakdown = ScheduleMetricsService.get_activity_status_breakdown(db, project_id)
        return {
            "project_name": project.display_name if project else project_id,
            "total": schedule.activity_count or 0,
            "breakdown": breakdown,
            "data_as_of": schedule.freshness.get("data_as_of"),
            "sources": ["p6_activity"],
        }

    @staticmethod
    def project_comparison(db: Session, project_ids: list[str]) -> dict:
        rows = []
        for project_id in project_ids:
            project = ProjectCatalogService.get_by_project_id(db, project_id)
            schedule = ScheduleMetricsService.get_by_project_id(db, project_id)
            if schedule.p6_available:
                forecast_finish = schedule.finish_date
                baseline_finish = schedule.baseline_finish
                baseline_slip_days = None
                if forecast_finish is not None and baseline_finish is not None:
                    forecast_date = forecast_finish.date() if hasattr(forecast_finish, "date") else forecast_finish
                    baseline_date = baseline_finish.date() if hasattr(baseline_finish, "date") else baseline_finish
                    baseline_slip_days = (forecast_date - baseline_date).days
                rows.append({
                    "project_id": project_id,
                    "project_name": project.display_name if project else project_id,
                    "progress_pct": schedule.progress_pct or 0,
                    "completed_activities": schedule.completed_activities or 0,
                    "in_progress_activities": schedule.in_progress_activities or 0,
                    "not_started_activities": schedule.not_started_activities or 0,
                    "planned_duration": schedule.planned_duration,
                    "actual_duration": schedule.actual_duration,
                    "remaining_duration": schedule.remaining_duration,
                    "baseline_slip_days": baseline_slip_days,
                    "forecast_finish": forecast_date.isoformat() if forecast_finish is not None else None,
                    "baseline_finish": baseline_date.isoformat() if baseline_finish is not None else None,
                    "data_as_of": schedule.freshness["data_as_of"],
                })
        rows.sort(key=lambda row: row["progress_pct"], reverse=True)
        return {"projects": rows, "sources": ["project_mapping", "p6_project"]}

    @staticmethod
    def daily_completion_trend(db: Session, project_id: str, days: int = 30) -> dict:
        project = ProjectCatalogService.get_by_project_id(db, project_id)
        trend = ScheduleMetricsService.get_daily_activity_completion_trend(
            db, project_id, days=days
        )
        return {
            **trend,
            "project_name": project.display_name if project else trend.get("project_name", project_id),
            "sources": ["p6_project", "p6_activity"],
        }

    @staticmethod
    def planned_vs_actual_progress(db: Session, project_id: str) -> dict:
        project = ProjectCatalogService.get_by_project_id(db, project_id)
        comparison = ScheduleMetricsService.get_planned_vs_actual_activity_progress(
            db, project_id
        )
        return {
            **comparison,
            "project_name": project.display_name if project else comparison.get("project_name", project_id),
            "sources": ["p6_project", "p6_activity"],
        }

    @staticmethod
    def block_progress(db: Session, project_id: str) -> dict:
        project = ProjectCatalogService.get_by_project_id(db, project_id)
        snapshot = ScheduleMetricsService.get_block_period_progress(
            db, project_id, period="current_month"
        )
        return {
            **snapshot,
            "project_name": project.display_name if project else snapshot.get("project_name", project_id),
            "sources": ["p6_project", "p6_activity", "p6_wbs_node"],
        }

    @staticmethod
    def delayed_activities(db: Session, project_id: str, limit: int = 12) -> dict:
        project = ProjectCatalogService.get_by_project_id(db, project_id)
        return {
            "project_name": project.display_name if project else project_id,
            "activities": ScheduleMetricsService.get_delayed_activities(
                db, project_id, limit=limit
            ),
            "sources": ["p6_activity"],
        }

    @staticmethod
    def _sap_grouped(db: Session, project_id: str, field: str) -> dict:
        data = SapProjectDataService.get_by_project_id(db, project_id)
        allocations = data["record_allocations"]["mt_poamount"]
        grouped = defaultdict(lambda: {"ordered": 0.0, "delivered": 0.0, "pending": 0.0})
        for row in data["purchase_orders"]:
            name = getattr(row, field, None)
            if field == "material_name" and not name:
                name = row.material_code
            name = name or "Unknown"
            weight = allocations.get(row.id, 1.0)
            grouped[name]["ordered"] += _quantity(row.order_quantity, weight)
            grouped[name]["delivered"] += _quantity(row.delivered_qty, weight)
            grouped[name]["pending"] += _quantity(row.still_to_deliver_qty, weight)
        rows = [
            {"name": name, **{key: _final_quantity(value) for key, value in totals.items()}}
            for name, totals in grouped.items()
        ]
        rows.sort(key=lambda row: (-row["pending"], row["name"]))
        return {
            "project_name": data["project_name"],
            "has_data": bool(rows),
            "rows": rows,
            "totals": data["totals"]["purchase_orders"],
            "freshness": data["freshness"]["mt_poamount"],
            "sources": ["mt_poamount"],
        }

    @classmethod
    def material_gaps(cls, db: Session, project_id: str, limit: int = 12) -> dict:
        data = cls._sap_grouped(db, project_id, "material_name")
        data["rows"] = [row for row in data["rows"] if row["pending"] > 0][:limit]
        data["has_data"] = bool(data["rows"])
        return data

    @classmethod
    def vendor_performance(cls, db: Session, project_id: str, limit: int = 8) -> dict:
        data = cls._sap_grouped(db, project_id, "vendor_name")
        data["rows"] = data["rows"][:limit]
        return data

    @classmethod
    def sap_po_fulfillment(cls, db: Session, project_id: str, limit: int = 12) -> dict:
        data = cls._sap_grouped(db, project_id, "material_name")
        totals = data["totals"]
        ordered = totals["ordered_quantity"]
        data["fulfillment_pct"] = round(totals["delivered_quantity"] / ordered * 100, 1) if ordered else 0
        data["rows"] = data["rows"][:limit]
        return data

    @staticmethod
    def transmission_status(db: Session, project_id: str | None = None) -> dict:
        if project_id:
            return {**transmission_service.project_status(db, project_id), "sources": ["tc_network_edge"]}
        return {**transmission_service.network_status(db), "sources": ["tc_network_edge"]}

    @staticmethod
    def portfolio_risk(db: Session, limit: int = 8) -> dict:
        rows = []
        seen = set()
        for project in ProjectCatalogService.list_projects(db):
            if not project.project_id or project.project_id in seen:
                continue
            seen.add(project.project_id)
            metrics = RiskAnalyticsService.project360(db, project.project_id)
            status = next(metric for metric in metrics if metric.metric_id == PROJECT360_STATUS_TIER)
            if status.availability and status.value != "Completed":
                rows.append({
                    "project_name": project.display_name,
                    "risk_tier": status.value,
                    "risk_level": RISK_TIER_ORDER.get(status.value, 0),
                })
        rows.sort(key=lambda row: (-row["risk_level"], row["project_name"]))
        return {"projects": rows[:limit], "sources": ["project_mapping", "p6_project", "mt_poamount"]}
