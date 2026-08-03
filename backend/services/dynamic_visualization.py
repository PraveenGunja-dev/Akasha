"""Governed dynamic visualization queries and renderer-neutral V2 specs.

The model may select only catalog identifiers. Data retrieval, aggregation,
authorization scope, chart selection, and the final data-bearing specification
remain deterministic backend responsibilities.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import math
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from services.capacity_milestone_service import CapacityMilestoneService
from services.chart_spec_service import ChartSpecService
from services.project_catalog_service import ProjectCatalogService
from services.quality_analytics_service import QualityAnalyticsService
from services.schedule_metrics_service import ScheduleMetricsService
from services import transmission_service


DatasetId = Literal[
    "p6.delayed_activities",
    "p6.block_progress",
    "p6.daily_completion",
    "p6.planned_actual",
    "sap.material_fulfillment",
    "sap.vendor_fulfillment",
    "transmission.lines",
    "portfolio.risk",
    "portfolio.capacity_quality",
    "portfolio.procurement_schedule",
]
VisualizationShapeV2 = Literal[
    "auto", "line", "bar", "horizontal_bar", "stacked_bar",
    "scatter", "heatmap", "waterfall", "donut",
]
Aggregation = Literal["sum", "avg", "min", "max", "count"]
FilterOperator = Literal["eq", "neq", "in", "gte", "lte", "contains"]
SortDirection = Literal["asc", "desc"]
FieldType = Literal["categorical", "temporal", "quantitative", "boolean"]
ValueFormat = Literal["integer", "decimal", "percent", "days", "mw"]


class VisualizationMetricRequestV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: str = Field(min_length=1, max_length=80)
    aggregation: Aggregation | None = None


class VisualizationFilterV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: str = Field(min_length=1, max_length=80)
    operator: FilterOperator
    value: str | int | float | bool | list[str | int | float | bool]

    @model_validator(mode="after")
    def validate_operator_value(self):
        if self.operator == "in" and not isinstance(self.value, list):
            raise ValueError("The in operator requires a list value")
        if self.operator != "in" and isinstance(self.value, list):
            raise ValueError(f"The {self.operator} operator requires a scalar value")
        return self


class VisualizationSortV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: str = Field(min_length=1, max_length=80)
    direction: SortDirection = "asc"


class VisualizationQueryV2(BaseModel):
    """Untrusted model-authored request containing catalog identifiers only."""

    model_config = ConfigDict(extra="forbid", strict=True)

    dataset_id: DatasetId
    metrics: list[VisualizationMetricRequestV2] = Field(min_length=1, max_length=4)
    dimensions: list[str] = Field(default_factory=list, max_length=2)
    filters: list[VisualizationFilterV2] = Field(default_factory=list, max_length=8)
    sort: list[VisualizationSortV2] = Field(default_factory=list, max_length=3)
    preferred_shape: VisualizationShapeV2 = "auto"
    title: str | None = Field(default=None, min_length=1, max_length=140)
    limit: int = Field(default=100, ge=1, le=500)

    @field_validator("dimensions")
    @classmethod
    def distinct_dimensions(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("dimensions must be distinct")
        return value

    @field_validator("title")
    @classmethod
    def safe_title(cls, value: str | None) -> str | None:
        if value is not None and (
            any(character in value for character in "<>\x00")
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("title contains unsupported characters")
        return value

    @model_validator(mode="after")
    def distinct_metrics(self):
        fields = [metric.field for metric in self.metrics]
        if len(set(fields)) != len(fields):
            raise ValueError("metric fields must be distinct")
        return self


class VisualizationChannelV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: str
    label: str
    field_type: FieldType
    value_format: ValueFormat | None = None
    unit: str | None = None
    axis_index: int = Field(default=0, ge=0, le=1)


class VisualizationEncodingV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    x: VisualizationChannelV2 | None = None
    y: list[VisualizationChannelV2] = Field(default_factory=list, max_length=4)
    color: VisualizationChannelV2 | None = None
    label: VisualizationChannelV2 | None = None


class VisualizationSpecV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    schema_version: Literal["visualization.v2"] = "visualization.v2"
    chart_id: str
    chart_type: str
    shape: Literal[
        "line", "bar", "horizontal_bar", "stacked_bar",
        "scatter", "heatmap", "waterfall", "donut",
    ]
    title: str
    subtitle: str | None = None
    summary: str
    accessibility_description: str
    encoding: VisualizationEncodingV2
    data: list[dict[str, str | int | float | bool | None]] = Field(max_length=500)
    data_as_of: str | None = None
    source_tables: list[str] = Field(default_factory=list, max_length=20)
    spec_hash: str | None = None

    @model_validator(mode="after")
    def bound_transport(self):
        for row in self.data:
            if any(len(key) > 80 for key in row):
                raise ValueError("data field names are too long")
            if any(isinstance(value, str) and len(value) > 500 for value in row.values()):
                raise ValueError("data labels are too long")
        if len(json.dumps(self.data, default=str, separators=(",", ":"))) > 250_000:
            raise ValueError("visualization data exceeds the transport limit")
        return self

    def transport(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude={"spec_hash"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        payload["spec_hash"] = f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"
        return payload


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    field: str
    label: str
    field_type: FieldType
    role: Literal["dimension", "metric"]
    unit: str | None = None
    value_format: ValueFormat | None = None
    aggregations: tuple[Aggregation, ...] = ()
    default_aggregation: Aggregation | None = None
    filterable: bool = True
    additive: bool = False


@dataclass(frozen=True, slots=True)
class DatasetResult:
    rows: list[dict[str, Any]]
    source_tables: tuple[str, ...]
    data_as_of: str | None = None


Loader = Callable[[Session, str | None, list[str], int, int], DatasetResult]


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    dataset_id: str
    title: str
    fields: dict[str, FieldDefinition]
    loader: Loader
    requires_project: bool = False
    allowed_shapes: tuple[str, ...] = (
        "line", "bar", "horizontal_bar", "stacked_bar",
        "scatter", "heatmap", "waterfall", "donut",
    )


def _dimension(field: str, label: str, field_type: FieldType = "categorical") -> FieldDefinition:
    return FieldDefinition(
        field=field,
        label=label,
        field_type=field_type,
        role="dimension",
    )


def _metric(
    field: str,
    label: str,
    *,
    value_format: ValueFormat = "decimal",
    unit: str | None = None,
    aggregations: tuple[Aggregation, ...] = ("sum", "avg", "min", "max"),
    default: Aggregation = "sum",
    additive: bool = False,
) -> FieldDefinition:
    return FieldDefinition(
        field=field,
        label=label,
        field_type="quantitative",
        role="metric",
        unit=unit,
        value_format=value_format,
        aggregations=aggregations,
        default_aggregation=default,
        filterable=True,
        additive=additive,
    )


def _minimum_date(values: list[str | None]) -> str | None:
    available = [str(value) for value in values if value]
    return min(available) if available else None


def _require_compatible_freshness(values: list[str | None], relationship: str) -> None:
    parsed = []
    for value in values:
        if not value:
            continue
        try:
            parsed.append(datetime.fromisoformat(str(value).replace("Z", "+00:00")).date())
        except ValueError:
            continue
    if parsed and (max(parsed) - min(parsed)).days > 45:
        raise VisualizationQueryError(
            f"{relationship} sources are more than 45 days apart and cannot be compared reliably."
        )


def _load_delayed(db: Session, project_id: str | None, _ids: list[str], limit: int, _days: int) -> DatasetResult:
    if not project_id:
        return DatasetResult([], ("p6_activity",))
    project = ProjectCatalogService.get_by_project_id(db, project_id)
    schedule = ScheduleMetricsService.get_by_project_id(db, project_id)
    activities = ScheduleMetricsService.get_delayed_activities(db, project_id, limit=min(500, limit))
    rows = []
    for row in activities:
        finish = str(row.get("finish_date") or "")
        rows.append({
            "activity": row.get("name") or row.get("activity_id") or "Unknown",
            "block": row.get("wbs_name") or row.get("wbs_code") or "Unknown",
            "finish_month": finish[:7] if len(finish) >= 7 else "Unknown",
            "status": row.get("status") or "Unknown",
            "drift_days": row.get("drift_days"),
            "delayed_activity_count": 1,
            "project_name": project.display_name if project else project_id,
        })
    return DatasetResult(rows, ("p6_activity", "p6_wbs_node"), schedule.freshness.get("data_as_of"))


def _load_blocks(db: Session, project_id: str | None, _ids: list[str], limit: int, _days: int) -> DatasetResult:
    if not project_id:
        return DatasetResult([], ("p6_project", "p6_activity", "p6_wbs_node"))
    data = ChartSpecService.block_progress(db, project_id)
    rows = [{
        "block": row.get("block"),
        "progress_pct": row.get("current_activity_completion_pct"),
        "activity_count": row.get("activity_count"),
        "completed_in_period": row.get("completed_in_period"),
    } for row in (data.get("blocks") or [])[:limit]]
    return DatasetResult(rows, tuple(data.get("sources") or ()), data.get("data_as_of"))


def _load_daily(db: Session, project_id: str | None, _ids: list[str], _limit: int, days: int) -> DatasetResult:
    if not project_id:
        return DatasetResult([], ("p6_project", "p6_activity"))
    data = ChartSpecService.daily_completion_trend(db, project_id, days=days)
    return DatasetResult(list(data.get("daily") or []), tuple(data.get("sources") or ()), data.get("data_as_of"))


def _load_planned_actual(db: Session, project_id: str | None, _ids: list[str], _limit: int, _days: int) -> DatasetResult:
    if not project_id:
        return DatasetResult([], ("p6_project", "p6_activity"))
    data = ChartSpecService.planned_vs_actual_progress(db, project_id)
    return DatasetResult(list(data.get("timeline") or []), tuple(data.get("sources") or ()), data.get("data_as_of"))


def _load_materials(db: Session, project_id: str | None, _ids: list[str], limit: int, _days: int) -> DatasetResult:
    if not project_id:
        return DatasetResult([], ("mt_poamount",))
    data = ChartSpecService.sap_po_fulfillment(db, project_id, limit=limit)
    rows = []
    for row in data.get("rows") or []:
        ordered = float(row.get("ordered") or 0)
        rows.append({
            "material": row.get("name") or "Unknown",
            "ordered_quantity": ordered,
            "delivered_quantity": float(row.get("delivered") or 0),
            "pending_quantity": float(row.get("pending") or 0),
            "fulfillment_pct": round(float(row.get("delivered") or 0) / ordered * 100, 2) if ordered else 0,
        })
    freshness = data.get("freshness") or {}
    return DatasetResult(rows, tuple(data.get("sources") or ("mt_poamount",)), freshness.get("data_as_of"))


def _load_vendors(db: Session, project_id: str | None, _ids: list[str], limit: int, _days: int) -> DatasetResult:
    if not project_id:
        return DatasetResult([], ("mt_poamount",))
    data = ChartSpecService.vendor_performance(db, project_id, limit=limit)
    rows = [{
        "vendor": row.get("name") or "Unknown",
        "ordered_quantity": float(row.get("ordered") or 0),
        "delivered_quantity": float(row.get("delivered") or 0),
        "pending_quantity": float(row.get("pending") or 0),
    } for row in data.get("rows") or []]
    freshness = data.get("freshness") or {}
    return DatasetResult(rows, tuple(data.get("sources") or ("mt_poamount",)), freshness.get("data_as_of"))


def _load_transmission(db: Session, project_id: str | None, _ids: list[str], limit: int, _days: int) -> DatasetResult:
    if project_id:
        data = transmission_service.project_status(db, project_id)
        lines = data.get("lines") or []
        data_as_of = data.get("last_synced_at")
    else:
        lines = [transmission_service.edge_dict(edge) for edge in transmission_service.latest_physical_edges(db)]
        data_as_of = transmission_service.freshness(db).get("synced_at")
    rows = [{
        "line": row.get("edge_id") or "Unknown",
        "region": row.get("region") or "Unknown",
        "status": row.get("canonical_status") or "unknown",
        "average_progress_pct": row.get("avg_progress"),
        "days_delayed": row.get("days_delayed"),
        "line_count": 1,
    } for row in lines[:limit]]
    return DatasetResult(rows, ("tc_network_edge",), data_as_of)


def _load_risk(db: Session, _project_id: str | None, _ids: list[str], limit: int, _days: int) -> DatasetResult:
    data = ChartSpecService.portfolio_risk(db, limit=limit)
    return DatasetResult(list(data.get("projects") or []), tuple(data.get("sources") or ()))


def _selected_project_ids(db: Session, project_id: str | None, project_ids: list[str], limit: int) -> list[str]:
    if project_id:
        return [project_id]
    if project_ids:
        return list(dict.fromkeys(project_ids))[:limit]
    return [
        project.project_id for project in ProjectCatalogService.list_projects(db)
        if project.project_id
    ][:limit]


def _load_capacity_quality(
    db: Session, project_id: str | None, project_ids: list[str], limit: int, _days: int,
) -> DatasetResult:
    selected = set(_selected_project_ids(db, project_id, project_ids, limit))
    capacity = CapacityMilestoneService.get_portfolio_overview(db)
    quality = {
        snapshot.project_id: snapshot
        for snapshot in QualityAnalyticsService.project_snapshots(db)
        if snapshot.project_id
    }
    rows = []
    freshness = []
    for row in capacity.get("projects") or []:
        identity = row.get("project_id")
        if selected and identity not in selected:
            continue
        snapshot = quality.get(identity)
        capacity_date = (row.get("freshness") or {}).get("data_as_of")
        quality_date = snapshot.provenance.data_as_of if snapshot else None
        _require_compatible_freshness(
            [capacity_date, quality_date],
            f"Capacity and quality data for {row.get('project_name') or identity}",
        )
        rows.append({
            "project_name": row.get("project_name") or identity,
            "total_capacity_mw": row.get("total_capacity"),
            "cod_capacity_mw": row.get("cod_mw"),
            "open_quality_issues": snapshot.open_ncs if snapshot else None,
            "critical_quality_issues": snapshot.critical_open if snapshot else None,
            "quality_score": snapshot.quality_score if snapshot else None,
        })
        freshness.append(capacity_date)
        if snapshot:
            freshness.append(quality_date)
    return DatasetResult(
        rows[:limit],
        ("project_mapping", "p6_project", "p6_activity", "pulse_nc", "pulse_rfi"),
        _minimum_date(freshness),
    )


def _load_procurement_schedule(
    db: Session, project_id: str | None, project_ids: list[str], limit: int, _days: int,
) -> DatasetResult:
    selected = _selected_project_ids(db, project_id, project_ids, min(limit, 20))
    schedule_rows = {
        row["project_id"]: row
        for row in ChartSpecService.project_comparison(db, selected).get("projects") or []
    }
    rows = []
    freshness = []
    for identity in selected:
        schedule = schedule_rows.get(identity)
        if not schedule:
            continue
        procurement = ChartSpecService.sap_po_fulfillment(db, identity, limit=1)
        rows.append({
            "project_name": schedule.get("project_name") or identity,
            "procurement_fulfillment_pct": procurement.get("fulfillment_pct"),
            "schedule_delay_days": schedule.get("baseline_slip_days"),
            "progress_pct": schedule.get("progress_pct"),
        })
        freshness.append(schedule.get("data_as_of"))
        procurement_freshness = procurement.get("freshness")
        procurement_date = (
            procurement_freshness.get("data_as_of")
            if isinstance(procurement_freshness, dict)
            else procurement_freshness
        )
        _require_compatible_freshness(
            [schedule.get("data_as_of"), procurement_date],
            f"Procurement and schedule data for {schedule.get('project_name') or identity}",
        )
        freshness.append(procurement_date)
    return DatasetResult(
        rows,
        ("project_mapping", "p6_project", "mt_poamount"),
        _minimum_date(freshness),
    )


QUANTITY_FIELDS = {
    "ordered_quantity": _metric("ordered_quantity", "Ordered quantity", additive=True),
    "delivered_quantity": _metric("delivered_quantity", "Delivered quantity", additive=True),
    "pending_quantity": _metric("pending_quantity", "Pending quantity", additive=True),
}


DATASET_CATALOG: dict[str, DatasetDefinition] = {
    "p6.delayed_activities": DatasetDefinition(
        "p6.delayed_activities", "Delayed Activities",
        {
            "activity": _dimension("activity", "Activity"),
            "block": _dimension("block", "Block"),
            "finish_month": _dimension("finish_month", "Finish month", "temporal"),
            "status": _dimension("status", "Status"),
            "project_name": _dimension("project_name", "Project"),
            "drift_days": _metric("drift_days", "Delay", value_format="days", unit="days", default="avg"),
            "delayed_activity_count": _metric("delayed_activity_count", "Delayed activities", value_format="integer", additive=True),
        },
        _load_delayed, requires_project=True,
    ),
    "p6.block_progress": DatasetDefinition(
        "p6.block_progress", "Block Progress",
        {
            "block": _dimension("block", "Block"),
            "progress_pct": _metric("progress_pct", "Progress", value_format="percent", unit="percent", default="avg"),
            "activity_count": _metric("activity_count", "Activities", value_format="integer", additive=True),
            "completed_in_period": _metric("completed_in_period", "Completed in period", value_format="integer", additive=True),
        },
        _load_blocks, requires_project=True,
    ),
    "p6.daily_completion": DatasetDefinition(
        "p6.daily_completion", "Daily Activity Completion",
        {
            "date": _dimension("date", "Date", "temporal"),
            "activities_completed": _metric("activities_completed", "Completed activities", value_format="integer", additive=True),
            "cumulative_activity_finish_pct": _metric("cumulative_activity_finish_pct", "Cumulative completion", value_format="percent", unit="percent", default="max"),
        },
        _load_daily, requires_project=True, allowed_shapes=("line", "bar", "stacked_bar"),
    ),
    "p6.planned_actual": DatasetDefinition(
        "p6.planned_actual", "Planned vs Actual Activity Completion",
        {
            "date": _dimension("date", "Date", "temporal"),
            "planned_activity_finish_pct": _metric("planned_activity_finish_pct", "Planned", value_format="percent", unit="percent", default="max"),
            "actual_activity_finish_pct": _metric("actual_activity_finish_pct", "Actual", value_format="percent", unit="percent", default="max"),
            "variance_pct_points": _metric("variance_pct_points", "Variance", value_format="percent", unit="percentage points", default="avg", additive=True),
        },
        _load_planned_actual, requires_project=True, allowed_shapes=("line", "bar", "waterfall"),
    ),
    "sap.material_fulfillment": DatasetDefinition(
        "sap.material_fulfillment", "Material Fulfilment",
        {"material": _dimension("material", "Material"), **QUANTITY_FIELDS,
         "fulfillment_pct": _metric("fulfillment_pct", "Fulfilment", value_format="percent", unit="percent", default="avg")},
        _load_materials, requires_project=True,
    ),
    "sap.vendor_fulfillment": DatasetDefinition(
        "sap.vendor_fulfillment", "Vendor Fulfilment",
        {"vendor": _dimension("vendor", "Vendor"), **QUANTITY_FIELDS},
        _load_vendors, requires_project=True,
    ),
    "transmission.lines": DatasetDefinition(
        "transmission.lines", "Transmission Lines",
        {
            "line": _dimension("line", "Line"),
            "region": _dimension("region", "Region"),
            "status": _dimension("status", "Status"),
            "average_progress_pct": _metric("average_progress_pct", "Average progress", value_format="percent", unit="percent", default="avg"),
            "days_delayed": _metric("days_delayed", "Delay", value_format="days", unit="days", default="avg"),
            "line_count": _metric("line_count", "Lines", value_format="integer", additive=True),
        },
        _load_transmission,
    ),
    "portfolio.risk": DatasetDefinition(
        "portfolio.risk", "Portfolio Risk",
        {
            "project_name": _dimension("project_name", "Project"),
            "risk_tier": _dimension("risk_tier", "Risk tier"),
            "risk_level": _metric("risk_level", "Risk level", value_format="integer", default="max"),
        },
        _load_risk,
    ),
    "portfolio.capacity_quality": DatasetDefinition(
        "portfolio.capacity_quality", "Capacity and Quality",
        {
            "project_name": _dimension("project_name", "Project"),
            "total_capacity_mw": _metric("total_capacity_mw", "Total capacity", value_format="mw", unit="MW"),
            "cod_capacity_mw": _metric("cod_capacity_mw", "COD capacity", value_format="mw", unit="MW"),
            "open_quality_issues": _metric("open_quality_issues", "Open quality issues", value_format="integer"),
            "critical_quality_issues": _metric("critical_quality_issues", "Critical quality issues", value_format="integer"),
            "quality_score": _metric("quality_score", "Quality score", value_format="percent", unit="percent", default="avg"),
        },
        _load_capacity_quality, allowed_shapes=("bar", "horizontal_bar", "scatter"),
    ),
    "portfolio.procurement_schedule": DatasetDefinition(
        "portfolio.procurement_schedule", "Procurement and Schedule",
        {
            "project_name": _dimension("project_name", "Project"),
            "procurement_fulfillment_pct": _metric("procurement_fulfillment_pct", "Procurement fulfilment", value_format="percent", unit="percent", default="avg"),
            "schedule_delay_days": _metric("schedule_delay_days", "Schedule delay", value_format="days", unit="days", default="avg"),
            "progress_pct": _metric("progress_pct", "Project progress", value_format="percent", unit="percent", default="avg"),
        },
        _load_procurement_schedule, allowed_shapes=("bar", "horizontal_bar", "scatter"),
    ),
}


class VisualizationQueryError(ValueError):
    """A safe, repairable error in a model-authored visualization request."""


def visualization_catalog_summary() -> str:
    parts = []
    for dataset in DATASET_CATALOG.values():
        dimensions = [field.field for field in dataset.fields.values() if field.role == "dimension"]
        metrics = [field.field for field in dataset.fields.values() if field.role == "metric"]
        parts.append(
            f"{dataset.dataset_id} (dimensions: {', '.join(dimensions)}; metrics: {', '.join(metrics)})"
        )
    return "; ".join(parts)


def _validate_query(query: VisualizationQueryV2, dataset: DatasetDefinition, project_id: str | None) -> None:
    if dataset.requires_project and not project_id:
        raise VisualizationQueryError(f"Dataset {dataset.dataset_id} requires project_id.")
    for dimension in query.dimensions:
        field = dataset.fields.get(dimension)
        if field is None or field.role != "dimension":
            raise VisualizationQueryError(f"Unknown or non-dimensional field: {dimension}.")
    for metric in query.metrics:
        field = dataset.fields.get(metric.field)
        if field is None or field.role != "metric":
            raise VisualizationQueryError(f"Unknown or non-metric field: {metric.field}.")
        aggregation = metric.aggregation or field.default_aggregation
        if aggregation not in field.aggregations:
            raise VisualizationQueryError(
                f"Aggregation {aggregation} is not allowed for {metric.field}."
            )
    for item in query.filters:
        field = dataset.fields.get(item.field)
        if field is None or not field.filterable:
            raise VisualizationQueryError(f"Field is not filterable: {item.field}.")


def _matches(value: Any, operator: FilterOperator, expected: Any) -> bool:
    if operator == "eq":
        return value == expected
    if operator == "neq":
        return value != expected
    if operator == "in":
        return isinstance(expected, list) and value in expected
    if operator == "contains":
        return str(expected).casefold() in str(value or "").casefold()
    try:
        if operator == "gte":
            return value is not None and value >= expected
        if operator == "lte":
            return value is not None and value <= expected
    except TypeError:
        return False
    return False


def _aggregate(values: list[Any], aggregation: Aggregation) -> int | float | None:
    available = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if aggregation == "count":
        return len(available)
    if not available:
        return None
    result = {
        "sum": sum(available),
        "avg": sum(available) / len(available),
        "min": min(available),
        "max": max(available),
    }[aggregation]
    rounded = round(result, 2)
    return int(rounded) if rounded.is_integer() else rounded


def _aggregate_rows(
    rows: list[dict[str, Any]], query: VisualizationQueryV2, dataset: DatasetDefinition,
) -> list[dict[str, Any]]:
    filtered = [
        row for row in rows
        if all(_matches(row.get(item.field), item.operator, item.value) for item in query.filters)
    ]
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in filtered:
        grouped[tuple(row.get(field) for field in query.dimensions)].append(row)
    if not query.dimensions and filtered:
        grouped[()] = filtered

    output = []
    for key, group in grouped.items():
        result = {field: key[index] for index, field in enumerate(query.dimensions)}
        for metric in query.metrics:
            definition = dataset.fields[metric.field]
            aggregation = metric.aggregation or definition.default_aggregation or "sum"
            result[metric.field] = _aggregate([row.get(metric.field) for row in group], aggregation)
        output.append(result)

    for ordering in reversed(query.sort):
        if ordering.field not in {*query.dimensions, *(metric.field for metric in query.metrics)}:
            raise VisualizationQueryError(f"Sort field is not present in the output: {ordering.field}.")
        output.sort(
            key=lambda row: (row.get(ordering.field) is None, row.get(ordering.field)),
            reverse=ordering.direction == "desc",
        )
    return output[:query.limit]


def _choose_shape(
    query: VisualizationQueryV2, dataset: DatasetDefinition,
) -> str:
    dimensions = [dataset.fields[field] for field in query.dimensions]
    requested = query.preferred_shape
    if requested == "auto":
        if len(dimensions) == 2:
            requested = "heatmap"
        elif dimensions and dimensions[0].field_type == "temporal":
            requested = "line"
        elif len(query.metrics) == 2 and query.dimensions:
            requested = "bar"
        else:
            requested = "horizontal_bar"
    if requested not in dataset.allowed_shapes:
        requested = "line" if "line" in dataset.allowed_shapes and dimensions and dimensions[0].field_type == "temporal" else dataset.allowed_shapes[0]
    if requested == "heatmap" and (len(query.dimensions) != 2 or len(query.metrics) != 1):
        raise VisualizationQueryError("A heatmap requires exactly two dimensions and one metric.")
    if requested == "scatter" and (len(query.metrics) != 2 or len(query.dimensions) > 1):
        raise VisualizationQueryError("A scatter chart requires exactly two metrics and at most one label dimension.")
    if requested in {"waterfall", "donut"} and (len(query.dimensions) != 1 or len(query.metrics) != 1):
        raise VisualizationQueryError(f"A {requested} chart requires exactly one dimension and one metric.")
    if requested == "waterfall" and not dataset.fields[query.metrics[0].field].additive:
        raise VisualizationQueryError("A waterfall requires an additive metric from the catalog.")
    if requested == "line" and (
        len(query.dimensions) != 1 or dimensions[0].field_type != "temporal"
    ):
        raise VisualizationQueryError("A line chart requires exactly one temporal dimension.")
    if requested in {"bar", "horizontal_bar", "stacked_bar"} and len(query.dimensions) != 1:
        raise VisualizationQueryError(f"A {requested} chart requires exactly one dimension.")
    return requested


def _channel(definition: FieldDefinition, axis_index: int = 0) -> VisualizationChannelV2:
    return VisualizationChannelV2(
        field=definition.field,
        label=definition.label,
        field_type=definition.field_type,
        value_format=definition.value_format,
        unit=definition.unit,
        axis_index=axis_index,
    )


def build_dynamic_visualization(
    db: Session,
    query_payload: dict[str, Any] | VisualizationQueryV2,
    *,
    project_id: str | None = None,
    project_ids: list[str] | None = None,
    days: int = 30,
    retrieval_limit: int = 500,
) -> dict[str, Any]:
    query = query_payload if isinstance(query_payload, VisualizationQueryV2) else VisualizationQueryV2.model_validate(query_payload)
    dataset = DATASET_CATALOG[query.dataset_id]
    _validate_query(query, dataset, project_id)
    loaded = dataset.loader(db, project_id, list(project_ids or []), retrieval_limit, days)
    rows = _aggregate_rows(loaded.rows, query, dataset)
    if not rows:
        return {
            "no_data": True,
            "chart_type": query.dataset_id,
            "message": "No authorized data matched the requested visualization fields and filters.",
        }
    shape = _choose_shape(query, dataset)
    if shape == "scatter":
        metric_names = [metric.field for metric in query.metrics]
        rows = [row for row in rows if all(row.get(field) is not None for field in metric_names)]
    elif shape == "heatmap":
        rows = [row for row in rows if row.get(query.metrics[0].field) is not None]
    if not rows:
        return {
            "no_data": True,
            "chart_type": query.dataset_id,
            "message": "No complete authorized data points are available for the requested chart shape.",
        }
    if shape == "donut" and any(float(row.get(query.metrics[0].field) or 0) < 0 for row in rows):
        raise VisualizationQueryError("A donut chart cannot represent negative values.")
    if shape == "scatter" and len(rows) < 2:
        raise VisualizationQueryError("A scatter chart requires at least two comparable data points.")
    dimension_defs = [dataset.fields[field] for field in query.dimensions]
    metric_defs = [dataset.fields[metric.field] for metric in query.metrics]
    if shape == "scatter":
        encoding = VisualizationEncodingV2(
            x=_channel(metric_defs[0]), y=[_channel(metric_defs[1])],
            label=_channel(dimension_defs[0]) if dimension_defs else None,
        )
    elif shape == "heatmap":
        encoding = VisualizationEncodingV2(
            x=_channel(dimension_defs[0]), y=[_channel(dimension_defs[1])],
            color=_channel(metric_defs[0]),
        )
    else:
        unit_groups = list(dict.fromkeys(field.unit or field.value_format or "value" for field in metric_defs))
        if shape == "stacked_bar" and len(unit_groups) > 1:
            raise VisualizationQueryError("Stacked bars require metrics with compatible units.")
        if shape == "horizontal_bar" and len(unit_groups) > 1:
            raise VisualizationQueryError("Horizontal bars require metrics with compatible units; use a grouped bar or scatter chart.")
        if len(unit_groups) > 2:
            raise VisualizationQueryError("A Cartesian chart supports at most two compatible unit axes.")
        encoding = VisualizationEncodingV2(
            x=_channel(dimension_defs[0]) if dimension_defs else None,
            y=[
                _channel(field, unit_groups.index(field.unit or field.value_format or "value"))
                for field in metric_defs
            ],
        )
    title = query.title or dataset.title
    metric_labels = ", ".join(field.label for field in metric_defs)
    dimension_labels = ", ".join(field.label for field in dimension_defs) or "the selected scope"
    summary = f"{metric_labels} by {dimension_labels}, using {len(rows)} validated data point{'s' if len(rows) != 1 else ''}."
    spec = VisualizationSpecV2(
        chart_id=f"dynamic.{query.dataset_id}",
        chart_type=query.dataset_id,
        shape=shape,
        title=title,
        subtitle=f"Authorized {query.dataset_id} data",
        summary=summary,
        accessibility_description=f"{title}. {summary}",
        encoding=encoding,
        data=rows,
        data_as_of=loaded.data_as_of,
        source_tables=list(loaded.source_tables),
    ).transport()
    return {
        "schema_version": "visualization.v2",
        "chart_type": query.dataset_id,
        "title": title,
        "subtitle": spec.get("subtitle"),
        "summary": summary,
        "accessibility_description": spec["accessibility_description"],
        "data_points": len(rows),
        "data_as_of": loaded.data_as_of,
        "data_table": rows,
        "visualization_spec": spec,
        "_source_tables": list(loaded.source_tables),
    }
