"""Email notifications - the administrator's side (services/email_notify).

Templates (edit, preview against a real project, test-send, version history,
restore, reset to the shipped text), distribution groups, the email log with
filters / CSV export / resend, and "run now" with a dry run that shows what
would go out. Everything needs the email.manage permission and every change
is written to the audit log.
"""
import csv
import io
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
from database import get_db
from routers.auth import client_ip, require_permission
from services import portfolio, security
from services.email_notify import alerts as A, catalogue, engine, render
from services.email_notify.config import settings

router = APIRouter(prefix="/api/admin/email", tags=["Email notifications"])
PERM = "email.manage"
IST = timedelta(hours=5, minutes=30)
EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _ist(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _tpl_or_404(db: Session, key: str) -> models.EmailTemplate:
    engine.seed_templates(db)
    t = db.get(models.EmailTemplate, key)
    if not t:
        raise HTTPException(status_code=404, detail=f"No template '{key}'")
    return t


def _tpl(t: models.EmailTemplate, last: Optional[datetime] = None, open_alerts: Optional[dict] = None) -> dict:
    return {"level": A.template_level(t), "ack_required": A.ack_required(t),
            "alerts": open_alerts or {"open": 0, "awaiting": 0, "acknowledged": 0, "by_level": {}, "last_ack": None},"key": t.key, "name": t.name, "category": t.category, "trigger": t.trigger,
            "trigger_label": catalogue.TRIGGERS.get(t.trigger, t.trigger), "description": t.description,
            "severity": t.severity, "subject": t.subject, "body": t.body,
            "to_groups": t.to_groups or [], "cc_groups": t.cc_groups or [], "config": t.config or {},
            "attach_snapshot": bool(t.attach_snapshot), "enabled": bool(t.enabled), "version": t.version,
            "updated_by": t.updated_by, "updated_at": _ist(t.updated_at), "last_sent_at": _ist(last),
            "problems": render.validate(t.subject, t.body)}


# ── Overview ─────────────────────────────────────────────────────────────────

@router.get("/status")
def status(db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM))):
    engine.seed_templates(db)
    since = datetime.utcnow() - timedelta(days=7)
    counts = dict(db.query(models.EmailLog.status, func.count(models.EmailLog.id))
                  .filter(models.EmailLog.created_at >= since).group_by(models.EmailLog.status).all())
    sched = db.get(models.SyncSchedule, "email")
    return {"settings": settings().public(),
            "templates": db.query(models.EmailTemplate).count(),
            "enabled_templates": db.query(models.EmailTemplate).filter(models.EmailTemplate.enabled.is_(True)).count(),
            "recipients": db.query(models.EmailRecipient).filter(models.EmailRecipient.active.is_(True)).count(),
            "last_7_days": counts,
            "schedule": {"enabled": bool(sched.enabled), "next_run_at": _ist(sched.next_run_at),
                         "last_run_at": _ist(sched.last_run_at)} if sched else None}


@router.get("/catalogue")
def catalogue_info(db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM))):
    return {"variables": [{"key": k, "label": v[0], "meaning": v[1], "sample": v[2]} for k, v in catalogue.VARIABLES.items()],
            "groups": [{"key": k, "label": v} for k, v in catalogue.GROUPS.items()],
            "triggers": [{"key": k, "label": v} for k, v in catalogue.TRIGGERS.items()],
            "portfolios": portfolio.all_clusters(db)}


@router.get("/projects")
def projects(db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM))):
    """Projects to preview or send a template for (project master, P6 id)."""
    rows = (db.query(models.ProjectMapping.project_id, models.ProjectMapping.project_name_from_p6,
                     models.ProjectMapping.project, models.ProjectMapping.cluster)
            .filter(models.ProjectMapping.project_id.isnot(None)).all())
    seen, out = set(), []
    for pid, p6, name, cluster in sorted(rows, key=lambda r: (r[3] or "", r[2] or r[1] or "")):
        if pid in seen:
            continue
        seen.add(pid)
        out.append({"project_id": pid, "name": name or p6 or pid, "portfolio": cluster or ""})
    return out


# ── Templates ────────────────────────────────────────────────────────────────

