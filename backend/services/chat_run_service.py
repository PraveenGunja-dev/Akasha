from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth_claims import AuthenticatedIdentity
import models
from services.freshness_service import build_answer_provenance


ACTIVE_RUN_STATUSES = {"pending", "running", "cancel_requested"}
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "interrupted"}


def create_chat_run(
    db: Session,
    *,
    session: models.ChatSession,
    user: AuthenticatedIdentity,
    request_id: str,
    run_id: str,
    engine: str,
    content: str,
) -> tuple[models.ChatMessage, models.ChatMessage, models.ChatRun]:
    active = db.query(models.ChatRun.id).filter(
        models.ChatRun.session_id == session.session_id,
        models.ChatRun.status.in_(ACTIVE_RUN_STATUSES),
    ).first()
    if active is not None:
        raise HTTPException(status_code=409, detail="This chat already has an active response.")

    user_message = models.ChatMessage(
        session_id=session.session_id,
        role="user",
        content=content,
        status="completed",
        run_id=run_id,
        engine=engine,
        request_id=request_id,
        completed_at=datetime.utcnow(),
    )
    assistant_message = models.ChatMessage(
        session_id=session.session_id,
        role="assistant",
        content="",
        status="running",
        run_id=run_id,
        engine=engine,
        request_id=request_id,
    )
    db.add_all([user_message, assistant_message])
    db.flush()

    run = models.ChatRun(
        run_id=run_id,
        session_id=session.session_id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        request_id=request_id,
        engine=engine,
        status="running",
    )
    db.add(run)
    if not session.title or session.title == "New conversation":
        session.title = content[:100] or "New conversation"
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    db.refresh(run)
    return user_message, assistant_message, run


def complete_chat_run(
    db: Session,
    *,
    run_id: str,
    content: str,
    intent_type: str,
    project_ids: list[str],
    domains: list[str],
    data_as_of,
    sources: list[str],
    evidence: list[dict] | None,
    visualizations: list[dict],
    latency_ms: int,
    checkpoint_id: str | None = None,
    model_name: str | None = None,
) -> models.ChatMessage:
    run = db.query(models.ChatRun).filter(models.ChatRun.run_id == run_id).first()
    if run is None:
        raise RuntimeError("Chat run not found.")
    db.refresh(run)
    if run.status in {"cancel_requested", "cancelled", "interrupted"}:
        raise RuntimeError("Chat run can no longer complete.")

    message = db.query(models.ChatMessage).filter(
        models.ChatMessage.id == run.assistant_message_id
    ).one()
    now = datetime.utcnow()
    message.content = content
    message.status = "completed"
    message.intent_type = intent_type
    message.project_ids = ",".join(project_ids) if project_ids else None
    message.data_domains = ",".join(domains) if domains else None
    provenance = build_answer_provenance(
        db,
        sources,
        evidence=evidence or (),
        answer_generated_at=now,
    )
    effective_data_as_of = data_as_of or provenance["data_as_of"]
    if isinstance(effective_data_as_of, str):
        effective_data_as_of = datetime.fromisoformat(effective_data_as_of.replace("Z", "+00:00")).replace(tzinfo=None)
    message.data_as_of = effective_data_as_of
    message.sources_used = provenance
    message.visualizations = visualizations or None
    message.latency_ms = latency_ms
    message.completed_at = now
    message.error_code = None
    message.model = model_name
    run.status = "completed"
    run.error_code = None
    run.graph_checkpoint_id = checkpoint_id
    run.model = model_name
    run.updated_at = now
    run.completed_at = now
    run.session.updated_at = now
    db.commit()
    db.refresh(message)
    return message


def finish_chat_run(
    db: Session,
    *,
    run_id: str,
    status: str,
    error_code: str,
    partial_content: str = "",
) -> models.ChatMessage | None:
    if status not in {"failed", "cancelled", "interrupted"}:
        raise ValueError("Invalid terminal chat status.")
    run = db.query(models.ChatRun).filter(models.ChatRun.run_id == run_id).first()
    if run is None:
        return None
    db.refresh(run)
    if run.status == "completed":
        return db.query(models.ChatMessage).filter(
            models.ChatMessage.id == run.assistant_message_id
        ).first()

    now = datetime.utcnow()
    run.status = status
    run.error_code = error_code
    run.updated_at = now
    run.completed_at = now
    message = db.query(models.ChatMessage).filter(
        models.ChatMessage.id == run.assistant_message_id
    ).first()
    if message is not None:
        message.content = partial_content
        message.status = status
        message.error_code = error_code
        message.completed_at = now
    user_message = db.query(models.ChatMessage).filter(
        models.ChatMessage.id == run.user_message_id
    ).first()
    if user_message is not None:
        user_message.status = status
        user_message.error_code = error_code
    run.session.updated_at = now
    db.commit()
    return message


def request_chat_run_cancellation(
    db: Session,
    *,
    run_id: str,
    user: AuthenticatedIdentity,
) -> models.ChatRun:
    run = db.query(models.ChatRun).join(
        models.ChatSession,
        models.ChatSession.session_id == models.ChatRun.session_id,
    ).filter(
        models.ChatRun.run_id == run_id,
        models.ChatSession.owner_subject == user.subject,
        models.ChatSession.tenant_id == user.tenant_id,
        models.ChatSession.is_active.is_(True),
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Chat run not found.")
    if run.status in TERMINAL_RUN_STATUSES:
        return run
    run.status = "cancel_requested"
    run.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(run)
    return run


def chat_run_is_cancelled(db: Session, run_id: str) -> bool:
    run = db.query(models.ChatRun).filter(models.ChatRun.run_id == run_id).first()
    if run is None:
        return True
    db.refresh(run)
    return run.status in {"cancel_requested", "cancelled", "interrupted"}
