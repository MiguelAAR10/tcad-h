# TCAD Studio

Localhost dashboard that visualizes the project as a building under
construction. Phase 1.7 / Phase 4 v0.

## Run

```bash
cd /home/miguel/projects/framework
python3 studio/server.py
# open http://127.0.0.1:8765
```

Override port:

```bash
python3 studio/server.py --port 9000
```

## What you see

- **Top bar** — project name, Conductor state, active Work Package, open
  questions, last refresh time.
- **Building panel** — floors stacked top-to-bottom-reversed (ground floor at
  the bottom). Each room is colored by its build status:
  - gray `planned` / yellow `foundations` / blue `built` / green `finished` /
    red `cracked`.
  - Bottom progress bar shows expected_furniture coverage.
- **Detail panel** — click a room to see its allowed paths, expected
  furniture, dependencies, and which Work Packages have touched it.
- **Timeline** — Work Packages as cards in creation order. Click a card to
  open its files.
- **WP detail** — opens below the timeline. Click any file chip to view its
  contents.

## Data flow

```
.protocol/blueprint/blueprint.yaml ──┐
.protocol/handoffs/WP-*/             ├──> server.py builds JSON
.protocol/questions/INDEX.md         │       /api/state
.protocol/status.json (Phase 1.5)    ┘       /api/wp/<id>
                                                │
                                                ▼
                          index.html + app.js renders building
                                                │
                                                ▼
                                  poll every 5 seconds
```

Auto-refresh is on. The page re-renders every 5 seconds without losing the
selected room.

## Limitations of v0

- The bundled YAML parser is intentionally minimal. It handles the blueprint
  schema as shipped; arbitrary YAML files may fail.
- File-system reads run on every `/api/state` request. Acceptable for the
  typical ≤200 file repo. Cache later if needed.
- No WebSocket; polling only.
- No 3D. The building view is 2D blueprint-style on purpose: faster to render,
  easier to scan.
- Room status is heuristic. Real precision arrives with Phase 2 (evidence
  capture) and Phase 2.5 (atlas).
- No authentication. Serves on `127.0.0.1` only. Do not expose to the
  network.

## Extending

- Replace `studio/index.html` + `studio/app.js` with a Vite + React frontend
  later if you want richer interactions. The API contract (`/api/state`,
  `/api/wp/<id>`) is meant to be stable.
- Add `/api/journal` once Phase 2 lands.
- Add `/api/atlas` once Phase 2.5 lands.
- Add `/api/transition` (POST) to drive the Conductor FSM from the UI once
  Phase 1.5 lands.
