import threading
from datetime import datetime, timezone
from typing import Any, Optional

from chevstyle_backend.config import settings

# Very small in-memory mock Convex client for development and tests.
# Replace with a real Convex SDK wrapper in production.
_store: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _default_notification_prefs() -> dict[str, bool]:
    return {
        "generation_complete": True,
        "generation_failed": True,
        "stylist_share": True,
        "consultation_update": True,
    }


class ConvexClient:
    def __init__(self, url: Optional[str] = None, deploy_key: Optional[str] = None):
        self.url = url or settings.convex_url
        self.deploy_key = deploy_key or settings.convex_deploy_key

    def upsert_user(
        self,
        clerk_user_id: str,
        email: str,
        role: str,
        full_name: str | None = None,
    ) -> tuple[str, bool, dict[str, Any]]:
        """Create or update a user record and return a synthetic Convex user id."""
        with _lock:
            is_new = clerk_user_id not in _store
            if is_new:
                _store[clerk_user_id] = {
                    "email": email,
                    "role": role,
                    "full_name": full_name,
                    "profile_image_url": None,
                    "notification_prefs": _default_notification_prefs(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                existing = _store[clerk_user_id]
                existing["email"] = email
                existing["role"] = role
                existing["full_name"] = full_name or existing.get("full_name")

            return f"convex_{clerk_user_id}", is_new, _store[clerk_user_id]

    def get_user_by_clerk_id(self, clerk_user_id: str) -> dict[str, Any] | None:
        with _lock:
            return _store.get(clerk_user_id)

    def update_user_profile(
        self,
        clerk_user_id: str,
        full_name: str | None = None,
        notification_prefs: dict[str, bool] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        with _lock:
            existing = _store.get(clerk_user_id)
            if existing is None:
                return False, {}

            if full_name is not None:
                existing["full_name"] = full_name
            if notification_prefs is not None:
                existing["notification_prefs"] = notification_prefs

            return True, existing
