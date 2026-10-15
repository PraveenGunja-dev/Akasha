"""Email settings - all from backend/.env, nothing in code.

    SMTP_SERVER            smtp.adani.com
    SMTP_PORT              25
    SMTP_USERNAME          the account the server signs in with (may be empty
                           when the server relays for the VM's address)
    SMTP_PASSWORD
    SMTP_STARTTLS          auto (default) / true / false
    EMAIL_FROM             akasha@adani.com - the From address people see
    EMAIL_FROM_NAME        Akasha Intelligence
    EMAIL_ENABLED          false (default) - nothing is sent until this is true
    EMAIL_TEST_MODE        true (default) - every email goes ONLY to
                           EMAIL_TEST_RECIPIENTS, subject marked [TEST]
    EMAIL_TEST_RECIPIENTS  comma list
    EMAIL_ALLOWED_DOMAINS  adani.com (comma list) - no mail leaves for other domains
    AKASHA_PUBLIC_URL      https://<host>/akasha - for "View in Akasha" links
    EMAIL_SUPPORT_CONTACT  who to ask, shown in the no-reply footer

Read on every use, so a change to .env takes effect after a restart and the
admin screen always shows what is really in force.
"""
import os
from dataclasses import dataclass, field
from typing import List


def _flag(name: str, default: bool) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def _list(name: str, default: str = "") -> List[str]:
    return [x.strip() for x in (os.getenv(name) or default).split(",") if x.strip()]


@dataclass
class EmailSettings:
    server: str = ""
    port: int = 25
    username: str = ""
    password: str = ""
    starttls: str = "auto"
    from_addr: str = ""
    from_name: str = "Akasha Intelligence"
    enabled: bool = False
    test_mode: bool = True
    test_recipients: List[str] = field(default_factory=list)
    allowed_domains: List[str] = field(default_factory=list)
    public_url: str = ""
    support_contact: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.server and self.from_addr)

    def problems(self) -> List[str]:
        """What stops sending, in words."""
        out = []
        if not self.server:
            out.append("SMTP_SERVER is not set")
        if not self.from_addr:
            out.append("EMAIL_FROM is not set")
        if self.test_mode and not self.test_recipients:
            out.append("EMAIL_TEST_MODE is on but EMAIL_TEST_RECIPIENTS is empty")
        if not self.public_url:
            out.append("AKASHA_PUBLIC_URL is not set - emails will have no 'View in Akasha' link")
        return out

    def public(self) -> dict:
        """For the admin screen: everything except the password."""
        return {
            "server": self.server, "port": self.port, "username": self.username,
            "password_set": bool(self.password), "starttls": self.starttls,
            "from_addr": self.from_addr, "from_name": self.from_name,
            "enabled": self.enabled, "test_mode": self.test_mode,
            "test_recipients": self.test_recipients, "allowed_domains": self.allowed_domains,
            "public_url": self.public_url, "support_contact": self.support_contact,
            "configured": self.configured, "problems": self.problems(),
        }


def settings() -> EmailSettings:
    try:
        port = int(os.getenv("SMTP_PORT") or 25)
    except ValueError:
        port = 25
    return EmailSettings(
        server=(os.getenv("SMTP_SERVER") or "").strip(),
        port=port,
        username=(os.getenv("SMTP_USERNAME") or "").strip(),
        password=os.getenv("SMTP_PASSWORD") or "",
        starttls=(os.getenv("SMTP_STARTTLS") or "auto").strip().lower(),
        from_addr=(os.getenv("EMAIL_FROM") or "").strip(),
        from_name=(os.getenv("EMAIL_FROM_NAME") or "Akasha Intelligence").strip(),
        enabled=_flag("EMAIL_ENABLED", False),
        test_mode=_flag("EMAIL_TEST_MODE", True),
        test_recipients=_list("EMAIL_TEST_RECIPIENTS"),
        allowed_domains=[d.lower().lstrip("@") for d in _list("EMAIL_ALLOWED_DOMAINS", "adani.com")],
        public_url=(os.getenv("AKASHA_PUBLIC_URL") or "").strip().rstrip("/"),
        support_contact=(os.getenv("EMAIL_SUPPORT_CONTACT") or "").strip(),
    )
