# 🛠️ TCAD-H — Full CLI Reference

Every subcommand of `tcad`. Run any with `--help` for flags.

## 🧭 Setup

```
tcad init                          Bootstrap .protocol/ in current repo
tcad doctor [--no-suggestions]     Validate repo health + suggest fixes
tcad quickstart                    Print 10-step first-time flow
tcad report alpha [--json]         Digest of repo state + next action
```

## 🔍 Project profile

```
tcad profile detect [--force]      Detect type from manifests
tcad profile show                  Print current profile
tcad profile validate              Verify layer globs match real files
```

## 📦 Work Packages

```
tcad wp create  [--lean] --name X --goal "..." --role <r>
tcad wp set     <wp-id>
tcad wp status
```

## 🎼 Conductor FSM

```
tcad conduct init
tcad conduct status
tcad conduct transition <STATE>
tcad conduct add-question <title> --blocks <state>
tcad conduct resolve-question <id> --resolution "..."
tcad conduct guards
```

State machine:
```
IDLE → INTAKE → SPEC_DRAFT → HANDOFF_GEN → WORKER_BRIEF
  → WORKER_DONE → ATLAS_GEN → REVIEWING
  → {PASS | PASS_WITH_NOTES | FAIL}
  → {LOG | FIX_REQUEST | ESCALATE}
  → DONE → IDLE
```

## 🌳 Worktrees

```
tcad worktree create  <wp> --role <r>
tcad worktree list
tcad worktree inspect <slug>
tcad worktree merge   <slug> [--no-ff] [--skip-checks]
tcad worktree destroy <slug> [--force] [--archive-patch] [--keep-branch]
tcad worktree prune
```

## ✅ Evidence + Gates

```
tcad close <slug>
    [--smoke-test "CMD"]      explicit smoke command (repeatable)
    [--smoke-group GROUP]     run named group from smoke_tests.yaml
    [--skip-smoke]            record-only
    [--review]                run reviewer gate (default)
    [--skip-review]
    [--force]                 ignore gate failures
```

## 🛡️ Reviewer (deterministic)

```
tcad review routes  <file>         List HTTP routes; flag duplicates
tcad review symbols <file>         List Python symbols; flag dupes
tcad review inspect <slug>         Full diff-aware WP review
```

## 🗺️ Graph + Atlas

```
tcad graph build <wp>              Per-WP code_graph.json + mermaid.md
tcad graph show  <wp>              Print mermaid

tcad atlas build                   Compose cross-WP atlas
tcad atlas show [--json]           Print atlas summary
```

## 👀 Watcher

```
tcad scan once [-v]
tcad scan loop [--interval N]
tcad scan tail [--n N]
```

## 🚧 Boundaries

```
tcad boundaries check
    [--staged]                check staged files only
    [--files A B ...]         check explicit list
    [--rollback]              git checkout -- on hard violation
    [--strict]                exit 3 on soft violation
    [--json]
```

## 📺 Studio

```
tcad studio [--port N]             Localhost dashboard (default :8765)
```

## ⚙️ Exit codes (common across scripts)

| Code | Meaning |
|---:|---|
| 0 | success |
| 1 | bad args |
| 2 | not found (WP / file / repo) |
| 3 | refused (would overwrite) |
| 4 | validation failed |
| 5 | smoke gate / reviewer gate failed |
| 6 | merge preconditions failed |

## 🔑 Environment

| Var | Effect |
|---|---|
| `TCAD_HOME` | Override framework root (where scripts live). |
| `TCAD_ROOT` | Override target repo root (where `.protocol/` is). |
| `TCAD_INSTALL_DIR` | Override `install.sh` symlink target (default `~/.local/bin`). |
