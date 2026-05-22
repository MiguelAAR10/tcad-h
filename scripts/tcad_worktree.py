#!/usr/bin/env python3
"""
tcad_worktree.py — TCAD-H git worktree manager for parallel-terminal isolation.

Phase 1.9 deliverable. Mentor's solution applied with bug fixes:
    - Atomic `git worktree add -b BRANCH PATH START` (no two-step race).
    - Status.json MERGED (does NOT clobber FSM state from tcad_conduct.py).
    - Event log via events.jsonl (WAL).
    - Idempotent: refuses to create over an existing worktree.
    - `list`, `merge`, `destroy` commands present.
    - Safety: destroy refuses on uncommitted changes (override with --force).

Stdlib only. No LLM tokens.

Commands:
    create <wp_id> [--role backend|frontend|tests|reading]
    list                     show all active worktrees
    inspect <wp_id-role>     show one worktree's state
    merge <wp_id-role>       fast-forward / no-ff merge onto base branch
    destroy <wp_id-role>     remove worktree + branch (safety checks)
    prune                    drop orphaned worktrees

Exit codes:
    0 ok
    1 bad args
    2 git error
    3 not a git repo
    4 worktree already exists
    5 worktree not found
    6 unsafe state (uncommitted changes, conflicts, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parent.parent
PROTOCOL_DIR = ROOT / ".protocol"
WORKTREES_DIR = PROTOCOL_DIR / "worktrees"
STATUS_FILE = PROTOCOL_DIR / "status.json"
EVENTS_FILE = PROTOCOL_DIR / "events.jsonl"
HANDOFFS_DIR = PROTOCOL_DIR / "handoffs"
TERMINALS_FILE = PROTOCOL_DIR / "terminals.yaml"
TERMINALS_EXAMPLE = PROTOCOL_DIR / "terminals.yaml.example"

VALID_ROLES = {"backend", "frontend", "tests", "reading", "docs"}
WP_DIR_RE = re.compile(r"^WP-(\d+)-(.+)$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run git from ROOT. Returns CompletedProcess; raises on failure when check=True."""
    cmd = ["git", *args]
    return subprocess.run(
        cmd, cwd=ROOT, text=True, check=check,
        capture_output=capture,
    )


def is_git_repo() -> bool:
    try:
        git("rev-parse", "--is-inside-work-tree")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def default_base_branch() -> str:
    """Return main / master / current trunk."""
    try:
        # symbolic-ref of HEAD if origin/HEAD set; otherwise probe.
        out = git("symbolic-ref", "refs/remotes/origin/HEAD", check=False)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().rsplit("/", 1)[-1]
    except Exception:
        pass
    for cand in ("main", "master"):
        out = git("rev-parse", "--verify", cand, check=False)
        if out.returncode == 0:
            return cand
    # Fallback: current branch.
    out = git("rev-parse", "--abbrev-ref", "HEAD")
    return out.stdout.strip()


def list_worktrees() -> list[dict[str, str]]:
    """Parse `git worktree list --porcelain`."""
    out = git("worktree", "list", "--porcelain")
    blocks = out.stdout.strip().split("\n\n")
    results: list[dict[str, str]] = []
    for blk in blocks:
        rec: dict[str, str] = {}
        for line in blk.splitlines():
            if " " in line:
                key, _, val = line.partition(" ")
                rec[key] = val
            else:
                rec[line] = ""
        if "worktree" in rec:
            results.append(rec)
    return results


def resolve_wp_dir(wp_id: str) -> Path | None:
    if not HANDOFFS_DIR.exists():
        return None
    candidate = HANDOFFS_DIR / wp_id
    if candidate.is_dir():
        return candidate
    if wp_id.isdigit():
        prefix = f"WP-{int(wp_id):03d}-"
        for child in HANDOFFS_DIR.iterdir():
            if child.is_dir() and child.name.startswith(prefix):
                return child
    return None


def append_event(event: dict) -> None:
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


