# 05 — Worker Prompt: Backend Role

<!--
The Conductor pastes the final, self-contained prompt for the backend worker
here. The worker should be able to read this file and ONLY the files it
references, and complete the task.
-->

## Role

You are the Backend Worker for this Work Package.

## Mandatory reading order

Before writing any code, read these files in this order. Do not read other files
unless the Work Package tells you to:

1. `AGENTS.md` at repo root
2. `OPENCODE.md` at repo root
3. This Work Package folder, files 00 through 04 and 10.

## Allowed and forbidden

- Edit only paths in `02_allowed_files.md`.
- Never edit paths in `03_forbidden_files.md`.

## Task

(Conductor pastes the precise backend implementation steps here.)

1. Step 1
2. Step 2
3. Step 3

## Commands you must run

(Conductor lists the exact commands the worker should run to validate its work.)

- `pytest path/to/relevant/test`
- `pnpm typecheck` (only if backend uses TS)

## Output

You must write your final summary to `11_worker_summary.md` in this Work Package
folder using exactly the format defined in `OPENCODE.md` § "Output format".

If you discover the Work Package is wrong, write `12_delta.md` instead and stop.
If you are blocked, write `13_blockers.md` and stop.

## Hard limits

- Do not edit forbidden files.
- Do not introduce new dependencies unless `04_existing_decisions.md` explicitly
  allows the specific package.
- Do not change public API shapes unless this prompt explicitly requests it.
- Do not call external services.
- Keep `11_worker_summary.md` under 400 lines.
