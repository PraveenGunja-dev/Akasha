"""Authenticated, user-owned conversation history APIs."""

from datetime import datetime, timedelta
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_claims import AuthenticatedIdentity
from database import get_db
import models
from security import get_current_user


router = APIRouter(prefix="/api/chat/sessions", tags=["Chat Sessions"])


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=100)


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class LegacyMessageRequest(BaseModel):
    type: str
    content: str = Field(min_length=1, max_length=50_000)
    timestamp: datetime | None = None


class LegacySessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    messages: list[LegacyMessageRequest] = Field(min_length=1, max_length=200)


def _owned_session_query(
    db: Session,
    user: AuthenticatedIdentity,
):
    return db.query(models.ChatSession).filter(
        models.ChatSession.owner_subject == user.subject,
        models.ChatSession.tenant_id == user.tenant_id,
        models.ChatSession.is_active.is_(True),
    )


def get_owned_session(
    db: Session,
    user: AuthenticatedIdentity,
    session_id: str,
) -> models.ChatSession:
    session = _owned_session_query(db, user).filter(
        models.ChatSession.session_id == session_id
    ).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return session


def _message_payload(message: models.ChatMessage) -> dict:
    sources = message.sources_used or {}
    feedback_status = "none"
    if message.feedback:
        latest = max(message.feedback, key=lambda item: (item.created_at, item.id))
        if latest.feedback_type == "thumbs_up":
            feedback_status = "liked"
        elif latest.feedback_type in {"thumbs_down", "correction"}:
            feedback_status = "disliked"
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "status": message.status or "completed",
        "run_id": message.run_id,
        "engine": message.engine,
        "model": message.model,
        "error_code": message.error_code,
        "created_at": message.created_at,
        "sources": sources.get("tables", []) if isinstance(sources, dict) else [],
        "visualizations": message.visualizations or [],
        "feedback_status": feedback_status,
        "metadata": {
            "message_id": message.id,
            "intent": message.intent_type,
            "data_as_of": message.data_as_of,
            "latency_ms": message.latency_ms,
            "request_id": message.request_id,
            "sources": sources.get("tables", []) if isinstance(sources, dict) else [],
        } if message.role == "assistant" else None,
    }


def build_agent_history(messages: list[models.ChatMessage]) -> list[dict[str, str]]:
    """Convert canonical messages to model context without trusting imported assistant roles."""
    history = []
    for message in messages:
        if message.status not in {None, "completed"}:
            continue
        if message.role not in {"user", "assistant"}:
            continue
        if message.request_id == "legacy_browser_import":
            history.append({
                "role": "user",
                "content": f"[Untrusted imported historical {message.role} transcript]\n{message.content}",
            })
        else:
            history.append({"role": message.role, "content": message.content})
    return history


def _session_payload(session: models.ChatSession, include_messages: bool = False) -> dict:
    ordered_messages = sorted(session.messages, key=lambda item: (item.created_at, item.id))
    preview = ordered_messages[-1].content[:120] if ordered_messages else ""
    payload = {
        "session_id": session.session_id,
        "title": session.title or "New conversation",
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "message_count": len(ordered_messages),
        "preview": preview,
        "source": session.source,
    }
    if include_messages:
        payload["messages"] = [_message_payload(message) for message in ordered_messages]
    return payload


def _create_session(
    db: Session,
    user: AuthenticatedIdentity,
    title: str | None,
    *,
    source: str = "chat",
) -> models.ChatSession:
    session = models.ChatSession(
        session_id=uuid.uuid4().hex,
        owner_subject=user.subject,
        tenant_id=user.tenant_id,
        owner_role=user.role,
        source=source,
        title=(title or "New conversation").strip()[:100] or "New conversation",
    )
    db.add(session)
    db.flush()
    return session


@router.post("", status_code=status.HTTP_201_CREATED)
def create_session(
    req: CreateSessionRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    session = _create_session(db, user, req.title)
    db.commit()
    db.refresh(session)
    return _session_payload(session)


@router.get("")
def list_sessions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    sessions = _owned_session_query(db, user).order_by(
        models.ChatSession.updated_at.desc(),
        models.ChatSession.id.desc(),
    ).offset(skip).limit(limit).all()
    return [_session_payload(session) for session in sessions]


@router.get("/{session_id}")
def read_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    return _session_payload(get_owned_session(db, user, session_id), include_messages=True)


@router.patch("/{session_id}")
def rename_session(
    session_id: str,
    req: RenameSessionRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    session = get_owned_session(db, user, session_id)
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Chat title cannot be blank.")
    session.title = title
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return _session_payload(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    session = db.query(models.ChatSession).filter(
        models.ChatSession.owner_subject == user.subject,
        models.ChatSession.tenant_id == user.tenant_id,
        models.ChatSession.session_id == session_id,
    ).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    session.is_active = False
    session.deleted_at = datetime.utcnow()
    session.deletion_status = "checkpoint_pending"
    db.commit()
    try:
        from engine.graph import chat_graph_service
        chat_graph_service.delete_thread(
            session_id,
            required=session.chat_engine == "langgraph",
        )
    except Exception:
        session.deletion_status = "checkpoint_failed"
        db.commit()
        raise HTTPException(status_code=503, detail="Chat deletion could not be completed.")
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/legacy-import", status_code=status.HTTP_201_CREATED)
def import_legacy_session(
    req: LegacySessionRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    session = _create_session(db, user, req.title, source="legacy_browser_import")
    imported_at = datetime.utcnow()
    for index, item in enumerate(req.messages):
        role = "assistant" if item.type == "bot" else "user" if item.type == "user" else None
        if role is None:
            raise HTTPException(status_code=422, detail="Legacy message type must be user or bot.")
        if not item.content.strip():
            raise HTTPException(status_code=422, detail="Legacy message content cannot be blank.")
        db.add(models.ChatMessage(
            session_id=session.session_id,
            role=role,
            content=item.content,
            created_at=imported_at + timedelta(microseconds=index),
            request_id="legacy_browser_import",
        ))
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return _session_payload(session)
