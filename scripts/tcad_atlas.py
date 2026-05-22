#!/usr/bin/env python3
"""
tcad_atlas.py — TCAD-H Cross-WP Atlas.

Phase 3.3 deliverable. Mentor scope:
    "Compose existing graphs. No LLM. No semantic enrich. Show how the project
     evolves across WPs by layer, hotspots, gates, and findings."

Deterministic. No LLM. No web. Reads:
    - .protocol/handoffs/WP-*/16_code_graph.json
    - .protocol/handoffs/WP-*/close_report.json
    - .protocol/handoffs/WP-*/review_report.json (optional)
    - .protocol/events.jsonl

Writes:
    - .protocol/atlas/atlas.json
    - .protocol/atlas/heatmap.md
    - .protocol/atlas/timeline.md
    - .protocol/atlas/layer_summary.md
    - .protocol/atlas/atlas.mermaid

Commands:
    build [--force]   Re-compose atlas from all WP graphs.
    show              Print atlas.json (or paths to artifacts).

Exit codes:
    0  success
    1  bad args
    2  no graphs to compose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT_PATH.parent))
from _tcad_root import resolve_tcad_root  # noqa: E402

ROOT = resolve_tcad_root(os.environ.get("TCAD_ROOT"))
PROTOCOL_DIR = ROOT / ".protocol"
HANDOFFS_DIR = PROTOCOL_DIR / "handoffs"
ATLAS_DIR = PROTOCOL_DIR / "atlas"
EVENTS_FILE = PROTOCOL_DIR / "events.jsonl"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def list_wp_graphs() -> list[tuple[Path, dict]]:
    """Return [(wp_dir, graph_dict)] for every WP with 16_code_graph.json."""
    out: list[tuple[Path, dict]] = []
    if not HANDOFFS_DIR.exists():
        return out
    for child in sorted(HANDOFFS_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        g = child / "16_code_graph.json"
        if not g.is_file():
            continue
        try:
            data = json.loads(g.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append((child, data))
    return out


def load_events() -> list[dict]:
    if not EVENTS_FILE.exists():
        return []
    out: list[dict] = []
    for line in EVENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------
def compose_atlas(graphs: list[tuple[Path, dict]], events: list[dict]) -> dict:
    """Build the aggregated atlas from per-WP graphs + events."""
    layer_stats: dict[str, dict] = defaultdict(lambda: {
        "wps_touched": set(),
        "files_changed": 0,
        "files_total": set(),
        "additions": 0,
        "deletions": 0,
        "critical_findings": 0,
    })
    file_touches: Counter = Counter()
    file_last_wp: dict[str, str] = {}
    file_wps: dict[str, list[str]] = defaultdict(list)
    wp_summaries: list[dict] = []
    findings_by_wp: dict[str, list[dict]] = {}

    for wp_dir, graph in graphs:
        wp_id = graph.get("wp") or wp_dir.name
        nodes = graph.get("nodes", []) or []
        summary = graph.get("summary", {}) or {}
        gates = graph.get("gates", {}) or {}
        findings = graph.get("review_findings", []) or []

        # Per-WP summary entry
        wp_summaries.append({
            "wp": wp_id,
            "role": graph.get("role"),
            "branch": graph.get("branch"),
            "generated_at": graph.get("generated_at"),
            "summary": summary,
            "review_pass": gates.get("review_pass"),
            "critical_count": gates.get("review_critical_count", 0),
            "smoke_total": gates.get("smoke_total", 0),
            "smoke_passed": gates.get("smoke_passed", 0),
            "layers_touched": list((graph.get("layer_touches") or {}).keys()),
        })
        if findings:
            findings_by_wp[wp_id] = findings

        # Layer aggregations
        layers_touched_in_wp: set[str] = set()
        for n in nodes:
            layer = n.get("layer") or "unlayered"
            layers_touched_in_wp.add(layer)
            lstats = layer_stats[layer]
            lstats["wps_touched"].add(wp_id)
            lstats["files_changed"] += 1
            lstats["files_total"].add(n["id"])
            lstats["additions"] += n.get("additions", 0)
            lstats["deletions"] += n.get("deletions", 0)
            # File hotspots
            file_touches[n["id"]] += 1
            file_last_wp[n["id"]] = wp_id
            if wp_id not in file_wps[n["id"]]:
                file_wps[n["id"]].append(wp_id)

        # Critical findings → distribute by layer if location file is known
        for f in findings:
            if f.get("severity") != "critical":
                continue
            locs = f.get("locations", []) or []
            target_layer = "unlayered"
            for loc in locs:
                fp = loc.get("file") or f.get("file") or ""
                # Try to match to a layer touched in this WP
                for n in nodes:
                    if n["id"] in fp:
                        target_layer = n.get("layer") or "unlayered"
                        break
                if target_layer != "unlayered":
                    break
            layer_stats[target_layer]["critical_findings"] += 1

    # Convert sets to counts for serialization
    layer_summary = []
    for layer, s in sorted(
        layer_stats.items(),
        key=lambda kv: -len(kv[1]["wps_touched"]),
    ):
        layer_summary.append({
            "layer": layer,
            "wps_touched_count": len(s["wps_touched"]),
            "wps_touched": sorted(s["wps_touched"]),
            "files_changed_total": s["files_changed"],
            "distinct_files": len(s["files_total"]),
            "additions": s["additions"],
            "deletions": s["deletions"],
            "critical_findings": s["critical_findings"],
        })

    # Hotspots: files touched more than once
    hotspots = []
    for path, count in file_touches.most_common():
        hotspots.append({
            "file": path,
            "times_changed": count,
            "last_wp": file_last_wp.get(path),
            "wps": file_wps.get(path, []),
        })

    # Timeline: extract worktree_created / wp_evidence_logged / review_gate_*
    timeline_events = []
    for ev in events:
        kind = ev.get("event", "")
        if kind in (
            "worktree_created", "worktree_merged", "worktree_destroyed",
            "wp_evidence_logged", "review_gate_failed", "review_gate_passed",
            "merge_conflict_detected",
        ):
            timeline_events.append({
                "ts": ev.get("ts"),
                "event": kind,
                "wp": ev.get("wp") or (ev.get("slug") or "").rsplit("-", 1)[0] if ev.get("slug") else None,
                "role": ev.get("role"),
                "extra": {
                    k: v for k, v in ev.items()
                    if k not in ("ts", "event", "wp", "role", "actor")
                },
            })
    timeline_events.sort(key=lambda e: e.get("ts") or "")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wps_total": len(graphs),
        "wp_summaries": wp_summaries,
        "layers": layer_summary,
        "hotspots": hotspots,
        "findings_by_wp": findings_by_wp,
        "timeline": timeline_events,
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def render_heatmap(atlas: dict) -> str:
    lines = ["# Layer heatmap", ""]
    layers = atlas.get("layers") or []
    if not layers:
        lines.append("(no layered data yet)")
        return "\n".join(lines) + "\n"
    lines.append("| Layer | WPs | Files | Additions | Deletions | Critical |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for L in layers:
        lines.append(
            f"| **{L['layer']}** | {L['wps_touched_count']} | "
            f"{L['files_changed_total']} | "
            f"+{L['additions']} | -{L['deletions']} | "
            f"{L['critical_findings']} |"
        )
    # Hotspots subsection
    hotspots = atlas.get("hotspots") or []
    # Filter to files touched 2+ times
    real = [h for h in hotspots if h["times_changed"] >= 2]
    lines.append("")
    lines.append("## Hotspots (files touched 2+ times)")
    lines.append("")
    if not real:
        lines.append("(none yet — every file touched once)")
    else:
        lines.append("| File | Times | Last WP | All WPs |")
        lines.append("|---|---:|---|---|")
        for h in real[:25]:
            wps = ", ".join(h["wps"][:4]) + ("…" if len(h["wps"]) > 4 else "")
            lines.append(f"| `{h['file']}` | {h['times_changed']} | {h['last_wp']} | {wps} |")
    return "\n".join(lines) + "\n"


def render_timeline(atlas: dict) -> str:
    lines = ["# Timeline", "", "Chronological cross-WP event log.", ""]
    for ev in atlas.get("timeline", []):
        ts = (ev.get("ts") or "")[:19]
        kind = ev.get("event", "")
        wp = ev.get("wp") or "—"
        lines.append(f"- `{ts}` **{kind}** wp=`{wp}`")
    if not atlas.get("timeline"):
        lines.append("(no timeline events recorded yet)")
    return "\n".join(lines) + "\n"


def render_layer_summary(atlas: dict) -> str:
    lines = ["# Per-layer summary", ""]
    for L in atlas.get("layers", []):
        lines.append(f"## `{L['layer']}` — {L['wps_touched_count']} WPs, "
                     f"{L['distinct_files']} distinct files")
        if L["wps_touched"]:
            lines.append("")
            lines.append(f"  WPs: {', '.join(L['wps_touched'])}")
            lines.append("")
        lines.append(f"  - files changed total: **{L['files_changed_total']}**")
        lines.append(f"  - additions: +{L['additions']}")
        lines.append(f"  - deletions: -{L['deletions']}")
        if L["critical_findings"]:
            lines.append(f"  - **critical findings**: {L['critical_findings']}")
        lines.append("")
    return "\n".join(lines)


def render_mermaid(atlas: dict) -> str:
    layers = atlas.get("layers") or []
    lines = ["```mermaid", "flowchart LR"]
    lines.append("  ATLAS[Atlas]")
    # Each layer as a node sized by WP count + critical chip
    for i, L in enumerate(layers):
        nid = f"L{i}"
        label = (
            f"{L['layer']}\\n"
            f"{L['wps_touched_count']} WPs · "
            f"{L['files_changed_total']} files"
        )
        if L["critical_findings"]:
            label += f"\\n⚠ {L['critical_findings']} critical"
        lines.append(f'  {nid}["{label}"]')
        lines.append(f"  ATLAS --> {nid}")
        style = "fill:#0e3b58,stroke:#38bdf8"
        if L["critical_findings"]:
            style = "fill:#471616,stroke:#ef4444"
        lines.append(f"  style {nid} {style},color:#fff")
    lines.append("```")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_build(args) -> int:
    graphs = list_wp_graphs()
    if not graphs:
        print("No WP graphs found. Run `tcad_graph.py static <wp>` first.",
              file=sys.stderr)
        return 2
    events = load_events()
    atlas = compose_atlas(graphs, events)

    ATLAS_DIR.mkdir(parents=True, exist_ok=True)
    (ATLAS_DIR / "atlas.json").write_text(
        json.dumps(atlas, indent=2, default=str), encoding="utf-8"
    )
    (ATLAS_DIR / "heatmap.md").write_text(render_heatmap(atlas), encoding="utf-8")
    (ATLAS_DIR / "timeline.md").write_text(render_timeline(atlas), encoding="utf-8")
    (ATLAS_DIR / "layer_summary.md").write_text(render_layer_summary(atlas), encoding="utf-8")
    (ATLAS_DIR / "atlas.mermaid").write_text(render_mermaid(atlas), encoding="utf-8")

    print(f"Atlas built from {len(graphs)} WP graph(s).")
    print(f"  WPs:    {atlas['wps_total']}")
    print(f"  layers: {len(atlas['layers'])}")
    print(f"  hotspots (≥2 touches): {sum(1 for h in atlas['hotspots'] if h['times_changed'] >= 2)}")
    print(f"  timeline events: {len(atlas['timeline'])}")
    print(f"  outputs:")
    for f in ("atlas.json", "heatmap.md", "timeline.md", "layer_summary.md", "atlas.mermaid"):
        print(f"    .protocol/atlas/{f}")
    return 0


def cmd_show(args) -> int:
    path = ATLAS_DIR / "atlas.json"
    if not path.is_file():
        print("No atlas yet. Run `tcad_atlas.py build`.", file=sys.stderr)
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    print(f"Atlas — generated {data['generated_at']}")
    print(f"  WPs:     {data['wps_total']}")
    print(f"  layers:  {len(data['layers'])}")
    for L in data["layers"][:10]:
        crit = f" · crit={L['critical_findings']}" if L["critical_findings"] else ""
        print(f"    {L['layer']:<12} WPs={L['wps_touched_count']:<2} "
              f"files={L['files_changed_total']:<3}{crit}")
    hot = [h for h in data["hotspots"] if h["times_changed"] >= 2]
    if hot:
        print(f"  hotspots:")
        for h in hot[:5]:
            print(f"    {h['file']:<40} touched {h['times_changed']}x  last={h['last_wp']}")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tcad_atlas", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("build", help="Compose atlas from all WP graphs.")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("show", help="Print atlas summary.")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
