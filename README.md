# TCAD-H — Multi-CLI Development Harness

**TCAD-H** is a local, deterministic harness for software development with
multiple coding agents (Claude Code, OpenCode, Kimi, Qwen, DeepSeek, GPT,
Minimax). It coordinates them through versioned protocol artifacts so the
human keeps control of context, scope, evidence, and architecture.

**Version:** 0.1.0-alpha — installable local harness, **not** a public
release. See [`RELEASE.md`](./RELEASE.md) for what is alpha-ready and what
is deferred.

---

## Why this exists

Working with one coding agent is hard enough. Working with several in
parallel breaks down on its own without structure:

- **Context rot.** Agents hand each other 60K-token chat histories; the
  signal-to-noise collapses.
- **Scope creep.** Agents proactively "fix" things outside the task.
- **Silent duplication.** Agents add `def health()` even when one already
  exists six lines above (this happened in the Phase 2.3 trial).
- **Race conditions.** Two terminals editing the same working tree
  produce ghost diffs and broken merges.
- **Diff overwhelm.** A 500-line patch shows nothing about which capability
  of the product just changed.

TCAD-H addresses each of these with a deterministic mechanism, not a
prompt. No model receives conversation history. Every model receives
versioned files on disk.

## What it does, in one diagram

```
Human intent
   │
   ▼
Conductor (Claude Code) ─── drives FSM, writes specs, generates Work Packages
   │
   ▼
Work Package folder (versioned artifacts, never chat history)
   │
   ▼
Worker CLI (OpenCode + role model) ─── reads ONLY the WP files, edits in isolated worktree
   │
   ▼
Evidence pipeline:
   • git diff captured as 15_diff.patch
   • smoke gate (deterministic shell)
   • reviewer gate (duplicate routes / functions)
   • close report (JSON)
   • sharded journal entry
   │
   ▼
Static graph per WP (16_code_graph.json + 19_mermaid.md)
   │
   ▼
Cross-WP Atlas (layer heatmap, hotspots, timeline)
   │
   ▼
Studio (localhost dashboard, reads everything above)
```

Every box above is a deterministic Python script. Zero LLM in the core
pipeline. The LLM lives in the workers, never in the gates.

## The iron rules

These are non-negotiable. They are checked by code, not by good behavior.

1. **No model receives conversation history.** All inputs are versioned
   protocol artifacts on disk.
2. **The Conductor never writes production code.** It writes plans,
   prompts, briefs, and journal entries.
3. **The Reviewer is never the Implementer.** Different CLI or model.
4. **Open blocking questions halt progress.** Resolve them, or progress
   stops.
5. **No file is edited outside the active WP's `02_allowed_files.md`.**
   A pre-commit firewall enforces this.

See [`PROTOCOL.md`](./PROTOCOL.md) for the full specification.

---

## Quick install

```bash
git clone <this-repo> ~/.tcad-h
cd ~/.tcad-h
./install.sh

# Make sure ~/.local/bin is on your PATH
export PATH="$HOME/.local/bin:$PATH"

# Verify
tcad --version       # 0.1.0-alpha
tcad --home          # framework root
tcad doctor          # health check
```

The installer symlinks the `tcad` CLI into `~/.local/bin` (override with
`TCAD_INSTALL_DIR`). It does not require sudo and does not install Python
packages.

## Five-minute first WP

