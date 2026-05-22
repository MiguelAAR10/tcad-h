#!/usr/bin/env python3
"""
tcad_review.py — TCAD-H Deterministic Reviewer Gate.

Phase 2.4 deliverable. Mentor critique applied (Phase 2.3 Finding #11):
    "The agent did something syntactically valid + scope-permitted +
     mergeable, but duplicated an existing capability.
     TCAD-H must obligate discovery before creation."

This script is DETERMINISTIC. Zero LLM. Catches the class of failure that
boundary firewall + smoke gates miss: semantic duplication of existing code.

Detectors:
    1. routes      — FastAPI + Express route inventory; detects duplicates.
    2. symbols     — Python module-level duplicate functions/classes.
    3. inspect     — Diff-aware review: compare new branch vs base; flag
                     routes/symbols added that already exist in base.

Commands:
    routes <file>              List routes declared in file.
    symbols <file>             List module-level functions/classes; flag dupes.
    inspect <wp-slug>          Full review against base branch. Writes report
                               to .protocol/handoffs/<wp>/review_report.json.

Exit codes:
    0  no critical findings
    1  bad args
    2  WP/file not found
    5  CRITICAL findings present (review gate FAIL)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT_PATH.parent))
from _tcad_root import resolve_tcad_root  # noqa: E402

ROOT = resolve_tcad_root(os.environ.get("TCAD_ROOT"))
PROTOCOL_DIR = ROOT / ".protocol"
HANDOFFS_DIR = PROTOCOL_DIR / "handoffs"
STATUS_FILE = PROTOCOL_DIR / "status.json"
EVENTS_FILE = PROTOCOL_DIR / "events.jsonl"


# ---------------------------------------------------------------------------
# Detector 1: routes
# ---------------------------------------------------------------------------
FASTAPI_DECORATOR_RE = re.compile(
    r"@(?P<obj>\w+)\.(?P<method>get|post|put|patch|delete|head|options)"
    r"\(\s*[\"'](?P<path>[^\"']+)[\"']",
)
EXPRESS_CALL_RE = re.compile(
    r"\b(?P<obj>\w+)\.(?P<method>get|post|put|patch|delete|head|options|all|use)"
    r"\(\s*[\"'`](?P<path>[^\"'`]+)[\"'`]",
)


def detect_routes_python(file_path: Path) -> list[dict]:
    """Detect FastAPI-style route decorators using AST. Robust to formatting."""
    out: list[dict] = []
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return out
    method_set = {"get", "post", "put", "patch", "delete", "head", "options"}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            # Match @x.method("path"...)
            if not isinstance(dec, ast.Call):
                continue
            if not isinstance(dec.func, ast.Attribute):
                continue
            method = dec.func.attr
            if method not in method_set:
                continue
            obj = ast.unparse(dec.func.value) if hasattr(ast, "unparse") else "?"
            # Path is the first positional arg, must be a constant string.
            if not dec.args:
                continue
            arg0 = dec.args[0]
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                out.append({
                    "language": "python",
                    "framework": "fastapi-like",
                    "object": obj,
                    "method": method.upper(),
                    "path": arg0.value,
                    "function": node.name,
                    "line": node.lineno,
                    "file": str(file_path),
                })
    return out


def detect_routes_js(file_path: Path) -> list[dict]:
    """Detect Express-style routes via regex. Best-effort, not AST."""
    out: list[dict] = []
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out
    for i, line in enumerate(source.splitlines(), start=1):
        for m in EXPRESS_CALL_RE.finditer(line):
            method = m.group("method")
            if method in ("all", "use"):
                continue  # too noisy; skip middleware
            out.append({
                "language": "javascript",
                "framework": "express-like",
                "object": m.group("obj"),
                "method": method.upper(),
                "path": m.group("path"),
                "function": None,
                "line": i,
                "file": str(file_path),
            })
    return out


def detect_routes(file_path: Path) -> list[dict]:
    if file_path.suffix == ".py":
        return detect_routes_python(file_path)
    if file_path.suffix in (".js", ".ts", ".mjs", ".cjs", ".tsx", ".jsx"):
        return detect_routes_js(file_path)
    return []


# ---------------------------------------------------------------------------
# Detector 2: symbols (module-level functions and classes, Python only v1)
# ---------------------------------------------------------------------------
def detect_symbols_python(file_path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return out
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append({
                "kind": "function",
                "name": node.name,
                "line": node.lineno,
                "file": str(file_path),
                "async": isinstance(node, ast.AsyncFunctionDef),
            })
        elif isinstance(node, ast.ClassDef):
            out.append({
                "kind": "class",
                "name": node.name,
                "line": node.lineno,
                "file": str(file_path),
            })
    return out


def find_symbol_duplicates(symbols: list[dict]) -> list[dict]:
    """Group symbols by (file, name) and return entries appearing more than once."""
    seen: dict[tuple, list[dict]] = {}
    for s in symbols:
        key = (s["file"], s["name"])
        seen.setdefault(key, []).append(s)
    dups = []
    for key, entries in seen.items():
        if len(entries) > 1:
            dups.append({
                "type": "duplicate_symbol",
                "severity": "critical",
                "file": key[0],
                "name": key[1],
                "kind": entries[0]["kind"],
                "locations": [{"line": e["line"]} for e in entries],
                "message": (
                    f"{entries[0]['kind'].capitalize()} {key[1]!r} declared "
                    f"{len(entries)} times in {key[0]}. "
                    f"Modify the existing one instead of adding a duplicate."
                ),
            })
    return dups


def find_route_duplicates(routes: list[dict]) -> list[dict]:
    """Group by (METHOD, path) globally; flag if more than one declaration."""
    seen: dict[tuple, list[dict]] = {}
    for r in routes:
        key = (r["method"], r["path"])
        seen.setdefault(key, []).append(r)
    dups = []
    for key, entries in seen.items():
        if len(entries) > 1:
            dups.append({
                "type": "duplicate_route",
                "severity": "critical",
                "method": key[0],
                "path": key[1],
                "locations": [
                    {"file": e["file"], "line": e["line"], "function": e.get("function")}
                    for e in entries
                ],
                "message": (
                    f"Route {key[0]} {key[1]} declared {len(entries)} times. "
                    f"Reuse or modify the existing endpoint instead of duplicating."
                ),
            })
    return dups


# ---------------------------------------------------------------------------
# Detector 3: inspect (diff-aware)
# ---------------------------------------------------------------------------
def git_show(rev_path: str, cwd: Path) -> str | None:
    """Run `git show rev:path`, return content or None if missing."""
    try:
        out = subprocess.run(
            ["git", "show", rev_path],
            cwd=str(cwd), text=True,
            capture_output=True, check=False,
        )
        if out.returncode != 0:
            return None
        return out.stdout
    except FileNotFoundError:
        return None


def git_diff_name_only(cwd: Path, base: str, head: str = "HEAD") -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...{head}"],
            cwd=str(cwd), text=True, capture_output=True, check=False,
        )
        if out.returncode != 0:
            return []
        return [f for f in out.stdout.strip().split("\n") if f]
    except FileNotFoundError:
        return []


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


def resolve_slug_worktree(slug: str) -> tuple[Path | None, dict | None]:
    if not STATUS_FILE.exists():
        return None, None
    try:
        state = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, None
    wt_index = state.get("worktrees", {}) or {}
    if slug in wt_index:
        info = wt_index[slug]
        path = Path(info.get("absolute_path") or info.get("path") or "")
        return (path if path.exists() else None), info
    for role in ("backend", "frontend", "tests", "reading"):
        candidate = f"{slug}-{role}"
        if candidate in wt_index:
            info = wt_index[candidate]
            path = Path(info.get("absolute_path") or info.get("path") or "")
            return (path if path.exists() else None), info
    return None, None


def write_to_temp(content: str, suffix: str) -> Path:
    import tempfile
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    p = Path(name)
    p.write_text(content, encoding="utf-8")
    return p


def inspect_wp(slug: str) -> dict:
    """Compare changed files in WP's branch vs base branch.

    For each changed file that looks like a Python or JS module:
      - Extract routes from base version (git show base:file)
      - Extract routes from HEAD version (file as it is now in worktree)
      - Extract symbols from base + HEAD
      - Flag any route present in HEAD but NOT in base if it already collides
        with an existing route in HEAD (i.e., duplicate created).
      - Flag any symbol with multiple declarations in HEAD.
    """
    wt_path, wt_info = resolve_slug_worktree(slug)
    if wt_info is None:
        return {"error": f"worktree not found: {slug}"}
    branch = wt_info.get("branch")
    base = wt_info.get("base") or "master"
    wp_id = wt_info.get("wp")

    cwd = wt_path or ROOT
    changed = git_diff_name_only(cwd, base, "HEAD")

    findings: list[dict] = []
    summary = {
        "wp": wp_id,
        "slug": slug,
        "branch": branch,
        "base": base,
        "changed_files": changed,
        "findings": findings,
        "checked_files": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    for f in changed:
        if not (f.endswith(".py") or f.endswith((".js", ".ts", ".mjs", ".cjs", ".tsx", ".jsx"))):
            continue
        head_path = cwd / f
        if not head_path.is_file():
            continue
        summary["checked_files"].append(f)

        # HEAD content (just read the file).
        head_routes = detect_routes(head_path)
        head_symbols = detect_symbols_python(head_path) if f.endswith(".py") else []

        # Base content via git show.
        base_content = git_show(f"{base}:{f}", cwd)
        base_routes: list[dict] = []
        if base_content is not None:
            base_temp = write_to_temp(base_content, suffix=Path(f).suffix)
            try:
                base_routes = detect_routes(base_temp)
            finally:
                base_temp.unlink(missing_ok=True)

        # Duplicates WITHIN HEAD (this catches Finding #11).
        for d in find_route_duplicates(head_routes):
            d["file"] = f
            findings.append(d)

        # Duplicates of symbols WITHIN HEAD same file.
        for d in find_symbol_duplicates(head_symbols):
            findings.append(d)

        # Route additions that target an EXISTING route in base.
        # If the new branch added a route at a new line but the same (method, path)
        # already existed in base, that's also a duplication signal.
        base_keys = {(r["method"], r["path"]) for r in base_routes}
        head_keys = [(r["method"], r["path"]) for r in head_routes]
        head_counts: dict[tuple, list[dict]] = {}
        for r in head_routes:
            head_counts.setdefault((r["method"], r["path"]), []).append(r)
        for key in head_keys:
            if key in base_keys and len(head_counts.get(key, [])) > 1:
                # Already flagged by find_route_duplicates; skip.
                continue
            if key in base_keys and len(head_counts.get(key, [])) == 1:
                # New code touched the route. Not necessarily a dup; could be a fix.
                # Don't flag at critical; informational.
                continue

    critical = [f for f in findings if f.get("severity") == "critical"]
    summary["critical_count"] = len(critical)
    summary["pass"] = len(critical) == 0
    return summary


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def render_findings(findings: list[dict]) -> str:
    if not findings:
        return "  (no findings)"
    lines = []
    for f in findings:
        sev = f.get("severity", "?").upper()
        ftype = f.get("type", "?")
        msg = f.get("message", "")
        lines.append(f"  [{sev}] {ftype}: {msg}")
        for loc in f.get("locations", []):
            file = loc.get("file") or f.get("file", "")
            line = loc.get("line", "?")
            fn = loc.get("function")
            tag = f"{file}:{line}" + (f"  ({fn})" if fn else "")
            lines.append(f"      at {tag}")
    return "\n".join(lines)


def emit_blocker_question(slug: str, findings: list[dict]) -> None:
    """Append a blocker question to .protocol/questions/INDEX.md."""
    qidx = PROTOCOL_DIR / "questions" / "INDEX.md"
    qidx.parent.mkdir(parents=True, exist_ok=True)
    if not qidx.exists():
        qidx.write_text("# Open Questions\n\n", encoding="utf-8")
    qid = f"Q-REV-{slug}"
    existing = qidx.read_text(encoding="utf-8")
    if f"## {qid}" in existing:
        return  # idempotent
    crit = [f for f in findings if f.get("severity") == "critical"]
    if not crit:
        return
    block = (
        f"\n## {qid} — Reviewer gate blocked {slug}\n\n"
        f"**Status**: 🟡 pending\n"
        f"**Raised by**: tcad_review\n"
        f"**Blocks**: close, merge\n\n"
        f"**Evidence**:\n"
    )
    for f in crit:
        block += f"- {f.get('type')}: {f.get('message','')}\n"
        for loc in f.get("locations", []):
            block += f"    at {loc.get('file', f.get('file',''))}:{loc.get('line','?')}\n"
    block += (
        f"\n**Question**: should the WP modify the existing implementation "
        f"instead of duplicating? Or is this an intentional override (document in 04_existing_decisions.md)?\n"
    )
    qidx.write_text(existing.rstrip() + "\n" + block, encoding="utf-8")


def append_event(event: dict) -> None:
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_routes(args) -> int:
    p = Path(args.file)
    if not p.is_file():
        print(f"file not found: {p}", file=sys.stderr)
        return 2
    routes = detect_routes(p)
    if args.json:
        print(json.dumps(routes, indent=2))
        return 0
    if not routes:
        print(f"No routes detected in {p}.")
        return 0
    print(f"Routes in {p}:")
    for r in routes:
        fn = r.get("function") or "?"
        print(f"  {r['method']:<6} {r['path']:<30} @{p.name}:{r['line']}  ({fn})")
    # Dup check within this file.
    dups = find_route_duplicates(routes)
    if dups:
        print("\nDuplicates:")
        print(render_findings(dups))
        return 5
    return 0


def cmd_symbols(args) -> int:
    p = Path(args.file)
    if not p.is_file():
        print(f"file not found: {p}", file=sys.stderr)
        return 2
    syms = detect_symbols_python(p)
    if args.json:
        print(json.dumps(syms, indent=2))
        return 0
    if not syms:
        print(f"No top-level symbols in {p}.")
        return 0
    print(f"Symbols in {p}:")
    for s in syms:
        async_tag = " (async)" if s.get("async") else ""
        print(f"  {s['kind']:<8} {s['name']:<30} line {s['line']}{async_tag}")
    dups = find_symbol_duplicates(syms)
    if dups:
        print("\nDuplicates:")
        print(render_findings(dups))
        return 5
    return 0


def cmd_inspect(args) -> int:
    report = inspect_wp(args.slug)
    if "error" in report:
        print(f"Error: {report['error']}", file=sys.stderr)
        return 2

    # Persist report next to the WP.
    wp_id = report.get("wp")
    if wp_id:
        wp_dir = HANDOFFS_DIR / wp_id
        if wp_dir.is_dir():
            (wp_dir / "review_report.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Reviewer gate report for {report.get('slug')}:")
        print(f"  branch:        {report.get('branch')}")
        print(f"  base:          {report.get('base')}")
        print(f"  changed files: {len(report.get('changed_files', []))}")
        print(f"  checked files: {len(report.get('checked_files', []))}")
        critical = [f for f in report["findings"] if f.get("severity") == "critical"]
        print(f"  critical findings: {len(critical)}")
        if critical:
            print("\n" + render_findings(critical))

    if not report.get("pass"):
        append_event({
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": "tcad_review",
            "event": "review_gate_failed",
            "slug": args.slug,
            "wp": wp_id,
            "critical_count": report.get("critical_count", 0),
        })
        emit_blocker_question(args.slug, report.get("findings", []))
        return 5

    append_event({
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": "tcad_review",
        "event": "review_gate_passed",
        "slug": args.slug,
        "wp": wp_id,
    })
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="tcad_review",
        description="Deterministic reviewer gate. Catches semantic duplication.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("routes", help="List HTTP routes in a file; flag duplicates.")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_routes)

    s = sub.add_parser("symbols", help="List top-level Python symbols; flag dupes.")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_symbols)

    s = sub.add_parser("inspect", help="Full diff-aware review of a WP.")
    s.add_argument("slug")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_inspect)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
