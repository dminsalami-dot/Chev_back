from fastapi import Header, Depends, HTTPException
from chevstyle_backend.auth.clerk import verify_clerk_jwt
from chevstyle_backend.auth.models import ClerkUser


async def get_current_user(authorization: str = Header(...)) -> ClerkUser:
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
