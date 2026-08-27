from pydantic import BaseModel, Field
from typing import List


class HairstyleResponse(BaseModel):
    """Response model for a single hairstyle, using camelCase field names
    to align with the Flutter client model."""

    id: str = Field(..., description="Unique hairstyle ID (Convex document ID)")
    name: str
    gender: str = Field("unisex", description="men | women | unisex")
    categories: List[str] = Field(default_factory=list)
    imageUrl: str
    pictureHash: str = "L6PZfSi_.AyE_3t7t7R**0o#DgR4"
    description: str
    maintenanceLevel: str = "Medium"  # "Low" | "Medium" | "High"
    stylistSpecs: str
    hashtags: List[str] = Field(default_factory=list)
    likesCount: str = "1.2k"
    isTrending: bool = False
