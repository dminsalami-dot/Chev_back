from pydantic import BaseModel, Field
from typing import List, Optional


class ToggleSavedStyleRequest(BaseModel):
    """Request model for toggling a saved hairstyle."""

    hairstyleId: str = Field(..., alias="hairstyleId", description="ID of the hairstyle from catalog")
    hairstyleName: str = Field(..., alias="hairstyleName", description="Name of the hairstyle")
    imageUrl: str = Field(..., alias="imageUrl", description="URL of the hairstyle image")
    previewId: Optional[str] = Field(None, alias="previewId", description="Optional preview ID of try-on")
    previewImageUrl: Optional[str] = Field(None, alias="previewImageUrl", description="Optional try-on preview image URL")

    model_config = {
        "populate_by_name": True,
    }


class ToggleSavedStyleResponse(BaseModel):
    """Response model returning the updated save state."""

    isSaved: bool = Field(..., alias="isSaved")
    id: str

    model_config = {
        "populate_by_name": True,
    }


class SavedStyleResponse(BaseModel):
    """Response model for a saved hairstyle, using camelCase fields."""

    id: str = Field(..., alias="id")
    userId: str = Field(..., alias="userId")
    hairstyleId: str = Field(..., alias="hairstyleId")
    hairstyleName: str = Field(..., alias="hairstyleName")
    imageUrl: str = Field(..., alias="imageUrl")
    previewId: Optional[str] = Field(None, alias="previewId")
    previewImageUrl: Optional[str] = Field(None, alias="previewImageUrl")
    savedAt: int = Field(..., alias="savedAt")
    tags: Optional[List[str]] = Field(None, alias="tags")

    model_config = {
        "populate_by_name": True,
    }


class SimpleSuccessResponse(BaseModel):
    """Basic indicator of success status."""

    success: bool
