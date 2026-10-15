"""Administration: users, roles and the audit log.

Guard rails, all enforced here rather than trusted to the UI:
- Only a superadmin can create, edit or reset a superadmin, or grant the
  administration permissions (users / roles / audit) to a role - holding
  users.manage or roles.manage alone cannot be turned into more power.
- Nobody can deactivate, demote or lock out themselves, and the last active
  superadmin cannot be removed.
- Accounts are deactivated, never deleted, so the audit trail stays whole.
- A new account or a reset gets a one-time temporary password, shown once to
  the administrator, which the user must change at first sign-in.
"""
import csv
import io
import json
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import AkashaAuditLog, AkashaRole, AkashaSession, AkashaUser
from routers.auth import client_ip, require_permission
from services import access, portfolio, security

router = APIRouter(prefix="/api/admin", tags=["Administration"])

ADMIN_PERMS = {p.key for p in access.PERMISSIONS if p.group == "Administration"}
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,40}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_super(user: AkashaUser) -> bool:
    return user.role == access.SUPERADMIN


def _active_superadmins(db: Session) -> int:
    return db.query(AkashaUser).filter(AkashaUser.role == access.SUPERADMIN,
                                       AkashaUser.is_active == True).count()  # noqa: E712


def _role_or_400(db: Session, key: str) -> AkashaRole:
    role = db.query(AkashaRole).filter(AkashaRole.key == key).first()
    if not role:
        raise HTTPException(status_code=400, detail=f"Unknown role '{key}'")
    return role


# "Online now" = a call in the last 10 minutes. The app sends no heartbeat (it
# would defeat the idle timeout), so someone reading one screen for longer
# shows as signed in but idle.
ONLINE_WINDOW = timedelta(minutes=10)
IST = timedelta(hours=5, minutes=30)


def _clean_department(value: Optional[str]) -> Optional[str]:
    v = " ".join((value or "").split())
    if len(v) > 60:
        raise HTTPException(status_code=400, detail="Department: at most 60 characters")
    return v or None


def _is_privileged(db: Session, role_key: Optional[str]) -> bool:
    """Superadmin, or a role holding any administration permission."""
    if not role_key:
        return False
    return role_key == access.SUPERADMIN or bool(set(access.role_permissions(db, role_key)) & ADMIN_PERMS)


def _user_row(u: AkashaUser, roles: dict, sessions: dict) -> dict:
    now = datetime.utcnow()
    return {
        "id": u.id, "username": u.username, "display_name": u.display_name, "email": u.email or "",
        "department": u.department or "",
        "role": u.role, "role_name": roles.get(u.role, u.role), "is_active": bool(u.is_active),
        "locked": bool(u.locked_until and u.locked_until > now),
        "locked_until": u.locked_until.isoformat() if u.locked_until and u.locked_until > now else None,
        "must_change_password": bool(u.must_change_password),
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "active_sessions": sessions.get(u.id, 0),
        # [] = every portfolio
        "portfolios": [] if u.role == access.SUPERADMIN else list(u.portfolios or []),
    }


def _clean_portfolios(db: Session, values: Optional[list[str]], role: str) -> Optional[list[str]]:
    """Validated cluster names, or None for every portfolio (always for superadmin)."""
    if role == access.SUPERADMIN or not values:
        return None
    known = {c.lower(): c for c in portfolio.all_clusters(db)}
    unknown = [v for v in values if v.strip().lower() not in known]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown portfolio(s): {', '.join(unknown)}")
    picked = sorted({known[v.strip().lower()] for v in values})
    return None if set(picked) == set(known.values()) else picked


def _get_user(db: Session, user_id: int, actor: AkashaUser) -> AkashaUser:
    u = db.query(AkashaUser).filter(AkashaUser.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if _is_super(u) and not _is_super(actor):
        raise HTTPException(status_code=403, detail="Only a superadmin can change a superadmin account")
    return u


# ── Catalogue ────────────────────────────────────────────────────────────────

@router.get("/portfolios")
def portfolios(db: Session = Depends(get_db),
               _: AkashaUser = Depends(require_permission("users.manage"))):
    """Every portfolio (project_mapping cluster) a user can be given."""
    return {"portfolios": portfolio.all_clusters(db)}


@router.get("/permissions")
def permissions(_: AkashaUser = Depends(require_permission("users.manage", "roles.manage"))):
    return {"permissions": [{"key": p.key, "label": p.label, "group": p.group, "description": p.description}
                            for p in access.PERMISSIONS],
            "dashboards": access.dashboards_for(frozenset(access.PERMISSION_KEYS))}


# ── Users ────────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(db: Session = Depends(get_db),
               _: AkashaUser = Depends(require_permission("users.manage"))):
    roles = {r.key: r.name for r in db.query(AkashaRole)}
    now = datetime.utcnow()
    sessions = dict(db.query(AkashaSession.user_id, func.count()).filter(
        AkashaSession.expires_at > now,
        (AkashaSession.last_seen_at.is_(None)) | (AkashaSession.last_seen_at > now - security.SESSION_IDLE),
    ).group_by(AkashaSession.user_id).all())
    users = db.query(AkashaUser).order_by(AkashaUser.is_active.desc(), func.lower(AkashaUser.display_name)).all()
    return {"users": [_user_row(u, roles, sessions) for u in users]}


