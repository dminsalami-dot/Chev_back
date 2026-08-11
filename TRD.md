# TECHNICAL REQUIREMENTS DOCUMENT (TRD)

**Project:** AI Hairstyle & Haircut Visualization Platform — Backend API  
**Author:** Redeemer Salami Okekale  
**Last Updated:** August 2026  
**Stack:** FastAPI · Clerk · Convex · Pydantic · Gemini / OpenCV · uv

---

## 1. OVERVIEW

This document defines the technical requirements for the **backend API** of the AI Hairstyle & Haircut Visualization Platform. The backend is a **Python / FastAPI** service managed with **uv** and exposed as a REST API consumed by a **React Native** mobile client.

### Core Responsibilities

| Responsibility | Description |
|---|---|
| Authentication | Clerk-based JWT authentication for all protected routes |
| Image Intake | Accept user photo uploads, store securely in Convex |
| Face Verification | Validate that an uploaded image contains a detectable human face (Gemini / OpenCV) |
| Hair Segmentation | Detect and segment the hair region; return bounding box coordinates |
| AI Visualization | Trigger and manage hairstyle transformation jobs |
| Hairstyle Catalog | Manage and serve hairstyle metadata and reference images |
| Consultation Management | Support stylist-led consultation workflows |
| Saved Hairstyles | Persist user-curated hairstyle collections |
| Admin Operations | User management, catalog management, analytics |

---

## 2. SYSTEM ARCHITECTURE

```
React Native App
     │
     ▼ HTTPS / REST
FastAPI Server (uv)
     │
     ├── Clerk SDK ──────────────── Clerk Auth (JWT verification / user sync)
     │
     ├── Convex Client ──────────── Database + File Storage
     │       ├── users
     │       ├── hairstyles
     │       ├── uploaded_images
     │       ├── generated_previews
     │       ├── consultations
     │       ├── saved_hairstyles
     │       └── audit_logs
     │
     ├── Vision Pipeline
     │       ├── Face Verification  ── OpenCV (fast) → Gemini Vision (fallback/deep)
     │       └── Hair Segmentation  ── Segmentation model → Bounding box output
     │
     └── AI Generation Service
             └── Abstracted hairstyle transformer (pluggable model interface)
```

### Environment & Tooling

| Tool | Purpose |
|---|---|
| `uv` | Dependency management, virtual environment, project runner |
| `FastAPI` | Web framework |
| `Pydantic v2` | Request/response validation and settings |
| `httpx` | Async HTTP client for external service calls |
| `Pillow` / `opencv-python` | Image preprocessing and face detection |
| `google-generativeai` | Gemini Vision API for deep face/quality verification |
| `python-multipart` | Multipart file upload handling |
| `clerk-sdk-python` (or manual JWKS) | Clerk JWT verification |
| `convex` (Python client) | Convex database + storage |

---

## 3. PROJECT STRUCTURE

```
hairstyle-api/
├── pyproject.toml
├── uv.lock
├── .env
├── .env.example
├── README.md
│
├── app/
│   ├── main.py                  # FastAPI app factory
│   ├── config.py                # Pydantic Settings (BaseSettings)
│   ├── dependencies.py          # Shared FastAPI dependencies (auth, db)
│   │
│   ├── auth/
│   │   ├── clerk.py             # Clerk JWT verification middleware
│   │   └── models.py            # ClerkUser Pydantic model
│   │
│   ├── convex/
│   │   └── client.py            # Convex client wrapper
│   │
│   ├── vision/
│   │   ├── face_verification.py # OpenCV + Gemini face detection
│   │   ├── hair_segmentation.py # Hair region segmentation → bounding box
│   │   └── image_utils.py       # Resize, EXIF fix, format validation
│   │
│   ├── ai/
│   │   ├── base.py              # Abstract hairstyle generator interface
│   │   └── generator.py         # Concrete implementation (pluggable)
│   │
│   ├── routers/
│   │   ├── auth.py              # User sync / profile setup
│   │   ├── images.py            # Upload, face verify, segment
│   │   ├── hairstyles.py        # Catalog CRUD + search
│   │   ├── previews.py          # AI generation + results
│   │   ├── saved.py             # Save / manage hairstyles
│   │   ├── consultations.py     # Stylist consultation flow
│   │   ├── comparisons.py       # Side-by-side comparison
│   │   ├── recommendations.py   # Hairstyle recommendations
│   │   ├── sharing.py           # Share links / export
│   │   ├── notifications.py     # Notification preferences
│   │   └── admin/
│   │       ├── users.py         # Admin user management
│   │       ├── catalog.py       # Admin hairstyle management
│   │       ├── analytics.py     # Platform analytics
│   │       └── ai_ops.py        # AI monitoring / configuration
│   │
│   └── schemas/
│       ├── user.py
│       ├── image.py
│       ├── hairstyle.py
│       ├── preview.py
│       ├── consultation.py
│       ├── saved.py
│       └── admin.py
│
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

---

## 4. CONFIGURATION

### `app/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Clerk
    clerk_secret_key: str
    clerk_publishable_key: str
    clerk_jwks_url: str

    # Convex
    convex_url: str
    convex_deploy_key: str

    # Gemini
    gemini_api_key: str

    # App
    app_env: str = "development"
    allowed_origins: list[str] = ["*"]
    max_image_size_mb: int = 10
    min_image_dimension: int = 256

    # AI Generation
    ai_provider: str = "gemini"  # pluggable
    ai_generation_timeout_seconds: int = 120

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
```

---

## 5. AUTHENTICATION

### 5.1 Clerk JWT Verification

All protected routes require a `Bearer <clerk_jwt>` in the `Authorization` header.

**Verification Flow:**
1. Extract JWT from `Authorization: Bearer <token>` header.
2. Fetch Clerk JWKS from `clerk_jwks_url` (cached, refreshed on failure).
3. Decode and verify the JWT signature.
4. Extract `sub` (Clerk User ID) and `email` claims.
5. Look up or create the user in Convex.
6. Attach `ClerkUser` to the request context via FastAPI `Depends`.

**Role-based access:**

| Role | Access |
|---|---|
| `customer` | Own data, catalog browse, generate previews |
| `stylist` | Customer data during consultations, consultation history |
| `admin` | Full platform access |

### 5.2 Pydantic Model

```python
# app/auth/models.py
from pydantic import BaseModel

