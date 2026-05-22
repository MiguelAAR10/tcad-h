# Field Trial — TCAD-H v0.1.0-alpha

Append-only log. One section per Work Package run during the trial.
See `FIELD_TRIAL_PLAN.md` for the rules and goal.

---

## Trial WP template (copy below the next horizontal rule)

```markdown
## WP-NNN — <slug>

- Repo:          /path/to/repo
- Profile:       lean | verbose
- Role:          backend | frontend | tests | reading
- Goal:          one-line
- Date:          YYYY-MM-DD
- Conductor:     claude-code (or other)
- Worker CLI:    opencode + <model>
- Reviewer CLI:  <CLI/model — must differ from worker>

### Timings (wall-clock minutes, human time)

| Phase | Minutes |
|---|---:|
| setup (init/profile/doctor)            |  |
| wp create + fill scope                 |  |
| worktree create                        |  |
| worker (incl. read + edits + summary)  |  |
| close + smoke + review                 |  |
| graph build                            |  |
| merge + destroy                        |  |
| atlas build                            |  |

### Diff size

- files changed:
- lines added:
- lines removed:

### Commands actually typed (count)

- count:

### Gate outcomes

- boundary firewall:    pass | hard | soft
- smoke:                 pass | fail | skipped     (groups: ...)
- review:                pass | FAIL | skipped     (critical findings: N)
- merge preconditions:   pass | fail | skipped
- merge ff:              pass | conflict

### Findings

- (paste any structured findings or copy from `review_report.json`)

### Friction

- (free text — anything that slowed you down, confused you, made you
  reach outside the TCAD-H flow)

### Did Studio help?

- (yes/no + one line explaining how)

### Did Atlas reveal anything?

- (yes/no + one line)

### Did `tcad doctor` flag anything actionable?

- (yes/no + one line)

### Verdict

- keep | simplify | drop | unclear

### Notes for next trial

- (one or two bullets)
```

---

(start of real trial log below this line)
