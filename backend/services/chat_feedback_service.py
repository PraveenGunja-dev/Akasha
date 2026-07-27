from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth_claims import AuthenticatedIdentity
import models


def submit_message_feedback(
    db: Session,
    *,
    message_id: int,
    user: AuthenticatedIdentity,
    feedback_type: str,
    issue_category: str | None = None,
    correction_text: str | None = None,
) -> tuple[models.ChatFeedback, bool]:
    if feedback_type not in {"thumbs_up", "thumbs_down"}:
        raise ValueError("Invalid feedback type.")
    message = db.query(models.ChatMessage).join(
        models.ChatSession,
        models.ChatSession.session_id == models.ChatMessage.session_id,
    ).filter(
        models.ChatMessage.id == message_id,
        models.ChatSession.owner_subject == user.subject,
        models.ChatSession.tenant_id == user.tenant_id,
        models.ChatSession.is_active.is_(True),
    ).one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail="Chat message not found.")
    if message.role != "assistant":
        raise HTTPException(status_code=422, detail="Feedback is only accepted for assistant messages.")

    existing = db.query(models.ChatFeedback).filter(
        models.ChatFeedback.message_id == message_id
    ).order_by(models.ChatFeedback.id.desc()).first()
    if existing is not None and existing.feedback_type == feedback_type:
        return existing, False
    feedback = models.ChatFeedback(
        message_id=message_id,
        feedback_type=feedback_type,
        correction_text=correction_text,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback, True