@router.get("/templates")
def list_templates(db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM))):
    engine.seed_templates(db)
    last = dict(db.query(models.EmailLog.template_key, func.max(models.EmailLog.created_at))
                .filter(models.EmailLog.status.in_(["sent", "test"])).group_by(models.EmailLog.template_key).all())
    order = {t["key"]: i for i, t in enumerate(catalogue.TEMPLATES)}
    rows = sorted(db.query(models.EmailTemplate).all(), key=lambda t: (order.get(t.key, 999), t.name))
    test = settings().test_mode
    open_by = {}
    for a in db.query(models.EmailAlert).filter(models.EmailAlert.status == "open", models.EmailAlert.test.is_(test)).all():
        o = open_by.setdefault(a.template_key, {"open": 0, "awaiting": 0, "acknowledged": 0, "by_level": {}, "last_ack": None})
        o["open"] += 1
        o["awaiting" if not a.acknowledged_at else "acknowledged"] += 1
        o["by_level"][str(a.level or 1)] = o["by_level"].get(str(a.level or 1), 0) + 1
        if a.acknowledged_at and (not o["last_ack"] or _ist(a.acknowledged_at) > o["last_ack"]["at"]):
            o["last_ack"] = {"by": a.acknowledged_by, "at": _ist(a.acknowledged_at), "level": a.ack_level,
                             "project": a.project_name}
    return [_tpl(t, last.get(t.key), open_by.get(t.key)) for t in rows]


class TemplateIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    severity: str = "info"
    subject: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=10, max_length=20000)
    to_groups: List[str] = []
    cc_groups: List[str] = []
    config: dict = {}
    attach_snapshot: bool = False
    enabled: bool = False
    level: int = Field(default=1, ge=1, le=3)
    ack_required: bool = False
    note: Optional[str] = Field(default=None, max_length=300)


def _check_timing(trigger: str, config: dict) -> None:
    """L1 / L2 / L3 days must be whole days and climb in the right order."""
    def bad(msg):
        raise HTTPException(status_code=400, detail=msg)
    if trigger == "ordering_due":
        levels = config.get("levels")
        if not isinstance(levels, dict) or not levels:
            bad("Set the days before the ordering date for at least one level")
        try:
            days = {int(k): int(v) for k, v in levels.items()}
        except (TypeError, ValueError):
            bad("Days must be whole numbers")
        if any(k not in (1, 2, 3) for k in days) or any(not 1 <= v <= 365 for v in days.values()):
            bad("Levels are 1-3 and days 1-365")
        order = [days[k] for k in sorted(days)]
        if any(a <= b for a, b in zip(order, order[1:])):
            bad("Each level must come later than the one before - e.g. L1 30, L2 15, L3 7 days before")
    elif trigger == "ordering_overdue":
        steps = config.get("escalation")
        if not isinstance(steps, list) or not steps:
            bad("Set at least one overdue reminder")
        try:
            days = [int(s.get("after_days", 0)) for s in steps]
        except (TypeError, ValueError, AttributeError):
            bad("Days overdue must be whole numbers")
        if any(not 0 <= d <= 180 for d in days) or any(a >= b for a, b in zip(days, days[1:])):
            bad("Days overdue must rise from L1 to L3 - e.g. 0, 7, 14")


