# 04 — Existing Decisions

<!--
Constraints from prior decisions: architecture, contracts, naming, libraries.
The worker treats these as fixed. Violating them requires writing to 12_delta.md.

This is where you encode the "why we don't redo this" knowledge so the worker
does not regress to defaults.
-->

## Architecture decisions

- (Decision 1, source: `specs/<id>/plan.md` or journal entry)
- (Decision 2)

## Library and framework choices

- (Library X is used because Y; do not introduce alternatives.)

## Naming and style

- (Module naming convention)
- (Test file pattern)
- (Commit message format)

## Reuse expectations

- (Component A in `path/...` should be extended, not re-implemented.)
- (Helper `func_x` in `path/utils.py` handles the parsing already.)

## Contract preservation

- (Endpoint `/api/foo` response shape must remain stable. Consumer: `frontend/...`)
- (Pydantic model `X` field order is locked.)
