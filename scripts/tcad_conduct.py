#!/usr/bin/env python3
"""
tcad_conduct.py — TCAD-H Conductor FSM enforcer.

Phase 1.5 deliverable.

Stdlib only. No LLM calls. No external services.

What it does:
    - Persists Conductor state to .protocol/status.json
    - Enforces state transitions declared in .protocol/conductor.yaml
    - Tracks attempt_count for FIX_REQUEST cycles
    - Manages open_questions and applies blocks on transitions
    - Logs all transitions to status.json history (append-only)

What it does NOT do:
    - Edit production code
    - Invoke worker CLIs (Conductor delegates via Work Packages on disk)
    - Make LLM calls

Commands:
    init                 — create .protocol/status.json if missing
    status               — print current state, active WP, open questions
    transition <STATE>   — move to a new state if guard allows
    set-wp <WP-ID>       — activate a Work Package
    clear-wp             — deactivate the active Work Package
    add-question <args>  — register a blocking question
    resolve-question <id>— mark question as resolved and unblock
    snapshot             — write a timestamped snapshot to history
    guards               — print guard check results for current WP
    reset                — back to IDLE (requires --force; safety)

Exit codes:
    0   success
    1   invalid arguments
    2   illegal transition (guard or FSM)
    3   state file corruption
    4   guard failure
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parent.parent
PROTOCOL_DIR = ROOT / ".protocol"
STATUS_FILE = PROTOCOL_DIR / "status.json"
STATUS_EXAMPLE = PROTOCOL_DIR / "status.json.example"
HANDOFFS_DIR = PROTOCOL_DIR / "handoffs"
QUESTIONS_INDEX = PROTOCOL_DIR / "questions" / "INDEX.md"

SCHEMA_VERSION = "2.4"

# ---------------------------------------------------------------------------
# Canonical FSM (mirrors .protocol/conductor.yaml; duplicated to avoid YAML dep)
# ---------------------------------------------------------------------------
# Each tuple: (from_state, to_state, guard_name).
# The guard name is informational; we enforce a small set programmatically.
TRANSITIONS: list[tuple[str, str, str]] = [
    ("IDLE",            "INTAKE",           "human-request-received"),
    ("INTAKE",          "SPEC_DRAFT",       "spec-draft-written"),
    ("SPEC_DRAFT",      "INTAKE",           "spec-rejected-by-human"),
    ("SPEC_DRAFT",      "HANDOFF_GEN",      "spec-approved-by-human"),
    ("HANDOFF_GEN",     "WORKER_BRIEF",     "work-package-complete"),
    ("WORKER_BRIEF",    "WORKER_DONE",      "worker-wrote-11_summary"),
    ("WORKER_BRIEF",    "REWRITE_WP",       "worker-wrote-12_delta"),
    ("WORKER_BRIEF",    "ESCALATE",         "worker-wrote-13_blockers"),
    ("WORKER_DONE",     "ATLAS_GEN",        "phase-2.5-enabled"),
    ("WORKER_DONE",     "REVIEWING",        "phase-2.5-disabled"),
    ("ATLAS_GEN",       "REVIEWING",        "atlas-artifacts-present"),
    ("ATLAS_GEN",       "ATLAS_FAIL",       "atlas-script-failed"),
    ("ATLAS_FAIL",      "REVIEWING",        "manual-skip"),
    ("REVIEWING",       "PASS",             "reviewer-verdict-pass"),
    ("REVIEWING",       "PASS_WITH_NOTES",  "reviewer-verdict-pass-with-notes"),
    ("REVIEWING",       "FAIL",             "reviewer-verdict-fail"),
    ("FAIL",            "FIX_REQUEST",      "attempt-count-under-3"),
    ("FAIL",            "ESCALATE",         "attempt-count-3-plus"),
    ("FIX_REQUEST",     "WORKER_BRIEF",     "fix-cycle-restart"),
    ("REWRITE_WP",      "HANDOFF_GEN",      "wp-rewritten"),
    ("REWRITE_WP",      "ESCALATE",         "rewrite-blocked"),
    ("ESCALATE",        "INTAKE",           "human-resumes"),
    ("ESCALATE",        "DONE",             "human-cancels"),
    ("PASS",            "LOG",              "auto"),
    ("PASS_WITH_NOTES", "LOG",              "auto"),
    ("LOG",             "DONE",             "journal-entry-written"),
    ("DONE",            "IDLE",             "auto"),
]

ALL_STATES = sorted(
    {s for t in TRANSITIONS for s in (t[0], t[1])} | {"IDLE"}
)

MAX_ATTEMPT_COUNT = 3


# ---------------------------------------------------------------------------
# State I/O
# ---------------------------------------------------------------------------
def empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "active_wp": None,
        "state": "IDLE",
        "attempt_count": 0,
        "open_questions": [],
        "last_transition": None,
        "history": [],
        "metadata": {
            "conductor": "tcad_conduct.py",
            "started_at": None,
            "tokens_estimated": 0,
        },
    }


def load_state() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return empty_state()
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"Error: .protocol/status.json is corrupted ({exc}).\n"
            f"  Use 'tcad_conduct.py reset --force' to recreate it.",
            file=sys.stderr,
        )
        raise SystemExit(3)


def save_state(state: dict[str, Any]) -> None:
    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(
        json.dumps(state, indent=2, default=str), encoding="utf-8"
    )


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def append_history(
    state: dict[str, Any],
    *,
    from_state: str,
    to_state: str,
    actor: str,
    artifact: str | None = None,
    note: str | None = None,
) -> None:
    entry = {
        "ts": now(),
        "from": from_state,
        "to": to_state,
        "actor": actor,
    }
    if artifact:
        entry["artifact"] = artifact
    if note:
        entry["note"] = note
    state.setdefault("history", []).append(entry)
    state["last_transition"] = entry["ts"]


# ---------------------------------------------------------------------------
# Work Package helpers
# ---------------------------------------------------------------------------
WP_DIR_RE = re.compile(r"^WP-(\d+)-(.+)$")


def resolve_wp_dir(wp_id: str) -> Path | None:
    if not HANDOFFS_DIR.exists():
        return None
    direct = HANDOFFS_DIR / wp_id
    if direct.is_dir():
        return direct
    # Allow short form: just the digits like "001".
    if wp_id.isdigit():
        prefix = f"WP-{int(wp_id):03d}-"
        for child in HANDOFFS_DIR.iterdir():
            if child.is_dir() and child.name.startswith(prefix):
                return child
    return None


def wp_required_files(wp_dir: Path) -> dict[str, bool]:
    """Return file -> exists for the WP's required files.

    Phase 2.2 Finding #1 fix: read .tcad_wp.json metadata to pick the right
    file set. Lean WPs require 5 files, verbose WPs require 12.
    Falls back to verbose list for legacy WPs without metadata.
    """
    meta_path = wp_dir / ".tcad_wp.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            required = meta.get("required_files") or []
            if required:
                return {f: (wp_dir / f).is_file() for f in required}
        except (json.JSONDecodeError, OSError):
            pass
    # Legacy fallback: verbose 12 files.
    files = [
        "00_context.md", "01_goal.md", "02_allowed_files.md",
        "03_forbidden_files.md", "04_existing_decisions.md",
        "05_worker_prompt_backend.md", "06_worker_prompt_frontend.md",
        "07_worker_prompt_tests.md", "08_worker_prompt_reading.md",
        "09_reviewer_prompt.md", "10_acceptance_criteria.md",
        "21_open_questions.md",
    ]
    return {f: (wp_dir / f).is_file() for f in files}


def wp_evidence(wp_dir: Path) -> dict[str, Any]:
    """Return a dict of evidence files present in the WP folder."""
    out = {
        "has_summary": (wp_dir / "11_worker_summary.md").is_file(),
        "has_delta": (wp_dir / "12_delta.md").is_file(),
        "has_blockers": (wp_dir / "13_blockers.md").is_file(),
        "has_review": (wp_dir / "14_review_result.md").is_file(),
        "verdict": None,
        "summary_ready": False,
    }
    summary_path = wp_dir / "11_worker_summary.md"
    if summary_path.is_file():
        text = summary_path.read_text(encoding="utf-8", errors="ignore")
        out["summary_ready"] = "NEXT STEP: ready for review" in text
    review_path = wp_dir / "14_review_result.md"
    if review_path.is_file():
        text = review_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"VERDICT:\s*(\w+)", text)
        if m:
            out["verdict"] = m.group(1)
    return out


# ---------------------------------------------------------------------------
# Transition guards
# ---------------------------------------------------------------------------
def guard_ok(state: dict[str, Any], to_state: str) -> tuple[bool, str]:
    """Programmatic guard checks for transitions that can be machine-verified.

    Returns (ok, reason). Guards that require external evidence (human GO,
    artifacts) are checked when possible; otherwise we accept and rely on
    the caller's --note to record the basis.
    """
    from_state = state.get("state", "IDLE")

    # Generic: target must be a known state.
    if to_state not in ALL_STATES:
        return False, f"unknown target state: {to_state}"

    # Generic: transition must exist.
    legal = [(f, t) for (f, t, _) in TRANSITIONS]
    if (from_state, to_state) not in legal:
        return False, f"illegal transition {from_state} -> {to_state}"

    # Specific guards we can verify deterministically.
    active = state.get("active_wp")
    wp_dir = resolve_wp_dir(active) if active else None

    if to_state == "WORKER_DONE":
        if wp_dir is None:
            return False, "no active WP"
        ev = wp_evidence(wp_dir)
        if not ev["has_summary"]:
            return False, f"missing 11_worker_summary.md in {wp_dir.name}"
        if not ev["summary_ready"]:
            return False, "11_worker_summary.md missing 'NEXT STEP: ready for review'"

    if to_state == "REWRITE_WP":
        if wp_dir is None:
            return False, "no active WP"
        ev = wp_evidence(wp_dir)
        if not ev["has_delta"]:
            return False, f"missing 12_delta.md in {wp_dir.name}"

    if to_state == "ESCALATE" and from_state == "WORKER_BRIEF":
        if wp_dir is None:
            return False, "no active WP"
        ev = wp_evidence(wp_dir)
        if not ev["has_blockers"]:
            return False, f"missing 13_blockers.md in {wp_dir.name}"

    if to_state in ("PASS", "PASS_WITH_NOTES", "FAIL"):
        if wp_dir is None:
            return False, "no active WP"
        ev = wp_evidence(wp_dir)
        if not ev["has_review"]:
            return False, f"missing 14_review_result.md in {wp_dir.name}"
        expected = {
            "PASS": "PASS",
            "PASS_WITH_NOTES": "PASS_WITH_NOTES",
            "FAIL": "FAIL",
        }[to_state]
        if ev["verdict"] != expected:
            return (
                False,
                f"reviewer verdict is {ev['verdict']!r}; expected {expected!r}",
            )

    if to_state == "FIX_REQUEST":
        if state.get("attempt_count", 0) >= MAX_ATTEMPT_COUNT:
            return (
                False,
                f"attempt_count {state['attempt_count']} >= {MAX_ATTEMPT_COUNT}; "
                f"must ESCALATE instead",
            )

    if to_state == "ESCALATE" and from_state == "FAIL":
        if state.get("attempt_count", 0) < MAX_ATTEMPT_COUNT:
            # ESCALATE from FAIL early is allowed, but warn via the note.
            pass

    if to_state == "HANDOFF_GEN" and from_state == "SPEC_DRAFT":
        # Programmatic side check: spec.md should exist in specs/<id>/.
        # We accept without it (this is human-approved), but emit a note.
        pass

    # Blocking questions check: if any open question blocks this target.
    for q in state.get("open_questions", []) or []:
        if q.get("blocks") == to_state and q.get("status") == "pending":
            return (
                False,
                f"blocked by open question {q.get('id')}: {q.get('title')}",
            )

    return True, "ok"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_init(args) -> int:
    if STATUS_FILE.exists() and not args.force:
        print(
            f".protocol/status.json already exists. Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1
    state = empty_state()
    state["metadata"]["started_at"] = now()
    append_history(state, from_state="-", to_state="IDLE", actor="init")
    save_state(state)
    print(f"Initialized .protocol/status.json (state=IDLE).")
    return 0


def cmd_status(args) -> int:
    state = load_state()
    if args.json:
        print(json.dumps(state, indent=2, default=str))
        return 0
    print(f"State:         {state.get('state')}")
    print(f"Active WP:     {state.get('active_wp') or '(none)'}")
    print(f"Attempt count: {state.get('attempt_count', 0)}")
    qs = state.get("open_questions", []) or []
    pending = [q for q in qs if q.get("status") == "pending"]
    print(f"Open questions: {len(pending)} pending / {len(qs)} total")
    if pending:
        for q in pending:
            blocks = q.get("blocks") or "—"
            print(f"  - {q['id']}: {q.get('title','?')}  [blocks: {blocks}]")
    print(f"Last transition: {state.get('last_transition') or '(none)'}")
    print(f"History entries: {len(state.get('history', []))}")
    return 0


def cmd_transition(args) -> int:
    state = load_state()
    target = args.target.upper()
    ok, reason = guard_ok(state, target)
    if not ok:
        print(f"Refused transition: {reason}", file=sys.stderr)
        return 2

    from_state = state["state"]

    # Side effects on attempt_count.
    if target == "FIX_REQUEST":
        state["attempt_count"] = state.get("attempt_count", 0) + 1
    if target == "DONE":
        state["attempt_count"] = 0
        state["active_wp"] = None

    state["state"] = target
    append_history(
        state,
        from_state=from_state,
        to_state=target,
        actor=args.actor or "human",
        note=args.note,
    )
    save_state(state)
    print(f"Transitioned: {from_state} -> {target}")
    if target == "FIX_REQUEST":
        print(f"  attempt_count now {state['attempt_count']}/{MAX_ATTEMPT_COUNT}")
    return 0


def cmd_set_wp(args) -> int:
    state = load_state()
    wp_dir = resolve_wp_dir(args.wp_id)
    if wp_dir is None:
        print(f"Error: Work Package not found: {args.wp_id}", file=sys.stderr)
        return 1
    files = wp_required_files(wp_dir)
    missing = [name for name, exists in files.items() if not exists]
    if missing and not args.force:
        print(
            f"Error: WP {wp_dir.name} is missing required files:\n  "
            + "\n  ".join(missing)
            + "\nUse --force to set anyway.",
            file=sys.stderr,
        )
        return 1
    prev = state.get("active_wp")
    state["active_wp"] = wp_dir.name
    state["attempt_count"] = 0
    append_history(
        state,
        from_state=state["state"],
        to_state=state["state"],
        actor="set-wp",
        artifact=wp_dir.name,
        note=f"active_wp: {prev!r} -> {wp_dir.name!r}",
    )
    save_state(state)
    print(f"Active WP set: {wp_dir.name}")
    return 0


def cmd_clear_wp(args) -> int:
    state = load_state()
    prev = state.get("active_wp")
    state["active_wp"] = None
    state["attempt_count"] = 0
    append_history(
        state,
        from_state=state["state"],
        to_state=state["state"],
        actor="clear-wp",
        note=f"active_wp: {prev!r} -> None",
    )
    save_state(state)
    print(f"Active WP cleared (was {prev!r}).")
    return 0


def append_to_index_md(question: dict) -> bool:
    """Mirror a new question into .protocol/questions/INDEX.md.

    Inserts the entry just before the "## Current open questions" body line
    "(none ..." marker, or appends at the end of the file. Idempotent on the
    Q-ID: if already present, no change.
    """
    if not QUESTIONS_INDEX.exists():
        return False
    text = QUESTIONS_INDEX.read_text(encoding="utf-8")
    if f"## {question['id']} —" in text:
        return False  # already there
    block = (
        f"\n## {question['id']} — {question.get('title', '')}\n\n"
        f"**Status**: 🟡 pending\n"
        f"**Raised by**: {question.get('raised_by', 'conductor')}\n"
        f"**Work Package**: {question.get('wp') or 'none'}\n"
        f"**Raised at**: {question.get('raised_at', '')}\n\n"
        f"**Evidence**:\n- (auto-generated from tcad_conduct.py add-question)\n\n"
        f"**Question**:\n{question.get('title', '')}\n\n"
        f"**Blocks**: {question.get('blocks') or 'nothing'}\n\n"
        f"**Answer**:\n(pending)\n"
    )
    # Replace "(none ...)" placeholder, else append.
    if "(none — Phase 1 just initialized)" in text:
        text = text.replace("(none — Phase 1 just initialized)", block.strip())
    elif "## Current open questions\n\n(none" in text:
        text = re.sub(
            r"(## Current open questions\s*\n\s*\n)\(none[^\n]*\n",
            r"\1" + block.strip() + "\n",
            text,
            count=1,
        )
    else:
        text = text.rstrip() + "\n" + block + "\n"
    QUESTIONS_INDEX.write_text(text, encoding="utf-8")
    return True


def cmd_add_question(args) -> int:
    state = load_state()
    qs = state.setdefault("open_questions", [])
    new_id = args.id or f"Q-{len(qs) + 1:03d}"
    if any(q.get("id") == new_id for q in qs):
        print(f"Error: question id already exists: {new_id}", file=sys.stderr)
        return 1
    q = {
        "id": new_id,
        "title": args.title,
        "blocks": args.blocks,
        "wp": state.get("active_wp"),
        "raised_at": now(),
        "raised_by": args.actor or "conductor",
        "status": "pending",
    }
    qs.append(q)
    append_history(
        state,
        from_state=state["state"],
        to_state=state["state"],
        actor="add-question",
        artifact=new_id,
        note=args.title,
    )
    save_state(state)
    mirrored = append_to_index_md(q)
    print(f"Added question {new_id} (blocks: {args.blocks or 'none'}).")
    if mirrored:
        print(f"  Mirrored to .protocol/questions/INDEX.md")
    else:
        print(f"  WARN: could not mirror to INDEX.md (file missing or already has it)")
    return 0


def mark_resolved_in_index_md(qid: str, resolution: str) -> bool:
    """Mark a question as resolved in INDEX.md by flipping its Status emoji."""
    if not QUESTIONS_INDEX.exists():
        return False
    text = QUESTIONS_INDEX.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(##\s*{re.escape(qid)}\s*—[^\n]*\n+\*\*Status\*\*:\s*)🟡 pending",
    )
    if not pattern.search(text):
        return False
    text = pattern.sub(r"\1✅ resolved", text, count=1)
    # Also try to fill the **Answer:** field if it is "(pending)".
    text = re.sub(
        r"(##\s*" + re.escape(qid) + r"\s*—.*?\*\*Answer\*\*:\s*\n)\(pending\)",
        r"\1" + (resolution or "(resolved)"),
        text,
        count=1,
        flags=re.DOTALL,
    )
    QUESTIONS_INDEX.write_text(text, encoding="utf-8")
    return True


def cmd_resolve_question(args) -> int:
    state = load_state()
    qs = state.get("open_questions", []) or []
    target = None
    for q in qs:
        if q.get("id") == args.id:
            target = q
            break
    if target is None:
        print(f"Error: question not found: {args.id}", file=sys.stderr)
        return 1
    target["status"] = "resolved"
    target["resolved_at"] = now()
    target["resolution"] = args.resolution or ""
    append_history(
        state,
        from_state=state["state"],
        to_state=state["state"],
        actor="resolve-question",
        artifact=args.id,
        note=args.resolution,
    )
    save_state(state)
    mirrored = mark_resolved_in_index_md(args.id, args.resolution or "")
    print(f"Resolved {args.id}.")
    if mirrored:
        print(f"  Updated .protocol/questions/INDEX.md")
    return 0


def cmd_snapshot(args) -> int:
    state = load_state()
    append_history(
        state,
        from_state=state["state"],
        to_state=state["state"],
        actor="snapshot",
        note=args.note or "manual snapshot",
    )
    save_state(state)
    print(f"Snapshot recorded at {state['last_transition']}.")
    return 0


def cmd_guards(args) -> int:
    state = load_state()
    active = state.get("active_wp")
    wp_dir = resolve_wp_dir(active) if active else None
    print(f"State:     {state.get('state')}")
    print(f"Active WP: {active or '(none)'}")
    if wp_dir is None:
        print("No active WP to inspect.")
        return 0
    files = wp_required_files(wp_dir)
    print("\nRequired template files:")
    for name, present in files.items():
        flag = "✓" if present else "✗"
        print(f"  {flag} {name}")
    ev = wp_evidence(wp_dir)
    print("\nEvidence:")
    for k, v in ev.items():
        print(f"  {k}: {v}")
    print("\nLegal transitions from current state:")
    from_state = state.get("state", "IDLE")
    for f, t, g in TRANSITIONS:
        if f == from_state:
            ok, reason = guard_ok(state, t)
            marker = "→" if ok else "×"
            print(f"  {marker} {t:<18}  guard: {g:<32}  {('' if ok else reason)}")
    return 0


def cmd_reset(args) -> int:
    if not args.force:
        print("Refused: pass --force to reset state to IDLE.", file=sys.stderr)
        return 1
    state = empty_state()
    state["metadata"]["started_at"] = now()
    append_history(state, from_state="-", to_state="IDLE", actor="reset")
    save_state(state)
    print("State reset to IDLE.")
    return 0


def cmd_states(args) -> int:
    """Helper: list states and legal transitions."""
    print("All states:")
    for s in ALL_STATES:
        print(f"  {s}")
    print("\nLegal transitions:")
    for f, t, g in TRANSITIONS:
        print(f"  {f:<18} -> {t:<18}  ({g})")
    return 0


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tcad_conduct", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="Initialize .protocol/status.json")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("status", help="Print current state")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("transition", help="Move to a new FSM state")
    s.add_argument("target")
    s.add_argument("--actor", default=None)
    s.add_argument("--note", default=None)
    s.set_defaults(func=cmd_transition)

    s = sub.add_parser("set-wp", help="Set the active Work Package")
    s.add_argument("wp_id")
    s.add_argument("--force", action="store_true",
                   help="Set even if required template files are missing.")
    s.set_defaults(func=cmd_set_wp)

    s = sub.add_parser("clear-wp", help="Deactivate the active Work Package")
    s.set_defaults(func=cmd_clear_wp)

    s = sub.add_parser("add-question", help="Register a blocking question")
    s.add_argument("title")
    s.add_argument("--id", default=None)
    s.add_argument("--blocks", default=None,
                   help="FSM state that this question blocks (e.g. REVIEWING)")
    s.add_argument("--actor", default=None)
    s.set_defaults(func=cmd_add_question)

    s = sub.add_parser("resolve-question", help="Mark a question as resolved")
    s.add_argument("id")
    s.add_argument("--resolution", default=None)
    s.set_defaults(func=cmd_resolve_question)

    s = sub.add_parser("snapshot", help="Append a snapshot to history")
    s.add_argument("--note", default=None)
    s.set_defaults(func=cmd_snapshot)

    s = sub.add_parser("guards", help="Inspect current guards and legal moves")
    s.set_defaults(func=cmd_guards)

    s = sub.add_parser("reset", help="Reset state to IDLE (dangerous)")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_reset)

    s = sub.add_parser("states", help="List FSM states and transitions")
    s.set_defaults(func=cmd_states)

    return p


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
