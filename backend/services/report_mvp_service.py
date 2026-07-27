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

from sqlalchemy import func, or_

import models
from engine.kpi_engine import compute_project_kpis
from engine.model_provider import get_model_provider
from engine.tools.p6_tools import p6_get_activities, p6_get_project_summary
from engine.tools.sap_tools import sap_get_po_summary
from engine.tools.tc_tools import tc_get_project_lines


_PREVIEW_SECRET = secrets.token_bytes(32)
REPORT_TYPE = "project_progress"


def _artifact_root() -> Path:
    root = Path(os.getenv(
        "AKASHA_REPORT_ARTIFACT_DIR",
        str(Path(__file__).resolve().parents[1] / "report_artifacts"),
    )).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _quality_summary(db, project) -> dict:
    names = [value for value in {project.project_id, project.name} if value]
    nc_filter = or_(*[models.PulseNC.project_name.ilike(f"%{name}%") for name in names])
    rfi_filter = or_(*[models.PulseRFI.project_name.ilike(f"%{name}%") for name in names])
    ncs = db.query(models.PulseNC).filter(nc_filter).all()
    rfis = db.query(models.PulseRFI).filter(rfi_filter).all()
    return {
        "has_data": bool(ncs or rfis),
        "non_conformances": len(ncs),
        "open_non_conformances": sum(1 for row in ncs if (row.status or "").lower() != "completed"),
        "rfis": len(rfis),
        "open_rfis": sum(1 for row in rfis if (row.status or "").lower() != "completed"),
        "last_synced_at": max(
            [row.last_synced_at for row in [*ncs, *rfis] if row.last_synced_at],
            default=None,
        ),
    }


def build_project_progress_dataset(db, project_id: str) -> dict:
    project = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()
    if project is None:
        raise ValueError("Unknown project.")
    summary = p6_get_project_summary(db, project_id)
    kpis = compute_project_kpis(db, project_id)
    procurement = sap_get_po_summary(db, project_id)
    transmission = tc_get_project_lines(db, project_id)
    quality = _quality_summary(db, project)
    in_progress = p6_get_activities(db, project_id, "in_progress", 20, 0)
    delayed = kpis.get("schedule", {})
    source_freshness = {
        "P6": summary.get("last_synced_at"),
        "SAP": procurement.get("last_synced_at") or procurement.get("_synced_at"),
        "TC": transmission.get("last_synced_at") or transmission.get("_synced_at"),
        "Pulse": quality.get("last_synced_at"),
    }
    missing_sources = [
        name for name, available in {
            "P6": summary is not None,
            "SAP": bool(procurement and procurement.get("has_data", True)),
            "TC": bool(transmission and transmission.get("has_data")),
            "Pulse": quality["has_data"],
        }.items() if not available
    ]
    return {
        "metadata": {
            "report_type": REPORT_TYPE,
            "project_id": project_id,
            "project_name": summary["project_name"],
            "generated_at": datetime.utcnow().isoformat(),
            "reporting_cutoff": summary.get("data_date"),
            "source_freshness": source_freshness,
            "missing_sources": missing_sources,
        },
        "project_summary": summary,
        "schedule": delayed,
        "in_progress_activities": in_progress,
        "procurement": procurement,
        "transmission": transmission,
        "quality": quality,
    }


def _fallback_narrative(dataset: dict) -> str:
    summary = dataset["project_summary"]
    schedule = dataset["schedule"]
    project_name = summary.get("project_name") or dataset.get("metadata", {}).get("project_name") or "The project"
    text = (
        f"{project_name} is active and {schedule.get('progress_pct')}% complete by P6 duration progress, "
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


def _preview_payload(session_id: str, project_id: str, expires: int) -> str:
    return json.dumps({"s": session_id, "p": project_id, "e": expires}, separators=(",", ":"))


def create_preview_token(session_id: str, project_id: str) -> str:
    payload = _preview_payload(session_id, project_id, int((datetime.utcnow() + timedelta(hours=1)).timestamp()))
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = hmac.new(_PREVIEW_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def create_project_progress_preview(db, runtime, project_id: str) -> dict:
    dataset = build_project_progress_dataset(db, project_id)
    metadata = dataset["metadata"]
    summary = dataset["project_summary"]
    return {
        "status": "awaiting_confirmation",
        "report_type": "Project Progress Report",
        "project_id": project_id,
        "project_name": metadata["project_name"],
        "reporting_cutoff": metadata["reporting_cutoff"],
        "formats": ["PDF", "DOCX"],
        "sections": ["Executive Summary", "P6 Schedule", "SAP Procurement", "TC Transmission", "Pulse Quality", "Source Freshness"],
        "source_freshness": metadata["source_freshness"],
        "missing_sources": metadata["missing_sources"],
        "progress_pct": summary.get("duration_percent_complete"),
        "preview_token": create_preview_token(runtime.session_id, project_id),
        "instruction": "Show this preview and ask the user to confirm. Do not generate the report in the same turn.",
    }


def validate_preview_token(token: str, session_id: str, project_id: str) -> None:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(_PREVIEW_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload != json.loads(_preview_payload(session_id, project_id, payload["e"])):
            raise ValueError
        if int(payload["e"]) < int(datetime.utcnow().timestamp()):
            raise ValueError
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


def _record_artifact(db, runtime, project_id: str, path: Path, fmt: str) -> models.ReportArtifact:
    content = path.read_bytes()
    artifact = models.ReportArtifact(
        artifact_id=uuid4().hex,
        session_id=runtime.session_id,
        owner_subject=runtime.user_id,
        tenant_id=runtime.tenant_id,
        project_id=project_id,
        report_type=REPORT_TYPE,
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


def generate_project_progress_report(db, runtime, project_id: str, preview_token: str) -> dict:
    validate_preview_token(preview_token, runtime.session_id, project_id)
    cleanup_expired_artifacts(db)
    dataset = build_project_progress_dataset(db, project_id)
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
