#!/usr/bin/env python3
"""
tcad_graph.py — TCAD-H Static Graph Lite.

Phase 2.5a deliverable. Mentor scope:
    "El grafo solo puede mostrar evidencia que ya existe en el filesystem."

Inputs (no inference, no LLM):
    - .protocol/handoffs/<wp>/15_diff.patch     — changed file list
    - .protocol/handoffs/<wp>/close_report.json — gate results
    - .protocol/handoffs/<wp>/review_report.json — reviewer findings (optional)
    - .protocol/events.jsonl                    — recent events for this WP

Outputs:
    - .protocol/handoffs/<wp>/16_code_graph.json
    - .protocol/handoffs/<wp>/19_mermaid.md

Answers exactly 5 questions:
    1. Which files did the WP change?
    2. Which files did the WP create?
    3. Which files did the WP delete?
    4. Which gates passed and which failed?
    5. What should the reviewer look at?

NOT in scope (mentor explicit prohibitions):
    - Inventing capabilities
    - LLM-based summarization
    - Naming components beyond what is observable
    - Drawing edges that were not observed in artifacts

Commands:
    static <slug>     Generate 16_code_graph.json + 19_mermaid.md
    show <slug>       Print mermaid graph (already generated)

Exit codes:
    0  ok
    1  bad args
    2  WP not found / missing inputs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT_PATH.parent))
from _tcad_root import resolve_tcad_root  # noqa: E402

ROOT = resolve_tcad_root(os.environ.get("FOREMAN_ROOT") or os.environ.get("TCAD_ROOT"))
PROTOCOL_DIR = ROOT / ".protocol"
HANDOFFS_DIR = PROTOCOL_DIR / "handoffs"
EVENTS_FILE = PROTOCOL_DIR / "events.jsonl"
PROFILE_FILE = PROTOCOL_DIR / "project_profile.json"


# ---------------------------------------------------------------------------
# Patch parsing (deterministic — no AST, just header lines)
# ---------------------------------------------------------------------------
DIFF_FILE_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)
NEW_FILE_RE = re.compile(r"^new file mode", re.MULTILINE)
DELETED_FILE_RE = re.compile(r"^deleted file mode", re.MULTILINE)


def parse_patch_files(patch_text: str) -> dict[str, dict]:
    """Return { file_path: {change_type, additions, deletions} } from a unified diff."""
    out: dict[str, dict] = {}
    # Split the patch into per-file sections (`diff --git a/... b/...`).
    sections = re.split(r"(?=^diff --git )", patch_text, flags=re.MULTILINE)
    for sec in sections:
        m = DIFF_FILE_RE.search(sec)
        if not m:
            continue
        path = m.group(2)
        if NEW_FILE_RE.search(sec):
            change_type = "created"
        elif DELETED_FILE_RE.search(sec):
            change_type = "deleted"
        else:
            change_type = "modified"
        # Count + and - lines (excluding +++ / --- headers).
        adds = 0
        dels = 0
        for line in sec.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                adds += 1
            elif line.startswith("-"):
                dels += 1
        out[path] = {
            "change_type": change_type,
            "additions": adds,
            "deletions": dels,
        }
    return out


# ---------------------------------------------------------------------------
# WP/report loaders
# ---------------------------------------------------------------------------
def resolve_wp_dir(slug_or_wp: str) -> Path | None:
    # slug looks like WP-NNN-name-role; WP id is WP-NNN-name.
    candidate = HANDOFFS_DIR / slug_or_wp
    if candidate.is_dir():
        return candidate
    # Try stripping role suffix.
    for role in ("-backend", "-frontend", "-tests", "-reading"):
        if slug_or_wp.endswith(role):
            stripped = slug_or_wp[: -len(role)]
            c2 = HANDOFFS_DIR / stripped
            if c2.is_dir():
                return c2
    if slug_or_wp.startswith("WP-") and slug_or_wp[3:6].isdigit():
        prefix = slug_or_wp[:6] + "-"
        for child in HANDOFFS_DIR.iterdir():
            if child.is_dir() and child.name.startswith(prefix):
                return child
    return None


def load_close_report(wp_dir: Path) -> dict | None:
    p = wp_dir / "close_report.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_review_report(wp_dir: Path) -> dict | None:
    p = wp_dir / "review_report.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def events_for_wp(wp_id: str, limit: int = 50) -> list[dict]:
    if not EVENTS_FILE.exists():
        return []
    out: list[dict] = []
    for line in EVENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("wp") == wp_id or ev.get("slug", "").startswith(wp_id):
            out.append(ev)
    return out[-limit:]


# ---------------------------------------------------------------------------
# Graph composition
# ---------------------------------------------------------------------------
def load_profile() -> dict | None:
    """Phase 3.1: load project_profile.json if present."""
    if not PROFILE_FILE.is_file():
        return None
    try:
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _walk_match(path_parts: list[str], pat_parts: list[str]) -> bool:
    """Pattern matching that handles `**` correctly across path segments."""
    import fnmatch
    if not pat_parts:
        return not path_parts
    head, rest = pat_parts[0], pat_parts[1:]
    if head == "**":
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


def classify_by_layer(path: str, profile: dict | None) -> str | None:
    """Phase 3.1: pick the first matching layer from profile.layers globs."""
    if not profile:
        return None
    layers = profile.get("layers", {}) or {}
    for layer_name, globs in layers.items():
        for g in globs:
            if _walk_match(path.split("/"), g.split("/")):
                return layer_name
    return None


def classify_file(path: str) -> str:
    """Return a category for color/grouping. Conservative — only by suffix/dir."""
    p = path.lower()
    if p.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")) \
            or "/tests/" in p or p.startswith("tests/"):
        return "test"
    if p.endswith(".md") or p.endswith(".txt") or p.startswith("docs/"):
        return "docs"
    if p.endswith((".yaml", ".yml", ".json", ".toml", ".cfg")):
        return "config"
    if p.endswith((".py",)):
        return "python"
    if p.endswith((".ts", ".tsx")):
        return "ts"
    if p.endswith((".js", ".jsx", ".mjs", ".cjs")):
        return "js"
    if p.endswith((".css", ".scss", ".sass")):
        return "css"
    if p.endswith((".html",)):
        return "html"
    return "other"


def compose_graph(
    *,
    wp_dir: Path,
    close: dict | None,
    review: dict | None,
    events: list[dict],
) -> dict:
    """Build the JSON graph from artifacts only — no inference."""
    wp_id = wp_dir.name

    # Load .tcad_wp.json metadata
    wp_meta_path = wp_dir / ".tcad_wp.json"
    wp_meta = {}
    if wp_meta_path.is_file():
        try:
            wp_meta = json.loads(wp_meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    # Parse 15_diff.patch
    patch_path = wp_dir / "15_diff.patch"
    files_by_change: dict[str, dict] = {}
    if patch_path.is_file():
        text = patch_path.read_text(encoding="utf-8")
        if text.strip().startswith("# NO_CHANGES"):
            files_by_change = {}
        else:
            files_by_change = parse_patch_files(text)

    # Phase 3.1: load profile (if present) for layer tagging
    profile = load_profile()

    # Build nodes (one per file)
    nodes = []
    for path, info in sorted(files_by_change.items()):
        node = {
            "id": path,
            "type": "file",
            "category": classify_file(path),
            "change_type": info["change_type"],
            "additions": info["additions"],
            "deletions": info["deletions"],
        }
        layer = classify_by_layer(path, profile)
        if layer:
            node["layer"] = layer
        nodes.append(node)

    # Build edges: test_target — heuristic only by name pairing.
    # If we see "tests/test_X.py" and a sibling "X.py" or "app/X.py", link them.
    edges = []
    test_nodes = [n for n in nodes if n["category"] == "test"]
    code_nodes = [n for n in nodes if n["category"] in ("python", "ts", "js", "tsx", "jsx")]
    for t in test_nodes:
        base = Path(t["id"]).name
        m = re.match(r"test_(.+?)\.py$", base)
        target = None
        if m:
            target_name = m.group(1) + ".py"
            for c in code_nodes:
                if Path(c["id"]).name == target_name:
                    target = c["id"]
                    break
        if target:
            edges.append({
                "from": t["id"],
                "to": target,
                "type": "test_target",
                "confidence": "heuristic",
            })

    # Gate annotations
    gates = {}
    if close:
        gates["close_present"] = True
        gates["no_changes"] = close.get("no_changes")
        gates["validation_errors"] = close.get("validation_errors", [])
        smoke_results = close.get("smoke_results", []) or []
        gates["smoke_total"] = len(smoke_results)
        gates["smoke_passed"] = sum(1 for r in smoke_results if r.get("ok"))
        gates["smoke_skipped"] = close.get("smoke_skipped", False)
        gates["review_pass"] = close.get("smoke_pass")  # actually smoke; will overwrite below
    else:
        gates["close_present"] = False

    review_findings = []
    if review:
        gates["review_present"] = True
        gates["review_pass"] = review.get("pass")
        gates["review_critical_count"] = review.get("critical_count", 0)
        review_findings = review.get("findings", [])
    else:
        gates["review_present"] = False

    # Reviewer focus: which files to look at first.
    # Heuristic: files cited in critical findings + files with high additions count.
    reviewer_focus = []
    cited_paths: set[str] = set()
    for f in review_findings:
        if f.get("severity") != "critical":
            continue
        for loc in f.get("locations", []) or []:
            fp = loc.get("file") or f.get("file")
            if fp:
                cited_paths.add(fp)
    for n in nodes:
        if n["id"] in cited_paths or any(n["id"].endswith(cp) for cp in cited_paths):
            reviewer_focus.append({
                "file": n["id"],
                "reason": "cited in critical review finding",
            })
    if not reviewer_focus:
        # Fallback: largest additions.
        top = sorted(nodes, key=lambda x: -x["additions"])[:3]
        for n in top:
            reviewer_focus.append({
                "file": n["id"],
                "reason": f"largest diff ({n['additions']} adds, {n['deletions']} dels)",
            })

    # Phase 3.1: project context for graph consumers
    project_ctx = None
    if profile:
        project_ctx = {
            "type": (profile.get("project") or {}).get("type"),
            "name": (profile.get("project") or {}).get("name"),
            "stack": profile.get("stack"),
            "layers_known": list((profile.get("layers") or {}).keys()),
        }
    # Tally layer touches
    layer_touches: dict[str, int] = {}
    for n in nodes:
        if n.get("layer"):
            layer_touches[n["layer"]] = layer_touches.get(n["layer"], 0) + 1

    graph = {
        "wp": wp_id,
        "wp_profile": wp_meta.get("profile"),
        "role": wp_meta.get("role"),
        "branch": (close or {}).get("branch"),
        "base": (close or {}).get("base"),
        "project": project_ctx,
        "layer_touches": layer_touches,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "files_total": len(nodes),
            "files_created": sum(1 for n in nodes if n["change_type"] == "created"),
            "files_modified": sum(1 for n in nodes if n["change_type"] == "modified"),
            "files_deleted": sum(1 for n in nodes if n["change_type"] == "deleted"),
            "additions": sum(n["additions"] for n in nodes),
            "deletions": sum(n["deletions"] for n in nodes),
        },
        "nodes": nodes,
        "edges": edges,
        "gates": gates,
        "review_findings": review_findings,
        "reviewer_focus": reviewer_focus,
        "events": [
            {"ts": e.get("ts"), "event": e.get("event"), "actor": e.get("actor")}
            for e in events[-10:]
        ],
    }
    return graph


# ---------------------------------------------------------------------------
# Mermaid renderer
# ---------------------------------------------------------------------------
CHANGE_STYLE = {
    "created":  "fill:#0f3a22,stroke:#22c55e",
    "modified": "fill:#0e3b58,stroke:#38bdf8",
    "deleted":  "fill:#471616,stroke:#ef4444",
}
CATEGORY_GROUPS = {
    "test":   "Tests",
    "docs":   "Docs",
    "config": "Config",
    "python": "Python",
    "ts":     "TypeScript",
    "tsx":    "TypeScript",
    "js":     "JavaScript",
    "jsx":    "JavaScript",
    "css":    "Styles",
    "html":   "HTML",
    "other":  "Other",
}


def _mermaid_id(s: str) -> str:
    return "N_" + re.sub(r"[^a-zA-Z0-9_]", "_", s)[:40]


def _mermaid_label(s: str) -> str:
    # Trim & escape — mermaid doesn't like quotes inside labels.
    return s.replace('"', "'")


def render_mermaid(graph: dict) -> str:
    lines: list[str] = []
    lines.append("```mermaid")
    lines.append("flowchart LR")
    # Title node
    title = f"WP[{graph['wp']}]"
    lines.append(f"  {title}")
    # Phase 3.1: group nodes by LAYER when profile applied; else fall back to category.
    use_layers = any(n.get("layer") for n in graph["nodes"])
    groups: dict[str, list[dict]] = {}
    for n in graph["nodes"]:
        if use_layers:
            gname = (n.get("layer") or "other").title()
        else:
            gname = CATEGORY_GROUPS.get(n["category"], "Other")
        groups.setdefault(gname, []).append(n)
    for gname, items in groups.items():
        # subgraph keyword expects an ID; use sanitized
        gid = "G_" + re.sub(r"[^a-zA-Z0-9_]", "_", gname)
        lines.append(f"  subgraph {gid}[{gname}]")
        for n in items:
            nid = _mermaid_id(n["id"])
            label = (
                f"{_mermaid_label(n['id'])}\\n"
                f"+{n['additions']}/-{n['deletions']}"
            )
            lines.append(f"    {nid}[\"{label}\"]")
        lines.append("  end")
    # Edges
    for e in graph["edges"]:
        f = _mermaid_id(e["from"])
        t = _mermaid_id(e["to"])
        lines.append(f"  {f} -- {e['type']} --> {t}")
    # Style nodes by change_type
    for n in graph["nodes"]:
        style = CHANGE_STYLE.get(n["change_type"], "")
        if style:
            lines.append(f"  style {_mermaid_id(n['id'])} {style},color:#fff")
    # Gate annotation block (text, not graph)
    g = graph["gates"]
    lines.append("```")
    lines.append("")
    lines.append("## Gates")
    lines.append("")
    if g.get("close_present"):
        sm_p, sm_t = g.get("smoke_passed", 0), g.get("smoke_total", 0)
        sm_label = "SKIPPED" if g.get("smoke_skipped") else f"{sm_p}/{sm_t}"
        lines.append(f"- close report: PRESENT")
        lines.append(f"- smoke: {sm_label}")
    else:
        lines.append("- close report: MISSING")
    if g.get("review_present"):
        if g.get("review_pass"):
            lines.append(f"- review: PASS")
        else:
            crit = g.get("review_critical_count", 0)
            lines.append(f"- review: **FAIL** ({crit} critical findings)")
    else:
        lines.append("- review: not run")
    val_errs = g.get("validation_errors") or []
    if val_errs:
        lines.append(f"- validation errors: {len(val_errs)}")

    # Phase 3.1: project + layer summary
    proj = graph.get("project") or {}
    if proj.get("type"):
        lines.append("")
        lines.append(f"## Project context")
        lines.append("")
        lines.append(f"- type: `{proj.get('type')}`")
        if proj.get("name"):
            lines.append(f"- name: `{proj['name']}`")
        stack = proj.get("stack") or {}
        backend = stack.get("backend")
        frontend = stack.get("frontend")
        if backend and backend != "none":
            lines.append(f"- backend: `{backend}`")
        if frontend and frontend != "none":
            lines.append(f"- frontend: `{frontend}`")
    layer_touches = graph.get("layer_touches") or {}
    if layer_touches:
        lines.append("")
        lines.append(f"## Layer touches")
        lines.append("")
        for layer, n in layer_touches.items():
            lines.append(f"- **{layer}**: {n} file(s)")

    # Reviewer focus
    if graph["reviewer_focus"]:
        lines.append("")
        lines.append("## Reviewer focus")
        lines.append("")
        for r in graph["reviewer_focus"]:
            lines.append(f"- `{r['file']}` — {r['reason']}")

    # Critical findings inlined
    crit = [f for f in graph["review_findings"] if f.get("severity") == "critical"]
    if crit:
        lines.append("")
        lines.append("## Critical findings")
        lines.append("")
        for f in crit:
            lines.append(f"- **{f.get('type')}**: {f.get('message')}")
            for loc in f.get("locations", []) or []:
                fp = loc.get("file", f.get("file", "?"))
                ln = loc.get("line", "?")
                lines.append(f"  - at `{fp}:{ln}`")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_static(args) -> int:
    wp_dir = resolve_wp_dir(args.slug)
    if wp_dir is None:
        print(f"WP not found: {args.slug}", file=sys.stderr)
        return 2

    close = load_close_report(wp_dir)
    review = load_review_report(wp_dir)
    events = events_for_wp(wp_dir.name)

    if close is None and not (wp_dir / "15_diff.patch").is_file():
        print(
            f"No close_report.json and no 15_diff.patch in {wp_dir.name}. "
            f"Run tcad_log close first.",
            file=sys.stderr,
        )
        return 2

    graph = compose_graph(
        wp_dir=wp_dir, close=close, review=review, events=events,
    )

    graph_path = wp_dir / "16_code_graph.json"
    mermaid_path = wp_dir / "19_mermaid.md"
    graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    mermaid_path.write_text(render_mermaid(graph), encoding="utf-8")

    if args.json:
        print(json.dumps(graph, indent=2))
        return 0

    summary = graph["summary"]
    print(f"Graph generated for {wp_dir.name}:")
    print(f"  files:        {summary['files_total']} "
          f"(created {summary['files_created']}, modified {summary['files_modified']}, deleted {summary['files_deleted']})")
    print(f"  changes:      +{summary['additions']} / -{summary['deletions']}")
    print(f"  nodes:        {len(graph['nodes'])}")
    print(f"  edges:        {len(graph['edges'])}")
    gates = graph["gates"]
    if gates.get("review_present"):
        if gates.get("review_pass"):
            print(f"  review:       PASS")
        else:
            print(f"  review:       FAIL ({gates.get('review_critical_count', 0)} critical)")
    proj = graph.get("project") or {}
    if proj.get("type"):
        layers = graph.get("layer_touches") or {}
        layer_str = ", ".join(f"{k}:{v}" for k, v in layers.items()) if layers else "none"
        print(f"  project:      {proj.get('type')} (backend={(proj.get('stack') or {}).get('backend')}, "
              f"frontend={(proj.get('stack') or {}).get('frontend')})")
        print(f"  layers:       {layer_str}")
    print(f"  outputs:")
    print(f"    {graph_path.relative_to(ROOT)}")
    print(f"    {mermaid_path.relative_to(ROOT)}")
    return 0


def cmd_show(args) -> int:
    wp_dir = resolve_wp_dir(args.slug)
    if wp_dir is None:
        print(f"WP not found: {args.slug}", file=sys.stderr)
        return 2
    mermaid_path = wp_dir / "19_mermaid.md"
    if not mermaid_path.is_file():
        print(f"19_mermaid.md not present. Run `tcad_graph.py static {args.slug}` first.",
              file=sys.stderr)
        return 2
    print(mermaid_path.read_text(encoding="utf-8"))
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="tcad_graph",
        description="Static graph from existing artifacts. No LLM, no invention.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("static", help="Generate code_graph.json + mermaid.md.")
    s.add_argument("slug", help="WP id or slug.")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_static)

    s = sub.add_parser("show", help="Print mermaid for a WP.")
    s.add_argument("slug")
    s.set_defaults(func=cmd_show)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
