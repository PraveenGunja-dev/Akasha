from sqlalchemy.orm import Session
from database import SessionLocal
import models
import logging
from routers.ai import call_groq, call_azure_openai_curl, get_ai_provider

logger = logging.getLogger(__name__)

def generate_ai_suggestion_for_notification(notif_id: int):
    db = SessionLocal()
    try:
        notif = db.query(models.Notification).filter(models.Notification.id == notif_id).first()
        if not notif or notif.ai_suggestion:
            return

        logger.info(f"Generating AI suggestion for notification {notif_id}")
        
        # 1. Gather full project context from DB
        project_name = notif.project_name
        
        project_context = ""
        if project_name:
            # Get P6 project data
            p6_proj = db.query(models.P6Project).filter(
                (models.P6Project.name == project_name) | 
                (models.P6Project.project_id == project_name)
            ).first()
            
            # Get Project Mapping
            mapping = db.query(models.ProjectMapping).filter(
                (models.ProjectMapping.project == project_name) | 
                (models.ProjectMapping.project_name_from_p6 == project_name) |
                (models.ProjectMapping.project_id == project_name)
            ).first()

            if p6_proj:
                project_context += f"- SPI: {p6_proj.schedule_performance_index}, CPI: {p6_proj.cost_performance_index}\n"
                project_context += f"- Progress: {p6_proj.duration_percent_complete}%\n"
                if p6_proj.baseline_finish_date and p6_proj.finish_date:
                    project_context += f"- Baseline Finish: {p6_proj.baseline_finish_date.strftime('%Y-%m-%d')}, Current Finish: {p6_proj.finish_date.strftime('%Y-%m-%d')}\n"
            
            if mapping:
                project_context += f"- Category: {mapping.category}, Capacity: {mapping.capacity_mwac} MW\n"

        prompt = f"""You are a highly specialized Senior Project Director and deeply technical expert in SAP, Primavera P6, and large-scale Transmission & Renewable Energy infrastructure.
Your job is to analyze this operational notification and provide a highly specific, tactical, and immediately actionable instruction (max 15-20 words) to resolve the issue. 
Do NOT be generic. Use precise engineering, procurement, and scheduling terminology (e.g. crashing schedules, fast-tracking, expediting POs, mobilizing specific crews, re-sequencing logic in P6).

Notification details:
- Project: {notif.project_name or 'Unknown'}
- Type: {notif.change_type}
- Block/Activity: {notif.block or ''} {notif.activity_name or ''}
- Message: {notif.message}

Project Context from Database:
{project_context if project_context else "No extended database context available."}

Provide ONLY the suggestion text, no conversational filler."""

        messages = [{"role": "user", "content": prompt}]
        
        provider = get_ai_provider()
        suggestion = "Fast-track parallel works or assign an extra crew to recover the delay." # fallback
        try:
            if provider == "azure":
                suggestion = call_azure_openai_curl(messages, temperature=0.3, max_tokens=60)
            else:
                suggestion = call_groq(messages, temperature=0.3, max_tokens=60)
        except Exception as e:
            logger.error(f"AI generation failed: {e}")

        # Clean up output
        suggestion = suggestion.strip().replace('"', '')
        
        # Save to DB
        notif.ai_suggestion = suggestion
        db.commit()
        logger.info(f"Saved AI suggestion for notification {notif_id}: {suggestion}")
        
    finally:
        db.close()

def populate_missing_ai_suggestions_bg():
    db = SessionLocal()
    try:
        # Get up to 10 recent notifications without suggestions
        notifs = db.query(models.Notification).filter(
            models.Notification.ai_suggestion == None,
            models.Notification.change_type.in_(["Date Delay", "Critical Slip", "Budget Exceeded", "New Risk Assignment", "Date Change"])
        ).order_by(models.Notification.created_at.desc()).limit(10).all()
        
        notif_ids = [n.id for n in notifs]
    finally:
        db.close()
        
    for nid in notif_ids:
        generate_ai_suggestion_for_notification(nid)
