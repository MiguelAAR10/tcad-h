# 10 — Acceptance Criteria

<!--
Testable bullets. Each must map to either a command that returns 0, a file
that must exist with expected content, or a behavior verifiable by a test.

The reviewer uses this file as the source of truth for PASS / FAIL.
-->

## Functional criteria

- [ ] Criterion 1 — (testable, e.g. `pytest tests/test_x.py::test_y` returns 0)
- [ ] Criterion 2 — (e.g. `GET /api/foo` returns 200 with shape `{...}`)
- [ ] Criterion 3 — (e.g. file `path/to/X.py` exists and exports `func_y`)

## Non-regression criteria

- [ ] All previously passing tests still pass
- [ ] Build succeeds: `pnpm build` / `pytest` / `cargo build` (per stack)
- [ ] No file outside `02_allowed_files.md` was modified

## Quality criteria

- [ ] No new dependencies added (or new deps are documented in `04_existing_decisions.md`)
- [ ] No console.log / print() debugging artifacts left in code
- [ ] No `// TODO` or `# TODO` introduced without an open issue or question

## Documentation criteria

- [ ] `11_worker_summary.md` exists and follows OPENCODE.md format
- [ ] Any new public function has a one-line docstring (no novels)
- [ ] If a contract was changed, it is noted in `11_worker_summary.md` § DECISIONS MADE

## Commands used to verify

(Conductor lists the exact commands the reviewer should run, in addition to
the inspection of `15_diff.patch` and `18_impact_map.md`.)

- `git diff --name-only main..HEAD` — verify file list matches `02_allowed_files.md`
- `pytest -q` — verify no regressions
- (other repo-specific commands)
