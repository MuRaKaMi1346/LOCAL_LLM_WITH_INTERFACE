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

# macOS: tkinter needs the real Python.app framework executable.
# Ask the venv Python itself where its framework lives.
if [[ "$(uname)" == "Darwin" ]]; then
    FRAMEWORK_PY=$("$VENV_PY" - <<'PYEOF' 2>/dev/null
import sysconfig, os, sys
prefix = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX") or ""
candidate = os.path.join(prefix, "Resources/Python.app/Contents/MacOS/Python")
if os.path.isfile(candidate):
    print(candidate)
else:
    # fallback: try cellar glob
    import glob
    patterns = [
        "/opt/homebrew/Cellar/python@3.*/*/Frameworks/Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python",
        "/usr/local/Cellar/python@3.*/*/Frameworks/Python.framework/Versions/*/Resources/Python.app/Contents/MacOS/Python",
    ]
    for p in patterns:
        matches = sorted(glob.glob(p), reverse=True)
        if matches:
            print(matches[0])
            break
PYEOF
    )

    VENV_SITE=$("$VENV_PY" -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || true)

    if [ -n "$FRAMEWORK_PY" ] && [ -f "$FRAMEWORK_PY" ] && [ -n "$VENV_SITE" ]; then
        echo "  Using framework Python: $FRAMEWORK_PY"
        exec env PYTHONPATH="$VENV_SITE" "$FRAMEWORK_PY" launcher/launcher.py
    fi
fi

exec "$VENV_PY" launcher/launcher.py
