# 🧪 TCAD-H Trials

This directory contains every formal trial run on TCAD-H. Each trial
captured measurements, findings, and a written verdict.

## Trial ledger

| Trial | When | What it proved |
|---|---|---|
| [`PHASE_2.1_DOGFOOD.md`](./PHASE_2.1_DOGFOOD.md) | Phase 2.1 | TCAD-H runs end-to-end against itself. 6 findings, 4 critical fixed in Phase 2.2. |
| [`PHASE_2.3_EXTERNAL.md`](./PHASE_2.3_EXTERNAL.md) | Phase 2.3 | First external repo trial (edu-app). Caught Finding #11 — silent duplicate route. Drove Phase 2.4 reviewer gate. |
| [`FIELD_TRIAL_PLAN.md`](./FIELD_TRIAL_PLAN.md) | Phase 3.5 (current) | Rules for the usage week. No new features until decision lands. |
| [`FIELD_TRIAL.md`](./FIELD_TRIAL.md) | Phase 3.5 | Append-only per-WP log. |
| [`FRICTION_REGISTER.md`](./FRICTION_REGISTER.md) | Phase 3.5 | Deduplicated frictions across trial WPs. |
| [`DECISION_REPORT.md`](./DECISION_REPORT.md) | Phase 3.5 | **Pending.** Final verdict: Keep / Simplify / Drop. |

## Why this matters

Every phase shipped on evidence, not opinion. The trials are the evidence.
When [`DECISION_REPORT.md`](./DECISION_REPORT.md) lands, the alpha graduates
(or doesn't). Until then, no new features ship.
