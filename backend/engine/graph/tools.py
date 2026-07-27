from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from database import SessionLocal
from engine.agent import TOOLS, build_chart_result, execute_tool
import models


logger = logging.getLogger(__name__)
ToolStatus = Literal["ok", "no_data", "error"]


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyArguments(ToolArguments):
    pass


class NameArguments(ToolArguments):
    name: str = Field(min_length=1, max_length=200)


class ProjectArguments(ToolArguments):
    project_id: str = Field(min_length=1, max_length=200)


class TopArguments(ToolArguments):
    top_n: int = Field(ge=1, le=20)


class NotificationArguments(ToolArguments):
    limit: int = Field(default=10, ge=1, le=50)
    category: str = Field(default="All", max_length=50)


class RiskLineArguments(ToolArguments):
    days_threshold: int = Field(default=60, ge=0, le=3_650)
    limit: int = Field(default=15, ge=1, le=200)
    region: str | None = Field(default=None, min_length=1, max_length=100)


class TransmissionCollectionArguments(ToolArguments):
    region: str = Field(min_length=1, max_length=100)
    delayed_only: bool = False
    limit: int = Field(default=100, ge=1, le=200)


class PulseCollectionArguments(ToolArguments):
    record_type: Literal["nc", "rfi"] | None = None
    status: str | None = Field(default=None, min_length=1, max_length=100)
    limit: int = Field(default=100, ge=1, le=100)


class ProjectLimitArguments(ProjectArguments):
    limit: int = Field(default=20, ge=1, le=100)


class ActivityListArguments(ProjectLimitArguments):
    status: Literal["all", "completed", "in_progress", "not_started"] = "all"
    offset: int = Field(default=0, ge=0, le=100_000)


class DelayedArguments(ProjectLimitArguments):
    min_drift_days: int = Field(default=7, ge=0, le=3_650)


class MaterialGapArguments(ProjectArguments):
    limit: int = Field(default=15, ge=1, le=100)


class ActivityArguments(ProjectArguments):
    activity_keyword: str = Field(min_length=1, max_length=200)


class WhatIfArguments(ActivityArguments):
    manpower_multiplier: float = Field(default=1.0, ge=0.1, le=5.0)


class ActivityFinishForecastArguments(ProjectArguments):
    period: Literal["month", "year"] = "month"
    target_year: int | None = Field(default=None, ge=2000, le=2100)
    target_month: int | None = Field(default=None, ge=1, le=12)
    limit: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def validate_target_period(self):
        if self.period == "month" and (self.target_year is None) != (self.target_month is None):
            raise ValueError("target_year and target_month must be provided together for a month")
        if self.period == "year" and self.target_month is not None:
            raise ValueError("target_month must be omitted for a year")
        return self


class ReportGenerateArguments(ProjectArguments):
    preview_token: str = Field(min_length=40, max_length=1_000)


class ChartArguments(ToolArguments):
    chart_type: Literal[
        "auto", "activity_status", "project_comparison", "delayed_activities",
        "material_gaps", "vendor_performance", "sap_po_fulfillment",
        "transmission_status", "portfolio_risk",
    ]
    project_id: str | None = Field(default=None, max_length=200)
    project_ids: list[str] | None = Field(default=None, max_length=20)
    domain_hint: str | None = Field(default=None, max_length=100)


