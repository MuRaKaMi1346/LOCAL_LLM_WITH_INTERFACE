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
:: 2. Ollama  (silent — install in background if winget available)
:: ══════════════════════════════════════════════════════════════════════════════
ollama --version >nul 2>&1
if errorlevel 1 (
    set "HAS_WINGET=0"
    winget --version >nul 2>&1
    if not errorlevel 1 set "HAS_WINGET=1"
    if "!HAS_WINGET!"=="1" (
        start /b "" winget install -e --id Ollama.Ollama ^
            --accept-source-agreements --accept-package-agreements >nul 2>&1
    ) else (
        powershell -NoProfile -WindowStyle Hidden -Command ^
            "Invoke-WebRequest 'https://ollama.com/download/OllamaSetup.exe' -OutFile '%TEMP%\OllamaSetup.exe' -UseBasicParsing; Start-Process '%TEMP%\OllamaSetup.exe' '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -Wait; Remove-Item '%TEMP%\OllamaSetup.exe' -Force -ErrorAction SilentlyContinue" >nul 2>&1
    )
)

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
