"""Microsoft Entra bearer-token validation for Akasha APIs."""

from dataclasses import dataclass
from functools import lru_cache
import os
import re

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from auth_claims import AuthenticatedIdentity, ClaimsValidationError, identity_from_claims


@dataclass(frozen=True)
class EntraSettings:
    tenant_id: str
    audience: str
    authority_host: str
    ceo_app_role: str
    pmag_app_role: str
    ceo_group_id: str | None
    pmag_group_id: str | None

    @property
    def issuer(self) -> str:
        return f"{self.authority_host}/{self.tenant_id}/v2.0"

    @property
    def jwks_url(self) -> str:
        return f"{self.authority_host}/{self.tenant_id}/discovery/v2.0/keys"


@lru_cache(maxsize=1)
def get_entra_settings() -> EntraSettings:
    tenant_id = os.getenv("ENTRA_TENANT_ID", "").strip()
    audience = os.getenv("ENTRA_AUDIENCE", os.getenv("ENTRA_CLIENT_ID", "")).strip()
    if not tenant_id or not audience:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Microsoft Entra authentication is not configured.",
        )
    return EntraSettings(
        tenant_id=tenant_id,
        audience=audience,
        authority_host=os.getenv(
            "ENTRA_AUTHORITY_HOST", "https://login.microsoftonline.com"
        ).rstrip("/"),
        ceo_app_role=os.getenv("ENTRA_CEO_APP_ROLE", "Akasha.CEO").strip(),
        pmag_app_role=os.getenv("ENTRA_PMAG_APP_ROLE", "Akasha.PMAG").strip(),
        ceo_group_id=os.getenv("ENTRA_CEO_GROUP_ID") or None,
        pmag_group_id=os.getenv("ENTRA_PMAG_GROUP_ID") or None,
    )


@lru_cache(maxsize=1)
def get_auth_mode() -> str:
    mode = os.getenv("AKASHA_AUTH_MODE", "development").strip().lower()
    if mode not in {"development", "entra"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AKASHA_AUTH_MODE must be development or entra.",
        )
    return mode


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    development_user: str | None = Header(default=None, alias="X-Akasha-Dev-User"),
    development_role: str | None = Header(default=None, alias="X-Akasha-Dev-Role"),
) -> AuthenticatedIdentity:
    if get_auth_mode() == "development":
        user_id = development_user if isinstance(development_user, str) else ""
        role = development_role if isinstance(development_role, str) else ""
        if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", user_id) or role not in {"executive", "pmag"}:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Select a development CEO or PMAG identity to continue.",
            )
        label = "CEO" if role == "executive" else "PMAG"
        return AuthenticatedIdentity(
            subject=f"dev:{user_id}",
            tenant_id="development",
            username=f"{role}-{user_id[:8]}@akasha.local",
            display_name=f"Development {label}",
            email="",
            role=role,
        )

    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A Microsoft Entra bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_entra_settings()
    try:
        signing_key = _jwks_client(settings.jwks_url).get_signing_key_from_jwt(
            credentials.credentials
        )
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.audience,
            issuer=settings.issuer,
            options={"require": ["exp", "iss", "aud", "tid"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The Microsoft Entra access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return identity_from_claims(
            claims,
            tenant_id=settings.tenant_id,
            ceo_app_role=settings.ceo_app_role,
            pmag_app_role=settings.pmag_app_role,
            ceo_group_id=settings.ceo_group_id,
            pmag_group_id=settings.pmag_group_id,
        )
    except ClaimsValidationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


def require_roles(*allowed_roles: str):
    allowed = frozenset(allowed_roles)

    def dependency(
        user: AuthenticatedIdentity = Depends(get_current_user),
    ) -> AuthenticatedIdentity:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The authenticated user does not have access to this Akasha area.",
            )
        return user

    return dependency


require_ceo_or_pmag = require_roles("executive", "pmag")
