# Open Questions — Global Index

Blocking questions raised by the Conductor or by Workers/Reviewers. Cross-Work-Package.

> Rule: the Conductor cannot transition out of `REVIEWING`, `FIX_REQUEST`, `ESCALATE`, or `REWRITE_WP` while any question with `Blocks: <state>` is unanswered.

---

## Status legend

- 🟡 **pending** — Question raised, awaiting answer.
- 🔵 **answered** — Answered, awaiting Conductor to apply the resolution.
- ✅ **resolved** — Conductor applied the resolution; question archived to `ANSWERED.md`.

---

## Q-ID format

`Q-NNN` where NNN is a zero-padded sequence number per repo. Sequence persists across Work Packages.

---

## Template

```markdown
## Q-NNN — <short title>

**Status**: 🟡 pending
**Raised by**: <conductor | worker | reviewer>
**Work Package**: WP-NNN-slug (or `none` if global)
**Raised at**: YYYY-MM-DDTHH:MM:SSZ

**Evidence**:
- file:line or path
- worker_summary excerpt
- atlas signal

**Question**:
A specific actionable question with one of: yes/no, choose A/B/C, or fill-in-X.

**Blocks**: <state-name | nothing>

**Answer**:
(filled by human)

**Resolved by**: <conductor-action | wp-rewrite | escalate>
```

---

## Current open questions

## Q-001 — Should /health include version field?

**Status**: 🟡 pending
**Raised by**: conductor
**Work Package**: WP-000-example-health-endpoint
**Raised at**: 2026-05-22T03:06:01.249468+00:00

**Evidence**:
- (auto-generated from tcad_conduct.py add-question)

**Question**:
Should /health include version field?

**Blocks**: REVIEWING

**Answer**:
(pending)

---

## How to add a question

1. Append a new entry above this line using the Template.
2. Increment Q-NNN.
3. If the question is tied to a specific Work Package, also append a reference to `.protocol/handoffs/WP-NNN-*/21_open_questions.md`.
4. If the question blocks state progression, set `Blocks:` to the FSM state that must wait.

## How to answer a question

1. Fill the `Answer:` field.
2. Change `Status:` to `🔵 answered`.
3. Notify the Conductor (or wait for the next `tcad_conduct.py status` poll).
4. Conductor applies the resolution and changes `Status:` to `✅ resolved`, then moves the block to `ANSWERED.md`.

## Q-MC-WP-002-fix6-b-frontend — Merge conflict on wp/WP-002-fix6-b-frontend

**Status**: 🟡 pending
**Raised by**: worktree merge
**WP**: WP-002-fix6-b
**Blocks**: merge

**Evidence**:
```
hint: Diverging branches can't be fast-forwarded, you need to either:
hint: 
hint: 	git merge --no-ff
hint: 
hint: or:
hint: 
hint: 	git rebase
hint: 
hint: Disable this message with "git config advice.diverging false"
fatal: Not possible to fast-forward, aborting.
```

**Question**: base 'master' advanced after this worktree was created. Choose: rebase, no-ff merge, or split into contract WP.

## Q-REV-WP-002-graph-test-dup-tests — Reviewer gate blocked WP-002-graph-test-dup-tests

**Status**: 🟡 pending
**Raised by**: tcad_review
**Blocks**: close, merge

**Evidence**:
- duplicate_symbol: Function 'load_yaml' declared 2 times in /home/miguel/projects/framework/.protocol/worktrees/WP-002-graph-test-dup-tests/studio/server.py. Modify the existing one instead of adding a duplicate.
    at /home/miguel/projects/framework/.protocol/worktrees/WP-002-graph-test-dup-tests/studio/server.py:244
    at /home/miguel/projects/framework/.protocol/worktrees/WP-002-graph-test-dup-tests/studio/server.py:664

**Question**: should the WP modify the existing implementation instead of duplicating? Or is this an intentional override (document in 04_existing_decisions.md)?

## Q-REV-WP-002-studio-dup-tests — Reviewer gate blocked WP-002-studio-dup-tests

**Status**: 🟡 pending
**Raised by**: tcad_review
**Blocks**: close, merge

**Evidence**:
- duplicate_symbol: Function 'load_yaml' declared 2 times in /home/miguel/projects/framework/.protocol/worktrees/WP-002-studio-dup-tests/studio/server.py. Modify the existing one instead of adding a duplicate.
    at /home/miguel/projects/framework/.protocol/worktrees/WP-002-studio-dup-tests/studio/server.py:244
    at /home/miguel/projects/framework/.protocol/worktrees/WP-002-studio-dup-tests/studio/server.py:664

**Question**: should the WP modify the existing implementation instead of duplicating? Or is this an intentional override (document in 04_existing_decisions.md)?
