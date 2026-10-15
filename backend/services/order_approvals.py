"""Module order approvals (models.ModuleOrderApproval).

    request()   from the Ordering Schedule: one month's order for a project,
                emailed to the approval template's To groups (TC Head)
    decide()    an approver approves, or returns it with remarks; the
                decision is emailed to TC Ordering and the requester
    cancel()    the requester withdraws it, or an approver releases a freeze
    attach()    on every Ordering Schedule load: each project's approvals and
                the quantities that are frozen in their month

The freeze
    An approved quantity is placed in its month before vendor levelling
    (services/module_planner.py), so neither the quota shifts nor the overdue
    carry-forward can move it. It holds until SAP shows the POs: growth in the
    project's ordered MWp since the request is credited to its approvals,
    oldest first. Fully credited, the approval becomes 'ordered' and the
    freeze is released. Nothing is estimated - the quantities are the ones
    asked for and the POs SAP holds.
"""
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

import models

IST = timedelta(hours=5, minutes=30)
OPEN = ("pending", "approved")
TOL = 0.05   # MWp - rounding in the plan


class ApprovalError(ValueError):
    pass


def _iso(dt) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def event(db: Session, a, kind: str, actor: Optional[str], detail: Optional[str] = None) -> None:
    db.add(models.ModuleOrderApprovalEvent(approval_id=a.id, at=datetime.utcnow(), kind=kind, actor=actor, detail=detail))


# ── The freeze ───────────────────────────────────────────────────────────────

def _credit(approved: List["models.ModuleOrderApproval"], ordered_now: float) -> Dict[int, float]:
    """{approval id: MWp still not covered by a PO}. PO growth since the
    earliest request is credited oldest approval first."""
    if not approved:
        return {}
    approved = sorted(approved, key=lambda a: (a.decided_at or a.requested_at, a.id))
    pool = max(0.0, ordered_now - min(a.ordered_at_request or 0.0 for a in approved))
    out = {}
    for a in approved:
        used = min(pool, a.mwp)
        pool -= used
        out[a.id] = round(a.mwp - used, 1)
    return out


def attach(db: Session, projects: List[dict]) -> None:
    """Set each Ordering Schedule row's `approvals` (newest first, with
    history) and `frozen_allocations` (what the planner must keep in its
    month). Called before the planner runs."""
    ids = [p["id"] for p in projects if p.get("id") is not None]
    if not ids:
        return
    rows = (db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.mapping_id.in_(ids))
            .order_by(models.ModuleOrderApproval.requested_at.desc()).all())
    by_map: Dict[int, list] = {}
    for a in rows:
        by_map.setdefault(a.mapping_id, []).append(a)
    events = {}
    if rows:
        for e in (db.query(models.ModuleOrderApprovalEvent)
                  .filter(models.ModuleOrderApprovalEvent.approval_id.in_([a.id for a in rows]))
                  .order_by(models.ModuleOrderApprovalEvent.at, models.ModuleOrderApprovalEvent.id).all()):
            events.setdefault(e.approval_id, []).append(e)
    for p in projects:
        mine = by_map.get(p.get("id"), [])
        approved = [a for a in mine if a.status == "approved"]
        remaining = _credit(approved, float(p.get("ordered_mwp") or 0.0))
        # Never freeze more than is still to order.
        cap = float(p.get("balance_ordering_mwp") or 0.0)
        frozen = []
        for a in sorted(approved, key=lambda a: (a.decided_at or a.requested_at, a.id)):
            left = min(remaining.get(a.id, 0.0), cap)
            cap -= left
            if left > TOL:
                frozen.append({"approval_id": a.id, "month": a.month, "mwp": round(left, 1),
                               "phases": [x.get("phase_label") for x in (a.phases or [])]})
        p["frozen_allocations"] = frozen
        p["approvals"] = [serialize(a, events.get(a.id, []), remaining.get(a.id)) for a in mine]


def refresh_ordered(db: Session, projects: List[dict]) -> int:
    """Mark approvals whose POs are now in SAP as 'ordered' (freeze released),
    from rows that went through attach(). Returns how many."""
    n = 0
    for p in projects:
        for row in p.get("approvals") or []:
            if row["status"] == "approved" and row.get("remaining_mwp") is not None and row["remaining_mwp"] <= TOL:
                a = db.get(models.ModuleOrderApproval, row["id"])
                if a and a.status == "approved":
                    a.status, a.ordered_at = "ordered", datetime.utcnow()
                    event(db, a, "ordered", "Akasha", f"POs in SAP now cover the {a.mwp:.1f} MWp - freeze released")
                    n += 1
    if n:
        db.commit()
    return n


