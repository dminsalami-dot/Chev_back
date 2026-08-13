import threading
from datetime import datetime, timezone
from typing import Any, Optional

from convex import ConvexClient as RealConvexClient
from chevstyle_backend.config import settings

# In-memory mock store fallback for testing and development offline.
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
        
        # We fall back to mock mode if settings.app_env is "test", if running in pytest, or if no real Convex URL is configured
        import sys
        self.is_mock = settings.app_env == "test" or "pytest" in sys.modules or not self.url

        if not self.is_mock:
            self.real_client = RealConvexClient(self.url)
            if self.deploy_key:
                self.real_client.set_admin_auth(self.deploy_key)

    def upsert_user(
        self,
        clerk_user_id: str,
        email: str,
        role: str,
        full_name: str | None = None,
    ) -> tuple[str, bool, dict[str, Any]]:
        """Create or update a user record and return a Convex user id."""
        if self.is_mock:
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
        else:
            res = self.real_client.mutation(
                "users:upsert_user",
                {
                    "clerk_user_id": clerk_user_id,
                    "email": email,
                    "role": role,
                    "full_name": full_name,
                },
            )
            # Convex ID (_id) is returned as a string, e.g. "j97...".
            return str(res["id"]), bool(res["is_new"]), dict(res["record"])

    def get_user_by_clerk_id(self, clerk_user_id: str) -> dict[str, Any] | None:
        if self.is_mock:
            with _lock:
                return _store.get(clerk_user_id)
        else:
            res = self.real_client.query(
                "users:get_user_by_clerk_id",
                {"clerk_user_id": clerk_user_id},
            )
            return res if res is None else dict(res)

    def update_user_profile(
        self,
        clerk_user_id: str,
        full_name: str | None = None,
        notification_prefs: dict[str, bool] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if self.is_mock:
            with _lock:
                existing = _store.get(clerk_user_id)
                if existing is None:
                    return False, {}

                if full_name is not None:
                    existing["full_name"] = full_name
                if notification_prefs is not None:
                    existing["notification_prefs"] = notification_prefs

                return True, existing
        else:
            res = self.real_client.mutation(
                "users:update_user_profile",
                {
                    "clerk_user_id": clerk_user_id,
                    "full_name": full_name,
                    "notification_prefs": notification_prefs,
                },
            )
            return bool(res["updated"]), dict(res["record"])
