CHANGED FILES:
- backend/app/routers/health.py (created)
- backend/tests/unit/test_health.py (created)

TESTS RUN:
- pytest backend/tests/unit/test_health.py -v (3 passed)

WHAT PASSED:
- test_health_returns_200_ok
- test_health_response_shape
- test_health_does_not_require_auth

WHAT FAILED:
- none

DECISIONS MADE:
- Followed naming convention from existing routers/__init__.py.
- Did not modify auth middleware (deferred per existing_decisions).

RISKS:
- /health not added to PUBLIC_PATHS — may fail in prod if middleware rejects.

NEXT STEP: ready for review