class UserCreate(BaseModel):
    username: str
    display_name: str
    email: Optional[str] = None
    role: str
    password: Optional[str] = None   # omitted -> a temporary password is generated
    portfolios: Optional[list[str]] = None   # omitted / empty -> every portfolio
    department: Optional[str] = None


@router.post("/users")
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db),
                actor: AkashaUser = Depends(require_permission("users.manage"))):
    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="Username: 3-40 letters, digits, dot, dash or underscore")
    if not body.display_name.strip():
        raise HTTPException(status_code=400, detail="Enter the person's name")
    email = (body.email or "").strip() or None
    if email and not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    _role_or_400(db, body.role)
    if body.role == access.SUPERADMIN and not _is_super(actor):
        raise HTTPException(status_code=403, detail="Only a superadmin can create a superadmin")
    clash = db.query(AkashaUser).filter(
        (func.lower(AkashaUser.username) == username.lower())
        | ((func.lower(AkashaUser.email) == email.lower()) if email else False)).first()
    if clash:
        raise HTTPException(status_code=409, detail="That username or email is already in use")

    temp = None
    if body.password:
        problems = security.password_problems(body.password, username)
        if problems:
            raise HTTPException(status_code=400, detail="Password needs: " + "; ".join(problems))
        password = body.password
    else:
        password = temp = security.temporary_password()
    u = AkashaUser(username=username, display_name=body.display_name.strip(), email=email, role=body.role,
                   password_hash=security.hash_password(password), is_active=True,
                   must_change_password=True, created_at=datetime.utcnow(), created_by=actor.id,
                   portfolios=_clean_portfolios(db, body.portfolios, body.role),
                   department=_clean_department(body.department))
    db.add(u)
    db.flush()
    security.audit(db, "user.created", actor=actor, target=username,
                   detail={"role": body.role, "email": email, "portfolios": u.portfolios or "all",
                           "department": u.department},
                   ip=client_ip(request))
    if _is_privileged(db, body.role):
        security.audit(db, "user.privileged_change", actor=actor, target=username,
                       detail={"role": [None, body.role]}, ip=client_ip(request))
    db.commit()
    roles = {r.key: r.name for r in db.query(AkashaRole)}
    return {"user": _user_row(u, roles, {}), "temporary_password": temp}


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    portfolios: Optional[list[str]] = None   # [] = every portfolio
    department: Optional[str] = None         # "" clears it


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                actor: AkashaUser = Depends(require_permission("users.manage"))):
    u = _get_user(db, user_id, actor)
    changes = {}
    if body.display_name is not None and body.display_name.strip() != u.display_name:
        if not body.display_name.strip():
            raise HTTPException(status_code=400, detail="Enter the person's name")
        changes["display_name"] = [u.display_name, body.display_name.strip()]
        u.display_name = body.display_name.strip()
    if body.email is not None and (body.email.strip() or None) != u.email:
        email = body.email.strip() or None
        if email and not EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Enter a valid email address")
        if email and db.query(AkashaUser).filter(func.lower(AkashaUser.email) == email.lower(),
                                                 AkashaUser.id != u.id).first():
            raise HTTPException(status_code=409, detail="That email is already in use")
        changes["email"] = [u.email, email]
        u.email = email
    if body.role is not None and body.role != u.role:
        _role_or_400(db, body.role)
        if u.id == actor.id:
            raise HTTPException(status_code=400, detail="You cannot change your own role")
        if body.role == access.SUPERADMIN and not _is_super(actor):
            raise HTTPException(status_code=403, detail="Only a superadmin can grant the superadmin role")
        if u.role == access.SUPERADMIN and u.is_active and _active_superadmins(db) <= 1:
            raise HTTPException(status_code=400, detail="This is the last active superadmin")
        changes["role"] = [u.role, body.role]
        u.role = body.role
    if body.is_active is not None and body.is_active != bool(u.is_active):
        if u.id == actor.id:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
        if not body.is_active and u.role == access.SUPERADMIN and _active_superadmins(db) <= 1:
            raise HTTPException(status_code=400, detail="This is the last active superadmin")
        changes["is_active"] = [bool(u.is_active), body.is_active]
        u.is_active = body.is_active
        if not body.is_active:
            security.end_all_sessions(db, u.id)
    if body.department is not None and _clean_department(body.department) != u.department:
        changes["department"] = [u.department, _clean_department(body.department)]
        u.department = _clean_department(body.department)
    if body.portfolios is not None or "role" in changes:
        new = _clean_portfolios(db, body.portfolios if body.portfolios is not None else u.portfolios, u.role)
        if (new or None) != (u.portfolios or None):
            changes["portfolios"] = [u.portfolios or "all", new or "all"]
            u.portfolios = new
    if not changes:
        return {"user": None, "changed": False}
    u.updated_at = datetime.utcnow()
    # A role change takes effect on the next request; end sessions so the
    # user's open screens reload with the new access.
    if "role" in changes or "portfolios" in changes:
        security.end_all_sessions(db, u.id)
    security.audit(db, "user.updated", actor=actor, target=u.username, detail=changes, ip=client_ip(request))
    if "role" in changes and any(_is_privileged(db, r) for r in changes["role"]):
        security.audit(db, "user.privileged_change", actor=actor, target=u.username,
                       detail={"role": changes["role"]}, ip=client_ip(request))
    db.commit()
    roles = {r.key: r.name for r in db.query(AkashaRole)}
    return {"user": _user_row(u, roles, {}), "changed": True}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, request: Request, db: Session = Depends(get_db),
                   actor: AkashaUser = Depends(require_permission("users.manage"))):
    u = _get_user(db, user_id, actor)
    if u.id == actor.id:
        raise HTTPException(status_code=400, detail="Change your own password from your account menu")
    temp = security.temporary_password()
    u.password_hash = security.hash_password(temp)
    u.must_change_password = True
    u.failed_login_count = 0
    u.locked_until = None
    u.updated_at = datetime.utcnow()
    ended = security.end_all_sessions(db, u.id)
    security.audit(db, "user.password_reset", actor=actor, target=u.username,
                   detail={"sessions_ended": ended}, ip=client_ip(request))
    db.commit()
    return {"temporary_password": temp}


