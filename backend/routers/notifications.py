from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
import models
from services.p6_service import P6Service
from typing import Dict, Any, Optional

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

class ThreadMessage(BaseModel):
    message: str
    sender: str = "User"

class PushPayload(BaseModel):
    updates: Dict[str, Any]
    resources: Optional[Dict[str, Any]] = None
    delete_thread: bool = False

@router.get("/")
def get_notifications(db: Session = Depends(get_db)):
    notifs = db.query(models.Notification).order_by(models.Notification.created_at.desc()).limit(500).all()
    return notifs

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
