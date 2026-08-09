"""Renderer-neutral visualization contracts shared by chat and reports.

The contract contains only validated data and presentation semantics.  It never
contains JavaScript callbacks, HTML, URLs, or renderer-specific configuration.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ChartShape = Literal[
    "horizontal_bar", "vertical_bar", "donut", "combo", "radial_progress", "lollipop"
]
SeriesShape = Literal["bar", "line", "donut"]
ValueFormat = Literal["integer", "decimal", "percent", "days"]


SEMANTIC_COLORS = {
    "primary": "#0B74B0",
    "progress": "#75479C",
    "warning": "#BD3861",
    "critical": "#B42318",
    "neutral": "#98A2B3",
    "teal": "#BD3861",
}


class VisualizationSeriesV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    shape: SeriesShape
    values: list[float | int | None]
    semantic_color: str = "primary"
    value_format: ValueFormat = "decimal"
    axis_index: int = Field(default=0, ge=0, le=1)
    item_semantic_colors: list[str] | None = None
    stack_group: str | None = None


class VisualizationSpecV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["visualization.v1"] = "visualization.v1"
    chart_id: str
    chart_type: str
    shape: ChartShape
    title: str
    subtitle: str | None = None
    summary: str
    accessibility_description: str
    categories: list[str]
    series: list[VisualizationSeriesV1]
    x_axis_title: str | None = None
    y_axis_title: str | None = None
    data_as_of: str | None = None
    source_tables: list[str] = Field(default_factory=list)
    data_table: list[dict[str, Any]] = Field(default_factory=list)
    spec_hash: str | None = None

    def transport(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude={"spec_hash"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        payload["spec_hash"] = f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"
        return payload


def daily_completion_spec(data: dict, project_name: str | None = None) -> VisualizationSpecV1 | None:
    rows = data.get("daily") or []
    if not rows:
        return None
    name = project_name or data.get("project_name") or "Project"
    total_events = int(data.get("completion_events_in_period") or 0)
    title = f"{name} — Daily Completion Trend"
    subtitle = (
        f"{total_events} activity actual-finish events • "
        f"{data.get('period_start')} to {data.get('period_end_inclusive')}"
    )
    cumulative = [row.get("cumulative_activity_finish_pct") for row in rows]
    latest = next((value for value in reversed(cumulative) if value is not None), None)
    summary = f"{total_events} activities recorded an actual finish during the period."
    if latest is not None:
        summary += f" Cumulative activity finishes reached {latest}% of project activities."
    table = [
        {
            "date": str(row.get("date")),
            "completed_activities": row.get("activities_completed") or 0,
            "cumulative_activity_finish_pct": row.get("cumulative_activity_finish_pct"),
        }
        for row in rows
    ]
    return VisualizationSpecV1(
        chart_id="project.daily-completion",
        chart_type="daily_completion_trend",
        shape="combo",
        title=title,
        subtitle=subtitle,
        summary=summary,
        accessibility_description=(
            f"{title}. Bars show daily completed activities and the line shows cumulative "
            "activity finish percentage. This is event-based and is not historical duration progress."
        ),
        categories=[str(row.get("date")) for row in rows],
        series=[
            VisualizationSeriesV1(
                name="Completed activities",
                shape="bar",
                values=[row.get("activities_completed") or 0 for row in rows],
                semantic_color="teal",
                value_format="integer",
            ),
            VisualizationSeriesV1(
                name="Cumulative activity finish",
                shape="line",
                values=cumulative,
                semantic_color="primary",
                value_format="percent",
                axis_index=1,
            ),
        ],
        x_axis_title="Date",
        y_axis_title="Activities / cumulative percent",
        data_as_of=str(data.get("data_as_of")) if data.get("data_as_of") else None,
        source_tables=list(data.get("sources") or ["p6_project", "p6_activity"]),
        data_table=table,
    )


def planned_vs_actual_progress_spec(
    data: dict,
    project_name: str | None = None,
) -> VisualizationSpecV1 | None:
    rows = data.get("timeline") or []
    if not rows:
        return None
    name = project_name or data.get("project_name") or "Project"
    planned = data.get("current_planned_activity_finish_pct")
    actual = data.get("current_actual_activity_finish_pct")
    variance = data.get("current_variance_pct_points")
    title = f"{name} - Planned vs Actual Activity Completion"
    subtitle = (
        "Cumulative activity finish S-curve through "
        f"{data.get('period_end_inclusive') or data.get('data_as_of') or 'latest P6 cutoff'}"
    )
    summary = f"Planned completion is {planned}% and actual completion is {actual}% as of the cutoff."
    if variance is not None:
        direction = "ahead of" if variance > 0 else "behind" if variance < 0 else "equal to"
        summary += f" Actual is {abs(variance)} percentage points {direction} plan."
    return VisualizationSpecV1(
        chart_id="project.planned-vs-actual-activity-progress",
        chart_type="planned_vs_actual_progress",
        shape="combo",
        title=title,
        subtitle=subtitle,
        summary=summary,
        accessibility_description=(
            f"{title}. Two lines compare cumulative activities planned to finish with activities "
            "that actually finished. This is not historical duration-percent progress."
        ),
        categories=[str(row["date"]) for row in rows],
        series=[
            VisualizationSeriesV1(
                name="Planned activity finishes",
                shape="line",
                values=[row.get("planned_activity_finish_pct") for row in rows],
                semantic_color="primary",
                value_format="percent",
            ),
            VisualizationSeriesV1(
                name="Actual activity finishes",
                shape="line",
                values=[row.get("actual_activity_finish_pct") for row in rows],
                semantic_color="progress",
                value_format="percent",
            ),
        ],
        x_axis_title="Date",
        y_axis_title="Cumulative activities completed (%)",
        data_as_of=str(data.get("data_as_of")) if data.get("data_as_of") else None,
        source_tables=list(data.get("sources") or ["p6_project", "p6_activity"]),
        data_table=[{
            "date": row["date"],
            "planned_activity_finish_pct": row.get("planned_activity_finish_pct"),
            "actual_activity_finish_pct": row.get("actual_activity_finish_pct"),
            "variance_pct_points": row.get("variance_pct_points"),
        } for row in rows],
    )


def activity_status_spec(data: dict, project_name: str | None = None) -> VisualizationSpecV1 | None:
    breakdown = data.get("breakdown") or {}
    rows = [
        (str(status), int(count or 0))
        for status, count in breakdown.items()
        if int(count or 0) > 0
    ]
    if not rows:
        return None
    preferred_order = {"completed": 0, "in progress": 1, "not started": 2}
    rows.sort(key=lambda item: (preferred_order.get(item[0].strip().casefold(), 3), item[0]))
    name = project_name or data.get("project_name") or "Project"
    total = int(data.get("total") or sum(value for _, value in rows))
    colors = []
    for status, _value in rows:
        normalized = status.strip().casefold()
        colors.append(
            "progress" if "complet" in normalized
            else "primary" if "progress" in normalized
            else "neutral" if "not start" in normalized
            else "warning"
        )
    title = f"{name} - Activity Status"
    return VisualizationSpecV1(
        chart_id="project.activity-status",
        chart_type="activity_status",
        shape="donut",
        title=title,
        subtitle=f"Current distribution across {total:,} activities",
        summary="Activity status composition from the latest synchronized P6 schedule.",
        accessibility_description=(
            f"{title}. Donut chart showing "
            + ", ".join(f"{status}: {value}" for status, value in rows)
            + "."
        ),
        categories=[status for status, _value in rows],
        series=[VisualizationSeriesV1(
            name="Activities",
            shape="donut",
            values=[value for _status, value in rows],
            semantic_color="primary",
            value_format="integer",
            item_semantic_colors=colors,
        )],
        data_as_of=str(data.get("data_as_of")) if data.get("data_as_of") else None,
        source_tables=list(data.get("sources") or ["p6_activity"]),
        data_table=[{"status": status, "activities": value} for status, value in rows],
    )


def block_progress_spec(data: dict, project_name: str | None = None, limit: int = 16) -> VisualizationSpecV1 | None:
    blocks = [
        row for row in (data.get("blocks") or [])
        if row.get("current_activity_completion_pct") is not None
    ]
    if not blocks:
        return None
    blocks.sort(key=lambda row: (-float(row["current_activity_completion_pct"]), str(row["block"])))
    if len(blocks) > limit and limit >= 4:
        high_count = (limit + 1) // 2
        low_count = limit - high_count
        blocks = [*blocks[:high_count], *blocks[-low_count:]]
    else:
        blocks = blocks[:limit]
    name = project_name or data.get("project_name") or "Project"
    title = f"{name} — Block Progress Snapshot"
    subtitle = f"Current average activity completion • data as of {data.get('data_as_of') or 'latest sync'}"
    values = [float(row["current_activity_completion_pct"]) for row in blocks]
    high, low = blocks[0], blocks[-1]
    return VisualizationSpecV1(
        chart_id="project.block-progress",
        chart_type="block_progress",
        shape="horizontal_bar",
        title=title,
        subtitle=subtitle,
        summary=(
            f"{high['block']} is highest at {high['current_activity_completion_pct']}%; "
            f"{low['block']} is lowest at {low['current_activity_completion_pct']}%."
        ),
        accessibility_description=f"{title}. Horizontal bars compare current average activity completion by block.",
        categories=[str(row["block"]) for row in blocks],
        series=[VisualizationSeriesV1(
            name="Average activity completion",
            shape="bar",
            values=values,
            semantic_color="primary",
            value_format="percent",
            item_semantic_colors=[
                "progress" if value >= 75 else "primary" if value >= 40 else "warning"
                for value in values
            ],
        )],
        x_axis_title="Average activity completion",
        data_as_of=str(data.get("data_as_of")) if data.get("data_as_of") else None,
        source_tables=list(data.get("sources") or ["p6_project", "p6_activity", "p6_wbs_node"]),
        data_table=[{
            "block": row["block"],
            "current_activity_completion_pct": row["current_activity_completion_pct"],
            "activities": row.get("activity_count"),
            "completed_this_month": row.get("completed_in_period"),
        } for row in blocks],
    )


def project_progress_spec(rows: list[dict], *, title: str = "Portfolio Progress Comparison") -> VisualizationSpecV1 | None:
    usable = [row for row in rows if row.get("progress_pct") is not None]
    usable.sort(key=lambda row: (-float(row["progress_pct"]), str(row.get("project_name") or "")))
    usable = usable[:12]
    if not usable:
        return None
    single_project = len(usable) == 1
    return VisualizationSpecV1(
        chart_id="portfolio.project-progress",
        chart_type="project_comparison",
        shape="radial_progress" if len(usable) <= 4 else "horizontal_bar",
        title=title,
        subtitle=(
            "Authoritative current P6 duration progress"
            if single_project else "Top projects by authoritative current P6 progress"
        ),
        summary=(
            f"Current authoritative P6 duration progress is {float(usable[0]['progress_pct']):.1f}%."
            if single_project else f"Comparison of authoritative current progress for {len(usable)} projects."
        ),
        accessibility_description=(
            f"{title}. Gauge shows current P6 duration progress."
            if single_project else f"{title}. Bars compare current P6 progress by project."
        ),
        categories=[str(row.get("project_name") or row.get("project_id")) for row in usable],
        series=[VisualizationSeriesV1(
            name="Progress",
            shape="bar",
            values=[float(row["progress_pct"]) for row in usable],
            semantic_color="primary",
            value_format="percent",
        )],
        x_axis_title="Progress",
        source_tables=["project_mapping", "p6_project"],
        data_table=[{
            "project_name": row.get("project_name") or row.get("project_id"),
            "progress_pct": row.get("progress_pct"),
        } for row in usable],
    )


def project_capacity_comparison_spec(rows: list[dict]) -> VisualizationSpecV1 | None:
    usable = [
        row for row in rows
        if row.get("project_name") and row.get("capacity_mwac") is not None
    ]
    if len(usable) < 2:
        return None
    values = [float(row["capacity_mwac"]) for row in usable]
    largest = max(usable, key=lambda row: float(row["capacity_mwac"]))
    return VisualizationSpecV1(
        chart_id="comparison.installed-capacity",
        chart_type="project_capacity_comparison",
        shape="vertical_bar",
        title="Installed Capacity Comparison",
        subtitle="Mapped project capacity; independent of P6 schedule availability",
        summary=(
            f"{largest['project_name']} has the largest mapped capacity at "
            f"{float(largest['capacity_mwac']):g} MW AC."
        ),
        accessibility_description="Vertical bars compare mapped project capacity in megawatts AC.",
        categories=[str(row["project_name"]) for row in usable],
        series=[VisualizationSeriesV1(
            name="Capacity",
            shape="bar",
            values=values,
            semantic_color="primary",
            value_format="decimal",
        )],
        x_axis_title="Project",
        y_axis_title="Capacity (MW AC)",
        source_tables=["project_mapping"],
        data_table=[{
            "project_id": row.get("project_id"),
            "project_name": row["project_name"],
            "capacity_mwac": row.get("capacity_mwac"),
            "location_count": row.get("location_count"),
            "cluster": row.get("cluster"),
            "p6_available": row.get("p6_available", False),
        } for row in usable],
    )


def activity_composition_spec(rows: list[dict]) -> VisualizationSpecV1 | None:
    usable = [
        row for row in rows
        if row.get("project_name") and row.get("p6_available", True)
    ]
    if not usable:
        return None
    categories = [str(row["project_name"]) for row in usable]
    return VisualizationSpecV1(
        chart_id="comparison.activity-composition",
        chart_type="project_activity_composition",
        shape="horizontal_bar",
        title="Activity Composition",
        subtitle="Completed, in-progress, and not-started activity counts",
        summary="The activity mix shows both achieved scope and the breadth of the remaining workfront.",
        accessibility_description="Stacked horizontal bars compare completed, in-progress, and not-started activity counts for each project.",
        categories=categories,
        series=[
            VisualizationSeriesV1(
                name="Completed", shape="bar",
                values=[int(row.get("completed_activities") or 0) for row in usable],
                semantic_color="progress", value_format="integer", stack_group="activities",
            ),
            VisualizationSeriesV1(
                name="In progress", shape="bar",
                values=[int(row.get("in_progress_activities") or 0) for row in usable],
                semantic_color="primary", value_format="integer", stack_group="activities",
            ),
            VisualizationSeriesV1(
                name="Not started", shape="bar",
                values=[int(row.get("not_started_activities") or 0) for row in usable],
                semantic_color="neutral", value_format="integer", stack_group="activities",
            ),
        ],
        x_axis_title="Activities",
        source_tables=["p6_project", "p6_activity"],
        data_table=[{
            "project_name": row["project_name"],
            "completed": row.get("completed_activities") or 0,
            "in_progress": row.get("in_progress_activities") or 0,
            "not_started": row.get("not_started_activities") or 0,
            "data_as_of": row.get("data_as_of"),
        } for row in usable],
    )


def duration_comparison_spec(rows: list[dict]) -> VisualizationSpecV1 | None:
    usable = [
        row for row in rows
        if any(row.get(key) is not None for key in ("planned_duration", "actual_duration", "remaining_duration"))
    ]
    if not usable:
        return None
    return VisualizationSpecV1(
        chart_id="comparison.duration-profile",
        chart_type="project_duration_comparison",
        shape="vertical_bar",
        title="Duration Profile",
        subtitle="Planned, actual, and remaining duration from the current P6 extract",
        summary="Duration measures expose the scale of executed and remaining schedule work; they are not cost or manpower measures.",
        accessibility_description="Grouped horizontal bars compare planned, actual, and remaining duration in hours for each project.",
        categories=[str(row["project_name"]) for row in usable],
        series=[
            VisualizationSeriesV1(
                name="Planned", shape="bar",
                values=[row.get("planned_duration") for row in usable],
                semantic_color="neutral", value_format="integer",
            ),
            VisualizationSeriesV1(
                name="Actual", shape="bar",
                values=[row.get("actual_duration") for row in usable],
                semantic_color="primary", value_format="integer",
            ),
            VisualizationSeriesV1(
                name="Remaining", shape="bar",
                values=[row.get("remaining_duration") for row in usable],
                semantic_color="warning", value_format="integer",
            ),
        ],
        x_axis_title="Duration (hours)",
        source_tables=["p6_project"],
        data_table=[{
            "project_name": row["project_name"],
            "planned_duration_hours": row.get("planned_duration"),
            "actual_duration_hours": row.get("actual_duration"),
            "remaining_duration_hours": row.get("remaining_duration"),
            "data_as_of": row.get("data_as_of"),
        } for row in usable],
    )


def baseline_slip_spec(rows: list[dict]) -> VisualizationSpecV1 | None:
    usable = [row for row in rows if row.get("baseline_slip_days") is not None]
    if not usable:
        return None
    values = [int(row["baseline_slip_days"]) for row in usable]
    return VisualizationSpecV1(
        chart_id="comparison.baseline-slip",
        chart_type="project_baseline_slip",
        shape="lollipop",
        title="Forecast Finish vs Baseline",
        subtitle="Direct calendar-day difference between current forecast and baseline finish",
        summary="Positive values indicate the current forecast finishes after the baseline; negative values indicate an earlier forecast.",
        accessibility_description="Horizontal bars compare forecast finish slippage against baseline finish in calendar days.",
        categories=[str(row["project_name"]) for row in usable],
        series=[VisualizationSeriesV1(
            name="Baseline slip",
            shape="bar",
            values=values,
            semantic_color="critical",
            value_format="days",
            item_semantic_colors=["critical" if value > 0 else "progress" for value in values],
        )],
        x_axis_title="Calendar days",
        source_tables=["p6_project"],
        data_table=[{
            "project_name": row["project_name"],
            "baseline_finish": row.get("baseline_finish"),
            "forecast_finish": row.get("forecast_finish"),
            "baseline_slip_days": row.get("baseline_slip_days"),
            "data_as_of": row.get("data_as_of"),
        } for row in usable],
    )


def portfolio_status_spec(counts: dict, data_as_of: str | None = None) -> VisualizationSpecV1 | None:
    buckets = [
        ("Delayed", int(counts.get("delayed", 0)), "critical"),
        ("On track", int(counts.get("on_track", 0)), "progress"),
        ("Completed", int(counts.get("completed", 0)), "primary"),
        ("P6 unavailable", int(counts.get("p6_unavailable", 0)), "neutral"),
    ]
    buckets = [bucket for bucket in buckets if bucket[1] > 0]
    if not buckets:
        return None
    total = sum(value for _, value, _ in buckets)
    return VisualizationSpecV1(
        chart_id="portfolio.schedule-status",
        chart_type="portfolio_schedule_status",
        shape="donut",
        title="Portfolio Schedule Status",
        subtitle="Current status distribution at the latest synchronized cutoff",
        summary=f"{total} projects are represented in the current schedule-status distribution.",
        accessibility_description="Portfolio schedule status distribution by delayed, on-track, completed, and unavailable projects.",
        categories=[label for label, _, _ in buckets],
        series=[VisualizationSeriesV1(
            name="Projects",
            shape="donut",
            values=[value for _, value, _ in buckets],
            semantic_color="primary",
            value_format="integer",
            item_semantic_colors=[color for _, _, color in buckets],
        )],
        data_as_of=data_as_of,
        source_tables=["project_mapping", "p6_project"],
        data_table=[{"status": label, "projects": value} for label, value, _ in buckets],
    )


def semantic_color(name: str) -> str:
    return SEMANTIC_COLORS.get(name, SEMANTIC_COLORS["primary"])