@router.post("/users/{user_id}/unlock")
def unlock(user_id: int, request: Request, db: Session = Depends(get_db),
           actor: AkashaUser = Depends(require_permission("users.manage"))):
    u = _get_user(db, user_id, actor)
    u.locked_until = None
    u.failed_login_count = 0
    security.audit(db, "user.unlocked", actor=actor, target=u.username, ip=client_ip(request))
    db.commit()
    return {"success": True}


@router.post("/users/{user_id}/end-sessions")
def end_sessions(user_id: int, request: Request, db: Session = Depends(get_db),
                 actor: AkashaUser = Depends(require_permission("users.manage"))):
    u = _get_user(db, user_id, actor)
    if u.id == actor.id:
        raise HTTPException(status_code=400, detail="Use Sign out to end your own session")
    ended = security.end_all_sessions(db, u.id)
    security.audit(db, "user.sessions_ended", actor=actor, target=u.username,
                   detail={"sessions_ended": ended}, ip=client_ip(request))
    db.commit()
    return {"sessions_ended": ended}


# ── Roles ────────────────────────────────────────────────────────────────────

def _role_row(r: AkashaRole, counts: dict) -> dict:
    perms = sorted(access.PERMISSION_KEYS) if r.key == access.SUPERADMIN else sorted(
        p for p in (r.permissions or []) if p in access.PERMISSION_KEYS)
    return {"key": r.key, "name": r.name, "description": r.description or "", "permissions": perms,
            "is_system": bool(r.is_system), "locked": r.key == access.SUPERADMIN,
            "user_count": counts.get(r.key, 0)}


@router.get("/roles")
def list_roles(db: Session = Depends(get_db),
               _: AkashaUser = Depends(require_permission("users.manage", "roles.manage"))):
    counts = dict(db.query(AkashaUser.role, func.count()).filter(AkashaUser.is_active == True)  # noqa: E712
                  .group_by(AkashaUser.role).all())
    order = {r["key"]: i for i, r in enumerate(access.DEFAULT_ROLES)}
    roles = sorted(db.query(AkashaRole).all(), key=lambda r: (order.get(r.key, 99), r.name.lower()))
    return {"roles": [_role_row(r, counts) for r in roles]}


