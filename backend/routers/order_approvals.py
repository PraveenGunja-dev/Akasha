"""Module order approvals - raised from the Ordering Schedule's month cell,
decided by the approval email's To recipients (services/order_approvals.py).
Every action is audited."""
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from database import get_db
from routers.auth import client_ip, current_user
from services import access, order_approvals as OA, portfolio, security

from fastapi import Depends as _Depends
from services.demo_scope import see_demo

# Module Ordering: demo projects are visible here (services/demo_scope.py).
router = APIRouter(prefix="/api/module-approvals", tags=["Module order approvals"], dependencies=[_Depends(see_demo)])


def _in_scope(db: Session, user, mapping_id: int) -> bool:
    """The project is in the user's portfolios (demo projects are in all)."""
    scope = access.user_scope(user)
    if scope is None:
        return True
    m = db.get(models.ProjectMapping, mapping_id)
    return bool(m) and portfolio.cluster_in(portfolio.mapping_cluster(m), scope)


def _sees(db: Session, user, a) -> bool:
    """Who may open an approval: its portfolio's users, its requester, and
    whoever may decide it."""
    return a.requested_by == user.username or _in_scope(db, user, a.mapping_id) or OA.can_decide(db, user, a)


def _get(db: Session, approval_id: int, user=None):
    a = db.get(models.ModuleOrderApproval, approval_id)
    if not a or (user is not None and not _sees(db, user, a)):
        raise HTTPException(status_code=404, detail="No such approval request")
    return a


def _out(db: Session, a, user) -> dict:
    events = (db.query(models.ModuleOrderApprovalEvent).filter(models.ModuleOrderApprovalEvent.approval_id == a.id)
              .order_by(models.ModuleOrderApprovalEvent.at, models.ModuleOrderApprovalEvent.id).all())
    row = OA.serialize(a, events)
    row["can_decide"] = a.status == "pending" and OA.can_decide(db, user, a)
    row["own_request"] = OA.self_request(user, a)
    row["you_are"] = ("superadmin" if user.role == "superadmin" else
                      "approver" if (user.email or "").lower() in {x.lower() for x in OA.approvers(db, a)} else None)
    row["can_cancel"] = a.status in OA.OPEN and (
        (a.requested_by == user.username and a.status == "pending") or OA.can_decide(db, user, a))
    row["approvers"] = OA.approvers(db, a)
    row["email"] = OA.email_outcome(db, a, events)
    return row


@router.get("")
def list_approvals(mapping_id: Optional[int] = None, status: Optional[str] = None, db: Session = Depends(get_db),
                   user: models.AkashaUser = Depends(current_user)):
    q = db.query(models.ModuleOrderApproval)
    if mapping_id is not None:
        q = q.filter(models.ModuleOrderApproval.mapping_id == mapping_id)
    if status:
        q = q.filter(models.ModuleOrderApproval.status.in_(status.split(",")))
    rows = q.order_by(models.ModuleOrderApproval.requested_at.desc()).limit(500).all()
    return [_out(db, a, user) for a in rows if _sees(db, user, a)]


@router.get("/me")
def my_role(db: Session = Depends(get_db), user: models.AkashaUser = Depends(current_user)):
    """May this user raise requests (TC Ordering) or decide them (TC Head),
    and for which portfolios - drives what the Ordering Schedule offers."""
    out = OA.roles(db, user)
    pending = db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.status == "pending").all()
    out["waiting"] = sum(1 for a in pending if OA.can_decide(db, user, a))
    return out


@router.get("/waiting")
def waiting_for_me(db: Session = Depends(get_db), user: models.AkashaUser = Depends(current_user)):
    """Pending requests this user can decide - they are in the approval
    email's To group for the project's portfolio (or a superadmin), and did
    not raise it themselves. Shown on the Ordering Schedule so an approver
    sees them on opening the dashboard, email or not."""
    rows = (db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.status == "pending")
            .order_by(models.ModuleOrderApproval.requested_at).all())
    return [_out(db, a, user) for a in rows if OA.can_decide(db, user, a)]


@router.get("/{approval_id}")
def get_approval(approval_id: int, db: Session = Depends(get_db), user: models.AkashaUser = Depends(current_user)):
    return _out(db, _get(db, approval_id, user), user)


class RequestIn(BaseModel):
    mapping_id: int
    month: str = Field(pattern=r"^[A-Z][a-z]{2}-\d{2}$")
    mwp: float = Field(gt=0)
    note: Optional[str] = Field(default=None, max_length=1000)


@router.post("")
def request_approval(body: RequestIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db),
                     user: models.AkashaUser = Depends(current_user)):
    """Records the request and replies at once; the approval email goes out
    straight after, in the background."""
    if not _in_scope(db, user, body.mapping_id):
        raise HTTPException(status_code=403, detail="This project is outside your portfolio access")
    try:
        a = OA.request(db, user, body.mapping_id, body.month, body.mwp, body.note, send_email=False)
    except OA.ApprovalError as e:
        raise HTTPException(status_code=400, detail=str(e))
    security.audit(db, "approval.requested", actor=user, target=f"approval #{a.id}",
                   detail={"project": a.project_name, "month": a.month, "mwp": a.mwp}, ip=client_ip(request))
    db.commit()
    background.add_task(OA.email_later, a.id, "request", user.username)
    return _out(db, a, user)


class DecideIn(BaseModel):
    decision: Literal["approve", "return"]
    note: Optional[str] = Field(default=None, max_length=1000)


@router.post("/{approval_id}/decide")
def decide(approval_id: int, body: DecideIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db),
           user: models.AkashaUser = Depends(current_user)):
    a = _get(db, approval_id, user)
    try:
        OA.decide(db, user, a, body.decision, body.note, send_email=False)
    except OA.ApprovalError as e:
        raise HTTPException(status_code=400, detail=str(e))
    security.audit(db, f"approval.{a.status}", actor=user, target=f"approval #{a.id}",
                   detail={"project": a.project_name, "month": a.month, "mwp": a.mwp}, ip=client_ip(request))
    db.commit()
    background.add_task(OA.email_later, a.id, "decision", user.username)
    return _out(db, a, user)


class CancelIn(BaseModel):
    note: str = Field(max_length=1000)


@router.post("/{approval_id}/cancel")
def cancel(approval_id: int, body: CancelIn, request: Request, db: Session = Depends(get_db),
           user: models.AkashaUser = Depends(current_user)):
    a = _get(db, approval_id, user)
    try:
        OA.cancel(db, user, a, body.note)
    except OA.ApprovalError as e:
        raise HTTPException(status_code=400, detail=str(e))
    security.audit(db, "approval.cancelled", actor=user, target=f"approval #{a.id}",
                   detail={"project": a.project_name, "month": a.month}, ip=client_ip(request))
    db.commit()
    return _out(db, a, user)
