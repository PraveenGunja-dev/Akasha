from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from collections import defaultdict
import re
from typing import Any, Literal

from sqlalchemy.orm import Session

import models


ProgressFormula = Literal[
    "actual_non_labor_units / at_completion_non_labor_units",
    "construction_percent_complete",
    "duration_percent_complete",
]


def _percentage(value: object | None) -> float | None:
    if value is None:
        return None
    percentage = float(value)
    if 0 <= percentage <= 1:
        percentage *= 100
    return round(percentage, 1)


def _date_value(value: object | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


@dataclass(frozen=True, slots=True)
class ScheduleMetrics:
    p6_available: bool
    project_id: str | None = None
    name: str | None = None
    parent_eps_name: str | None = None
    status: str | None = None
    start_date: datetime | date | None = None
    finish_date: datetime | date | None = None
    planned_start: datetime | date | None = None
    scheduled_finish: datetime | date | None = None
    must_finish_by: datetime | date | None = None
    baseline_start: datetime | date | None = None
    baseline_finish: datetime | date | None = None
    progress_pct: float | None = None
    progress_formula: ProgressFormula | None = None
    progress_formula_version: str = "dashboard-progress-v1"
    progress_units: str = "percent"
    duration_percent_complete: float | None = None
    is_delayed: bool | None = None
    delay_formula: str = (
        "finish_date_variance < 0 OR "
        "(forecast_finish > baseline_or_scheduled_finish AND progress_pct < 100)"
    )
    finish_date_variance: float | None = None
    finish_date_variance_units: str = "days"
    delay_reference_finish: datetime | date | None = None
    forecast_vs_reference_days: int | None = None
    duration_units: str = "hours"
    total_float_units: str = "hours"
    planned_duration: float | None = None
    actual_duration: float | None = None
    remaining_duration: float | None = None
    baseline_duration: float | None = None
    total_float: float | None = None
    spi: float | None = None
    cpi: float | None = None
    activity_count: int | None = None
    completed_activities: int | None = None
    in_progress_activities: int | None = None
    not_started_activities: int | None = None
    data_date: datetime | date | None = None
    last_synced_at: datetime | date | None = None

    @property
    def activity_counts(self) -> dict[str, int | None]:
        return {
            "total": self.activity_count,
            "completed": self.completed_activities,
            "in_progress": self.in_progress_activities,
            "not_started": self.not_started_activities,
        }

    @property
    def freshness(self) -> dict[str, str | None]:
        data_as_of = self.data_date.isoformat() if self.data_date else None
        return {
            "data_as_of": data_as_of,
            "data_date": data_as_of,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
        }


class ScheduleMetricsService:
    """Canonical P6 progress, schedule health, count, and provenance facts."""

    @staticmethod
    def calculate(
        p6: object | None,
        *,
        activity_counts: dict[str, int] | None = None,
    ) -> ScheduleMetrics:
        if p6 is None:
            return ScheduleMetrics(p6_available=False)

        denominator = getattr(p6, "at_completion_non_labor_units", None)
        if denominator is not None and denominator > 0:
            numerator = getattr(p6, "actual_non_labor_units", None) or 0
            progress = round((float(numerator) / float(denominator)) * 100, 1)
            formula: ProgressFormula = "actual_non_labor_units / at_completion_non_labor_units"
        else:
            construction_progress = getattr(p6, "construction_percent_complete", None)
            if construction_progress is not None:
                progress = _percentage(construction_progress)
                formula = "construction_percent_complete"
            else:
                progress = _percentage(getattr(p6, "duration_percent_complete", None))
                formula = "duration_percent_complete"

        variance = getattr(p6, "finish_date_variance", None)
        forecast = _date_value(getattr(p6, "finish_date", None))
        baseline = _date_value(getattr(p6, "baseline_finish_date", None))
        scheduled = _date_value(getattr(p6, "scheduled_finish_date", None))
        incomplete = progress is None or progress < 100
        # A baseline supersedes the scheduled date. Do not let a later scheduled
        # date contradict the approved baseline comparison.
        reference_finish = baseline if baseline is not None else scheduled
        forecast_vs_reference_days = (
            (forecast - reference_finish).days
            if forecast is not None and reference_finish is not None
            else None
        )
        later_than_reference = bool(
            forecast_vs_reference_days is not None and forecast_vs_reference_days > 0
        )
        is_delayed = bool((variance is not None and variance < 0) or (incomplete and later_than_reference))

        counts = activity_counts or {}
        return ScheduleMetrics(
            p6_available=True,
            project_id=getattr(p6, "project_id", None),
            name=getattr(p6, "name", None),
            parent_eps_name=getattr(p6, "parent_eps_name", None),
            status=getattr(p6, "status", None),
            start_date=getattr(p6, "start_date", None),
            finish_date=getattr(p6, "finish_date", None),
            planned_start=getattr(p6, "planned_start_date", None),
            scheduled_finish=getattr(p6, "scheduled_finish_date", None),
            must_finish_by=getattr(p6, "must_finish_by_date", None),
            baseline_start=getattr(p6, "baseline_start_date", None),
            baseline_finish=getattr(p6, "baseline_finish_date", None),
            progress_pct=progress,
            progress_formula=formula,
            duration_percent_complete=_percentage(getattr(p6, "duration_percent_complete", None)),
            is_delayed=is_delayed,
            finish_date_variance=float(variance) if variance is not None else None,
            delay_reference_finish=(
                getattr(p6, "baseline_finish_date", None)
                if baseline is not None
                else getattr(p6, "scheduled_finish_date", None)
            ),
            forecast_vs_reference_days=forecast_vs_reference_days,
            planned_duration=getattr(p6, "planned_duration", None),
            actual_duration=getattr(p6, "actual_duration", None),
            remaining_duration=getattr(p6, "remaining_duration", None),
            baseline_duration=getattr(p6, "baseline_duration", None),
            total_float=getattr(p6, "total_float", None),
            spi=getattr(p6, "schedule_performance_index", None),
            cpi=getattr(p6, "cost_performance_index", None),
            activity_count=counts.get("total", getattr(p6, "activity_count", None)),
            completed_activities=counts.get(
                "completed", getattr(p6, "completed_activity_count", None)
            ),
            in_progress_activities=counts.get(
                "in_progress", getattr(p6, "in_progress_activity_count", None)
            ),
            not_started_activities=counts.get(
                "not_started", getattr(p6, "not_started_activity_count", None)
            ),
            data_date=getattr(p6, "data_date", None),
            last_synced_at=getattr(p6, "last_synced_at", None),
        )

    @classmethod
    def get_by_project_id(cls, db: Session, project_id: str) -> ScheduleMetrics:
        p6 = db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        if p6 is None:
            return cls.calculate(None)

        activities = db.query(models.P6Activity.status).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        ).all()
        statuses = [str(row[0] or "").casefold() for row in activities]
        return cls.calculate(
            p6,
            activity_counts={
                "total": len(statuses),
                "completed": sum("completed" in status for status in statuses),
                "in_progress": sum("progress" in status for status in statuses),
                "not_started": sum("not started" in status for status in statuses),
            },
        )

    @classmethod
    def get_activities(
        cls,
        db: Session,
        project_id: str,
        *,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Return canonical activity facts without exposing ORM rows to consumers."""
        p6 = db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        if p6 is None:
            return []
        query = db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        )
        if status:
            query = query.filter(models.P6Activity.status == status)
        query = query.order_by(
            models.P6Activity.activity_id.asc(),
            models.P6Activity.p6_object_id.asc(),
        )
        if limit is not None:
            query = query.limit(limit)
        return [cls._activity_fact(activity) for activity in query.all()]

    @classmethod
    def get_activity_page(
        cls,
        db: Session,
        project_id: str,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return activity facts and project provenance for chatbot pagination."""
        metrics = cls.get_by_project_id(db, project_id)
        if not metrics.p6_available:
            return {
                "exists": False,
                "total_matching": None,
                "activities": [],
                "metrics": metrics,
            }

        p6 = db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        query = db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        )
        if status:
            query = query.filter(models.P6Activity.status == status)
        total_matching = query.count()
        rows = query.order_by(
            models.P6Activity.activity_id.asc(),
            models.P6Activity.p6_object_id.asc(),
        ).offset(offset).limit(limit).all()
        return {
            "exists": True,
            "total_matching": total_matching,
            "activities": [cls._activity_fact(activity) for activity in rows],
            "metrics": metrics,
        }

    @classmethod
    def get_block_period_progress(
        cls,
        db: Session,
        project_id: str,
        *,
        period: Literal["last_month", "current_month", "last_n_days"] = "last_month",
        days: int = 30,
    ) -> dict[str, Any]:
        """Rank blocks by activity completion events in a calendar period.

        P6 activity rows contain only the latest percentage, so this method does
        not claim a historical percentage delta without persisted snapshots.
        """
        project = db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        if project is None:
            return {"p6_available": False, "project_id": project_id, "blocks": []}

        data_date = _date_value(project.data_date)
        anchor = data_date or datetime.utcnow().date()
        current_month_start = anchor.replace(day=1)
        if period == "last_month":
            period_end = current_month_start
            previous_day = current_month_start - timedelta(days=1)
            period_start = previous_day.replace(day=1)
        elif period == "current_month":
            period_start = current_month_start
            period_end = anchor + timedelta(days=1)
        else:
            if not 1 <= days <= 365:
                raise ValueError("days must be between 1 and 365")
            period_end = anchor + timedelta(days=1)
            period_start = period_end - timedelta(days=days)

        nodes = db.query(models.P6WBSNode).filter(
            models.P6WBSNode.project_object_id == project.p6_object_id
        ).all()
        nodes_by_id = {node.p6_object_id: node for node in nodes}
        activities = db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == project.p6_object_id
        ).all()
        activities_by_block: dict[str, list[models.P6Activity]] = defaultdict(list)
        wbs_ids_by_block: dict[str, set[int]] = defaultdict(set)
        unassigned = 0
        for activity in activities:
            block_identity = cls._activity_block(activity, nodes_by_id)
            if block_identity is None:
                unassigned += 1
                continue
            block, block_wbs_object_id = block_identity
            activities_by_block[block].append(activity)
            wbs_ids_by_block[block].add(block_wbs_object_id)

        blocks = []
        for block, rows in sorted(activities_by_block.items()):
            percentages = [
                value for value in (_percentage(row.percent_complete) for row in rows)
                if value is not None
            ]
            completed_in_period = [
                row for row in rows
                if row.actual_finish_date
                and period_start <= row.actual_finish_date.date() < period_end
            ]
            currently_completed = sum(
                "complete" in str(row.status or "").casefold()
                or (_percentage(row.percent_complete) or 0) >= 100
                for row in rows
            )
            blocks.append({
                "block": block,
                "activity_count": len(rows),
                "currently_completed_activities": currently_completed,
                "activities_with_percent_complete": len(percentages),
                "current_activity_completion_pct": (
                    round(sum(percentages) / len(percentages), 2)
                    if percentages else None
                ),
                "completed_in_period": len(completed_in_period),
                "period_completion_event_pct": round(
                    len(completed_in_period) / len(rows) * 100, 2
                ),
                "completed_activity_ids": [
                    row.activity_id for row in completed_in_period if row.activity_id
                ],
                "activity_ids": [row.activity_id for row in rows if row.activity_id],
                "wbs_object_ids": sorted(wbs_ids_by_block[block]),
                "latest_actual_finish": max(
                    (row.actual_finish_date for row in rows if row.actual_finish_date),
                    default=None,
                ).isoformat() if any(row.actual_finish_date for row in rows) else None,
            })

        blocks.sort(key=lambda block: (
            -block["period_completion_event_pct"],
            -block["completed_in_period"],
            block["block"],
        ))
        highest_progress_pct = max(
            (block["period_completion_event_pct"] for block in blocks), default=0.0
        )
        highest_blocks = [
            block["block"] for block in blocks
            if block["period_completion_event_pct"] == highest_progress_pct
        ]
        lowest_progress_pct = min(
            (block["period_completion_event_pct"] for block in blocks), default=0.0
        )
        lowest_blocks = [
            block["block"] for block in blocks
            if block["period_completion_event_pct"] == lowest_progress_pct
        ]
        any_completion_count = max(
            (block["completed_in_period"] for block in blocks), default=0
        )
        warnings = [
            "True month-over-month percentage progress is unavailable because P6 activity history is not persisted; ranking uses actual activity completions in the period."
        ]
        if any_completion_count == 0 and blocks:
            warnings.append("No block has an activity completion recorded in the requested period.")
        if unassigned:
            warnings.append(
                f"{unassigned} project activities are outside a BLOCK-* WBS branch and are excluded."
            )
        if data_date is None:
            warnings.append(
                "P6 data_date is unavailable; the calendar period is anchored to the server date."
            )
        return {
            "p6_available": True,
            "project_id": project_id,
            "project_name": project.name,
            "period": period,
            "days": days if period == "last_n_days" else None,
            "period_start": period_start.isoformat(),
            "period_end_exclusive": period_end.isoformat(),
            "ranking_basis": "percentage of block activities with an actual completion in period",
            "period_anchor": "p6_data_date" if data_date else "server_date_fallback",
            "historical_percentage_delta_available": False,
            "highest_progress_pct": highest_progress_pct,
            "highest_blocks": highest_blocks,
            "lowest_progress_pct": lowest_progress_pct,
            "lowest_blocks": lowest_blocks,
            "blocks": blocks,
            "excluded_unassigned_activities": unassigned,
            "data_as_of": project.data_date.isoformat() if project.data_date else None,
            "last_synced_at": project.last_synced_at.isoformat() if project.last_synced_at else None,
            "warnings": warnings,
        }

    @classmethod
    def get_daily_activity_completion_trend(
        cls,
        db: Session,
        project_id: str,
        *,
        days: int = 30,
    ) -> dict[str, Any]:
        """Return a daily, event-based progress trend from P6 actual finishes.

        The source database stores only the latest project/activity percentage,
        not historical snapshots. This method therefore reports dated activity
        completion events and never represents them as historical duration
        percent complete.
        """
        if not 1 <= days <= 365:
            raise ValueError("days must be between 1 and 365")

        project = db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        if project is None:
            return {
                "p6_available": False,
                "project_id": project_id,
                "days": days,
                "daily": [],
            }

        data_date = _date_value(project.data_date)
        anchor = data_date or datetime.utcnow().date()
        period_end = anchor + timedelta(days=1)
        period_start = period_end - timedelta(days=days)
        activities = db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == project.p6_object_id
        ).all()
        total_activities = len(activities)

        completions_by_date: dict[date, int] = defaultdict(int)
        completed_before_period = 0
        for activity in activities:
            finish = _date_value(activity.actual_finish_date)
            if finish is None or finish > anchor:
                continue
            if finish < period_start:
                completed_before_period += 1
            else:
                completions_by_date[finish] += 1

        cumulative = completed_before_period
        daily = []
        for offset in range(days):
            day = period_start + timedelta(days=offset)
            completed = completions_by_date.get(day, 0)
            cumulative += completed
            daily.append({
                "date": day.isoformat(),
                "activities_completed": completed,
                "daily_completion_event_pct": (
                    round(completed / total_activities * 100, 2)
                    if total_activities else None
                ),
                "cumulative_activities_with_actual_finish": cumulative,
                "cumulative_activity_finish_pct": (
                    round(cumulative / total_activities * 100, 2)
                    if total_activities else None
                ),
            })

        completion_events = sum(item["activities_completed"] for item in daily)
        warnings = [
            "Historical duration-percent progress is unavailable because P6/DPR snapshots are not persisted; this trend uses activity actual-finish events."
        ]
        if completion_events == 0:
            warnings.append("No activity actual-finish events were recorded in the requested period.")
        if data_date is None:
            warnings.append("P6 data_date is unavailable; the period is anchored to the server date.")
        return {
            "p6_available": True,
            "project_id": project_id,
            "project_name": project.name,
            "days": days,
            "period_start": period_start.isoformat(),
            "period_end_inclusive": anchor.isoformat(),
            "period_anchor": "p6_data_date" if data_date else "server_date_fallback",
            "trend_basis": "activity actual-finish events",
            "historical_duration_progress_available": False,
            "total_activities": total_activities,
            "completion_events_in_period": completion_events,
            "daily": daily,
            "data_as_of": project.data_date.isoformat() if project.data_date else None,
            "last_synced_at": project.last_synced_at.isoformat() if project.last_synced_at else None,
            "warnings": warnings,
        }

    @staticmethod
    def _activity_block(
        activity: models.P6Activity,
        nodes_by_id: dict[int, models.P6WBSNode],
    ) -> tuple[str, int] | None:
        node = nodes_by_id.get(activity.wbs_object_id)
        visited = set()
        while node is not None and node.p6_object_id not in visited:
            visited.add(node.p6_object_id)
            for candidate in (node.wbs_name, node.wbs_code):
                match = re.fullmatch(
                    r"BLOCK[-_ ]*0?([1-9][0-9]*)",
                    str(candidate or "").strip(),
                    re.IGNORECASE,
                )
                if match:
                    return f"BLOCK-{int(match.group(1)):02d}", node.p6_object_id
            node = nodes_by_id.get(node.parent_object_id)
        return None

    @staticmethod
    def _activity_fact(activity: models.P6Activity) -> dict[str, Any]:
        drift_days = (
            (activity.finish_date - activity.baseline_finish_date).days
            if activity.finish_date and activity.baseline_finish_date
            else None
        )
        return {
            "activity_id": activity.activity_id,
            "name": activity.name,
            "status": activity.status,
            "percent_complete": _percentage(activity.percent_complete),
            "start_date": activity.start_date.isoformat() if activity.start_date else None,
            "finish_date": activity.finish_date.isoformat() if activity.finish_date else None,
            "baseline_finish": activity.baseline_finish_date.isoformat() if activity.baseline_finish_date else None,
            "drift_days": drift_days,
            "total_float": activity.total_float,
            "wbs_name": activity.wbs_name,
            "wbs_code": activity.wbs_code,
        }

    @classmethod
    def get_critical_activities(
        cls,
        db: Session,
        project_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        p6 = db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        if p6 is None:
            return []
        rows = db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id,
            models.P6Activity.total_float <= 0,
        ).order_by(
            models.P6Activity.total_float.asc(),
            models.P6Activity.activity_id.asc(),
            models.P6Activity.p6_object_id.asc(),
        ).limit(limit).all()
        return [cls._activity_fact(activity) for activity in rows]

    @classmethod
    def list_by_project_ids(
        cls,
        db: Session,
        project_ids: list[str],
    ) -> dict[str, ScheduleMetrics]:
        if not project_ids:
            return {}
        projects = db.query(models.P6Project).filter(
            models.P6Project.project_id.in_(project_ids)
        ).order_by(
            models.P6Project.project_id.asc(),
            models.P6Project.p6_object_id.asc(),
        ).all()
        return {project.project_id: cls.calculate(project) for project in projects}

    @classmethod
    def get_activity_status_breakdown(cls, db: Session, project_id: str) -> dict[str, int]:
        breakdown: dict[str, int] = {}
        for activity in cls.get_activities(db, project_id):
            status = activity["status"] or "Unknown"
            breakdown[status] = breakdown.get(status, 0) + 1
        return breakdown

    @classmethod
    def get_delayed_activities(
        cls,
        db: Session,
        project_id: str,
        *,
        min_drift_days: int = 1,
        limit: int = 12,
    ) -> list[dict]:
        delayed = []
        for activity in cls.get_activities(db, project_id):
            drift = activity["drift_days"]
            if drift is None:
                continue
            if drift < min_drift_days:
                continue
            delayed.append({
                **activity,
                "drift_days": drift,
                "is_critical": activity["total_float"] is not None and activity["total_float"] <= 0,
            })
        delayed.sort(key=lambda row: (-row["drift_days"], str(row["activity_id"])))
        return delayed[:limit]


def calculate_schedule_metrics(
    p6: object | None,
    *,
    activity_counts: dict[str, int] | None = None,
) -> ScheduleMetrics:
    return ScheduleMetricsService.calculate(p6, activity_counts=activity_counts)


def get_schedule_metrics(db: Session, project_id: str) -> ScheduleMetrics:
    return ScheduleMetricsService.get_by_project_id(db, project_id)