class RoleBody(BaseModel):
    key: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[list[str]] = None


def _check_grant(actor: AkashaUser, before: set, after: set) -> None:
    unknown = after - access.PERMISSION_KEYS
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown permission(s): {', '.join(sorted(unknown))}")
    if ((after ^ before) & ADMIN_PERMS) and not _is_super(actor):
        raise HTTPException(status_code=403, detail="Only a superadmin can grant or remove administration permissions")


@router.post("/roles")
def create_role(body: RoleBody, request: Request, db: Session = Depends(get_db),
                actor: AkashaUser = Depends(require_permission("roles.manage"))):
    key = (body.key or "").strip().lower()
    if not re.match(r"^[a-z][a-z0-9_]{2,30}$", key):
        raise HTTPException(status_code=400, detail="Role key: 3-31 lowercase letters, digits or underscore")
    if db.query(AkashaRole).filter(AkashaRole.key == key).first():
        raise HTTPException(status_code=409, detail="A role with that key exists")
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="Enter a role name")
    perms = set(body.permissions or [])
    _check_grant(actor, set(), perms)
    r = AkashaRole(key=key, name=body.name.strip(), description=(body.description or "").strip(),
                   permissions=sorted(perms), is_system=False, created_at=datetime.utcnow())
    db.add(r)
    security.audit(db, "role.created", actor=actor, target=key, detail={"permissions": sorted(perms)},
                   ip=client_ip(request))
    db.commit()
    access.invalidate()
    return {"role": _role_row(r, {})}


@router.patch("/roles/{key}")
def update_role(key: str, body: RoleBody, request: Request, db: Session = Depends(get_db),
                actor: AkashaUser = Depends(require_permission("roles.manage"))):
    r = db.query(AkashaRole).filter(AkashaRole.key == key).first()
    if not r:
        raise HTTPException(status_code=404, detail="Role not found")
    if key == access.SUPERADMIN:
        raise HTTPException(status_code=400, detail="The Super Admin role always holds every permission")
    changes = {}
    if body.name is not None and body.name.strip() and body.name.strip() != r.name:
        changes["name"] = [r.name, body.name.strip()]
        r.name = body.name.strip()
    if body.description is not None and body.description.strip() != (r.description or ""):
        changes["description"] = [r.description, body.description.strip()]
        r.description = body.description.strip()
    if body.permissions is not None:
        before, after = set(r.permissions or []), set(body.permissions)
        _check_grant(actor, before, after)
        if before != after:
            changes["added"] = sorted(after - before)
            changes["removed"] = sorted(before - after)
            r.permissions = sorted(after)
    if not changes:
        return {"role": None, "changed": False}
    r.updated_at = datetime.utcnow()
    security.audit(db, "role.updated", actor=actor, target=key, detail=changes, ip=client_ip(request))
    granted = [p for p in changes.get("added", []) if p in ADMIN_PERMS]
    revoked = [p for p in changes.get("removed", []) if p in ADMIN_PERMS]
    if granted or revoked:
        security.audit(db, "role.admin_grant", actor=actor, target=key,
                       detail={"added": granted, "removed": revoked}, ip=client_ip(request))
    db.commit()
    access.invalidate()
    counts = dict(db.query(AkashaUser.role, func.count()).filter(AkashaUser.role == key).group_by(AkashaUser.role).all())
    return {"role": _role_row(r, counts), "changed": True}


@router.delete("/roles/{key}")
def delete_role(key: str, request: Request, db: Session = Depends(get_db),
                actor: AkashaUser = Depends(require_permission("roles.manage"))):
    r = db.query(AkashaRole).filter(AkashaRole.key == key).first()
    if not r:
        raise HTTPException(status_code=404, detail="Role not found")
    if r.is_system:
        raise HTTPException(status_code=400, detail="Built-in roles cannot be deleted")
    if db.query(AkashaUser).filter(AkashaUser.role == key).count():
        raise HTTPException(status_code=400, detail="Move this role's users to another role first")
    db.delete(r)
    security.audit(db, "role.deleted", actor=actor, target=key, ip=client_ip(request))
    db.commit()
    access.invalidate()
    return {"success": True}


# ── Audit ────────────────────────────────────────────────────────────────────