@router.put("/templates/{key}")
def save_template(key: str, body: TemplateIn, request: Request, db: Session = Depends(get_db),
                  user: models.AkashaUser = Depends(require_permission(PERM))):
    t = _tpl_or_404(db, key)
    problems = render.validate(body.subject, body.body)
    if problems:
        raise HTTPException(status_code=400, detail="; ".join(problems))
    if body.severity not in render.SEVERITY:
        raise HTTPException(status_code=400, detail="Severity must be info, action or critical")
    _check_timing(t.trigger, body.config)
    unknown = [g for g in body.to_groups + body.cc_groups if g not in catalogue.GROUPS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown group(s): {', '.join(unknown)}")
    if body.enabled and not body.to_groups and t.trigger not in ("manual",):
        raise HTTPException(status_code=400, detail="An enabled template needs at least one 'To' group")
    t.level, t.ack_required = A.template_level(t), A.ack_required(t)   # NULL -> the default it was using
    changed = [f for f in ("name", "severity", "subject", "body", "to_groups", "cc_groups", "config",
                           "attach_snapshot", "enabled", "level", "ack_required") if getattr(t, f) != getattr(body, f)]
    if not changed:
        return _tpl(t)
    for f in changed:
        setattr(t, f, getattr(body, f))
    t.version = (t.version or 1) + 1
    t.updated_by, t.updated_at = user.username, datetime.utcnow()
    db.add(engine.version_row(t, user.username, body.note or ""))
    security.audit(db, "email.template_saved", actor=user, target=key,
                   detail={"version": t.version, "changed": changed}, ip=client_ip(request))
    db.commit()
    return _tpl(t)


@router.get("/templates/{key}/versions")
def versions(key: str, db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM))):
    _tpl_or_404(db, key)
    rows = (db.query(models.EmailTemplateVersion).filter(models.EmailTemplateVersion.template_key == key)
            .order_by(models.EmailTemplateVersion.version.desc()).all())
    return [{"version": v.version, "name": v.name, "subject": v.subject, "body": v.body,
             "to_groups": v.to_groups or [], "cc_groups": v.cc_groups or [], "config": v.config or {},
             "attach_snapshot": bool(v.attach_snapshot), "enabled": bool(v.enabled), "note": v.note,
             "level": v.level, "ack_required": v.ack_required,
             "changed_by": v.changed_by, "changed_at": _ist(v.changed_at)} for v in rows]


def _apply(t, src, user, note, request, db, action):
    for f in ("name", "subject", "body", "to_groups", "cc_groups", "config", "attach_snapshot", "level", "ack_required"):
        v = src.get(f) if isinstance(src, dict) else getattr(src, f, None)
        if v is not None or f not in ("level", "ack_required"):   # versions saved before levels keep the current one
            setattr(t, f, v)
    t.version = (t.version or 1) + 1
    t.updated_by, t.updated_at = user.username, datetime.utcnow()
    db.add(engine.version_row(t, user.username, note))
    security.audit(db, action, actor=user, target=t.key, detail={"version": t.version, "note": note}, ip=client_ip(request))
    db.commit()
    return _tpl(t)


@router.post("/templates/{key}/restore/{version}")
def restore(key: str, version: int, request: Request, db: Session = Depends(get_db),
            user: models.AkashaUser = Depends(require_permission(PERM))):
    t = _tpl_or_404(db, key)
    v = (db.query(models.EmailTemplateVersion)
         .filter(models.EmailTemplateVersion.template_key == key, models.EmailTemplateVersion.version == version).first())
    if not v:
        raise HTTPException(status_code=404, detail=f"No version {version}")
    return _apply(t, v, user, f"Restored version {version}", request, db, "email.template_restored")


@router.post("/templates/{key}/reset")
def reset(key: str, request: Request, db: Session = Depends(get_db),
          user: models.AkashaUser = Depends(require_permission(PERM))):
    t = _tpl_or_404(db, key)
    src = next((x for x in catalogue.TEMPLATES if x["key"] == key), None)
    if not src:
        raise HTTPException(status_code=400, detail="This template has no shipped default")
    return _apply(t, src, user, "Reset to the Akasha default text", request, db, "email.template_reset")


class PreviewIn(BaseModel):
    project_id: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    severity: Optional[str] = None
    level: Optional[int] = Field(default=None, ge=1, le=3)
    ack_required: Optional[bool] = None


@router.post("/templates/{key}/preview")
def preview(key: str, body: PreviewIn, db: Session = Depends(get_db),
            _: models.AkashaUser = Depends(require_permission(PERM))):
    """The template as it would go out now - unsaved edits included."""
    t = _tpl_or_404(db, key)
    draft = models.EmailTemplate(**{c.name: getattr(t, c.name) for c in models.EmailTemplate.__table__.columns})
    for f in ("subject", "body", "severity"):
        if getattr(body, f):
            setattr(draft, f, getattr(body, f))
    for f in ("level", "ack_required"):
        if getattr(body, f) is not None:
            setattr(draft, f, getattr(body, f))
    return engine.preview(db, draft, body.project_id)


class TestIn(BaseModel):
    to: Optional[str] = None
    project_id: Optional[str] = None


