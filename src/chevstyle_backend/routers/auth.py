from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from chevstyle_backend.auth.clerk import verify_clerk_jwt
from chevstyle_backend.auth.models import (
    AuthMeUpdateRequest,
    AuthSyncRequest,
    AuthSyncResponse,
    AuthUpdateResponse,
    ClerkUser,
)
from chevstyle_backend.convex.client import ConvexClient
from chevstyle_backend.dependencies import get_current_user, require_admin, require_stylist

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me")
async def me(user: ClerkUser = Depends(get_current_user)) -> ClerkUser:
    return user


@router.post("/sync", response_model=AuthSyncResponse)
async def sync_user(
    payload: AuthSyncRequest,
    user: ClerkUser = Depends(get_current_user),
) -> AuthSyncResponse:
    convex = ConvexClient()
    convex_user_id, is_new_user, record = convex.upsert_user(
        clerk_user_id=user.clerk_user_id,
        email=user.email,
        role=payload.role,
        full_name=payload.full_name or user.full_name,
    )
    return AuthSyncResponse(
        convex_user_id=convex_user_id,
        clerk_user_id=user.clerk_user_id,
        email=user.email,
        role=payload.role,
        is_new_user=is_new_user,
        created_at=record["created_at"],
        full_name=record.get("full_name"),
    )


@router.patch("/me", response_model=AuthUpdateResponse)
async def update_me(
    payload: AuthMeUpdateRequest,
    user: ClerkUser = Depends(get_current_user),
) -> AuthUpdateResponse:
    convex = ConvexClient()
    updated, _ = convex.update_user_profile(
        clerk_user_id=user.clerk_user_id,
        full_name=payload.full_name,
        notification_prefs=payload.notification_prefs,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return AuthUpdateResponse(updated=True)


@router.get("/admin-check")
async def admin_check(user: ClerkUser = Depends(require_admin)) -> dict[str, str]:
    return {"status": "ok", "role": user.role}


@router.get("/stylist-check")
async def stylist_check(user: ClerkUser = Depends(require_stylist)) -> dict[str, str]:
    return {"status": "ok", "role": user.role}
