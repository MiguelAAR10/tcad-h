#!/usr/bin/env python3
"""
tcad_profile.py — TCAD-H Project Profile Detector.

Phase 3.1 deliverable. Mentor scope:
    "TCAD-H must know the TYPE of project before diagramming.
     Without this, every graph is just a file graph."

Deterministic. No LLM. No web fetch. Inspects manifest files and folder
patterns to produce .protocol/project_profile.json.

Commands:
    detect [--force]   Inspect repo, emit project_profile.json.
                       Refuses to overwrite an existing profile without --force.
    show [--json]      Print current profile.
    validate           For each layer's globs, count actual matches in the repo
                       and warn about layers that match zero files (likely drift).

Exit codes:
    0  success
    1  bad args
    2  no manifest detected and no --force; cannot guess project type
    3  validation found empty layers (warning) — exit 0 unless --strict
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT_PATH.parent))
from _tcad_root import resolve_tcad_root  # noqa: E402

ROOT = resolve_tcad_root(os.environ.get("FOREMAN_ROOT") or os.environ.get("TCAD_ROOT"))
PROTOCOL_DIR = ROOT / ".protocol"
PROFILE_JSON = PROTOCOL_DIR / "project_profile.json"
PROFILE_YAML_EXAMPLE = PROTOCOL_DIR / "project_profile.yaml.example"


# ---------------------------------------------------------------------------
# Manifest inspectors
# ---------------------------------------------------------------------------
def has(path: str) -> bool:
    return (ROOT / path).exists()


def read_text_safe(path: str) -> str:
    p = ROOT / path
    if not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def has_dir(name: str) -> bool:
    return (ROOT / name).is_dir()


def find_first(*candidates: str) -> str | None:
    for c in candidates:
        if (ROOT / c).exists():
            return c
    return None


def detect_stack() -> dict[str, str]:
    """Determine backend / frontend / package_manager / test_runner / build_tool."""
    stack: dict[str, str] = {
        "backend": "none",
        "frontend": "none",
        "package_manager": "none",
        "test_runner": "none",
        "build_tool": "none",
    }

    # Backend
    if "fastapi" in read_text_safe("backend/requirements.txt").lower() \
       or "fastapi" in read_text_safe("requirements.txt").lower() \
       or "fastapi" in read_text_safe("backend/pyproject.toml").lower() \
       or "fastapi" in read_text_safe("pyproject.toml").lower():
        stack["backend"] = "fastapi"
    elif "django" in read_text_safe("requirements.txt").lower() or has("manage.py"):
        stack["backend"] = "django"
    elif "flask" in read_text_safe("requirements.txt").lower():
        stack["backend"] = "flask"
    elif "express" in read_text_safe("package.json"):
        stack["backend"] = "express"
    elif "nestjs" in read_text_safe("package.json") or "@nestjs" in read_text_safe("package.json"):
        stack["backend"] = "nest"

    # Frontend
    pkg = read_text_safe("package.json") + read_text_safe("frontend/package.json")
    if "next" in pkg.lower():
        stack["frontend"] = "next"
    elif "@angular/" in pkg:
        stack["frontend"] = "angular"
    elif "vue" in pkg.lower() and "react" not in pkg.lower():
        stack["frontend"] = "vue"
    elif "svelte" in pkg.lower():
        stack["frontend"] = "svelte"
    elif "react" in pkg.lower():
        stack["frontend"] = "react"

    # Package manager
    if has("pnpm-lock.yaml") or has("pnpm-workspace.yaml"):
        stack["package_manager"] = "pnpm"
    elif has("yarn.lock"):
        stack["package_manager"] = "yarn"
    elif has("bun.lock") or has("bun.lockb"):
        stack["package_manager"] = "bun"
    elif has("package-lock.json"):
        stack["package_manager"] = "npm"
    elif has("poetry.lock") or "[tool.poetry]" in read_text_safe("pyproject.toml"):
        stack["package_manager"] = "poetry"
    elif has("uv.lock"):
        stack["package_manager"] = "uv"
    elif has("Pipfile.lock") or has("Pipfile"):
        stack["package_manager"] = "pipenv"
    elif has("requirements.txt") or has("pyproject.toml"):
        stack["package_manager"] = "pip"
    elif has("Cargo.toml"):
        stack["package_manager"] = "cargo"
    elif has("go.mod"):
        stack["package_manager"] = "go-mod"

    # Test runner
    if "vitest" in pkg.lower():
        stack["test_runner"] = "vitest"
    elif "jest" in pkg.lower():
        stack["test_runner"] = "jest"
    if "pytest" in read_text_safe("requirements.txt").lower() \
       or "pytest" in read_text_safe("backend/requirements.txt").lower() \
       or "pytest" in read_text_safe("pyproject.toml").lower():
        # Backends with pytest may coexist with frontend test runner.
        if stack["test_runner"] == "none":
            stack["test_runner"] = "pytest"
        else:
            stack["test_runner"] = f"{stack['test_runner']}+pytest"

    # Build tool
    if "next" in pkg.lower():
        stack["build_tool"] = "next"
    elif "vite" in pkg.lower() or has("vite.config.ts") or has("vite.config.js") or has("frontend/vite.config.ts"):
        stack["build_tool"] = "vite"
    elif has("angular.json"):
        stack["build_tool"] = "angular"
    elif has("webpack.config.js") or has("webpack.config.ts"):
        stack["build_tool"] = "webpack"

    return stack


def detect_project_type(stack: dict[str, str]) -> str:
    """Pick a coarse project type from stack + folder layout."""
    has_backend = stack["backend"] not in ("none", "")
    has_frontend = stack["frontend"] not in ("none", "")
    has_apps = has_dir("apps") or has_dir("packages")
    has_agent_dirs = has_dir("agents") or has_dir("retrievers") or has_dir("prompts")
    has_scripts = has_dir("scripts") and not has_backend and not has_frontend

    if has_apps and (has_backend or has_frontend):
        return "monorepo"
    if has_backend and has_frontend:
        return "fullstack_web"
    if has_backend and not has_frontend:
        return "backend_api"
    if has_frontend and not has_backend:
        return "frontend_spa"
    if has_agent_dirs:
        return "agent_rag"
    if has_scripts and stack["package_manager"] in ("pip", "poetry", "uv"):
        return "python_library"
    if has("Cargo.toml"):
        return "rust_project"
    if has("go.mod"):
        return "go_project"
    return "other"


def detect_layers(project_type: str, stack: dict[str, str]) -> dict[str, list[str]]:
    """Return layers map adapted to detected stack. Adjusts globs based on layout."""
    base: dict[str, list[str]] = {
        "backend": [],
        "frontend": [],
        "tests": [],
        "infra": [
            ".github/workflows/**",
            "Dockerfile",
            "docker-compose*.yml",
            "fly.toml",
            "vercel.json",
            "infra/**",
        ],
        "docs": ["docs/**", "*.md", "**/*.md"],
        "config": ["*.json", "*.yaml", "*.yml", "*.toml", "*.cfg", "*.ini"],
        "scripts": ["scripts/**", "bin/**"],
    }

    # Backend layer
    if stack["backend"] in ("fastapi", "django", "flask"):
        if has_dir("backend"):
            base["backend"] = ["backend/**/*.py"]
        elif has_dir("app"):
            base["backend"] = ["app/**/*.py", "main.py"]
        else:
            base["backend"] = ["*.py", "**/*.py"]
    elif stack["backend"] in ("express", "nest"):
        if has_dir("backend"):
            base["backend"] = ["backend/**/*.ts", "backend/**/*.js"]
        elif has_dir("server"):
            base["backend"] = ["server/**/*.ts", "server/**/*.js"]
        elif has_dir("apps"):
            base["backend"] = ["apps/api/**", "apps/server/**"]

    # Frontend layer
    if stack["frontend"] in ("next",):
        if has_dir("frontend"):
            base["frontend"] = ["frontend/**/*.tsx", "frontend/**/*.ts", "frontend/**/*.jsx"]
        elif has_dir("app"):
            base["frontend"] = ["app/**/*.tsx", "app/**/*.ts"]
        else:
            base["frontend"] = ["src/**/*.tsx", "pages/**/*.tsx", "components/**/*.tsx"]
    elif stack["frontend"] == "react":
        base["frontend"] = ["src/**/*.tsx", "src/**/*.jsx", "frontend/**/*.tsx"]
    elif stack["frontend"] == "angular":
        base["frontend"] = ["src/**/*.ts", "src/**/*.html", "src/**/*.scss"]
    elif stack["frontend"] == "vue":
        base["frontend"] = ["src/**/*.vue", "src/**/*.ts"]

    # Tests layer
    base["tests"] = [
        "tests/**",
        "**/test_*.py",
        "**/*_test.py",
        "**/*.test.ts",
        "**/*.test.tsx",
        "**/*.spec.ts",
        "**/*.spec.tsx",
    ]

    # Project-specific layers
    if project_type == "agent_rag":
        base["agent"] = ["agents/**", "prompts/**", "tools/**", "retrievers/**"]

    # Studio layer for TCAD-H itself
    if has_dir("studio") and has_dir("scripts") and (ROOT / ".protocol").is_dir():
        base["studio"] = ["studio/**"]

    # Drop empty layers
    return {k: v for k, v in base.items() if v}


def detect_detectors(stack: dict[str, str]) -> dict[str, list[str]]:
    detectors: dict[str, list[str]] = {"routes": [], "symbols": [], "components": []}
    if stack["backend"] == "fastapi":
        detectors["routes"].append("fastapi")
    if stack["backend"] in ("express", "nest"):
        detectors["routes"].append("express")
    if stack["backend"] == "flask":
        detectors["routes"].append("flask")
    if has(".py") or has_dir("app") or has_dir("backend") or stack["package_manager"] in ("pip", "poetry", "uv", "pipenv"):
        detectors["symbols"].append("python")
    if stack["frontend"] in ("react", "next", "vue", "svelte"):
        detectors["symbols"].append("typescript")
    if stack["frontend"] == "react" or stack["frontend"] == "next":
        detectors["components"].append("react")
    elif stack["frontend"] == "angular":
        detectors["components"].append("angular")
    return detectors


def detect_project_name() -> str:
    # Prefer package.json name.
    pkg = read_text_safe("package.json")
    if pkg:
        try:
            data = json.loads(pkg)
            if isinstance(data, dict) and "name" in data:
                return data["name"]
        except json.JSONDecodeError:
            pass
    # Else pyproject.toml [project] name
    py = read_text_safe("pyproject.toml")
    if "name" in py:
        for line in py.splitlines():
            if line.strip().startswith("name"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"').strip("'")
    return ROOT.name


# ---------------------------------------------------------------------------
# Glob match helper (same semantics as tcad_check_boundaries)
# ---------------------------------------------------------------------------
def _walk_match(path_parts: list[str], pat_parts: list[str]) -> bool:
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


def match_glob(path: str, pattern: str) -> bool:
    return _walk_match(path.split("/"), pattern.split("/"))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_detect(args) -> int:
    if PROFILE_JSON.exists() and not args.force:
        print(
            f"Refusing: {PROFILE_JSON.relative_to(ROOT)} already exists. "
            f"Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    stack = detect_stack()
    project_type = detect_project_type(stack)
    layers = detect_layers(project_type, stack)
    detectors = detect_detectors(stack)

    profile = {
        "schema_version": 1.0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "tcad_profile.py detect",
        "project": {
            "name": detect_project_name(),
            "type": project_type,
        },
        "stack": stack,
        "layers": layers,
        "detectors": detectors,
        "architecture_blocks": [],
        "visual_model": "file_layer_grouped",
    }

    PROTOCOL_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_JSON.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    print(f"Wrote {PROFILE_JSON.relative_to(ROOT)}")
    print(f"  name:    {profile['project']['name']}")
    print(f"  type:    {profile['project']['type']}")
    print(f"  backend: {stack['backend']}")
    print(f"  frontend:{stack['frontend']}")
    print(f"  layers:  {list(layers.keys())}")
    print(f"  detectors: {detectors}")
    return 0


def cmd_show(args) -> int:
    if not PROFILE_JSON.exists():
        print("No profile yet. Run `tcad_profile.py detect`.", file=sys.stderr)
        return 2
    data = json.loads(PROFILE_JSON.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    print(f"Project: {data['project']['name']} ({data['project']['type']})")
    print(f"Stack:")
    for k, v in (data.get("stack") or {}).items():
        print(f"  {k:<18} {v}")
    print(f"Layers:")
    for k, globs in (data.get("layers") or {}).items():
        print(f"  {k}:")
        for g in globs:
            print(f"    - {g}")
    print(f"Detectors: {data.get('detectors')}")
    print(f"Visual model: {data.get('visual_model')}")
    return 0


def cmd_validate(args) -> int:
    if not PROFILE_JSON.exists():
        print("No profile yet. Run `tcad_profile.py detect`.", file=sys.stderr)
        return 2
    data = json.loads(PROFILE_JSON.read_text(encoding="utf-8"))
    layers = data.get("layers", {}) or {}
    # Walk the repo (excluding noise) and count files per layer.
    all_files: list[str] = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(ROOT))
        if any(seg in rel.split("/") for seg in (".git", "__pycache__", "node_modules", ".venv", "dist", "build")):
            continue
        if rel.startswith(".protocol/worktrees/"):
            continue
        all_files.append(rel)

    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    for layer, globs in layers.items():
        c = 0
        ex: list[str] = []
        for f in all_files:
            if any(match_glob(f, g) for g in globs):
                c += 1
                if len(ex) < 3:
                    ex.append(f)
        counts[layer] = c
        examples[layer] = ex

    empty = [l for l, c in counts.items() if c == 0]
    if args.json:
        print(json.dumps({"counts": counts, "examples": examples, "empty": empty}, indent=2))
        return 3 if (empty and args.strict) else 0

    print(f"Layer match counts (over {len(all_files)} files):")
    for layer, c in counts.items():
        flag = "" if c > 0 else "  [EMPTY]"
        print(f"  {layer:<10} {c:>5}{flag}")
        for ex in examples[layer]:
            print(f"      e.g. {ex}")
    if empty:
        print(f"\nWarning: {len(empty)} empty layer(s): {empty}")
        return 3 if args.strict else 0
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tcad_profile", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("detect", help="Detect project type and write profile.")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_detect)

    s = sub.add_parser("show", help="Print current profile.")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("validate", help="Verify layer globs match real files.")
    s.add_argument("--json", action="store_true")
    s.add_argument("--strict", action="store_true",
                   help="Exit 3 if any layer is empty.")
    s.set_defaults(func=cmd_validate)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
