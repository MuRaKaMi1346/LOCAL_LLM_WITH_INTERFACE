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
APP_BUNDLE="$PROJECT_DIR/launcher/LineBot.app"
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
# Always activate Homebrew PATH first (Apple Silicon: /opt/homebrew, Intel: /usr/local)
# This ensures 'brew' is available even if the user's shell profile isn't set up yet.
for _BREW_PREFIX in /opt/homebrew /usr/local; do
    if [[ -f "${_BREW_PREFIX}/bin/brew" ]]; then
        eval "$("${_BREW_PREFIX}/bin/brew" shellenv)"
        break
    fi
done

if ! command -v brew &>/dev/null; then
    info "Homebrew not found — installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    for _BREW_PREFIX in /opt/homebrew /usr/local; do
        if [[ -f "${_BREW_PREFIX}/bin/brew" ]]; then
            eval "$("${_BREW_PREFIX}/bin/brew" shellenv)"
            break
        fi
    done
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

# ── Homebrew expat shim (pyexpat / xml fix) ──────────────────────────────────
# Python 3.12 Homebrew bottles reference _XML_SetAllocTrackerAct from expat 2.6+
# but macOS system libexpat is older and missing the symbol.
# Setting DYLD_LIBRARY_PATH makes the dynamic linker prefer Homebrew expat.
_EXPAT_LIB="$(brew --prefix expat 2>/dev/null)/lib"
if [[ -d "$_EXPAT_LIB" ]]; then
    export DYLD_LIBRARY_PATH="${_EXPAT_LIB}:${DYLD_LIBRARY_PATH:-}"
fi

# ── Python native-module health check ────────────────────────────────────────
info "Verifying Python native modules (expat, ssl)..."
if ! "$PYTHON" -c "import xml.parsers.expat, ssl" 2>/dev/null; then
    _PY_MINOR=$("$PYTHON" -c \
        'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' \
        2>/dev/null || echo "3.12")
    warn "Python native modules broken (expat/ssl mismatch)"
    info "Trying brew reinstall python@${_PY_MINOR}..."
    brew reinstall "python@${_PY_MINOR}" 2>/dev/null || true
    export PATH="$(brew --prefix "python@${_PY_MINOR}" 2>/dev/null)/bin:$PATH"
    # Remove any stale venv built with broken Python
    if [ -d "$VENV_DIR" ]; then
        warn "Removing stale .venv..."
        rm -rf "$VENV_DIR"
    fi
    # Final check
    if ! "$PYTHON" -c "import xml.parsers.expat, ssl" 2>/dev/null; then
        error "Python still broken after reinstall.
  Fix manually:
    brew reinstall expat
    export DYLD_LIBRARY_PATH=\"\$(brew --prefix expat)/lib\"
    rm -rf '${VENV_DIR}'
  Then run this script again.
  Or install Python from https://www.python.org/downloads/ (bundles its own expat)."
    fi
    success "Python modules OK after reinstall"
else
    success "Python native modules OK"
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
# 4. Ollama (install + start + pull models)
# ══════════════════════════════════════════════════════════════════════════════
info "Checking Ollama..."
"$PYTHON" "$SCRIPT_DIR/ollama_setup.py" --install --start --pull-models

# ══════════════════════════════════════════════════════════════════════════════
# 5. ngrok (optional — for public webhook URL)
# ══════════════════════════════════════════════════════════════════════════════
info "Checking ngrok..."
if command -v ngrok &>/dev/null; then
    success "ngrok already installed ($(ngrok --version 2>/dev/null | head -1))"
else
    info "ngrok not found — installing via Homebrew..."
    brew install --cask ngrok 2>/dev/null \
        || brew install ngrok/ngrok/ngrok 2>/dev/null \
        || { warn "ngrok install failed — skipped (bot works without it)"; true; }
    command -v ngrok &>/dev/null \
        && success "ngrok installed" \
        || warn "ngrok skipped (optional — bot works without it)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 6. git  (required for auto-update)
# ══════════════════════════════════════════════════════════════════════════════
info "Checking git..."
if command -v git &>/dev/null; then
    success "git $(git --version | awk '{print $NF}')"
else
    info "git not found — installing via Xcode Command Line Tools / Homebrew..."
    xcode-select --install 2>/dev/null || brew install git
    command -v git &>/dev/null \
        && success "git installed" \
        || warn "git install may need a Terminal restart"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 7. Virtual environment
# ══════════════════════════════════════════════════════════════════════════════
if [ -d "$VENV_DIR" ]; then
    info "Virtual environment already exists — skipping creation"
else
    info "Creating virtual environment..."
    # Homebrew Python often ships without ensurepip → fall back to --without-pip
    "$PYTHON" -m venv "$VENV_DIR" 2>/tmp/_venv_err || {
        warn "ensurepip unavailable (Homebrew Python) — retrying with --without-pip"
        rm -rf "$VENV_DIR"
        "$PYTHON" -m venv --without-pip "$VENV_DIR"
    }
    rm -f /tmp/_venv_err
    success "Virtual environment created"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# Bootstrap pip when ensurepip was unavailable
if [ ! -f "$VENV_PIP" ]; then
    info "Bootstrapping pip via get-pip.py..."
    if curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/_get_pip.py \
            && "$VENV_PY" /tmp/_get_pip.py --quiet; then
        rm -f /tmp/_get_pip.py
        success "pip bootstrapped"
    else
        rm -f /tmp/_get_pip.py
        warn "pip bootstrap failed"
        _PY_MINOR=$("$PYTHON" -c \
            'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' \
            2>/dev/null || echo "3.12")
        error "Python appears broken (expat/ssl mismatch). Fix with:
  brew reinstall python@${_PY_MINOR}
  rm -rf '${VENV_DIR}'
Then run this script again."
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# 8. Dependencies
# ══════════════════════════════════════════════════════════════════════════════
info "Upgrading pip..."
"$VENV_PY" -m pip install --upgrade pip --quiet
success "pip up to date"

info "Installing Python dependencies (this may take a minute)..."
"$VENV_PIP" install -r "$PROJECT_DIR/requirements.txt" --quiet
success "All dependencies installed"

# ══════════════════════════════════════════════════════════════════════════════
# 9. LineBot.app permissions
# ══════════════════════════════════════════════════════════════════════════════
if [ -f "$APP_EXEC" ]; then
    chmod +x "$APP_EXEC"
    xattr -rd com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true
    success "LineBot.app ready"
else
    warn "LineBot.app not found — skipping (you can still use: bash start.sh)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 10. Create directories
# ══════════════════════════════════════════════════════════════════════════════
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/logs" "$PROJECT_DIR/custom"
success "data/, logs/, and custom/ directories ready"

# ══════════════════════════════════════════════════════════════════════════════
# 11. Copy to /Applications (optional)
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
        "$VENV_PY" "$PROJECT_DIR/launcher/launcher.py"
    fi
fi