```bash
cd /path/to/your/project
tcad init                 # bootstrap .protocol/ (does not touch your code)
tcad profile detect       # guess project type from manifests
tcad doctor               # confirm health

# Create a Work Package
tcad wp create --lean --name "first-feature" --goal "Add /health endpoint" --role backend

# Fill 02_allowed_files.md and 03_forbidden_files.md in the WP folder

# Drive the conductor
tcad conduct init
tcad wp set WP-001-first-feature
tcad conduct transition INTAKE
tcad conduct transition SPEC_DRAFT
tcad conduct transition HANDOFF_GEN
tcad conduct transition WORKER_BRIEF

# Create an isolated worktree
tcad worktree create WP-001-first-feature --role backend

# Hand the worker prompt to OpenCode (or Kimi / Qwen / DeepSeek / GPT)
opencode --read .protocol/handoffs/WP-001-first-feature/05_worker_prompt_backend.md

# After the worker writes 11_worker_summary.md and commits in the worktree:
tcad close WP-001-first-feature-backend \
    --smoke-test "pytest -q"

# If reviewer + smoke pass:
tcad graph build WP-001-first-feature
tcad worktree merge WP-001-first-feature-backend
tcad worktree destroy WP-001-first-feature-backend
tcad atlas build
tcad studio        # open http://127.0.0.1:8765
```

Run `tcad quickstart` for a compact version of the above.

The full walkthrough lives in [`docs/QUICKSTART.md`](./docs/QUICKSTART.md).

---

## Project layout

```
framework/
├── PROTOCOL.md            ← method specification (read first)
├── AGENTS.md              ← universal agent entry point (Linux Foundation spec)
├── CLAUDE.md              ← Claude Code as Conductor
├── OPENCODE.md            ← OpenCode + others as Workers
├── README.md              ← this file
├── VERSION.md             ← 0.1.0-alpha
├── CHANGELOG.md           ← per-phase history
├── RELEASE.md             ← what is alpha-ready, what is deferred
├── FIELD_TRIAL_PLAN.md    ← rules for the Phase 3.5 usage week
├── FIELD_TRIAL.md         ← append-only log of trial WPs
├── FRICTION_REGISTER.md   ← deduplicated frictions
├── DECISION_REPORT.md     ← (pending) keep / simplify / drop
├── install.sh             ← local installer
├── bin/
│   └── tcad               ← single CLI entry point
├── scripts/
│   ├── _tcad_root.py      ← framework / target / worktree root resolver
│   ├── _tcad_lock.py      ← advisory file lock for status.json
│   ├── tcad_init.py       ← bootstrap .protocol/ in a repo
│   ├── tcad_doctor.py     ← repo health validator
│   ├── tcad_handoff.py    ← WP generator (lean / verbose)
│   ├── tcad_conduct.py    ← Conductor FSM
│   ├── tcad_worktree.py   ← git worktree manager
│   ├── tcad_log.py        ← evidence capture + gates
│   ├── tcad_scan.py       ← deterministic watcher
│   ├── tcad_check_boundaries.py   ← path firewall
│   ├── tcad_review.py     ← deterministic reviewer (duplicates)
│   ├── tcad_graph.py      ← per-WP graph + mermaid
│   ├── tcad_atlas.py      ← cross-WP atlas
│   ├── tcad_profile.py    ← project type detection
│   └── tcad_report.py     ← alpha state digest
├── studio/
│   ├── server.py          ← stdlib HTTP server
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── README.md
├── docs/
│   ├── QUICKSTART.md      ← 10-minute walkthrough
│   └── CONCEPTS.md        ← Framework / Target / Worktree roots
└── .protocol/
    ├── method.md
    ├── conductor.yaml
    ├── workflow.yaml
    ├── boundaries.yaml
    ├── smoke_tests.yaml
    ├── terminals.yaml
    ├── project_profile.json
    ├── status.json.example
    ├── handoffs/
    │   ├── _template/            ← 12-file WP template
    │   └── WP-000-example-...    ← populated example
    ├── questions/
    │   ├── INDEX.md
    │   └── ANSWERED.md
    ├── journal/
    ├── atlas/                    ← built by `tcad atlas build`
    └── blueprint/
```

The protocol's runtime state (`.protocol/worktrees/`, `status.lock`) is
gitignored by the installer.

---

## CLI reference

