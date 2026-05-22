# AGENTS.md

> Authoritative entry point for any AI coding agent working in this repository.
> Read this file FIRST before reading any other file or making any change.

## Project

This repository hosts the **TCAD-H Protocol** itself — a Multi-CLI Development Harness for coordinating software work across multiple coding agents.

If you are an agent operating on a *client project* using TCAD-H, this file lives at the project root and tells you how to behave there.

## Mandatory reading order

Before proposing any change or writing any code:

1. `PROTOCOL.md` — what TCAD-H is, the 5 questions, the iron rules.
2. `.protocol/method.md` — formal TCAD-H method (Recall → T → C → A → D → Verify → Log).
3. `.protocol/boundaries.yaml` — which paths you may edit and which are forbidden.
4. `.protocol/status.json` — current Conductor state and active Work Package.
5. The active Work Package: `.protocol/handoffs/WP-NNN-*/` (look at `status.json` for the ID).
6. Last 3 entries in `.protocol/journal/INDEX.md` (when present).

If any of these files is missing, stop and ask. Do not improvise.

## Commands

| Purpose | Command |
|---|---|
| Generate a Work Package | `python scripts/tcad_handoff.py --name <slug> --goal "<text>" --role <backend\|frontend\|tests\|reading>` |
| Inspect Conductor state | `python scripts/tcad_conduct.py status` *(Phase 1.5)* |
| Capture evidence post-implementation | `python scripts/tcad_log.py <wp-path>` *(Phase 2)* |
| Generate code graph | `python scripts/tcad_graph_static.py <wp-path>` *(Phase 2.5a)* |
| Run tests (client project) | Defined per repo; see `OPENCODE.md` or `CLAUDE.md` |

## Hard rules

These are non-negotiable. Violating them rejects your work.

1. **You never receive conversation history.** All inputs are files in this repo.
2. **You read only the files listed in your worker prompt** (`05_*.md` through `08_*.md` depending on role).
3. **You write only files listed in `02_allowed_files.md`.** If you must touch something outside, stop and write to `12_delta.md`.
4. **You never edit `03_forbidden_files.md` paths.** Ever.
5. **You never write to `.protocol/**` except `11_worker_summary.md`, `12_delta.md`, `13_blockers.md` (worker role) or `14_review_result.md` (reviewer role).**
6. **You never edit `AGENTS.md`, `CLAUDE.md`, `OPENCODE.md`, `PROTOCOL.md`** unless the Work Package goal explicitly says so.
7. **No `git add -A` or `git add .`.** Stage files explicitly by name.
8. **No `--no-verify`, no force push, no amending another agent's commits.**
9. **No new dependencies without prior approval** documented in `04_existing_decisions.md`.
10. **If you are uncertain, stop and write to `13_blockers.md`** rather than guess.

## Output format (worker role)

When you finish a Work Package, write `11_worker_summary.md` using exactly this structure:

```
CHANGED FILES:
- path/to/file (created|modified|deleted)

TESTS RUN:
- command and result

WHAT PASSED:
- bullet list

WHAT FAILED:
- bullet list with paths and error messages

DECISIONS MADE:
- any judgment call not specified in the WP

RISKS:
- anything the reviewer should inspect

NEXT STEP:
- ready for review | needs human input | blocked
```

## Output format (reviewer role)

```
VERDICT: PASS | PASS_WITH_NOTES | FAIL

CHECKS:
- Scope respected: yes|no
- Forbidden files untouched: yes|no
- Tests adequate: yes|no|unknown
- Contracts safe: yes|no|n/a
- Existing architecture reused: yes|no

IF FAIL:
- Blocking issues with file:line
- Suggested fix
- Same-worker fix or escalation

OPEN QUESTIONS:
- New Q-IDs raised
```

## Tool discovery

- **MCP servers** are listed in `.protocol/mcp.json` *(Phase 5)*. If absent, no MCP available.
- **Subagents and skills** for Claude Code are listed in `CLAUDE.md`.
- **Worker model preferences** are listed in `.protocol/tool-router.yaml` *(Phase 4)*. If absent, the Conductor picks per task.

## Size budget

This file is kept under 32 KiB per the open AGENTS.md community spec, so any agent can load it without truncation.
