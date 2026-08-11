from fastapi import FastAPI

from chevstyle_backend.config import settings


app = FastAPI(title=settings.app_name, debug=settings.app_debug)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
