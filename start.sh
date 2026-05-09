#!/usr/bin/env bash
# start.sh — LINE Bot quick launcher for macOS / Linux
# First run: bash start.sh  (triggers setup automatically)
# After that: bash start.sh  or double-click LineBot.app
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

exec "$VENV_PY" launcher.py
