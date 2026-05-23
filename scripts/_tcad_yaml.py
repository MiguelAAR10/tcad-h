"""Minimal YAML parser shared by all TCAD-H / Foreman scripts.

Phase 3.5+ consolidation. Previously duplicated in:
    - scripts/tcad_check_boundaries.py
    - studio/server.py
both with their own copy. Now single source.

Supports the subset of YAML used across the project:
    - dict / list / scalar
    - quoted and bare strings
    - integers, floats, booleans, null
    - inline lists with [a, b, c]
    - comments starting with '#'
    - nested blocks via indentation

Does NOT support: anchors, references, multi-line strings, flow style for
dicts, custom tags. If you need those, you already need PyYAML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class TinyYAML:
    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.pos = 0

    def parse(self) -> Any:
        result, _ = self._parse_block(indent=0)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _peek(self) -> str | None:
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            stripped = line.split("#", 1)[0].rstrip()
            if stripped.strip() == "":
                self.pos += 1
                continue
            return line
        return None

    @staticmethod
    def _line_indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

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

    def _scalar(self, raw: str) -> Any:
        raw = raw.strip()
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
            pass
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [self._scalar(item) for item in self._split_csv(inner)]
        return raw

    def _parse_block(self, indent: int) -> tuple[Any, int]:
        line = self._peek()
        if line is None:
            return None, indent

        line_indent = self._line_indent(line)
        if line_indent < indent:
            return None, line_indent

        stripped = line.lstrip(" ")

        # ---------- list ----------
        if stripped.startswith("- "):
            items: list[Any] = []
            while True:
                line = self._peek()
                if line is None:
                    break
                li = self._line_indent(line)
                if li < indent or li > indent:
                    break
                s = line.lstrip(" ")
                if not s.startswith("- "):
                    break
                self.pos += 1
                rest = s[2:]
                if ":" in rest and not rest.startswith('"'):
                    synthesized = " " * (indent + 2) + rest
                    self.lines.insert(self.pos, synthesized)
                    item, _ = self._parse_block(indent + 2)
                    items.append(item)
                elif rest.strip() == "":
                    item, _ = self._parse_block(indent + 2)
                    items.append(item)
                else:
                    items.append(self._scalar(rest))
            return items, indent

        # ---------- dict ----------
        result: dict[str, Any] = {}
        while True:
            line = self._peek()
            if line is None:
                break
            li = self._line_indent(line)
            if li < indent or li > indent:
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
            rest_stripped = (
                rest.split("#", 1)[0].rstrip()
                if not rest.lstrip().startswith(('"', "'"))
                else rest.rstrip()
            )
            if rest_stripped.strip() == "":
                next_line = self._peek()
                if next_line is None or self._line_indent(next_line) <= indent:
                    result[key] = None
                    continue
                value, _ = self._parse_block(self._line_indent(next_line))
                result[key] = value
            else:
                result[key] = self._scalar(rest_stripped)
        return result, indent


def load_yaml(path: Path) -> dict | None:
    """Convenience: read a YAML file or return None if missing/empty."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return TinyYAML(text).parse()
