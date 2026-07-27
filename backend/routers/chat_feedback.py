from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from auth_claims import AuthenticatedIdentity
from database import get_db
from security import get_current_user
from services.chat_feedback_service import submit_message_feedback


router = APIRouter(prefix="/api/chat/messages", tags=["Chat Feedback"])


class ChatFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    feedback_type: Literal["thumbs_up", "thumbs_down"]


@router.post("/{message_id}/feedback")
def submit_feedback(
    message_id: int,
    req: ChatFeedbackRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    feedback, changed = submit_message_feedback(
        db,
        message_id=message_id,
        user=user,
        feedback_type=req.feedback_type,
    )
    return {"id": feedback.id, "changed": changed}
