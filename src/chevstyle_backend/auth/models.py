from pydantic import BaseModel, Field


class ClerkUser(BaseModel):
    clerk_user_id: str
    email: str
    role: str  # "customer" | "stylist" | "admin"
    convex_user_id: str | None = None
    full_name: str | None = None
    profile_image_url: str | None = None
    gender: str | None = None  # "men" | "women" | "unisex"
    style_preferences: list[str] = Field(default_factory=list)
    has_completed_onboarding: bool = False
    notification_prefs: dict[str, bool] = Field(default_factory=lambda: {
        "generation_complete": True,
        "generation_failed": True,
        "stylist_share": True,
        "consultation_update": True,
    })


class AuthSyncRequest(BaseModel):
    full_name: str | None = None
    role: str = "customer"
    gender: str | None = None
    style_preferences: list[str] | None = None


class AuthSyncResponse(BaseModel):
    convex_user_id: str
    clerk_user_id: str
    email: str
    role: str
    is_new_user: bool
    created_at: str
    full_name: str | None = None
    gender: str | None = None
    style_preferences: list[str] = Field(default_factory=list)
    has_completed_onboarding: bool = False


class AuthMeUpdateRequest(BaseModel):
    full_name: str | None = None
    notification_prefs: dict[str, bool] | None = None
    gender: str | None = None
    style_preferences: list[str] | None = None
    has_completed_onboarding: bool | None = None


class AuthUpdateResponse(BaseModel):
    updated: bool