class ClerkUser(BaseModel):
    clerk_user_id: str
    email: str
    role: str  # "customer" | "stylist" | "admin"
    convex_user_id: str
```

### 5.3 Dependency

```python
# app/dependencies.py
async def get_current_user(
    authorization: str = Header(...),
) -> ClerkUser:
    token = authorization.removeprefix("Bearer ").strip()
    return await verify_clerk_jwt(token)

async def require_stylist(user: ClerkUser = Depends(get_current_user)) -> ClerkUser:
    if user.role not in ("stylist", "admin"):
        raise HTTPException(status_code=403, detail="Stylist access required")
    return user

async def require_admin(user: ClerkUser = Depends(get_current_user)) -> ClerkUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
```

---

## 6. CONVEX DATA SCHEMA

Convex is used as both the **database** and **file storage** layer. All collections are managed via Convex's document model.

### 6.1 `users`

| Field | Type | Notes |
|---|---|---|
| `_id` | ConvexID | Auto-generated |
| `clerk_user_id` | string | Unique, indexed |
| `email` | string | |
| `full_name` | string? | Optional |
| `role` | "customer" \| "stylist" \| "admin" | |
| `profile_image_url` | string? | Convex storage URL |
| `is_active` | boolean | Default `true` |
| `notification_prefs` | object | Per-channel preferences |
| `created_at` | number | Unix timestamp |

### 6.2 `uploaded_images`

| Field | Type | Notes |
|---|---|---|
| `_id` | ConvexID | |
| `user_id` | ConvexID | FK → users |
| `storage_id` | string | Convex storage ID |
| `url` | string | Serving URL |
| `face_verified` | boolean | |
| `face_verification_score` | number? | Confidence 0–1 |
| `hair_bounding_box` | object? | `{x, y, width, height}` |
| `hair_segmentation_mask_url` | string? | Optional mask image |
| `image_metadata` | object | Width, height, format |
| `consent_given` | boolean | User consent flag |
| `is_deleted` | boolean | Soft delete |
| `created_at` | number | |

### 6.3 `hairstyles`

| Field | Type | Notes |
|---|---|---|
| `_id` | ConvexID | |
| `name` | string | |
| `slug` | string | Unique, URL-safe |
| `description` | string | |
| `category` | string | e.g., "Fades", "Braids" |
| `hair_length` | "short" \| "medium" \| "long" | |
| `hair_texture` | string[] | e.g., ["coily", "wavy"] |
| `maintenance_level` | "low" \| "medium" \| "high" | |
| `styling_time_minutes` | number | |
| `reference_images` | string[] | Convex storage URLs |
| `tags` | string[] | For search |
| `related_hairstyle_ids` | ConvexID[] | |
| `is_active` | boolean | |
| `created_by_admin_id` | ConvexID | |
| `created_at` | number | |

### 6.4 `generated_previews`

| Field | Type | Notes |
|---|---|---|
| `_id` | ConvexID | |
| `user_id` | ConvexID | |
| `uploaded_image_id` | ConvexID | Source photo |
| `hairstyle_id` | ConvexID | |
| `status` | "pending" \| "processing" \| "completed" \| "failed" | |
| `result_url` | string? | Final generated image URL |
| `result_storage_id` | string? | Convex storage ID |
| `error_message` | string? | |
| `generation_time_ms` | number? | |
| `ai_provider` | string | Which model was used |
| `is_deleted` | boolean | |
| `created_at` | number | |

### 6.5 `saved_hairstyles`

| Field | Type | Notes |
|---|---|---|
| `_id` | ConvexID | |
| `user_id` | ConvexID | |
| `hairstyle_id` | ConvexID? | From catalog |
| `generated_preview_id` | ConvexID? | Or a generated result |
| `collection_name` | string | e.g., "Next haircut" |
| `notes` | string? | |
| `created_at` | number | |

### 6.6 `consultations`

| Field | Type | Notes |
|---|---|---|
| `_id` | ConvexID | |
| `stylist_id` | ConvexID | |
| `customer_id` | ConvexID? | Linked customer (optional) |
| `customer_name` | string? | Walk-in name |
| `uploaded_image_id` | ConvexID? | |
| `selected_hairstyle_id` | ConvexID? | |
| `selected_preview_id` | ConvexID? | |
| `notes` | string? | |
| `status` | "active" \| "completed" \| "archived" | |
| `created_at` | number | |
| `updated_at` | number | |

### 6.7 `audit_logs`

| Field | Type | Notes |
|---|---|---|
| `_id` | ConvexID | |
| `actor_user_id` | ConvexID | Who performed the action |
| `action` | string | e.g., `"user.suspended"` |
| `target_id` | string? | The resource acted on |
| `metadata` | object | Additional context |
| `created_at` | number | |

---

## 7. VISION PIPELINE

### 7.1 Face Verification

**Goal:** Confirm the uploaded image contains a detectable human face before storing or processing.

**Two-stage approach:**

| Stage | Tool | Trigger |
|---|---|---|
| Stage 1 (Fast) | OpenCV `haarcascade_frontalface_default` | Always run first |
| Stage 2 (Deep) | Gemini Vision API | If OpenCV confidence < threshold OR OpenCV finds no face |

**Stage 1 — OpenCV**

```python
# app/vision/face_verification.py

import cv2
import numpy as np
from PIL import Image

CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
face_cascade = cv2.CascadeClassifier(CASCADE_PATH)

def detect_faces_opencv(image_bytes: bytes) -> dict:
    """
    Returns:
        {
          "detected": bool,
          "face_count": int,
          "confidence": float,   # 0.0 – 1.0 approximation
          "faces": [{"x", "y", "width", "height"}]
        }
    """
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
    ...
