"""Alerts the signed-in user was emailed and must acknowledge
(services/email_notify/alerts.py).

The "Acknowledge in Akasha" button in an alert email opens /alerts/<id>.
Sign-in identifies the person; only a To recipient of the alert (or an
administrator recording it for one) can acknowledge, and the page needs a
deliberate click - a mail scanner fetching the link acknowledges nothing.
"""
from datetime import date, timedelta
from urllib.parse import quote
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from database import get_db
from routers.auth import client_ip, current_user
from services import access, security
from services.email_notify import alerts as A, context as C

from fastapi import Depends as _Depends
from services.demo_scope import see_demo

# Module Ordering: demo projects are visible here (services/demo_scope.py).
router = APIRouter(prefix="/api/alerts", tags=["Alerts"], dependencies=[_Depends(see_demo)])
ADMIN_PERM = "email.manage"


def _iso(dt) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _names(db: Session) -> dict:
    """email -> display name, from the distribution groups and Akasha users."""
    out = {}
    for r in db.query(models.EmailRecipient).all():
        if r.name:
            out[r.email.lower()] = r.name
    for u in db.query(models.AkashaUser).filter(models.AkashaUser.email.isnot(None)).all():
        out.setdefault(u.email.lower(), u.display_name or u.username)
    return out


def serialize(db: Session, a: "models.EmailAlert", names: Optional[dict] = None, full: bool = False) -> dict:
    names = names if names is not None else _names(db)
    t = db.get(models.EmailTemplate, a.template_key)
    recips = A.recipients(db, a)
    row = {
        "id": a.id, "kind": a.kind, "status": a.status, "test": bool(a.test),
        "template_key": a.template_key, "template_name": t.name if t else a.template_key,
        "severity": t.severity if t else None,
        "project_id": a.project_id, "project_name": a.project_name, "phase": a.phase, "due_date": a.due_date,
        "level": a.level or 1, "emails": a.emails or 0, "opened_at": _iso(a.opened_at), "last_sent_at": _iso(a.last_sent_at),
        "acknowledged_at": _iso(a.acknowledged_at), "acknowledged_by": a.acknowledged_by, "ack_level": a.ack_level,
        "update_note": a.update_note, "expected_date": a.expected_date.date().isoformat() if a.expected_date else None,
        "updated_at": _iso(a.updated_at), "holds": A.holds(a), "late_commitment": A.late_commitment(a),
        "resolved_at": _iso(a.resolved_at), "resolved_reason": a.resolved_reason,
        "next_step": A.next_step(db, a),
        "approval_id": int(a.case_key.split(":")[1]) if a.kind == "approval" and a.case_key.count(":") >= 1
                       and a.case_key.split(":")[1].isdigit() else None,
        "recipients": [{"email": r.email, "name": names.get(r.email.lower(), ""), "level": r.level,
                        "acknowledged_at": _iso(r.acknowledged_at)} for r in recips],
    }
    if full:
        row["timeline"] = [{"at": _iso(e.at), "kind": e.kind, "level": e.level, "actor": e.actor, "detail": e.detail,
                            "log_id": e.log_id}
                           for e in db.query(models.EmailAlertEvent).filter(models.EmailAlertEvent.alert_id == a.id)
                           .order_by(models.EmailAlertEvent.at, models.EmailAlertEvent.id).all()]
        row["emails_sent"] = [{"id": l.id, "at": _iso(l.created_at), "subject": l.subject, "level": l.level,
                               "status": l.status, "to": l.to_addrs or [], "cc": l.cc_addrs or []}
                              for l in db.query(models.EmailLog).filter(models.EmailLog.alert_id == a.id)
                              .order_by(models.EmailLog.created_at).all()]
        row["project_link"] = f"/project/{quote(a.project_id, safe='')}" if a.project_id else None
    return row


def _is_admin(db: Session, user) -> bool:
    return ADMIN_PERM in access.role_permissions(db, user.role)


def _mine(db: Session, a: "models.EmailAlert", user) -> Optional["models.EmailAlertRecipient"]:
    email = (user.email or "").strip().lower()
    if not email:
        return None
    return next((r for r in A.recipients(db, a) if r.email.lower() == email), None)


def _copied(db: Session, a: "models.EmailAlert", user) -> bool:
    email = (user.email or "").strip().lower()
    if not email:
        return False
    for l in db.query(models.EmailLog).filter(models.EmailLog.alert_id == a.id).all():
        if email in {x.lower() for x in (l.to_addrs or []) + (l.cc_addrs or [])}:
            return True
    return False


def _alert_or_404(db: Session, alert_id: int) -> "models.EmailAlert":
    a = db.get(models.EmailAlert, alert_id)
    if not a:
        raise HTTPException(status_code=404, detail="No such alert")
    return a


