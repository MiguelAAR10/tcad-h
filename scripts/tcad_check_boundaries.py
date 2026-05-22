#!/usr/bin/env python3
"""
tcad_check_boundaries.py — TCAD-H Boundary Firewall.

Phase 1.8 deliverable. Mentor critique applied:
    "Don't trust LLM compliance. Use OS-level filesystem firewall."

This script is a DETERMINISTIC validator. Zero LLM tokens. Zero network.
Reads:
    - .protocol/boundaries.yaml      (global allow/deny)
    - .protocol/status.json          (active_wp, if any)
    - WP 02_allowed_files.md         (WP-scope allow list)
    - WP 03_forbidden_files.md       (WP-scope deny list)
    - `git diff --name-only`         (what changed in the working tree)
    - `git diff --name-only --cached` (what is staged)

Usage:
    python3 scripts/tcad_check_boundaries.py             # check vs working tree
    python3 scripts/tcad_check_boundaries.py --staged    # check vs staged files
    python3 scripts/tcad_check_boundaries.py --files a.py b.py
    python3 scripts/tcad_check_boundaries.py --rollback  # auto-revert violations
    python3 scripts/tcad_check_boundaries.py --json      # machine-readable output

Exit codes:
    0   no violations
    1   bad arguments
    2   global_deny violation (HARD FAIL)
    3   WP-scope violation (soft fail unless --strict)
    4   require_human_approval triggered (WARN)

Use as a pre-commit hook by symlinking to .git/hooks/pre-commit.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parent.parent
PROTOCOL_DIR = ROOT / ".protocol"
BOUNDARIES_FILE = PROTOCOL_DIR / "boundaries.yaml"
BOUNDARIES_EXAMPLE = PROTOCOL_DIR / "boundaries.yaml.example"
STATUS_FILE = PROTOCOL_DIR / "status.json"
HANDOFFS_DIR = PROTOCOL_DIR / "handoffs"


# ---------------------------------------------------------------------------
# Minimal YAML parser (reuse the one from studio/server.py philosophy)
# ---------------------------------------------------------------------------
class TinyYAML:
    """Parse boundaries.yaml. Supports dict/list/scalar + comments + quoted strings."""

    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.pos = 0

    def parse(self) -> Any:
        result, _ = self._block(0)
        return result

    def _peek(self) -> str | None:
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            if line.strip() == "" or line.strip().startswith("#"):
                self.pos += 1
                continue
            return line
        return None

    def _indent(self, line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def _scalar(self, raw: str) -> Any:
        raw = raw.strip()
        # strip inline comment if not inside quotes
        if raw and not (raw.startswith('"') or raw.startswith("'")):
            raw = raw.split("#", 1)[0].rstrip()
        if raw == "" or raw.lower() == "null" or raw == "~":
            return None
        if raw.lower() == "true":
            return True
        if raw.lower() == "false":
            return False
        if (raw.startswith('"') and raw.endswith('"')) or (
            raw.startswith("'") and raw.endswith("'")
        ):
            return raw[1:-1]
        try:
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            return raw

    def _block(self, indent: int):
        line = self._peek()
        if line is None:
            return None, indent
        li = self._indent(line)
        if li < indent:
            return None, li
        s = line.lstrip(" ")
        if s.startswith("- "):
            items = []
            while True:
                line = self._peek()
                if line is None:
                    break
                li = self._indent(line)
                if li != indent:
                    break
                s = line.lstrip(" ")
                if not s.startswith("- "):
                    break
                self.pos += 1
                rest = s[2:]
                if ":" in rest and not rest.startswith(('"', "'")):
                    synth = " " * (indent + 2) + rest
                    self.lines.insert(self.pos, synth)
                    item, _ = self._block(indent + 2)
                    items.append(item)
                elif rest.strip() == "":
                    item, _ = self._block(indent + 2)
                    items.append(item)
                else:
                    items.append(self._scalar(rest))
            return items, indent

        result: dict[str, Any] = {}
        while True:
            line = self._peek()
            if line is None:
                break
            li = self._indent(line)
            if li != indent:
                break
            s = line.lstrip(" ")
            if s.startswith("- "):
                break
            if ":" not in s:
                self.pos += 1
                continue
            key, _, rest = s.partition(":")
            key = key.strip()
            self.pos += 1
            rest_stripped = rest.split("#", 1)[0].rstrip() if not rest.lstrip().startswith(('"', "'")) else rest.rstrip()
            if rest_stripped.strip() == "":
                next_line = self._peek()
                if next_line is None or self._indent(next_line) <= indent:
                    result[key] = None
                    continue
                value, _ = self._block(self._indent(next_line))
                result[key] = value
            else:
                result[key] = self._scalar(rest_stripped)
        return result, indent


def load_yaml(path: Path) -> dict | None:
    if not path.exists():
        return None
    return TinyYAML(path.read_text(encoding="utf-8")).parse()


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------
def git_changed_files(staged: bool = False) -> list[str]:
    """Return list of changed file paths relative to ROOT."""
    args = ["git", "diff", "--name-only"]
    if staged:
        args.append("--cached")
    try:
        out = subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [f for f in out.strip().split("\n") if f]


def git_is_repo() -> bool:
    try:
        subprocess.check_output(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def git_checkout_file(path: str) -> bool:
    """Revert a file in the working tree (and unstage if staged)."""
    try:
        subprocess.check_call(
            ["git", "checkout", "--", path],
            cwd=ROOT, stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


# ---------------------------------------------------------------------------
# Boundary parsing
# ---------------------------------------------------------------------------
def parse_md_paths_list(file_path: Path) -> list[str]:
    """Extract bullet-list paths from a Markdown file like 02_allowed_files.md."""
    if not file_path.is_file():
        return []
    paths: list[str] = []
    for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        # Take everything after "- ", strip surrounding backticks/code fences.
        item = stripped[2:].strip()
        # Drop inline comment after "—" or "#".
        for sep in (" — ", " - ", "  #", "  --"):
            if sep in item:
                item = item.split(sep, 1)[0].rstrip()
        item = item.strip().strip("`")
        if item:
            paths.append(item)
    return paths


def get_active_wp_dir() -> Path | None:
    if not STATUS_FILE.exists():
        return None
    try:
        status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    wp = status.get("active_wp")
    if not wp:
        return None
    candidate = HANDOFFS_DIR / wp
    return candidate if candidate.is_dir() else None


def globs_match(path: str, patterns: list[str]) -> str | None:
    """Return the first matching pattern, or None."""
    for pat in patterns or []:
        # fnmatch handles ** by treating it as *. Use a small adapter:
        if _match_glob(path, pat):
            return pat
    return None


def _match_glob(path: str, pattern: str) -> bool:
    """Glob matcher that understands `**` as 'any depth'."""
    # Normalize Windows separators for safety.
    path = path.replace("\\", "/")
    pattern = pattern.replace("\\", "/")
    # Translate ** -> a sentinel, then translate the whole thing with fnmatch.
    # fnmatch's `*` does not cross `/`. We replicate the standard pathlib
    # semantics by splitting and recursing.
    parts_pat = pattern.split("/")
    parts_path = path.split("/")
    return _walk_match(parts_path, parts_pat)


def _walk_match(path_parts: list[str], pat_parts: list[str]) -> bool:
    if not pat_parts:
        return not path_parts
    head, rest = pat_parts[0], pat_parts[1:]
    if head == "**":
        # ** matches zero-or-more path segments.
        if not rest:
            return True
        for i in range(len(path_parts) + 1):
            if _walk_match(path_parts[i:], rest):
                return True
        return False
    if not path_parts:
        return False
    if fnmatch.fnmatchcase(path_parts[0], head):
        return _walk_match(path_parts[1:], rest)
    return False


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------
def evaluate(files: list[str]) -> dict[str, Any]:
    """Classify each changed file and aggregate verdicts.

    Output: { violations: { hard: [...], soft: [...], approval: [...] }, ok: [...] }
    """
    boundaries = load_yaml(BOUNDARIES_FILE) or load_yaml(BOUNDARIES_EXAMPLE) or {}
    global_deny = boundaries.get("global_deny", []) or []
    approval = boundaries.get("require_human_approval", []) or []
    protocol_allow = boundaries.get("protocol_write_allow", []) or []

    wp_dir = get_active_wp_dir()
    wp_allow: list[str] = []
    wp_deny: list[str] = []
    if wp_dir:
        wp_allow = parse_md_paths_list(wp_dir / "02_allowed_files.md")
        wp_deny = parse_md_paths_list(wp_dir / "03_forbidden_files.md")

    result = {
        "active_wp": wp_dir.name if wp_dir else None,
        "checked_files": files,
        "violations": {"hard": [], "soft": [], "approval": []},
        "ok": [],
    }

    for f in files:
        # 1. global_deny is HARD unless explicitly allowed by protocol_write_allow.
        deny_hit = globs_match(f, global_deny)
        if deny_hit:
            override = globs_match(f, protocol_allow)
            if not override:
                result["violations"]["hard"].append(
                    {"file": f, "reason": f"global_deny match: {deny_hit}"}
                )
                continue

        # 2. WP-specific forbidden.
        wp_deny_hit = globs_match(f, wp_deny)
        if wp_deny_hit:
            result["violations"]["hard"].append(
                {"file": f, "reason": f"WP 03_forbidden_files match: {wp_deny_hit}"}
            )
            continue

        # 3. WP allow list (if any).
        if wp_dir and wp_allow:
            wp_allow_hit = globs_match(f, wp_allow)
            if not wp_allow_hit:
                # Outside WP scope. Soft violation: worker should have raised delta.
                result["violations"]["soft"].append(
                    {"file": f, "reason": "outside 02_allowed_files of active WP"}
                )
                continue

        # 4. require_human_approval (WARN).
        approval_hit = globs_match(f, approval)
        if approval_hit:
            result["violations"]["approval"].append(
                {"file": f, "reason": f"requires human approval: {approval_hit}"}
            )
            continue

        result["ok"].append(f)

    return result


def render_report(report: dict, *, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2)
    lines = []
    wp = report.get("active_wp") or "(none)"
    lines.append(f"Active WP: {wp}")
    lines.append(f"Checked:   {len(report['checked_files'])} file(s)")
    hard = report["violations"]["hard"]
    soft = report["violations"]["soft"]
    appr = report["violations"]["approval"]
    ok = report["ok"]
    lines.append(
        f"Verdict:   hard={len(hard)}  soft={len(soft)}  approval={len(appr)}  ok={len(ok)}"
    )
    if hard:
        lines.append("\nHARD violations (firewall must reject):")
        for v in hard:
            lines.append(f"  ✗ {v['file']}    ({v['reason']})")
    if soft:
        lines.append("\nSOFT violations (scope escape — worker should have raised delta):")
        for v in soft:
            lines.append(f"  ⚠ {v['file']}    ({v['reason']})")
    if appr:
        lines.append("\nAPPROVAL required (human gate):")
        for v in appr:
            lines.append(f"  ◐ {v['file']}    ({v['reason']})")
    if ok and report.get("show_ok"):
        lines.append("\nOK:")
        for f in ok:
            lines.append(f"  ✓ {f}")
    return "\n".join(lines)


def apply_rollback(report: dict) -> int:
    """Revert HARD-violating files via `git checkout --`. Returns count reverted."""
    n = 0
    for v in report["violations"]["hard"]:
        if git_checkout_file(v["file"]):
            print(f"  ↩ reverted: {v['file']}", file=sys.stderr)
            n += 1
        else:
            print(f"  ! could not revert: {v['file']}", file=sys.stderr)
    return n


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="tcad_check_boundaries",
        description="TCAD-H boundary firewall. Deterministic. Zero LLM tokens.",
    )
    p.add_argument("--staged", action="store_true",
                   help="Check staged files (git diff --cached).")
    p.add_argument("--files", nargs="*", default=None,
                   help="Check explicit file list instead of git diff.")
    p.add_argument("--rollback", action="store_true",
                   help="On hard violation, run `git checkout --` to revert.")
    p.add_argument("--strict", action="store_true",
                   help="Treat soft violations as hard (exit 2).")
    p.add_argument("--json", action="store_true", help="Output JSON.")
    p.add_argument("--show-ok", action="store_true",
                   help="Also list files that passed.")
    args = p.parse_args(argv)

    # Resolve files to check.
    if args.files is not None:
        files = list(args.files)
    else:
        if not git_is_repo():
            print("Not a git repo and no --files provided.", file=sys.stderr)
            return 1
        files = git_changed_files(staged=args.staged)

    if not files:
        print("No changed files to check.")
        return 0

    report = evaluate(files)
    if args.show_ok:
        report["show_ok"] = True
    print(render_report(report, fmt="json" if args.json else "text"))

    hard = report["violations"]["hard"]
    soft = report["violations"]["soft"]
    appr = report["violations"]["approval"]

    if args.rollback and hard:
        print("\nRolling back HARD violations...", file=sys.stderr)
        apply_rollback(report)

    if hard:
        return 2
    if args.strict and soft:
        return 3
    if soft:
        # Non-strict: emit warning but exit 0 for the soft cases. Phase 1.8
        # default is to surface, not block, soft violations.
        return 0
    if appr:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
