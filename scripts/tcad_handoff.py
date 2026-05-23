#!/usr/bin/env python3
"""
tcad_handoff.py — Generate a Work Package folder from the _template.

TCAD-H Protocol v2.4, Phase 1 deliverable.

No LLM calls. No external services. Standard library only.

Usage:
    python scripts/tcad_handoff.py \\
        --name "add-health-endpoint" \\
        --goal "Add a /health endpoint returning 200" \\
        --role backend

Effect:
    Creates .protocol/handoffs/WP-NNN-<slug>/ with the 12 template files,
    light-filling name, date, goal, and role placeholders where applicable.

Exit codes:
    0  success
    1  invalid arguments
    2  template missing or unreadable
    3  destination already exists (WP collision)
    4  validation failure after generation
"""

from __future__ import annotations

import argparse
import os
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate the framework root regardless of where the script is invoked from.
# Convention: this script lives at <root>/scripts/tcad_handoff.py
# ---------------------------------------------------------------------------
SCRIPT_PATH = Path(__file__).resolve()
import sys as _sys
_sys.path.insert(0, str(SCRIPT_PATH.parent))
from _tcad_root import resolve_tcad_root  # noqa: E402
ROOT = resolve_tcad_root(os.environ.get("FOREMAN_ROOT") or os.environ.get("TCAD_ROOT"))
TEMPLATE_DIR = ROOT / ".protocol" / "handoffs" / "_template"
HANDOFFS_DIR = ROOT / ".protocol" / "handoffs"
STATUS_FILE = ROOT / ".protocol" / "status.json"
STATUS_EXAMPLE = ROOT / ".protocol" / "status.json.example"

VALID_ROLES = {"backend", "frontend", "tests", "reading"}

# Verbose mode: full 12-file template (rich didactic context).
VERBOSE_FILES = [
    "00_context.md",
    "01_goal.md",
    "02_allowed_files.md",
    "03_forbidden_files.md",
    "04_existing_decisions.md",
    "05_worker_prompt_backend.md",
    "06_worker_prompt_frontend.md",
    "07_worker_prompt_tests.md",
    "08_worker_prompt_reading.md",
    "09_reviewer_prompt.md",
    "10_acceptance_criteria.md",
    "21_open_questions.md",
]

