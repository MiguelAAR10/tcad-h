# Changelog

All notable changes to Foreman (originally TCAD-H), by phase.

## [unreleased] — Phase 3.5+ Rename + Staff-Engineer Feedback Fixes

### Renamed
- Project: **TCAD-H → Foreman** ("Site supervisor for AI coding crews").
- Primary CLI: `tcad` → `foreman` (the `tcad` command remains as a deprecated alias until v0.3).
- Env vars: `TCAD_HOME` / `TCAD_ROOT` → `FOREMAN_HOME` / `FOREMAN_ROOT`
  (legacy vars still honored as fallback).
- Internal script filenames keep `tcad_*.py` for one more release to avoid
  breaking everyone's symlinks; v0.2 plans to rename.

### Added
- `bin/foreman` primary entrypoint + `bin/tcad` deprecation shim.
- `foreman wp express`: one-shot init + create + FSM + worktree.
  Cuts the "5-minute" flow from ~10 commands to 1. Drops the user into
  `$EDITOR` for the scope files (or accepts `--allowed` / `--forbidden`
  globs directly to skip).
- `scripts/_tcad_yaml.py`: single shared YAML parser. Removes the
  duplicated TinyYAML class from `tcad_check_boundaries.py` and
  `studio/server.py`.

### Documentation
- README rewritten with explicit **auth model section**: Foreman does NOT
  manage API tokens. Workers authenticate via their own CLI subscriptions.
  All references to "tokens" reframed as throughput + auditability.
- "Honest scope" section added listing what Foreman does NOT do
  (Staff-Engineer feedback: cross-file dup detection, Flask/Django
  detectors, auto-orchestration of CLI workers, PyPI packaging — all
  explicit non-goals for v0.1).
- Iron rule #1 reframed from "guarantee" to "policy" with honest
  enforcement strength column.

## [0.1.0-alpha] — Phase 3.4 Alpha Packaging

### Added
- `VERSION.md`, `CHANGELOG.md`, `RELEASE.md` — versioned packaging.
- `install.sh` — local installer that symlinks `tcad` into the user's PATH.
- `bin/tcad` — single CLI wrapper dispatching to existing scripts.
- `scripts/tcad_doctor.py` — repo health validator.
- `docs/QUICKSTART.md` — 10-minute external-repo walkthrough.
- `docs/CONCEPTS.md` — Framework Root vs Target Root vs Worktree Root.

### Goal
Reduce friction. A user should be able to clone the framework, run
`./install.sh`, then in any other repo run `tcad init` and start working.

### Not in this release
- LLM-based semantic enrichment.
- MCP integration.
- Mermaid.js visual render in studio.
- Python package on PyPI.
- Cross-file duplicate detection.
- Flask / Django route detectors.

---

## Phase 3.3 — Cross-WP Atlas

### Added
- `scripts/tcad_atlas.py build|show` — composes all WP graphs into one atlas.
- `.protocol/atlas/atlas.json|heatmap.md|timeline.md|layer_summary.md|atlas.mermaid`.
- Studio `/api/atlas` + new panel showing layer rows and hotspots.

### Why
Per-WP graph was a single snapshot. The Atlas reveals patterns across many
WPs: which layer changes most, which file is a hotspot, which gate fails most.

---

## Phase 3.1 — Project Profile + Architecture Mapping

### Added
- `.protocol/project_profile.yaml.example` — schema for project type, stack,
  layers, detectors, architecture blocks.
- `scripts/tcad_profile.py detect|show|validate` — deterministic detection of
  project type from manifests (`package.json`, `pyproject.toml`, lockfiles).
- `scripts/tcad_graph.py` enriched — each graph node carries `layer`;
  mermaid subgraphs group by layer instead of file extension.

### Verified
Detection correctly identified edu-app as `fullstack_web` (fastapi + next).

---

## Phase 3 — Studio Integration

### Added
- `/api/graphs`, `/api/graph/<wp>`, `/api/mermaid/<wp>`, `/api/review/<wp>`.
- Studio panel `Development Graph` with WP selector, gate chips, critical
  findings, reviewer focus, and a `<pre>` view of mermaid source.

### Why
Until Phase 3, graphs lived only on disk. Studio v0 finally surfaces them.

---

