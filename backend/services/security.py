"""Credential and session handling for Akasha sign-in.

- Passwords: salted PBKDF2-HMAC-SHA256 at OWASP's current work factor
  (600,000 iterations). Standard library only - native hashing modules are
  blocked by application control on some managed PCs. Hashes made with fewer
  iterations, or by the original unsalted seed, still verify and are
  re-hashed on the next successful sign-in.
- Sessions: a random 256-bit token in an HttpOnly cookie. Only its SHA-256 is
  stored, so a database read cannot be replayed as a login. Sessions end after
  AKASHA_SESSION_IDLE_HOURS without use, or AKASHA_SESSION_MAX_DAYS after
  sign-in, whichever comes first.
- Lockout: AKASHA_LOCKOUT_ATTEMPTS failed sign-ins lock the account for
  AKASHA_LOCKOUT_MINUTES.
- Every sign-in, failure, lockout and account change is written to
  akasha_audit_log.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

PBKDF2_ROUNDS = 600_000
SESSION_COOKIE = "akasha_session"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


SESSION_IDLE = timedelta(hours=_env_int("AKASHA_SESSION_IDLE_HOURS", 12))
SESSION_MAX = timedelta(days=_env_int("AKASHA_SESSION_MAX_DAYS", 7))
LOCKOUT_ATTEMPTS = _env_int("AKASHA_LOCKOUT_ATTEMPTS", 5)
LOCKOUT_FOR = timedelta(minutes=_env_int("AKASHA_LOCKOUT_MINUTES", 15))
# last_seen is written at most this often, not on every request.
_TOUCH_EVERY = timedelta(minutes=1)

PASSWORD_MIN = 10
PASSWORD_MAX = 128
_COMMON = {"password", "password1", "password123", "123456789", "1234567890", "qwerty123",
           "admin123", "welcome1", "welcome123", "adani123", "akasha123", "letmein123", "iloveyou1"}


# ── Passwords ────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _algo, rounds, salt, digest = stored.split("$")
            got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        except ValueError:
            return False
        return hmac.compare_digest(got, digest)
    # The first seed stored unsalted SHA-256.
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def needs_rehash(stored: str) -> bool:
    if not stored.startswith("pbkdf2_sha256$"):
        return True
    try:
        return int(stored.split("$")[1]) < PBKDF2_ROUNDS
    except (IndexError, ValueError):
        return True


def password_problems(password: str, username: str = "") -> list[str]:
    """Length-based policy (NIST SP 800-63B): long, not common, not the username."""
    problems = []
    if len(password) < PASSWORD_MIN:
        problems.append(f"at least {PASSWORD_MIN} characters")
    if len(password) > PASSWORD_MAX:
        problems.append(f"at most {PASSWORD_MAX} characters")
    if password.lower() in _COMMON:
        problems.append("not a commonly used password")
    if username and username.lower() in password.lower():
        problems.append("must not contain the username")
    if len(set(password)) < 4:
        problems.append("more varied characters")
    return problems


def temporary_password() -> str:
    """A one-time password for a new account or a reset; the user must change it."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


# ── Sessions ─────────────────────────────────────────────────────────────────

def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user_id: int, ip: Optional[str], user_agent: Optional[str]) -> str:
    from models import AkashaSession
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(AkashaSession(token=_digest(token), user_id=user_id, created_at=now, last_seen_at=now,
                         expires_at=now + SESSION_MAX, ip=ip, user_agent=(user_agent or "")[:300]))
    # Housekeeping: drop sessions past their absolute or idle limit.
    db.query(AkashaSession).filter(
        (AkashaSession.expires_at < now) | (AkashaSession.last_seen_at < now - SESSION_IDLE)
    ).delete(synchronize_session=False)
    return token


def resolve_session(db: Session, token: Optional[str]):
    """(user, session) for a live token, else (None, None). Slides the idle window."""
    from models import AkashaSession, AkashaUser
    if not token:
        return None, None
    s = db.query(AkashaSession).filter(AkashaSession.token == _digest(token)).first()
    now = datetime.utcnow()
    if not s or s.expires_at < now or (s.last_seen_at and s.last_seen_at < now - SESSION_IDLE):
        return None, None
    user = db.query(AkashaUser).filter(AkashaUser.id == s.user_id, AkashaUser.is_active == True).first()  # noqa: E712
    if not user:
        return None, None
    if not s.last_seen_at or now - s.last_seen_at > _TOUCH_EVERY:
        s.last_seen_at = now
        db.commit()
    return user, s