```

**Stage 2 — Gemini Vision (deep verification)**

Prompt to Gemini Vision:

```
You are an image analysis assistant.
Analyze the provided image and answer ONLY in JSON:

{
  "has_human_face": true | false,
  "face_clearly_visible": true | false,
  "lighting_adequate": true | false,
  "face_obstructed": true | false,
  "image_quality_score": 0.0 – 1.0,
  "issues": []  // list of specific issues if any
}

Be factual and concise. Do not add any commentary outside the JSON object.
```

**Combined decision logic:**

```
if opencv.detected AND opencv.face_count == 1:
    if gemini_needed (quality check):
        run gemini for quality metadata only
    → PASS
elif opencv.face_count > 1:
    → FAIL (multiple faces detected)
elif not opencv.detected:
    run gemini as fallback
    if gemini.has_human_face AND gemini.face_clearly_visible:
        → PASS
    else:
        → FAIL
```

### 7.2 Hair Segmentation

**Goal:** Identify the hair region in the photo and return a **bounding box** `{x, y, width, height}` for use by the AI transformation step.

**Approach:** Semantic segmentation using a lightweight model (e.g., MediaPipe or a custom hair segmentation model served locally).

```python
# app/vision/hair_segmentation.py

from dataclasses import dataclass

@dataclass
class HairBoundingBox:
    x: int
    y: int
    width: int
    height: int
    confidence: float
    mask_available: bool

def segment_hair(image_bytes: bytes) -> HairBoundingBox:
    """
    1. Preprocess image.
    2. Run segmentation model.
    3. Extract hair mask.
    4. Compute tight bounding box around mask region.
    5. Return HairBoundingBox.
    """
    ...
```

**Pydantic response model:**

```python
class HairSegmentationResult(BaseModel):
    bounding_box: BoundingBox
    confidence: float
    mask_image_url: str | None = None   # Optional Convex-stored mask

