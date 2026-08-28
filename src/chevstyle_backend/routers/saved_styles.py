import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from chevstyle_backend.dependencies import get_current_user
from chevstyle_backend.auth.models import ClerkUser
from chevstyle_backend.convex.client import ConvexClient
from chevstyle_backend.schemas.saved_style import (
    ToggleSavedStyleRequest,
    ToggleSavedStyleResponse,
    SavedStyleResponse,
    SimpleSuccessResponse,
)

logger = logging.getLogger("chevstyle_backend.routers.saved_styles")
router = APIRouter(prefix="/api/v1/saved-styles", tags=["Saved Styles"])


def _map_saved_style(s: dict) -> SavedStyleResponse:
    """Map raw Convex saved_styles document to Pydantic schema."""
    return SavedStyleResponse(
        id=str(s["_id"]),
        userId=str(s["userId"]),
        hairstyleId=s["hairstyleId"],
        hairstyleName=s["hairstyleName"],
        imageUrl=s["imageUrl"],
        previewId=s.get("previewId"),
        previewImageUrl=s.get("previewImageUrl"),
        savedAt=s["savedAt"],
        tags=s.get("tags"),
    )


@router.post("", response_model=ToggleSavedStyleResponse, status_code=status.HTTP_200_OK)
async def toggle_saved_style(
    req: ToggleSavedStyleRequest,
    user: ClerkUser = Depends(get_current_user),
):
    """
    Toggles (saves or unsaves) a hairstyle for the current user.
    """
    if not user.convex_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Convex user ID is missing. Ensure your account is fully synced.",
        )

    logger.info(
        f"User '{user.convex_user_id}' toggling saved style hairstyleId '{req.hairstyleId}'"
    )

    try:
        convex = ConvexClient()
        res = convex.toggle_saved_style(
            user_id=user.convex_user_id,
            hairstyle_id=req.hairstyleId,
            hairstyle_name=req.hairstyleName,
            image_url=req.imageUrl,
            preview_id=req.previewId,
            preview_image_url=req.previewImageUrl,
        )
        return ToggleSavedStyleResponse(
            isSaved=res["isSaved"],
            id=str(res["id"]),
        )
    except Exception as exc:
        logger.exception(f"Error toggling saved style: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update saved style status",
        )


@router.get("", response_model=List[SavedStyleResponse])
async def list_saved_styles(
    user: ClerkUser = Depends(get_current_user),
):
    """
    Lists all saved styles for the current user.
    """
    if not user.convex_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Convex user ID is missing. Ensure your account is fully synced.",
        )

    logger.info(f"Listing saved styles for user '{user.convex_user_id}'")

    try:
        convex = ConvexClient()
        results = convex.list_saved_styles(user.convex_user_id)
        return [_map_saved_style(s) for s in results]
    except Exception as exc:
        logger.exception(f"Error listing saved styles: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve saved styles",
        )


@router.delete("/{id}", response_model=SimpleSuccessResponse)
async def delete_saved_style(
    id: str,
    user: ClerkUser = Depends(get_current_user),
):
    """
    Deletes a saved style by its document ID.
    Enforces ownership check before deleting.
    """
    if not user.convex_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Convex user ID is missing. Ensure your account is fully synced.",
        )

    logger.info(
        f"Request by user '{user.convex_user_id}' to delete saved style ID '{id}'"
    )

    try:
        convex = ConvexClient()

        # Enforce ownership check
        saved_items = convex.list_saved_styles(user.convex_user_id)
        if not any(str(s["_id"]) == id for s in saved_items):
            logger.warning(
                f"Ownership check failed or style not found for id '{id}' by user '{user.convex_user_id}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this saved style or it does not exist.",
            )

        convex.remove_saved_style(id)
        logger.info(f"Deleted saved style ID '{id}' successful")
        return SimpleSuccessResponse(success=True)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error deleting saved style {id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete saved style",
        )
