# Chevstyle Backend

This repository contains the initial backend foundation for the Chevstyle platform.

## Setup

Install dependencies with uv:

```bash
uv sync --extra dev
```

## Run the API

Start the FastAPI application locally:

```bash
uv run uvicorn chevstyle_backend.app:app --reload
```

The API exposes a minimal health endpoint at `/health`.

## Run tests

Run the test suite with:

```bash
uv run pytest
```
