from fastapi import APIRouter, Depends, HTTPException, status

from auth_claims import AuthenticatedIdentity
from security import get_current_user


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.get("/me")
def read_current_user(
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    return {
        "id": user.subject,
        "tenant_id": user.tenant_id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "email": user.email,
    }


@router.post("/login")
def local_login_removed():
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Local password login has been replaced by Microsoft Entra ID.",
    )


@router.post("/seed")
def local_seed_removed():
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Local user seeding is disabled. Assign users through Microsoft Entra ID.",
    )
