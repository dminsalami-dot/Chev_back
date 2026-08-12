import time
from typing import Any

import httpx
from fastapi import HTTPException
from jose import JWTError, jwt

from chevstyle_backend.config import settings
from chevstyle_backend.convex.client import ConvexClient
from .models import ClerkUser


# Simple dev token -> role mapping. Keeps tests deterministic without external JWKS.
_DEV_TOKENS = {
    "test-token": {"clerk_user_id": "user_test", "email": "test@example.com", "role": "customer"},
    "stylist-token": {"clerk_user_id": "user_stylist", "email": "stylist@example.com", "role": "stylist"},
    "admin-token": {"clerk_user_id": "user_admin", "email": "admin@example.com", "role": "admin"},
}

_JWKS_CACHE: dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 300


async def _fetch_jwks() -> dict[str, Any]:
    now = time.time()
    cached_keys = _JWKS_CACHE["keys"]
    if cached_keys and now - _JWKS_CACHE["fetched_at"] < _JWKS_TTL_SECONDS:
        return cached_keys

    if not settings.clerk_jwks_url:
        raise HTTPException(
            status_code=500, detail="Clerk JWKS URL is not configured")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(settings.clerk_jwks_url)
            response.raise_for_status()
            jwks = response.json()
            _JWKS_CACHE["keys"] = jwks
            _JWKS_CACHE["fetched_at"] = now
            return jwks
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="Unable to fetch Clerk JWKS") from exc


def _find_jwk_for_token(token: str, jwks: dict[str, Any]) -> dict[str, Any]:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Invalid token header")

    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    raise HTTPException(status_code=401, detail="Unable to resolve token key")


async def verify_clerk_jwt(token: str) -> ClerkUser:
    if not token:
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")

    # Fast-path dev tokens when Clerk integration is not configured.
    if token in _DEV_TOKENS and not (
        settings.clerk_jwks_url and settings.clerk_issuer and settings.clerk_audience
    ):
        info = _DEV_TOKENS[token]
        user = ClerkUser(
            clerk_user_id=info["clerk_user_id"],
            email=info["email"],
            role=info["role"],
        )

        try:
            convex = ConvexClient()
            convex_id, _, record = convex.upsert_user(
                clerk_user_id=user.clerk_user_id,
                email=user.email,
                role=user.role,
            )
            user.convex_user_id = convex_id
            user.full_name = record.get("full_name")
        except Exception:
            pass

        return user

    if not (settings.clerk_jwks_url and settings.clerk_issuer and settings.clerk_audience):
        raise HTTPException(
            status_code=401, detail="Clerk authentication is not configured")

    jwks = await _fetch_jwks()
    jwk = _find_jwk_for_token(token, jwks)

    try:
        claims = jwt.decode(
            token,
            jwk,
            algorithms=["RS256"],
            audience=settings.clerk_audience,
            issuer=settings.clerk_issuer,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=401, detail="Invalid authentication token") from exc

    clerk_user_id = claims.get("sub")
    email = claims.get("email") or claims.get("email_address")
    full_name = claims.get("name")
    role = claims.get("role", "customer")

    if not clerk_user_id or not email:
        raise HTTPException(
            status_code=401, detail="Invalid Clerk token claims")

    user = ClerkUser(
        clerk_user_id=clerk_user_id,
        email=email,
        role=role,
        full_name=full_name,
    )

    try:
        convex = ConvexClient()
        convex_id, _, record = convex.upsert_user(
            clerk_user_id=clerk_user_id,
            email=email,
            role=role,
            full_name=full_name,
        )
        user.convex_user_id = convex_id
        user.full_name = record.get("full_name")
        user.profile_image_url = record.get("profile_image_url")
        user.notification_prefs = record.get(
            "notification_prefs", user.notification_prefs)
    except Exception:
        pass

    return user
