# 21 — Open Questions (WP-000 scope)

## Status legend

- 🟡 **pending** — Awaiting answer.
- 🔵 **answered** — Awaiting Conductor to apply.
- ✅ **resolved** — Applied; archived in `.protocol/questions/ANSWERED.md`.

## Current open questions

(none — example WP is intentionally unambiguous)

---

## Hypothetical example (for documentation)

If during implementation the worker discovered that the auth middleware does
NOT exempt `/health` by default, it would raise:

```markdown
## Q-001 — Auth middleware does not exempt /health

**Status**: 🟡 pending
**Raised by**: worker (opencode-kimi)
**Raised at**: 2026-05-21T14:30:00Z

**Evidence**:
- backend/app/auth/middleware.py:42 — `PUBLIC_PATHS` default does not include "/health"
- test_health_does_not_require_auth fails with 401

**Question**:
Should the Conductor:
(A) extend the WP scope to add "/health" to PUBLIC_PATHS in config.py
(B) split into WP-001 for the config change and keep this WP green
(C) park the unauth requirement for a follow-up WP

**Blocks**: WORKER_DONE
```

The Conductor would then mirror this entry in `.protocol/questions/INDEX.md`
as `Q-001` and wait for a human answer before proceeding.
