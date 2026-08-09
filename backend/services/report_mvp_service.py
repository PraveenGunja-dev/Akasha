from __future__ import annotations

import base64
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

import models
from engine.model_provider import get_model_provider
from services.capacity_milestone_service import CapacityMilestoneService
from services.chart_spec_service import ChartSpecService
from services.project_catalog_service import ProjectCatalogService
from services.quality_analytics_service import QualityAnalyticsService
from services.risk_analytics_service import RiskAnalyticsService
from services.sap_project_data_service import SapProjectDataService
from services.schedule_metrics_service import ScheduleMetricsService
from services.visualization_spec import (
    activity_status_spec,
    activity_composition_spec,
    baseline_slip_spec,
    block_progress_spec,
    daily_completion_spec,
    duration_comparison_spec,
    portfolio_status_spec,
    planned_vs_actual_progress_spec,
    project_capacity_comparison_spec,
    project_progress_spec,
)
from services import transmission_service


_PREVIEW_SECRET = secrets.token_bytes(32)
REPORT_TYPE = "project_progress"
PORTFOLIO_REPORT_TYPE = "portfolio_progress"
PORTFOLIO_SCOPE_ID = "__portfolio__"
COMPARISON_REPORT_TYPE = "project_comparison"
COMPARISON_SCOPE_ID = "__comparison__"


def _transport_spec(spec) -> dict | None:
    return spec.transport() if spec is not None else None


def _portfolio_token_scope(portfolio: str | None) -> str:
    normalized = " ".join(str(portfolio or "All portfolios").strip().casefold().split())
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:20]
    return f"{PORTFOLIO_SCOPE_ID}:{digest}"


def _comparison_token_scope(project_ids: list[str]) -> str:
    normalized = "|".join(sorted({str(project_id).strip() for project_id in project_ids if project_id}))
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:20]
    return f"{COMPARISON_SCOPE_ID}:{digest}"


def _artifact_root() -> Path:
    root = Path(os.getenv(
        "AKASHA_REPORT_ARTIFACT_DIR",
        str(Path(__file__).resolve().parents[1] / "report_artifacts"),
    )).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _quality_summary(db, project_id: str) -> dict:
    snapshot = QualityAnalyticsService.project_status(db, project_id).to_dict()
    provenance = snapshot.get("provenance", {})
    sync_values = [
        value for value in (
            provenance.get("nc_last_synced_at"),
            provenance.get("rfi_last_synced_at"),
        ) if value
    ]
    return {
        **snapshot,
        "has_data": snapshot["available"],
        "non_conformances": snapshot["total_ncs"],
        "open_non_conformances": snapshot["open_ncs"],
        "rfis": snapshot["total_rfis"],
        "last_synced_at": max(sync_values, default=None),
    }


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _project_summary(project, schedule) -> dict:
    return {
        "project_id": project.project_id,
        "project_name": project.display_name,
        "name": project.p6_mapping_name or project.project_name,
        "status": schedule.status or "P6 data unavailable",
        "start_date": _iso(schedule.start_date),
        "finish_date": _iso(schedule.finish_date),
        "planned_start": _iso(schedule.planned_start),
        "scheduled_finish": _iso(schedule.scheduled_finish),
        "must_finish_by": _iso(schedule.must_finish_by),
        "data_date": _iso(schedule.data_date),
        "duration_percent_complete": schedule.duration_percent_complete,
        "planned_duration": schedule.planned_duration,
        "actual_duration": schedule.actual_duration,
        "remaining_duration": schedule.remaining_duration,
        "spi": schedule.spi,
        "cpi": schedule.cpi,
        "total_float_hours": schedule.total_float,
        "finish_date_variance_days": schedule.finish_date_variance,
        "activity_count": schedule.activity_count,
        "completed_activities": schedule.completed_activities,
        "in_progress_activities": schedule.in_progress_activities,
        "not_started_activities": schedule.not_started_activities,
        "baseline_start": _iso(schedule.baseline_start),
        "baseline_finish": _iso(schedule.baseline_finish),
        "baseline_duration": schedule.baseline_duration,
        "last_synced_at": _iso(schedule.last_synced_at),
        "p6_available": schedule.p6_available,
        "progress_pct": schedule.progress_pct,
        "progress_formula": schedule.progress_formula,
        "progress_formula_version": schedule.progress_formula_version,
        "progress_units": schedule.progress_units,
        "is_delayed": schedule.is_delayed,
        "delay_formula": schedule.delay_formula,
    }


