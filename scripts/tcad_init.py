#!/usr/bin/env python3
"""
tcad_init.py — Bootstrap .protocol/ in a target repo.

Phase 3.4 alpha. Copies template files + creates minimal directory structure
in the current working directory. Does NOT overwrite existing files.

Usage:
    tcad init                  Bootstrap CWD as a TCAD-H target repo.
    tcad init --force          Overwrite existing files (dangerous).
    tcad init --target <dir>   Bootstrap a specific directory.

Exit codes:
    0  success (created or already initialized)
    1  bad args
    2  target is not writable
    3  refused: existing .protocol/ would be overwritten without --force
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
FRAMEWORK_HOME = SCRIPT_PATH.parent.parent  # framework root


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tcad init", description=__doc__)
    p.add_argument("--target", default=None,
                   help="Directory to bootstrap. Default: cwd.")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing files in .protocol/")
    args = p.parse_args(argv)

    target = Path(args.target).expanduser().resolve() if args.target else Path.cwd().resolve()
    if not target.is_dir():
        print(f"Target is not a directory: {target}", file=sys.stderr)
        return 2

    protocol = target / ".protocol"
    if protocol.exists() and not args.force:
        # Already initialized; just print summary.
        print(f"TCAD-H already present at {protocol.relative_to(target.parent)}")
        print(f"  Use --force to re-copy template files.")
        # Show what's missing.
        for required in (
            "handoffs/_template",
            "boundaries.yaml",
            "smoke_tests.yaml.example",
        ):
            p = protocol / required
            if not p.exists():
                print(f"  MISSING: .protocol/{required}")
        return 0

    print(f"Bootstrapping TCAD-H in {target}")

    # ---- Directories ------------------------------------------------------
    dirs = [
        protocol,
        protocol / "handoffs" / "_template",
        protocol / "questions",
        protocol / "journal",
        protocol / "atlas",
        protocol / "blueprint",
        protocol / "worktrees",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # ---- Copy templates (from framework repo) -----------------------------
    src_template_dir = FRAMEWORK_HOME / ".protocol" / "handoffs" / "_template"
    dst_template_dir = protocol / "handoffs" / "_template"
    if src_template_dir.is_dir():
        for f in src_template_dir.iterdir():
            if f.is_file():
                dst = dst_template_dir / f.name
                if dst.exists() and not args.force:
                    continue
                shutil.copy2(f, dst)
        print(f"  copied handoff template (12 files)")

    # ---- Copy examples + initial configs ----------------------------------
    examples = [
        ("boundaries.yaml.example",            "boundaries.yaml.example"),
        ("smoke_tests.yaml.example",           "smoke_tests.yaml.example"),
        ("capabilities.yaml.example",          "capabilities.yaml.example"),
        ("terminals.yaml.example",             "terminals.yaml.example"),
        ("project_profile.yaml.example",       "project_profile.yaml.example"),
        ("status.json.example",                "status.json.example"),
    ]
    for src_rel, dst_rel in examples:
        src = FRAMEWORK_HOME / ".protocol" / src_rel
        dst = protocol / dst_rel
        if src.is_file():
            if dst.exists() and not args.force:
                continue
            shutil.copy2(src, dst)
    print(f"  copied {len(examples)} example configs")

    # ---- Promote example to live where missing ----------------------------
    # boundaries.yaml: copy example to live so the firewall has something to read.
    live_boundaries = protocol / "boundaries.yaml"
    if not live_boundaries.exists():
        ex = protocol / "boundaries.yaml.example"
        if ex.is_file():
            shutil.copy2(ex, live_boundaries)
            print(f"  created boundaries.yaml from example")

    # smoke_tests.yaml: optional; do NOT auto-promote because it's project-specific.

    # ---- Questions index --------------------------------------------------
    qidx = protocol / "questions" / "INDEX.md"
    if not qidx.exists():
        qidx.write_text(
            "# Open Questions\n\n"
            "Blocking questions raised by Conductor, Workers, or Reviewers.\n\n"
            "## Current open questions\n\n"
            "(none)\n",
            encoding="utf-8",
        )
        (protocol / "questions" / "ANSWERED.md").write_text(
            "# Answered Questions — Archive\n\n", encoding="utf-8",
        )
        print(f"  created questions/INDEX.md")

    # ---- Events.jsonl placeholder -----------------------------------------
    events = protocol / "events.jsonl"
    if not events.exists():
        events.write_text("", encoding="utf-8")

    # ---- .gitignore note --------------------------------------------------
    gi = target / ".gitignore"
    snippet = "\n# TCAD-H runtime\n.protocol/worktrees/\n.protocol/status.lock\n"
    if gi.is_file():
        text = gi.read_text(encoding="utf-8")
        if ".protocol/worktrees/" not in text:
            gi.write_text(text.rstrip() + snippet, encoding="utf-8")
            print(f"  appended TCAD-H entries to existing .gitignore")
    else:
        gi.write_text(snippet.lstrip(), encoding="utf-8")
        print(f"  created .gitignore with TCAD-H entries")

    # ---- Done -------------------------------------------------------------
    print()
    print(f"Initialized .protocol/ in {target.name}")
    print()
    print(f"Next steps:")
    print(f"  cd {target}")
    print(f"  tcad profile detect")
    print(f"  tcad doctor")
    print(f"  tcad wp create --lean --name 'first-feature' --goal '...' --role backend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