@router.get("/mine")
def my_alerts(status: str = Query("open", pattern="^(open|all)$"), db: Session = Depends(get_db),
              user: models.AkashaUser = Depends(current_user)):
    """Alerts the user is a To recipient of, newest first."""
    email = (user.email or "").strip().lower()
    if not email:
        return {"email": None, "alerts": []}
    ids = [r.alert_id for r in db.query(models.EmailAlertRecipient)
           .filter(models.EmailAlertRecipient.email.ilike(email)).all()]
    q = db.query(models.EmailAlert).filter(models.EmailAlert.id.in_(ids or [0]))
    if status == "open":
        q = q.filter(models.EmailAlert.status == "open")
    names = _names(db)
    rows = [serialize(db, a, names) for a in q.order_by(models.EmailAlert.last_sent_at.desc().nullslast()).limit(200).all()]
    for r in rows:
        mine = next((x for x in r["recipients"] if x["email"].lower() == email), None)
        r["my_ack"] = mine["acknowledged_at"] if mine else None
    return {"email": user.email, "alerts": rows}


@router.get("/{alert_id}")
def alert_detail(alert_id: int, db: Session = Depends(get_db), user: models.AkashaUser = Depends(current_user)):
    a = _alert_or_404(db, alert_id)
    mine, admin = _mine(db, a, user), _is_admin(db, user)
    if not (mine or admin or _copied(db, a, user)):
        raise HTTPException(status_code=403, detail="This alert was not sent to you")
    row = serialize(db, a, full=True)
    row["can_acknowledge"] = bool(mine) and a.status == "open"
    row["my_ack"] = _iso(mine.acknowledged_at) if mine else None
    row["is_admin"] = admin
    row["you"] = {"email": user.email, "name": user.display_name or user.username}
    return row


class AckIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=1000)
    expected_date: Optional[date] = None
    on_behalf_of: Optional[str] = Field(default=None, max_length=200)   # admin: the recipient's email


@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: int, body: AckIn, request: Request, db: Session = Depends(get_db),
                user: models.AkashaUser = Depends(current_user)):
    """Acknowledge (first time) or update (later): what is being done and
    the date it is expected done. An expected date that has not passed holds
    the alert at its level."""
    a = _alert_or_404(db, alert_id)
    if a.status != "open":
        raise HTTPException(status_code=400, detail="This alert is already closed")
    if a.kind == "approval":
        raise HTTPException(status_code=400, detail="An approval is decided in the approval itself (Approve / Return)")
    today = C.today()
    if body.expected_date and not (today <= body.expected_date <= today + timedelta(days=365)):
        raise HTTPException(status_code=400, detail="The expected date must be between today and a year from now")
    name = user.display_name or user.username
    recorded_by = None
    if body.on_behalf_of:
        if not _is_admin(db, user):
            raise HTTPException(status_code=403, detail="Only an email administrator can record an acknowledgement for someone else")
        target = (body.on_behalf_of or "").strip().lower()
        r = next((x for x in A.recipients(db, a) if x.email.lower() == target), None)
        if not r:
            raise HTTPException(status_code=400, detail="That person is not a To recipient of this alert")
        if not (body.note or "").strip():
            raise HTTPException(status_code=400, detail="Say how they confirmed (e.g. 'confirmed by phone') in the note")
        name, recorded_by = _names(db).get(target) or r.email, user.display_name or user.username
    else:
        r = _mine(db, a, user)
        if not r:
            raise HTTPException(status_code=403, detail="Only the people this alert was sent to (To) can acknowledge it")
    A.acknowledge(db, a, r, name, body.note, body.expected_date, recorded_by)
    security.audit(db, "alert.acknowledged", actor=user, target=f"alert #{a.id}",
                   detail={"recipient": r.email, "level": a.level, "expected_date": str(body.expected_date or ""),
                           "on_behalf": bool(recorded_by)}, ip=client_ip(request))
    db.commit()
    return alert_detail(alert_id, db, user)


# ── Administrator list (Email notifications → Alerts) ────────────────────────

def admin_query(db: Session, status: Optional[str], level: Optional[int], template: Optional[str],
                q: Optional[str], ack: Optional[str]):
    query = db.query(models.EmailAlert)
    if status:
        query = query.filter(models.EmailAlert.status == status)
    if level:
        query = query.filter(models.EmailAlert.level == level)
    if template:
        query = query.filter(models.EmailAlert.template_key == template)
    if ack == "awaiting":
        query = query.filter(models.EmailAlert.acknowledged_at.is_(None))
    elif ack == "acknowledged":
        query = query.filter(models.EmailAlert.acknowledged_at.isnot(None))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(models.EmailAlert.project_name.ilike(like), models.EmailAlert.project_id.ilike(like),
                                 models.EmailAlert.phase.ilike(like), models.EmailAlert.acknowledged_by.ilike(like)))
    return query
