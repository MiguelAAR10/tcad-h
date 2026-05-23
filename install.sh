#!/usr/bin/env bash
# TCAD-H local installer.
#
# Symlinks the `tcad` CLI into ~/.local/bin (or a user-chosen location)
# and verifies dependencies. POSIX bash only. No pip. No sudo (unless the
# install target requires it).

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FOREMAN_BIN="$HERE/bin/foreman"
TCAD_BIN="$HERE/bin/tcad"   # deprecated alias
DEFAULT_INSTALL_DIR="$HOME/.local/bin"

cyan()  { printf '\033[36m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }

cyan "Foreman installer (Site supervisor for AI coding crews)"
echo "  framework home: $HERE"

# ---- Dependency checks ----------------------------------------------------
ok=1
for cmd in python3 git; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        red "  missing required: $cmd"
        ok=0
    fi
done
if [ "$ok" -ne 1 ]; then
    red "Install python3 + git and retry."
    exit 1
fi
pyver="$(python3 --version | awk '{print $2}')"
echo "  python: $pyver"
echo "  git:    $(git --version | awk '{print $3}')"

# ---- Verify tcad wrapper present ------------------------------------------
for b in "$FOREMAN_BIN" "$TCAD_BIN"; do
    if [ ! -x "$b" ]; then
        chmod +x "$b" 2>/dev/null || true
    fi
    if [ ! -x "$b" ]; then
        red "Wrapper not executable: $b"
        exit 1
    fi
done

# ---- Sanity: compile all scripts ------------------------------------------
echo ""
echo "Compiling scripts..."
for f in "$HERE"/scripts/*.py "$HERE"/studio/server.py; do
    [ -f "$f" ] || continue
    if ! python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
        red "  syntax error in: $f"
        exit 1
    fi
done
green "  all scripts compile"

# ---- Pick install target --------------------------------------------------
INSTALL_DIR="${TCAD_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
echo ""
echo "Install target: $INSTALL_DIR"
if [ ! -d "$INSTALL_DIR" ]; then
    yellow "  directory does not exist, creating..."
    mkdir -p "$INSTALL_DIR"
fi
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$INSTALL_DIR"; then
    yellow "  WARNING: $INSTALL_DIR is not on your PATH."
    yellow "           Add this line to your shell rc:"
    yellow "             export PATH=\"$INSTALL_DIR:\$PATH\""
fi

# ---- Symlink --------------------------------------------------------------
for pair in "foreman:$FOREMAN_BIN" "tcad:$TCAD_BIN"; do
    name="${pair%%:*}"
    src="${pair#*:}"
    target="$INSTALL_DIR/$name"
    if [ -L "$target" ] || [ -f "$target" ]; then
        yellow "  $target already exists; replacing"
        rm -f "$target"
    fi
    ln -s "$src" "$target"
    green "  linked: $target -> $src"
done
TARGET="$INSTALL_DIR/foreman"

# ---- Verify -------------------------------------------------------------
echo ""
echo "Verifying..."
if "$TARGET" --version >/dev/null 2>&1; then
    green "  foreman --version: $("$TARGET" --version)"
else
    red "  tcad --version failed"
    exit 1
fi

echo ""
green "Installation complete."
echo ""
echo "Next steps:"
echo "  cd /path/to/your/project"
echo "  foreman init"
echo "  foreman profile detect"
echo "  foreman doctor"
echo ""
echo "See $HERE/docs/QUICKSTART.md for a 10-minute walkthrough."
