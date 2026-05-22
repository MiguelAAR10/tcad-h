#!/usr/bin/env python3
"""
tcad_log.py — TCAD-H Evidence Closing Layer.

Phase 2 deliverable. Scope strict per mentor: evidence capture only.
NOT included (intentionally deferred):
    - merge (lives in tcad_worktree.py)
    - atlas / tree-sitter (Phase 2.5)
    - coverage parsing (Phase 2.5b)
    - LLM-based summary (never, by design)

Commands:
    close <slug>            close a WP+worktree, generate evidence + journal
    validate <wp-id>        check evidence completeness without writing
    journal-list            show journal entries (sharded)
    journal-show <id>       print a specific journal entry

What `close` does (deterministic, ordered):
    1. Resolve slug -> WP dir + worktree
    2. Capture `git diff base...branch` into .protocol/handoffs/<wp>/15_diff.patch
       (empty diff is fine — marks NO_CHANGES)
    3. Validate 11_worker_summary.md exists with required sections
    4. Detect 12_delta.md / 13_blockers.md presence
    5. Detect 14_review_result.md verdict
    6. Write .protocol/journal/YYYY-MM-DD-NNN.md with frontmatter
    7. Append wp_evidence_logged event to events.jsonl
    8. Write .protocol/handoffs/<wp>/close_report.json
    9. Leave FSM state alone (tcad_conduct.py owns it; the human transitions)
   10. Print human summary

Exit codes:
    0  success (evidence captured; may be flagged)
    1  bad args
    2  WP / worktree not found
    3  refusing to overwrite existing evidence (use --force)
    4  validation failure (missing 11_summary or other required artifact)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
# Phase 2.2 Finding #2 fix: resolve root via shared helper, not naive parent.parent.
# tcad_log.py may be invoked from a worktree where SCRIPT_PATH.parent.parent
# points to a stale .protocol/ snapshot.
sys.path.insert(0, str(SCRIPT_PATH.parent))  # noqa
from _tcad_root import resolve_tcad_root  # noqa: E402
ROOT = resolve_tcad_root(os.environ.get("TCAD_ROOT"))
PROTOCOL_DIR = ROOT / ".protocol"
STATUS_FILE = PROTOCOL_DIR / "status.json"
EVENTS_FILE = PROTOCOL_DIR / "events.jsonl"
HANDOFFS_DIR = PROTOCOL_DIR / "handoffs"
JOURNAL_DIR = PROTOCOL_DIR / "journal"
JOURNAL_INDEX = JOURNAL_DIR / "INDEX.md"
LOCK_FILE = PROTOCOL_DIR / "status.lock"

sys.path.insert(0, str(SCRIPT_PATH.parent))
from _tcad_lock import status_lock  # noqa: E402
from tcad_check_boundaries import load_yaml, _match_glob  # noqa: E402

SMOKE_FILE = PROTOCOL_DIR / "smoke_tests.yaml"
SMOKE_EXAMPLE = PROTOCOL_DIR / "smoke_tests.yaml.example"

# Required sections in 11_worker_summary.md (OPENCODE.md contract).
REQUIRED_SUMMARY_SECTIONS = [
    "CHANGED FILES:",
    "TESTS RUN:",
    "WHAT PASSED:",
    "WHAT FAILED:",
    "DECISIONS MADE:",
    "RISKS:",
    "NEXT STEP:",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def today() -> str:
    return dt.date.today().isoformat()


def load_status() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return {}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_status(data: dict) -> None:
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def append_event(event: dict) -> None:
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


def resolve_slug(slug: str) -> tuple[Path | None, dict | None]:
    """Return (worktree_dir, worktree_info_from_status) for the slug.

    If no worktree by that slug, try interpreting `slug` as a bare WP id and
    look up its 'backend' worktree by convention.
    """
    state = load_status()
    wt_index = state.get("worktrees", {}) or {}
    if slug in wt_index:
        info = wt_index[slug]
        path = Path(info.get("absolute_path") or info.get("path") or "")
        return (path if path.exists() else None), info

    # Fallback: try <slug>-backend, <slug>-frontend in that order.
    for role in ("backend", "frontend", "tests", "reading"):
        candidate = f"{slug}-{role}"
        if candidate in wt_index:
            info = wt_index[candidate]
            path = Path(info.get("absolute_path") or info.get("path") or "")
            return (path if path.exists() else None), info

    return None, None


def resolve_wp_dir(wp_id: str) -> Path | None:
    candidate = HANDOFFS_DIR / wp_id
    if candidate.is_dir():
        return candidate
    if wp_id.isdigit():
        prefix = f"WP-{int(wp_id):03d}-"
        for child in HANDOFFS_DIR.iterdir():
            if child.is_dir() and child.name.startswith(prefix):
                return child
    return None


def git_diff_patch(worktree_path: Path, base: str, branch: str) -> str:
    """Return `git diff base...branch` as a string. Empty string if no changes."""
    out = subprocess.run(
        ["git", "diff", f"{base}...{branch}"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    return out.stdout


def parse_summary(path: Path) -> dict:
    """Inspect 11_worker_summary.md and return structural info."""
    info = {
        "exists": path.is_file(),
        "missing_sections": [],
        "ready_for_review": False,
        "changed_files": [],
        "tests_run": [],
        "what_failed": [],
    }
    if not info["exists"]:
        info["missing_sections"] = REQUIRED_SUMMARY_SECTIONS[:]
        return info
    text = path.read_text(encoding="utf-8", errors="ignore")
    for sec in REQUIRED_SUMMARY_SECTIONS:
        if sec not in text:
            info["missing_sections"].append(sec)
    info["ready_for_review"] = "NEXT STEP: ready for review" in text
    # Best-effort extraction of CHANGED FILES bullet list.
    m = re.search(r"CHANGED FILES:\s*\n((?:\s*-.+\n)+)", text)
    if m:
        info["changed_files"] = [
            line.strip("- ").strip() for line in m.group(1).splitlines() if line.strip()
        ]
    m = re.search(r"TESTS RUN:\s*\n((?:\s*-.+\n)+)", text)
    if m:
        info["tests_run"] = [
            line.strip("- ").strip() for line in m.group(1).splitlines() if line.strip()
        ]
    m = re.search(r"WHAT FAILED:\s*\n((?:\s*-.+\n)+)", text)
    if m:
        info["what_failed"] = [
            line.strip("- ").strip() for line in m.group(1).splitlines() if line.strip()
        ]
    return info


def select_smoke_commands(
    changed_files: list[str],
    group: str | None,
    explicit: list[str] | None,
) -> tuple[list[str], list[str]]:
    """Pick smoke-test commands deterministically.

    Returns (commands, group_names_used).

    Order of precedence:
      1. explicit --smoke-test commands → use them directly, skip YAML.
      2. --smoke-group <name> → use that group only.
      3. auto-detect: any group whose match_paths globs hit any changed file.
      4. fallback to 'default' group.
    """
    if explicit:
        return list(explicit), ["explicit"]

    cfg = load_yaml(SMOKE_FILE) or load_yaml(SMOKE_EXAMPLE) or {}
    groups = cfg.get("groups", {}) or {}

    if group:
        g = groups.get(group)
        if not g:
            return [], []
        return list(g.get("commands", []) or []), [group]

    # Auto-detect by changed_files vs match_paths globs.
    picked: list[str] = []
    used: list[str] = []
    for gname, gdef in groups.items():
        if gname == "default":
            continue
        match_paths = gdef.get("match_paths", []) or []
        if not match_paths:
            continue
        if any(_match_glob(f, mp) for f in changed_files for mp in match_paths):
            picked.extend(gdef.get("commands", []) or [])
            used.append(gname)

    if not picked:
        # Fallback to default group.
        default = groups.get("default") or {}
        picked = list(default.get("commands", []) or [])
        if picked:
            used.append("default")

    return picked, used


def run_smoke_tests(cmds: list[str], cwd: Path) -> list[dict]:
    """Run each command, return list of {cmd, exit_code, stdout, stderr, ok}."""
    results: list[dict] = []
    for cmd in cmds:
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=str(cwd),
                capture_output=True, text=True, timeout=60,
            )
            results.append({
                "cmd": cmd,
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-2000:],  # last 2KB
                "stderr": proc.stderr[-2000:],
                "ok": proc.returncode == 0,
            })
        except subprocess.TimeoutExpired:
            results.append({"cmd": cmd, "exit_code": 124, "ok": False,
                            "stdout": "", "stderr": "TIMEOUT (60s)"})
        except Exception as exc:
            results.append({"cmd": cmd, "exit_code": -1, "ok": False,
                            "stdout": "", "stderr": str(exc)})
    return results


def parse_review(path: Path) -> dict:
    info = {"exists": path.is_file(), "verdict": None}
    if not info["exists"]:
        return info
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"VERDICT:\s*(\w+)", text)
    if m:
        info["verdict"] = m.group(1)
    return info


def next_journal_seq() -> int:
    """Return next zero-padded sequence number for today's journal entries."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    today_s = today()
    existing = 0
    for f in JOURNAL_DIR.glob(f"{today_s}-*.md"):
        # Parse the trailing -NNN
        m = re.search(r"(\d+)\.md$", f.name)
        if not m:
            continue
        existing = max(existing, int(m.group(1)))
    return existing + 1


