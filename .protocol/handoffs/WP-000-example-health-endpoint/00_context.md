# 00 — Context

## Project at a glance

Hypothetical FastAPI backend serving an internal analytics dashboard. Deployed
on Fly.io behind a load balancer that runs HTTP health probes every 10 seconds.
This is an example Work Package illustrating how a real WP looks once filled in.

## Active spec

`specs/007-uptime-probes/spec.md` — "Provide an HTTP endpoint usable by external
uptime probes (Fly.io, StatusCake) without coupling to internal auth middleware."

## Related prior work

- `.protocol/journal/2026-05-18-014.md` — Auth middleware was refactored; rejects
  unauthenticated requests with 401. This blocks naive `/health` endpoints.
- `.protocol/journal/2026-05-12-009.md` — Router structure standardized: each
  feature lives under `backend/app/routers/<name>.py`.
- `.protocol/journal/2026-04-30-003.md` — `pytest` config locked: integration
  tests live in `backend/tests/integration/`, unit tests in `backend/tests/unit/`.

## Existing components likely to be reused

- `backend/app/routers/__init__.py` — Router registration central point.
- `backend/app/main.py` — Application factory; includes routers.
- `backend/tests/unit/conftest.py` — Provides a `client` fixture (FastAPI TestClient).

## Contracts that must not break

- `backend/app/auth/middleware.py` — Public middleware contract; do not modify.
  The new endpoint must be registered BEFORE auth middleware, or the middleware
  must explicitly exempt the new path.

## Reuse score

`reuse_score: 0.78`

(High reuse: existing router pattern, existing test fixture, existing app factory.
The only new code is one router file plus one test file.)
