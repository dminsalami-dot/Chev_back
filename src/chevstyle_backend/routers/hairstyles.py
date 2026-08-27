import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from chevstyle_backend.convex.client import ConvexClient
from chevstyle_backend.schemas.hairstyle import HairstyleResponse

logger = logging.getLogger("chevstyle_backend")

router = APIRouter(prefix="/api/v1/hairstyles", tags=["hairstyles"])

# Shared Convex client instance for this module
_convex: ConvexClient | None = None


def _get_convex() -> ConvexClient:
    global _convex
    if _convex is None:
        _convex = ConvexClient()
    return _convex


def _map_hairstyle(h: dict) -> HairstyleResponse:
    """Map a raw Convex hairstyle document to the API response model."""
    return HairstyleResponse(
        id=str(h["_id"]),
        name=h["name"],
        gender=h.get("gender", "unisex"),
        categories=h.get("categories", []),
        imageUrl=h["imageUrl"],
        pictureHash=h.get("pictureHash", "L6PZfSi_.AyE_3t7t7R**0o#DgR4"),
        description=h.get("description", ""),
        maintenanceLevel=h.get("maintenanceLevel", "Medium"),
        stylistSpecs=h.get("stylistSpecs", ""),
        hashtags=h.get("hashtags", []),
        likesCount=h.get("likesCount", "1.2k"),
        isTrending=h.get("isTrending", False),
    )


@router.get("", response_model=List[HairstyleResponse])
async def list_hairstyles(
    gender: Optional[str] = Query(
        None, description="Filter by 'men', 'women', or 'unisex'"
    ),
):
    """
    Returns a list of hairstyles from the catalog.
    Public endpoint — no authentication required.
    """
    convex = _get_convex()
    try:
        results = convex.list_hairstyles(gender=gender)
        logger.info(
            f"Hairstyles listed: {len(results)} results"
            + (f" (gender={gender})" if gender else "")
        )
        return [_map_hairstyle(h) for h in results]
    except Exception as exc:
        logger.exception(f"Error listing hairstyles: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve hairstyles",
        )


@router.get("/{hairstyle_id}", response_model=HairstyleResponse)
async def get_hairstyle(hairstyle_id: str):
    """
    Returns a single hairstyle by its Convex document ID.
    Public endpoint — no authentication required.
    """
    convex = _get_convex()
    try:
        h = convex.get_hairstyle_by_id(hairstyle_id)
        if not h:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Hairstyle not found",
            )
        logger.info(f"Hairstyle retrieved: {hairstyle_id}")
        return _map_hairstyle(h)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error retrieving hairstyle {hairstyle_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
