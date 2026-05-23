#!/usr/bin/env python3
"""
tcad_doctor.py — TCAD-H repo health validator.

Phase 3.4 alpha. Inspects the current target repo (resolved via _tcad_root)
and reports which protocol pieces are healthy, which are missing, and which
are stale.

NO LLM. NO network. Pure filesystem + JSON + git introspection.

Exit codes:
    0  healthy (or only informational warnings)
    1  bad args
    2  one or more critical issues found
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT_PATH.parent))
from _tcad_root import resolve_tcad_root  # noqa: E402

ROOT = resolve_tcad_root(os.environ.get("FOREMAN_ROOT") or os.environ.get("TCAD_ROOT"))
PROTOCOL = ROOT / ".protocol"


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------
class Check:
    __slots__ = ("name", "status", "detail")

    def __init__(self, name: str, status: str, detail: str = ""):
        # status: ok | warn | fail | info
        self.name = name
        self.status = status
        self.detail = detail


def ok(name: str, detail: str = "") -> Check:
    return Check(name, "ok", detail)


def warn(name: str, detail: str) -> Check:
    return Check(name, "warn", detail)


def fail(name: str, detail: str) -> Check:
    return Check(name, "fail", detail)


def info(name: str, detail: str) -> Check:
    return Check(name, "info", detail)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def check_protocol_dir() -> list[Check]:
    if not PROTOCOL.exists():
        return [fail(".protocol/ present",
                     f"not found at {PROTOCOL}. Run `tcad init`.")]
    return [ok(".protocol/ present", str(PROTOCOL))]


def check_required_files() -> list[Check]:
    """Files we expect at the protocol root."""
    out: list[Check] = []
    required = {
        "handoffs/_template": "directory",
        "boundaries.yaml": "file",
        "questions/INDEX.md": "file",
    }
    optional = {
        "smoke_tests.yaml": "file",
        "capabilities.yaml": "file",
        "terminals.yaml": "file",
        "project_profile.json": "file",
        "status.json": "file",
        "events.jsonl": "file",
    }
    for rel, kind in required.items():
        p = PROTOCOL / rel
        if kind == "directory":
            if not p.is_dir():
                out.append(fail(f"required dir {rel}", f"missing: {p}"))
            else:
                out.append(ok(f"required dir {rel}"))
        else:
            if not p.is_file():
                out.append(fail(f"required file {rel}", f"missing: {p}"))
            else:
                out.append(ok(f"required file {rel}"))
    for rel, kind in optional.items():
        p = PROTOCOL / rel
        if not p.exists():
            out.append(info(f"optional {rel}", "not present"))
        else:
            out.append(ok(f"optional {rel}"))
    return out


def check_status_json() -> list[Check]:
    p = PROTOCOL / "status.json"
    if not p.is_file():
        return [info("status.json", "absent — run `tcad conduct init` to create")]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [fail("status.json", f"invalid JSON: {exc}")]
    if "state" not in data or "schema_version" not in data:
        return [warn("status.json", "missing keys: state / schema_version")]
    return [ok("status.json", f"state={data.get('state')} "
               f"active_wp={data.get('active_wp')}")]


def check_handoffs() -> list[Check]:
    out: list[Check] = []
    handoffs = PROTOCOL / "handoffs"
    if not handoffs.is_dir():
        return [fail("handoffs/", "missing directory")]
    wps = [d for d in handoffs.iterdir()
           if d.is_dir() and not d.name.startswith("_")]
    out.append(info("handoffs/ WP count", f"{len(wps)} WP folder(s)"))
    for wp in wps:
        meta = wp / ".tcad_wp.json"
        if not meta.is_file():
            out.append(warn(f"WP {wp.name}", "no .tcad_wp.json metadata (legacy?)"))
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            out.append(fail(f"WP {wp.name}", ".tcad_wp.json is invalid JSON"))
            continue
        required = data.get("required_files", [])
        missing = [f for f in required if not (wp / f).is_file()]
        if missing:
            out.append(warn(f"WP {wp.name}",
                            f"missing {len(missing)} required file(s): {missing[:3]}"))
        else:
            out.append(ok(f"WP {wp.name}", f"profile={data.get('profile')}, role={data.get('role')}"))
    return out


def check_worktrees() -> list[Check]:
    """Detect orphaned worktrees (registered in status.json but path missing) and
    worktree paths that exist but are not in status.json."""
    out: list[Check] = []
    status_path = PROTOCOL / "status.json"
    if not status_path.is_file():
        return [info("worktrees", "no status.json yet")]
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [warn("worktrees", "status.json invalid; cannot check")]
    registered = status.get("worktrees", {}) or {}

    # Check registered against disk
    orphan_indexed: list[str] = []
    for slug, info_d in registered.items():
        wpath = Path(info_d.get("absolute_path") or info_d.get("path") or "")
        if not wpath.exists():
            orphan_indexed.append(slug)

    # Check disk against registered
    wt_dir = PROTOCOL / "worktrees"
    on_disk: list[str] = []
    if wt_dir.is_dir():
        on_disk = [d.name for d in wt_dir.iterdir() if d.is_dir()]
    unregistered = [d for d in on_disk if d not in registered]

    if orphan_indexed:
        out.append(warn("worktree index", f"{len(orphan_indexed)} registered "
                        f"but missing on disk: {orphan_indexed}"))
    if unregistered:
        out.append(warn("worktree dir", f"{len(unregistered)} on disk but not "
                        f"in status.json: {unregistered}"))
    if not orphan_indexed and not unregistered:
        out.append(ok("worktrees", f"{len(registered)} registered, all consistent"))
    return out


def check_events_jsonl() -> list[Check]:
    p = PROTOCOL / "events.jsonl"
    if not p.is_file():
        return [info("events.jsonl", "not present")]
    bad = 0
    total = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            json.loads(line)
        except json.JSONDecodeError:
            bad += 1
    if bad == 0:
        return [ok("events.jsonl", f"{total} events parse cleanly")]
    return [warn("events.jsonl", f"{bad}/{total} lines fail to parse")]


def check_scripts_executable() -> list[Check]:
    out: list[Check] = []
    scripts_dir = SCRIPT_PATH.parent
    # We expect these to exist + compile
    expected = [
        "tcad_handoff.py", "tcad_conduct.py", "tcad_worktree.py",
        "tcad_log.py", "tcad_scan.py", "tcad_check_boundaries.py",
        "tcad_review.py", "tcad_graph.py", "tcad_profile.py",
        "tcad_atlas.py", "tcad_init.py", "tcad_doctor.py",
        "_tcad_root.py", "_tcad_lock.py",
    ]
    missing: list[str] = []
    syntax_errors: list[str] = []
    for name in expected:
        p = scripts_dir / name
        if not p.is_file():
            missing.append(name)
            continue
        try:
            import py_compile
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError:
            syntax_errors.append(name)
    if missing:
        out.append(fail("scripts present", f"missing: {missing}"))
    else:
        out.append(ok("scripts present", f"{len(expected)} scripts"))
    if syntax_errors:
        out.append(fail("scripts compile", f"errors: {syntax_errors}"))
    else:
        out.append(ok("scripts compile"))
    return out


def check_git() -> list[Check]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(ROOT), text=True, capture_output=True, check=False,
        )
        if out.returncode != 0:
            return [warn("git repo", f"target {ROOT} is not a git repo")]
    except FileNotFoundError:
        return [fail("git", "git not available on PATH")]
    return [ok("git repo")]


def check_profile() -> list[Check]:
    p = PROTOCOL / "project_profile.json"
    if not p.is_file():
        return [info("project profile", "absent — run `tcad profile detect`")]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [fail("project profile", "invalid JSON")]
    return [ok("project profile",
               f"type={data.get('project', {}).get('type')} "
               f"backend={data.get('stack', {}).get('backend')} "
               f"frontend={data.get('stack', {}).get('frontend')}")]


def check_atlas() -> list[Check]:
    p = PROTOCOL / "atlas" / "atlas.json"
    if not p.is_file():
        return [info("atlas", "absent — run `tcad atlas build`")]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [fail("atlas", "atlas.json is invalid JSON")]
    return [ok("atlas",
               f"{data.get('wps_total', 0)} WPs, "
               f"{len(data.get('layers', []))} layers")]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
SYMBOL = {"ok": "✓", "warn": "!", "fail": "✗", "info": "·"}
COLOR_TEXT = {
    "ok": "\033[32m",
    "warn": "\033[33m",
    "fail": "\033[31m",
    "info": "\033[37m",
}
RESET = "\033[0m"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tcad doctor", description=__doc__)
    p.add_argument("--json", action="store_true",
                   help="Emit machine-readable JSON report.")
    p.add_argument("--no-color", action="store_true",
                   help="Disable ANSI colors.")
    p.add_argument("--fix-suggestions", action="store_true",
                   help="(default on) Print suggested commands for each warning/fail.")
    p.add_argument("--no-suggestions", action="store_true",
                   help="Suppress suggestion section.")
    args = p.parse_args(argv)

    checks: list[Check] = []
    checks += check_protocol_dir()
    if (PROTOCOL).exists():
        checks += check_required_files()
        checks += check_status_json()
        checks += check_handoffs()
        checks += check_worktrees()
        checks += check_events_jsonl()
        checks += check_profile()
        checks += check_atlas()
    checks += check_scripts_executable()
    checks += check_git()

    # Counts
    counts = {"ok": 0, "warn": 0, "fail": 0, "info": 0}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1

    if args.json:
        print(json.dumps({
            "root": str(ROOT),
            "counts": counts,
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail}
                       for c in checks],
        }, indent=2))
        return 2 if counts["fail"] else 0

    use_color = (not args.no_color) and sys.stdout.isatty()
    def col(s: str, status: str) -> str:
        if not use_color:
            return s
        return f"{COLOR_TEXT.get(status, '')}{s}{RESET}"

    print(f"TCAD Doctor — root: {ROOT}")
    print(f"  Python: {sys.version.split()[0]}")
    print()
    for c in checks:
        sym = SYMBOL.get(c.status, "?")
        line = f"  {sym} {c.name}"
        if c.detail:
            line += f"    {c.detail}"
        print(col(line, c.status))
    print()
    print(f"Summary: "
          f"{counts['ok']} ok, "
          f"{counts['warn']} warn, "
          f"{counts['fail']} fail, "
          f"{counts['info']} info")

    # Phase 3.5: emit suggestions unless explicitly disabled
    if not args.no_suggestions:
        suggestions = []
        for c in checks:
            if c.status not in ("warn", "fail", "info"):
                continue
            hint = suggestion_for(c.name, c.detail)
            if hint:
                suggestions.append((c.name, hint))
        if suggestions:
            print()
            print("Suggestions:")
            for name, hint in suggestions:
                print(f"  • {name}: {hint}")
    if counts["fail"]:
        return 2
    return 0


def suggestion_for(name: str, detail: str) -> str | None:
    """Map a check name + detail to a suggested command. Idempotent."""
    n = name.lower()
    if ".protocol/ present" in n and "not found" in detail.lower():
        return "tcad init"
    if "status.json" in n and "absent" in detail.lower():
        return "tcad conduct init"
    if "project profile" in n and "absent" in detail.lower():
        return "tcad profile detect"
    if "atlas" in n and "absent" in detail.lower():
        return "tcad atlas build"
    if "scripts present" in n and "missing" in detail.lower():
        return "Reinstall TCAD-H: cd ~/.tcad-h && ./install.sh"
    if "scripts compile" in n and "errors" in detail.lower():
        return "Run: python3 -m py_compile scripts/*.py  (then check stderr)"
    if "worktree index" in n and "missing on disk" in detail.lower():
        return "tcad worktree prune  (drops stale entries from status.json)"
    if "worktree dir" in n and "not in status.json" in detail.lower():
        return "tcad worktree list  (then destroy stale dirs manually if needed)"
    if "git" in n and "not available" in detail.lower():
        return "Install git and rerun tcad doctor"
    if "events.jsonl" in n and "fail to parse" in detail.lower():
        return "Inspect .protocol/events.jsonl manually; remove malformed lines"
    if "wp " in n and "missing" in detail.lower() and ".tcad_wp.json" in detail.lower():
        return "Add .tcad_wp.json metadata (legacy WP — see docs/CONCEPTS.md)"
    if "wp " in n and "missing" in detail.lower():
        return f"Fill the missing files inside the WP folder"
    return None


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