class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int
```

### 7.3 Image Pre-processing (Before Any Pipeline Step)

All uploaded images pass through `image_utils.py` before vision pipeline execution:

1. **Format check** — accept JPEG, PNG, WEBP only.
2. **Size check** — reject if > `max_image_size_mb`.
3. **Dimension check** — reject if shorter than `min_image_dimension` on any side.
4. **EXIF rotation fix** — apply `ImageOps.exif_transpose`.
5. **Resize** — scale down to max 1920px on the longest side (preserve aspect ratio).
6. **Convert to RGB** — strip alpha channels.
7. **Return normalized bytes + metadata.**

---

## 8. API ENDPOINTS

All endpoints are prefixed with `/api/v1`.

Standard error response:
```json
{
  "error": "FACE_NOT_DETECTED",
  "message": "No human face was detected in the uploaded image.",
  "detail": {}
}
```

---

### 8.1 Auth & User Sync

#### `POST /api/v1/auth/sync`
Sync a Clerk user into the Convex `users` collection after first sign-in or profile update.

**Auth:** Bearer JWT (Clerk)

**Request body:**
```json
{
  "full_name": "Jane Doe",
  "role": "customer"
}
```

**Response `200`:**
```json
{
  "convex_user_id": "jd7x9...",
  "clerk_user_id": "user_2abc...",
  "email": "jane@example.com",
  "role": "customer",
  "is_new_user": true,
  "created_at": "2026-08-11T11:00:00Z"
}
```

---

#### `GET /api/v1/auth/me`
Return the current user's profile.

**Auth:** Bearer JWT

**Response `200`:**
```json
{
  "convex_user_id": "jd7x9...",
  "email": "jane@example.com",
  "full_name": "Jane Doe",
  "role": "customer",
  "profile_image_url": "https://cdn.convex.dev/...",
  "notification_prefs": {
    "generation_complete": true,
    "generation_failed": true,
    "stylist_share": true,
    "consultation_update": true
  }
}
```

---

#### `PATCH /api/v1/auth/me`
Update profile fields (name, notification preferences).

**Auth:** Bearer JWT

**Request body:**
```json
{
  "full_name": "Jane Doe",
  "notification_prefs": {
    "generation_complete": false
  }
}
```

**Response `200`:**
```json
{ "updated": true }
```

---

### 8.2 Image Upload & Vision Pipeline

#### `POST /api/v1/images/upload`
Upload a user photo, run face verification, run hair segmentation, and store results.

**Auth:** Bearer JWT  
**Content-Type:** `multipart/form-data`

**Form fields:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | ✅ | JPEG / PNG / WEBP |
| `consent_given` | boolean | ✅ | Must be `true` |

**Processing flow:**
```
1. Validate file format, size, dimensions
2. Preprocess (EXIF fix, resize, RGB normalization)
3. Stage 1 face verification (OpenCV)
4. If needed → Stage 2 face verification (Gemini)
5. If face not detected → return 422
6. Hair segmentation → bounding box
7. Upload processed image to Convex Storage
8. Write record to `uploaded_images` collection
9. Return image record
```

**Response `201`:**
```json
{
  "image_id": "img_abc123",
  "url": "https://cdn.convex.dev/img/img_abc123.jpg",
  "face_verified": true,
  "face_verification_score": 0.97,
  "hair_bounding_box": {
    "x": 142,
    "y": 34,
    "width": 210,
    "height": 180
  },
  "hair_segmentation_confidence": 0.88,
  "image_metadata": {
    "original_width": 1080,
    "original_height": 1920,
    "processed_width": 1080,
    "processed_height": 1920,
    "format": "JPEG"
  },
  "created_at": "2026-08-11T11:00:00Z"
}
```

**Error responses:**

| Code | Error key | Trigger |
|---|---|---|
| `400` | `CONSENT_REQUIRED` | `consent_given` is false |
| `415` | `UNSUPPORTED_FORMAT` | File is not JPEG/PNG/WEBP |
| `413` | `FILE_TOO_LARGE` | Exceeds `max_image_size_mb` |
| `422` | `FACE_NOT_DETECTED` | Neither OpenCV nor Gemini detects a face |
| `422` | `MULTIPLE_FACES` | More than one face detected |
| `422` | `IMAGE_QUALITY_LOW` | Gemini score below threshold |
| `422` | `IMAGE_TOO_SMALL` | Below minimum dimension |

---

#### `GET /api/v1/images`
List all uploaded images for the current user.

**Auth:** Bearer JWT  
**Query params:** `limit` (default 20), `cursor` (pagination)

**Response `200`:**
```json
{
  "images": [
    {
      "image_id": "img_abc123",
      "url": "https://cdn.convex.dev/...",
      "face_verified": true,
      "hair_bounding_box": { "x": 142, "y": 34, "width": 210, "height": 180 },
      "created_at": "2026-08-11T11:00:00Z"
    }
  ],
  "next_cursor": "cursor_xyz",
  "total": 5
}
```

---

#### `GET /api/v1/images/{image_id}`
Get details of a single uploaded image.

**Auth:** Bearer JWT (owner only)

**Response `200`:** Same structure as single image object above.

---

#### `DELETE /api/v1/images/{image_id}`
Soft-delete an uploaded image and all associated generated previews.

**Auth:** Bearer JWT (owner only)

**Response `200`:**
```json
{ "deleted": true, "affected_previews": 3 }
```

---

#### `POST /api/v1/images/{image_id}/re-segment`
Re-run the hair segmentation pipeline on an already-uploaded image (e.g., if initial segmentation failed or user requests a retry).

**Auth:** Bearer JWT (owner only)

**Response `200`:**
```json
{
  "hair_bounding_box": { "x": 145, "y": 36, "width": 208, "height": 177 },
  "hair_segmentation_confidence": 0.91
}
```

---

### 8.3 Hairstyle Catalog

#### `GET /api/v1/hairstyles`
Browse the hairstyle catalog with optional filtering and search.

**Auth:** Optional (public endpoint)  
**Query params:**

| Param | Type | Notes |
|---|---|---|
| `q` | string | Natural-language / partial name search |
| `category` | string | e.g., `"Fades"` |
| `hair_length` | string | `"short"` \| `"medium"` \| `"long"` |
| `hair_texture` | string[] | e.g., `["coily"]` |
| `maintenance_level` | string | `"low"` \| `"medium"` \| `"high"` |
| `limit` | int | Default 20, max 100 |
| `cursor` | string | Pagination cursor |

**Response `200`:**
```json
{
  "hairstyles": [
    {
      "hairstyle_id": "hs_xyz",
      "name": "Low Fade",
      "slug": "low-fade",
      "description": "A clean taper that fades from short...",
      "category": "Fades",
      "hair_length": "short",
      "hair_texture": ["straight", "wavy", "coily"],
      "maintenance_level": "low",
      "styling_time_minutes": 30,
      "reference_images": [
        "https://cdn.convex.dev/ref/low-fade-1.jpg"
      ],
      "tags": ["fade", "short", "clean", "taper"]
    }
  ],
  "next_cursor": "cursor_abc",
  "total": 120
}
```

---

#### `GET /api/v1/hairstyles/categories`
Return all available hairstyle categories.

**Auth:** None

**Response `200`:**
```json
{
  "categories": [
    "Fades", "Tapers", "Buzz Cuts", "Afros", "Braids",
    "Cornrows", "Locs", "Twists", "Bobs", "Pixie Cuts",
    "Undercuts", "Waves", "Curls", "Natural Hairstyles",
    "Protective Hairstyles"
  ]
}
```

---

#### `GET /api/v1/hairstyles/{hairstyle_id}`
Get full details for a single hairstyle including related styles.

**Auth:** None

**Response `200`:**
```json
{
  "hairstyle_id": "hs_xyz",
  "name": "Low Fade",
  "slug": "low-fade",
  "description": "...",
  "category": "Fades",
  "hair_length": "short",
  "hair_texture": ["straight", "wavy", "coily"],
  "maintenance_level": "low",
  "styling_time_minutes": 30,
  "reference_images": ["https://cdn.convex.dev/..."],
  "tags": ["fade", "clean"],
  "related_hairstyles": [
    { "hairstyle_id": "hs_abc", "name": "Mid Fade", "slug": "mid-fade" }
  ]
}
```

---

### 8.4 AI Hairstyle Visualization (Previews)

#### `POST /api/v1/previews/generate`
Trigger an AI hairstyle visualization. The uploaded image must have already passed face verification.

**Auth:** Bearer JWT

**Request body:**
```json
{
  "image_id": "img_abc123",
  "hairstyle_id": "hs_xyz"
}
```

**Validation:**
- `image_id` must belong to the requesting user.
- `image_id.face_verified` must be `true`.
- `hairstyle_id` must be an active hairstyle.
- Image must not be soft-deleted.

**Processing flow:**
```
1. Validate ownership and face verification status
2. Create `generated_previews` record with status = "pending"
3. Return 202 immediately with preview_id
4. Background task:
   a. Set status = "processing"
   b. Retrieve image from Convex Storage
   c. Retrieve hairstyle reference images
   d. Call AI generator with (image, hair_bounding_box, hairstyle)
   e. Store result image to Convex Storage
   f. Update preview record: status = "completed", result_url
   g. Trigger notification to user
