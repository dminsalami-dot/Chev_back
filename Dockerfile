# Multi-stage production Dockerfile for FastAPI backend using uv
FROM python:3.13-slim

# Install system dependencies required for OpenCV, MediaPipe, Pillow, and cairosvg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libgomp1 \
    curl \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv by copying binary from official uv image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy dependency definition files first for optimal Docker caching
COPY pyproject.toml uv.lock README.md ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source code
COPY src ./src

# Install project root package
RUN uv sync --frozen --no-dev

# Ensure virtual environment binaries are on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Expose default GCP Cloud Run port
ENV PORT=8080
EXPOSE 8080

# Launch FastAPI app with uvicorn listening on 0.0.0.0:${PORT}
CMD exec uvicorn chevstyle_backend.app:app --host 0.0.0.0 --port ${PORT}