def end_session(db: Session, token: Optional[str]) -> None:
    from models import AkashaSession
    if token:
        db.query(AkashaSession).filter(AkashaSession.token == _digest(token)).delete(synchronize_session=False)


def end_all_sessions(db: Session, user_id: int, keep_token: Optional[str] = None) -> int:
    from models import AkashaSession
    q = db.query(AkashaSession).filter(AkashaSession.user_id == user_id)
    if keep_token:
        q = q.filter(AkashaSession.token != _digest(keep_token))
    return q.delete(synchronize_session=False)


# ── Lockout ──────────────────────────────────────────────────────────────────

def is_locked(user) -> bool:
    return bool(user.locked_until and user.locked_until > datetime.utcnow())


def record_failure(user) -> bool:
    """Count a failed sign-in; returns True when this failure locks the account."""
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= LOCKOUT_ATTEMPTS:
        user.locked_until = datetime.utcnow() + LOCKOUT_FOR
        user.failed_login_count = 0
        return True
    return False


def record_success(user) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()


# ── Audit ────────────────────────────────────────────────────────────────────

# How serious each event is. warning / critical entries are security alerts:
# they surface in the admin console (and the account menu badge) until a
# superadmin acknowledges them.
SEVERITY = {
    "login.locked": "critical",          # 5 wrong passwords in a row
    "login.blocked_locked": "critical",  # tried again while locked
    "access.denied": "warning",          # asked for data or an action outside their access
    "api_key.invalid": "warning",        # a system used a wrong / revoked / expired key
    "login.failed": "info",
    "password.change_failed": "warning",
    "user.privileged_change": "warning", # someone was given or lost superadmin / admin rights
    "role.admin_grant": "warning",
}


def audit(db: Session, action: str, actor=None, target: Optional[str] = None,
          detail: Optional[dict] = None, ip: Optional[str] = None, severity: Optional[str] = None,
          actor_username: Optional[str] = None) -> None:
    from models import AkashaAuditLog
    db.add(AkashaAuditLog(at=datetime.utcnow(), actor_id=getattr(actor, "id", None),
                          actor_username=actor_username or getattr(actor, "username", None),
                          action=action, target=target, detail=detail, ip=ip,
                          severity=severity or SEVERITY.get(action, "info")))


FAILED_BURST_WINDOW = timedelta(minutes=15)
FAILED_BURST_COUNT = 10


def flag_failed_login_burst(db: Session, ip: Optional[str]) -> None:
    """Many failed sign-ins from one address across any usernames (password
    guessing that the per-account lockout cannot see): one critical alert per
    address per window."""
    from models import AkashaAuditLog
    if not ip:
        return
    since = datetime.utcnow() - FAILED_BURST_WINDOW
    db.flush()
    recent = db.query(AkashaAuditLog).filter(AkashaAuditLog.ip == ip, AkashaAuditLog.at >= since)
    failures = recent.filter(AkashaAuditLog.action.in_(("login.failed", "login.locked", "login.blocked_locked"))).count()
    if failures >= FAILED_BURST_COUNT and not recent.filter(AkashaAuditLog.action == "login.burst").count():
        users = {t for (t,) in recent.with_entities(AkashaAuditLog.target)
                 .filter(AkashaAuditLog.action.like("login.%")).distinct()}
        audit(db, "login.burst", target=ip, ip=ip, severity="critical",
              detail={"failed_attempts": failures, "minutes": int(FAILED_BURST_WINDOW.total_seconds() // 60),
                      "usernames_tried": len(users)})


# ── API keys (systems, not people) ──────────────────────────────────────────

API_KEY_PREFIX = "ak_"


def new_api_key() -> tuple[str, str, str]:
    """(key shown once, display prefix, stored hash)."""
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, key[:10], _digest(key)


def resolve_api_key(db: Session, key: Optional[str]):
    """The live AkashaApiKey for a presented key, else None. Records the use."""
    from models import AkashaApiKey
    if not key or not key.startswith(API_KEY_PREFIX):
        return None
    k = db.query(AkashaApiKey).filter(AkashaApiKey.key_hash == _digest(key)).first()
    now = datetime.utcnow()
    if not k or k.revoked_at or (k.expires_at and k.expires_at < now):
        return None
    if not k.last_used_at or now - k.last_used_at > _TOUCH_EVERY:
        k.last_used_at = now
        k.use_count = (k.use_count or 0) + 1
        db.commit()
    return k
