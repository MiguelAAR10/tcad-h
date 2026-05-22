# 05 — Worker Prompt: Backend Role

## Role

You are the Backend Worker for WP-000-example-health-endpoint.

## Mandatory reading order

1. `AGENTS.md` at repo root
2. `OPENCODE.md` at repo root
3. This Work Package folder: `00_context.md`, `01_goal.md`, `02_allowed_files.md`,
   `03_forbidden_files.md`, `04_existing_decisions.md`, `10_acceptance_criteria.md`
4. `backend/app/routers/__init__.py` (to learn the registration pattern)
5. `backend/tests/unit/conftest.py` (to learn the `client` fixture)

## Allowed and forbidden

- Edit only paths in `02_allowed_files.md`.
- Never edit paths in `03_forbidden_files.md`.

## Task

1. Create `backend/app/routers/health.py` with:
   - A FastAPI `APIRouter` named `router`.
   - A response model `HealthResponse(BaseModel)` with a single field `status: str`.
   - A `GET /health` endpoint that returns `HealthResponse(status="ok")`.
   - The function should not perform any I/O, database call, or external request.
   - The function should not log per-request (omit any explicit logger call).

2. Register the new router in `backend/app/routers/__init__.py` following the
   existing list pattern. Append, do not reorder.

3. Ensure `backend/app/main.py` already calls the registration helper from
   `routers/__init__.py`. If it does, no change is required. If it does not,
   minimal addition is allowed (this is in your allow list).

4. Create `backend/tests/unit/test_health.py` with at least these tests:
   - `test_health_returns_200_ok`
   - `test_health_response_shape`
   - `test_health_does_not_require_auth`

5. Run the tests and confirm they pass.

## Commands you must run

```
pytest backend/tests/unit/test_health.py -v
pytest -q                              # full unit suite, no regressions
```

## Output

Write `11_worker_summary.md` using exactly the format in `OPENCODE.md` §
"Output format". Map each acceptance criterion in `10_acceptance_criteria.md`
to the test name that verifies it.

## Hard limits

- Do not edit `backend/app/auth/middleware.py`.
- Do not edit `backend/app/config.py` without writing to `12_delta.md` first.
- Do not add a logger or per-request side effect.
- Do not introduce new dependencies.
- Do not change the response shape from `{"status": "ok"}`.
- Keep `11_worker_summary.md` under 400 lines.
