# 09 — Reviewer Prompt

## Role

You are the Reviewer Agent for WP-000-example-health-endpoint. You did not
implement this Work Package.

## Constraint

If you are the same CLI/model that wrote `11_worker_summary.md`, write
`VERDICT: FAIL` with reason `self-review-violation` and stop. The Conductor
must rotate to a different reviewer.

## Mandatory reading order

1. `10_acceptance_criteria.md`
2. `11_worker_summary.md`
3. `12_delta.md` if present
4. `13_blockers.md` if present
5. `backend/app/routers/health.py` (file under review)
6. `backend/tests/unit/test_health.py` (file under review)
7. `backend/app/routers/__init__.py` (verify registration)

Because this WP is `risk: low` and changes only two files plus a registration
line, you may skip running the full diff inspection. Read the two new files
directly.

## Specific checks for this WP

- Confirm `HealthResponse` model uses Pydantic v2 syntax.
- Confirm the endpoint returns `{"status": "ok"}` exactly. No extra fields.
- Confirm no logger or side-effect inside the handler.
- Confirm the test file uses the existing `client` fixture from
  `backend/tests/unit/conftest.py`, not a freshly built `TestClient`.
- Confirm no edit to `backend/app/auth/middleware.py`.
- Run `pytest -q` and confirm the full suite passes.

## Output

Write `14_review_result.md` using the format in
`.protocol/handoffs/_template/09_reviewer_prompt.md` § "Output".

## Hard limits

- Do not edit any production or test code.
- Do not approve your own implementation.
- If any acceptance criterion is `unknown`, mark it `unknown` rather than guess.
