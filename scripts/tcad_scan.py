#!/usr/bin/env python3
"""
tcad_scan.py — TCAD-H deterministic watcher.

Phase 1.8 deliverable. Mentor critique applied:
    "Run a deterministic Python watcher. Write append-only WAL events.
     Zero LLM tokens. Truth at filesystem level."

What it does, per invocation:
    1. Read git working tree state (`git diff --name-only`).
    2. Cross-check against active WP + global boundaries (reuses tcad_check_boundaries).
    3. Assign each changed file to a capability via DETERMINISTIC globs.
    4. Compute risk level by path patterns from boundaries.yaml.
    5. Append events to .protocol/events.jsonl (WAL pattern).
    6. Update .protocol/status.json health block.

Modes:
    once             — single scan and exit (default)
    loop --interval N — scan every N seconds until SIGINT (use in dedicated terminal)

Output:
    .protocol/events.jsonl   (append-only)
    .protocol/status.json    (health block updated; other fields untouched)

Exit codes:
    0   scan completed
    1   bad arguments
    2   not a git repo
    3   protocol files missing or unreadable
"""

from __future__ import annotations

import argparse
import os
import json
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
import sys as _sys
_sys.path.insert(0, str(SCRIPT_PATH.parent))
from _tcad_root import resolve_tcad_root  # noqa: E402
ROOT = resolve_tcad_root(os.environ.get("TCAD_ROOT"))
PROTOCOL_DIR = ROOT / ".protocol"
STATUS_FILE = PROTOCOL_DIR / "status.json"
EVENTS_FILE = PROTOCOL_DIR / "events.jsonl"
BOUNDARIES_FILE = PROTOCOL_DIR / "boundaries.yaml"
BOUNDARIES_EXAMPLE = PROTOCOL_DIR / "boundaries.yaml.example"
CAPABILITIES_FILE = PROTOCOL_DIR / "capabilities.yaml"
CAPABILITIES_EXAMPLE = PROTOCOL_DIR / "capabilities.yaml.example"

# Reuse the firewall's evaluator and YAML loader.
sys.path.insert(0, str(SCRIPT_PATH.parent))
from tcad_check_boundaries import (  # noqa: E402
    evaluate,
    git_changed_files,
    git_is_repo,
    load_yaml,
    globs_match,
    _match_glob,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Event log (WAL)
# ---------------------------------------------------------------------------
def append_event(event: dict) -> None:
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


def load_last_scan_event() -> dict | None:
    """Return the most recent `scan_completed` event, if any."""
    if not EVENTS_FILE.exists():
        return None
    last = None
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "scan_completed":
                last = ev
    return last


# ---------------------------------------------------------------------------
# Capability mapping (deterministic globs only)
# ---------------------------------------------------------------------------
def map_files_to_capabilities(files: list[str]) -> dict[str, list[str]]:
    """Return { capability_id: [files...] } using files_glob from capabilities.yaml."""
    cap_cfg = load_yaml(CAPABILITIES_FILE) or load_yaml(CAPABILITIES_EXAMPLE) or {}
    capabilities = cap_cfg.get("capabilities", []) or []
    orphan_excluded = cap_cfg.get("orphan_globs_excluded", []) or []
    mapping: dict[str, list[str]] = {}
    orphans: list[str] = []
    for f in files:
        if globs_match(f, orphan_excluded):
            continue  # legitimately ignored (lockfiles, caches, etc.)
        matched = False
        for cap in capabilities:
            cid = cap.get("id")
            globs = cap.get("files_glob", []) or []
            if globs_match(f, globs):
                mapping.setdefault(cid, []).append(f)
                matched = True
                break  # first capability wins; deterministic
        if not matched:
            orphans.append(f)
    if orphans:
        mapping["__orphans__"] = orphans
    return mapping


# ---------------------------------------------------------------------------
# Risk scoring (deterministic, per boundaries.yaml.risk_patterns)
# ---------------------------------------------------------------------------
def compute_risk(files: list[str]) -> dict[str, Any]:
    boundaries = load_yaml(BOUNDARIES_FILE) or load_yaml(BOUNDARIES_EXAMPLE) or {}
    risk_patterns = boundaries.get("risk_patterns", {}) or {}
    high = risk_patterns.get("high", []) or []
    medium = risk_patterns.get("medium", []) or []
    high_hits = [f for f in files if globs_match(f, high)]
    medium_hits = [f for f in files if globs_match(f, medium)]
    if high_hits:
        level = "high"
    elif medium_hits:
        level = "medium"
    else:
        level = "low"
    return {
        "level": level,
        "deterministic": True,
        "high_hits": high_hits,
        "medium_hits": medium_hits,
    }


# ---------------------------------------------------------------------------
# Health score (deterministic — does NOT use LLM)
# ---------------------------------------------------------------------------
def compute_health(eval_report: dict, risk: dict) -> dict:
    hard = len(eval_report["violations"]["hard"])
    soft = len(eval_report["violations"]["soft"])
    appr = len(eval_report["violations"]["approval"])
    risk_penalty = {"high": 30, "medium": 15, "low": 0}[risk["level"]]
    # Heuristic but bounded. Mentor warning: this is a signal, not a guarantee.
    # We expose the raw counts too so the UI can show the math.
    score = max(0, 100 - (hard * 25) - (soft * 10) - (appr * 5) - risk_penalty)
    return {
        "score": score,
        "blockers": hard,
        "warnings": soft + appr,
        "risk_level": risk["level"],
        "method": "deterministic_v1",
        "components": {
            "hard_violations": hard,
            "soft_violations": soft,
            "approval_required": appr,
            "risk_penalty": risk_penalty,
        },
    }


# ---------------------------------------------------------------------------
# Status.json update (preserve everything else)
# ---------------------------------------------------------------------------
def update_status_health(health: dict, risk: dict, mapping: dict, changed_files: list[str]) -> None:
    if not STATUS_FILE.exists():
        # Don't create status.json from scratch here. tcad_conduct.py owns it.
        # Just emit an event so the studio still sees us.
        return
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    data.setdefault("scan", {})
    data["scan"] = {
        "last_scan": now(),
        "health": health,
        "risk": risk,
        "capability_touches": {k: len(v) for k, v in mapping.items()},
        "changed_files_count": len(changed_files),
    }
    STATUS_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# Single scan
# ---------------------------------------------------------------------------
def git_changed_files_in(worktree: Path) -> list[str]:
    """Audit fix #6: scan a specific worktree path."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only"],
            cwd=str(worktree), text=True, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [f for f in out.strip().split("\n") if f]


def collect_changed_files() -> tuple[list[str], dict[str, list[str]]]:
    """Audit fix #6: collect changed files from root + registered worktrees."""
    by_source: dict[str, list[str]] = {}
    combined: list[str] = []
    root_files = git_changed_files()
    if root_files:
        by_source["root"] = root_files
        combined.extend(root_files)
    if STATUS_FILE.exists():
        try:
            status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}
        wt_index = status.get("worktrees", {}) or {}
        for slug, info in wt_index.items():
            wt_path = Path(info.get("absolute_path") or info.get("path") or "")
            if not wt_path.exists():
                continue
            wt_files = git_changed_files_in(wt_path)
            if wt_files:
                tagged = [f"[{slug}] {f}" for f in wt_files]
                by_source[slug] = tagged
                combined.extend(tagged)
    return combined, by_source


