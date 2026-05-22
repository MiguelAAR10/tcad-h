#!/usr/bin/env python3
"""
TCAD Studio — localhost dashboard for visualizing the project as a building.

Phase 1.7 / Phase 4 v0 deliverable.

Stdlib only. No external dependencies. No build step.

Usage:
    python studio/server.py
    # then open http://localhost:8765

What it serves:
    /                       static index.html
    /styles.css             stylesheet
    /app.js                 client logic
    /api/state              JSON: { project, floors, wps, status, timestamp }
    /api/wp/<wp-id>         JSON: full WP details (files, snippets, timeline)
    /api/blueprint          JSON: parsed blueprint.yaml
    /api/refresh            POST: forces a fresh read from disk (cache bust)

Why this design:
    - No external deps means anyone can run it.
    - File-system reads on every request keep state honest (no stale cache).
    - JSON-only API decouples server from UI; UI can be rewritten in any
      framework later.
    - YAML parser is intentionally minimal — covers the blueprint schema
      shape, not arbitrary YAML.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import socketserver
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_PATH = Path(__file__).resolve()
STUDIO_DIR = SCRIPT_PATH.parent
ROOT = STUDIO_DIR.parent
PROTOCOL_DIR = ROOT / ".protocol"
BLUEPRINT_FILE = ROOT / ".protocol" / "blueprint" / "blueprint.yaml"
BLUEPRINT_EXAMPLE = ROOT / ".protocol" / "blueprint" / "blueprint.yaml.example"
HANDOFFS_DIR = ROOT / ".protocol" / "handoffs"
QUESTIONS_INDEX = ROOT / ".protocol" / "questions" / "INDEX.md"
STATUS_FILE = ROOT / ".protocol" / "status.json"
JOURNAL_INDEX = ROOT / ".protocol" / "journal" / "INDEX.md"

DEFAULT_PORT = 8765


# ---------------------------------------------------------------------------
# Minimal YAML parser (enough for our blueprint schema)
# ---------------------------------------------------------------------------
class TinyYAML:
    """Parse the subset of YAML we use in blueprint files.

    Supports:
        - dict keys followed by ':' and value or ':' followed by indented block
        - lists as '-' items at the same indent
        - scalars: strings (quoted or bare), numbers, booleans, null
        - comments starting with '#'
        - empty lines

    Does NOT support: anchors, references, multi-line strings, flow style,
    tags. Sufficient for our blueprint shape.
    """

    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.pos = 0

    def parse(self) -> Any:
        result, _ = self._parse_block(indent=0)
        return result

    def _peek(self) -> str | None:
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            stripped = line.split("#", 1)[0].rstrip()
            if stripped.strip() == "":
                self.pos += 1
                continue
            return line
        return None

    def _line_indent(self, line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def _scalar(self, raw: str) -> Any:
        raw = raw.strip()
        # strip inline comment
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
        # numeric?
        try:
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            pass
        # inline flow list
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [self._scalar(item) for item in self._split_csv(inner)]
        return raw

    @staticmethod
    def _split_csv(s: str) -> list[str]:
        items: list[str] = []
        buf = ""
        depth_b = depth_p = 0
        in_str: str | None = None
        for ch in s:
            if in_str:
                buf += ch
                if ch == in_str:
                    in_str = None
                continue
            if ch in ('"', "'"):
                in_str = ch
                buf += ch
                continue
            if ch == "[":
                depth_b += 1
            elif ch == "]":
                depth_b -= 1
            elif ch == "(":
                depth_p += 1
            elif ch == ")":
                depth_p -= 1
            if ch == "," and depth_b == 0 and depth_p == 0:
                items.append(buf.strip())
                buf = ""
                continue
            buf += ch
        if buf.strip():
            items.append(buf.strip())
        return items

    def _parse_block(self, indent: int) -> tuple[Any, int]:
        line = self._peek()
        if line is None:
            return None, indent

        line_indent = self._line_indent(line)
        if line_indent < indent:
            return None, line_indent

        # List?
        stripped = line.lstrip(" ")
        if stripped.startswith("- "):
            items = []
            while True:
                line = self._peek()
                if line is None:
                    break
                li = self._line_indent(line)
                if li < indent:
                    break
                if li > indent:
                    break
                s = line.lstrip(" ")
                if not s.startswith("- "):
                    break
                self.pos += 1
                rest = s[2:]
                if ":" in rest and not rest.startswith('"'):
                    # Inline first key of a dict item: "- key: value"
                    # Or "- key:\n   nested..."
                    # Rewind treatment: synthesize an indented mapping line.
                    synthesized = " " * (indent + 2) + rest
                    self.lines.insert(self.pos, synthesized)
                    item, _ = self._parse_block(indent + 2)
                    items.append(item)
                elif rest.strip() == "":
                    # Empty list item that contains a nested block.
                    item, _ = self._parse_block(indent + 2)
                    items.append(item)
                else:
                    items.append(self._scalar(rest))
            return items, indent

        # Dict
        result: dict[str, Any] = {}
        while True:
            line = self._peek()
            if line is None:
                break
            li = self._line_indent(line)
            if li < indent:
                break
            if li > indent:
                break
            s = line.lstrip(" ")
            if s.startswith("- "):
                break
            if ":" not in s:
                # Unexpected; skip line to avoid infinite loop.
                self.pos += 1
                continue
            key, _, rest = s.partition(":")
            key = key.strip()
            self.pos += 1
            rest_stripped = rest.split("#", 1)[0].rstrip() if not rest.lstrip().startswith(('"', "'")) else rest.rstrip()
            if rest_stripped.strip() == "":
                # Nested block
                next_line = self._peek()
                if next_line is None:
                    result[key] = None
                    continue
                next_indent = self._line_indent(next_line)
                if next_indent <= indent:
                    result[key] = None
                    continue
                value, _ = self._parse_block(next_indent)
                result[key] = value
            else:
                result[key] = self._scalar(rest_stripped)
        return result, indent


def load_yaml(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return TinyYAML(text).parse()


# ---------------------------------------------------------------------------
# Repo scanning helpers
# ---------------------------------------------------------------------------
WP_DIR_RE = re.compile(r"^WP-(\d+)-(.+)$")


def scan_work_packages() -> list[dict[str, Any]]:
    """Return a list of Work Package summaries."""
    wps: list[dict[str, Any]] = []
    if not HANDOFFS_DIR.exists():
        return wps
    for child in sorted(HANDOFFS_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_"):
            continue
        match = WP_DIR_RE.match(child.name)
        if not match:
            continue
        wps.append(summarize_wp(child))
    return wps


def summarize_wp(wp_dir: Path) -> dict[str, Any]:
    """Cheap, mostly structural summary for the timeline view."""
    summary = {
        "id": wp_dir.name,
        "path": str(wp_dir.relative_to(ROOT)),
        "files": [],
        "status": "draft",
        "goal": None,
        "target_room": None,
        "created": None,
        "has_summary": False,
        "has_delta": False,
        "has_blockers": False,
        "has_review": False,
        "verdict": None,
    }

    for f in sorted(wp_dir.iterdir()):
        if not f.is_file():
            continue
        summary["files"].append(f.name)

    # Created date from the header comment if present.
    goal_path = wp_dir / "01_goal.md"
    if goal_path.exists():
        text = goal_path.read_text(encoding="utf-8", errors="ignore")
        m_created = re.search(r"created:\s*(\S+)", text)
        if m_created:
            summary["created"] = m_created.group(1)
        m_goal = re.search(r"goal:\s*(.+)", text)
        if m_goal:
            summary["goal"] = m_goal.group(1).strip().rstrip("-").rstrip()
        # Parse "User intent" section for the human-edited goal.
        m_intent = re.search(r"##\s*User intent\s*\n+\s*(.+?)\n", text)
        if m_intent:
            summary["goal"] = m_intent.group(1).strip()
        # Parse "target_room" if user added it.
        m_room = re.search(r"target_room:\s*([\w.\-]+)", text)
        if m_room:
            summary["target_room"] = m_room.group(1)

    summary["has_summary"] = (wp_dir / "11_worker_summary.md").exists()
    summary["has_delta"] = (wp_dir / "12_delta.md").exists()
    summary["has_blockers"] = (wp_dir / "13_blockers.md").exists()
    review_path = wp_dir / "14_review_result.md"
    summary["has_review"] = review_path.exists()
    if summary["has_review"]:
        text = review_path.read_text(encoding="utf-8", errors="ignore")
        m_v = re.search(r"VERDICT:\s*(\w+)", text)
        if m_v:
            summary["verdict"] = m_v.group(1)

    # Derive a coarse status for the timeline.
    if summary["has_blockers"]:
        summary["status"] = "blocked"
    elif summary["verdict"] == "FAIL":
        summary["status"] = "failed"
    elif summary["verdict"] in ("PASS", "PASS_WITH_NOTES"):
        summary["status"] = "graduated"
    elif summary["has_summary"]:
        summary["status"] = "review"
    elif summary["has_delta"]:
        summary["status"] = "rewrite"
    else:
        summary["status"] = "draft"

    return summary


def _normalize_pattern(pattern: str) -> str:
    """pathlib glob does not recurse into a trailing `/**`. Append `/*` so
    `foo/**` becomes `foo/**/*`, which matches files at any depth under foo.
    """
    if pattern.endswith("/**"):
        return pattern + "/*"
    return pattern


def glob_count(pattern: str) -> int:
    """Count files matching a glob, relative to ROOT."""
    try:
        matches = list(ROOT.glob(_normalize_pattern(pattern)))
    except (ValueError, OSError):
        return 0
    return sum(1 for m in matches if m.is_file())


def loc_for_paths(patterns: list[str]) -> int:
    total = 0
    seen: set[Path] = set()
    for pat in patterns or []:
        for f in ROOT.glob(_normalize_pattern(pat)):
            if not f.is_file():
                continue
            if f in seen:
                continue
            seen.add(f)
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            total += sum(1 for _ in text.splitlines())
    return total


def compute_room_status(
    room: dict, wps: list[dict], open_questions: list[dict]
) -> dict:
    """Compute status, progress, and which WPs touched the room."""
    allowed = room.get("allowed_paths", []) or []
    file_count = sum(glob_count(p) for p in allowed)
    loc = loc_for_paths(allowed)

    # Match WPs that touched this room (target_room field or path overlap).
    touched: list[str] = []
    active = False
    finished = False
    failed = False
    for wp in wps:
        if wp.get("target_room") == room["id"]:
            touched.append(wp["id"])
            if wp["status"] in ("draft", "review", "rewrite"):
                active = True
            if wp["status"] == "graduated":
                finished = True
            if wp["status"] in ("failed", "blocked"):
                failed = True

    # Open questions referencing the room.
    has_open_question = any(q.get("room") == room["id"] for q in open_questions)

    # Status decision.
    if failed or has_open_question:
        status = "cracked"
    elif finished and file_count > 0:
        status = "finished"
    elif active:
        status = "foundations"
    elif file_count > 0:
        status = "built"
    else:
        status = "planned"

    # Progress: ratio of expected_furniture seemingly present.
    expected = room.get("expected_furniture", []) or []
    if expected:
        # Heuristic: progress = files_present_for_globs / len(expected),
        # clipped to [0, 1].
        progress = min(1.0, file_count / max(len(expected), 1))
    else:
        progress = 1.0 if file_count > 0 else 0.0

    return {
        "status": status,
        "progress": round(progress, 2),
        "file_count": file_count,
        "loc": loc,
        "built_by_wps": touched,
    }


def parse_open_questions() -> list[dict]:
    """Return open questions from .protocol/questions/INDEX.md."""
    questions: list[dict] = []
    if not QUESTIONS_INDEX.exists():
        return questions
    text = QUESTIONS_INDEX.read_text(encoding="utf-8", errors="ignore")
    # Q-NNN sections with Status: 🟡 pending
    for m in re.finditer(
        r"##\s*(Q-\d+)\s*—\s*(.+?)\n(.*?)(?=\n##\s|\Z)",
        text,
        re.DOTALL,
    ):
        qid, title, body = m.group(1), m.group(2), m.group(3)
        if "pending" not in body and "🟡" not in body:
            continue
        m_blocks = re.search(r"\*\*Blocks\*\*:\s*([^\n]+)", body)
        m_room = re.search(r"room:\s*([\w.\-]+)", body)
        questions.append(
            {
                "id": qid,
                "title": title.strip(),
                "blocks": m_blocks.group(1).strip() if m_blocks else None,
                "room": m_room.group(1) if m_room else None,
            }
        )
    return questions


def read_status_json() -> dict:
    if not STATUS_FILE.exists():
        return {"state": "IDLE", "active_wp": None, "note": "status.json not yet present (Phase 1.5)"}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"state": "ERROR", "error": str(exc)}


def merge_questions(md_questions: list[dict], status: dict) -> list[dict]:
    """Combine markdown-parsed questions with live status.json open_questions.

    status.json is the live registry written by tcad_conduct.py and wins on
    conflicts. INDEX.md may contain extra context fields (room, evidence)
    that status.json lacks, so we merge by id.
    """
    by_id: dict[str, dict] = {}
    for q in md_questions or []:
        by_id[q["id"]] = dict(q)
    for q in (status.get("open_questions") or []):
        if q.get("status") and q["status"] != "pending":
            # Drop resolved/answered from open view.
            by_id.pop(q.get("id"), None)
            continue
        existing = by_id.get(q["id"], {})
        existing.update({k: v for k, v in q.items() if v is not None})
        by_id[q["id"]] = existing
    return list(by_id.values())


def build_state_payload() -> dict:
    blueprint = load_yaml(BLUEPRINT_FILE) or load_yaml(BLUEPRINT_EXAMPLE)
    wps = scan_work_packages()
    status = read_status_json()
    md_questions = parse_open_questions()
    open_questions = merge_questions(md_questions, status)

    if blueprint:
        for floor in blueprint.get("floors", []) or []:
            for room in floor.get("rooms", []) or []:
                room.update(compute_room_status(room, wps, open_questions))

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project": (blueprint or {}).get("project", {}),
        "floors": (blueprint or {}).get("floors", []),
        "pipes": (blueprint or {}).get("pipes", []),
        "construction_plan": (blueprint or {}).get("construction_plan", []),
        "wps": wps,
        "open_questions": open_questions,
        "status": status,
        "warnings": [] if blueprint else ["No blueprint.yaml found. Showing empty building."],
    }




def read_events_tail(n: int = 10) -> list:
    """Read the last N lines of events.jsonl as parsed JSON objects."""
    if not (PROTOCOL_DIR / "events.jsonl").exists():
        return []
    lines = (PROTOCOL_DIR / "events.jsonl").read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def list_wps_with_graphs() -> list[dict]:
    """Return WPs that have a 16_code_graph.json on disk."""
    out: list[dict] = []
    if not HANDOFFS_DIR.exists():
        return out
    for child in sorted(HANDOFFS_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        graph_path = child / "16_code_graph.json"
        if not graph_path.is_file():
            continue
        # Lightweight summary so the UI selector can render fast.
        try:
            data = json.loads(graph_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        gates = data.get("gates", {}) or {}
        review_pass = gates.get("review_pass")
        out.append({
            "wp": child.name,
            "role": data.get("role"),
            "branch": data.get("branch"),
            "files_total": data.get("summary", {}).get("files_total", 0),
            "review_present": gates.get("review_present", False),
            "review_pass": review_pass,
            "critical_count": gates.get("review_critical_count", 0),
            "generated_at": data.get("generated_at"),
        })
    return out


def read_graph(wp_id: str) -> dict | None:
    p = HANDOFFS_DIR / wp_id / "16_code_graph.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def read_mermaid(wp_id: str) -> str | None:
    p = HANDOFFS_DIR / wp_id / "19_mermaid.md"
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8")


def read_review(wp_id: str) -> dict | None:
    p = HANDOFFS_DIR / wp_id / "review_report.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def read_wp_details(wp_id: str) -> dict | None:
    wp_dir = HANDOFFS_DIR / wp_id
    if not wp_dir.is_dir():
        return None
    out: dict[str, Any] = {"id": wp_id, "files": {}}
    for f in sorted(wp_dir.iterdir()):
        if not f.is_file():
            continue
        try:
            out["files"][f.name] = f.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            out["files"][f.name] = f"<read error: {exc}>"
    return out


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class StudioHandler(http.server.BaseHTTPRequestHandler):
    # Quieter logs.
    def log_message(self, format, *args):  # noqa: A002
        sys.stderr.write("[studio] " + (format % args) + "\n")

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path, content_type: str) -> None:
        try:
            data = file_path.read_bytes()
        except OSError:
            self.send_error(404, f"Not found: {file_path.name}")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._send_file(STUDIO_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path == "/styles.css":
            self._send_file(STUDIO_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._send_file(STUDIO_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if path == "/api/state":
            self._send_json(build_state_payload())
            return
        if path == "/api/blueprint":
            self._send_json(load_yaml(BLUEPRINT_FILE) or load_yaml(BLUEPRINT_EXAMPLE) or {})
            return
        if path == "/api/events":
            try:
                limit = int(urllib.parse.parse_qs(parsed.query).get("limit", ["10"])[0])
            except ValueError:
                limit = 10
            self._send_json(read_events_tail(limit))
            return
        if path.startswith("/api/wp/"):
            wp_id = urllib.parse.unquote(path[len("/api/wp/"):])
            details = read_wp_details(wp_id)
            if details is None:
                self._send_json({"error": "not_found", "id": wp_id}, status=404)
            else:
                self._send_json(details)
            return

        # Phase 3 — graph endpoints (read-only, no LLM).
        if path == "/api/graphs":
            self._send_json(list_wps_with_graphs())
            return
        if path.startswith("/api/graph/"):
            wp_id = urllib.parse.unquote(path[len("/api/graph/"):])
            graph = read_graph(wp_id)
            if graph is None:
                self._send_json({"error": "graph_not_found", "wp": wp_id}, status=404)
            else:
                self._send_json(graph)
            return
        if path.startswith("/api/mermaid/"):
            wp_id = urllib.parse.unquote(path[len("/api/mermaid/"):])
            mermaid = read_mermaid(wp_id)
            if mermaid is None:
                self.send_error(404, f"No mermaid for {wp_id}")
                return
            # Serve as plain text so the client can render or display verbatim.
            body = mermaid.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/api/review/"):
            wp_id = urllib.parse.unquote(path[len("/api/review/"):])
            review = read_review(wp_id)
            if review is None:
                self._send_json({"error": "review_not_found", "wp": wp_id}, status=404)
            else:
                self._send_json(review)
            return

        self.send_error(404, f"No route for {path}")


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(port: int) -> None:
    with ReusableThreadingTCPServer(("127.0.0.1", port), StudioHandler) as httpd:
        print(f"TCAD Studio listening at http://127.0.0.1:{port}")
        print(f"  blueprint: {BLUEPRINT_FILE.relative_to(ROOT)}")
        print(f"  root:      {ROOT}")
        print("  Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down studio.")


def main(argv: list[str]) -> int:
    port = DEFAULT_PORT
    if len(argv) >= 1 and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if "--port" in argv:
        try:
            port = int(argv[argv.index("--port") + 1])
        except (ValueError, IndexError):
            print("Error: --port requires an integer.", file=sys.stderr)
            return 1
    if not BLUEPRINT_FILE.exists() and not BLUEPRINT_EXAMPLE.exists():
        print(
            f"Warning: no blueprint at {BLUEPRINT_FILE} nor example at {BLUEPRINT_EXAMPLE}.\n"
            f"Studio will render an empty building.",
            file=sys.stderr,
        )
    serve(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
