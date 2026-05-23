#!/usr/bin/env python3
"""
tcad_express.py — Foreman wp express: low-friction WP launcher.

Phase 3.5+ Staff-Engineer-feedback fix. Collapses ~10 commands into 1
for low-risk Work Packages. The full multi-step flow is still available
via the individual subcommands; `express` is the express lane.

What it does in one call:
    1. If .protocol/ missing → tcad_init.py
    2. If status.json missing → tcad_conduct.py init
    3. If project_profile.json missing → tcad_profile.py detect
    4. tcad_handoff.py --lean (writes 5 files)
    5. Open editor on 02_allowed_files.md and 03_forbidden_files.md
       (skipped with --no-edit; mandatory in production)
    6. tcad_conduct.py set-wp + transition to WORKER_BRIEF
    7. tcad_worktree.py create
    8. Print worker command to copy/paste

Usage:
    foreman wp express --name <slug> --goal "..." --role <role>
                       [--allowed glob1,glob2,...]   skip prompt; use these
                       [--forbidden glob1,glob2,...] skip prompt; use these
                       [--no-edit]                   don't drop user into editor
                       [--worker-cli opencode]       (informational only)

Auth model (Staff-Engineer feedback):
    Workers are launched by HUMAN via their respective CLI tools
    (claude code, opencode, kimi-cli, etc.) using THEIR OWN
    subscription auth. Foreman does NOT manage API keys, does NOT
    invoke models directly. It only prepares files + isolates worktree.

Exit codes:
    0  success
    1  bad args
    2  step failed (see stderr)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
SCRIPTS_DIR = SCRIPT_PATH.parent
sys.path.insert(0, str(SCRIPTS_DIR))
from _tcad_root import resolve_tcad_root  # noqa: E402

ROOT = resolve_tcad_root(os.environ.get("FOREMAN_ROOT") or os.environ.get("TCAD_ROOT"))
PROTOCOL = ROOT / ".protocol"

VALID_ROLES = {"backend", "frontend", "tests", "reading"}


def run(args: list[str], **kw) -> int:
    """Run a python subprocess; pass through stdout/stderr."""
    cmd = [sys.executable, *args]
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), **kw)
        return p.returncode
    except FileNotFoundError as exc:
        print(f"  failed to launch: {exc}", file=sys.stderr)
        return 2


def step(label: str) -> None:
    print(f"\n→ {label}")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="foreman wp express",
                                description="Low-friction WP launcher.")
    p.add_argument("--name", required=True)
    p.add_argument("--goal", required=True)
    p.add_argument("--role", required=True, choices=sorted(VALID_ROLES))
    p.add_argument("--allowed", default=None,
                   help="Comma-separated globs for 02_allowed_files.md.")
    p.add_argument("--forbidden", default=None,
                   help="Comma-separated globs for 03_forbidden_files.md.")
    p.add_argument("--no-edit", action="store_true",
                   help="Skip dropping into $EDITOR for scope files.")
    p.add_argument("--worker-cli", default=None,
                   help="Informational. Printed in the final hand-off message.")
    args = p.parse_args(argv)

    # ---- 1. init if needed ------------------------------------------------
    if not PROTOCOL.exists():
        step("Bootstrapping .protocol/ (first-time)")
        rc = run([str(SCRIPTS_DIR / "tcad_init.py")])
        if rc != 0:
            print("  tcad init failed.", file=sys.stderr)
            return 2

    # ---- 2. conductor init if needed --------------------------------------
    if not (PROTOCOL / "status.json").exists():
        step("Initializing Conductor state")
        rc = run([str(SCRIPTS_DIR / "tcad_conduct.py"), "init"])
        if rc != 0:
            print("  tcad conduct init failed.", file=sys.stderr)
            return 2

    # ---- 3. profile detect if needed --------------------------------------
    if not (PROTOCOL / "project_profile.json").exists():
        step("Detecting project profile")
        rc = run([str(SCRIPTS_DIR / "tcad_profile.py"), "detect"])
        if rc != 0:
            print("  tcad profile detect failed; continuing.", file=sys.stderr)

    # ---- 4. WP create (lean) ----------------------------------------------
    step(f"Creating lean WP: {args.name}")
    rc = run([
        str(SCRIPTS_DIR / "tcad_handoff.py"),
        "--lean",
        "--name", args.name,
        "--goal", args.goal,
        "--role", args.role,
    ])
    if rc != 0:
        print("  tcad wp create failed.", file=sys.stderr)
        return 2

    # Find the WP we just created (latest WP-NNN matching the slug).
    handoffs = PROTOCOL / "handoffs"
    candidates = sorted(
        (d for d in handoffs.iterdir() if d.is_dir() and args.name.lower() in d.name.lower()),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        print("  Could not locate created WP directory.", file=sys.stderr)
        return 2
    wp_dir = candidates[-1]
    wp_id = wp_dir.name
    slug = f"{wp_id}-{args.role}"
    print(f"  WP id: {wp_id}")

    # ---- 5. Fill scope files ---------------------------------------------
    allowed_path = wp_dir / "02_allowed_files.md"
    forbidden_path = wp_dir / "03_forbidden_files.md"
    if args.allowed:
        allowed_lines = "\n".join(f"- `{g.strip()}`" for g in args.allowed.split(",") if g.strip())
        allowed_path.write_text(f"# 02 — Allowed Files\n\n{allowed_lines}\n", encoding="utf-8")
        print(f"  wrote allowed_files.md from --allowed")
    if args.forbidden:
        forbidden_lines = "\n".join(f"- `{g.strip()}`" for g in args.forbidden.split(",") if g.strip())
        forbidden_path.write_text(f"# 03 — Forbidden Files\n\n{forbidden_lines}\n", encoding="utf-8")
        print(f"  wrote forbidden_files.md from --forbidden")
    if not args.allowed and not args.no_edit:
        editor = os.environ.get("EDITOR") or "vi"
        step(f"Opening 02_allowed_files.md in $EDITOR ({editor})")
        print(f"  Fill the allow list, save & quit to continue.")
        subprocess.run([editor, str(allowed_path)])
    if not args.forbidden and not args.no_edit:
        editor = os.environ.get("EDITOR") or "vi"
        step(f"Opening 03_forbidden_files.md in $EDITOR ({editor})")
        subprocess.run([editor, str(forbidden_path)])

    # ---- 6. Conductor: set-wp + transitions ------------------------------
    step("Conductor: set-wp + transitions → WORKER_BRIEF")
    for cmd_args in (
        ["set-wp", wp_id],
        ["transition", "INTAKE"],
        ["transition", "SPEC_DRAFT"],
        ["transition", "HANDOFF_GEN"],
        ["transition", "WORKER_BRIEF"],
    ):
        rc = run([str(SCRIPTS_DIR / "tcad_conduct.py"), *cmd_args])
        if rc != 0:
            print(f"  conduct {cmd_args} failed.", file=sys.stderr)
            return 2

    # ---- 7. Worktree ------------------------------------------------------
    step("Creating isolated worktree")
    rc = run([str(SCRIPTS_DIR / "tcad_worktree.py"), "create", wp_id, "--role", args.role])
    if rc != 0:
        print("  worktree create failed.", file=sys.stderr)
        return 2

    # ---- 8. Hand-off message ---------------------------------------------
    wt_path = PROTOCOL / "worktrees" / slug
    worker_prompt = wp_dir / f"05_worker_prompt_{args.role}.md" if args.role == "backend" \
        else wp_dir / f"06_worker_prompt_{args.role}.md" if args.role == "frontend" \
        else wp_dir / f"07_worker_prompt_{args.role}.md" if args.role == "tests" \
        else wp_dir / f"08_worker_prompt_{args.role}.md"

    cli_hint = args.worker_cli or "<your CLI: claude code | opencode | kimi-cli | codex-cli>"

    print("")
    print("=" * 70)
    print(f"  WP {wp_id} is READY for the worker.")
    print("=" * 70)
    print(f"  Open a new terminal in:")
    print(f"      cd {wt_path}")
    print(f"  Launch your worker CLI (auth via its OWN login — Foreman does NOT")
    print(f"  manage API keys):")
    print(f"      {cli_hint}")
    print(f"  Read the worker prompt:")
    print(f"      {worker_prompt.relative_to(ROOT)}")
    print(f"")
    print(f"  When the worker finishes (writes 11_worker_summary.md):")
    print(f"      foreman close {slug} --smoke-test \"YOUR_TEST_CMD\"")
    print(f"      foreman graph build {wp_id}")
    print(f"      foreman worktree merge {slug}")
    print(f"      foreman worktree destroy {slug}")
    print(f"      foreman atlas build")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