def perform_scan(verbose: bool = False) -> dict[str, Any]:
    files, by_source = collect_changed_files()
    raw_files = [f.split("] ", 1)[1] if f.startswith("[") and "] " in f else f for f in files]
    eval_report = evaluate(raw_files)
    risk = compute_risk(raw_files)
    mapping = map_files_to_capabilities(raw_files)
    health = compute_health(eval_report, risk)

    # Emit per-file events (boundary_warning / boundary_violation).
    for v in eval_report["violations"]["hard"]:
        append_event({
            "ts": now(), "actor": "watcher", "event": "boundary_violation",
            "file": v["file"], "reason": v["reason"],
            "wp": eval_report.get("active_wp"),
        })
    for v in eval_report["violations"]["soft"]:
        append_event({
            "ts": now(), "actor": "watcher", "event": "boundary_warning",
            "file": v["file"], "reason": v["reason"],
            "wp": eval_report.get("active_wp"),
        })
    for v in eval_report["violations"]["approval"]:
        append_event({
            "ts": now(), "actor": "watcher", "event": "approval_required",
            "file": v["file"], "reason": v["reason"],
            "wp": eval_report.get("active_wp"),
        })

    # Always emit a scan_completed event (heartbeat).
    summary = {
        "ts": now(), "actor": "watcher", "event": "scan_completed",
        "changed_files": len(files),
        "sources": {k: len(v) for k, v in by_source.items()},
        "hard": len(eval_report["violations"]["hard"]),
        "soft": len(eval_report["violations"]["soft"]),
        "approval": len(eval_report["violations"]["approval"]),
        "risk_level": risk["level"],
        "health_score": health["score"],
        "wp": eval_report.get("active_wp"),
        "capabilities_touched": list(mapping.keys()),
    }
    append_event(summary)

    update_status_health(health, risk, mapping, files)

    if verbose:
        print(f"[{summary['ts']}] scan:")
        print(f"  files={len(files)}  hard={summary['hard']}  soft={summary['soft']}  "
              f"approval={summary['approval']}  risk={risk['level']}  health={health['score']}")
        if mapping:
            for cid, lst in mapping.items():
                print(f"  cap {cid}: {len(lst)} file(s)")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
_keep_running = True


def _handle_sigint(signum, frame):
    global _keep_running
    _keep_running = False
    print("\nWatcher stopping (SIGINT received).", file=sys.stderr)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="tcad_scan",
        description="TCAD-H deterministic watcher. Reads filesystem, writes events.jsonl. Zero LLM tokens.",
    )
    sub = p.add_subparsers(dest="cmd")
    sub.required = False

    s_once = sub.add_parser("once", help="Single scan (default).")
    s_once.add_argument("--verbose", "-v", action="store_true")

    s_loop = sub.add_parser("loop", help="Loop until SIGINT.")
    s_loop.add_argument("--interval", type=int, default=5,
                        help="Seconds between scans (default 5).")
    s_loop.add_argument("--verbose", "-v", action="store_true")

    s_tail = sub.add_parser("tail", help="Print recent events from events.jsonl.")
    s_tail.add_argument("--n", type=int, default=10)

    args = p.parse_args(argv)

    if not git_is_repo():
        print("Not a git repository. Initialize git or run from inside one.", file=sys.stderr)
        return 2

    cmd = args.cmd or "once"

    if cmd == "tail":
        if not EVENTS_FILE.exists():
            print("No events.jsonl yet.")
            return 0
        lines = EVENTS_FILE.read_text(encoding="utf-8").strip().split("\n")
        for ln in lines[-args.n:]:
            print(ln)
        return 0

    if cmd == "once":
        perform_scan(verbose=args.verbose)
        return 0

    if cmd == "loop":
        signal.signal(signal.SIGINT, _handle_sigint)
        print(f"Watcher loop started (interval={args.interval}s). Ctrl+C to stop.")
        while _keep_running:
            perform_scan(verbose=args.verbose)
            for _ in range(args.interval):
                if not _keep_running:
                    break
                time.sleep(1)
        print("Watcher stopped.")
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