ARGUMENT_MODELS: dict[str, type[ToolArguments]] = {
    "portfolio_resolve_project_id": NameArguments,
    "portfolio_get_riskiest_projects": TopArguments,
    "p6_get_project_summary": ProjectArguments,
    "sap_get_po_summary": ProjectArguments,
    "tc_get_project_lines": ProjectArguments,
    "tc_search_lines": TransmissionCollectionArguments,
    "portfolio_get_notifications": NotificationArguments,
    "tc_get_at_risk_lines": RiskLineArguments,
    "tc_get_network_summary": EmptyArguments,
    "p6_list_all_projects": EmptyArguments,
    "p6_get_critical_activities": ProjectLimitArguments,
    "p6_get_delayed_activities": DelayedArguments,
    "p6_get_activity_status_breakdown": ProjectArguments,
    "p6_get_activities": ActivityListArguments,
    "sap_get_material_gaps": MaterialGapArguments,
    "sap_get_vendor_performance": ProjectArguments,
    "sap_get_inventory": ProjectArguments,
    "sap_get_consumption": ProjectArguments,
    "sim_get_activity_productivity": ActivityArguments,
    "sim_project_duration_what_if": WhatIfArguments,
    "sim_monsoon_impact": ActivityArguments,
    "sim_material_bottlenecks": ActivityArguments,
    "get_project_kpis": ProjectArguments,
    "sim_forecast_completion": ProjectArguments,
    "sim_forecast_activity_finishes": ActivityFinishForecastArguments,
    "render_chart": ChartArguments,
    "report_preview_project_progress": ProjectArguments,
    "report_generate_project_progress": ReportGenerateArguments,
}

PORTFOLIO_TOOLS = {
    "portfolio_get_riskiest_projects", "tc_get_at_risk_lines",
    "tc_get_network_summary", "tc_search_lines", "p6_list_all_projects",
    "portfolio_get_notifications",
}


@dataclass(frozen=True, slots=True)
class ToolRuntimeContext:
    user_id: str
    tenant_id: str
    role: str
    session_id: str
    run_id: str
    request_id: str
    active_project_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolExecution:
    content: str
    status: ToolStatus
    visualization: dict | None = None


class ToolRunCancelled(RuntimeError):
    pass


def _check_cancelled(db, run_id: str) -> None:
    status = db.query(models.ChatRun.status).filter(models.ChatRun.run_id == run_id).scalar()
    if status in {"cancel_requested", "cancelled", "interrupted"}:
        raise ToolRunCancelled("Chat run was cancelled.")


def _authorize_project(db, project_id: str, runtime: ToolRuntimeContext) -> None:
    if runtime.active_project_ids and project_id not in runtime.active_project_ids:
        raise PermissionError("Project is outside the selected authorized scope.")
    exists = db.query(models.ProjectMapping.id).filter(
        models.ProjectMapping.project_id == project_id
    ).first() or db.query(models.P6Project.id).filter(
        models.P6Project.project_id == project_id
    ).first()
    if not exists:
        raise ValueError("Unknown project.")


def _result_status(data) -> ToolStatus:
    if data is None or data == [] or data == {}:
        return "no_data"
    if isinstance(data, dict) and (
        data.get("status") == "no_data" or data.get("has_data") is False
    ):
        return "no_data"
    return "ok"


def _bounded_result(status: ToolStatus, data, max_chars: int = 50_000) -> str:
    payload = {"status": status, "data": data, "truncated": False}
    encoded = json.dumps(payload, default=str, separators=(",", ":"))
    if len(encoded) <= max_chars:
        return encoded
    payload = {
        "status": status,
        "data": {"preview": json.dumps(data, default=str)[:max_chars - 500]},
        "truncated": True,
    }
    return json.dumps(payload, default=str, separators=(",", ":"))