# What each category filter in the activity log matches (prefixes end in ".").
CATEGORIES = {
    "signin": ("login.", "logout", "password."),
    "changes": ("data.", "notification."),
    "admin": ("user.", "role.", "api_key.created", "api_key.revoked", "audit.", "session."),
    "access": ("access.", "api_key.invalid"),
}
ALERT_LEVELS = ("warning", "critical")


def _audit_query(db: Session, *, action=None, q=None, category=None, severity=None, department=None,
                 user=None, since=None, until=None, open_alerts=False):
    query = db.query(AkashaAuditLog)
    if action:
        query = query.filter(AkashaAuditLog.action.like(f"{action}%"))
    if category:
        prefixes = CATEGORIES.get(category)
        if prefixes is None:
            raise HTTPException(status_code=400, detail=f"Unknown category '{category}'")
        cond = None
        for p in prefixes:
            c = AkashaAuditLog.action.like(f"{p}%") if p.endswith(".") else AkashaAuditLog.action == p
            cond = c if cond is None else (cond | c)
        query = query.filter(cond)
    if severity:
        query = query.filter(AkashaAuditLog.severity.in_([v for v in severity.split(",") if v]))
    if open_alerts:
        query = query.filter(AkashaAuditLog.severity.in_(ALERT_LEVELS), AkashaAuditLog.acknowledged_at.is_(None))
    if user:
        query = query.filter((func.lower(AkashaAuditLog.actor_username) == user.lower())
                             | (func.lower(AkashaAuditLog.target) == user.lower()))
    if department:
        names = [n.lower() for (n,) in db.query(AkashaUser.username).filter(
            func.lower(AkashaUser.department) == department.lower())]
        if not names:
            return query.filter(False)
        query = query.filter(func.lower(AkashaAuditLog.actor_username).in_(names)
                             | func.lower(AkashaAuditLog.target).in_(names))
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(func.lower(AkashaAuditLog.target).like(like)
                             | func.lower(AkashaAuditLog.actor_username).like(like)
                             | func.lower(AkashaAuditLog.action).like(like)
                             | func.lower(AkashaAuditLog.ip).like(like))
    if since:
        query = query.filter(AkashaAuditLog.at >= since)
    if until:
        query = query.filter(AkashaAuditLog.at < until)
    return query


def _people(db: Session) -> dict:
    return {u.lower(): {"name": n, "department": d or None}
            for u, n, d in db.query(AkashaUser.username, AkashaUser.display_name, AkashaUser.department)}


def _audit_row(a: AkashaAuditLog, people: dict) -> dict:
    actor = people.get((a.actor_username or "").lower()) or {}
    # The department of whoever did it, else of the account it was done to
    # (a failed sign-in has no actor, only a target).
    dept = actor.get("department") or (people.get((a.target or "").lower()) or {}).get("department")
    return {"id": a.id, "at": a.at.isoformat() if a.at else None, "actor": a.actor_username,
            "actor_name": actor.get("name"), "department": dept,
            "action": a.action, "target": a.target, "detail": a.detail, "ip": a.ip,
            "severity": a.severity or "info",
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            "acknowledged_by": a.acknowledged_by}


def _filters(action: Optional[str] = Query(None), q: Optional[str] = Query(None),
             category: Optional[str] = Query(None), severity: Optional[str] = Query(None),
             department: Optional[str] = Query(None), user: Optional[str] = Query(None),
             since: Optional[datetime] = Query(None, description="UTC"),
             until: Optional[datetime] = Query(None, description="UTC"),
             open_alerts: bool = Query(False)) -> dict:
    return {"action": action, "q": q, "category": category, "severity": severity, "department": department,
            "user": user, "since": since, "until": until, "open_alerts": open_alerts}


