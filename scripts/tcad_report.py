#!/usr/bin/env python3
"""
tcad_report.py — TCAD-H Alpha State Report.

Phase 3.5 deliverable (pre-field-trial). Mentor scope:
    "A single command that tells: WPs, open questions, hotspots, latest
     failed gate, next recommended action."

NO LLM. Reads existing artifacts on disk:
    - .protocol/status.json
    - .protocol/project_profile.json
    - .protocol/handoffs/*/close_report.json
    - .protocol/handoffs/*/.tcad_wp.json
    - .protocol/atlas/atlas.json
    - .protocol/questions/INDEX.md
    - .protocol/events.jsonl (last N)

Commands:
    alpha [--json]   Prints a digest of current repo state.

Exit codes:
    0  ok
    1  bad args
    2  .protocol/ missing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT_PATH.parent))
from _tcad_root import resolve_tcad_root  # noqa: E402

ROOT = resolve_tcad_root(os.environ.get("FOREMAN_ROOT") or os.environ.get("TCAD_ROOT"))
PROTOCOL = ROOT / ".protocol"


def load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def collect_wps() -> list[dict]:
    out: list[dict] = []
    handoffs = PROTOCOL / "handoffs"
    if not handoffs.is_dir():
        return out
    for child in sorted(handoffs.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        close = load_json(child / "close_report.json")
        meta = load_json(child / ".tcad_wp.json") or {}
        review = load_json(child / "review_report.json")
        out.append({
            "wp": child.name,
            "profile": meta.get("profile"),
            "role": meta.get("role"),
            "has_summary": (child / "11_worker_summary.md").is_file(),
            "has_close_report": close is not None,
            "no_changes": (close or {}).get("no_changes"),
            "smoke_skipped": (close or {}).get("smoke_skipped"),
            "review_pass": (review or {}).get("pass"),
            "review_critical_count": (review or {}).get("critical_count", 0),
            "closed_at": (close or {}).get("closed_at"),
            "validation_errors": (close or {}).get("validation_errors", []),
        })
    return out


def count_open_questions() -> int:
    idx = PROTOCOL / "questions" / "INDEX.md"
    if not idx.is_file():
        return 0
    text = idx.read_text(encoding="utf-8")
    # Pending questions appear as "## Q-... — ..." followed by "Status: 🟡 pending".
    sections = re.findall(r"^## Q-[\w-]+", text, flags=re.MULTILINE)
    pending = 0
    # Heuristic: count `🟡 pending` occurrences.
    pending = text.count("🟡 pending") + text.count("pending")
    # Avoid overcount: minimum of sections and pending matches.
    return min(len(sections), max(1 if "🟡" in text else 0, text.count("🟡 pending")))


def parse_open_questions_struct() -> list[dict]:
    """Return structured open questions from INDEX.md (best-effort regex)."""
    idx = PROTOCOL / "questions" / "INDEX.md"
    if not idx.is_file():
        return []
    text = idx.read_text(encoding="utf-8")
    out: list[dict] = []
    for m in re.finditer(
        r"##\s+(?P<id>Q-[\w-]+)\s*—\s*(?P<title>[^\n]+)\n+(?P<body>[\s\S]+?)(?=^##\s|\Z)",
        text, flags=re.MULTILINE,
    ):
        body = m.group("body")
        status_match = re.search(r"\*\*Status\*\*:\s*([^\n]+)", body)
        blocks_match = re.search(r"\*\*Blocks\*\*:\s*([^\n]+)", body)
        status = (status_match.group(1).strip() if status_match else "").lower()
        if "pending" not in status and "🟡" not in status:
            continue
        out.append({
            "id": m.group("id"),
            "title": m.group("title").strip(),
            "blocks": blocks_match.group(1).strip() if blocks_match else None,
        })
    return out


def tail_events(n: int) -> list[dict]:
    p = PROTOCOL / "events.jsonl"
    if not p.is_file():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def recommend_next_action(state: dict) -> str:
    """Suggest the most useful next command based on state."""
    if not PROTOCOL.exists():
        return "Run: tcad init"
    if not (PROTOCOL / "project_profile.json").is_file():
        return "Run: tcad profile detect"
    pending = state.get("open_questions") or []
    if pending:
        ids = ", ".join(q["id"] for q in pending[:3])
        return f"Resolve blocking question(s): {ids}  (see .protocol/questions/INDEX.md)"
    # WP-level checks
    wps = state.get("wps") or []
    for wp in wps:
        if wp.get("review_pass") is False:
            return f"Fix critical review findings in {wp['wp']}  (`.protocol/handoffs/{wp['wp']}/review_report.json`)"
        if wp.get("has_summary") and not wp.get("has_close_report"):
            return f"Close evidence: tcad close {wp['wp']}"
    if not (PROTOCOL / "atlas" / "atlas.json").is_file() and wps:
        return "Run: tcad atlas build"
    if not wps:
        return "Run: tcad wp create --lean --name <slug> --goal '...' --role <role>"
    return "Idle. All WPs closed. Run: tcad studio  (or create a new WP)"


def build_state() -> dict:
    if not PROTOCOL.exists():
        return {"protocol_present": False}
    status = load_json(PROTOCOL / "status.json") or {}
    profile = load_json(PROTOCOL / "project_profile.json") or {}
    atlas = load_json(PROTOCOL / "atlas" / "atlas.json") or {}
    wps = collect_wps()
    open_questions = parse_open_questions_struct()
    latest_events = tail_events(8)

    # Latest gate failure scan
    latest_fail = None
    for ev in reversed(latest_events):
        if ev.get("event") in ("review_gate_failed", "boundary_violation", "merge_conflict_detected"):
            latest_fail = {
                "ts": ev.get("ts"),
                "event": ev.get("event"),
                "wp": ev.get("wp") or ev.get("slug"),
                "extra": {k: v for k, v in ev.items() if k not in ("ts", "event", "wp")},
            }
            break

    state = {
        "protocol_present": True,
        "root": str(ROOT),
        "conductor_state": status.get("state"),
        "active_wp": status.get("active_wp"),
        "project_type": (profile.get("project") or {}).get("type"),
        "stack": profile.get("stack"),
        "wps": wps,
        "open_questions": open_questions,
        "latest_fail": latest_fail,
        "atlas_summary": {
            "wps_total": atlas.get("wps_total", 0),
            "layers_count": len(atlas.get("layers", [])),
            "hotspots_count": sum(1 for h in atlas.get("hotspots", []) if h["times_changed"] >= 2),
            "top_hotspots": [
                {"file": h["file"], "times": h["times_changed"], "last_wp": h["last_wp"]}
                for h in atlas.get("hotspots", []) if h["times_changed"] >= 2
            ][:5],
            "layer_totals": [
                {"layer": L["layer"], "wps": L["wps_touched_count"],
                 "files": L["files_changed_total"], "critical": L["critical_findings"]}
                for L in atlas.get("layers", [])[:6]
            ],
        },
        "recent_events": [
            {"ts": e.get("ts"), "event": e.get("event"), "wp": e.get("wp") or e.get("slug")}
            for e in latest_events[-5:]
        ],
    }
    state["next_action"] = recommend_next_action(state)
    return state


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def render(state: dict) -> str:
    if not state.get("protocol_present"):
        return "TCAD-H not initialized here.\nRun: tcad init"

    lines = []
    lines.append(f"TCAD-H alpha report — {state['root']}")
    lines.append("")
    lines.append(f"  Conductor:   {state.get('conductor_state') or '—'}")
    lines.append(f"  Active WP:   {state.get('active_wp') or '(none)'}")
    pt = state.get("project_type")
    stack = state.get("stack") or {}
    if pt:
        lines.append(f"  Project:     {pt}  (backend={stack.get('backend')}, frontend={stack.get('frontend')})")
    else:
        lines.append(f"  Project:     (run `tcad profile detect`)")

    wps = state.get("wps") or []
    closed = [w for w in wps if w["has_close_report"]]
    review_fail = [w for w in wps if w.get("review_pass") is False]
    lines.append("")
    lines.append(f"Work Packages: {len(wps)} total, {len(closed)} closed, "
                 f"{len(review_fail)} with review FAIL")
    for wp in wps[-5:]:
        flag = ""
        if wp.get("review_pass") is False:
            flag = "  [REVIEW FAIL]"
        elif wp.get("review_pass") is True:
            flag = "  [reviewed]"
        elif wp.get("has_close_report"):
            flag = "  [closed]"
        elif wp.get("has_summary"):
            flag = "  [summary written]"
        else:
            flag = "  [draft]"
        lines.append(f"  - {wp['wp']:<40}{flag}")

    oq = state.get("open_questions") or []
    if oq:
        lines.append("")
        lines.append(f"Open questions: {len(oq)} pending")
        for q in oq[:5]:
            blocks = f"  [blocks: {q['blocks']}]" if q.get("blocks") else ""
            lines.append(f"  - {q['id']}: {q['title']}{blocks}")

    lf = state.get("latest_fail")
    if lf:
        lines.append("")
        lines.append(f"Latest failure: {lf['event']} @ {lf['ts'][:19]} wp={lf.get('wp') or '—'}")

    atlas = state.get("atlas_summary") or {}
    if atlas.get("wps_total"):
        lines.append("")
        lines.append(f"Atlas: {atlas['wps_total']} WPs, {atlas['layers_count']} layers, "
                     f"{atlas['hotspots_count']} hotspot(s)")
        for L in atlas.get("layer_totals", []):
            crit = f"  crit={L['critical']}" if L["critical"] else ""
            lines.append(f"  {L['layer']:<14} WPs={L['wps']:<3} files={L['files']:<4}{crit}")
        for h in atlas.get("top_hotspots", []):
            lines.append(f"  hotspot  {h['file']:<40} {h['times']}x  last={h['last_wp']}")

    rec = state.get("recent_events") or []
    if rec:
        lines.append("")
        lines.append("Recent events:")
        for e in rec:
            lines.append(f"  {e['ts'][:19] if e.get('ts') else '—':<19}  {e.get('event', '?'):<28}  wp={e.get('wp') or '—'}")

    lines.append("")
    lines.append(f"→ Next: {state['next_action']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_alpha(args) -> int:
    state = build_state()
    if args.json:
        print(json.dumps(state, indent=2, default=str))
    else:
        print(render(state))
    return 0 if state.get("protocol_present") else 2


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tcad report", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("alpha", help="Print alpha state digest.")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_alpha)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