def _schedule_summary(schedule) -> dict:
    return {
        "progress_pct": schedule.progress_pct,
        "completed_activities": schedule.completed_activities,
        "in_progress_activities": schedule.in_progress_activities,
        "not_started_activities": schedule.not_started_activities,
        "spi": schedule.spi,
        "cpi": schedule.cpi,
        "is_delayed": schedule.is_delayed,
        "finish_date_variance": schedule.finish_date_variance,
        "finish_date_variance_units": schedule.finish_date_variance_units,
        "progress_formula": schedule.progress_formula,
        "progress_formula_version": schedule.progress_formula_version,
    }


def _procurement_summary(sap: dict) -> dict:
    totals = sap["totals"]["purchase_orders"]
    ordered = totals["ordered_quantity"]
    return {
        "project_id": sap["project_id"],
        "project_name": sap["project_name"],
        "has_data": bool(sap["purchase_orders"]),
        "total_po_count": sap["counts"]["po_row_count"],
        "distinct_po_count": sap["counts"]["distinct_po_count"],
        "total_ordered_qty": totals["ordered_quantity"],
        "total_delivered_qty": totals["delivered_quantity"],
        "total_pending_qty": totals["pending_quantity"],
        "fulfillment_pct": round(totals["delivered_quantity"] / ordered * 100, 1) if ordered else 0,
        "total_value_inr": totals["order_value"],
        "scope": sap["scope"],
        "units": sap["units"],
        "warnings": sap["warnings"],
        "last_synced_at": sap["freshness"]["mt_poamount"],
    }


def build_project_progress_dataset(db, project_id: str) -> dict:
    project = ProjectCatalogService.get_by_project_id(db, project_id)
    if project is None:
        raise ValueError("Unknown project.")
    schedule_metrics = ScheduleMetricsService.get_by_project_id(db, project_id)
    summary = _project_summary(project, schedule_metrics)
    schedule = _schedule_summary(schedule_metrics)
    sap = SapProjectDataService.get_by_project_id(db, project_id)
    procurement = _procurement_summary(sap)
    transmission = transmission_service.project_status(db, project_id)
    quality = _quality_summary(db, project_id)
    capacity = CapacityMilestoneService.get_project_status(db, project_id)
    risk_metrics = {
        metric.metric_id: metric.to_dict()
        for metric in RiskAnalyticsService.project360(db, project_id)
    }
    activities = ScheduleMetricsService.get_activities(
        db, project_id, status="In Progress", limit=20
    )
    in_progress = {
        "project_id": project_id,
        "project_name": project.display_name,
        "has_data": bool(activities),
        "status_filter": "in_progress",
        "total_matching": schedule_metrics.in_progress_activities,
        "returned": len(activities),
        "offset": 0,
        "activities": activities,
        "data_date": _iso(schedule_metrics.data_date),
        "last_synced_at": _iso(schedule_metrics.last_synced_at),
    }
    source_freshness = {
        "P6": summary.get("last_synced_at"),
        "SAP": procurement.get("last_synced_at"),
        "TC": transmission.get("last_synced_at"),
        "Pulse": quality.get("last_synced_at"),
        "Capacity": capacity.get("metadata", {}).get("freshness", {}).get("last_synced_at"),
    }
    missing_sources = [
        name for name, available in {
            "P6": schedule_metrics.p6_available,
            "SAP": procurement["has_data"],
            "TC": bool(transmission and transmission.get("has_data")),
            "Pulse": quality["has_data"],
            "Capacity": bool(capacity.get("projects")),
        }.items() if not available
    ]
    return {
        "metadata": {
            "report_type": REPORT_TYPE,
            "project_id": project_id,
            "project_name": project.display_name,
            "generated_at": datetime.utcnow().isoformat(),
            "reporting_cutoff": summary.get("data_date"),
            "source_freshness": source_freshness,
            "missing_sources": missing_sources,
            "period": "current_month",
            "period_start": (
                f"{str(schedule_metrics.data_date)[:7]}-01"
                if schedule_metrics.data_date else None
            ),
            "period_definition": "Current calendar month through the latest P6 data cutoff",
            "limitations": [
                "Historical planned-versus-actual progress curves are unavailable because snapshots are not persisted."
            ],
        },
        "project_summary": summary,
        "schedule": schedule,
        "in_progress_activities": in_progress,
        "procurement": procurement,
        "transmission": transmission,
        "quality": quality,
        "capacity": capacity,
        "risk": risk_metrics,
        "report_visualizations": {
            "overall_progress": _transport_spec(project_progress_spec([{
                "project_id": project_id,
                "project_name": project.display_name,
                "progress_pct": schedule.get("progress_pct"),
            }], title=f"{project.display_name} - Overall Progress")),
            "planned_vs_actual": _transport_spec(planned_vs_actual_progress_spec(
                ChartSpecService.planned_vs_actual_progress(db, project_id),
                project.display_name,
            )),
            "activity_status": _transport_spec(activity_status_spec(
                ChartSpecService.activity_status(db, project_id),
                project.display_name,
            )),
            "block_progress": _transport_spec(block_progress_spec(
                ScheduleMetricsService.get_block_period_progress(db, project_id, period="current_month"),
                project.display_name,
            )),
            "daily_completion_trend": _transport_spec(daily_completion_spec(
                ScheduleMetricsService.get_daily_activity_completion_trend(db, project_id, days=30),
                project.display_name,
            )),
        },
    }


