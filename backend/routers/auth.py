"""Sign-in for the Akasha web app.

Username (or email) + password -> a server-side session held in an HttpOnly,
SameSite=Lax cookie. /me returns the user with the role's permissions and the
dashboards they open; /password changes the password; /logout ends the
session. No account or password lives in code: the first superadmin is created
with `scripts/create_superadmin.py` (or AKASHA_BOOTSTRAP_SUPERADMIN_* on first
start) and every other account from the admin console.

See services/security.py for hashing, sessions and lockout, and
services/access.py for roles and permissions.
"""
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import AkashaRole, AkashaUser
from services import access, security

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

GENERIC_FAILURE = "Incorrect username or password"


# ── Request context helpers ──────────────────────────────────────────────────

def client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def request_token(request: Request) -> Optional[str]:
    """The session token: the cookie, or a Bearer header for API tools."""
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(security.SESSION_COOKIE)


def _cookie_secure(request: Request) -> bool:
    mode = (os.getenv("AKASHA_COOKIE_SECURE") or "auto").lower()
    if mode in ("1", "true", "yes"):
        return True
    if mode in ("0", "false", "no"):
        return False
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto == "https"


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(security.SESSION_COOKIE, token, httponly=True, samesite="lax",
                        secure=_cookie_secure(request), path="/",
                        max_age=int(security.SESSION_MAX.total_seconds()))


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(security.SESSION_COOKIE, path="/")