```

**Response `202`:**
```json
{
  "preview_id": "prev_abc",
  "status": "pending",
  "hairstyle_id": "hs_xyz",
  "hairstyle_name": "Low Fade",
  "image_id": "img_abc123",
  "created_at": "2026-08-11T11:00:00Z"
}
```

---

#### `GET /api/v1/previews/{preview_id}`
Poll for the status and result of a generated preview.

**Auth:** Bearer JWT (owner only)

**Response `200`:**
```json
{
  "preview_id": "prev_abc",
  "status": "completed",
  "hairstyle_id": "hs_xyz",
  "hairstyle_name": "Low Fade",
  "image_id": "img_abc123",
  "result_url": "https://cdn.convex.dev/gen/prev_abc.jpg",
  "generation_time_ms": 8420,
  "ai_provider": "gemini",
  "created_at": "2026-08-11T11:00:00Z"
}
```

**Status values:** `pending` → `processing` → `completed` | `failed`

---

#### `GET /api/v1/previews`
List all generated previews for the current user.

**Auth:** Bearer JWT  
**Query params:** `image_id` (filter by source photo), `hairstyle_id`, `status`, `limit`, `cursor`

**Response `200`:**
```json
{
  "previews": [
    {
      "preview_id": "prev_abc",
      "status": "completed",
      "hairstyle_id": "hs_xyz",
      "hairstyle_name": "Low Fade",
      "result_url": "https://cdn.convex.dev/gen/prev_abc.jpg",
      "created_at": "2026-08-11T11:00:00Z"
    }
  ],
  "next_cursor": null,
  "total": 7
}
```

---

#### `POST /api/v1/previews/{preview_id}/retry`
Retry a failed preview generation.

**Auth:** Bearer JWT (owner only)

**Condition:** `status` must be `"failed"`.

**Response `202`:**
```json
{
  "preview_id": "prev_abc",
  "status": "pending",
  "retried_at": "2026-08-11T11:05:00Z"
}
```

---

#### `DELETE /api/v1/previews/{preview_id}`
Delete a generated preview (soft delete).

**Auth:** Bearer JWT (owner only)

**Response `200`:**
```json
{ "deleted": true }
```

---

### 8.5 Hairstyle Comparison

#### `POST /api/v1/comparisons`
Create a comparison session from multiple preview IDs.

**Auth:** Bearer JWT

**Request body:**
```json
{
  "preview_ids": ["prev_abc", "prev_def", "prev_ghi"]
}
```

**Validation:** 2–6 previews, all must belong to the user and have status `"completed"`.

**Response `201`:**
```json
{
  "comparison_id": "cmp_123",
  "previews": [
    {
      "preview_id": "prev_abc",
      "hairstyle_name": "Low Fade",
      "result_url": "https://cdn.convex.dev/gen/prev_abc.jpg"
    },
    {
      "preview_id": "prev_def",
      "hairstyle_name": "Mid Fade",
      "result_url": "https://cdn.convex.dev/gen/prev_def.jpg"
    }
  ],
  "created_at": "2026-08-11T11:00:00Z"
}
```

---

#### `POST /api/v1/comparisons/{comparison_id}/select`
Mark a preferred preview within a comparison.

**Auth:** Bearer JWT

**Request body:**
```json
{
  "selected_preview_id": "prev_abc"
}
```

**Response `200`:**
```json
{
  "comparison_id": "cmp_123",
  "selected_preview_id": "prev_abc",
  "selected_hairstyle_name": "Low Fade"
}
```

---

### 8.6 Saved Hairstyles & Collections

#### `POST /api/v1/saved`
Save a hairstyle catalog entry or a generated preview to a named collection.

**Auth:** Bearer JWT

**Request body:**
```json
{
  "hairstyle_id": "hs_xyz",
  "generated_preview_id": "prev_abc",
  "collection_name": "Next haircut",
  "notes": "Ask for this on Saturday"
}
```

*(At least one of `hairstyle_id` or `generated_preview_id` required)*

**Response `201`:**
```json
{
  "saved_id": "sv_abc",
  "hairstyle_id": "hs_xyz",
  "hairstyle_name": "Low Fade",
  "generated_preview_id": "prev_abc",
  "collection_name": "Next haircut",
  "notes": "Ask for this on Saturday",
  "created_at": "2026-08-11T11:00:00Z"
}
```

---

#### `GET /api/v1/saved`
List all saved hairstyles for the current user.

**Auth:** Bearer JWT  
**Query params:** `collection` (filter by collection name), `limit`, `cursor`

**Response `200`:**
```json
{
  "collections": {
    "Next haircut": [
      {
        "saved_id": "sv_abc",
        "hairstyle_id": "hs_xyz",
        "hairstyle_name": "Low Fade",
        "result_url": "https://cdn.convex.dev/gen/prev_abc.jpg",
        "notes": "Ask for this on Saturday",
        "created_at": "2026-08-11T11:00:00Z"
      }
    ],
    "Styles to try": []
  }
}
```

---

#### `DELETE /api/v1/saved/{saved_id}`
Remove a saved hairstyle.

**Auth:** Bearer JWT (owner only)

**Response `200`:**
```json
{ "deleted": true }
```

---

#### `GET /api/v1/saved/collections`
Return the list of collection names the user has created.

**Auth:** Bearer JWT

**Response `200`:**
```json
{
  "collections": ["Next haircut", "Styles to try", "Wedding hairstyles"]
}
```

---

### 8.7 Hairstyle Recommendations

#### `GET /api/v1/recommendations`
Get recommended hairstyles based on user preferences and optionally a reference image.

**Auth:** Bearer JWT  
**Query params:**

| Param | Type | Notes |
|---|---|---|
| `image_id` | string | Use this image's bounding box / metadata as input |
| `current_hair_length` | string | `"short"` \| `"medium"` \| `"long"` |
| `desired_hair_length` | string | |
| `hair_texture` | string | |
| `maintenance_preference` | string | `"low"` \| `"medium"` \| `"high"` |
| `category` | string | Preferred category |
| `limit` | int | Default 10 |

**Response `200`:**
```json
{
  "recommendations": [
    {
      "hairstyle_id": "hs_xyz",
      "name": "Low Fade",
      "relevance_score": 0.91,
      "reason": "Matches your preferred low maintenance level and short hair length",
      "reference_images": ["https://cdn.convex.dev/..."]
    }
  ],
  "disclaimer": "These are suggestions only and are not a definitive judgment on which hairstyle is suitable for you."
}
```

---

### 8.8 Sharing

#### `POST /api/v1/share`
Generate a shareable link for a generated preview.

**Auth:** Bearer JWT

**Request body:**
```json
{
  "preview_id": "prev_abc",
  "expires_in_hours": 72
}
```

**Response `201`:**
```json
{
  "share_id": "shr_abc",
  "share_url": "https://app.example.com/share/shr_abc",
  "preview_id": "prev_abc",
  "hairstyle_name": "Low Fade",
  "expires_at": "2026-08-14T11:00:00Z"
}
```

---

#### `GET /api/v1/share/{share_id}`
Resolve a share link and return the preview. **Public endpoint** — no auth required.

**Response `200`:**
```json
{
  "hairstyle_name": "Low Fade",
  "hairstyle_description": "...",
  "result_url": "https://cdn.convex.dev/gen/prev_abc.jpg",
  "reference_images": ["https://cdn.convex.dev/ref/low-fade-1.jpg"],
  "expires_at": "2026-08-14T11:00:00Z"
}
```

**Error `410` — LINK_EXPIRED** if past `expires_at`.

---

#### `POST /api/v1/share/{share_id}/download`
Return a signed download URL for the generated image.

**Auth:** None (public)

**Response `200`:**
```json
{
  "download_url": "https://cdn.convex.dev/gen/prev_abc.jpg?token=...",
  "filename": "hairstyle-low-fade-preview.jpg",
  "expires_in_seconds": 300
}
```

---

### 8.9 Stylist Consultation

#### `POST /api/v1/consultations`
Start a new customer consultation.

**Auth:** Bearer JWT (stylist or admin)

**Request body:**
```json
{
  "customer_id": "jd7x9...",
  "customer_name": "Walk-in Customer"
}
```

*(Either `customer_id` for registered users OR `customer_name` for walk-ins)*

**Response `201`:**
```json
{
  "consultation_id": "con_abc",
  "stylist_id": "st_xyz",
  "customer_id": "jd7x9...",
  "customer_name": null,
  "status": "active",
  "created_at": "2026-08-11T11:00:00Z"
}
```

---

#### `POST /api/v1/consultations/{consultation_id}/upload-photo`
Upload the customer's photo within a consultation session (requires explicit consent).

**Auth:** Bearer JWT (stylist or admin)  
**Content-Type:** `multipart/form-data`

**Form fields:** Same as `POST /api/v1/images/upload` + `customer_consent: boolean`.

**Response `201`:** Same as `POST /api/v1/images/upload`.

---

#### `POST /api/v1/consultations/{consultation_id}/generate`
Generate a hairstyle preview within a consultation.

**Auth:** Bearer JWT (stylist or admin)

**Request body:**
```json
{
  "image_id": "img_abc123",
  "hairstyle_id": "hs_xyz"
}
```

**Response `202`:** Same as `POST /api/v1/previews/generate`.

---

#### `POST /api/v1/consultations/{consultation_id}/select-style`
Record the customer's selected hairstyle for the consultation.

**Auth:** Bearer JWT (stylist or admin)

**Request body:**
```json
{
  "hairstyle_id": "hs_xyz",
  "preview_id": "prev_abc",
  "notes": "Customer wants slightly longer on top"
}
```

**Response `200`:**
```json
{
  "consultation_id": "con_abc",
  "selected_hairstyle_id": "hs_xyz",
  "selected_preview_id": "prev_abc",
  "notes": "Customer wants slightly longer on top"
}
```

---

#### `POST /api/v1/consultations/{consultation_id}/share-with-customer`
Share the selected hairstyle preview with the linked customer.

**Auth:** Bearer JWT (stylist or admin)

**Response `200`:**
```json
{
  "share_url": "https://app.example.com/share/shr_def",
  "share_id": "shr_def",
  "sent_to_customer": true
}
```

---

#### `PATCH /api/v1/consultations/{consultation_id}`
Update consultation status or notes.

**Auth:** Bearer JWT (stylist or admin)

**Request body:**
```json
{
  "status": "completed",
  "notes": "Customer very happy with the Low Fade result"
}
```

**Response `200`:**
```json
{ "updated": true }
```

---

#### `GET /api/v1/consultations`
List consultations for the current stylist.

**Auth:** Bearer JWT (stylist or admin)  
**Query params:** `status`, `limit`, `cursor`

**Response `200`:**
```json
{
  "consultations": [
    {
      "consultation_id": "con_abc",
      "customer_id": "jd7x9...",
      "customer_name": null,
      "selected_hairstyle_name": "Low Fade",
      "status": "completed",
      "created_at": "2026-08-11T11:00:00Z"
    }
  ],
  "next_cursor": null,
  "total": 14
}
```

---

#### `GET /api/v1/consultations/{consultation_id}`
Get full details of a single consultation.

**Auth:** Bearer JWT (stylist who owns it, or admin)

**Response `200`:** Full consultation object with linked previews and hairstyle.

---

### 8.10 Notifications

#### `GET /api/v1/notifications/preferences`
Get the current user's notification preferences.

**Auth:** Bearer JWT

**Response `200`:**
```json
{
  "generation_complete": true,
  "generation_failed": true,
  "stylist_share": true,
  "consultation_update": true,
  "saved_hairstyle_update": false
}
```

---

#### `PATCH /api/v1/notifications/preferences`
Update notification preferences.

**Auth:** Bearer JWT

**Request body:**
```json
{
  "generation_complete": false
}
```

**Response `200`:**
```json
{ "updated": true }
```

---

### 8.11 Admin — User Management

All admin routes require `role = "admin"`.

#### `GET /api/v1/admin/users`
List all users.

**Query params:** `role`, `is_active`, `q` (name/email search), `limit`, `cursor`

**Response `200`:**
```json
{
  "users": [
    {
      "convex_user_id": "jd7x9...",
      "email": "jane@example.com",
      "full_name": "Jane Doe",
      "role": "customer",
      "is_active": true,
      "created_at": "2026-08-11T11:00:00Z"
    }
  ],
  "total": 1042
}
```

---

#### `GET /api/v1/admin/users/{user_id}`
Get full profile of a specific user.

---

#### `PATCH /api/v1/admin/users/{user_id}/suspend`
Suspend a user account.

**Request body:**
```json
{ "reason": "Terms of service violation" }
```

**Response `200`:**
```json
{ "suspended": true }
```

*(Logs to `audit_logs`)*

---

#### `PATCH /api/v1/admin/users/{user_id}/reactivate`
Reactivate a suspended user.

**Response `200`:**
```json
{ "reactivated": true }
```

---

### 8.12 Admin — Hairstyle Catalog Management

#### `POST /api/v1/admin/hairstyles`
Create a new hairstyle.

**Auth:** Bearer JWT (admin)  
**Content-Type:** `multipart/form-data`

**Form fields:**

| Field | Type |
|---|---|
| `name` | string |
| `description` | string |
| `category` | string |
| `hair_length` | string |
| `hair_texture` | string[] (JSON) |
| `maintenance_level` | string |
| `styling_time_minutes` | int |
| `tags` | string[] (JSON) |
| `related_hairstyle_ids` | string[] (JSON) |
| `reference_images` | file[] (1–10 images) |

**Response `201`:**
```json
{
  "hairstyle_id": "hs_new",
  "name": "Bantu Knots",
  "slug": "bantu-knots",
  "created_at": "2026-08-11T11:00:00Z"
}
```

---

#### `PUT /api/v1/admin/hairstyles/{hairstyle_id}`
Update an existing hairstyle (full update).

**Response `200`:** Full hairstyle object.

---

#### `PATCH /api/v1/admin/hairstyles/{hairstyle_id}`
Partial update (e.g., toggle `is_active`, update description).

**Response `200`:**
```json
{ "updated": true }
```

---

#### `DELETE /api/v1/admin/hairstyles/{hairstyle_id}`
Deactivate a hairstyle (soft delete, preserves existing previews).

**Response `200`:**
```json
{ "deactivated": true }
```

---

#### `POST /api/v1/admin/hairstyles/{hairstyle_id}/reference-images`
Add additional reference images to an existing hairstyle.

**Content-Type:** `multipart/form-data`, field: `images` (file[])

**Response `200`:**
```json
{
  "added_images": ["https://cdn.convex.dev/ref/..."],
  "total_reference_images": 5
}
```

---

#### `DELETE /api/v1/admin/hairstyles/{hairstyle_id}/reference-images/{image_url_encoded}`
Remove a specific reference image.

**Response `200`:**
```json
{ "removed": true }
```

---

### 8.13 Admin — AI Operations

#### `GET /api/v1/admin/ai/stats`
Get AI generation statistics.

**Auth:** Bearer JWT (admin)

**Response `200`:**
```json
{
  "period": "last_7_days",
  "total_generations": 4210,
  "completed": 4108,
  "failed": 102,
  "success_rate": 0.976,
  "average_generation_time_ms": 7840,
  "p95_generation_time_ms": 14200,
  "by_provider": {
    "gemini": { "total": 4210, "failed": 102 }
  }
}
```

---

#### `GET /api/v1/admin/ai/failed-previews`
List recently failed generations for review.

**Query params:** `limit`, `cursor`, `from_date`, `to_date`

**Response `200`:**
```json
{
  "failed_previews": [
    {
      "preview_id": "prev_fail",
      "user_id": "jd7x9...",
      "hairstyle_name": "Afro",
      "error_message": "AI provider timeout",
      "created_at": "2026-08-11T10:00:00Z"
    }
  ]
}
```

---

#### `GET /api/v1/admin/ai/config`
Get current AI provider configuration.

**Response `200`:**
```json
{
  "active_provider": "gemini",
  "generation_timeout_seconds": 120,
  "available_providers": ["gemini"]
}
```

---

#### `PATCH /api/v1/admin/ai/config`
Update AI provider configuration.

**Request body:**
```json
{
  "active_provider": "gemini",
  "generation_timeout_seconds": 90
}
```

**Response `200`:**
```json
{ "updated": true }
```

---

### 8.14 Admin — Analytics

#### `GET /api/v1/admin/analytics/overview`
High-level platform analytics.

**Auth:** Bearer JWT (admin)  
**Query params:** `period` (`"7d"` | `"30d"` | `"90d"`)

**Response `200`:**
```json
{
  "period": "30d",
  "active_users": 3204,
  "new_registrations": 841,
  "total_photos_uploaded": 5102,
  "total_previews_generated": 18840,
  "ai_success_rate": 0.976,
  "hairstyles_saved": 6720,
  "hairstyles_shared": 1430,
  "average_previews_per_user": 5.9,
  "top_hairstyles": [
    { "hairstyle_id": "hs_xyz", "name": "Low Fade", "generation_count": 2840 }
  ],
  "active_stylists": 120,
  "total_consultations": 380
}
```

---

## 9. PYDANTIC SCHEMAS SUMMARY

Key schemas (abbreviated):

```python
# app/schemas/image.py
class ImageUploadResponse(BaseModel):
    image_id: str
    url: str
    face_verified: bool
    face_verification_score: float | None
    hair_bounding_box: BoundingBox | None
    hair_segmentation_confidence: float | None
    image_metadata: ImageMetadata
    created_at: datetime