def build_portfolio_progress_dataset(db, portfolio: str | None = None) -> dict:
    projects = [project for project in ProjectCatalogService.list_projects(db, portfolio) if project.project_id]
    metrics_by_id = ScheduleMetricsService.list_by_project_ids(
        db, [project.project_id for project in projects]
    )
    rows = []
    for project in projects:
        schedule = metrics_by_id.get(project.project_id, ScheduleMetricsService.calculate(None))
        rows.append({
            "project_id": project.project_id,
            "project_name": project.display_name,
            "capacity_mwac": project.capacity_mwac,
            "progress_pct": schedule.progress_pct,
            "status": (
                "P6 unavailable" if not schedule.p6_available
                else "Completed" if schedule.progress_pct is not None and schedule.progress_pct >= 100
                else "Delayed" if schedule.is_delayed
                else "On track"
            ),
            "is_delayed": schedule.is_delayed,
            "forecast_finish": _iso(schedule.finish_date),
            "baseline_finish": _iso(schedule.baseline_finish),
            "finish_date_variance_days": schedule.finish_date_variance,
            "data_date": _iso(schedule.data_date),
            "last_synced_at": _iso(schedule.last_synced_at),
        })

    rows.sort(key=lambda row: (
        0 if row["status"] == "Delayed" else 1 if row["status"] == "On track" else 2,
        -(row["progress_pct"] or 0),
        row["project_name"],
    ))
    cutoffs = [row["data_date"] for row in rows if row["data_date"]]
    cutoff = max(cutoffs, default=None)
    period_start = f"{cutoff[:7]}-01" if cutoff else None
    counts = {
        "total_projects": len(rows),
        "projects_with_p6": sum(row["status"] != "P6 unavailable" for row in rows),
        "delayed": sum(row["status"] == "Delayed" for row in rows),
        "on_track": sum(row["status"] == "On track" for row in rows),
        "completed": sum(row["status"] == "Completed" for row in rows),
        "p6_unavailable": sum(row["status"] == "P6 unavailable" for row in rows),
    }
    return {
        "metadata": {
            "report_type": PORTFOLIO_REPORT_TYPE,
            "portfolio": portfolio or "All portfolios",
            "generated_at": datetime.utcnow().isoformat(),
            "reporting_cutoff": cutoff,
            "period": "current_month",
            "period_start": period_start,
            "period_definition": "Current calendar month through the latest synchronized P6 cutoff",
            "source_freshness": {
                "P6": max((row["last_synced_at"] for row in rows if row["last_synced_at"]), default=None),
            },
            "missing_sources": [],
            "limitations": [
                "This is a latest-snapshot portfolio report; historical planned-versus-actual curves are unavailable."
            ],
        },
        "summary": counts,
        "projects": rows,
        "report_visualizations": {
            "project_progress": _transport_spec(project_progress_spec(rows)),
            "schedule_status": _transport_spec(portfolio_status_spec(counts, cutoff)),
        },
    }


