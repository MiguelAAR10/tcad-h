# 01 — Goal

## User intent

Add a public `/health` endpoint so external uptime probes can verify the service
is alive without authenticating.

## Specifics

- Endpoint path: `GET /health`
- Response status: `200 OK`
- Response body: `{"status": "ok"}` (application/json)
- Response time budget: under 50ms p99 in production
- Endpoint must not require authentication
- Endpoint must not log a record per request (probes hit it every 10s — would flood logs)

## Non-goals

- No database health check (probes only need process liveness in this Phase)
- No version or build SHA in the response yet
- No `/ready` endpoint (that is a follow-up WP)
- No metrics emission (Prometheus integration is a separate WP)

## Risk level

`low`

- One new file, one new test file.
- No contract changes.
- Auth middleware exemption is documented and reversible.
- No data writes.