def serialize(a, events: Iterable = (), remaining: Optional[float] = None) -> dict:
    return {
        "id": a.id, "mapping_id": a.mapping_id, "project_id": a.project_id, "project_name": a.project_name,
        "month": a.month, "mwp": round(a.mwp, 1), "phases": a.phases or [], "vendor_type": a.vendor_type,
        "status": a.status, "remaining_mwp": remaining if a.status == "approved" else None,
        "request_note": a.request_note, "requested_by": a.requested_by_name or a.requested_by,
        "requested_at": _iso(a.requested_at), "decided_by": a.decided_by_name or a.decided_by,
        "decided_at": _iso(a.decided_at), "decision_note": a.decision_note, "ordered_at": _iso(a.ordered_at),
        "alert_id": a.alert_id, "basis": a.basis or {},
        "history": [{"at": _iso(e.at), "kind": e.kind, "actor": e.actor, "detail": e.detail} for e in events],
    }


# ── Who may do what ──────────────────────────────────────────────────────────

def approvers(db: Session, a) -> List[str]:
    """The approval template's To members (every level) for the project's
    portfolio - the people who decide."""
    from services.email_notify import alerts, engine
    t = db.get(models.EmailTemplate, "approval_request")
    m = db.get(models.ProjectMapping, a.mapping_id)
    # Exactly the people the request email goes to: same groups, portfolio and level.
    return engine.members(db, list((t.to_groups if t else None) or ["tc_head"]), getattr(m, "cluster", None),
                          alerts.template_level(t) if t else 1)


def self_request(user, a) -> bool:
    return user.username == a.requested_by


def can_decide(db: Session, user, a) -> bool:
    """An approver - the approval email's To recipients, or a superadmin -
    who did not raise the request: nobody approves their own order."""
    if self_request(user, a):
        return False
    if user.role == "superadmin":
        return True
    email = (user.email or "").strip().lower()
    return bool(email) and email in {x.lower() for x in approvers(db, a)}


# ── Actions ──────────────────────────────────────────────────────────────────

def _summary_row(db: Session, mapping_id: int) -> dict:
    from routers.module_deliveries import get_module_deliveries_summary
    s = get_module_deliveries_summary(scenario="baseline", priorities=None, portfolio=None, phase="all", db=db)
    p = next((x for x in s.get("projects") or [] if x.get("id") == mapping_id), None)
    if not p:
        raise ApprovalError("This project is not in the Ordering Schedule")
    return p


def request(db: Session, user, mapping_id: int, month: str, mwp: float, note: Optional[str]) -> "models.ModuleOrderApproval":
    """Raise a request for (up to) the month's planned quantity. The phases
    and figures come from the plan itself, never from the browser."""
    p = _summary_row(db, mapping_id)
    planned = float((p.get("month_mwp") or {}).get(month) or 0.0)
    if planned <= TOL:
        raise ApprovalError(f"Nothing is planned for {month} - there is no order to approve")
    if mwp <= TOL or mwp > planned + TOL:
        raise ApprovalError(f"The quantity must be between 0.1 and the {planned:.1f} MWp planned for {month}")
    clash = (db.query(models.ModuleOrderApproval)
             .filter(models.ModuleOrderApproval.mapping_id == mapping_id, models.ModuleOrderApproval.month == month,
                     models.ModuleOrderApproval.status.in_(OPEN)).first())
    if clash:
        raise ApprovalError(f"{month} already has an approval {clash.status} (#{clash.id}) for this project")
    phases, left = [], mwp
    for ph in (p.get("month_phases") or {}).get(month) or []:
        if left <= TOL:
            break
        take = min(left, float(ph.get("mwp") or 0.0))
        if take <= TOL:
            continue
        phases.append({k: ph.get(k) for k in ("phase_label", "order_date", "tc_date", "ftc_date", "ftc_reachable",
                                               "ftc_short_days", "overdue", "delay_months", "shifted")} | {"mwp": round(take, 1)})
        left -= take
    basis = _basis(p, month, planned, phases)
    a = models.ModuleOrderApproval(
        mapping_id=mapping_id, project_id=getattr(db.get(models.ProjectMapping, mapping_id), "project_id", None),
        project_name=p.get("project_name"), month=month, mwp=round(mwp, 1), phases=phases,
        vendor_type=p.get("type"), ordered_at_request=float(p.get("ordered_mwp") or 0.0), status="pending", basis=basis,
        request_note=(note or "").strip()[:1000] or None, requested_by=user.username,
        requested_by_name=user.display_name or user.username, requested_by_email=(user.email or None),
        requested_at=datetime.utcnow())
    db.add(a)
    db.flush()
    event(db, a, "requested", a.requested_by_name, f"{a.mwp:.1f} MWp in {month}" + (f" - {a.request_note}" if a.request_note else ""))
    db.commit()
    _email(db, a, "request", user.username)
    return a


