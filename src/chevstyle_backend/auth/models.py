from pydantic import BaseModel, Field


class ClerkUser(BaseModel):
    clerk_user_id: str
    email: str
    role: str  # "customer" | "stylist" | "admin"
    convex_user_id: str | None = None
    full_name: str | None = None
    profile_image_url: str | None = None
    notification_prefs: dict[str, bool] = Field(default_factory=lambda: {
        "generation_complete": True,
        "generation_failed": True,
        "stylist_share": True,
        "consultation_update": True,
    })


class AuthSyncRequest(BaseModel):
    full_name: str | None = None
    role: str = "customer"


class AuthSyncResponse(BaseModel):
    convex_user_id: str
    clerk_user_id: str
    email: str
    role: str
    is_new_user: bool
    created_at: str
    full_name: str | None = None
