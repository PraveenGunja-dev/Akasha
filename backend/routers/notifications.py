from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
import models
from services.p6_service import P6Service
from typing import Dict, Any, Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tasks.ai_suggestion_task import populate_missing_ai_suggestions_bg

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

class ThreadMessage(BaseModel):
    message: str
    sender: str = "User"

class PushPayload(BaseModel):
    updates: Dict[str, Any]
    resources: Optional[Dict[str, Any]] = None
    delete_thread: bool = False

@router.get("/")
def get_notifications(
    background_tasks: BackgroundTasks, 
    skip: int = 0, 
    limit: int = 50, 
    tab: str = "All", 
    project_id: Optional[str] = None,
    phase: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Notification)
    if tab != "All":
        if tab == "Transmission":
            query = query.filter(models.Notification.module == "Transmission")
        else:
            query = query.filter(models.Notification.category == tab)
            
    if project_id or (phase and phase != "ALL"):
        mapping_query = db.query(models.ProjectMapping.project)
        if project_id:
            mapping_query = mapping_query.filter(models.ProjectMapping.project_id == project_id)
        if phase and phase != "ALL":
            is_comm = True if phase == "Commissioned" else False
            mapping_query = mapping_query.filter(models.ProjectMapping.is_commissioned == is_comm)
            
        allowed_projects = [m[0] for m in mapping_query.all()]
        # Include Global notifications (project_name is None) along with filtered projects
        query = query.filter((models.Notification.project_name.in_(allowed_projects)) | (models.Notification.project_name == None))
            
    notifs = query.order_by(models.Notification.created_at.desc()).offset(skip).limit(limit).all()
    
    project_names = {n.project_name for n in notifs if n.project_name}
    mapping_dict = {}
    if project_names:
        mappings = db.query(models.ProjectMapping.project, models.ProjectMapping.project_name_from_p6).filter(
            models.ProjectMapping.project.in_(project_names)
        ).all()
        mapping_dict = {m.project: m.project_name_from_p6 for m in mappings}
        
    results = []
    for n in notifs:
        n_dict = {c.name: getattr(n, c.name) for c in n.__table__.columns}
        n_dict["p6_project_name"] = mapping_dict.get(n.project_name, n.project_name)
        results.append(n_dict)
        
    # Trigger background task to populate any missing AI suggestions
    background_tasks.add_task(populate_missing_ai_suggestions_bg)
    return results

@router.post("/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db)):
    notif = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if notif:
        notif.is_read = True
        db.commit()
    return {"status": "success"}

@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(models.Notification).filter(models.Notification.is_read == False).update({"is_read": True})
    db.commit()
    return {"status": "success"}

@router.post("/{notification_id}/action")
def update_action_status(notification_id: int, status: str, db: Session = Depends(get_db)):
    notif = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if notif:
        notif.action_status = status
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Notification not found")

@router.get("/{notification_id}/ai-suggestion")
def get_ai_suggestion(notification_id: int, db: Session = Depends(get_db)):
    notif = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    if notif.ai_suggestion:
        return {"suggestion": notif.ai_suggestion}
        
    # Generate synchronously if missing
    from tasks.ai_suggestion_task import generate_ai_suggestion_for_notification
    generate_ai_suggestion_for_notification(notification_id)
    
    # Reload from DB
    db.refresh(notif)
    fallback = "Fast-track parallel works or assign an extra crew to recover the delay."
    return {"suggestion": notif.ai_suggestion or fallback}

@router.get("/{notification_id}/thread")
def get_thread(notification_id: int, db: Session = Depends(get_db)):
    threads = db.query(models.NotificationThread).filter(models.NotificationThread.notification_id == notification_id).order_by(models.NotificationThread.created_at.asc()).all()
    return threads

@router.post("/{notification_id}/thread")
def post_thread_message(notification_id: int, msg: ThreadMessage, db: Session = Depends(get_db)):
    notif = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if notif:
        thread = models.NotificationThread(
            notification_id=notification_id,
            sender=msg.sender,
            message=msg.message
        )
        db.add(thread)
        db.commit()
        db.refresh(thread)
        return thread
    raise HTTPException(status_code=404, detail="Notification not found")

@router.post("/{notification_id}/push")
def push_to_p6(notification_id: int, payload: PushPayload, db: Session = Depends(get_db)):
    notif = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if notif and notif.p6_object_id and notif.p6_type:
        p6 = P6Service()
        result = {"success": False, "message": "Unknown P6 Type"}
        
        updates = payload.updates
        if payload.resources:
            updates['resources'] = payload.resources

        if notif.p6_type == "Activity" or notif.p6_type == "ResourceAssignment":
            result = p6.update_activity_in_p6(db, notif.p6_object_id, updates)
        elif notif.p6_type == "Project":
            result = p6.update_project_in_p6(db, notif.p6_object_id, updates)
            
        if result.get("success"):
            notif.action_status = "Resolved"
            if payload.delete_thread:
                db.query(models.NotificationThread).filter(models.NotificationThread.notification_id == notification_id).delete()
            db.commit()
            return result
        else:
            raise HTTPException(status_code=500, detail=result.get("message"))
            
    raise HTTPException(status_code=404, detail="Notification or P6 Object not found")