def public_user(db: Session, user: AkashaUser) -> dict:
    perms = access.role_permissions(db, user.role)
    role = db.query(AkashaRole).filter(AkashaRole.key == user.role).first()
    return {
        "id": user.id, "username": user.username, "display_name": user.display_name,
        "email": user.email or "", "role": user.role, "role_name": role.name if role else user.role,
        "department": user.department or "",
        "permissions": sorted(perms), "dashboards": access.dashboards_for(perms),
        "portfolio_access": access.portfolio_access(db, user),
        "must_change_password": bool(user.must_change_password),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


# ── Dependencies for routers ─────────────────────────────────────────────────

def current_user(request: Request, db: Session = Depends(get_db)) -> AkashaUser:
    user, _ = security.resolve_session(db, request_token(request))
    if not user:
        raise HTTPException(status_code=401, detail="Your session has ended - please sign in again")
    return user


def require_permission(*perms: str):
    """Allow the call when the user holds ANY of `perms`."""
    def dep(user: AkashaUser = Depends(current_user), db: Session = Depends(get_db)) -> AkashaUser:
        held = access.role_permissions(db, user.role)
        if not any(p in held for p in perms):
            raise HTTPException(status_code=403, detail="You do not have access to this")
        return user
    return dep


# ── Start-up ─────────────────────────────────────────────────────────────────

def bootstrap() -> None:
    """Seed the default roles, and create the first superadmin from the
    environment when AKASHA_BOOTSTRAP_SUPERADMIN_USERNAME / _PASSWORD are set
    and that account does not exist. The password must be changed at first
    sign-in. Never touches an existing account."""
    db = SessionLocal()
    try:
        access.seed_roles(db)
        # One-time: accounts that predate this sign-in system had their
        # passwords written in source code (now in git history). Each must
        # choose a new one. must_change_password is NULL only on those rows -
        # the column arrived empty - so this runs once per account.
        legacy = db.query(AkashaUser).filter(AkashaUser.must_change_password.is_(None)).all()
        for u in legacy:
            u.must_change_password = True
            security.end_all_sessions(db, u.id)
            security.audit(db, "user.password_expired", target=u.username,
                           detail={"reason": "password predates the managed sign-in"})
        if legacy:
            db.commit()
            logger.info(f"{len(legacy)} pre-existing account(s) must set a new password at next sign-in")
        username = (os.getenv("AKASHA_BOOTSTRAP_SUPERADMIN_USERNAME") or "").strip()
        password = os.getenv("AKASHA_BOOTSTRAP_SUPERADMIN_PASSWORD") or ""
        if username and password:
            exists = db.query(AkashaUser).filter(func.lower(AkashaUser.username) == username.lower()).first()
            if not exists:
                problems = security.password_problems(password, username)
                if problems:
                    logger.warning(f"Bootstrap superadmin not created - password needs: {', '.join(problems)}")
                else:
                    u = AkashaUser(username=username, display_name="Super Admin", role=access.SUPERADMIN,
                                   password_hash=security.hash_password(password), is_active=True,
                                   must_change_password=True, created_at=datetime.utcnow())
                    db.add(u)
                    db.flush()
                    security.audit(db, "user.bootstrap", target=username, detail={"role": access.SUPERADMIN})
                    db.commit()
                    logger.info(f"Bootstrap superadmin '{username}' created; password change required at first sign-in")
        if not db.query(AkashaUser).filter(AkashaUser.role == access.SUPERADMIN,
                                           AkashaUser.is_active == True).count():  # noqa: E712
            logger.warning("No active superadmin. Create one: cd backend && python scripts/create_superadmin.py")
    finally:
        db.close()


# ── Endpoints ────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: str


@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ident = (req.username or req.email or "").strip()
    if not ident or not req.password:
        raise HTTPException(status_code=400, detail="Enter your username and password")
    ip = client_ip(request)
    user = db.query(AkashaUser).filter(
        (func.lower(AkashaUser.username) == ident.lower()) | (func.lower(AkashaUser.email) == ident.lower())
    ).first()

    if user and security.is_locked(user):
        security.audit(db, "login.blocked_locked", target=user.username, ip=ip)
        db.commit()
        mins = max(1, int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1)
        raise HTTPException(status_code=423, detail=f"Too many failed attempts. Try again in {mins} minute{'s' if mins > 1 else ''}, or ask an administrator to unlock the account.")

    if not user or not user.is_active or not security.verify_password(req.password, user.password_hash):
        locked = False
        if user and user.is_active:
            locked = security.record_failure(user)
        security.audit(db, "login.locked" if locked else "login.failed",
                       target=user.username if user else ident[:80], ip=ip)
        security.flag_failed_login_burst(db, ip)
        db.commit()
        # Same message whether the account exists or not.
        raise HTTPException(status_code=401, detail=GENERIC_FAILURE)

    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(req.password)
    security.record_success(user)
    token = security.create_session(db, user.id, ip, request.headers.get("user-agent"))
    security.audit(db, "login.success", actor=user, target=user.username, ip=ip)
    db.commit()
    _set_cookie(response, request, token)
    return {"success": True, "user": public_user(db, user),
            "message": f"Welcome back, {user.display_name}"}


@router.get("/me")
def me(user: AkashaUser = Depends(current_user), db: Session = Depends(get_db)):
    return {"user": public_user(db, user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request_token(request)
    user, _ = security.resolve_session(db, token)
    security.end_session(db, token)
    if user:
        security.audit(db, "logout", actor=user, target=user.username, ip=client_ip(request))
    db.commit()
    _clear_cookie(response)
    return {"success": True}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/password")
def change_password(body: PasswordChange, request: Request,
                    user: AkashaUser = Depends(current_user), db: Session = Depends(get_db)):
    if not security.verify_password(body.current_password, user.password_hash):
        security.audit(db, "password.change_failed", actor=user, target=user.username, ip=client_ip(request))
        db.commit()
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="Choose a password different from the current one")
    problems = security.password_problems(body.new_password, user.username)
    if problems:
        raise HTTPException(status_code=400, detail="Password needs: " + "; ".join(problems))
    user.password_hash = security.hash_password(body.new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.utcnow()
    # Sign out every other device; this one stays signed in.
    ended = security.end_all_sessions(db, user.id, keep_token=request_token(request))
    security.audit(db, "password.changed", actor=user, target=user.username,
                   detail={"other_sessions_ended": ended}, ip=client_ip(request))
    db.commit()
    return {"success": True, "user": public_user(db, user)}
