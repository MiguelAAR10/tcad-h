# TCAD-H v0.1.0-alpha — Release Notes

**Status:** alpha — installable local harness, not a public release.

This is the first release packaged for use outside the framework's own repo.
It is intended for one user (you), or a tightly controlled small group,
running the pipeline against real codebases for validation.

---

## What is ready

| Capability | Status |
|---|---|
| Multi-CLI Work Package generation (lean / verbose) | Ready |
| Git worktree isolation per WP+role | Ready |
| Conductor FSM (deterministic Python, zero LLM) | Ready |
| Boundary firewall (path-level, OS-enforced) | Ready |
| Smoke-test gate (configurable shell commands) | Ready |
| Deterministic reviewer gate (duplicate routes/symbols) | Ready |
| Evidence capture (diff.patch + journal + close report) | Ready |
| Per-WP static graph (no LLM, no inference beyond manifests) | Ready |
| Cross-WP atlas (heatmap, hotspots, timeline) | Ready |
| Project profile detection (fastapi, next, react, monorepo, etc.) | Ready |
| Studio localhost UI (vanilla HTML/CSS/JS, no build step) | Ready |
| `tcad` CLI unified entrypoint | Ready (this release) |
| `tcad doctor` repo health check | Ready (this release) |
| `install.sh` local installer | Ready (this release) |
| End-to-end on TCAD-H itself (dogfood) | Verified |
| End-to-end on one external repo (edu-app trial) | Verified |

## What is NOT ready

| Capability | Status |
|---|---|
| Public package on PyPI | Not implemented |
| Cross-file duplicate detection | Not implemented |
| Flask / Django / NestJS route detectors | Not implemented |
| Capability registry + LLM enrichment | Deferred (Phase 5+) |
| Mermaid.js visual render in studio | Deferred (currently `<pre>` only) |
| MCP server integration | Deferred |
| Multi-user / team mode | Not designed |
| Windows native install | Not tested (POSIX-only paths in some scripts) |
| Performance with 50+ WPs | Not benchmarked |
| OpenCode + Claude Code integration tested live | Documented, not benchmarked |

## Install

```bash
git clone <this-repo> ~/.tcad-h
cd ~/.tcad-h
./install.sh
# adds tcad to ~/.local/bin (or asks for confirmation before symlinking)

# Verify
tcad --version
tcad doctor
```

## First use in a fresh repo

```bash
cd /path/to/your/project
tcad init
tcad profile detect
tcad doctor
# read docs/QUICKSTART.md for a 10-minute walkthrough
```

## Iron rules still apply

These have not changed:

1. No model receives conversation history. All inputs are versioned files.
2. The Conductor never writes production code.
3. The Reviewer is never the Implementer.
4. Open blocking questions halt progress.
5. No file edited outside the active Work Package's `02_allowed_files.md`.

See `PROTOCOL.md` for the full spec.

## Known limitations of this alpha

- **Smoke tests for foreign projects.** `.protocol/smoke_tests.yaml` ships with
  TCAD-H's own commands. You will need to author smoke groups for each target
  project. There is no auto-generation today.
- **WP template assumes a generic layout.** The lean handoff works in any
  repo, but `02_allowed_files.md` / `03_forbidden_files.md` still have to be
  filled by a human.
- **Atlas is single-repo.** Cannot compose graphs from multiple repos yet.
- **Studio is read-only.** No "transition" buttons; FSM is driven by CLI.
- **Reviewer gate is conservative.** FastAPI + Express duplicate routes and
  Python duplicate top-level functions/classes. Misses many real semantic
  issues. Treat it as a useful filter, not a complete reviewer.
- **events.jsonl grows forever.** No rotation yet. Hand-truncate if it gets
  large.

## Honest framing

This is alpha because the **pipeline works end-to-end** and has been
validated on both the framework itself (dogfood) and a real external repo
(edu-app trial that found Finding #11). It is NOT release-ready because:

- One external repo trial is not "broadly tested".
- No third party has run it.
- No `tcad doctor` failure modes have been catalogued from the field.
- Documentation is functional but not friendly.

Treat 0.1.0-alpha as a personal tool worth using. Do not promise it to anyone.

## What's next (not in this release)

- 0.2.0 — Mermaid.js visual render + Studio improvements.
- 0.3.0 — Cross-file duplicate detection + Flask/Django route detectors.
- 0.4.0 — Optional LLM enrichment (etiqueta only, never invents structure).
- 0.5.0 — MCP server exposing the protocol artifacts.
- 1.0.0 — Public release. Requires a usage cohort and a stability period
  that does not exist yet.
