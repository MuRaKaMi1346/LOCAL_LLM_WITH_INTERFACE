#!/usr/bin/env bash
# ============================================================
#  setup_mac.sh — One-time setup for LINE Bot on macOS
#  Run once: bash scripts/setup_mac.sh
#  After that, just double-click LineBot.app
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

VENV_DIR="$PROJECT_DIR/.venv"
APP_BUNDLE="$PROJECT_DIR/LineBot.app"
APP_EXEC="$APP_BUNDLE/Contents/MacOS/LineBot"

# ── Pretty printer ───────────────────────────────────────────────────────────
info()    { echo "  ✦  $*"; }
success() { echo "  ✅  $*"; }
warn()    { echo "  ⚠️   $*"; }
error()   { echo "  ❌  $*"; exit 1; }
banner() {
    echo ""
    echo "  ╔══════════════════════════════════════════════╗"
    echo "  ║        LINE Bot — macOS Setup                ║"
    echo "  ╚══════════════════════════════════════════════╝"
    echo ""
}

banner

# ── 1. Check Python 3.10+ ────────────────────────────────────────────────────
info "Checking Python version..."

PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON=$(command -v "$cmd")
            success "Found $cmd $VER at $PYTHON"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    error "Python 3.10 or newer is required.\nInstall from https://www.python.org/downloads/ or via Homebrew: brew install python@3.12"
fi

# ── 2. Check tkinter is available ───────────────────────────────────────────
info "Checking tkinter..."
if ! "$PYTHON" -c "import tkinter" 2>/dev/null; then
    warn "tkinter not found in $PYTHON"
    warn "If you installed Python via Homebrew, install: brew install python-tk"
    warn "Or download the official installer from python.org (includes Tk)"
    read -rp "  Continue anyway? (y/N) " CONT
    [[ "$CONT" =~ ^[Yy]$ ]] || exit 1
else
    success "tkinter OK"
fi

# ── 3. Create virtual environment ────────────────────────────────────────────
if [ -d "$VENV_DIR" ]; then
    info "Virtual environment already exists — skipping creation"
else
    info "Creating virtual environment at .venv ..."
    "$PYTHON" -m venv "$VENV_DIR"
    success "Virtual environment created"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ── 4. Upgrade pip silently ──────────────────────────────────────────────────
info "Upgrading pip..."
"$VENV_PY" -m pip install --upgrade pip --quiet
success "pip up to date"

# ── 5. Install requirements ──────────────────────────────────────────────────
if [ ! -f "$PROJECT_DIR/requirements.txt" ]; then
    error "requirements.txt not found in $PROJECT_DIR"
fi

info "Installing Python dependencies (this may take a minute)..."
"$VENV_PIP" install -r "$PROJECT_DIR/requirements.txt" --quiet
success "All dependencies installed"

# ── 6. Make app executable ───────────────────────────────────────────────────
info "Setting permissions on LineBot.app..."
if [ -f "$APP_EXEC" ]; then
    chmod +x "$APP_EXEC"
    success "LineBot.app is executable"
else
    warn "LineBot.app/Contents/MacOS/LineBot not found — skipping chmod"
fi

# ── 7. Remove macOS quarantine flag (so it opens without Gatekeeper warning) ─
if [ -d "$APP_BUNDLE" ]; then
    xattr -rd com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true
    success "Quarantine flag removed"
fi

# ── 8. Create data directory if missing ──────────────────────────────────────
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/logs"
success "data/ and logs/ directories ready"

# ── 9. Offer to copy app to /Applications ───────────────────────────────────
echo ""
read -rp "  Copy LineBot.app to /Applications? (y/N) " COPY_APP
if [[ "$COPY_APP" =~ ^[Yy]$ ]]; then
    if cp -R "$APP_BUNDLE" /Applications/; then
        success "LineBot.app copied to /Applications"
    else
        warn "Could not copy to /Applications (try with sudo if needed)"
    fi
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   Done! Double-click LineBot.app to launch   ║"
echo "  ║   (or open /Applications/LineBot.app)        ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

read -rp "  Launch LINE Bot now? (Y/n) " LAUNCH
if [[ ! "$LAUNCH" =~ ^[Nn]$ ]]; then
    open "$APP_BUNDLE"
fi