def load_status() -> dict[str, Any]:
    """Load status.json. Returns minimal stub if missing.

    Critical: we MERGE into existing status.json, never overwrite. This protects
    FSM state owned by tcad_conduct.py.
    """
    if not STATUS_FILE.exists():
        return {}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_status(state: dict[str, Any]) -> None:
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def update_worktree_index(action: str, slug: str, payload: dict) -> None:
    """Maintain a 'worktrees' map inside status.json (additive, FSM-safe)."""
    state = load_status()
    wt = state.setdefault("worktrees", {})
    if action == "add":
        wt[slug] = payload
    elif action == "remove":
        wt.pop(slug, None)
    save_status(state)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_create(args) -> int:
    if not is_git_repo():
        print("Not a git repo.", file=sys.stderr)
        return 3

    wp_dir = resolve_wp_dir(args.wp_id)
    if wp_dir is None:
        print(f"Work Package not found: {args.wp_id}", file=sys.stderr)
        return 1
    wp_canonical = wp_dir.name

    role = args.role
    if role not in VALID_ROLES:
        print(f"Invalid role {role!r}. Choose from: {sorted(VALID_ROLES)}", file=sys.stderr)
        return 1

    slug = f"{wp_canonical}-{role}"
    branch = f"wp/{wp_canonical}-{role}"
    wt_path = WORKTREES_DIR / slug

    if wt_path.exists():
        print(f"Worktree already exists at {wt_path}", file=sys.stderr)
        return 4

    WORKTREES_DIR.mkdir(parents=True, exist_ok=True)

    base = args.base or default_base_branch()

    # Atomic: `git worktree add -b BRANCH PATH BASE` creates branch+worktree
    # in one call. If branch already exists, `-b` errors out cleanly.
    try:
        git("worktree", "add", "-b", branch, str(wt_path), base)
    except subprocess.CalledProcessError as exc:
        # If branch already exists, retry without -b (reuse existing branch).
        if "already exists" in (exc.stderr or "") or "already used" in (exc.stderr or ""):
            print(f"Branch {branch} exists; attaching worktree to it.", file=sys.stderr)
            try:
                git("worktree", "add", str(wt_path), branch)
            except subprocess.CalledProcessError as exc2:
                print(f"git worktree add failed: {exc2.stderr}", file=sys.stderr)
                return 2
        else:
            print(f"git worktree add failed: {exc.stderr}", file=sys.stderr)
            return 2

    payload = {
        "wp": wp_canonical,
        "role": role,
        "branch": branch,
        "path": str(wt_path.relative_to(ROOT)),
        "absolute_path": str(wt_path),
        "base": base,
        "created_at": now(),
        "status": "active",
    }
    update_worktree_index("add", slug, payload)
    append_event({
        "ts": now(), "actor": "worktree", "event": "worktree_created",
        "wp": wp_canonical, "role": role, "branch": branch,
        "path": payload["path"],
    })

    print(f"Worktree created.")
    print(f"  WP:     {wp_canonical}")
    print(f"  Role:   {role}")
    print(f"  Branch: {branch}  (from {base})")
    print(f"  Path:   {wt_path}")
    print(f"\nTo work in it, open a terminal and:")
    print(f"  cd {wt_path}")
    print(f"  # then launch your worker CLI (opencode / kimi / etc.)")
    return 0


def cmd_list(args) -> int:
    if not is_git_repo():
        print("Not a git repo.", file=sys.stderr)
        return 3
    state = load_status()
    wt_index = state.get("worktrees", {}) or {}
    raw = list_worktrees()
    if args.json:
        print(json.dumps({"managed": wt_index, "all_git_worktrees": raw}, indent=2))
        return 0
    if not wt_index:
        print("No TCAD-managed worktrees.")
        # Still show git's view of worktrees for completeness.
        if raw:
            print("\nAll git worktrees:")
            for w in raw:
                print(f"  {w.get('worktree')}  branch={w.get('branch','-')}")
        return 0
    print(f"{'SLUG':<48} {'ROLE':<10} {'BRANCH':<40} {'STATUS':<10}")
    print("-" * 110)
    for slug, info in wt_index.items():
        print(
            f"{slug:<48} {info.get('role',''):<10} {info.get('branch',''):<40} "
            f"{info.get('status',''):<10}"
        )
    return 0


def cmd_inspect(args) -> int:
    state = load_status()
    wt = (state.get("worktrees") or {}).get(args.slug)
    if not wt:
        print(f"Worktree not found in status.json: {args.slug}", file=sys.stderr)
        return 5
    print(json.dumps(wt, indent=2))
    # Show git status inside the worktree.
    wt_path = Path(wt.get("absolute_path") or wt.get("path"))
    if wt_path.exists():
        out = subprocess.run(
            ["git", "status", "--short"], cwd=wt_path, text=True,
            capture_output=True, check=False,
        )
        print("\ngit status (inside worktree):")
        print(out.stdout or "(clean)")
    return 0


def cmd_merge(args) -> int:
    state = load_status()
    wt = (state.get("worktrees") or {}).get(args.slug)
    if not wt:
        print(f"Worktree not found: {args.slug}", file=sys.stderr)
        return 5

    wt_path = Path(wt.get("absolute_path") or wt.get("path"))
    branch = wt.get("branch")
    base = wt.get("base") or default_base_branch()

    if not wt_path.exists():
        print(f"Worktree path missing on disk: {wt_path}", file=sys.stderr)
        return 5

    # Safety: refuse if worktree has uncommitted changes.
    status_out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=wt_path, text=True,
        capture_output=True, check=False,
    )
    if status_out.stdout.strip():
        print(
            f"Refusing to merge: worktree has uncommitted changes.\n"
            f"  cd {wt_path}\n  git status",
            file=sys.stderr,
        )
        return 6

    # Switch base branch to top and merge.
    try:
        git("checkout", base)
        if args.no_ff:
            git("merge", "--no-ff", "--no-edit", branch)
        else:
            git("merge", "--ff-only", branch)
    except subprocess.CalledProcessError as exc:
        print(f"git merge failed: {exc.stderr}", file=sys.stderr)
        return 2

    append_event({
        "ts": now(), "actor": "worktree", "event": "worktree_merged",
        "wp": wt.get("wp"), "role": wt.get("role"),
        "branch": branch, "base": base,
        "strategy": "no-ff" if args.no_ff else "ff-only",
    })

    # Mark as merged in status.json (don't destroy yet — user can inspect post-merge).
    wt["status"] = "merged"
    wt["merged_at"] = now()
    save_status(state)

    print(f"Merged {branch} into {base}.")
    print(f"Run `tcad_worktree.py destroy {args.slug}` to remove the worktree.")
    return 0


