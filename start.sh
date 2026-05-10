#!/usr/bin/env bash
# start.sh — LINE Bot GUI launcher for macOS / Linux
# On macOS: finds a framework Python for stable tkinter (no blinking).
# If no framework Python is found: falls back to headless server mode (start_mac.sh).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# Prefer Homebrew expat over system expat (fixes pyexpat Symbol not found on macOS)
_EXPAT_LIB="$(brew --prefix expat 2>/dev/null)/lib"
[[ -d "$_EXPAT_LIB" ]] && export DYLD_LIBRARY_PATH="${_EXPAT_LIB}:${DYLD_LIBRARY_PATH:-}"
unset _EXPAT_LIB

VENV_PY=".venv/bin/python"

# ── git pull (auto-update code) ──────────────────────────────────────────────
command -v git &>/dev/null && git pull --ff-only origin main 2>/dev/null || true

# ── Ollama models (pull if missing — only runs once per model) ────────────────
if command -v ollama &>/dev/null; then
    for _M in llama3.2 nomic-embed-text; do
        if [ ! -d "$HOME/.ollama/models/manifests/registry.ollama.ai/library/${_M}" ]; then
            echo "  [Ollama] Pulling ${_M} (first time)..."
            ollama pull "$_M" 2>/dev/null || true
        fi
    done
    unset _M
fi

# ── First run ─────────────────────────────────────────────────────────────────
if [ ! -f "$VENV_PY" ]; then
    echo ""
    echo "  First run detected — running setup..."
    echo ""
    bash scripts/setup_mac.sh
    exit 0
fi

# ── macOS: tkinter requires a framework Python ────────────────────────────────
if [[ "$(uname)" == "Darwin" ]]; then

    VENV_SITE=$("$VENV_PY" -c \
        "import site; print(site.getsitepackages()[0])" 2>/dev/null || true)

    # ── helper: if $1 has _tkinter, exec it with venv packages ───────────────
    # Returns normally (0) if check fails; never returns if exec succeeds.
    _launch_if_tk() {
        local py="$1"
        [[ -x "$py" ]] || return 0
        env PYTHONPATH="${VENV_SITE}" "$py" -c "import _tkinter" 2>/dev/null \
            || return 0
        echo "  ✓ Using: $py"
        exec env PYTHONPATH="${VENV_SITE}" "$py" launcher/launcher.py \
            || return 0   # exec failed (very rare) — fall through
    }

    # ── 1. pythonw / pythonw3 — provided by Python.org installer ─────────────
    for _pw in pythonw3 pythonw; do
        if command -v "$_pw" &>/dev/null; then
            _launch_if_tk "$(command -v "$_pw")"
        fi
    done

    # ── 2. Python.org framework at standard system path ───────────────────────
    for _fw in /Library/Frameworks/Python.framework/Versions/3.*/Resources/Python.app/Contents/MacOS/Python; do
        [[ -f "$_fw" ]] && _launch_if_tk "$_fw"
    done

    # ── 3. Homebrew cellar framework Python (matches venv version first) ──────
    _FRAMEWORK_PY=$("$VENV_PY" - 2>/dev/null <<'PYEOF' || true
import sysconfig, os, glob, subprocess, sys

def has_tk(py):
    try:
        return subprocess.run(
            [py, '-c', 'import _tkinter'],
            capture_output=True, timeout=5
        ).returncode == 0
    except Exception:
        return False

# Try the framework linked to the venv's own Python first
prefix = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX") or ""
c = os.path.join(prefix, "Resources/Python.app/Contents/MacOS/Python")
if os.path.isfile(c) and has_tk(c):
    print(c); sys.exit(0)

# Scan Homebrew cellar (version-matched first, then any 3.x)
ver = f"python@{sys.version_info.major}.{sys.version_info.minor}"
patterns = [
    f"/opt/homebrew/Cellar/{ver}/*/Frameworks/Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python",
    f"/usr/local/Cellar/{ver}/*/Frameworks/Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python",
    "/opt/homebrew/Cellar/python@3.*/*/Frameworks/Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python",
    "/usr/local/Cellar/python@3.*/*/Frameworks/Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python",
]
for pat in patterns:
    for match in sorted(glob.glob(pat)):
        if has_tk(match):
            print(match); sys.exit(0)
PYEOF
    )
    [[ -n "$_FRAMEWORK_PY" ]] && _launch_if_tk "$_FRAMEWORK_PY"

    # ── 4. Fallback: headless server + Admin Panel in browser ─────────────────
    echo ""
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║  ⚠  ไม่พบ framework Python ที่รองรับ tkinter GUI    ║"
    echo "  ║  ↳  เปิดแอพในโหมดเซิร์ฟเวอร์ + เบราว์เซอร์แทน    ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "  หากต้องการ GUI ให้ติดตั้ง Python จาก https://python.org"
    echo "  แล้วลบ .venv และรัน setup อีกครั้ง: bash scripts/setup_mac.sh"
    echo ""
    exec bash start_mac.sh
fi

# ── Linux / other ─────────────────────────────────────────────────────────────
exec "$VENV_PY" launcher/launcher.py