# Lean mode (Phase 1.9 KISS): 4 base + 1 role-specific worker prompt = 5 files.
LEAN_FILES_BASE = [
    "01_goal.md",
    "02_allowed_files.md",
    "03_forbidden_files.md",
    "10_acceptance_criteria.md",
]
LEAN_ROLE_PROMPT = {
    "backend":  "05_worker_prompt_backend.md",
    "frontend": "06_worker_prompt_frontend.md",
    "tests":    "07_worker_prompt_tests.md",
    "reading":  "08_worker_prompt_reading.md",
}


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="tcad_handoff",
        description="Generate a TCAD-H Work Package folder from the _template.",
    )
    p.add_argument(
        "--name",
        required=True,
        help='Short slug for the Work Package, e.g. "add-health-endpoint".',
    )
    p.add_argument(
        "--goal",
        required=True,
        help="One-sentence description of the goal; inserted into 01_goal.md.",
    )
    p.add_argument(
        "--role",
        required=True,
        choices=sorted(VALID_ROLES),
        help="Primary worker role for this Work Package.",
    )
    p.add_argument(
        "--id",
        default=None,
        help="Explicit numeric ID (e.g. 042). If omitted, auto-incremented.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing files.",
    )
    p.add_argument(
        "--lean",
        action="store_true",
        help=(
            "Lean mode (Phase 1.9 KISS): generate 5 files instead of 12. "
            "01_goal + 02_allowed + 03_forbidden + 10_acceptance + the role prompt."
        ),
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def slugify(text: str) -> str:
    """Lowercase, alphanumerics and dashes only, collapse runs."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def next_wp_id() -> str:
    """Scan existing WP folders and return the next zero-padded 3-digit id."""
    if not HANDOFFS_DIR.exists():
        return "001"
    existing = []
    pattern = re.compile(r"^WP-(\d+)-")
    for child in HANDOFFS_DIR.iterdir():
        if not child.is_dir():
            continue
        # Skip the template directory.
        if child.name.startswith("_"):
            continue
        match = pattern.match(child.name)
        if match:
            existing.append(int(match.group(1)))
    next_int = (max(existing) + 1) if existing else 1
    return f"{next_int:03d}"


def fill_placeholders(content: str, ctx: dict) -> str:
    """Light templating: replace WP_ID / WP_DATE / WP_GOAL / WP_ROLE tokens.

    The templates do not currently use tokens, so this is a safety pass for
    future template revisions. Today it inserts a small header block at the
    top of 00_context.md and 01_goal.md.
    """
    # Replace tokens of the form {{WP_X}}.
    for key, value in ctx.items():
        content = content.replace("{{" + key + "}}", value)
    return content


def header_block(ctx: dict) -> str:
    """Frontmatter-ish header injected at the top of every generated file."""
    return (
        f"<!-- TCAD-H Work Package\n"
        f"     id: {ctx['WP_ID']}\n"
        f"     slug: {ctx['WP_SLUG']}\n"
        f"     created: {ctx['WP_DATE']}\n"
        f"     primary_role: {ctx['WP_ROLE']}\n"
        f"     goal: {ctx['WP_GOAL']}\n"
        f"-->\n\n"
    )


def write_file(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] would write {path}")
        return
    path.write_text(content, encoding="utf-8")


def files_for_mode(lean: bool, role: str) -> list[str]:
    if not lean:
        return list(VERBOSE_FILES)
    return list(LEAN_FILES_BASE) + [LEAN_ROLE_PROMPT[role]]


def validate_template(files: list[str]) -> list[str]:
    """Return a list of error messages, empty if the template is valid."""
    errors: list[str] = []
    if not TEMPLATE_DIR.exists():
        errors.append(f"Template directory missing: {TEMPLATE_DIR}")
        return errors
    for required in files:
        if not (TEMPLATE_DIR / required).is_file():
            errors.append(f"Template file missing: {TEMPLATE_DIR / required}")
    return errors


def validate_generated(wp_dir: Path, files: list[str]) -> list[str]:
    """Confirm all required files exist after generation."""
    errors: list[str] = []
    for required in files:
        target = wp_dir / required
        if not target.is_file():
            errors.append(f"Missing generated file: {target}")
        elif target.stat().st_size == 0:
            errors.append(f"Empty generated file: {target}")
    return errors


def maybe_update_status(wp_id_full: str, dry_run: bool) -> None:
    """If a live status.json exists, suggest the new WP. Never overwrite state.

    For Phase 1 we only print a hint. Phase 1.5 (tcad_conduct.py) will manage
    real state transitions.
    """
    if not STATUS_FILE.exists():
        print(
            f"\nHint: no live .protocol/status.json yet (Phase 1.5 will create it).\n"
            f"      Example schema is at: {STATUS_EXAMPLE.relative_to(ROOT)}",
        )
        return
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"\nWarning: status.json is not valid JSON ({exc}).", file=sys.stderr)
        return
    active = data.get("active_wp")
    if active:
        print(
            f"\nNote: status.json already tracks active_wp={active!r}.\n"
            f"      Generated WP {wp_id_full} is NOT auto-activated. Use\n"
            f"      tcad_conduct.py (Phase 1.5) to transition state.",
        )
    else:
        print(
            f"\nNote: status.json has no active_wp. Generated WP {wp_id_full}\n"
            f"      is ready to be activated by tcad_conduct.py (Phase 1.5).",
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if not args.name.strip():
        print("Error: --name cannot be empty.", file=sys.stderr)
        return 1
    if not args.goal.strip():
        print("Error: --goal cannot be empty.", file=sys.stderr)
        return 1

    files_to_make = files_for_mode(args.lean, args.role)
    profile = "lean" if args.lean else "verbose"
    template_errors = validate_template(files_to_make)
    if template_errors:
        for err in template_errors:
            print(f"Template error: {err}", file=sys.stderr)
        return 2

    slug = slugify(args.name)
    if not slug:
        print(f"Error: --name {args.name!r} produced empty slug.", file=sys.stderr)
        return 1

    wp_id = args.id.zfill(3) if args.id else next_wp_id()
    wp_id_full = f"WP-{wp_id}-{slug}"
    wp_dir = HANDOFFS_DIR / wp_id_full

    if wp_dir.exists():
        print(
            f"Error: destination already exists: {wp_dir}\n"
            f"       Pick a different --name or --id, or remove the existing folder.",
            file=sys.stderr,
        )
        return 3

    today = dt.date.today().isoformat()
    ctx = {
        "WP_ID": wp_id_full,
        "WP_SLUG": slug,
        "WP_DATE": today,
        "WP_GOAL": args.goal,
        "WP_ROLE": args.role,
    }

    print(f"Generating Work Package: {wp_id_full}")
    print(f"  destination: {wp_dir.relative_to(ROOT)}")
    print(f"  goal:        {args.goal}")
    print(f"  role:        {args.role}")
    print(f"  date:        {today}")
    print(f"  mode:        {'lean (5 files)' if args.lean else 'verbose (12 files)'}")
    if args.dry_run:
        print("  dry-run:     ON (no files will be written)")

    if not args.dry_run:
        wp_dir.mkdir(parents=True, exist_ok=False)

    for filename in files_to_make:
        src = TEMPLATE_DIR / filename
        dst = wp_dir / filename
        try:
            content = src.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Error reading template {src}: {exc}", file=sys.stderr)
            return 2
        rendered = header_block(ctx) + fill_placeholders(content, ctx)
        write_file(dst, rendered, args.dry_run)

    if args.dry_run:
        print("\nDry run complete. No files were created.")
        return 0

    # Phase 2.2 Finding #1 fix: write profile metadata so tcad_conduct.py
    # validates the right file set.
    metadata = {
        "wp_id": wp_id_full,
        "profile": profile,
        "role": args.role,
        "required_files": files_to_make,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "schema_version": 1,
    }
    (wp_dir / ".tcad_wp.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    print(f"\nGenerated {len(files_to_make)} files under {wp_dir.relative_to(ROOT)}/")
    print(f"  profile: {profile}")

    gen_errors = validate_generated(wp_dir, files_to_make)
    if gen_errors:
        for err in gen_errors:
            print(f"Validation error: {err}", file=sys.stderr)
        print(
            "\nThe Work Package folder was created but failed validation.\n"
            "Inspect the listed files. Consider deleting and regenerating.",
            file=sys.stderr,
        )
        return 4

    maybe_update_status(wp_id_full, args.dry_run)

    print(
        "\nNext steps:\n"
        f"  1. Open {wp_dir.relative_to(ROOT)}/01_goal.md and refine the goal.\n"
        f"  2. Fill 02_allowed_files.md and 03_forbidden_files.md.\n"
        f"  3. Fill 04_existing_decisions.md with constraints.\n"
        f"  4. Fill 10_acceptance_criteria.md with testable bullets.\n"
        f"  5. Tailor 05_worker_prompt_{args.role}.md to the worker CLI.\n"
        f"  6. Hand the worker prompt to your worker CLI."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
