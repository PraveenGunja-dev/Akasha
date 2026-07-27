"""Application-owned feedback helpers."""

import re
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

import models

logger = logging.getLogger(__name__)


def normalize_question(question: str) -> str:
    """Normalize a question into a reusable pattern.
    
    "What is the SPI for MANDVI?" → "what is the spi for {project}"
    "How many activities are delayed in FY25-BAIYA?" → "how many activities are delayed in {project}"
    """
    q = question.lower().strip()
    
    # Remove specific project names (they'll be replaced with {project})
    # Match common project ID patterns: FY25-XXX, MANDVI, etc.
    q = re.sub(r'fy\d{2}-\w+', '{project}', q)
    q = re.sub(r'[A-Z]{3,}(?:-\w+)?', '{project}', question.lower().strip())
    
    # Remove specific numbers that might be project-specific
    q = re.sub(r'\b\d{4,}\b', '{number}', q)
    
    # Clean up whitespace
    q = re.sub(r'\s+', ' ', q).strip()
    
    return q


def store_feedback(
    db: Session,
    message_id: int,
    feedback_type: str,
    correction_text: str = None,
    project_id: str = None,
    question_pattern: str = None,
):
    """Store user feedback on a chatbot response.
    
    Args:
        message_id: The chat_message.id being rated
        feedback_type: 'thumbs_up' | 'thumbs_down' | 'correction'
        correction_text: What the right answer should have been
        project_id: Which project this relates to
        question_pattern: Normalized question pattern for future matching
    """
    feedback = models.ChatFeedback(
        message_id=message_id,
        feedback_type=feedback_type,
        correction_text=correction_text,
        project_id=project_id,
        question_pattern=question_pattern,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    
    logger.info(
        f"Feedback stored: type={feedback_type}, project={project_id}, "
        f"pattern={question_pattern[:50] if question_pattern else 'N/A'}"
    )
    return feedback


def get_relevant_feedback(
    db: Session,
    project_id: str = None,
    question: str = None,
    limit: int = 5,
) -> list[dict]:
    """Return previous corrections relevant to a project or similar question."""
    query = db.query(models.ChatFeedback).filter(
        models.ChatFeedback.correction_text.isnot(None)
    )
    if project_id:
        query = query.filter(models.ChatFeedback.project_id == project_id)
    rows = query.order_by(desc(models.ChatFeedback.created_at)).limit(limit * 4).all()
    normalized = normalize_question(question) if question else None
    ranked = sorted(
        rows,
        key=lambda item: _pattern_similarity(item.question_pattern, normalized)
        if normalized and item.question_pattern else 0,
        reverse=True,
    )
    return [{
        "feedback_type": item.feedback_type,
        "correction_text": item.correction_text,
        "project_id": item.project_id,
        "question_pattern": item.question_pattern,
    } for item in ranked[:limit]]


def build_memory_context(db: Session, project_id: str = None, question: str = None) -> str:
    """Build runtime context from current time and relevant prior corrections."""
    current_time = datetime.now().strftime("%I:%M %p")
    feedback = get_relevant_feedback(db, project_id, question)
    context = f"Current System Time: {current_time}\n"
    if feedback:
        context += "\nRelevant corrections from previous user feedback:\n"
        for item in feedback:
            context += f"- {item['correction_text']}\n"
    return context


def get_feedback_stats(db: Session) -> dict:
    """Get aggregate feedback statistics."""
    total = db.query(models.ChatFeedback).count()
    thumbs_up = db.query(models.ChatFeedback).filter(
        models.ChatFeedback.feedback_type == "thumbs_up"
    ).count()
    thumbs_down = db.query(models.ChatFeedback).filter(
        models.ChatFeedback.feedback_type == "thumbs_down"
    ).count()
    corrections = db.query(models.ChatFeedback).filter(
        models.ChatFeedback.feedback_type == "correction"
    ).count()
    
    return {
        "total": total,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "corrections": corrections,
        "satisfaction_pct": round(thumbs_up / total * 100, 1) if total > 0 else None,
    }


def _pattern_similarity(pattern1: str, pattern2: str) -> float:
    """Simple word-overlap similarity between two question patterns."""
    if not pattern1 or not pattern2:
        return 0.0
    words1 = set(pattern1.split())
    words2 = set(pattern2.split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)