```text
tcad init                       Bootstrap .protocol/ in current repo.
tcad doctor [--no-suggestions]  Validate repo health + suggest fixes.
tcad quickstart                 Print the 10-step first-time flow.
tcad report alpha [--json]      Digest of current repo state + next action.

tcad profile detect [--force]   Detect project type, write profile JSON.
tcad profile show               Print current profile.
tcad profile validate           Verify layer globs match real files.

tcad wp create  ...             Generate a Work Package.
tcad wp set     <wp-id>         Activate a WP in the Conductor FSM.
tcad wp status                  Show Conductor state and active WP.

tcad conduct init               Create live status.json.
tcad conduct status             Print state.
tcad conduct transition <STATE> Move FSM forward.
tcad conduct add-question ...   Register a blocking question.
tcad conduct resolve-question <id>
tcad conduct guards             Inspect legal moves and required artifacts.

tcad worktree create <wp> --role <r>     Isolated branch + working tree.
tcad worktree list                       Show managed worktrees.
tcad worktree inspect <slug>             Show one worktree's status.
tcad worktree merge   <slug> [--no-ff] [--skip-checks]
tcad worktree destroy <slug> [--force] [--archive-patch] [--keep-branch]
tcad worktree prune                      Clean orphans.

tcad close <slug> [--smoke-test "..."] [--smoke-group X]
                  [--skip-smoke] [--review] [--skip-review] [--force]

tcad review routes  <file>      List HTTP routes; flag duplicates.
tcad review symbols <file>      List top-level Python symbols; flag dupes.
tcad review inspect <slug>      Full diff-aware review of a WP.

tcad graph build <wp>           Per-WP code_graph.json + mermaid.md.
tcad graph show  <wp>           Print mermaid.

tcad atlas build                Compose cross-WP atlas (heatmap, hotspots,
                                 timeline, layer_summary, atlas.mermaid).
tcad atlas show                 Print atlas summary.

tcad scan once [-v]             One-shot watcher.
tcad scan loop --interval N     Continuous watcher (Ctrl+C to stop).
tcad scan tail [--n N]          Tail events.jsonl.

tcad boundaries check [--rollback] [--strict] [--staged] [--files ...]

tcad studio [--port N]          Launch localhost dashboard.
```

Every command has `--help`.

---

## Roles, terminals, and the three "roots"

TCAD-H assumes you work with up to 5 terminals, each with a stable role:

| Terminal | Role             | Tool         | Typical model              |
|---------:|------------------|--------------|----------------------------|
| T1       | Conductor        | Claude Code  | Claude Opus / Sonnet       |
| T2       | Backend worker   | OpenCode     | Kimi / GPT                 |
| T3       | Frontend worker  | OpenCode     | Qwen / GPT                 |
| T4       | Docs/Tests       | OpenCode     | Minimax / DeepSeek         |
| T5       | Watcher + Studio | shell        | (no LLM — `tcad scan loop`)|

Three filesystem locations are involved:

1. **Framework Root** — where TCAD-H itself is installed (`~/.tcad-h`).
2. **Target Root** — the project repo where you run `tcad`.
3. **Worktree Root** — each `.protocol/worktrees/<wp>-<role>/` directory.

Confusing them is the most common source of bugs. See
[`docs/CONCEPTS.md`](./docs/CONCEPTS.md) for the resolution rules.

---

## What works today (alpha-ready)

| Capability | Notes |
|---|---|
| Lean / verbose Work Package generation | `tcad wp create --lean` writes 5 files; verbose writes 12 |
| Git worktree isolation per WP+role | `tcad worktree create/list/merge/destroy/prune` |
| Conductor FSM (17 states, deterministic) | `tcad conduct transition` enforces transitions |
| Path boundary firewall (OS-level) | `tcad boundaries check --rollback` |
| Smoke-test gate (YAML config) | `tcad close --smoke-test "..." --smoke-group X` |
| Deterministic reviewer gate | Duplicate FastAPI/Express routes + Python symbols |
| Evidence capture | `15_diff.patch` + sharded journal + `close_report.json` |
| Per-WP static graph | `16_code_graph.json` + `19_mermaid.md` (no LLM, no tree-sitter) |
| Cross-WP atlas | heatmap, hotspots, timeline, layer summary |
| Project profile detection | FastAPI / Next / React / Django / monorepo / etc. |
| Studio localhost UI | Stdlib HTTP server, no build step |
| `tcad doctor` repo health | 20+ checks with suggested fixes |
| `tcad report alpha` digest | Next-action recommendation |

