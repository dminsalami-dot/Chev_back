from fastapi import FastAPI

from chevstyle_backend.config import settings

# Routers
from chevstyle_backend.routers.auth import router as auth_router


app = FastAPI(title=settings.app_name, debug=settings.app_debug)


app.include_router(auth_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