def update_journal_index(entry_name: str, takeaway: str) -> None:
    """Append a one-line pointer to journal/INDEX.md (idempotent)."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    if not JOURNAL_INDEX.exists():
        JOURNAL_INDEX.write_text(
            "# Journal Index\n\n"
            "Sharded journal entries. One file per closed Work Package.\n\n"
            "## Entries\n\n",
            encoding="utf-8",
        )
    line = f"- [{entry_name}](./{entry_name}.md) — {takeaway}\n"
    text = JOURNAL_INDEX.read_text(encoding="utf-8")
    if entry_name in text:
        return
    JOURNAL_INDEX.write_text(text + line, encoding="utf-8")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_close(args) -> int:
    wt_path, wt_info = resolve_slug(args.slug)
    if wt_info is None:
        print(f"Worktree/slug not found: {args.slug}", file=sys.stderr)
        return 2
    wp_id = wt_info.get("wp")
    role = wt_info.get("role")
    branch = wt_info.get("branch")
    base = wt_info.get("base") or "master"

    wp_dir = resolve_wp_dir(wp_id) if wp_id else None
    if wp_dir is None:
        print(f"Work Package directory missing: {wp_id}", file=sys.stderr)
        return 2

    # ---- 1. Diff capture -------------------------------------------------
    patch_path = wp_dir / "15_diff.patch"
    if patch_path.exists() and not args.force:
        print(
            f"Refusing: {patch_path.relative_to(ROOT)} already exists. "
            f"Use --force to overwrite.",
            file=sys.stderr,
        )
        return 3

    diff = ""
    if wt_path is not None:
        diff = git_diff_patch(wt_path, base, branch) if branch else ""
    if not diff and wp_id:
        # Worktree gone? Try the branch directly.
        if branch:
            diff = git_diff_patch(ROOT, base, branch)

    is_empty = not diff.strip()
    if is_empty:
        patch_path.write_text(
            f"# NO_CHANGES — diff between {base} and {branch} is empty.\n",
            encoding="utf-8",
        )
    else:
        patch_path.write_text(diff, encoding="utf-8")

    # ---- 2. Inspect evidence files --------------------------------------
    summary_info = parse_summary(wp_dir / "11_worker_summary.md")
    has_delta = (wp_dir / "12_delta.md").is_file() and (wp_dir / "12_delta.md").stat().st_size > 0
    has_blockers = (wp_dir / "13_blockers.md").is_file() and (wp_dir / "13_blockers.md").stat().st_size > 0
    review_info = parse_review(wp_dir / "14_review_result.md")

    # ---- 3. Validation ---------------------------------------------------
    validation_errors: list[str] = []
    if not summary_info["exists"]:
        validation_errors.append("11_worker_summary.md is missing")
    elif summary_info["missing_sections"]:
        validation_errors.append(
            f"11_worker_summary.md missing sections: {summary_info['missing_sections']}"
        )
    if not summary_info["ready_for_review"] and not has_blockers and not has_delta:
        validation_errors.append(
            "11_worker_summary.md does not declare 'NEXT STEP: ready for review' "
            "and no delta/blockers present — worker did not finish a stable state"
        )

    if validation_errors and not args.force:
        print("Validation failed:", file=sys.stderr)
        for e in validation_errors:
            print(f"  ✗ {e}", file=sys.stderr)
        print("\nUse --force to write evidence anyway (validation_errors will appear in the journal entry).", file=sys.stderr)
        return 4

    # ---- 3b. Smoke tests (Phase 2.2 Finding #4 fix) ---------------------
    smoke_cmds, smoke_groups = select_smoke_commands(
        changed_files=summary_info["changed_files"],
        group=getattr(args, "smoke_group", None),
        explicit=getattr(args, "smoke_test", None) or None,
    )
    smoke_results: list[dict] = []
    smoke_skipped = getattr(args, "skip_smoke", False)
    if smoke_cmds and not smoke_skipped:
        cwd_for_smoke = wt_path if (wt_path and wt_path.exists()) else ROOT
        smoke_results = run_smoke_tests(smoke_cmds, cwd_for_smoke)
        failed = [r for r in smoke_results if not r["ok"]]
        if failed and not args.force:
            print("Smoke-test gate FAILED:", file=sys.stderr)
            for r in failed:
                print(f"  ✗ exit={r['exit_code']}  {r['cmd']}", file=sys.stderr)
                if r["stderr"]:
                    for line in r["stderr"].strip().splitlines()[:5]:
                        print(f"      {line}", file=sys.stderr)
            print(
                f"\nGroups: {smoke_groups}. Pass --skip-smoke to skip "
                f"(record-only), --force to ignore.",
                file=sys.stderr,
            )
            return 5

    # ---- 3c. Reviewer gate (Phase 2.4 Finding #11 fix) ------------------
    # Run deterministic reviewer if --review flag is set or by default
    # when not explicitly skipped. Detects duplicate routes / functions /
    # classes that smoke tests cannot catch.
    review_report: dict | None = None
    review_skipped = getattr(args, "skip_review", False)
    review_enabled = (
        getattr(args, "review", False) or not review_skipped
    )
    if review_enabled and not review_skipped:
        reviewer = SCRIPT_PATH.parent / "tcad_review.py"
        if reviewer.is_file():
            proc = subprocess.run(
                [sys.executable, str(reviewer), "inspect", args.slug, "--json"],
                cwd=str(ROOT), capture_output=True, text=True, timeout=60,
            )
            try:
                review_report = json.loads(proc.stdout) if proc.stdout else None
            except json.JSONDecodeError:
                review_report = {"error": "review output not JSON", "raw": proc.stdout[:200]}
            if proc.returncode == 5 and not args.force:
                # Critical findings: block close.
                print("Reviewer gate FAILED:", file=sys.stderr)
                if review_report:
                    crit = [f for f in review_report.get("findings", []) if f.get("severity") == "critical"]
                    for f in crit:
                        print(f"  ✗ {f.get('type')}: {f.get('message','')}", file=sys.stderr)
                print(
                    "\nBlocker question added to .protocol/questions/INDEX.md.\n"
                    "Pass --skip-review to bypass, --force to override.",
                    file=sys.stderr,
                )
                return 6

    # ---- 4. Journal entry ------------------------------------------------
    seq = next_journal_seq()
    entry_name = f"{today()}-{seq:03d}-{wp_id}"
    entry_path = JOURNAL_DIR / f"{entry_name}.md"

    changed_count = len(summary_info["changed_files"])
    if validation_errors:
        takeaway = "(no takeaway — review failed)"
    elif is_empty:
        takeaway = f"closed {wp_id} ({role}) — NO_CHANGES"
    else:
        takeaway = f"closed {wp_id} ({role}) — {changed_count} files"

    frontmatter = {
        "id": entry_name,
        "date": today(),
        "wp": wp_id,
        "role": role,
        "branch": branch,
        "base": base,
        "changed_files": summary_info["changed_files"],
        "tests_run": summary_info["tests_run"],
        "what_failed": summary_info["what_failed"],
        "no_changes": is_empty,
        "verdict": review_info["verdict"],
        "has_delta": has_delta,
        "has_blockers": has_blockers,
        "validation_errors": validation_errors,
        "smoke_groups": smoke_groups,
        "smoke_pass": all(r["ok"] for r in smoke_results) if smoke_results else None,
        "smoke_skipped": smoke_skipped,
        "review_pass": (review_report.get("pass") if review_report else None),
        "review_critical_count": (review_report.get("critical_count") if review_report else None),
        "closed_at": now(),
    }

    body_lines = [
        "---",
    ]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            if not v:
                body_lines.append(f"{k}: []")
            else:
                body_lines.append(f"{k}:")
                for item in v:
                    body_lines.append(f"  - {item}")
        else:
            body_lines.append(f"{k}: {v}")
    body_lines.append("---")
    body_lines.append("")
    body_lines.append(f"## Closed: {wp_id}")
    body_lines.append("")
    body_lines.append(f"**Role:** {role}    **Branch:** `{branch}`    **Base:** `{base}`")
    body_lines.append("")
    if is_empty:
        body_lines.append("Diff is empty — NO_CHANGES.")
        body_lines.append("")
    else:
        body_lines.append(f"Changed {len(summary_info['changed_files'])} file(s). "
                          f"See `.protocol/handoffs/{wp_id}/15_diff.patch`.")
        body_lines.append("")
    if review_info["verdict"]:
        body_lines.append(f"**Reviewer verdict:** `{review_info['verdict']}`")
        body_lines.append("")
    if validation_errors:
        body_lines.append("**Validation errors at close:**")
        for e in validation_errors:
            body_lines.append(f"  - {e}")
        body_lines.append("")
    body_lines.append("See:")
    body_lines.append(f"- `.protocol/handoffs/{wp_id}/11_worker_summary.md`")
    body_lines.append(f"- `.protocol/handoffs/{wp_id}/15_diff.patch`")
    if has_delta:
        body_lines.append(f"- `.protocol/handoffs/{wp_id}/12_delta.md`")
    if has_blockers:
        body_lines.append(f"- `.protocol/handoffs/{wp_id}/13_blockers.md`")
    if review_info["exists"]:
        body_lines.append(f"- `.protocol/handoffs/{wp_id}/14_review_result.md`")

    entry_path.write_text("\n".join(body_lines) + "\n", encoding="utf-8")
    update_journal_index(entry_name, takeaway)

    # ---- 5. close_report.json -------------------------------------------
    close_report = wp_dir / "close_report.json"
    close_report.write_text(
        json.dumps(
            {
                "wp": wp_id,
                "role": role,
                "branch": branch,
                "base": base,
                "patch_path": str(patch_path.relative_to(ROOT)),
                "no_changes": is_empty,
                "patch_bytes": patch_path.stat().st_size,
                "summary": summary_info,
                "review": review_info,
                "has_delta": has_delta,
                "has_blockers": has_blockers,
                "validation_errors": validation_errors,
                "smoke_groups": smoke_groups,
                "smoke_results": smoke_results,
                "smoke_skipped": smoke_skipped,
                "journal_entry": entry_name,
                "closed_at": now(),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    # ---- 6. Events + status update (under lock; FSM untouched) ----------
    append_event({
        "ts": now(), "actor": "tcad_log", "event": "wp_evidence_logged",
        "wp": wp_id, "role": role, "branch": branch,
        "no_changes": is_empty, "journal_entry": entry_name,
        "validation_errors": validation_errors,
    })

    with status_lock(LOCK_FILE):
        state = load_status()
        state.setdefault("evidence", {})
        state["evidence"][wp_id] = {
            "closed_at": now(),
            "journal_entry": entry_name,
            "patch_path": str(patch_path.relative_to(ROOT)),
            "no_changes": is_empty,
            "validation_errors": validation_errors,
        }
        save_status(state)

    # ---- 7. Human summary -----------------------------------------------
    print(f"Evidence captured for {wp_id} ({role}).")
    print(f"  patch:    {patch_path.relative_to(ROOT)} "
          f"({'EMPTY' if is_empty else f'{patch_path.stat().st_size} bytes'})")
    print(f"  journal:  .protocol/journal/{entry_name}.md")
    print(f"  report:   {close_report.relative_to(ROOT)}")
    # Quick stats (Phase 2.1 trial enhancement).
    if not is_empty and summary_info["changed_files"]:
        top = summary_info["changed_files"][:3]
        print(f"  quick stats:")
        print(f"    files:  {len(summary_info["changed_files"])} changed")
        if summary_info["tests_run"]:
            print(f"    tests:  {len(summary_info["tests_run"])} run")
        print(f"    top:    {', '.join(top)}")
    if validation_errors:
        print(f"  WARN:     {len(validation_errors)} validation issue(s) recorded.")
    if review_info["verdict"]:
        print(f"  review:   {review_info['verdict']}")
    if smoke_results:
        passed = sum(1 for r in smoke_results if r["ok"])
        print(f"  smoke:    {passed}/{len(smoke_results)} passed "
              f"(groups: {','.join(smoke_groups)})")
    elif smoke_skipped:
        print(f"  smoke:    SKIPPED (--skip-smoke)")
    if review_report and not review_skipped:
        crit = review_report.get("critical_count", 0)
        if crit == 0:
            print(f"  review:   PASS (0 critical findings)")
        else:
            print(f"  review:   {crit} critical findings (BLOCKED unless --force)")
    elif review_skipped:
        print(f"  review:   SKIPPED (--skip-review)")
    print("\nNext step: review the journal entry, then run "
          "`tcad_worktree.py merge <slug>` (with preconditions enforced).")
    return 0


def cmd_validate(args) -> int:
    wp_dir = resolve_wp_dir(args.wp_id)
    if wp_dir is None:
        print(f"Work Package not found: {args.wp_id}", file=sys.stderr)
        return 2

    summary_info = parse_summary(wp_dir / "11_worker_summary.md")
    has_delta = (wp_dir / "12_delta.md").is_file()
    has_blockers = (wp_dir / "13_blockers.md").is_file()
    review_info = parse_review(wp_dir / "14_review_result.md")

    print(f"WP: {wp_dir.name}")
    print(f"  11_worker_summary.md: {'present' if summary_info['exists'] else 'MISSING'}")
    if summary_info["missing_sections"]:
        print(f"    missing sections: {summary_info['missing_sections']}")
    print(f"  ready_for_review:    {summary_info['ready_for_review']}")
    print(f"  12_delta.md:         {'present' if has_delta else 'absent'}")
    print(f"  13_blockers.md:      {'present' if has_blockers else 'absent'}")
    print(f"  14_review_result:    "
          f"{'verdict=' + review_info['verdict'] if review_info['verdict'] else 'absent'}")
    if args.json:
        print(json.dumps({
            "wp": wp_dir.name,
            "summary": summary_info,
            "has_delta": has_delta,
            "has_blockers": has_blockers,
            "review": review_info,
        }, indent=2))
    return 0 if summary_info["exists"] else 4


def cmd_journal_list(args) -> int:
    if not JOURNAL_DIR.exists():
        print("No journal yet.")
        return 0
    entries = sorted(JOURNAL_DIR.glob("*.md"))
    entries = [e for e in entries if e.name != "INDEX.md"]
    if not entries:
        print("Journal is empty.")
        return 0
    for e in entries[-args.n:]:
        print(e.name)
    return 0


def cmd_journal_show(args) -> int:
    target = JOURNAL_DIR / f"{args.id}.md"
    if not target.exists():
        # try partial match
        matches = list(JOURNAL_DIR.glob(f"*{args.id}*.md"))
        if not matches:
            print(f"Journal entry not found: {args.id}", file=sys.stderr)
            return 1
        target = matches[0]
    print(target.read_text(encoding="utf-8"))
    return 0


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tcad_log", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("close", help="Capture evidence and write journal entry.")
    s.add_argument("slug",
                   help="Worktree slug (WP-NNN-name-role) or bare WP id.")
    s.add_argument("--force", action="store_true",
                   help="Overwrite existing patch and ignore validation/smoke errors.")
    s.add_argument("--smoke-test", action="append", default=None,
                   metavar="CMD",
                   help="Explicit smoke-test shell command (repeatable). Skips YAML.")
    s.add_argument("--smoke-group", default=None,
                   help="Run a specific group from smoke_tests.yaml (e.g. python_scripts).")
    s.add_argument("--skip-smoke", action="store_true",
                   help="Record close without running smoke tests.")
    s.add_argument("--review", action="store_true",
                   help="(default) Run deterministic reviewer gate (tcad_review inspect).")
    s.add_argument("--skip-review", action="store_true",
                   help="Skip the reviewer gate entirely.")
    s.set_defaults(func=cmd_close)

    s = sub.add_parser("validate", help="Validate WP evidence (read-only).")
    s.add_argument("wp_id")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("journal-list", help="List journal entries.")
    s.add_argument("--n", type=int, default=10)
    s.set_defaults(func=cmd_journal_list)

    s = sub.add_parser("journal-show", help="Print one journal entry.")
    s.add_argument("id")
    s.set_defaults(func=cmd_journal_show)

    return p


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
