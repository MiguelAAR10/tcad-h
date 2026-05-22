# 03 — Forbidden Files

<!--
Explicit deny list. The worker must NEVER edit these files, even by accident,
even if it seems necessary to complete the goal.

If the goal genuinely requires touching a forbidden path, the worker MUST stop
and write to 12_delta.md or 13_blockers.md. The Conductor decides whether to
rewrite the Work Package or escalate to the human.
-->

## Always forbidden (inherited from .protocol/boundaries.yaml)

(Conductor copies the global deny list here for worker convenience.)

- `infra/**`
- `migrations/**`
- `.env*`
- `.protocol/**` (except files this WP owns: 11, 12, 13)
- `AGENTS.md`
- `CLAUDE.md`
- `OPENCODE.md`
- `PROTOCOL.md`

## Forbidden for this Work Package specifically

(Conductor adds WP-specific forbids. Examples: legacy modules, modules owned by
another team, modules under active refactor by another WP.)

- (path 1) — (reason)
- (path 2) — (reason)