def cmd_destroy(args) -> int:
    state = load_status()
    wt = (state.get("worktrees") or {}).get(args.slug)
    if not wt:
        print(f"Worktree not found in status.json: {args.slug}", file=sys.stderr)
        return 5

    wt_path = Path(wt.get("absolute_path") or wt.get("path"))
    branch = wt.get("branch")

    # Safety: uncommitted changes block destroy unless --force.
    if wt_path.exists():
        out = subprocess.run(
            ["git", "status", "--porcelain"], cwd=wt_path, text=True,
            capture_output=True, check=False,
        )
        if out.stdout.strip() and not args.force:
            print(
                f"Refusing to destroy: worktree has uncommitted changes.\n"
                f"Use --force to override (changes will be lost).",
                file=sys.stderr,
            )
            return 6

    # Remove worktree.
    if wt_path.exists():
        rm_args = ["worktree", "remove"]
        if args.force:
            rm_args.append("--force")
        rm_args.append(str(wt_path))
        try:
            git(*rm_args)
        except subprocess.CalledProcessError as exc:
            print(f"git worktree remove failed: {exc.stderr}", file=sys.stderr)
            if not args.force:
                return 2
            # Best-effort manual cleanup.
            shutil.rmtree(wt_path, ignore_errors=True)

    # Delete branch if requested (default yes unless --keep-branch).
    if branch and not args.keep_branch:
        del_args = ["branch", "-d", branch]
        if args.force:
            del_args = ["branch", "-D", branch]
        try:
            git(*del_args)
        except subprocess.CalledProcessError as exc:
            print(f"git branch delete warning: {exc.stderr.strip()}", file=sys.stderr)

    update_worktree_index("remove", args.slug, {})
    append_event({
        "ts": now(), "actor": "worktree", "event": "worktree_destroyed",
        "slug": args.slug, "wp": wt.get("wp"), "role": wt.get("role"),
        "branch": branch,
    })
    print(f"Destroyed worktree {args.slug}.")
    return 0


def cmd_prune(args) -> int:
    """Run `git worktree prune` and clean stale entries from status.json."""
    try:
        git("worktree", "prune")
    except subprocess.CalledProcessError as exc:
        print(f"git worktree prune failed: {exc.stderr}", file=sys.stderr)
        return 2
    # Clean status.json entries whose path no longer exists.
    state = load_status()
    wt_index = state.get("worktrees", {}) or {}
    stale = []
    for slug, info in list(wt_index.items()):
        p = Path(info.get("absolute_path") or info.get("path") or "")
        if not p.exists():
            stale.append(slug)
            del wt_index[slug]
    if stale:
        save_status(state)
        for s in stale:
            append_event({
                "ts": now(), "actor": "worktree", "event": "worktree_pruned",
                "slug": s,
            })
    print(f"Prune done. Removed {len(stale)} stale entr{'y' if len(stale)==1 else 'ies'} from status.json.")
    return 0


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tcad_worktree", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("create", help="Create a worktree for a WP+role.")
    s.add_argument("wp_id", help="WP slug or number (e.g. WP-001-foo or 001)")
    s.add_argument("--role", required=True, choices=sorted(VALID_ROLES))
    s.add_argument("--base", default=None, help="Base branch to fork from.")
    s.set_defaults(func=cmd_create)

    s = sub.add_parser("list", help="List managed worktrees.")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("inspect", help="Show details of one worktree.")
    s.add_argument("slug", help="WP-NNN-name-role")
    s.set_defaults(func=cmd_inspect)

    s = sub.add_parser("merge", help="Merge a worktree branch back into base.")
    s.add_argument("slug")
    s.add_argument("--no-ff", action="store_true",
                   help="Use --no-ff (create merge commit) instead of fast-forward.")
    s.set_defaults(func=cmd_merge)

    s = sub.add_parser("destroy", help="Remove a worktree and its branch.")
    s.add_argument("slug")
    s.add_argument("--force", action="store_true",
                   help="Override safety checks; discard uncommitted changes.")
    s.add_argument("--keep-branch", action="store_true",
                   help="Remove worktree only; keep branch.")
    s.set_defaults(func=cmd_destroy)

    s = sub.add_parser("prune", help="Clean orphaned worktree entries.")
    s.set_defaults(func=cmd_prune)

    return p


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
