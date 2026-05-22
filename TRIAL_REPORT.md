# TCAD-H Phase 2.1 Trial Report

**Date:** 2026-05-22
**Trial type:** dogfood (3 WPs run through TCAD-H against TCAD-H itself + synthetic conflict)
**Framework version:** v2.4 post Phase 2 + audit fixes
**Trial duration (wall-clock, automated):** ~5 seconds across 3 WPs
**Trial duration (real human + worker time):** would be hours; the automation only stress-tests the harness

---

## TL;DR

> The harness works end-to-end and caught one critical class of failure (merge conflict).
> It also revealed **5 real bugs / UX gaps** in 3 WPs.
> Phase 2.5 is not the next priority. Fixing the 5 findings is.

---

## What was tested

| WP | Goal | Role | Mode | Outcome |
|---|---|---|---|---|
| WP-001 | Add "quick stats" block to `tcad_log close` output | tests | lean (5 files) | shipped + merged + verified in WP-002 |
| WP-002 | Studio events panel reading `events.jsonl` | frontend | lean (5 files) | shipped + merged + hotfix needed |
| WP-003 + WP-004 | Conflict test — two worktrees both edit `shared_module.txt` | backend/frontend | lean | conflict correctly blocked |

---

## Measurements (automated wall-clock, no human in loop)

| Phase | WP-001 | WP-002 | WP-003+004 |
|---|---:|---:|---:|
| `tcad_handoff` generate | 0.07s | 0.08s | 0.14s (2 WPs) |
| Setup: yaml fill + FSM + worktree | 0.50s | 0.49s | 0.33s |
| Worker edits | 0.05s | 0.21s | 0.04s |
| Worker summary write | 0.01s | 0.01s | — |
| Boundary check | 0.07s | 0.07s | — |
| `tcad_log close` | 0.08s | 0.10s | — |
| Merge + cleanup | 0.26s | 0.18s | 0.33s (incl. conflict refusal) |
| **Total cycle (no human)** | **~0.5s** | **~0.6s** | **~0.85s** |

Human time was zero in this trial. Real-world: minutes/hours per WP.

---

## Findings

### Finding #1 — `tcad_conduct set-wp` validates verbose template on lean WP

**Severity:** medium
**Location:** `scripts/tcad_conduct.py` :: `cmd_set_wp`
**Symptom:**
```
Error: WP WP-001-improve-close-summary is missing required files:
  00_context.md, 04_existing_decisions.md, 05_worker_prompt_backend.md,
  06_worker_prompt_frontend.md, 08_worker_prompt_reading.md, 09_reviewer_prompt.md,
  21_open_questions.md
Use --force to set anyway.
```
**Root cause:** `wp_required_files()` returns the full 12-file VERBOSE_FILES list, but `tcad_handoff --lean` writes 5 files. The conductor doesn't know about lean mode.
**Workaround used:** `--force`
**Fix:** Detect mode (sniff for `{wp}/00_context.md` to distinguish verbose from lean) and validate the matching set.

### Finding #2 — Scripts launched from inside a worktree use stale `.protocol/status.json`

**Severity:** medium
**Location:** all scripts that resolve paths via `SCRIPT_PATH.parent.parent`
**Symptom:** `tcad_log close` from worktree returned `Worktree/slug not found` even though the worktree was registered in main repo's `status.json`.
**Root cause:** `SCRIPT_PATH.parent.parent` resolves to the worktree's root because the script file is copied along with the tree. The worktree contains a stale `.protocol/status.json` snapshot.
**Fix options:**
  1. Detect when ROOT is a worktree and walk up to main repo (`git rev-parse --git-common-dir`).
  2. Document strictly: all `tcad_*` scripts must run from main repo root.
  Option 1 is correct.

### Finding #3 — META-SUCCESS — closed-loop self-improvement

**Severity:** positive
**Evidence:** WP-001 added a "quick stats" block to `tcad_log close`. After merging WP-001, when closing WP-002 the new output appeared:
```
quick stats:
  files:  4 changed
  tests:  1 run
  top:    studio/server.py, studio/index.html, studio/app.js
```
The framework improved itself through itself. This is the dogfood validation we wanted.

### Finding #4 — CRITICAL — boundary firewall passed a buggy patch

**Severity:** high
**Symptom:** WP-002 worker added a function that referenced `PROTOCOL_DIR`, which was not defined in `studio/server.py`. Boundary firewall passed (all changed paths were in `02_allowed_files.md`). `tcad_log close` passed (summary was complete). Patch merged. Import-time check FAILED at runtime.
**Implication:** the firewall catches PATH violations, not SEMANTIC violations. The worker's self-test (`py_compile`) only verified syntax — Python resolves names at call time, so `PROTOCOL_DIR` being undefined wasn't caught.
**What would have caught it:** an actual reviewer agent running the file or running tests that import it. The framework does NOT do this today.
**Hotfix:** added `PROTOCOL_DIR = ROOT / ".protocol"` to `server.py`.
**Long-term fix:** Phase 3 reviewer agent must run an import smoke test, or `tcad_log close` must require a non-trivial test command.

