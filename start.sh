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

# macOS: tkinter requires a framework Python build.
# Find one and inject venv packages via PYTHONPATH.
if [[ "$(uname)" == "Darwin" ]]; then
    VENV_SITE="$("$VENV_PY" -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)"
    FRAMEWORK_PY=""
    for candidate in \
        "/opt/homebrew/opt/python@3.13/Frameworks/Python.framework/Versions/3.13/bin/python3.13" \
        "/opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/bin/python3.12" \
        "/opt/homebrew/opt/python@3.11/Frameworks/Python.framework/Versions/3.11/bin/python3.11" \
        "/usr/local/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/bin/python3.12" \
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12" \
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11" \
    ; do
        if [ -f "$candidate" ]; then
            FRAMEWORK_PY="$candidate"
            break
        fi
    done

    if [ -n "$FRAMEWORK_PY" ] && [ -n "$VENV_SITE" ]; then
        exec env PYTHONPATH="$VENV_SITE" "$FRAMEWORK_PY" launcher/launcher.py
    fi
fi

exec "$VENV_PY" launcher/launcher.py
