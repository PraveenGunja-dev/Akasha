"""Pure Microsoft Entra claim validation and Akasha role mapping."""

from dataclasses import dataclass
from typing import Any


class ClaimsValidationError(ValueError):
    """Raised when a valid token does not identify an authorized Akasha user."""


@dataclass(frozen=True)
class AuthenticatedIdentity:
    subject: str
    tenant_id: str
    username: str
    display_name: str
    email: str
    role: str


def _claim_strings(claims: dict[str, Any], name: str) -> set[str]:
    value = claims.get(name, [])
    if isinstance(value, str):
        return {value}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return set(value)
    return set()


def identity_from_claims(
    claims: dict[str, Any],
    *,
    tenant_id: str,
    ceo_app_role: str,
    pmag_app_role: str,
    ceo_group_id: str | None = None,
    pmag_group_id: str | None = None,
) -> AuthenticatedIdentity:
    """Map verified Entra claims to the two roles currently supported by Akasha."""
    token_tenant = str(claims.get("tid") or "").strip()
    subject = str(claims.get("oid") or "").strip()
    if token_tenant.casefold() != tenant_id.casefold():
        raise ClaimsValidationError("The token tenant is not authorized for Akasha.")
    if not subject:
        raise ClaimsValidationError("The token does not contain a user object identifier.")
    roles = {role.casefold() for role in _claim_strings(claims, "roles")}
    role_is_ceo = ceo_app_role.casefold() in roles
    role_is_pmag = pmag_app_role.casefold() in roles
    claim_names = claims.get("_claim_names")
    has_group_overage = isinstance(claim_names, dict) and "groups" in claim_names
    if not role_is_ceo and not role_is_pmag and has_group_overage and not isinstance(claims.get("groups"), list):
        raise ClaimsValidationError("The token contains an overage group claim that Akasha cannot authorize.")

    groups = {group.casefold() for group in _claim_strings(claims, "groups")}
    is_ceo = role_is_ceo or bool(
        ceo_group_id and ceo_group_id.casefold() in groups
    )
    is_pmag = role_is_pmag or bool(
        pmag_group_id and pmag_group_id.casefold() in groups
    )
    if not is_ceo and not is_pmag:
        raise ClaimsValidationError("The user is not assigned an Akasha CEO or PMAG role.")

    email = str(
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("upn")
        or ""
    ).strip()
    username = email or subject
    display_name = str(claims.get("name") or username).strip()
    return AuthenticatedIdentity(
        subject=subject,
        tenant_id=token_tenant,
        username=username,
        display_name=display_name,
        email=email,
        role="executive" if is_ceo else "pmag",
    )
