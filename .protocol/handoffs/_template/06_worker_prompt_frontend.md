# 06 — Worker Prompt: Frontend Role

<!--
Filled by the Conductor when the WP requires frontend changes. If this WP has
no frontend work, mark this file as "N/A" in the first line and the worker
will skip it.
-->

## Role

You are the Frontend Worker for this Work Package.

## Mandatory reading order

1. `AGENTS.md` at repo root
2. `OPENCODE.md` at repo root
3. This Work Package folder, files 00 through 04 and 10.

## Allowed and forbidden

- Edit only paths in `02_allowed_files.md`.
- Never edit paths in `03_forbidden_files.md`.
- Do not touch backend files.

## Task

(Conductor pastes the precise frontend implementation steps here.)

1. Step 1
2. Step 2

## Reuse rules

- Reuse existing components and styles. If a component already exists for this
  purpose, extend it; do not duplicate.
- Preserve responsive behavior.
- Do not invent new design system tokens.
- Do not restructure the component tree unless the WP explicitly requests it.

## Commands you must run

- `pnpm build`
- `pnpm test:unit -- path/to/changed`

## Output

Write your final summary to `11_worker_summary.md` using the format in
`OPENCODE.md` § "Output format".

## Hard limits

- Do not edit backend files.
- Do not add new design system packages.
- Do not refactor unrelated components.
- Keep `11_worker_summary.md` under 400 lines.
