# Backend Engineering Rules

## Project

AI Hairstyle & Haircut Visualization Platform Backend.

## Stack

* Python
* FastAPI
* uv
* Pydantic v2
* Clerk
* Convex
* OpenCV
* Gemini
* Pillow

## Rules

1. Read the Technical Requirements Document before implementing a feature.
2. Do not implement multiple unrelated features in one task.
3. Inspect the existing code before modifying it.
4. Explain the implementation plan before making substantial changes.
5. Keep route handlers thin.
6. Put business logic in services.
7. Keep database access behind repository abstractions where practical.
8. Use Pydantic models for API input and output.
9. Never hardcode secrets.
10. Never commit `.env`.
11. Never trust client-supplied roles.
12. Always enforce resource ownership.
13. External services must be mockable in tests.
14. Do not use real AI services in ordinary unit tests.
15. Do not delete tests simply to make them pass.
16. Do not claim a feature works unless it has been tested.
17. After implementation, report exactly what was changed and which tests passed.