@router.get("/audit")
def audit_log(db: Session = Depends(get_db),
              _: AkashaUser = Depends(require_permission("audit.view")),
              f: dict = Depends(_filters),
              limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    query = _audit_query(db, **f)
    total = query.count()
    rows = query.order_by(AkashaAuditLog.at.desc(), AkashaAuditLog.id.desc()).offset(offset).limit(limit).all()
    people = _people(db)
    return {"total": total, "entries": [_audit_row(a, people) for a in rows]}


EXPORT_MAX = 50000


def _ist(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return (dt + IST).strftime(fmt) if dt else ""


def _csv_response(header: list, rows: list, stem: str) -> StreamingResponse:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    name = f"{stem}-{(datetime.utcnow() + IST).strftime('%Y%m%d-%H%M')}.csv"
    # BOM so Excel opens it as UTF-8
    return StreamingResponse(iter(["﻿" + out.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/audit/export")
def export_audit(request: Request, db: Session = Depends(get_db),
                 actor: AkashaUser = Depends(require_permission("audit.view")),
                 f: dict = Depends(_filters)):
    """The activity log with the screen's filters, as CSV (IST and UTC times).
    The export itself is recorded."""
    query = _audit_query(db, **f)
    total = query.count()
    rows = query.order_by(AkashaAuditLog.at.desc(), AkashaAuditLog.id.desc()).limit(EXPORT_MAX).all()
    people = _people(db)
    used = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in f.items() if v}
    security.audit(db, "audit.exported", actor=actor, target="activity log",
                   detail={"rows": len(rows), "matching": total, "filters": used}, ip=client_ip(request))
    db.commit()
    out = []
    for a in rows:
        r = _audit_row(a, people)
        out.append([_ist(a.at), a.at.strftime("%Y-%m-%d %H:%M:%S") if a.at else "", r["severity"], a.action,
                    a.actor_username or "", r["actor_name"] or "", r["department"] or "", a.target or "",
                    a.ip or "", "" if a.detail is None else json.dumps(a.detail, default=str),
                    a.acknowledged_by or "", _ist(a.acknowledged_at)])
    return _csv_response(["time_ist", "time_utc", "severity", "event", "by_username", "by_name", "department",
                          "target", "ip", "detail", "acknowledged_by", "acknowledged_at_ist"], out,
                         "akasha-activity")


@router.get("/users/export")
def export_users(request: Request, db: Session = Depends(get_db),
                 actor: AkashaUser = Depends(require_permission("users.manage"))):
    roles = {r.key: r.name for r in db.query(AkashaRole)}
    users = db.query(AkashaUser).order_by(func.lower(AkashaUser.department), func.lower(AkashaUser.display_name)).all()
    security.audit(db, "audit.users_exported", actor=actor, target="user list",
                   detail={"rows": len(users)}, ip=client_ip(request))
    db.commit()
    now = datetime.utcnow()
    out = []
    for u in users:
        status = ("inactive" if not u.is_active else "locked" if u.locked_until and u.locked_until > now
                  else "must change password" if u.must_change_password else "active")
        out.append([u.username, u.display_name, u.email or "", u.department or "", roles.get(u.role, u.role),
                    "all" if u.role == access.SUPERADMIN or not u.portfolios else "; ".join(u.portfolios),
                    status, _ist(u.last_login_at, "%Y-%m-%d %H:%M"), _ist(u.created_at, "%Y-%m-%d %H:%M")])
    return _csv_response(["username", "name", "email", "department", "role", "portfolios", "status",
                          "last_sign_in_ist", "created_ist"], out, "akasha-users")


# ── Activity: who is online, sign-ins and changes by department ─────────────

def _session_ref(token_hash: str) -> str:
    # A handle for one session. The stored token is already a SHA-256, so a
    # prefix of it identifies the row without revealing anything usable.
    return token_hash[:16]


def _device(ua: Optional[str]) -> str:
    ua = ua or ""
    browser = next((b for k, b in (("Edg/", "Edge"), ("Chrome/", "Chrome"), ("Firefox/", "Firefox"),
                                   ("Safari/", "Safari")) if k in ua), "Other")
    system = next((o for k, o in (("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"),
                                  ("iPad", "iPad"), ("Mac OS", "macOS"), ("Linux", "Linux")) if k in ua), "")
    return f"{browser} on {system}" if system else browser


@router.get("/activity")
def activity(db: Session = Depends(get_db),
             _: AkashaUser = Depends(require_permission("audit.view")),
             days: int = Query(7, ge=1, le=90)):
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    today = (now + IST).replace(hour=0, minute=0, second=0, microsecond=0) - IST   # midnight IST, in UTC
    users = {u.id: u for u in db.query(AkashaUser)}
    roles = {r.key: r.name for r in db.query(AkashaRole)}

    live = db.query(AkashaSession).filter(
        AkashaSession.expires_at > now,
        (AkashaSession.last_seen_at.is_(None)) | (AkashaSession.last_seen_at > now - security.SESSION_IDLE),
    ).all()
    sessions = []
    for s in live:
        u = users.get(s.user_id)
        if not u or not u.is_active:
            continue
        seen = s.last_seen_at or s.created_at
        sessions.append({
            "ref": _session_ref(s.token), "user_id": u.id, "username": u.username, "name": u.display_name,
            "department": u.department or None, "role_name": roles.get(u.role, u.role),
            "started_at": s.created_at.isoformat() if s.created_at else None,
            "last_seen_at": seen.isoformat() if seen else None,
            "online": bool(seen and seen > now - ONLINE_WINDOW),
            "view": s.last_view, "ip": s.ip, "device": _device(s.user_agent),
        })
    sessions.sort(key=lambda x: x["last_seen_at"] or "", reverse=True)

    def count(*conds) -> int:
        return db.query(AkashaAuditLog).filter(*conds).count()

    failed = ("login.failed", "login.locked", "login.blocked_locked")
    summary = {
        "online_now": len({x["user_id"] for x in sessions if x["online"]}),
        "signed_in": len({x["user_id"] for x in sessions}),
        "sign_ins_today": count(AkashaAuditLog.action == "login.success", AkashaAuditLog.at >= today),
        "people_today": db.query(func.count(func.distinct(AkashaAuditLog.actor_username))).filter(
            AkashaAuditLog.action == "login.success", AkashaAuditLog.at >= today).scalar() or 0,
        "failed_today": count(AkashaAuditLog.action.in_(failed), AkashaAuditLog.at >= today),
        "changes_today": count(AkashaAuditLog.action.like("data.%"), AkashaAuditLog.at >= today),
        "denied_today": count(AkashaAuditLog.action.like("access.%"), AkashaAuditLog.at >= today),
        "alerts_open": count(AkashaAuditLog.severity.in_(ALERT_LEVELS), AkashaAuditLog.acknowledged_at.is_(None)),
        "critical_open": count(AkashaAuditLog.severity == "critical", AkashaAuditLog.acknowledged_at.is_(None)),
    }

    # Per person over the window, rolled up by department.
    by_user: dict = {}
    for name, action, n in db.query(AkashaAuditLog.actor_username, AkashaAuditLog.action, func.count()).filter(
            AkashaAuditLog.at >= since, AkashaAuditLog.actor_username.isnot(None)).group_by(
            AkashaAuditLog.actor_username, AkashaAuditLog.action):
        row = by_user.setdefault(name.lower(), {"sign_ins": 0, "changes": 0, "denied": 0})
        if action == "login.success":
            row["sign_ins"] += n
        elif action.startswith(("data.", "notification.")):
            row["changes"] += n
        elif action.startswith("access."):
            row["denied"] += n
    online_ids = {x["user_id"] for x in sessions if x["online"]}
    depts: dict = {}
    people = []
    for u in users.values():
        if not u.is_active:
            continue
        stats = by_user.get(u.username.lower(), {"sign_ins": 0, "changes": 0, "denied": 0})
        dept = u.department or "Unassigned"
        d = depts.setdefault(dept, {"department": dept, "users": 0, "online": 0, "active_users": 0,
                                    "sign_ins": 0, "changes": 0, "denied": 0})
        d["users"] += 1
        d["online"] += int(u.id in online_ids)
        d["active_users"] += int(stats["sign_ins"] > 0)
        for k in ("sign_ins", "changes", "denied"):
            d[k] += stats[k]
        people.append({"user_id": u.id, "username": u.username, "name": u.display_name,
                       "department": u.department or None, "role_name": roles.get(u.role, u.role),
                       "online": u.id in online_ids,
                       "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None, **stats})
    people.sort(key=lambda p: (-(p["sign_ins"] + p["changes"] + p["denied"]), p["name"].lower()))
    return {"days": days, "summary": summary, "sessions": sessions, "people": people,
            "departments": sorted(depts.values(),
                                  key=lambda d: (d["department"] == "Unassigned", d["department"].lower()))}


@router.get("/departments")
def departments(db: Session = Depends(get_db),
                _: AkashaUser = Depends(require_permission("users.manage", "audit.view"))):
    rows = db.query(AkashaUser.department).filter(AkashaUser.department.isnot(None)).distinct().all()
    return {"departments": sorted({d for (d,) in rows if d}, key=str.lower)}


@router.post("/sessions/{ref}/end")
def end_one_session(ref: str, request: Request, db: Session = Depends(get_db),
                    actor: AkashaUser = Depends(require_permission("users.manage"))):
    if not re.fullmatch(r"[0-9a-f]{16}", ref):
        raise HTTPException(status_code=400, detail="Unknown session")
    s = db.query(AkashaSession).filter(AkashaSession.token.like(f"{ref}%")).first()
    if not s:
        raise HTTPException(status_code=404, detail="That session has already ended")
    u = _get_user(db, s.user_id, actor)
    if u.id == actor.id:
        raise HTTPException(status_code=400, detail="Use Sign out to end your own session")
    detail = {"ip": s.ip, "device": _device(s.user_agent)}
    db.delete(s)
    security.audit(db, "session.ended", actor=actor, target=u.username, detail=detail, ip=client_ip(request))
    db.commit()
    return {"success": True}


# ── Security alerts ──────────────────────────────────────────────────────────

@router.get("/alerts/summary")
def alerts_summary(db: Session = Depends(get_db),
                   _: AkashaUser = Depends(require_permission("audit.view"))):
    """For the badge the app polls: open alerts and the newest one."""
    open_q = _audit_query(db, open_alerts=True)
    latest = open_q.order_by(AkashaAuditLog.id.desc()).first()
    return {"open": open_q.count(),
            "critical": open_q.filter(AkashaAuditLog.severity == "critical").count(),
            "latest": _audit_row(latest, _people(db)) if latest else None}


class AckBody(BaseModel):
    ids: Optional[list[int]] = None   # omitted -> every open alert


@router.post("/alerts/acknowledge")
def acknowledge(body: AckBody, request: Request, db: Session = Depends(get_db),
                actor: AkashaUser = Depends(require_permission("audit.view"))):
    q = _audit_query(db, open_alerts=True)
    if body.ids is not None:
        q = q.filter(AkashaAuditLog.id.in_(body.ids))
    n = q.update({AkashaAuditLog.acknowledged_at: datetime.utcnow(),
                  AkashaAuditLog.acknowledged_by: actor.username}, synchronize_session=False)
    if n:
        security.audit(db, "audit.alerts_acknowledged", actor=actor, target=f"{n} alert{'s' if n != 1 else ''}",
                       detail={"ids": body.ids} if body.ids is not None else {"all": True}, ip=client_ip(request))
    db.commit()
    return {"acknowledged": n}


# ── API keys (for systems reading /api/v1) ──────────────────────────────────

def _key_row(k) -> dict:
    now = datetime.utcnow()
    state = "revoked" if k.revoked_at else "expired" if (k.expires_at and k.expires_at < now) else "active"
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "portfolios": list(k.portfolios or []),
            "state": state, "created_at": k.created_at.isoformat() if k.created_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "use_count": k.use_count or 0}


@router.get("/api-keys")
def list_api_keys(db: Session = Depends(get_db),
                  _: AkashaUser = Depends(require_permission("users.manage"))):
    from models import AkashaApiKey
    return {"keys": [_key_row(k) for k in db.query(AkashaApiKey).order_by(AkashaApiKey.created_at.desc()).all()]}


class ApiKeyCreate(BaseModel):
    name: str
    portfolios: Optional[list[str]] = None   # omitted / empty -> every portfolio
    expires_in_days: Optional[int] = 365


@router.post("/api-keys")
def create_api_key(body: ApiKeyCreate, request: Request, db: Session = Depends(get_db),
                   actor: AkashaUser = Depends(require_permission("users.manage"))):
    """Issue a read-only key for /api/v1. The key is returned once and only its
    hash is kept - it cannot be shown again, only revoked and replaced."""
    from datetime import timedelta
    from models import AkashaApiKey
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name the system or team that will use the key")
    if body.expires_in_days is not None and not 1 <= body.expires_in_days <= 730:
        raise HTTPException(status_code=400, detail="Expiry must be 1-730 days")
    key, prefix, digest = security.new_api_key()
    k = AkashaApiKey(name=body.name.strip(), prefix=prefix, key_hash=digest,
                     portfolios=_clean_portfolios(db, body.portfolios, "integration"),
                     created_by=actor.id, created_at=datetime.utcnow(),
                     expires_at=(datetime.utcnow() + timedelta(days=body.expires_in_days)) if body.expires_in_days else None)
    db.add(k)
    db.flush()
    security.audit(db, "api_key.created", actor=actor, target=k.name,
                   detail={"prefix": prefix, "portfolios": k.portfolios or "all", "expires_at": str(k.expires_at)},
                   ip=client_ip(request))
    db.commit()
    return {"key": key, "api_key": _key_row(k)}


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(key_id: int, request: Request, db: Session = Depends(get_db),
                   actor: AkashaUser = Depends(require_permission("users.manage"))):
    from models import AkashaApiKey
    k = db.query(AkashaApiKey).filter(AkashaApiKey.id == key_id).first()
    if not k:
        raise HTTPException(status_code=404, detail="Key not found")
    if not k.revoked_at:
        k.revoked_at = datetime.utcnow()
        security.audit(db, "api_key.revoked", actor=actor, target=k.name, detail={"prefix": k.prefix},
                       ip=client_ip(request))
        db.commit()
    return {"api_key": _key_row(k)}
