from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import AkashaUser
import hashlib
import os
import secrets

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
_SESSION_TOKENS: dict[str, int] = {}


def hash_password(password: str) -> str:
    """Simple SHA-256 hash for passwords."""
    return hashlib.sha256(password.encode()).hexdigest()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: str | None = None
    user: dict | None = None
    message: str = ""


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(AkashaUser).filter(
        AkashaUser.username == req.username,
        AkashaUser.is_active == True
    ).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if user.password_hash != hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Generate a simple session token
    token = secrets.token_hex(32)
    _SESSION_TOKENS[token] = user.id

    return LoginResponse(
        success=True,
        token=token,
        user={
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "email": user.email or "",
        },
        message=f"Welcome back, {user.display_name}!"
    )


@router.get("/me_legacy")
def get_current_user_legacy():
    """Placeholder — in production, validate the token from headers."""
    return {"detail": "Use token-based auth in production"}


def get_current_user_optional(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AkashaUser | None:
    """Validate a Bearer token when supplied."""
    require_auth = os.getenv("AKASHA_REQUIRE_CHAT_AUTH", "false").lower() == "true"
    if not authorization:
        if require_auth:
            raise HTTPException(status_code=401, detail="Authentication required")
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    user_id = _SESSION_TOKENS.get(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(AkashaUser).filter(AkashaUser.id == user_id, AkashaUser.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return user


@router.get("/me")
def get_current_user(user: AkashaUser | None = Depends(get_current_user_optional)):
    if not user:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "email": user.email or "",
        },
    }


@router.post("/seed")
def seed_users(db: Session = Depends(get_db)):
    """Seed default users for each role. Idempotent — skips existing users."""
    default_users = [
        {"username": "praveen", "password": "akasha@2026", "display_name": "Praveen Gunja", "role": "executive", "email": "praveen@akasha.io"},
        {"username": "pmag_lead", "password": "akasha@2026", "display_name": "Rajesh Kumar", "role": "pmag", "email": "rajesh@akasha.io"},
        {"username": "site_lead", "password": "akasha@2026", "display_name": "Amit Sharma", "role": "projects", "email": "amit@akasha.io"},
        {"username": "tc_ordering", "password": "akasha@2026", "display_name": "Priya Mehta", "role": "tc_ordering", "email": "priya@akasha.io"},
        {"username": "tc_stores", "password": "akasha@2026", "display_name": "Vikram Singh", "role": "tc_stores", "email": "vikram@akasha.io"},
    ]

    created = []
    skipped = []

    for u in default_users:
        existing = db.query(AkashaUser).filter(AkashaUser.username == u["username"]).first()
        if existing:
            skipped.append(u["username"])
            continue

        new_user = AkashaUser(
            username=u["username"],
            password_hash=hash_password(u["password"]),
            display_name=u["display_name"],
            role=u["role"],
            email=u["email"],
        )
        db.add(new_user)
        created.append(u["username"])

    db.commit()
    return {"created": created, "skipped": skipped}
