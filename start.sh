#!/usr/bin/env bash
# start.sh — LINE Bot GUI launcher for macOS / Linux
# On macOS: finds a framework Python for stable tkinter (no blinking).
# If no framework Python is found: falls back to headless server mode (start_mac.sh).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Homebrew PATH (MUST come first, before any `brew` call) ──────────────────
# Apple Silicon: /opt/homebrew  |  Intel: /usr/local
for _BREW_PREFIX in /opt/homebrew /usr/local; do
    if [[ -f "${_BREW_PREFIX}/bin/brew" ]]; then
        eval "$("${_BREW_PREFIX}/bin/brew" shellenv)" 2>/dev/null || true
        break
    fi
done
unset _BREW_PREFIX

# ── Prefer Homebrew expat over system expat ───────────────────────────────────
# Fixes: "Symbol not found: _XML_SetAllocTrackerAct" on macOS with Homebrew Python.
# Note: DYLD_LIBRARY_PATH is stripped by SIP only for system binaries (/usr/bin etc.).
# Homebrew Python and Python.org Python are NOT system binaries, so this works.
if command -v brew &>/dev/null; then
    _EXPAT_LIB="$(brew --prefix expat 2>/dev/null || echo '')/lib"
    [[ -d "$_EXPAT_LIB" ]] && export DYLD_LIBRARY_PATH="${_EXPAT_LIB}:${DYLD_LIBRARY_PATH:-}"
    unset _EXPAT_LIB
fi

VENV_PY="$SCRIPT_DIR/.venv/bin/python"

# ── git pull (auto-update — uses the current tracked remote branch) ───────────
if command -v git &>/dev/null; then
    git pull --ff-only 2>/dev/null || true
fi

# ── First run ─────────────────────────────────────────────────────────────────
if [ ! -f "$VENV_PY" ]; then
    echo ""
    echo "  First run detected — running setup..."
    echo ""
    bash "$SCRIPT_DIR/scripts/setup_mac.sh"
    exit 0
fi

# ── Ollama: auto-start + auto-pull models ─────────────────────────────────────
"$VENV_PY" "$SCRIPT_DIR/scripts/ollama_setup.py" --start --pull-models 2>/dev/null || true

# ── macOS: tkinter requires a framework Python ────────────────────────────────
if [[ "$(uname)" == "Darwin" ]]; then

    VENV_SITE=$("$VENV_PY" -c \
        "import site; print(site.getsitepackages()[0])" 2>/dev/null || true)

    # ── helper: if $1 has _tkinter, exec it with venv packages ───────────────
    # Never returns if exec succeeds; returns 0 if check fails (safe fall-through).
    _launch_if_tk() {
        local py="$1"
        [[ -x "$py" ]] || return 0
        env PYTHONPATH="${VENV_SITE}" "$py" -c "import _tkinter" 2>/dev/null \
            || return 0
        echo "  ✓ Using: $py"
        # Pass DYLD_LIBRARY_PATH explicitly so the expat fix survives exec.
        exec env \
            PYTHONPATH="${VENV_SITE}" \
            DYLD_LIBRARY_PATH="${DYLD_LIBRARY_PATH:-}" \
            "$py" "$SCRIPT_DIR/launcher/launcher.py" \
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
    unset _FRAMEWORK_PY

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
    exec bash "$SCRIPT_DIR/start_mac.sh"
fi

# ── Linux / other ─────────────────────────────────────────────────────────────
exec "$VENV_PY" "$SCRIPT_DIR/launcher/launcher.py"