class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int

class ImageMetadata(BaseModel):
    original_width: int
    original_height: int
    processed_width: int
    processed_height: int
    format: str

# app/schemas/preview.py
class PreviewGenerateRequest(BaseModel):
    image_id: str
    hairstyle_id: str

class PreviewResponse(BaseModel):
    preview_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    hairstyle_id: str
    hairstyle_name: str
    image_id: str
    result_url: str | None = None
    generation_time_ms: int | None = None
    ai_provider: str | None = None
    error_message: str | None = None
    created_at: datetime

# app/schemas/hairstyle.py
class HairstyleResponse(BaseModel):
    hairstyle_id: str
    name: str
    slug: str
    description: str
    category: str
    hair_length: Literal["short", "medium", "long"]
    hair_texture: list[str]
    maintenance_level: Literal["low", "medium", "high"]
    styling_time_minutes: int
    reference_images: list[str]
    tags: list[str]
    related_hairstyles: list[RelatedHairstyle]
```

---

## 10. AI GENERATION ABSTRACTION LAYER

The AI generator is abstracted behind an interface to allow the underlying model to be swapped without changing application code.

```python
# app/ai/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class GenerationInput:
    image_bytes: bytes
    hairstyle_reference_images: list[bytes]
    hair_bounding_box: dict  # {x, y, width, height}
    hairstyle_name: str
    hairstyle_description: str

