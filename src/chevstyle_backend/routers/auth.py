import logging
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

logger = logging.getLogger("chevstyle_backend.routers.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me")
async def me(user: ClerkUser = Depends(get_current_user)) -> ClerkUser:
    return user


@router.post("/sync", response_model=AuthSyncResponse)
async def sync_user(
    payload: AuthSyncRequest,
    user: ClerkUser = Depends(get_current_user),
) -> AuthSyncResponse:
    logger.info(f"Initiating sync for clerk_user_id='{user.clerk_user_id}' with role='{payload.role}'")
    try:
        convex = ConvexClient()
        convex_user_id, is_new_user, record = convex.upsert_user(
            clerk_user_id=user.clerk_user_id,
            email=user.email,
            role=payload.role,
            full_name=payload.full_name or user.full_name,
            gender=payload.gender,
            style_preferences=payload.style_preferences,
        )
        logger.info(
            f"Successfully synced user - clerk_user_id='{user.clerk_user_id}' -> "
            f"convex_user_id='{convex_user_id}' (New user: {is_new_user})"
        )
    except Exception as exc:
        logger.error(f"Convex sync failed for clerk_user_id='{user.clerk_user_id}': {str(exc)}")
        raise exc

    return AuthSyncResponse(
        convex_user_id=convex_user_id,
        clerk_user_id=user.clerk_user_id,
        email=user.email,
        role=payload.role,
        is_new_user=is_new_user,
        created_at=record["created_at"],
        full_name=record.get("full_name"),
        gender=record.get("gender"),
        style_preferences=record.get("style_preferences", []),
        has_completed_onboarding=record.get("has_completed_onboarding", False),
    )


@router.patch("/me", response_model=AuthUpdateResponse)
async def update_me(
    payload: AuthMeUpdateRequest,
    user: ClerkUser = Depends(get_current_user),
) -> AuthUpdateResponse:
    try:
        convex = ConvexClient()
        updated, _ = convex.update_user_profile(
            clerk_user_id=user.clerk_user_id,
            full_name=payload.full_name,
            notification_prefs=payload.notification_prefs,
            gender=payload.gender,
            style_preferences=payload.style_preferences,
            has_completed_onboarding=payload.has_completed_onboarding,
        )
        if not updated:
            logger.warning(f"Profile update failed: user not found for clerk_user_id='{user.clerk_user_id}'")
            raise HTTPException(status_code=404, detail="User not found")
        logger.info(f"Updated user profile for clerk_user_id='{user.clerk_user_id}'")
    except Exception as exc:
        if not isinstance(exc, HTTPException):
            logger.error(f"Profile update exception for clerk_user_id='{user.clerk_user_id}': {str(exc)}")
        raise exc
    return AuthUpdateResponse(updated=True)


@router.get("/admin-check")
async def admin_check(user: ClerkUser = Depends(require_admin)) -> dict[str, str]:
    return {"status": "ok", "role": user.role}


@router.get("/stylist-check")
async def stylist_check(user: ClerkUser = Depends(require_stylist)) -> dict[str, str]:
    return {"status": "ok", "role": user.role}