def build_project_comparison_dataset(db, project_ids: list[str]) -> dict:
    if len(set(project_ids)) < 2:
        raise ValueError("A comparison report requires at least two distinct projects.")
    comparison = ChartSpecService.project_comparison(db, project_ids)
    by_id = {row["project_id"]: row for row in comparison.get("projects") or []}
    rows = []
    for project_id in project_ids:
        row = by_id.get(project_id)
        if row is None:
            continue
        catalog = ProjectCatalogService.get_by_project_id(db, project_id)
        rows.append({
            **row,
            "capacity_mwac": catalog.capacity_mwac if catalog else None,
            "spv_name": catalog.spv_name if catalog else None,
            "status": (
                "P6 unavailable"
                if not row.get("p6_available")
                else "Delayed" if (row.get("baseline_slip_days") or 0) > 0
                else "On track"
            ),
        })
    if len(rows) < 2:
        raise ValueError("Project mapping data is unavailable for enough projects to create a comparison report.")
    cutoffs = [row["data_as_of"] for row in rows if row.get("data_as_of")]
    cutoff = max(cutoffs, default=None)
    visualizations = [spec for spec in [
        project_progress_spec(rows, title="Project Comparison — % Complete"),
        activity_composition_spec(rows),
        duration_comparison_spec(rows),
        baseline_slip_spec(rows),
        project_capacity_comparison_spec(rows),
    ] if spec is not None][:4]
    return {
        "metadata": {
            "report_type": COMPARISON_REPORT_TYPE,
            "project_ids": [row["project_id"] for row in rows],
            "project_names": [row["project_name"] for row in rows],
            "generated_at": datetime.utcnow().isoformat(),
            "reporting_cutoff": cutoff,
            "source_freshness": {"P6": cutoff},
            "limitations": [
                "SPI/CPI are reported only when present in the synchronized extract.",
                "Forecast-versus-baseline slippage is a direct calendar-date comparison, not a historical progress curve.",
                "Catalog attributes remain comparable when P6 schedule metrics are unavailable.",
            ],
        },
        "projects": rows,
        "report_visualizations": {
            spec.chart_id: spec.transport() for spec in visualizations
        },
    }


def _fallback_narrative(dataset: dict) -> str:
    summary = dataset["project_summary"]
    schedule = dataset["schedule"]
    project_name = summary.get("project_name") or dataset.get("metadata", {}).get("project_name") or "The project"
    if not summary.get("p6_available", True):
        text = f"{project_name} is present in the project catalog, but P6 schedule facts are unavailable."
    else:
        text = (
            f"{project_name} is {schedule.get('progress_pct')}% complete using the authoritative P6 progress formula, "
            f"with {schedule.get('completed_activities')} completed, "
            f"{schedule.get('in_progress_activities')} in-progress, and "
            f"{schedule.get('not_started_activities')} not-started activities."
        )
    if schedule.get("spi") is None:
        text += " SPI is unavailable, so the report does not classify the project as ahead or behind."
    missing = dataset.get("metadata", {}).get("missing_sources") or []
    if missing:
        text += f" No mapped data is available from {', '.join(missing)}, so those sections remain unassessed."
    return text


