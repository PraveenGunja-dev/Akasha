"""Account emails: a new user's sign-in details, and a reset password.

Sent when an administrator creates a user or resets a password (routers/
admin.py). The temporary password is in the email the person receives, and
they must change it at first sign-in. It is never stored: the email log keeps
a copy with the password masked.

Follows the same settings as every Akasha email (EMAIL_ENABLED, test mode,
allowed domains). Never raises: the result says whether it went and, if
not, why - the administrator still sees the password on screen.
"""
import html
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import models
from . import render, sender
from .config import settings

logger = logging.getLogger(__name__)

MASK = "••••••••"
IST_OFFSET_MIN = 330


def _ist_now() -> str:
    return (datetime.utcnow() + timedelta(minutes=IST_OFFSET_MIN)).strftime("%d-%b-%y %H:%M IST")


def _body(user, password: str, kind: str, actor: str, sign_in: str) -> tuple[str, str]:
    """(inner html, plain text) of the message."""
    e = html.escape
    name = user.display_name or user.username
    if kind == "created":
        lead = f"An Akasha account has been created for you by {actor}. Sign in with these details:"
    else:
        lead = f"Your Akasha password has been reset by {actor}. Sign in with this temporary password:"
    rows = [("Username", user.username), ("Temporary password", password)]
    cell = render.FONT + "padding:9px 14px;border-bottom:1px solid #e7eaee;font-size:14px;"
    table = ('<table role="presentation" cellspacing="0" cellpadding="0" style="margin:14px 0 16px;border:1px solid #e7eaee;'
             'border-radius:8px;background:#f7f8fa;">'
             + "".join(
                 f'<tr><td style="{cell}color:#5b6472;width:170px;">{e(k)}</td>'
                 f'<td style="{cell}font-family:Consolas,\'Courier New\',monospace;font-weight:700;color:#111827;'
                 f'letter-spacing:.5px;">{e(v)}</td></tr>' for k, v in rows)
             + "</table>")
    steps = [
        "You will be asked to set your own password when you first sign in.",
        "The temporary password stops working once you set your own. Do not share it or forward this email.",
        "If you did not expect this, tell your Akasha administrator.",
    ]
    inner = (f'<p style="margin:0 0 4px;">Dear {e(name)},</p>'
             f'<p style="margin:10px 0 0;line-height:1.55;">{e(lead)}</p>{table}'
             + "".join(f'<p style="margin:0 0 6px;line-height:1.5;color:#374151;">&bull;&nbsp; {e(s)}</p>' for s in steps)
             + (f'<p style="margin:12px 0 0;line-height:1.5;color:#5b6472;">Sign in at '
                f'<a href="{e(sign_in)}" style="color:{render.BRAND};">{e(sign_in)}</a></p>' if sign_in else ""))
    text = (f"Dear {name},\n\n{lead}\n\n  Username: {user.username}\n  Temporary password: {password}\n\n"
            + "\n".join(f"- {s}" for s in steps)
            + (f"\n\nSign in at {sign_in}" if sign_in else "")
            + "\n\n--\nAutomated message from Akasha. Replies to this address are not monitored.")
    return inner, text


def send_credentials(db: Session, user, password: str, kind: str, actor: str) -> dict:
    """Email `user` their temporary password. kind: "created" | "reset".
    Returns {"status": sent|test|failed|off|no_email|not_allowed, "to": [...], "detail": str}."""
    cfg = settings()
    if not cfg.enabled:
        return {"status": "off", "to": [], "detail": "Email sending is off (EMAIL_ENABLED=false) - give the password to the person yourself"}
    address = (user.email or "").strip()
    if not address:
        return {"status": "no_email", "to": [], "detail": "This user has no email address - give the password to them yourself"}
    to, dropped = sender.allowed([address], cfg.allowed_domains)
    if dropped:
        return {"status": "not_allowed", "to": [], "detail": f"{address} is outside the allowed domains ({', '.join(cfg.allowed_domains)})"}

    banner = ""
    if cfg.test_mode:
        banner = f"TEST MODE - would have gone to: {address}"
        to = sender.allowed(cfg.test_recipients, cfg.allowed_domains)[0]
        if not to:
            return {"status": "failed", "to": [], "detail": "EMAIL_TEST_RECIPIENTS is empty"}

    base = (cfg.public_url or "").rstrip("/")
    sign_in = f"{base}/login" if base else ""
    subj = ("Akasha Account | Your account is ready" if kind == "created"
            else "Akasha Account | Your password has been reset")
    if cfg.test_mode:
        subj = f"[TEST] {subj}"
    inner, text = _body(user, password, kind, actor, sign_in)
    ctx = {"akasha_link": base, "support_contact": cfg.support_contact, "generated_at": _ist_now()}
    page = render.layout(inner, "info", ctx, banner, None, subj,
                         [("Sign in to Akasha", sign_in)] if sign_in else None, data_note=False)

    status, detail = ("test" if cfg.test_mode else "sent"), None
    try:
        sender.send(cfg, to, [], subj, page, text, tag=f"account_{kind}")
    except sender.SendError as ex:
        status, detail = "failed", str(ex)
    try:
        db.add(models.EmailLog(
            template_key=f"account_{kind}", event_key=f"account:{user.id}:{kind}:{datetime.utcnow():%Y%m%d%H%M%S}",
            severity="info", to_addrs=[address], cc_addrs=[], subject=subj,
            body_html=page.replace(html.escape(password), MASK).replace(password, MASK),
            status=status, detail=detail, attempts=1, triggered_by=actor, created_at=datetime.utcnow()))
        db.commit()
    except Exception as ex:  # noqa: BLE001 - the log must not undo the account change
        db.rollback()
        logger.warning(f"Account email log failed: {ex}")
    return {"status": status, "to": to if cfg.test_mode else [address], "detail": detail}
