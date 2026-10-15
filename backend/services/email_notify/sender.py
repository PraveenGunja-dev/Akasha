"""SMTP delivery. The From address and name come from settings (EMAIL_FROM /
EMAIL_FROM_NAME); the server account (SMTP_USERNAME) may be a different
mailbox, which the mail server must allow to send as EMAIL_FROM.

Every message is marked machine-generated (RFC 3834 Auto-Submitted, and the
Exchange header that suppresses out-of-office replies), so nobody's
auto-reply loops back to a mailbox no one reads.
"""
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Iterable, List, Optional, Tuple

from .config import EmailSettings


class SendError(RuntimeError):
    pass


def allowed(addresses: Iterable[str], domains: List[str]) -> Tuple[List[str], List[str]]:
    """(kept, dropped): only addresses in the allowed domains leave Akasha."""
    keep, drop = [], []
    for a in addresses:
        a = (a or "").strip()
        if not a:
            continue
        dom = a.rsplit("@", 1)[-1].lower() if "@" in a else ""
        (keep if not domains or dom in domains else drop).append(a)
    # de-duplicate, keep order
    seen = set()
    keep = [a for a in keep if not (a.lower() in seen or seen.add(a.lower()))]
    return keep, drop


def send(cfg: EmailSettings, to: List[str], cc: List[str], subject: str, html: str, text: str,
         attachments: Optional[List[Tuple[str, bytes, str]]] = None, tag: str = "") -> str:
    """Send one message; returns its Message-ID. Raises SendError."""
    if not cfg.configured:
        raise SendError("; ".join(cfg.problems()) or "Email is not configured")
    if not to:
        raise SendError("No recipients")
    msg = EmailMessage()
    msg["From"] = formataddr((cfg.from_name, cfg.from_addr))
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    domain = cfg.from_addr.split("@")[-1] or "akasha.local"
    msg_id = make_msgid(idstring=uuid.uuid4().hex[:12], domain=domain)
    msg["Message-ID"] = msg_id
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"
    if tag:
        msg["X-Akasha-Template"] = tag
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    # The banner travels inside the email (render.BANNER_CID) so it is shown
    # without the reader having to allow downloaded pictures.
    from . import render
    if f"cid:{render.BANNER_CID}" in html:
        html_part = msg.get_payload()[1]
        html_part.add_related(render.banner_bytes(), maintype="image", subtype="jpeg",
                              cid=f"<{render.BANNER_CID}>", filename="adani-banner.jpg", disposition="inline")
    for name, data, mime in attachments or []:
        main, _, sub = mime.partition("/")
        msg.add_attachment(data, maintype=main, subtype=sub or "octet-stream", filename=name)

    try:
        with smtplib.SMTP(cfg.server, cfg.port, timeout=30) as s:
            s.ehlo()
            wants_tls = cfg.starttls == "true" or (cfg.starttls == "auto" and s.has_extn("starttls"))
            if wants_tls:
                ctx = ssl.create_default_context()
                s.starttls(context=ctx)
                s.ehlo()
            if cfg.username and cfg.password:
                s.login(cfg.username, cfg.password)
            refused = s.send_message(msg, from_addr=cfg.from_addr, to_addrs=list(to) + list(cc))
        if refused and len(refused) == len(to) + len(cc):
            raise SendError(f"Server refused every recipient: {refused}")
    except SendError:
        raise
    except (smtplib.SMTPException, OSError) as e:
        raise SendError(f"{type(e).__name__}: {e}") from e
    return msg_id
