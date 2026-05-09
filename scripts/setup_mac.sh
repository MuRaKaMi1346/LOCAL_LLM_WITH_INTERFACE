#!/usr/bin/env bash
# ============================================================
#  setup_mac.sh — One-time setup for LINE Bot on macOS
#  Installs: Homebrew, Python 3.12, tkinter, Ollama, venv, deps
#
#  Run once:  bash scripts/setup_mac.sh
#  After that: bash start.sh  OR  double-click LineBot.app
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

# ══════════════════════════════════════════════════════════════════════════════
# 1. Homebrew
# ══════════════════════════════════════════════════════════════════════════════
if ! command -v brew &>/dev/null; then
    info "Homebrew not found — installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Activate brew for this session (Apple Silicon path first, then Intel)
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -f /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    success "Homebrew installed"
else
    success "Homebrew $(brew --version | head -1)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 2. Python 3.10+
# ══════════════════════════════════════════════════════════════════════════════
info "Checking Python version..."

PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON="$(command -v "$cmd")"
            success "Python $VER found at $PYTHON"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    info "Python 3.10+ not found — installing Python 3.12 via Homebrew..."
    brew install python@3.12
    # Activate for this session
    export PATH="$(brew --prefix python@3.12)/bin:$PATH"
    PYTHON="$(command -v python3.12 2>/dev/null || command -v python3)"
    success "Python 3.12 installed"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 3. tkinter
# ══════════════════════════════════════════════════════════════════════════════
info "Checking tkinter..."
if ! "$PYTHON" -c "import tkinter" 2>/dev/null; then
    info "tkinter not found — installing..."
    PY_VER_SHORT=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    brew install "python-tk@${PY_VER_SHORT}" 2>/dev/null \
        || brew install python-tk 2>/dev/null \
        || true
    if ! "$PYTHON" -c "import tkinter" 2>/dev/null; then
        warn "tkinter still missing. Try: brew install python-tk"
        warn "Or use the official installer from https://www.python.org/downloads/ (includes Tk)"
        read -rp "  Continue anyway? (y/N) " CONT
        [[ "$CONT" =~ ^[Yy]$ ]] || exit 1
    else
        success "tkinter OK"
    fi
else
    success "tkinter OK"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 4. Ollama
# ══════════════════════════════════════════════════════════════════════════════
info "Checking Ollama..."
if command -v ollama &>/dev/null; then
    success "Ollama already installed ($(ollama --version 2>/dev/null | head -1 || echo 'version unknown'))"
else
    info "Ollama not found — installing via Homebrew..."
    brew install ollama
    success "Ollama installed"

    info "Starting Ollama service..."
    brew services start ollama 2>/dev/null || true
    sleep 2
    success "Ollama service started"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 5. Virtual environment
# ══════════════════════════════════════════════════════════════════════════════
if [ -d "$VENV_DIR" ]; then
    info "Virtual environment already exists — skipping creation"
else
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
    success "Virtual environment created"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ══════════════════════════════════════════════════════════════════════════════
# 6. Dependencies
# ══════════════════════════════════════════════════════════════════════════════
info "Upgrading pip..."
"$VENV_PY" -m pip install --upgrade pip --quiet
success "pip up to date"

info "Installing Python dependencies (this may take a minute)..."
"$VENV_PIP" install -r "$PROJECT_DIR/requirements.txt" --quiet
success "All dependencies installed"

# ══════════════════════════════════════════════════════════════════════════════
# 7. LineBot.app permissions
# ══════════════════════════════════════════════════════════════════════════════
if [ -f "$APP_EXEC" ]; then
    chmod +x "$APP_EXEC"
    xattr -rd com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true
    success "LineBot.app ready"
else
    warn "LineBot.app not found — skipping (you can still use: bash start.sh)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 8. Create directories
# ══════════════════════════════════════════════════════════════════════════════
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/logs"
success "data/ and logs/ directories ready"

# ══════════════════════════════════════════════════════════════════════════════
# 9. Copy to /Applications (optional)
# ══════════════════════════════════════════════════════════════════════════════
if [ -d "$APP_BUNDLE" ]; then
    echo ""
    read -rp "  Copy LineBot.app to /Applications? (y/N) " COPY_APP
    if [[ "$COPY_APP" =~ ^[Yy]$ ]]; then
        cp -R "$APP_BUNDLE" /Applications/ \
            && success "LineBot.app copied to /Applications" \
            || warn "Could not copy to /Applications (try: sudo cp -R LineBot.app /Applications/)"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# Done
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║   Setup complete!  🌸                            ║"
echo "  ║                                                  ║"
echo "  ║   เปิดแอพ:  bash start.sh                       ║"
echo "  ║   หรือ:     double-click LineBot.app            ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""

read -rp "  Launch LINE Bot now? (Y/n) " LAUNCH
if [[ ! "$LAUNCH" =~ ^[Nn]$ ]]; then
    if [ -d "$APP_BUNDLE" ]; then
        open "$APP_BUNDLE"
    else
        "$VENV_PY" "$PROJECT_DIR/launcher.py"
    fi
fi
