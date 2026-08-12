from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from chevstyle_backend.auth.clerk import verify_clerk_jwt
from chevstyle_backend.auth.models import ClerkUser

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> ClerkUser:
    if not credentials:
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")
    token = credentials.credentials
    return await verify_clerk_jwt(token)


async def require_stylist(user: ClerkUser = Depends(get_current_user)) -> ClerkUser:
    if user.role not in ("stylist", "admin"):
        raise HTTPException(status_code=403, detail="Stylist access required")
    return user


async def require_admin(user: ClerkUser = Depends(get_current_user)) -> ClerkUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

