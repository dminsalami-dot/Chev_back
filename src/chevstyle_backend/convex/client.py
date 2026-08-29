import logging

logger = logging.getLogger("chevstyle_backend.convex.client")
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from convex import ConvexClient as RealConvexClient
from chevstyle_backend.config import settings

# In-memory mock store fallback for testing and development offline.
_store: dict[str, dict[str, Any]] = {}
_image_store: dict[str, dict[str, Any]] = {}
_hairstyle_store: dict[str, dict[str, Any]] = {}
_saved_styles_store: dict[str, dict[str, Any]] = {}
_generation_job_store: dict[str, dict[str, Any]] = {}
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
        gender: str | None = None,
        style_preferences: list[str] | None = None,
    ) -> tuple[str, bool, dict[str, Any]]:
        """Create or update a user record and return a Convex user id."""
        logger.info(
            f"[ConvexClient.upsert_user] clerk_user_id='{clerk_user_id}', email='{email}', "
            f"role='{role}', gender='{gender}', style_preferences={style_preferences}"
        )
        if self.is_mock:
            with _lock:
                is_new = clerk_user_id not in _store
                if is_new:
                    _store[clerk_user_id] = {
                        "email": email,
                        "role": role,
                        "full_name": full_name,
                        "profile_image_url": None,
                        "gender": gender,
                        "style_preferences": style_preferences or [],
                        "has_completed_onboarding": bool(gender),
                        "notification_prefs": _default_notification_prefs(),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                else:
                    existing = _store[clerk_user_id]
                    existing["email"] = email
                    existing["role"] = role
                    if full_name is not None:
                        existing["full_name"] = full_name
                    if gender is not None:
                        existing["gender"] = gender
                        existing["has_completed_onboarding"] = True
                    if style_preferences is not None:
                        existing["style_preferences"] = style_preferences

                logger.debug(f"[Convex Mock] Upserted user record: {_store[clerk_user_id]}")
                return f"convex_{clerk_user_id}", is_new, _store[clerk_user_id]
        else:
            payload: dict[str, Any] = {
                "clerk_user_id": clerk_user_id,
                "email": email,
                "role": role,
                "full_name": full_name,
            }
            if gender is not None:
                payload["gender"] = gender
                payload["has_completed_onboarding"] = True
            if style_preferences is not None:
                payload["style_preferences"] = style_preferences
            logger.info(f"[Convex Real] Calling users:upsert_user with payload={payload}")
            res = self.real_client.mutation("users:upsert_user", payload)
            logger.info(f"[Convex Real] Upsert response id={res.get('id')}, is_new={res.get('is_new')}")
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
        gender: str | None = None,
        style_preferences: list[str] | None = None,
        has_completed_onboarding: bool | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        logger.info(
            f"[ConvexClient.update_user_profile] clerk_user_id='{clerk_user_id}' | "
            f"updates={{'full_name': '{full_name}', 'gender': '{gender}', "
            f"'style_preferences': {style_preferences}, 'has_completed_onboarding': {has_completed_onboarding}, "
            f"'notification_prefs': {notification_prefs}}}"
        )
        if self.is_mock:
            with _lock:
                existing = _store.get(clerk_user_id)
                if existing is None:
                    logger.warning(f"[Convex Mock] User not found for update: clerk_user_id='{clerk_user_id}'")
                    return False, {}

                if full_name is not None:
                    existing["full_name"] = full_name
                if notification_prefs is not None:
                    existing["notification_prefs"] = notification_prefs
                if gender is not None:
                    existing["gender"] = gender
                if style_preferences is not None:
                    existing["style_preferences"] = style_preferences
                if has_completed_onboarding is not None:
                    existing["has_completed_onboarding"] = has_completed_onboarding
                elif gender is not None:
                    existing["has_completed_onboarding"] = True

                logger.debug(f"[Convex Mock] Updated user record: {existing}")
                return True, existing
        else:
            # Build strictly partial dictionary excluding any None values
            payload: dict[str, Any] = {
                "clerk_user_id": clerk_user_id,
            }
            if full_name is not None:
                payload["full_name"] = full_name
            if notification_prefs is not None:
                payload["notification_prefs"] = notification_prefs
            if gender is not None:
                payload["gender"] = gender
                payload["has_completed_onboarding"] = True
            if style_preferences is not None:
                payload["style_preferences"] = style_preferences
            if has_completed_onboarding is not None:
                payload["has_completed_onboarding"] = has_completed_onboarding
            elif gender is not None:
                payload["has_completed_onboarding"] = True
            
            logger.info(f"[Convex Real] Calling users:update_user_profile with payload={payload}")
            res = self.real_client.mutation(
                "users:update_user_profile",
                payload,
            )
            logger.info(f"[Convex Real] Update response: {res}")
            return bool(res["updated"]), dict(res["record"])

    def store_image(self, file_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        """Uploads an image to Convex storage and returns the storage ID."""
        if self.is_mock:
            import uuid
            storage_id = f"storage_{uuid.uuid4().hex[:8]}"
            return storage_id
        else:
            import httpx
            # 1. Get a short-lived upload URL from our custom Convex mutation.
            upload_url = self.real_client.mutation(
                "uploaded_images:generate_upload_url", {}
            )
            # 2. POST the raw bytes directly to the returned URL.
            response = httpx.post(
                str(upload_url),
                content=file_bytes,
                headers={"Content-Type": mime_type},
            )
            response.raise_for_status()
            return response.json()["storageId"]

    def get_storage_url(self, storage_id: str) -> str:
        """Returns the public serving URL for a Convex storage ID."""
        if self.is_mock:
            return f"https://mock.cdn.convex.dev/img/{storage_id}.jpg"
        else:
            res = self.real_client.query(
                "uploaded_images:get_url", {"storage_id": storage_id}
            )
            return str(res)

    def create_uploaded_image_record(
        self,
        user_id: str,
        storage_id: str,
        url: str,
        face_verified: bool,
        face_verification_score: float | None,
        hair_bounding_box: dict | None,
        hair_segmentation_confidence: float | None,
        image_metadata: dict,
        hair_segmentation_path: str | None = None,
        consent_given: bool = True,
        image_validated: bool = False,
    ) -> dict[str, Any]:
        """Creates a record in the uploaded_images collection."""
        if self.is_mock:
            import uuid
            image_id = f"img_{uuid.uuid4().hex[:8]}"
            record = {
                "image_id": image_id,
                "user_id": user_id,
                "storage_id": storage_id,
                "url": url,
                "face_verified": face_verified,
                "face_verification_score": face_verification_score,
                "hair_bounding_box": hair_bounding_box,
                "hair_segmentation_confidence": hair_segmentation_confidence,
                "hair_segmentation_path": hair_segmentation_path,
                "image_metadata": image_metadata,
                "consent_given": consent_given,
                "image_validated": image_validated,
                "is_deleted": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            with _lock:
                _image_store[image_id] = record
            return record
        else:
            res = self.real_client.mutation(
                "uploaded_images:create",
                {
                    "user_id": user_id,
                    "storage_id": storage_id,
                    "url": url,
                    "face_verified": face_verified,
                    "face_verification_score": face_verification_score,
                    "hair_bounding_box": hair_bounding_box,
                    "hair_segmentation_confidence": hair_segmentation_confidence,
                    "hair_segmentation_path": hair_segmentation_path,
                    "image_metadata": image_metadata,
                    "consent_given": consent_given,
                    "image_validated": image_validated,
                },
            )
            # Convex returns { id, record } — flatten to a single dict with image_id
            nested_record = dict(res.get("record") or {})
            nested_record["image_id"] = str(res.get("id", ""))
            if "created_at" not in nested_record:
                nested_record["created_at"] = datetime.now(timezone.utc).isoformat()
            return nested_record

    def update_image_validated(self, image_id: str, image_validated: bool) -> None:
        """Update the image_validated flag on an existing uploaded_images record."""
        if self.is_mock:
            with _lock:
                record = _image_store.get(image_id)
                if record is not None:
                    record["image_validated"] = image_validated
        else:
            self.real_client.mutation(
                "uploaded_images:update_validated",
                {
                    "image_id": image_id,
                    "image_validated": image_validated,
                },
            )

    def delete_image(self, image_id: str, user_id: str) -> dict[str, Any]:
        """
        Hard-delete an uploaded image record from Convex using both image_id and
        user_id for authorization. Prints a terminal message on success.

        In mock mode the record is removed from the in-memory store.
        In real mode the Convex `uploaded_images:delete_image` mutation is called.
        """
        if self.is_mock:
            with _lock:
                removed = _image_store.pop(image_id, None)
            if removed is not None:
                print(
                    f"[Convex Mock] Deleted image record: "
                    f"image_id='{image_id}' user_id='{user_id}'"
                )
                return {"deleted": True, "image_id": image_id}
            else:
                print(
                    f"[Convex Mock] Delete attempted but record not found: "
                    f"image_id='{image_id}' user_id='{user_id}'"
                )
                return {"deleted": False, "image_id": image_id}
        else:
            res = self.real_client.mutation(
                "uploaded_images:delete_image",
                {
                    "image_id": image_id,
                    "user_id": user_id,
                },
            )
            return dict(res)

    # ------------------------------------------------------------------ #
    #  Hairstyle catalog                                                  #
    # ------------------------------------------------------------------ #

    def create_hairstyle(
        self,
        name: str,
        gender: str,
        categories: list[str],
        image_url: str,
        picture_hash: str,
        description: str,
        maintenance_level: str,
        stylist_specs: str,
        hashtags: list[str],
        likes_count: str = "0",
        is_trending: bool = False,
    ) -> dict[str, Any]:
        """Creates a hairstyle record in Convex."""
        payload = {
            "name": name,
            "gender": gender,
            "categories": categories,
            "imageUrl": image_url,
            "pictureHash": picture_hash,
            "description": description,
            "maintenanceLevel": maintenance_level,
            "stylistSpecs": stylist_specs,
            "hashtags": hashtags,
            "likesCount": likes_count,
            "isTrending": is_trending,
        }
        if self.is_mock:
            import uuid
            doc_id = f"style_{uuid.uuid4().hex[:8]}"
            record = dict(payload)
            record["_id"] = doc_id
            with _lock:
                _hairstyle_store[doc_id] = record
            return record
        else:
            res = self.real_client.mutation("hairstyles:create", payload)
            if isinstance(res, dict):
                return dict(res)
            return {"_id": str(res), **payload}

    def list_hairstyles(self, gender: str | None = None) -> list[dict[str, Any]]:
        """Return all hairstyles, optionally filtered by gender."""
        if self.is_mock:
            with _lock:
                items = list(_hairstyle_store.values())
            if gender:
                items = [h for h in items if h.get("gender") == gender or h.get("gender") == "unisex"]
            return items
        else:
            args: dict[str, Any] = {}
            if gender:
                args["gender"] = gender
            results = self.real_client.query("hairstyles:list", args)
            return [dict(r) for r in results]

    def get_hairstyle_by_id(self, hairstyle_id: str) -> dict[str, Any] | None:
        """Return a single hairstyle by its Convex document ID."""
        if self.is_mock:
            with _lock:
                return _hairstyle_store.get(hairstyle_id)
        else:
            res = self.real_client.query(
                "hairstyles:getById", {"id": hairstyle_id}
            )
            return dict(res) if res else None

    # ------------------------------------------------------------------ #
    #  Saved styles                                                       #
    # ------------------------------------------------------------------ #

    def list_saved_styles(self, user_id: str) -> list[dict[str, Any]]:
        """Return all saved styles for a specific user ID."""
        if self.is_mock:
            with _lock:
                items = [
                    dict(h)
                    for h in _saved_styles_store.values()
                    if h.get("userId") == user_id
                ]
            # order desc by savedAt
            items.sort(key=lambda x: x.get("savedAt", 0), reverse=True)
            return items
        else:
            results = self.real_client.query(
                "saved_styles:listSavedStyles", {"userId": user_id}
            )
            return [dict(r) for r in results]

    def toggle_saved_style(
        self,
        user_id: str,
        hairstyle_id: str,
        hairstyle_name: str,
        image_url: str,
        preview_id: str | None = None,
        preview_image_url: str | None = None,
    ) -> dict[str, Any]:
        """Toggles a hairstyle in the user's saved styles list."""
        if self.is_mock:
            import uuid
            with _lock:
                existing = None
                for style_id, value in _saved_styles_store.items():
                    if (
                        value.get("userId") == user_id
                        and value.get("hairstyleId") == hairstyle_id
                    ):
                        existing = value
                        break

                if existing:
                    existing_id = existing["_id"]
                    _saved_styles_store.pop(existing_id)
                    return {"isSaved": False, "id": existing_id}
                else:
                    new_id = f"saved_{uuid.uuid4().hex[:8]}"
                    record = {
                        "_id": new_id,
                        "userId": user_id,
                        "hairstyleId": hairstyle_id,
                        "hairstyleName": hairstyle_name,
                        "imageUrl": image_url,
                        "previewId": preview_id,
                        "previewImageUrl": preview_image_url,
                        "savedAt": int(datetime.now(timezone.utc).timestamp() * 1000),
                    }
                    _saved_styles_store[new_id] = record
                    return {"isSaved": True, "id": new_id}
        else:
            args: dict[str, Any] = {
                "userId": user_id,
                "hairstyleId": hairstyle_id,
                "hairstyleName": hairstyle_name,
                "imageUrl": image_url,
            }
            if preview_id:
                args["previewId"] = preview_id
            if preview_image_url:
                args["previewImageUrl"] = preview_image_url

            res = self.real_client.mutation(
                "saved_styles:toggleSavedStyle",
                args,
            )
            return dict(res)

    def remove_saved_style(self, id: str) -> dict[str, Any]:
        """Remove a saved style by its document ID."""
        if self.is_mock:
            with _lock:
                _saved_styles_store.pop(id, None)
            return {"success": True}
        else:
            res = self.real_client.mutation(
                "saved_styles:removeSavedStyle", {"id": id}
            )
            return dict(res)

    # ------------------------------------------------------------------ #
    #  Generation Jobs                                                    #
    # ------------------------------------------------------------------ #

    def create_generation_job(
        self,
        user_id: str,
        source_image_id: str,
        hairstyle_id: str,
    ) -> dict[str, Any]:
        """Create a new generation job record with status='queued'. Returns {id, ...}."""
        if self.is_mock:
            import uuid
            job_id = f"job_{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc).isoformat()
            record = {
                "_id": job_id,
                "user_id": user_id,
                "source_image_id": source_image_id,
                "hairstyle_id": hairstyle_id,
                "status": "queued",
                "model_used": None,
                "result_storage_id": None,
                "result_url": None,
                "error_message": None,
                "attempt_count": 0,
                "created_at": now,
                "updated_at": now,
            }
            with _lock:
                _generation_job_store[job_id] = record
            logger.debug(f"[Convex Mock] Created generation job: {job_id}")
            return {"id": job_id, "record": record}
        else:
            res = self.real_client.mutation(
                "generation_jobs:create",
                {
                    "user_id": user_id,
                    "source_image_id": source_image_id,
                    "hairstyle_id": hairstyle_id,
                },
            )
            return dict(res)

    def update_generation_job(
        self,
        job_id: str,
        status: str,
        model_used: str | None = None,
        result_storage_id: str | None = None,
        result_url: str | None = None,
        error_message: str | None = None,
        attempt_count: int | None = None,
    ) -> None:
        """Patch a generation job's status and optional result/error fields."""
        if self.is_mock:
            with _lock:
                record = _generation_job_store.get(job_id)
                if record is None:
                    logger.warning(f"[Convex Mock] Generation job not found: {job_id}")
                    return
                record["status"] = status
                record["updated_at"] = datetime.now(timezone.utc).isoformat()
                if model_used is not None:
                    record["model_used"] = model_used
                if result_storage_id is not None:
                    record["result_storage_id"] = result_storage_id
                if result_url is not None:
                    record["result_url"] = result_url
                if error_message is not None:
                    record["error_message"] = error_message
                if attempt_count is not None:
                    record["attempt_count"] = attempt_count
            logger.debug(f"[Convex Mock] Updated generation job {job_id}: status={status}")
        else:
            payload: dict[str, Any] = {"job_id": job_id, "status": status}
            if model_used is not None:
                payload["model_used"] = model_used
            if result_storage_id is not None:
                payload["result_storage_id"] = result_storage_id
            if result_url is not None:
                payload["result_url"] = result_url
            if error_message is not None:
                payload["error_message"] = error_message
            if attempt_count is not None:
                payload["attempt_count"] = attempt_count
            self.real_client.mutation("generation_jobs:update_status", payload)

    def get_generation_job(self, job_id: str) -> dict[str, Any] | None:
        """Return a single generation job by its document ID."""
        if self.is_mock:
            with _lock:
                record = _generation_job_store.get(job_id)
            return dict(record) if record else None
        else:
            res = self.real_client.query(
                "generation_jobs:get", {"job_id": job_id}
            )
            return dict(res) if res else None

    def list_generation_jobs(self, user_id: str) -> list[dict[str, Any]]:
        """Return all generation jobs for a user (newest first in mock)."""
        if self.is_mock:
            with _lock:
                jobs = [
                    dict(j) for j in _generation_job_store.values()
                    if j.get("user_id") == user_id
                ]
            jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return jobs
        else:
            results = self.real_client.query(
                "generation_jobs:list_by_user", {"user_id": user_id}
            )
            return [dict(r) for r in results]
