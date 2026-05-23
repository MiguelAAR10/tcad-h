# Field Trial Plan — TCAD-H v0.1.0-alpha

**Status:** active until a real decision report is produced.
**Owner:** the human running TCAD-H day-to-day.
**Rule:** no feature development during this trial. Bug fixes only if a
trial WP is blocked.

---

## Why this trial exists

Mentor verdict after Phase 3.4:

> *"TCAD-H ya tiene motor y llave. Ahora falta manejarlo una semana en
> carretera real."*

Until this trial closes, every "should we build X" question gets the same
answer: **no — use it first**.

## Goal

Run 3 to 5 real Work Packages across at least 2 repos and answer:

1. Does TCAD-H reduce recontextualization for the human?
2. Does it reduce review effort on the diff?
3. Does it catch real semantic problems (duplicates, scope creep)?
4. Where does it generate ritual without value?
5. What is missing for daily use?

## Scope discipline

- **No** Mermaid.js render.
- **No** MCP integration.
- **No** LLM semantic enrichment.
- **No** new detectors unless a trial WP is blocked.
- **No** Studio redesign.
- **No** packaging refactor.
- Bug fixes only if they unblock a real trial WP.

## Required WP mix

| Slot | Type | Repo | Notes |
|---|---|---|---|
| WP A | backend / script | framework or external | small endpoint, helper, or script |
| WP B | frontend / UI | edu-app or another | empty state, loading state, microcopy |
| WP C | docs / tests | any | doc string, single test, README section |
| WP D | refactor (optional) | any | move function, deduplicate logic |
| WP E | bug fix (optional) | any | a real issue surfaced by `tcad doctor`/`smoke` |

At least 3 of the 5 must close cleanly. At least 1 must surface a real
finding (smoke fail, review fail, conflict, or boundary violation) so the
trial validates the gate, not just the pipeline.

## Inputs to record per WP

Every WP fills `FIELD_TRIAL.md` (one row each). Capture:

- WP id and slug
- Repo
- Goal
- Wall-clock time per phase (setup, worktree, worker, close, merge)
- Lines of code in diff
- Commands typed manually
- Friction encountered (free text)
- Did Studio help reviewing?
- Did Atlas reveal anything useful?
- Did `tcad doctor` flag anything actionable?
- Verdict: keep / simplify / drop

## Outputs of the trial

When 3+ WPs are complete:

1. `FIELD_TRIAL.md`         — append-only log, one section per WP.
2. `FRICTION_REGISTER.md`   — deduplicated list of frictions across WPs.
3. `DECISION_REPORT.md`     — final recommendation: keep / simplify / expand.

## Schedule

| Day | Activity |
|---|---|
| 1 | Pick 2 repos, write `FIELD_TRIAL.md` first stub, run WP A on framework or simple project. |
| 2 | WP B on UI / Next.js / Angular repo. |
| 3 | WP C on docs/tests. |
| 4 | WP D refactor (or skip). |
| 5 | WP E real bug (or skip). |
| 6 | Consolidate `FRICTION_REGISTER.md`. |
| 7 | Write `DECISION_REPORT.md`. |

Total: 5 working days + 2 wrap-up. Adjust if needed; do not start new
phases before `DECISION_REPORT.md` exists.

## How to abort

If a WP gets stuck because of a TCAD-H bug:

1. Log the friction in `FIELD_TRIAL.md`.
2. Patch the bug minimally.
3. Re-run the WP.
4. Do NOT add new features while patching — note them in the register.

If three WPs in a row produce no useful signal, stop and rethink. The
trial is to learn, not to perform.

## Definition of done

`DECISION_REPORT.md` exists and answers literally:

1. Should TCAD-H continue? Keep / Simplify / Drop.
2. If keep, what is the highest-value next feature based on real friction?
3. If simplify, which scripts / docs / panels can be removed without losing core value?
4. If drop, what was the actual failure mode?

The trial is closed when this report lands and is committed.