@router.post("/templates/{key}/test")
def test_send(key: str, body: TestIn, request: Request, db: Session = Depends(get_db),
              user: models.AkashaUser = Depends(require_permission(PERM))):
    import re
    t = _tpl_or_404(db, key)
    to = (body.to or user.email or "").strip()
    if not re.match(EMAIL_RE, to):
        raise HTTPException(status_code=400, detail="Give an address to send the test to (your account has no email)")
    r = engine.send_test(db, t, to, body.project_id, user.username)
    security.audit(db, "email.test_sent", actor=user, target=key, detail={"to": to, "status": r["status"]}, ip=client_ip(request))
    db.commit()
    return r


class ManualIn(BaseModel):
    project_id: str


@router.post("/templates/{key}/send")
def manual_send(key: str, body: ManualIn, request: Request, db: Session = Depends(get_db),
                user: models.AkashaUser = Depends(require_permission(PERM))):
    """Send a template for one project to its groups now (approval / completion)."""
    if not settings().enabled:
        raise HTTPException(status_code=400, detail="Email sending is off (EMAIL_ENABLED=false)")
    t = _tpl_or_404(db, key)
    try:
        r = engine.send_manual(db, t, body.project_id, user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    security.audit(db, "email.manual_sent", actor=user, target=key,
                   detail={"project_id": body.project_id, "status": r["status"]}, ip=client_ip(request))
    db.commit()
    return r


@router.get("/templates/export")
def export_templates(db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM))):
    rows = []
    for t in db.query(models.EmailTemplate).all():
        rows.append([t.key, t.name, t.category, t.trigger, t.severity, "yes" if t.enabled else "no",
                     f"L{A.template_level(t)}", "yes" if A.ack_required(t) else "no",
                     ", ".join(t.to_groups or []), ", ".join(t.cc_groups or []), t.version, t.updated_by or "",
                     (t.updated_at + IST).strftime("%Y-%m-%d %H:%M") if t.updated_at else "", t.subject, t.body])
    return _csv(["key", "name", "category", "trigger", "severity", "enabled", "level", "acknowledge", "to_groups", "cc_groups", "version",
                 "updated_by", "updated_at_ist", "subject", "body"], rows, "akasha-email-templates")


# ── Recipients ───────────────────────────────────────────────────────────────

@router.get("/users")
def users(db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM))):
    """Active Akasha users with an email address - to pick recipients from."""
    roles = {r.key: r.name for r in db.query(models.AkashaRole).all()}
    rows = (db.query(models.AkashaUser).filter(models.AkashaUser.is_active.is_(True), models.AkashaUser.email.isnot(None))
            .order_by(models.AkashaUser.display_name, models.AkashaUser.username).all())
    return [{"id": u.id, "username": u.username, "name": u.display_name or u.username, "email": u.email,
             "role": roles.get(u.role, u.role), "department": u.department or "",
             "portfolios": [] if u.role == "superadmin" else list(u.portfolios or [])}
            for u in rows if (u.email or "").strip()]


@router.get("/recipients")
def list_recipients(db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM))):
    rows = db.query(models.EmailRecipient).order_by(models.EmailRecipient.group_key, models.EmailRecipient.email).all()
    akasha = {(u.email or "").strip().lower() for u in db.query(models.AkashaUser)
              .filter(models.AkashaUser.is_active.is_(True), models.AkashaUser.email.isnot(None)).all()}
    return [{"akasha_user": r.email.strip().lower() in akasha, "id": r.id, "group_key": r.group_key, "group": catalogue.GROUPS.get(r.group_key, r.group_key),
             "name": r.name or "", "email": r.email, "portfolios": r.portfolios or [], "level": r.level or 1,
             "active": bool(r.active),
             "created_at": _ist(r.created_at), "created_by": r.created_by} for r in rows]


class RecipientIn(BaseModel):
    group_key: str
    email: str = Field(max_length=200)
    name: Optional[str] = Field(default=None, max_length=120)
    portfolios: List[str] = []
    level: int = Field(default=1, ge=1, le=3)
    active: bool = True