def _parse_narrative(content: str | None) -> str | None:
    if not content:
        return None
    try:
        payload = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    narrative = payload.get("executive_summary") if isinstance(payload, dict) else None
    if not isinstance(narrative, str):
        return None
    narrative = " ".join(narrative.split()).strip()
    if len(narrative) < 40 or len(narrative) > 2_000:
        return None
    meta_phrases = (
        "the user wants", "i need to", "let me", "supplied json", "json facts",
        "constraints:", "i cannot mention", "let me draft", "my task",
    )
    if any(phrase in narrative.lower() for phrase in meta_phrases):
        return None
    return narrative


def generate_narrative(dataset: dict) -> str:
    fallback = _fallback_narrative(dataset)
    if os.getenv("AKASHA_REPORT_AI_NARRATIVE", "true").lower() not in {"1", "true", "yes"}:
        return fallback
    facts = json.dumps(dataset, default=str, separators=(",", ":"))[:30_000]
    try:
        result = get_model_provider().invoke(
            [
                {"role": "system", "content": (
                    "Return a JSON object with exactly one string field named executive_summary. "
                    "The field must contain one polished 80-140 word executive paragraph suitable "
                    "for the final report. Use only facts, numbers, dates, and classifications present "
                    "in the supplied dataset; do not invent or infer new ones. State unavailable SPI/CPI "
                    "and missing source systems plainly. Never include analysis, instructions, planning, "
                    "JSON commentary, or phrases such as 'the user wants', 'I need to', or 'let me'."
                )},
                {"role": "user", "content": facts},
            ],
            temperature=0.1,
            max_tokens=350,
            json_mode=True,
        )
        return _parse_narrative(result.content) or fallback
    except Exception:
        return fallback


def _preview_payload(
    session_id: str, project_id: str, expires: int, visualization_refs: list[dict] | None = None
) -> str:
    payload = {"s": session_id, "p": project_id, "e": expires}
    if visualization_refs is not None:
        payload["v"] = visualization_refs
    return json.dumps(payload, separators=(",", ":"))


def create_preview_token(
    session_id: str, project_id: str, visualization_refs: list[dict] | None = None
) -> str:
    payload = _preview_payload(
        session_id,
        project_id,
        int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
        visualization_refs,
    )
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = hmac.new(_PREVIEW_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _latest_report_request(db, session_id: str) -> str | None:
    message = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session_id,
        models.ChatMessage.role == "user",
    ).order_by(models.ChatMessage.created_at.desc(), models.ChatMessage.id.desc()).first()
    return message.content if message is not None else None


def _preview_visualizations(
    db, runtime, *, scope_kind: str, project_ids: list[str] | None, chart_selection: str | None
) -> tuple[list[dict], list[dict], list[dict]]:
    from services.report_visualization_service import select_conversation_visualizations

    selected, excluded = select_conversation_visualizations(
        db,
        session_id=runtime.session_id,
        scope_kind=scope_kind,
        scope_project_ids=project_ids,
        selection_text=chart_selection or _latest_report_request(db, runtime.session_id),
    )
    return (
        [item.reference() for item in selected],
        [{
            "title": item.report_payload()["title"],
            "section": item.domain,
            "reason": item.reason,
        } for item in selected],
        excluded,
    )


def create_project_progress_preview(
    db, runtime, project_id: str, chart_selection: str | None = None
) -> dict:
    dataset = build_project_progress_dataset(db, project_id)
    metadata = dataset["metadata"]
    summary = dataset["project_summary"]
    refs, selected, excluded = _preview_visualizations(
        db, runtime, scope_kind="project", project_ids=[project_id], chart_selection=chart_selection
    )
    return {
        "status": "awaiting_confirmation",
        "report_type": "Project Progress Report",
        "project_id": project_id,
        "project_name": metadata["project_name"],
        "reporting_cutoff": metadata["reporting_cutoff"],
        "formats": ["PDF", "DOCX"],
        "sections": [
            "Executive Summary",
            "P6 Schedule",
            "SAP Procurement",
            "TC Transmission",
            "Pulse Quality",
            "Capacity Milestones",
            "Named Risk Metrics",
            "Selected Conversation Charts",
            "Source Freshness",
        ],
        "source_freshness": metadata["source_freshness"],
        "missing_sources": metadata["missing_sources"],
        "progress_pct": summary.get("duration_percent_complete"),
        "conversation_charts": selected,
        "excluded_conversation_charts": excluded,
        "preview_token": create_preview_token(runtime.session_id, project_id, refs),
        "instruction": "Show this preview and ask the user to confirm. Do not generate the report in the same turn.",
    }