def execute_authenticated_tool(
    name: str,
    arguments: dict,
    runtime: ToolRuntimeContext,
) -> ToolExecution:
    argument_model = ARGUMENT_MODELS.get(name)
    if argument_model is None:
        return ToolExecution(_bounded_result("error", {"message": "Unknown tool."}), "error")
    try:
        validated = argument_model.model_validate(arguments).model_dump(exclude_none=True)
    except ValidationError:
        return ToolExecution(_bounded_result("error", {"message": "Invalid tool arguments."}), "error")

    db = SessionLocal()
    try:
        _check_cancelled(db, runtime.run_id)
        if runtime.active_project_ids and name in PORTFOLIO_TOOLS:
            raise PermissionError("Portfolio-wide access is outside the selected project scope.")
        project_ids = []
        if validated.get("project_id"):
            project_ids.append(validated["project_id"])
        project_ids.extend(validated.get("project_ids") or [])
        for project_id in project_ids:
            _authorize_project(db, project_id, runtime)

        visualization = None
        if name == "render_chart":
            spec, raw = build_chart_result(db, validated)
            if spec is not None:
                visualization = {
                    "chart_type": spec.get("chart_type"),
                    "title": spec.get("title"),
                    "spec": spec.get("option"),
                }
        elif name == "report_preview_project_progress":
            from services.report_mvp_service import create_project_progress_preview
            raw = create_project_progress_preview(db, runtime, validated["project_id"])
        elif name == "report_generate_project_progress":
            from services.report_mvp_service import generate_project_progress_report
            raw = generate_project_progress_report(
                db,
                runtime,
                validated["project_id"],
                validated["preview_token"],
            )
        else:
            raw = execute_tool(db, name, validated)
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            data = raw
        if name == "portfolio_resolve_project_id" and isinstance(data, dict) and data.get("project_id"):
            _authorize_project(db, str(data["project_id"]), runtime)
        if isinstance(data, dict) and "error" in data:
            return ToolExecution(_bounded_result("error", {"message": "Tool execution failed."}), "error")
        status = _result_status(data)
        _check_cancelled(db, runtime.run_id)
        return ToolExecution(_bounded_result(status, data), status, visualization)
    except ToolRunCancelled:
        raise
    except (PermissionError, ValueError) as exc:
        return ToolExecution(_bounded_result("error", {"message": str(exc)}), "error")
    except Exception as exc:
        logger.error("Graph tool %s failed (%s)", name, type(exc).__name__)
        return ToolExecution(_bounded_result("error", {"message": "Tool execution failed."}), "error")
    finally:
        db.close()


def model_tool_schemas() -> list[dict]:
    schemas = []
    for legacy_tool in TOOLS:
        tool = deepcopy(legacy_tool)
        function = tool.get("function") or {}
        name = function.get("name")
        argument_model = ARGUMENT_MODELS.get(name)
        if argument_model is not None:
            generated = argument_model.model_json_schema()
            old_properties = (function.get("parameters") or {}).get("properties") or {}
            for property_name, property_schema in generated.get("properties", {}).items():
                description = (old_properties.get(property_name) or {}).get("description")
                if description:
                    property_schema.setdefault("description", description)
            function["parameters"] = generated
        schemas.append(tool)
    return schemas


_RAW_TOOL_CALL = re.compile(
    r"^\s*<tool_call>\s*<function=([A-Za-z][A-Za-z0-9_]*)>\s*(.*?)\s*</function>\s*</tool_call>\s*$",
    re.IGNORECASE | re.DOTALL,
)
_RAW_PARAMETER = re.compile(
    r"<parameter=([A-Za-z][A-Za-z0-9_]*)>\s*(.*?)\s*</parameter>",
    re.IGNORECASE | re.DOTALL,
)


def parse_raw_tool_call(content: str) -> tuple[str, dict] | None:
    """Normalize one provider-emitted XML-style call through the normal tool contract."""
    match = _RAW_TOOL_CALL.fullmatch(content)
    if match is None:
        return None
    name, body = match.groups()
    argument_model = ARGUMENT_MODELS.get(name)
    if argument_model is None:
        return None

    raw_arguments = {}
    cursor = 0
    for parameter in _RAW_PARAMETER.finditer(body):
        if body[cursor:parameter.start()].strip():
            return None
        key, value = parameter.groups()
        if key in raw_arguments:
            return None
        raw_arguments[key] = value.strip()
        cursor = parameter.end()
    if body[cursor:].strip():
        return None

    candidates = [raw_arguments]
    coerced = {}
    for key, value in raw_arguments.items():
        try:
            coerced[key] = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            coerced[key] = value
    if coerced != raw_arguments:
        candidates.append(coerced)
    for candidate in candidates:
        try:
            validated = argument_model.model_validate(candidate).model_dump(exclude_none=True)
            return name, validated
        except ValidationError:
            continue
    return None
