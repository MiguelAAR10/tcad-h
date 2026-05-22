# TCAD-H Quickstart — 10 minutes

This guide walks you from zero to a closed Work Package on a fresh repo.

## 0. Prerequisites

- Python 3.10+
- git
- Bash-compatible shell

## 1. Install (~1 min)

```bash
git clone <this-repo> ~/.tcad-h
cd ~/.tcad-h
./install.sh
```

The installer symlinks `tcad` into `~/.local/bin`. If that's not on your
PATH, add this line to `~/.bashrc` or `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Verify:

```bash
tcad --version
# 0.1.0-alpha

tcad --home
# /home/<you>/.tcad-h
```

## 2. Bootstrap your project (~30s)

Pick any repo (or `mkdir my-test-app && cd my-test-app && git init -q`).

```bash
cd /path/to/your/project
tcad init
```

This creates:

```
.protocol/
├── handoffs/_template/      ← 12 WP template files
├── questions/INDEX.md       ← blocking questions
├── journal/                 ← per-WP entries (sharded)
├── atlas/                   ← cross-WP composed view (built later)
├── worktrees/               ← gitignored; created as you make WPs
├── boundaries.yaml          ← live allow/deny zones
├── boundaries.yaml.example
├── smoke_tests.yaml.example
├── capabilities.yaml.example
├── terminals.yaml.example
├── project_profile.yaml.example
└── status.json.example
```

Plus an updated `.gitignore` for runtime artifacts.

## 3. Detect your project type (~5s)

```bash
tcad profile detect
tcad profile show
```

TCAD-H reads `package.json`, `pyproject.toml`, lockfiles, and folder layout
to guess your project type (`fullstack_web`, `backend_api`, `frontend_spa`,
`agent_rag`, `monorepo`, …) and writes `.protocol/project_profile.json`.

```bash
tcad profile validate
```

Checks each layer's globs against real files; warns about empty layers.

If the detection is wrong, edit `.protocol/project_profile.yaml.example`,
save it as `.protocol/project_profile.yaml`, and rerun.

## 4. Doctor — confirm health (~2s)

```bash
tcad doctor
```

You should see a list of ok/warn/info lines:

```
✓ .protocol/ present
✓ required dir handoffs/_template
✓ required file boundaries.yaml
✓ required file questions/INDEX.md
· optional smoke_tests.yaml    not present
· optional status.json         not present
✓ scripts present              13 scripts
✓ scripts compile
✓ git repo
```

Anything `fail` (✗) is a blocker. Fix it and rerun.

## 5. First Work Package (~3 min)

Pick a small change. Example: add a `/health` endpoint to your backend.

```bash
tcad wp create --lean --name "add-health" --goal "Add GET /health" --role backend
```

This produces a folder under `.protocol/handoffs/WP-001-add-health/`
with 5 files. Open `02_allowed_files.md` and list paths the worker may
edit. Open `03_forbidden_files.md` and list paths it must not touch.

Initialize the conductor and activate the WP:

```bash
tcad conduct init
tcad wp set WP-001-add-health
tcad conduct transition INTAKE
tcad conduct transition SPEC_DRAFT
tcad conduct transition HANDOFF_GEN
tcad conduct transition WORKER_BRIEF
```

Create an isolated worktree for the work:

```bash
tcad worktree create WP-001-add-health --role backend
```

The worktree lives at `.protocol/worktrees/WP-001-add-health-backend/`
on a branch `wp/WP-001-add-health-backend`. Open another terminal there:

```bash
cd .protocol/worktrees/WP-001-add-health-backend
# launch your worker CLI (opencode, kimi, qwen, etc.)
# point it at .protocol/handoffs/WP-001-add-health/05_worker_prompt_backend.md
```

After the worker finishes its edits and commits to the WP branch, return
to the main repo terminal:

```bash
cd /path/to/your/project

# Author 11_worker_summary.md (or have the worker write it).
# It must follow the OPENCODE.md format, including 'NEXT STEP: ready for review'.

tcad close WP-001-add-health-backend \
  --smoke-test "cd .protocol/worktrees/WP-001-add-health-backend && pytest -q"
```

What `tcad close` does:

1. Captures `git diff base...branch` into `15_diff.patch`.
2. Runs the smoke test you passed; fails the close if non-zero.
3. Runs `tcad_review.py inspect` — duplicate route/symbol detection.
4. Writes `close_report.json` + `journal/<date>-<id>-<wp>.md`.
5. Emits `wp_evidence_logged` to `events.jsonl`.

If the reviewer gate finds critical issues, `close` returns 6 and leaves
a question in `.protocol/questions/INDEX.md`. Fix the duplicate or pass
`--skip-review` to bypass (not recommended).

## 6. Build the graph (~5s)

```bash
tcad graph build WP-001-add-health
```

Outputs `16_code_graph.json` + `19_mermaid.md` inside the WP folder.
Nodes are tagged with the architecture layer they belong to (per your
profile). Reviewer focus highlights files cited in critical findings, or
the largest diff.

## 7. Merge and clean up (~5s)

```bash
tcad worktree merge WP-001-add-health-backend
tcad worktree destroy WP-001-add-health-backend
```

Merge fails (exit 6) unless:

- `11_worker_summary.md` declares `NEXT STEP: ready for review`
- No unresolved content in `13_blockers.md`
- No uncommitted changes in the worktree

## 8. Build the cross-WP atlas (~2s)

After you have a few WPs closed:

```bash
tcad atlas build
```

Outputs in `.protocol/atlas/`:

- `atlas.json` — full aggregation
- `heatmap.md` — layer + hotspot tables
- `timeline.md` — event chronology
- `layer_summary.md` — per-layer breakdown
- `atlas.mermaid` — visual

## 9. Studio (~5s)

```bash
tcad studio
# open http://127.0.0.1:8765
```

Panels:

- **Building** — your profile's layers rendered as floors and rooms.
- **Timeline** — Work Packages as cards.
- **Events** — last 10 events.jsonl entries.
- **Development Graph** — pick a WP, see its gates, findings, mermaid.
- **Atlas (cross-WP)** — layer heatmap + hotspots.

## 10. Common loops

### Daily

```bash
tcad doctor
tcad atlas build       # refresh cross-WP view
tcad studio
```

### Per WP

```bash
tcad wp create ...
tcad worktree create <wp> --role <role>
# worker edits
tcad close <slug>
tcad graph build <wp>
tcad worktree merge <slug>
tcad worktree destroy <slug>
tcad atlas build
```

## Where to go next

- `docs/CONCEPTS.md` — Framework root vs Target root vs Worktree root.
- `PROTOCOL.md` — full method specification.
- `RELEASE.md` — what is in this alpha and what is deferred.
