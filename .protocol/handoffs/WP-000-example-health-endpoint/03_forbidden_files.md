# 03 — Forbidden Files

## Always forbidden (inherited from .protocol/boundaries.yaml)

- `infra/**`
- `migrations/**`
- `.env*`
- `.protocol/**` (except files this WP owns: 11, 12, 13)
- `AGENTS.md`
- `CLAUDE.md`
- `OPENCODE.md`
- `PROTOCOL.md`

## Forbidden for this Work Package specifically

- `backend/app/auth/middleware.py` — Do not edit. The middleware already supports
  a public-path allow list via `PUBLIC_PATHS` config. Add `/health` to the
  config in `backend/app/config.py` if needed, but do not modify the middleware
  itself.
- `backend/app/config.py` — Do not edit unless the test confirms the new path
  is not exempted by default. If you must edit it, write to `12_delta.md` first.
- `backend/app/models/**` — Out of scope.
- `frontend/**` — Out of scope.