## What is deferred

| Capability | Why deferred |
|---|---|
| Cross-file duplicate detection | Out of scope for v0.1 reviewer |
| Flask / Django / NestJS route detectors | Add when a real trial WP demands one |
| Mermaid.js visual render | Studio shows raw markdown for now |
| LLM-based semantic enrichment | Only after the field trial closes |
| MCP server | After 0.4 |
| PyPI package | After field trial signal |
| Multi-user / team mode | Not in scope |
| Windows native install | POSIX-only paths in some scripts |

See [`RELEASE.md`](./RELEASE.md) for the full status table.

---

## Where TCAD-H is in its journey

Each phase produced measurable evidence, not opinions:

```
Phase 1     Handoff MVP                              ✓
Phase 1.5   Conductor FSM                            ✓
Phase 1.7   Blueprint + Studio v0                    ✓
Phase 1.8   Boundaries + Watcher + Capabilities     ✓
Phase 1.9   Worktrees + Terminals + Lean             ✓
Phase 2     Evidence capture                         ✓
Phase 2.1   Dogfood trial (6 findings)               ✓
Phase 2.2   Fix dogfood findings                     ✓
Phase 2.3   External trial — caught Finding #11      ✓
Phase 2.4   Deterministic reviewer (closes #11)      ✓
Phase 2.5a  Static graph Lite                        ✓
Phase 3     Studio integration                       ✓
Phase 3.1   Project profile + layer mapping          ✓
Phase 3.3   Cross-WP atlas                           ✓
Phase 3.4   Alpha packaging — installable today      ✓  ← v0.1.0-alpha
Phase 3.5   Field trial / usage week                 → in progress
```

[`CHANGELOG.md`](./CHANGELOG.md) has the full ledger.

## What the trial will decide

The Phase 3.5 field trial runs 3 to 5 real WPs across 2+ repos and answers:

1. Did TCAD-H reduce recontextualization for the human?
2. Did it reduce review effort on the diff?
3. Did it catch real semantic problems?
4. Where did it generate ritual without value?
5. What is missing for daily use?

When [`DECISION_REPORT.md`](./DECISION_REPORT.md) is filled in, TCAD-H
moves to one of: **Keep**, **Simplify**, or **Drop**. Until then, no new
feature ships.

---

## Acknowledgements and design notes

TCAD-H absorbs hard-won lessons from:

- The METR Productivity Study (Feb 2026) on agentic slowdown.
- Mentor's repeated insistence: *boundary check ≠ correctness check*.
- The Phase 2.3 external trial, where TCAD-H found its own most critical
  failure mode (duplicate-route silently merged) and the Phase 2.4
  reviewer gate was built specifically to close it.
- Git worktrees — a Linux feature from 2015 that turns out to be the
  cleanest way to run multiple agents in parallel without races.

The project deliberately refuses certain features:

- **No LLM in the core pipeline.** Smoke gates, reviewer, graph, atlas
  are all Python + git + glob.
- **No invented capabilities.** The graph only shows evidence that
  exists on disk.
- **No public release until usage proves value.** v0.1.0 is alpha.

## Status

Active. Pre-1.0. Use at your own risk on real projects. File frictions in
`FRICTION_REGISTER.md`. Read `DECISION_REPORT.md` to know what happens
next.

## License

Internal experimental project. License to be set when (and if) v1.0 ships.

## Contact

Maintainer: Miguel.
