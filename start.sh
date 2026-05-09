#!/usr/bin/env bash
# start.sh — LINE Bot quick launcher for macOS / Linux
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

VENV_PY=".venv/bin/python"

if [ ! -f "$VENV_PY" ]; then
    echo ""
    echo "  First run detected — running setup..."
    echo ""
    bash scripts/setup_mac.sh
    exit 0
fi

# macOS: tkinter needs a framework Python that actually has _tkinter built in.
if [[ "$(uname)" == "Darwin" ]]; then
    VENV_SITE=$("$VENV_PY" -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || true)

    FRAMEWORK_PY=$("$VENV_PY" - <<'PYEOF' 2>/dev/null
import sysconfig, os, glob, subprocess, sys

def has_tk(py):
    try:
        r = subprocess.run([py, '-c', 'import _tkinter'],
                           capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

# 1. Try the framework matching the venv's own Python version first
prefix = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX") or ""
candidate = os.path.join(prefix, "Resources/Python.app/Contents/MacOS/Python")
if os.path.isfile(candidate) and has_tk(candidate):
    print(candidate)
    sys.exit(0)

# 2. Search cellar — prefer version that matches venv Python
ver = f"python@{sys.version_info.major}.{sys.version_info.minor}"
patterns = [
    f"/opt/homebrew/Cellar/{ver}/*/Frameworks/Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python",
    f"/usr/local/Cellar/{ver}/*/Frameworks/Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python",
    "/opt/homebrew/Cellar/python@3.*/*/Frameworks/Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python",
    "/usr/local/Cellar/python@3.*/*/Frameworks/Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python",
    "/Library/Frameworks/Python.framework/Versions/3.*/Resources/Python.app/Contents/MacOS/Python",
]
for p in patterns:
    for match in sorted(glob.glob(p)):
        if has_tk(match):
            print(match)
            sys.exit(0)
PYEOF
    )

    if [ -n "$FRAMEWORK_PY" ] && [ -f "$FRAMEWORK_PY" ] && [ -n "$VENV_SITE" ]; then
        echo "  Using framework Python: $FRAMEWORK_PY"
        exec env PYTHONPATH="$VENV_SITE" "$FRAMEWORK_PY" launcher/launcher.py
    fi

    echo "  Warning: no framework Python with tkinter found, trying venv Python..."
fi

exec "$VENV_PY" launcher/launcher.py
