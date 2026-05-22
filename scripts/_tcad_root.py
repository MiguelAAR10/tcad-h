"""Resolve the canonical TCAD-H repo root.

Phase 2.2 Finding #2 fix. Scripts launched from inside a git worktree have
their SCRIPT_PATH.parent.parent resolving to the worktree root, not the main
repo. The worktree's .protocol/ may be a stale snapshot.

Resolution order:
    1. --root CLI argument (caller's responsibility to pass)
    2. TCAD_ROOT environment variable
    3. Walk upward from cwd looking for .protocol/status.json
    4. `git rev-parse --git-common-dir` → main repo root
    5. Fallback: cwd

Returns a Path. Always exists or fallback (last option always succeeds).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _walk_upward_for_protocol(start: Path) -> Path | None:
    """Walk start, start.parent, ... up to filesystem root looking for .protocol/.

    Prefers a directory that has .protocol/status.json (live state) over one
    that only has .protocol/ (could be a worktree snapshot).
    """
    cur = start.resolve()
    best_partial: Path | None = None
    while True:
        protocol = cur / ".protocol"
        if protocol.is_dir():
            status = protocol / "status.json"
            if status.is_file():
                return cur
            if best_partial is None:
                best_partial = cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return best_partial


def _git_common_dir(start: Path) -> Path | None:
    """Use `git rev-parse --git-common-dir` to find the main repo root.

    For a normal clone, this is `<repo>/.git`, so the parent is the repo root.
    For a worktree, it still points at the MAIN repo's `.git`, which is what
    we want.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(start), text=True,
            capture_output=True, check=False,
        )
    except FileNotFoundError:
        return None
    if out.returncode != 0:
        return None
    git_dir = Path(out.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (start / git_dir).resolve()
    if git_dir.name == ".git":
        return git_dir.parent
    return git_dir.parent  # bare repo edge case; best-effort


def resolve_tcad_root(cli_arg: str | None = None, start: Path | None = None) -> Path:
    """Pick the canonical repo root."""
    # 1. CLI arg wins.
    if cli_arg:
        p = Path(cli_arg).expanduser().resolve()
        if p.is_dir():
            return p

    # 2. Env var.
    env_val = os.environ.get("TCAD_ROOT")
    if env_val:
        p = Path(env_val).expanduser().resolve()
        if p.is_dir():
            return p

    # 3. Walk upward from start.
    start = (start or Path.cwd()).resolve()
    found = _walk_upward_for_protocol(start)
    if found is not None:
        return found

    # 4. Git common dir.
    git_root = _git_common_dir(start)
    if git_root is not None and (git_root / ".protocol").is_dir():
        return git_root
    if git_root is not None:
        return git_root  # accept even without .protocol; caller decides

    # 5. Fallback.
    return start


def is_inside_worktree(path: Path) -> bool:
    """Best-effort detection: is `path` inside a TCAD-managed worktree?"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(path), text=True, capture_output=True, check=False,
        )
        if out.returncode != 0:
            return False
        toplevel = Path(out.stdout.strip())
        common = _git_common_dir(path)
        # If toplevel != common-dir's parent, we're in a worktree.
        return common is not None and toplevel.resolve() != common.resolve()
    except FileNotFoundError:
        return False


if __name__ == "__main__":
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    root = resolve_tcad_root(arg)
    print(f"TCAD_ROOT = {root}")
    print(f"in_worktree = {is_inside_worktree(Path.cwd())}")
