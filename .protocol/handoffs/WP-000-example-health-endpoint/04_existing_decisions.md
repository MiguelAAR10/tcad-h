# 04 — Existing Decisions

## Architecture decisions

- Each feature lives under `backend/app/routers/<name>.py` (Journal 2026-05-12-009).
- Routers are registered in `backend/app/routers/__init__.py` via an explicit list.
- The application factory (`create_app` in `main.py`) calls the registration function.

## Library and framework choices

- FastAPI is the only HTTP framework. Do not add Flask, Starlette directly, or alternatives.
- Pydantic v2 for response models. Use a `BaseModel` even for trivial responses
  to keep OpenAPI accurate.

## Naming and style

- Module file: lowercase, no plural. `health.py`, not `Health.py` or `healths.py`.
- Router variable: `router = APIRouter(prefix="", tags=["health"])`.
- Test module: `test_<feature>.py` mirroring the production module name.
- Commit message format: `feat(health): description` (Angular convention).

## Reuse expectations

- Use the existing `TestClient` fixture in `backend/tests/unit/conftest.py` named `client`.
- Do not create a new conftest. Do not duplicate the FastAPI app instance.

## Contract preservation

- The auth middleware uses `PUBLIC_PATHS` from `backend/app/config.py` to exempt
  endpoints. If `/health` is not exempted by default, the test will fail with
  401 — surface this in `12_delta.md` rather than editing the middleware.
- Response body shape `{"status": "ok"}` is locked. Do not add extra fields.
  Adding fields (e.g., `version`, `uptime_seconds`) is a separate WP.
