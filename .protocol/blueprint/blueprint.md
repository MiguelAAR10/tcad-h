# Blueprint — Project as Building

> Phase 1.7 deliverable. The construction metaphor for TCAD-H.

## Why a building

A long-running project is hard to *see*. Tickets, branches, and PRs do not
answer "how much of the system is actually built?". A blueprint answers it.

The blueprint declares the *planned* architecture as a building. Work Packages
fill it in. Studio (Phase 4) renders the building and colors each room by its
build status, so a human can look at the whole project in 10 seconds and know:

- What is planned but not started.
- What is being built right now (and by which CLI/model).
- What is built but lacking tests.
- What is finished.
- What is broken.

## Mapping

| Real | Software |
|---|---|
| Building | Project |
| Floor | Top-level module (backend, frontend, infra, docs) |
| Room | Capability inside a floor (auth, billing, dashboard) |
| Furniture | Files, functions, endpoints inside a room |
| Lights | Tests covering the room |
| Pipes / wiring | Contracts and integrations between rooms |
| Work crew | Work Package (one or more crews build one or more rooms) |
| Materials | Lines of code |
| Plans / blueprint | `.protocol/blueprint/blueprint.yaml` |

## Room status

Status drives the color in Studio.

| Status | Color | Meaning |
|---|---|---|
| `planned` | gray | Declared in blueprint, no code yet |
| `foundations` | yellow | Active WP touching this room |
| `built` | blue | Code exists, tests partial or missing |
| `finished` | green | Code + tests + reviewer PASS |
| `cracked` | red | Failing tests or open blocking question |

Status is computed by Studio from:

1. `allowed_paths` glob match against current files in repo.
2. Existence and verdict of `14_review_result.md` in WPs that touched the room.
3. Coverage report when available (Phase 2.5).
4. Open blocking questions in `.protocol/questions/INDEX.md` referencing the room.

## Floors

A floor groups a coherent area. Common floors:

- **Protocol Core** — the TCAD-H spec itself (this repo)
- **Backend** — server-side modules
- **Frontend** — client-side modules
- **Infrastructure** — CI/CD, hosting, secrets
- **Documentation** — user-facing docs
- **Tests** — when test suites are large enough to deserve their own floor

You may add domain-specific floors: *Billing*, *Reporting*, *ML pipeline*, etc.

## Rooms

A room is the smallest unit that Studio renders as a clickable shape.

Each room declares:

- `id` — dotted, e.g. `backend.auth`
- `label` — human label shown in Studio
- `description` — one sentence
- `allowed_paths` — globs that Studio uses to find code belonging to the room
- `expected_furniture` — the things the room *should* contain when finished
- `contracts` — public surface (endpoints, schemas) for `pipes` to attach to
- `depends_on` — rooms that must exist first for this one to make sense

A room is **finished** when all `expected_furniture` items have a corresponding
file or function in the codebase and a PASS reviewer verdict exists in at least
one WP that touched the room.

## Pipes

Pipes are contracts between rooms. Studio renders them as lines between rooms,
colored by contract health:

- Green — contract validated (Phase 2.5b contract checks pass)
- Yellow — contract declared but not validated
- Red — contract drift detected

## Construction plan

Optional. Declares the planned *order* of construction as named phases. Studio
renders this as a Gantt-ish strip at the bottom of the building view.

```yaml
construction_plan:
  - phase: "Phase 1 — Foundations"
    rooms: [protocol.spec, handoff.template, handoff.generator]
  - phase: "Phase 2 — Walls"
    rooms: [evidence.log, memory.journal]
```

## How the blueprint stays alive

- **Initial draft** — the human writes `.protocol/blueprint/blueprint.yaml`
  during the **T (Translate)** phase of the first Work Package.
- **Updates** — when a WP introduces a new capability not in the blueprint, the
  Conductor proposes a blueprint patch. The human approves before the WP can
  graduate.
- **Drift detection** — Studio flags rooms whose `allowed_paths` match no files
  *(blueprint claims a room that does not exist)* and files matched by no room
  *(orphan files outside the blueprint)*.

## What the blueprint is NOT

- It is **not** a dependency graph of imports. That is the Static Atlas
  (Phase 2.5a).
- It is **not** a project schedule. There is no estimation in days/hours. The
  `construction_plan` orders rooms but does not commit to dates.
- It is **not** the source of truth for code. Code lives in the repo; the
  blueprint maps which code belongs to which room.

## Cold start

If you start a new project today:

1. Copy `.protocol/blueprint/blueprint.yaml.example` to
   `.protocol/blueprint/blueprint.yaml`.
2. Replace floors and rooms with your project's actual layout.
3. Run `python studio/server.py` and open `http://localhost:8765`.
4. Generate your first WP with `python scripts/tcad_handoff.py`.
5. Mark the WP's target room in `01_goal.md`:
   ```markdown
   ## Specifics
   - target_room: backend.auth
   ```
6. When the WP closes, Studio re-renders the room with the new status.
