@echo off
setlocal enabledelayedexpansion
set PYTHONUTF8=1
cd /d "%~dp0"

echo.
echo  +--------------------------------------------------+
echo  ^|   LINE Bot  ^|  Starting...               ^|
echo  +--------------------------------------------------+
echo.

:: ── 1. Check Python ───────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo.
    echo  Please install Python 3.10 or newer:
    echo  https://www.python.org/downloads/
    echo  Check "Add Python to PATH" during install.
    goto :fail
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  [OK] Python %PY_VER%

:: ── 2. Create virtual environment (first time only) ───────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo  Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        goto :fail
    )
    echo  [OK] Virtual environment created.
) else (
    echo  [OK] Virtual environment ready.
)

:: ── 3. Install / update dependencies ─────────────────────────────────────────
echo  Checking dependencies (first run may take a minute)...
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Failed to install dependencies.
    goto :fail
)
echo  [OK] All dependencies installed.

:: ── 4. Launch GUI ─────────────────────────────────────────────────────────────
echo  Launching LINE Bot...
echo.
.venv\Scripts\python.exe launcher.py
if errorlevel 1 goto :fail
exit /b 0

:: ── Error handler (window stays open so you can read the error) ───────────────
:fail
echo.
echo  --------------------------------------------------
echo  Something went wrong. Read the error above.
echo  Fix it, then double-click start.bat again.
echo  --------------------------------------------------
echo.
cmd /k