def _basis(p: dict, month: str, planned: float, phases: List[dict]) -> dict:
    """The facts an approver decides on, as the plan stood when requested -
    straight from the Ordering Schedule row, nothing estimated."""
    from services.email_notify.context import parse_day
    lta = parse_day(p.get("lta"))
    warnings = []
    if any(x.get("overdue") for x in phases):
        warnings.append("The ordering date has already passed - this is a late order")
    short = [x for x in phases if x.get("ftc_reachable") is False]
    if short:
        worst = max(int(x.get("ftc_short_days") or 0) for x in short)
        warnings.append(f"Ordering in {month} cannot meet the P6 FTC for {len(short)} of {len(phases)} phase(s) - up to {worst} days short")
    late = [x for x in phases if lta and parse_day(x.get("ftc_date")) and parse_day(x.get("ftc_date")) > lta]
    if late:
        warnings.append(f"The FTC of {len(late)} phase(s) falls after the LTA ({p.get('lta')})")
    # A late order is carried into the current month by the overdue rule, not
    # by quota - only a planner shift of an on-time order is the vendor's doing.
    if any(x.get("shifted") and not x.get("overdue") and (x.get("delay_months") or 0) > 0 for x in phases):
        warnings.append("Vendor quota has moved this order later than its planned month")
    return {"lta": p.get("lta") or "", "scod": p.get("scod") or "", "capacity_mwp": p.get("capacity_mwp"),
            "ordered_mwp": p.get("ordered_mwp"), "balance_mwp": p.get("balance_ordering_mwp"),
            "month_planned_mwp": round(planned, 1), "vendor_type": p.get("type") or "", "priority": p.get("priority") or "",
            "warnings": warnings}


def _email(db: Session, a, what: str, who: str) -> None:
    """Send the request / decision email and record the outcome on the
    approval - never fails the action itself."""
    from services.email_notify import engine
    from services.email_notify.config import settings
    if not settings().enabled:
        event(db, a, "email", "Akasha", "Not emailed - email sending is off (EMAIL_ENABLED=false)")
        db.commit()
        return
    try:
        r = engine.send_approval_request(db, a, who) if what == "request" else engine.send_approval_decision(db, a, who)
        if what == "request" and r.get("alert_id"):
            a.alert_id = r["alert_id"]
        to = ", ".join(r.get("to") or []) or "nobody"
        event(db, a, "email", "Akasha", f"{'Request' if what == 'request' else 'Decision'} email {r.get('status')} - To {to}"
              + (f" ({r.get('detail')})" if r.get("status") not in ("sent", "test") and r.get("detail") else ""))
    except Exception as e:  # noqa: BLE001
        event(db, a, "email", "Akasha", f"Email failed: {e}")
    db.commit()


def _close_alert(db: Session, a, reason: str, actor: str) -> None:
    from services.email_notify import alerts
    al = db.get(models.EmailAlert, a.alert_id) if a.alert_id else None
    if al and al.status == "open":
        alerts.resolve(db, al, reason, actor)


def decide(db: Session, user, a, decision: str, note: Optional[str]) -> None:
    if a.status != "pending":
        raise ApprovalError(f"This request is already {a.status}")
    if self_request(user, a):
        raise ApprovalError("You raised this request - another approver has to decide it")
    if not can_decide(db, user, a):
        raise ApprovalError("Only the approvers this request was sent to (To) can decide it")
    note = (note or "").strip()
    if decision == "return" and len(note) < 5:
        raise ApprovalError("Say why it is returned (at least 5 characters)")
    name = user.display_name or user.username
    a.status = "approved" if decision == "approve" else "returned"
    a.decided_by, a.decided_by_name, a.decided_at, a.decision_note = user.username, name, datetime.utcnow(), note[:1000] or None
    word = "Approved" if a.status == "approved" else "Returned"
    event(db, a, a.status, name, note or None)
    if a.status == "approved":
        event(db, a, "frozen", "Akasha", f"{a.mwp:.1f} MWp frozen in {a.month} until the PO is in SAP")
    _close_alert(db, a, f"{word} by {name}" + (f": {note}" if note else ""), name)
    db.commit()
    _email(db, a, "decision", user.username)


def cancel(db: Session, user, a, note: Optional[str]) -> None:
    if a.status not in OPEN:
        raise ApprovalError(f"This request is already {a.status}")
    mine = user.username == a.requested_by
    if not (mine and a.status == "pending") and not can_decide(db, user, a):
        raise ApprovalError("Only the requester (while pending) or an approver can cancel this")
    note = (note or "").strip()
    if len(note) < 5:
        raise ApprovalError("Say why it is cancelled (at least 5 characters)")
    name = user.display_name or user.username
    was = a.status
    a.status = "cancelled"
    event(db, a, "cancelled", name, (("Freeze released - " if was == "approved" else "") + note)[:1000])
    _close_alert(db, a, f"Cancelled by {name}: {note}", name)
    db.commit()