def _check_recipient(db, body: RecipientIn):
    import re
    if body.group_key not in catalogue.GROUPS:
        raise HTTPException(status_code=400, detail=f"Unknown group '{body.group_key}'")
    if not re.match(EMAIL_RE, body.email.strip()):
        raise HTTPException(status_code=400, detail="Not a valid email address")
    doms = settings().allowed_domains
    if doms and body.email.strip().rsplit("@", 1)[-1].lower() not in doms:
        raise HTTPException(status_code=400, detail=f"Only {', '.join('@' + d for d in doms)} addresses can receive Akasha email")
    known = {c.lower(): c for c in portfolio.all_clusters(db)}
    bad = [p for p in body.portfolios if p.lower() not in known]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown portfolio(s): {', '.join(bad)}")
    return [known[p.lower()] for p in body.portfolios] or None


@router.post("/recipients")
def add_recipient(body: RecipientIn, request: Request, db: Session = Depends(get_db),
                  user: models.AkashaUser = Depends(require_permission(PERM))):
    ports = _check_recipient(db, body)
    email = body.email.strip()
    dup = db.query(models.EmailRecipient).filter(models.EmailRecipient.group_key == body.group_key,
                                                 func.lower(models.EmailRecipient.email) == email.lower()).first()
    if dup:
        raise HTTPException(status_code=400, detail=f"{email} is already in {catalogue.GROUPS[body.group_key]}")
    r = models.EmailRecipient(group_key=body.group_key, email=email, name=(body.name or "").strip() or None,
                              portfolios=ports, level=body.level, active=body.active, created_by=user.username)
    db.add(r)
    security.audit(db, "email.recipient_added", actor=user, target=email,
                   detail={"group": body.group_key, "level": body.level, "portfolios": ports}, ip=client_ip(request))
    db.commit()
    return {"id": r.id}


@router.put("/recipients/{rid}")
def update_recipient(rid: int, body: RecipientIn, request: Request, db: Session = Depends(get_db),
                     user: models.AkashaUser = Depends(require_permission(PERM))):
    r = db.get(models.EmailRecipient, rid)
    if not r:
        raise HTTPException(status_code=404, detail="No such recipient")
    ports = _check_recipient(db, body)
    r.group_key, r.email, r.name = body.group_key, body.email.strip(), (body.name or "").strip() or None
    r.portfolios, r.active, r.level = ports, body.active, body.level
    security.audit(db, "email.recipient_changed", actor=user, target=r.email,
                   detail={"group": r.group_key, "level": r.level, "active": r.active, "portfolios": ports},
                   ip=client_ip(request))
    db.commit()
    return {"id": r.id}


@router.delete("/recipients/{rid}")
def delete_recipient(rid: int, request: Request, db: Session = Depends(get_db),
                     user: models.AkashaUser = Depends(require_permission(PERM))):
    r = db.get(models.EmailRecipient, rid)
    if not r:
        raise HTTPException(status_code=404, detail="No such recipient")
    security.audit(db, "email.recipient_removed", actor=user, target=r.email, detail={"group": r.group_key},
                   ip=client_ip(request))
    db.delete(r)
    db.commit()
    return {"ok": True}


# ── Log ──────────────────────────────────────────────────────────────────────

def _log_query(db, since, until, status, template, q):
    query = db.query(models.EmailLog)
    if since:
        query = query.filter(models.EmailLog.created_at >= since)
    if until:
        query = query.filter(models.EmailLog.created_at < until)
    if status:
        query = query.filter(models.EmailLog.status.in_(status.split(",")))
    if template:
        query = query.filter(models.EmailLog.template_key == template)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(models.EmailLog.project_name.ilike(like), models.EmailLog.project_id.ilike(like),
                                 models.EmailLog.subject.ilike(like)))
    return query


def _log_filters(since: Optional[datetime] = None, until: Optional[datetime] = None, status: Optional[str] = None,
                 template: Optional[str] = None, q: Optional[str] = None) -> dict:
    return {"since": since, "until": until, "status": status, "template": template, "q": q}


