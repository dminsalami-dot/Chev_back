import logging
import time
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from chevstyle_backend.config import settings

# Routers
from chevstyle_backend.routers.auth import router as auth_router
from chevstyle_backend.routers.images import router as images_router
from chevstyle_backend.routers.hairstyles import router as hairstyles_router
from chevstyle_backend.routers.saved_styles import router as saved_styles_router
from chevstyle_backend.routers.previews import router as previews_router

# Setup logger
logger = logging.getLogger("chevstyle_backend")
logger.setLevel(logging.INFO)

# If handlers are empty, configure standard stderr handler to output logs to terminal
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(levelname)s:     %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

app = FastAPI(title=settings.app_name, debug=settings.app_debug)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path
        logger.info(f"Incoming request: {method} {path}")
        
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration = (time.perf_counter() - start_time) * 1000
            
            if response.status_code >= 400:
                logger.error(
                    f"Request failed: {method} {path} - Status: {response.status_code} - Duration: {duration:.2f}ms"
                )
            else:
                logger.info(
                    f"Request successful: {method} {path} - Status: {response.status_code} - Duration: {duration:.2f}ms"
                )
            return response
        except Exception as exc:
            duration = (time.perf_counter() - start_time) * 1000
            logger.exception(
                f"Unhandled exception during {method} {path} - Duration: {duration:.2f}ms - Error: {str(exc)}"
            )
            raise exc


app.add_middleware(LoggingMiddleware)

app.include_router(auth_router)
app.include_router(images_router)
app.include_router(hairstyles_router)
app.include_router(saved_styles_router)
app.include_router(previews_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Welcome to Chevstyle API", "status": "running"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
