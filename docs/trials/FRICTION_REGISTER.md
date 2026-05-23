# Friction Register — TCAD-H v0.1.0-alpha

Deduplicated friction collected during the field trial. Cross-cuts the
per-WP entries in `FIELD_TRIAL.md`. One row per distinct friction.

Severity convention:
- **block** = trial WP could not finish without a workaround.
- **slow** = trial WP finished but took more time than it should.
- **noise** = unnecessary message or step; no time lost.
- **doc** = the framework works, but the human had to guess.

Resolution status:
- **open** = not addressed yet.
- **patched** = fixed in code during trial.
- **deferred** = will be considered after `DECISION_REPORT.md`.
- **wontfix** = decided not to address.

---

## Template (copy when adding a new friction)

```markdown
## F-NNN — <short title>

- **Severity:** block | slow | noise | doc
- **First seen:** WP-XXX (date)
- **Repeat count:** how many WPs this friction appeared in
- **Description:** what happened in two or three sentences
- **Workaround:** what the human did to keep moving
- **Proposed fix:** one-line suggestion (do not implement during trial)
- **Status:** open | patched | deferred | wontfix
```

---

## Frictions

(none yet — start of trial)
