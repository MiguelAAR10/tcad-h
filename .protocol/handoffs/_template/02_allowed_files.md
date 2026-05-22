# 02 — Allowed Files

<!--
Explicit allow list. The worker may CREATE or MODIFY files matching these paths
or globs. Anything else is out of scope.

Rules:
- Use exact paths when known.
- Use globs (`backend/services/auth/*.py`) when a directory is fair game.
- If the worker discovers it must edit a file not listed here, it MUST stop and
  write to 12_delta.md. Do not silently expand.
-->

## Paths and globs

- `path/to/specific/file.py`
- `path/to/dir/**/*.ts`
- `tests/path/to/test_file.py`

## Files the worker must create (not just modify)

(If the WP requires creating new files, list them explicitly here.)

- `path/to/new_file.py`
