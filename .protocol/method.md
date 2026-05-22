# TCAD-H Method Specification

The formal method that every Work Package must traverse.

Mental brand: **TCAD** (4 letters, public).
Operational phases: **R-T-C-A-D-V-L** (7 phases, internal).

---

## R — Recall

**Owner**: Conductor.
**Inputs**: `AGENTS.md`, `.protocol/method.md` (this file), `.protocol/boundaries.yaml`, `.protocol/status.json`, last 3 entries of `.protocol/journal/INDEX.md` (when present), `.protocol/questions/INDEX.md`.
**Output**: Conductor internal state. No file artifact yet.
**Gate**: Conductor confirms it has loaded the stable prefix. No conversation history is used.

This is the cache-friendly phase. The stable prefix loaded here should not change mid-task so that the prompt cache stays warm across Work Packages.

---

## T — Translate

**Owner**: Conductor (with human approval).
**Inputs**: human request, recalled state.
**Output**: `specs/<id>/spec.md`.
**Gate**: Human approves spec or the Conductor iterates (max 3 cycles).

The spec must answer:

- User intent in one paragraph.
- Business goal or technical motivation.
- Non-goals (out of scope).
- Acceptance criteria (testable bullets).
- Risk level (`low` / `medium` / `high`) based on `.protocol/graph_rules.yaml`.

---

## C — Context

**Owner**: Conductor.
**Inputs**: spec, repo tree, journal recall, boundaries.
**Output**:

- `.protocol/handoffs/WP-NNN-*/00_context.md`
- `.protocol/handoffs/WP-NNN-*/04_existing_decisions.md`
- Reuse score (target ≥ 0.6 for `AUTO_GO`).

**Gate**: Reuse score computed; impacted files identified; no forbidden zones touched.

The Conductor lists reusable components, restrictions, danger zones, and impacted contracts. This phase prevents duplicate components and forbidden edits.

---

## A — Approach

**Owner**: Conductor (with conditional human approval).
**Inputs**: context.
**Output**:

- `specs/<id>/plan.md`
- `.protocol/handoffs/WP-NNN-*/05_worker_prompt_<role>.md` through `09_reviewer_prompt.md`
- `10_acceptance_criteria.md`

**Auto-GO rules**: Conductor may transition to `WORKER_BRIEF` without human approval when ALL hold:

- `reuse_score ≥ 0.6`
- `estimated_diff_loc < 200`
- `no_denied_paths_touched`
- `contracts_changed == false`
- `risk_level == low`

Otherwise the human reviews and approves.

---

## D — Develop

**Owner**: Worker CLI (OpenCode / Kimi / Qwen / DeepSeek / GPT / Minimax).
**Inputs**: ONLY the Work Package files (`00`–`10`).
**Output**:

- Code changes on branch `wp/NNN-<slug>`.
- `.protocol/handoffs/WP-NNN-*/11_worker_summary.md`
- `.protocol/handoffs/WP-NNN-*/12_delta.md` (if scope discovery)
- `.protocol/handoffs/WP-NNN-*/13_blockers.md` (if blocked)

**Gate**: Worker writes `11_worker_summary.md` with `NEXT STEP: ready for review`, OR escalates via `12_delta.md` / `13_blockers.md`.

The worker NEVER receives conversation history. The worker ONLY reads the Work Package folder.

---

## V — Verify

**Owner**: Reviewer Agent (different CLI/model than Worker).
**Inputs**:

- `09_reviewer_prompt.md`
- `10_acceptance_criteria.md`
- `11_worker_summary.md`
- `15_diff.patch` (Phase 2+)
- `18_impact_map.md` and `20_reviewer_focus.md` (Phase 2.5+)
- Selected files from `15_diff.patch` for high-risk areas only.

**Output**: `14_review_result.md` with verdict `PASS` / `PASS_WITH_NOTES` / `FAIL`.
**Gate**: PASS or PASS_WITH_NOTES → proceed to Log. FAIL → return to Develop with `FIX_REQUEST` (max 3 cycles before escalation to human).

The reviewer must be a different CLI/model than the implementer. No self-validation.

---

## L — Log

**Owner**: Conductor.
**Inputs**: closed Work Package.
**Output**:

- `.protocol/journal/YYYY-MM-DD-NNN.md` (sharded entry)
- Update `.protocol/journal/INDEX.md`
- Atlas update (Phase 2.5c): merge into `.protocol/atlas/atlas.json`
- Update `.protocol/status.json` to `IDLE` with `active_wp: null`

**Gate**: Journal entry exists with required frontmatter (id, date, agent, spec, tags, contracts_touched, files, tokens_used, status).

---

## Phase-to-state map

| Phase | FSM state |
|---|---|
| R | (transient, no state) |
| T | `INTAKE` → `SPEC_DRAFT` |
| C | `HANDOFF_GEN` |
| A | `HANDOFF_GEN` → `WORKER_BRIEF` |
| D | `WORKER_BRIEF` → `WORKER_DONE` |
| V | `ATLAS_GEN` → `REVIEWING` → `{PASS|NOTES|FAIL}` |
| L | `LOG` → `DONE` → `IDLE` |

See `.protocol/conductor.yaml` for the canonical transition table.

---

## The 5 questions revisited

Every phase answers part of the 5 questions:

1. **What is being built?** → T
2. **What can the agent touch?** → C
3. **What actually changed?** → D + atlas
4. **What impact does it have?** → V + atlas
5. **What should the human review or ask?** → V + questions protocol

If a phase cannot answer its share, the Work Package does not graduate.

---

## Failure protocols

- **Worker blocked** → `13_blockers.md` → Conductor reads → either patches the Work Package or escalates to human.
- **Worker discovers WP is wrong** → `12_delta.md` → Conductor reviews → rewrites WP or escalates.
- **Reviewer FAIL** → `FIX_REQUEST` cycle, max 3 attempts. After 3rd, escalate to human.
- **Atlas generation fail** → reviewer proceeds without graph but flags `ATLAS_FAIL` in `14_review_result.md`.
- **Boundary violation detected** → Conductor refuses to advance state; opens question in `.protocol/questions/INDEX.md`.

---

## Cache discipline

To preserve Anthropic prompt-cache hits:

- Files loaded in **R** (Recall) must not change mid-Work-Package.
- Append-only artifacts (`11_worker_summary.md`, `12_delta.md`, `journal/*.md`) are added at the tail of the context, never inserted into the cached prefix.
- Cross-Work-Package context (status.json, journal index) is referenced by path, not inlined.
