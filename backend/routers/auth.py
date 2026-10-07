"""Sign-in for the Akasha web app: email + password, a server-side session
token the browser keeps, /me to confirm it and /logout to end it.

Passwords are stored as salted PBKDF2-SHA256. Accounts made by the earlier
seed (plain SHA-256) still verify and are upgraded on their next sign-in.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import AkashaSession, AkashaUser

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

SESSION_DAYS = 7
PBKDF2_ROUNDS = 200_000

# The account the platform is used with for now (user, 2026-10-07). Created on
# start-up if missing; its password is only set when the account is created,
# so a later change is never overwritten.
DEFAULT_USERS = [
    {"username": "akashaceo", "email": "Akashaceo@adani.com", "password": "admin123",
     "display_name": "Akasha CEO", "role": "executive"},
]


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2_sha256$"):
        _algo, rounds, salt, digest = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(got, digest)
    # Legacy unsalted SHA-256 from the first seed.
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def _public(user: AkashaUser) -> dict:
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "role": user.role, "email": user.email or ""}


def ensure_default_users() -> None:
    """Create DEFAULT_USERS that do not exist yet. Called once at start-up."""
    db = SessionLocal()
    try:
        for u in DEFAULT_USERS:
            exists = db.query(AkashaUser).filter(
                (func.lower(AkashaUser.email) == u["email"].lower()) | (AkashaUser.username == u["username"])
            ).first()
            if not exists:
                db.add(AkashaUser(username=u["username"], email=u["email"],
                                  password_hash=hash_password(u["password"]),
                                  display_name=u["display_name"], role=u["role"]))
        db.commit()
    finally:
        db.close()


class LoginRequest(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None      # older clients
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user: Optional[dict] = None
    message: str = ""


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    ident = (req.email or req.username or "").strip()
    if not ident or not req.password:
        raise HTTPException(status_code=400, detail="Enter your email and password")
    user = db.query(AkashaUser).filter(
        AkashaUser.is_active == True,  # noqa: E712
        (func.lower(AkashaUser.email) == ident.lower()) | (AkashaUser.username == ident),
    ).first()
    # One message for a wrong email or a wrong password: no hint which it was.
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.password_hash.startswith("pbkdf2_sha256$"):
        user.password_hash = hash_password(req.password)

    token = secrets.token_urlsafe(32)
    db.add(AkashaSession(token=token, user_id=user.id,
                         expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS)))
    db.query(AkashaSession).filter(AkashaSession.expires_at < datetime.utcnow()).delete()
    db.commit()
    return LoginResponse(success=True, token=token, user=_public(user),
                         message=f"Welcome back, {user.display_name}")


def _session_user(authorization: Optional[str], db: Session) -> AkashaUser:
    token = (authorization or "").removeprefix("Bearer ").strip()
    s = db.query(AkashaSession).filter(AkashaSession.token == token).first() if token else None
    if not s or s.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired - please sign in again")
    user = db.query(AkashaUser).filter(AkashaUser.id == s.user_id, AkashaUser.is_active == True).first()  # noqa: E712
    if not user:
        raise HTTPException(status_code=401, detail="Account not active")
    return user


@router.get("/me")
def me(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """The signed-in user for a bearer token; 401 if the session is gone."""
    return {"user": _public(_session_user(authorization, db))}


@router.post("/logout")
def logout(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token:
        db.query(AkashaSession).filter(AkashaSession.token == token).delete()
        db.commit()
    return {"success": True}