def create_portfolio_progress_preview(
    db, runtime, portfolio: str | None = None, chart_selection: str | None = None
) -> dict:
    dataset = build_portfolio_progress_dataset(db, portfolio)
    metadata = dataset["metadata"]
    refs, selected, excluded = _preview_visualizations(
        db, runtime, scope_kind="portfolio", project_ids=None, chart_selection=chart_selection
    )
    return {
        "status": "awaiting_confirmation",
        "report_type": "Portfolio Progress Report",
        "scope": metadata["portfolio"],
        "reporting_cutoff": metadata["reporting_cutoff"],
        "period": metadata["period"],
        "period_definition": metadata["period_definition"],
        "formats": ["PDF", "DOCX"],
        "sections": [
            "Executive Summary", "Portfolio KPI Summary", "Project Progress",
            "Schedule Exposure", "Selected Conversation Charts", "Source Freshness", "Limitations",
        ],
        "summary": dataset["summary"],
        "source_freshness": metadata["source_freshness"],
        "conversation_charts": selected,
        "excluded_conversation_charts": excluded,
        "preview_token": create_preview_token(runtime.session_id, _portfolio_token_scope(portfolio), refs),
        "instruction": "Show this preview and ask the user to confirm. Do not generate the report in the same turn.",
    }


def create_project_comparison_preview(
    db, runtime, project_ids: list[str], chart_selection: str | None = None
) -> dict:
    dataset = build_project_comparison_dataset(db, project_ids)
    metadata = dataset["metadata"]
    refs, selected, excluded = _preview_visualizations(
        db,
        runtime,
        scope_kind="comparison",
        project_ids=metadata["project_ids"],
        chart_selection=chart_selection,
    )
    return {
        "status": "awaiting_confirmation",
        "report_type": "Project Comparison Report",
        "project_ids": metadata["project_ids"],
        "project_names": metadata["project_names"],
        "reporting_cutoff": metadata["reporting_cutoff"],
        "formats": ["PDF", "DOCX"],
        "sections": [
            "Executive Summary", "Key Metrics Comparison", "Progress Visual",
            "Activity Composition", "Duration Profile", "Baseline Slip",
            "Selected Conversation Charts", "Limitations",
        ],
        "source_freshness": metadata["source_freshness"],
        "conversation_charts": selected,
        "excluded_conversation_charts": excluded,
        "preview_token": create_preview_token(
            runtime.session_id, _comparison_token_scope(metadata["project_ids"]), refs
        ),
        "instruction": (
            "Show this preview after the in-chat comparison and ask whether the user wants the "
            "PDF and DOCX generated. Do not generate files in the same turn."
        ),
    }


