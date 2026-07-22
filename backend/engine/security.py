"""Authorization helpers for the Akasha chatbot runtime."""

from __future__ import annotations

import os
from typing import Any

from engine.contracts import UserScope


EXECUTIVE_ROLES = {"admin", "ceo", "executive"}
PORTFOLIO_ROLES = EXECUTIVE_ROLES | {"pmag"}
DEFAULT_ROLE_DOMAINS = {
    "admin": ["*"],
    "ceo": ["*"],
    "executive": ["*"],
    "pmag": ["p6", "sap", "tc"],
    "projects": ["p6", "sap"],
    "tc_ordering": ["tc"],
    "tc_stores": ["sap", "tc"],
}


def build_user_scope(user: Any | None) -> UserScope:
    """Build trusted chatbot scope from the authenticated user and env policy.

    Project assignments are not modeled in the database yet, so restricted
    project lists are read from environment variables until a durable ACL table
    exists.
    """
    if user is None:
        return UserScope(
            role="anonymous",
            project_ids=["*"],
            domains=["*"],
            can_access_portfolio=True,
            is_authenticated=False,
        )

    role = (getattr(user, "role", None) or "anonymous").strip().lower()
    username = getattr(user, "username", None)
    user_id = getattr(user, "id", None)

    projects = (
        _env_list(f"AKASHA_CHAT_ALLOWED_PROJECTS_USER_{username}")
        or _env_list(f"AKASHA_CHAT_ALLOWED_PROJECTS_ROLE_{role}")
        or (["*"] if role in PORTFOLIO_ROLES else [])
    )
    domains = (
        _env_list(f"AKASHA_CHAT_ALLOWED_DOMAINS_USER_{username}")
        or _env_list(f"AKASHA_CHAT_ALLOWED_DOMAINS_ROLE_{role}")
        or DEFAULT_ROLE_DOMAINS.get(role, ["p6"])
    )

    return UserScope(
        user_id=str(user_id) if user_id is not None else None,
        username=username,
        role=role,
        project_ids=_normalize_list(projects),
        domains=_normalize_list(domains),
        can_access_portfolio=_env_bool(
            f"AKASHA_CHAT_CAN_ACCESS_PORTFOLIO_USER_{username}",
            _env_bool(
                f"AKASHA_CHAT_CAN_ACCESS_PORTFOLIO_ROLE_{role}",
                role in PORTFOLIO_ROLES or "*" in projects,
            ),
        ),
        is_authenticated=True,
    )


def public_dev_scope() -> UserScope:
    return build_user_scope(None)


def scope_allows_project(scope: UserScope | None, project_id: str | None) -> bool:
    scope = scope or public_dev_scope()
    if not project_id:
        return True
    allowed = _normalize_list(scope.project_ids)
    return "*" in allowed or project_id.strip().lower() in allowed


def scope_allows_domain(scope: UserScope | None, domain: str | None) -> bool:
    scope = scope or public_dev_scope()
    if not domain:
        return True
    allowed = _normalize_list(scope.domains)
    return "*" in allowed or domain.strip().lower() in allowed


def scope_allows_portfolio(scope: UserScope | None) -> bool:
    scope = scope or public_dev_scope()
    return scope.can_access_portfolio or "*" in _normalize_list(scope.project_ids)


def denied_projects(scope: UserScope | None, project_ids: list[str]) -> list[str]:
    return [pid for pid in project_ids if not scope_allows_project(scope, pid)]


def denied_domains(scope: UserScope | None, domains: list[str]) -> list[str]:
    return [domain for domain in domains if not scope_allows_domain(scope, domain)]


def unauthorized_tool_envelope(
    tool_name: str,
    *,
    reason: str,
    project_id: str | None = None,
) -> dict:
    return {
        "status": "unauthorized",
        "data": None,
        "evidence": [],
        "warnings": [reason],
        "error": f"Unauthorized tool call blocked: {tool_name}",
        "project_id": project_id,
    }


def _env_list(name: str) -> list[str]:
    value = os.environ.get(name)
    if not value:
        return []
    return _normalize_list(value.split(","))


def _normalize_list(values: list[str]) -> list[str]:
    return [str(value).strip().lower() for value in values if str(value).strip()]


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
