@echo off
setlocal enabledelayedexpansion
set PYTHONUTF8=1
cd /d "%~dp0"

:: ══════════════════════════════════════════════════════════════════════════════
:: 1. Python  (terminal only stays open if Python is missing)
:: ══════════════════════════════════════════════════════════════════════════════
python --version >nul 2>&1
if not errorlevel 1 goto :python_ok

echo.
echo  +--------------------------------------------------+
echo  ^|  LINE Bot needs Python 3.10+                    ^|
echo  +--------------------------------------------------+
echo.

set "HAS_WINGET=0"
winget --version >nul 2>&1
if not errorlevel 1 set "HAS_WINGET=1"

if "%HAS_WINGET%"=="1" (
    echo  Installing Python 3.12 via winget...
    winget install -e --id Python.Python.3.12 ^
        --accept-source-agreements --accept-package-agreements --scope user
) else (
    echo  Downloading Python 3.12 installer...
    powershell -NoProfile -Command ^
        "Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' ^
         -OutFile '%TEMP%\py_setup.exe' -UseBasicParsing"
    start /wait %TEMP%\py_setup.exe /passive PrependPath=1 Include_pip=1 Include_launcher=0
    del /q %TEMP%\py_setup.exe 2>nul
)

for /f "delims=" %%d in ('dir /b /ad "%LOCALAPPDATA%\Programs\Python\Python3*" 2^>nul') do (
    if not defined PY_NEW set "PY_NEW=%LOCALAPPDATA%\Programs\Python\%%d"
)
if defined PY_NEW set "PATH=%PY_NEW%;%PY_NEW%\Scripts;%PATH%"

python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Python installed. Close this window and run start.bat again.
    echo.
    pause
    exit /b 0
)

:python_ok

:: ══════════════════════════════════════════════════════════════════════════════
:: 1b. Desktop shortcut (created once — runs immediately after Python confirmed)
:: ══════════════════════════════════════════════════════════════════════════════
set "_LNK=%USERPROFILE%\Desktop\LINE Bot.lnk"
set "_BAT=%~f0"
if not exist "%_LNK%" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell;$s=$ws.CreateShortcut($env:_LNK);$s.TargetPath=$env:_BAT;$s.WorkingDirectory=[IO.Path]::GetDirectoryName($env:_BAT);$s.Description='LINE Bot Controller';$s.WindowStyle=1;$s.Save()" >nul 2>&1
    echo.
    echo   [Shortcut] Desktop shortcut created.
)
set "_LNK=" & set "_BAT="

:: ══════════════════════════════════════════════════════════════════════════════
:: 1c. git pull  (auto-update code)
:: ══════════════════════════════════════════════════════════════════════════════
git --version >nul 2>&1
if not errorlevel 1 (
    git pull --ff-only >nul 2>&1
)

:: ══════════════════════════════════════════════════════════════════════════════
:: 2. Ollama  (auto-install, auto-start, auto-pull models)
:: ══════════════════════════════════════════════════════════════════════════════
python scripts\ollama_setup.py --install --start --pull-models

:: ══════════════════════════════════════════════════════════════════════════════
:: 3. ngrok  (silent — winget only)
:: ══════════════════════════════════════════════════════════════════════════════
ngrok --version >nul 2>&1
if errorlevel 1 (
    set "HAS_WINGET=0"
    winget --version >nul 2>&1
    if not errorlevel 1 set "HAS_WINGET=1"
    if "!HAS_WINGET!"=="1" (
        start /b "" winget install -e --id Ngrok.Ngrok ^
            --accept-source-agreements --accept-package-agreements >nul 2>&1
    )
)

:: ══════════════════════════════════════════════════════════════════════════════
:: 4. Virtual environment  (silent)
:: ══════════════════════════════════════════════════════════════════════════════
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv >nul 2>&1
)

:: ══════════════════════════════════════════════════════════════════════════════
:: 5. Launch setup GUI — handles pip install + launches the main app
::    Using pythonw.exe so NO console window appears
:: ══════════════════════════════════════════════════════════════════════════════
if exist ".venv\Scripts\pythonw.exe" (
    start "" .venv\Scripts\pythonw.exe launcher\setup_gui.py
) else (
    start "" pythonw launcher\setup_gui.py
)