def validate_preview_token(token: str, session_id: str, project_id: str) -> dict:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(_PREVIEW_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload.get("s") != session_id or payload.get("p") != project_id:
            raise ValueError
        if set(payload) - {"s", "p", "e", "v"}:
            raise ValueError
        if not isinstance(payload.get("v", []), list):
            raise ValueError
        if int(payload["e"]) < int(datetime.utcnow().timestamp()):
            raise ValueError
        return payload
    except Exception as exc:
        raise ValueError("Report preview is invalid or expired. Create a new preview.") from exc


def cleanup_expired_artifacts(db) -> None:
    expired = db.query(models.ReportArtifact).filter(
        models.ReportArtifact.expires_at <= datetime.utcnow()
    ).all()
    for artifact in expired:
        try:
            Path(artifact.file_path).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(artifact)
    if expired:
        db.flush()


def _record_artifact(
    db, runtime, project_id: str, path: Path, fmt: str, report_type: str = REPORT_TYPE
) -> models.ReportArtifact:
    content = path.read_bytes()
    artifact = models.ReportArtifact(
        artifact_id=uuid4().hex,
        session_id=runtime.session_id,
        owner_subject=runtime.user_id,
        tenant_id=runtime.tenant_id,
        project_id=project_id,
        report_type=report_type,
        format=fmt,
        file_path=str(path.resolve()),
        filename=path.name,
        mime_type=(
            "application/pdf" if fmt == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(artifact)
    db.flush()
    return artifact


def _report_visualizations(
    db,
    runtime,
    *,
    preview_token: str | None,
    token_scope: str,
    scope_kind: str,
    project_ids: list[str] | None,
    chart_selection: str | None,
) -> list[dict]:
    """Resolve a frozen preview selection or select current conversation charts directly."""
    from services.report_visualization_service import (
        resolve_visualization_references,
        select_conversation_visualizations,
    )

    if preview_token:
        preview = validate_preview_token(preview_token, runtime.session_id, token_scope)
        return resolve_visualization_references(
            db, session_id=runtime.session_id, references=preview.get("v") or []
        )
    selected, _excluded = select_conversation_visualizations(
        db,
        session_id=runtime.session_id,
        scope_kind=scope_kind,
        scope_project_ids=project_ids,
        selection_text=chart_selection or _latest_report_request(db, runtime.session_id),
    )
    return [item.report_payload() for item in selected]


def generate_project_progress_report(
    db,
    runtime,
    project_id: str,
    preview_token: str | None = None,
    chart_selection: str | None = None,
) -> dict:
    cleanup_expired_artifacts(db)
    dataset = build_project_progress_dataset(db, project_id)
    dataset["conversation_visualizations"] = _report_visualizations(
        db, runtime, preview_token=preview_token, token_scope=project_id,
        scope_kind="project", project_ids=[project_id], chart_selection=chart_selection,
    )
    dataset["executive_summary"] = generate_narrative(dataset)
    from services.report_renderers import render_project_progress_docx, render_project_progress_pdf

    root = _artifact_root()
    stem = f"{project_id}_project_progress_{datetime.utcnow():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    pdf_path = root / f"{stem}.pdf"
    docx_path = root / f"{stem}.docx"
    render_project_progress_pdf(dataset, pdf_path)
    render_project_progress_docx(dataset, docx_path)
    artifacts = [
        _record_artifact(db, runtime, project_id, pdf_path, "pdf"),
        _record_artifact(db, runtime, project_id, docx_path, "docx"),
    ]
    db.commit()
    return {
        "status": "generated",
        "project_id": project_id,
        "project_name": dataset["metadata"]["project_name"],
        "expires_at": min(row.expires_at for row in artifacts).isoformat(),
        "downloads": [{
            "format": row.format.upper(),
            "filename": row.filename,
            "url": f"/akasha/api/reports/artifacts/{row.artifact_id}/download",
        } for row in artifacts],
        "instruction": "Return both download links exactly as Markdown links in the final answer.",
    }


def generate_portfolio_progress_report(
    db,
    runtime,
    preview_token: str | None = None,
    portfolio: str | None = None,
    chart_selection: str | None = None,
) -> dict:
    cleanup_expired_artifacts(db)
    dataset = build_portfolio_progress_dataset(db, portfolio)
    dataset["conversation_visualizations"] = _report_visualizations(
        db, runtime, preview_token=preview_token, token_scope=_portfolio_token_scope(portfolio),
        scope_kind="portfolio", project_ids=None, chart_selection=chart_selection,
    )
    summary = dataset["summary"]
    dataset["executive_summary"] = (
        f"The {dataset['metadata']['portfolio']} portfolio contains {summary['total_projects']} projects. "
        f"P6 schedule data is available for {summary['projects_with_p6']}; {summary['delayed']} are delayed, "
        f"{summary['on_track']} are on track, and {summary['completed']} are completed as of the latest "
        f"synchronized cutoff. This report is a current-month snapshot and does not represent a historical "
        f"planned-versus-actual progress curve."
    )
    from services.report_renderers import render_portfolio_progress_docx, render_portfolio_progress_pdf

    root = _artifact_root()
    stem = f"portfolio_progress_{datetime.utcnow():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    pdf_path = root / f"{stem}.pdf"
    docx_path = root / f"{stem}.docx"
    render_portfolio_progress_pdf(dataset, pdf_path)
    render_portfolio_progress_docx(dataset, docx_path)
    artifacts = [
        _record_artifact(db, runtime, PORTFOLIO_SCOPE_ID, pdf_path, "pdf", PORTFOLIO_REPORT_TYPE),
        _record_artifact(db, runtime, PORTFOLIO_SCOPE_ID, docx_path, "docx", PORTFOLIO_REPORT_TYPE),
    ]
    db.commit()
    return {
        "status": "generated",
        "report_type": "Portfolio Progress Report",
        "scope": dataset["metadata"]["portfolio"],
        "expires_at": min(row.expires_at for row in artifacts).isoformat(),
        "downloads": [{
            "format": row.format.upper(),
            "filename": row.filename,
            "url": f"/akasha/api/reports/artifacts/{row.artifact_id}/download",
        } for row in artifacts],
        "instruction": "Return both download links exactly as Markdown links in the final answer.",
    }


def generate_project_comparison_report(
    db,
    runtime,
    project_ids: list[str],
    preview_token: str | None = None,
    chart_selection: str | None = None,
) -> dict:
    scope = _comparison_token_scope(project_ids)
    cleanup_expired_artifacts(db)
    dataset = build_project_comparison_dataset(db, project_ids)
    dataset["conversation_visualizations"] = _report_visualizations(
        db, runtime, preview_token=preview_token, token_scope=scope,
        scope_kind="comparison", project_ids=dataset["metadata"]["project_ids"],
        chart_selection=chart_selection,
    )
    rows = dataset["projects"]
    highest_progress = max(rows, key=lambda row: float(row.get("progress_pct") or 0))
    highest_slip = max(rows, key=lambda row: int(row.get("baseline_slip_days") or 0))
    dataset["executive_summary"] = (
        f"{highest_progress['project_name']} has the highest current progress at "
        f"{highest_progress.get('progress_pct')}%. {highest_slip['project_name']} has the largest "
        f"direct forecast-versus-baseline finish slippage at "
        f"{highest_slip.get('baseline_slip_days')} calendar days. The comparison uses the latest "
        "available synchronized P6 snapshot for each project; source cutoff dates are shown in the detail table."
    )
    from services.report_renderers import (
        render_project_comparison_docx,
        render_project_comparison_pdf,
    )

    root = _artifact_root()
    stem = f"project_comparison_{datetime.utcnow():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    pdf_path = root / f"{stem}.pdf"
    docx_path = root / f"{stem}.docx"
    render_project_comparison_pdf(dataset, pdf_path)
    render_project_comparison_docx(dataset, docx_path)
    artifacts = [
        _record_artifact(db, runtime, COMPARISON_SCOPE_ID, pdf_path, "pdf", COMPARISON_REPORT_TYPE),
        _record_artifact(db, runtime, COMPARISON_SCOPE_ID, docx_path, "docx", COMPARISON_REPORT_TYPE),
    ]
    db.commit()
    return {
        "status": "generated",
        "report_type": "Project Comparison Report",
        "project_ids": dataset["metadata"]["project_ids"],
        "project_names": dataset["metadata"]["project_names"],
        "expires_at": min(row.expires_at for row in artifacts).isoformat(),
        "downloads": [{
            "format": row.format.upper(),
            "filename": row.filename,
            "url": f"/akasha/api/reports/artifacts/{row.artifact_id}/download",
        } for row in artifacts],
        "instruction": "Return both download links exactly as Markdown links in the final answer.",
    }