def _log_row(r: models.EmailLog) -> dict:
    return {"id": r.id, "at": _ist(r.created_at), "template_key": r.template_key, "template_version": r.template_version,
            "severity": r.severity, "project_id": r.project_id, "project_name": r.project_name, "phase": r.phase,
            "to": r.to_addrs or [], "cc": r.cc_addrs or [], "subject": r.subject, "status": r.status,
            "detail": r.detail, "attempts": r.attempts, "attachments": r.attachments or [],
            "triggered_by": r.triggered_by, "level": r.level, "alert_id": r.alert_id}


@router.get("/log")
def email_log(db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM)),
              f: dict = Depends(_log_filters), limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    query = _log_query(db, **f)
    total = query.count()
    stats = dict(_log_query(db, **{**f, "status": None}).with_entities(models.EmailLog.status, func.count(models.EmailLog.id))
                 .group_by(models.EmailLog.status).all())
    rows = query.order_by(models.EmailLog.created_at.desc(), models.EmailLog.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "by_status": stats, "entries": [_log_row(r) for r in rows]}


@router.get("/log/{log_id}")
def email_log_entry(log_id: int, db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM))):
    r = db.get(models.EmailLog, log_id)
    if not r:
        raise HTTPException(status_code=404, detail="No such email")
    return {**_log_row(r), "html": r.body_html or "", "event_key": r.event_key}


@router.post("/log/{log_id}/resend")
def email_resend(log_id: int, request: Request, db: Session = Depends(get_db),
                 user: models.AkashaUser = Depends(require_permission(PERM))):
    if not settings().enabled:
        raise HTTPException(status_code=400, detail="Email sending is off (EMAIL_ENABLED=false)")
    try:
        r = engine.resend(db, log_id, user.username)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    security.audit(db, "email.resent", actor=user, target=f"email #{log_id}", detail={"status": r["status"]},
                   ip=client_ip(request))
    db.commit()
    return r


def _csv(header, rows, stem) -> StreamingResponse:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    name = f"{stem}-{(datetime.utcnow() + IST).strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(iter(["﻿" + out.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/log-export")
def export_log(request: Request, db: Session = Depends(get_db),
               user: models.AkashaUser = Depends(require_permission(PERM)), f: dict = Depends(_log_filters)):
    rows = _log_query(db, **f).order_by(models.EmailLog.created_at.desc()).limit(50000).all()
    names = {t.key: t.name for t in db.query(models.EmailTemplate).all()}
    out = [[(r.created_at + IST).strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "", r.status,
            names.get(r.template_key, r.template_key), r.template_version or "", r.severity or "",
            r.project_id or "", r.project_name or "", r.phase or "", "; ".join(r.to_addrs or []),
            "; ".join(r.cc_addrs or []), r.subject or "", ", ".join(r.attachments or []), r.attempts or 1,
            r.triggered_by or "", r.detail or "", f"L{r.level}" if r.level else "", r.alert_id or ""] for r in rows]
    security.audit(db, "email.log_exported", actor=user, target="email log", detail={"rows": len(out)},
                   ip=client_ip(request))
    db.commit()
    return _csv(["time_ist", "status", "template", "template_version", "severity", "project_id", "project", "phase",
                 "to", "cc", "subject", "attachments", "attempts", "triggered_by", "detail", "level", "alert_id"], out,
                "akasha-email-log")


# ── Run ──────────────────────────────────────────────────────────────────────

@router.post("/baseline")
def go_live_baseline(request: Request, db: Session = Depends(get_db),
                     user: models.AkashaUser = Depends(require_permission(PERM))):
    """Go-live: mark every alert already true today as handled, so turning
    email on does not flood people with the backlog."""
    r = engine.baseline(db, user.username)
    security.audit(db, "email.baseline", actor=user, target="email alerts", detail={"result": r["message"]},
                   ip=client_ip(request))
    db.commit()
    return r



class RunIn(BaseModel):
    dry_run: bool = True
    only: Optional[List[str]] = None


@router.post("/run")
def run_now(body: RunIn, request: Request, db: Session = Depends(get_db),
            user: models.AkashaUser = Depends(require_permission(PERM))):
    """Dry run (default): what the next pass would send, nothing sent or
    recorded. Real run: needs EMAIL_ENABLED."""
    if not body.dry_run and not settings().enabled:
        raise HTTPException(status_code=400, detail="Email sending is off (EMAIL_ENABLED=false)")
    r = engine.run(db, triggered_by=user.username, dry_run=body.dry_run, only=body.only)
    if not body.dry_run:
        security.audit(db, "email.run", actor=user, target="email alerts", detail={"result": r["message"]},
                       ip=client_ip(request))
        db.commit()
    return r