### Finding #5 — CONFLICT DETECTED AND BLOCKED (audit #7 closed in principle)

**Severity:** positive
**Test:** WP-003 backend + WP-004 frontend both modify `shared_module.txt`.
**Result:**
  - Merge A: `ff-only` succeeded.
  - Merge B: `fatal: Not possible to fast-forward, aborting.`
  - Master content = A's version. B's content preserved in `wp/WP-004-conflict-b-frontend` branch.
  - **No corruption.**
**Verdict:** the harness defends master through `ff-only`. The most-feared mentor concern is structurally resolved.
**Gap:** see Finding #6.

### Finding #6 — UX gap on conflict refusal

**Severity:** medium
**Symptom:** when merge B failed, the user got raw git output:
```
fatal: Not possible to fast-forward, aborting.
```
No event emitted, no open question created, no guidance.
**Fix:** `tcad_worktree.py merge` should:
  1. Catch ff-only failure
  2. Append `merge_conflict_detected` event to `events.jsonl`
  3. Append open question to `.protocol/questions/INDEX.md` with both branches as evidence
  4. Print suggested resolution: rebase B onto new master OR file a follow-up WP-NNN-resolve-conflict
**Scope:** ~20 LOC patch to `cmd_merge`.

---

## What the trial validated

| Claim | Evidence |
|---|---|
| Lean mode reduces friction | 5 files vs 12, generation in <0.1s |
| Worktrees prevent cross-WP contamination | WP-003+004 isolated, only first merge accepted |
| `tcad_log close` produces traceable evidence | 962-byte patch + journal entry + close_report.json per WP |
| Conductor FSM stays intact through external script edits | All 3 WPs left FSM functional |
| events.jsonl captures full audit trail | 11 events recorded across 3 WPs |
| Studio reads merged framework changes | `read_events_tail` available after WP-002 merge (post-hotfix) |
| The framework can improve itself through itself | Finding #3 (meta-success) |

---

## What the trial did NOT prove

- The framework helps a HUMAN go faster. Trial was automated; no developer was in the loop.
- The framework works on a real external (non-self) project. Deferred — no external repo available locally.
- The semantic correctness layer (Phase 3 reviewer agent) catches bugs. **It doesn't exist yet** — Finding #4.
- Multi-CLI parallel really avoids race conditions in the wild. Synthetic conflict was sequential; real parallel CLIs not tested.

---

## Recommendations — what to build BEFORE Phase 2.5

Ordered by leverage. None of these is "more architecture". All close gaps found in the trial.

1. **Fix Finding #1** (lean mode set-wp). 10 LOC. ~15 min.
2. **Fix Finding #2** (worktree script reroute). ~30 LOC. ~1 hour.
3. **Fix Finding #6** (conflict UX in `tcad_worktree.py merge`). ~30 LOC. ~1 hour.
4. **Address Finding #4** (semantic gate). Hardest. Options:
   a. `tcad_log close` runs an `--smoke-test` command listed in `10_acceptance_criteria.md`.
   b. Phase 3 minimum: write `tcad_review.py` that, at minimum, runs `pytest -q` if present.
5. **Run a real external WP** on Synthetic Lab / Zero Voice / any non-self repo. Audit #7 partial close requires REAL parallel CLIs, not synthetic.

**Estimated cost to close gaps 1–4:** ~1 working day.
**Decision point:** after gaps closed + 1 external WP, re-evaluate Phase 2.5 (atlas) vs declare Phase 2 done.

---

## Honest verdict

The trial confirms mentor's framing:

> *"TCAD-H ya puede coordinar trabajo. Ahora tiene que demostrar que mejora el trabajo."*

- Coordination: **proven** (5 of 6 findings positive or actionable; conflict blocked correctly).
- Improvement: **not yet measured**. Requires human-in-loop trial on real external project.

Next move is NOT Atlas. Next move is closing the 5 findings + 1 external trial. Then decide.

---

## Appendix — raw measurement log

See `/tmp/trial/measurements.txt` (ephemeral) or rerun:

```bash
# Replay (lossy — paths and timing vary):
python3 scripts/tcad_handoff.py --lean --name X --goal "..." --role backend
python3 scripts/tcad_conduct.py set-wp WP-NNN-X --force
python3 scripts/tcad_worktree.py create WP-NNN-X --role backend
# ... worker edits in .protocol/worktrees/WP-NNN-X-backend ...
python3 scripts/tcad_log.py close WP-NNN-X-backend
python3 scripts/tcad_worktree.py merge WP-NNN-X-backend
python3 scripts/tcad_worktree.py destroy WP-NNN-X-backend
```
