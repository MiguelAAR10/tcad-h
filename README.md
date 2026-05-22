# TCAD-H — Multi-CLI Development Harness

> Coordinate multiple coding agents (Claude Code, OpenCode, Kimi, Qwen, DeepSeek, GPT, Minimax) on real software projects without losing context, breaking the system, or burning tokens on rework.

## In 30 seconds

```
Human intent
   ↓
Conductor Agent (Claude Code)         ← drives FSM, writes spec, generates Work Package
   ↓
Work Package folder                   ← versioned artifacts, NOT chat history
   ↓
Worker CLI (OpenCode + role model)    ← reads only the WP files, implements, writes summary
   ↓
Evidence (diff + summary + delta + blockers)
   ↓
Atlas (static graph → semantic graph → impact map)   [Phase 2.5]
   ↓
Reviewer Agent (different CLI/model)  ← reads compressed brief, not full diff
   ↓
Journal entry (sharded, indexable)
```

The unit of coordination is the **Work Package**, not the API call.

## What is here today (Phase 1)

```
framework/
├── PROTOCOL.md                  ← read first, 3 pages
├── AGENTS.md                    ← universal agent entry point
├── CLAUDE.md                    ← Claude Code as Conductor
├── OPENCODE.md                  ← OpenCode as Worker
├── README.md                    ← this file
├── scripts/
│   └── tcad_handoff.py          ← functional, no LLM, no external deps
├── studio/                      ← localhost dashboard (Phase 1.7 / Phase 4 v0)
│   ├── server.py                ← stdlib-only HTTP server
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── README.md
├── .protocol/
│   ├── method.md                ← formal TCAD-H method
│   ├── conductor.yaml           ← Conductor FSM spec
│   ├── workflow.yaml            ← phase ownership map
│   ├── status.json.example      ← FSM state schema
│   ├── blueprint/
│   │   ├── blueprint.yaml       ← project-as-building (live)
│   │   ├── blueprint.yaml.example
│   │   └── blueprint.md         ← construction metaphor docs
│   ├── questions/
│   │   ├── INDEX.md             ← global blocking questions
│   │   └── ANSWERED.md          ← archive
│   └── handoffs/
│       ├── _template/           ← Work Package template (12 files)
│       └── WP-000-example-health-endpoint/   ← populated example
└── (v1 docs preserved: AGENTS_v1.md, TCAD_FRAMEWORK.md, CAVEMAN_LOG.md, CONTRACT_GATES.md, PHASE_CARDS.md)
```

## Quickstart (5 minutes)

```bash
cd /path/to/framework

# 1. Inspect the example Work Package
cat .protocol/handoffs/WP-000-example-health-endpoint/01_goal.md

# 2. Generate your own Work Package
python scripts/tcad_handoff.py \
  --name "my-first-feature" \
  --goal "Describe what you want built in one sentence" \
  --role backend

# 3. Open the generated folder
ls -1 .protocol/handoffs/WP-001-my-first-feature/

# 4. Fill in the human-owned files:
#    - 01_goal.md (refine the goal)
#    - 02_allowed_files.md (paths the worker may edit)
#    - 03_forbidden_files.md (paths the worker must not touch)
#    - 04_existing_decisions.md (constraints and reuse)
#    - 10_acceptance_criteria.md (how to know it is done)

# 5. Hand the worker prompt to your worker CLI:
opencode --read .protocol/handoffs/WP-001-my-first-feature/05_worker_prompt_backend.md
# or
kimi run .protocol/handoffs/WP-001-my-first-feature/05_worker_prompt_backend.md
# (the exact invocation depends on your CLI)

# 6. When the worker finishes, it must write 11_worker_summary.md
#    inside the same WP folder.

# 7. Phase 2 will add scripts/tcad_log.py to capture diff + journal entry.
#    Phase 1.5 will add scripts/tcad_conduct.py for FSM enforcement.
```

## Visualize the project (Studio)

The Studio renders the project as a building under construction. Each floor
is a module, each room is a capability, color = build status. Open it in
parallel to your terminals — Claude Code in one, OpenCode in another, etc. —
and watch rooms light up as Work Packages graduate.

```bash
python3 studio/server.py
# open http://127.0.0.1:8765
# default port 8765; override with --port 9000
```

See `studio/README.md` for what each panel does and
`.protocol/blueprint/blueprint.md` for the construction metaphor.

## Iron rules (read before using)

1. No model ever receives conversation history. All inputs are files in this repo.
2. The Conductor never writes production code.
3. The Reviewer is always a different CLI/model than the Implementer.
4. Open blocking questions halt progress until resolved.
5. No file is edited outside the active Work Package's `02_allowed_files.md`.

See `PROTOCOL.md` for the full specification.

## Roadmap

- [x] **Phase 1** — Handoff MVP: protocol docs + Work Package template + `tcad_handoff.py`.
- [ ] **Phase 1.5** — Conductor FSM: `tcad_conduct.py` enforces state machine.
- [x] **Phase 1.7** — Blueprint + Studio v0: `.protocol/blueprint/blueprint.yaml` + `studio/` localhost dashboard.
- [ ] **Phase 2** — Evidence capture: `tcad_log.py` produces diff, summary validation, journal entry.
- [ ] **Phase 2.5a** — Static graph: `tcad_graph_static.py` (deterministic, no LLM).
- [ ] **Phase 2.5b** — Semantic graph: `tcad_graph_enrich.py` (LLM enriches, never invents structure).
- [ ] **Phase 2.5c** — Atlas: cross-WP composed view, heatmap, capability timeline.
- [ ] **Phase 3** — Reviewer focus + contract gates.
- [ ] **Phase 4** — TCAD Studio v1 (richer interactions: WebSocket, transition controls, atlas overlay).
- [ ] **Phase 5** — MCP integration, Drive sync, reports.

## License / status

Internal experimental protocol. v2.4. Not yet stable. See `PROTOCOL.md` § Versioning.