# ── Alerts (acknowledgement and escalation) ──────────────────────────────────

@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db), _: models.AkashaUser = Depends(require_permission(PERM)),
                status: Optional[str] = Query("open", pattern="^(open|resolved|)$"),
                level: Optional[int] = Query(None, ge=1, le=3), template: Optional[str] = None, q: Optional[str] = None,
                ack: Optional[str] = Query(None, pattern="^(awaiting|acknowledged|)$"),
                limit: int = Query(200, ge=1, le=1000)):
    """Alerts in the current mode (test alerts while EMAIL_TEST_MODE is on),
    with counts for the filter chips."""
    from routers import alerts as alerts_router
    test = settings().test_mode
    counts = {"open": 0, "awaiting": 0, "acknowledged": 0, "resolved": 0, "by_level": {"1": 0, "2": 0, "3": 0}}
    for a in db.query(models.EmailAlert).filter(models.EmailAlert.test.is_(test)).all():
        if a.status == "open":
            counts["open"] += 1
            counts["acknowledged" if a.acknowledged_at else "awaiting"] += 1
            counts["by_level"][str(a.level or 1)] = counts["by_level"].get(str(a.level or 1), 0) + 1
        else:
            counts["resolved"] += 1
    query = (alerts_router.admin_query(db, status or None, level, template, q, ack or None)
             .filter(models.EmailAlert.test.is_(test)))
    names = alerts_router._names(db)
    rows = query.order_by(models.EmailAlert.last_sent_at.desc().nullslast(), models.EmailAlert.id.desc()).limit(limit).all()
    return {"test_mode": test, "counts": counts, "total": query.count(),
            "alerts": [alerts_router.serialize(db, a, names) for a in rows]}


@router.get("/alerts-export")
def export_alerts(request: Request, db: Session = Depends(get_db), user: models.AkashaUser = Depends(require_permission(PERM)),
                  status: Optional[str] = None, level: Optional[int] = None, template: Optional[str] = None,
                  q: Optional[str] = None, ack: Optional[str] = None):
    from routers import alerts as alerts_router
    test = settings().test_mode
    names = alerts_router._names(db)
    rows = (alerts_router.admin_query(db, status or None, level, template, q, ack or None)
            .filter(models.EmailAlert.test.is_(test)).order_by(models.EmailAlert.id.desc()).limit(50000).all())
    tnames = {t.key: t.name for t in db.query(models.EmailTemplate).all()}

    def fmt(dt):
        return (dt + IST).strftime("%Y-%m-%d %H:%M") if dt else ""

    out = []
    for a in rows:
        rec = A.recipients(db, a)
        out.append([a.id, a.status, tnames.get(a.template_key, a.template_key), a.project_id or "", a.project_name or "",
                    a.phase or "", a.due_date or "", f"L{a.level or 1}", a.emails or 0, fmt(a.opened_at), fmt(a.last_sent_at),
                    "; ".join(f"{names.get(r.email.lower(), r.email)} (L{r.level})"
                              f"{' - acknowledged' if r.acknowledged_at else ''}" for r in rec),
                    fmt(a.acknowledged_at), a.acknowledged_by or "", f"L{a.ack_level}" if a.ack_level else "",
                    a.update_note or "", a.expected_date.date().isoformat() if a.expected_date else "",
                    fmt(a.resolved_at), a.resolved_reason or ""])
    security.audit(db, "email.alerts_exported", actor=user, target="email alerts", detail={"rows": len(out)},
                   ip=client_ip(request))
    db.commit()
    return _csv(["alert_id", "status", "latest_email", "project_id", "project", "phase", "ordering_date", "level", "emails",
                 "opened_ist", "last_email_ist", "to_recipients", "acknowledged_ist", "acknowledged_by",
                 "acknowledged_at_level", "update", "expected_date", "closed_ist", "closed_because"], out,
                "akasha-email-alerts")