## Phase 2.5a — Static Graph Lite

### Added
- `scripts/tcad_graph.py static|show` — per-WP graph from `15_diff.patch`,
  `close_report.json`, `review_report.json`, `events.jsonl`.
- Outputs: `16_code_graph.json`, `19_mermaid.md`.

### Mentor scope respected
Graph only shows evidence already on disk. No LLM. No tree-sitter. No
invented capability names.

---

## Phase 2.4 — Deterministic Reviewer Gate

### Added
- `scripts/tcad_review.py routes|symbols|inspect`.
- FastAPI/Express duplicate-route detector (AST + regex).
- Python module-level duplicate function/class detector.
- `tcad_log.py close --review` wires the reviewer into the close pipeline.

### Closes
Finding #11 from the Phase 2.3 external trial: a duplicate `/health`
endpoint was committed to edu-app silently. The reviewer gate now blocks
that class of failure structurally.

---

## Phase 2.3 — External Trial (edu-app)

### Did
- Bootstrapped a minimal `.protocol/` in `learning/edu-app`.
- Ran a real WP through the entire pipeline.
- Reverted edu-app to clean state after trial.

### Findings
- #7  `TCAD_ROOT` env only honored by `tcad_log.py` (CRITICAL). FIXED.
- #8  WP template encoded framework conventions, not target's.
- #9  Worktree didn't inherit venv.
- #10 Target venv broken on host.
- #11 CRITICAL — boundary firewall + smoke gates passed a duplicate `/health`.

### Documented in
`EXTERNAL_TRIAL_REPORT.md`.

---

## Phase 2.2 — Fix Trial Findings

### Added
- `scripts/tcad_log.py` smoke-test gate (`--smoke-test`, `--smoke-group`,
  `--skip-smoke`).
- `.protocol/smoke_tests.yaml` — deterministic shell commands per group.
- `scripts/_tcad_root.py` — shared `resolve_tcad_root()` helper.
- `tcad_handoff.py` writes `.tcad_wp.json` metadata; `tcad_conduct.py`
  reads it for lean-aware WP validation.
- `tcad_worktree.py merge` — structured conflict UX with `merge_conflict_detected`
  event + open question + suggested actions.

---

## Phase 2.1 — Dogfood Trial (TCAD-H on TCAD-H)

### Did
Ran 3 WPs through the framework against itself. Captured measurements,
6 findings, and produced `TRIAL_REPORT.md`.

---

## Phase 2 — Evidence Capture

### Added
- `scripts/tcad_log.py close|validate|journal-list|journal-show`.
- Per-WP: `15_diff.patch`, `close_report.json`, `journal/YYYY-MM-DD-NNN.md`.
- Append-only audit via `events.jsonl`.

---

## Phase 1.9 — Worktrees + Terminals + Lean Mode

### Added
- `scripts/tcad_worktree.py create|list|inspect|merge|destroy|prune`.
- `.protocol/terminals.yaml` — 5-terminal RBAC + review pairing rules.
- `tcad_handoff.py --lean` — generate 5 files instead of 12.

---

## Phase 1.8 — Boundaries + Watcher + Capabilities

### Added
- `scripts/tcad_check_boundaries.py --rollback` — OS-level firewall.
- `scripts/tcad_scan.py once|loop|tail` — deterministic watcher.
- `.protocol/boundaries.yaml`, `.protocol/capabilities.yaml.example`.

---

## Phase 1.7 — Blueprint + Studio v0

### Added
- `.protocol/blueprint/blueprint.yaml` — project-as-building metaphor.
- `studio/server.py`, `studio/index.html`, `studio/app.js`, `studio/styles.css`.

---

## Phase 1.5 — Conductor FSM

### Added
- `scripts/tcad_conduct.py init|status|transition|set-wp|add-question|...`.
- `.protocol/conductor.yaml` — canonical FSM transitions.
- `.protocol/status.json` — live state.

---

## Phase 1 — Handoff MVP

### Added
- `scripts/tcad_handoff.py` (lean / verbose modes).
- `.protocol/handoffs/_template/` (12 files).
- `WP-000-example-health-endpoint/` (populated example).
- Foundation docs: `PROTOCOL.md`, `AGENTS.md`, `CLAUDE.md`, `OPENCODE.md`.
