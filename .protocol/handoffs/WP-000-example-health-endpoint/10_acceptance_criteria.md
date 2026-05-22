# 10 — Acceptance Criteria

## Functional criteria

- [ ] AC-1 — `GET /health` returns HTTP 200.
  - Verified by: `test_health_returns_200_ok` in `backend/tests/unit/test_health.py`
- [ ] AC-2 — Response body equals `{"status": "ok"}` exactly.
  - Verified by: `test_health_response_shape`
- [ ] AC-3 — Endpoint does not require authentication.
  - Verified by: `test_health_does_not_require_auth` (sends request without Authorization header, expects 200)
- [ ] AC-4 — Endpoint does not perform I/O or external calls.
  - Verified by: code inspection in `14_review_result.md` (handler body has no DB / network / logger calls)

## Non-regression criteria

- [ ] All previously passing tests still pass: `pytest -q` exits 0.
- [ ] No file outside `02_allowed_files.md` was modified.
  - Verified by: `git diff --name-only main..HEAD` matches the allow list.

## Quality criteria

- [ ] No new dependencies in `pyproject.toml` or `requirements.txt`.
- [ ] No `print()`, `breakpoint()`, or `TODO` introduced.
- [ ] Pydantic v2 syntax used (no `BaseModel.dict()` legacy calls).

## Documentation criteria

- [ ] `11_worker_summary.md` exists and follows the OPENCODE.md format.
- [ ] Each AC-N above is mapped to a specific test name in `11_worker_summary.md`.

## Commands used to verify

```
git diff --name-only main..HEAD
pytest backend/tests/unit/test_health.py -v
pytest -q
```

Reviewer must run these three commands and paste the results into
`14_review_result.md` under `CHECKS:`.