@dataclass
class GenerationOutput:
    result_image_bytes: bytes
    generation_time_ms: int
    provider: str
    metadata: dict

class HairstyleGenerator(ABC):
    @abstractmethod
    async def generate(self, input: GenerationInput) -> GenerationOutput:
        ...
```

The active generator is injected via `app/dependencies.py` based on `settings.ai_provider`. Adding a new provider requires only a new concrete class implementing `HairstyleGenerator`.

---

## 11. SECURITY REQUIREMENTS

| Requirement | Implementation |
|---|---|
| JWT Verification | Clerk JWKS endpoint, cached public keys, RS256 |
| Role-based access | FastAPI `Depends` guards per route |
| Photo access control | Images served only via user-owned tokens; Convex storage policies |
| Consent enforcement | `consent_given = true` validated before storing any image |
| Soft deletes | Images and previews are soft-deleted; hard delete available to users via explicit request |
| Rate limiting | Per-user and per-IP limits on upload and generation endpoints (middleware) |
| CORS | Configured to allowed mobile app origins only |
| Audit logging | All admin-level mutations logged to `audit_logs` |
| Data in transit | HTTPS enforced; internal Convex communication uses TLS |
| No raw key storage | All sensitive tokens handled via Clerk/Convex; no raw user PII stored beyond what's needed |

---

## 12. ERROR CODES REFERENCE

| Error Key | HTTP | Meaning |
|---|---|---|
| `UNAUTHORIZED` | 401 | Missing or invalid Clerk JWT |
| `FORBIDDEN` | 403 | Authenticated but insufficient role |
| `NOT_FOUND` | 404 | Resource not found |
| `CONSENT_REQUIRED` | 400 | `consent_given` was not `true` |
| `UNSUPPORTED_FORMAT` | 415 | Image format not accepted |
| `FILE_TOO_LARGE` | 413 | Upload exceeds size limit |
| `IMAGE_TOO_SMALL` | 422 | Image below minimum dimensions |
| `FACE_NOT_DETECTED` | 422 | No human face found by either OpenCV or Gemini |
| `MULTIPLE_FACES` | 422 | More than one face detected |
| `IMAGE_QUALITY_LOW` | 422 | Gemini quality score below threshold |
| `FACE_NOT_VERIFIED` | 422 | Attempting to generate preview on unverified image |
| `PREVIEW_NOT_FAILED` | 422 | Retry requested on non-failed preview |
| `LINK_EXPIRED` | 410 | Share link has passed expiry |
| `GENERATION_TIMEOUT` | 504 | AI provider did not respond in time |
| `AI_PROVIDER_ERROR` | 502 | Upstream AI generation service error |
| `COMPARISON_LIMIT` | 422 | More than 6 previews in a comparison |
| `INVALID_COMPARISON` | 422 | Preview not owned by user or not completed |
| `CONSULTATION_ACCESS` | 403 | Stylist does not own this consultation |

---

## 13. TESTING & QA PLAN

### 13.1 Unit Tests

- Clerk JWT verification (valid, expired, tampered)
- Face verification pipeline (OpenCV path, Gemini fallback, multi-face rejection)
- Hair segmentation bounding box computation
- Image preprocessing (format rejection, resize, EXIF fix)
- Pydantic schema validation (all request/response models)
- AI generator abstraction (mock provider)

### 13.2 Integration Tests

- Full upload → verify → segment → generate → poll flow
- Multi-hairstyle previews from single uploaded image
- Stylist consultation end-to-end
- Share link creation → public resolution → download
- Admin suspend user → user cannot access protected routes
- Admin add hairstyle → visible in catalog

### 13.3 Load Tests (Locust)

| Scenario | Target |
|---|---|
| Catalog browse | 200 RPS |
| Image upload + face verify | 50 RPS |
| Preview generation (trigger) | 100 RPS |
| Preview poll | 500 RPS |
| Comparison create | 20 RPS |

### 13.4 Security Tests

- Attempt to access another user's image → 403
- Attempt to generate preview on unverified image → 422
- Expired share link → 410
- Admin endpoint without admin role → 403
- Upload image without `consent_given` → 400

---

## 14. DELIVERY MILESTONES

| Milestone | Deliverables | Timeline |
|---|---|---|
| **M1 – Project Setup** | uv project, FastAPI skeleton, Convex schema, `.env` config | 2 days |
| **M2 – Auth** | Clerk JWT middleware, user sync, role-based guards | 3 days |
| **M3 – Image Upload & Vision** | Upload endpoint, OpenCV face detection, Gemini fallback, hair segmentation | 5 days |
| **M4 – Hairstyle Catalog** | Catalog CRUD (admin), search/filter, public browse | 3 days |
| **M5 – AI Preview Generation** | Background generation task, polling endpoint, retry logic | 5 days |
| **M6 – Saved Hairstyles & Collections** | Save/remove/organize endpoints | 2 days |
| **M7 – Comparison & Recommendations** | Comparison session, selection, recommendation engine | 3 days |
| **M8 – Stylist Consultation** | Full consultation workflow endpoints | 3 days |
| **M9 – Sharing** | Share link creation, public resolution, download URL | 2 days |
| **M10 – Admin Dashboard API** | User management, catalog management, AI ops, analytics | 4 days |
| **M11 – Notifications** | Preferences management, notification dispatch hooks | 2 days |
| **M12 – Testing & QA** | Unit, integration, load, security tests | 5 days |

**Total: ~39 engineering days**

---

## 15. NORTH-STAR METRIC

> **Successful Hairstyle Visualizations**
>
> The number of users who upload a verified photo AND successfully receive a completed AI hairstyle preview.
>
> Tracked per day / week / month via `generated_previews` where `status = "completed"`.
