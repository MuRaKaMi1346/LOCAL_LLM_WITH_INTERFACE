@echo off
setlocal enabledelayedexpansion
set PYTHONUTF8=1
cd /d "%~dp0"

echo.
echo  +--------------------------------------------------+
echo  ^|          LINE Bot  --  Starting                 ^|
echo  +--------------------------------------------------+
echo.

:: ── Detect winget ─────────────────────────────────────────────────────────────
set "HAS_WINGET=0"
winget --version >nul 2>&1
if not errorlevel 1 set "HAS_WINGET=1"

:: ══════════════════════════════════════════════════════════════════════════════
:: 1. Python
:: ══════════════════════════════════════════════════════════════════════════════
python --version >nul 2>&1
if not errorlevel 1 goto :python_ok

echo  [INFO] Python not found -- installing Python 3.12...
echo.

if "%HAS_WINGET%"=="1" (
    winget install -e --id Python.Python.3.12 ^
        --accept-source-agreements --accept-package-agreements --scope user
) else (
    echo  [INFO] Downloading Python 3.12 installer...
    powershell -NoProfile -Command ^
        "Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' ^
         -OutFile '%TEMP%\py_setup.exe' -UseBasicParsing"
    echo  [INFO] Installing Python (please wait)...
    start /wait %TEMP%\py_setup.exe /passive PrependPath=1 Include_pip=1 Include_launcher=0
    del /q %TEMP%\py_setup.exe 2>nul
)

:: Try to add newly-installed Python to PATH for this session
for /f "delims=" %%d in ('dir /b /ad "%LOCALAPPDATA%\Programs\Python\Python3*" 2^>nul') do (
    if not defined PY_NEW set "PY_NEW=%LOCALAPPDATA%\Programs\Python\%%d"
)
if defined PY_NEW set "PATH=%PY_NEW%;%PY_NEW%\Scripts;%PATH%"

python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Python installed. Please CLOSE this window, then run start.bat again.
    echo.
    pause
    exit /b 0
)

:python_ok
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  [OK] Python %PY_VER%

:: ══════════════════════════════════════════════════════════════════════════════
:: 2. Ollama
:: ══════════════════════════════════════════════════════════════════════════════
ollama --version >nul 2>&1
if not errorlevel 1 goto :ollama_ok

echo  [INFO] Ollama not found -- installing...
echo.

if "%HAS_WINGET%"=="1" (
    winget install -e --id Ollama.Ollama ^
        --accept-source-agreements --accept-package-agreements
) else (
    echo  [INFO] Downloading Ollama installer...
    powershell -NoProfile -Command ^
        "Invoke-WebRequest 'https://ollama.com/download/OllamaSetup.exe' ^
         -OutFile '%TEMP%\OllamaSetup.exe' -UseBasicParsing"
    echo  [INFO] Installing Ollama (please wait)...
    start /wait %TEMP%\OllamaSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
    del /q %TEMP%\OllamaSetup.exe 2>nul
)

:: Add Ollama to PATH for this session if needed
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
)

ollama --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Ollama installed. Please CLOSE this window, then run start.bat again.
    echo.
    pause
    exit /b 0
)

:ollama_ok
echo  [OK] Ollama ready

:: ══════════════════════════════════════════════════════════════════════════════
:: 3. ngrok (optional — for public webhook URL)
:: ══════════════════════════════════════════════════════════════════════════════
ngrok --version >nul 2>&1
if not errorlevel 1 goto :ngrok_ok

echo  [INFO] ngrok not found -- installing...
if "%HAS_WINGET%"=="1" (
    winget install -e --id Ngrok.Ngrok ^
        --accept-source-agreements --accept-package-agreements
) else (
    echo  [INFO] Downloading ngrok...
    powershell -NoProfile -Command ^
        "Invoke-WebRequest 'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip' ^
         -OutFile '%TEMP%\ngrok.zip' -UseBasicParsing; ^
         Expand-Archive '%TEMP%\ngrok.zip' -DestinationPath '%LOCALAPPDATA%\ngrok' -Force"
    del /q %TEMP%\ngrok.zip 2>nul
    set "PATH=%LOCALAPPDATA%\ngrok;%PATH%"
)
if exist "%LOCALAPPDATA%\ngrok\ngrok.exe" set "PATH=%LOCALAPPDATA%\ngrok;%PATH%"

:ngrok_ok
ngrok --version >nul 2>&1
if not errorlevel 1 (
    echo  [OK] ngrok ready
) else (
    echo  [OK] ngrok skipped ^(optional — bot works without it^)
)

:: ══════════════════════════════════════════════════════════════════════════════
:: 4. Virtual environment
:: ══════════════════════════════════════════════════════════════════════════════
if not exist ".venv\Scripts\python.exe" (
    echo  Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :fail
    echo  [OK] Virtual environment created.
) else (
    echo  [OK] Virtual environment ready.
)

:: ══════════════════════════════════════════════════════════════════════════════
:: 5. Dependencies
:: ══════════════════════════════════════════════════════════════════════════════
echo  Checking dependencies (first run may take a minute)...
.venv\Scripts\pip install -r requirements.txt -q
if errorlevel 1 goto :fail
echo  [OK] All dependencies installed.

:: ══════════════════════════════════════════════════════════════════════════════
:: 6. Launch GUI
:: ══════════════════════════════════════════════════════════════════════════════
echo  Launching LINE Bot...
echo.
.venv\Scripts\python.exe launcher.py
if errorlevel 1 goto :fail
exit /b 0

:: ── Error handler ──────────────────────────────────────────────────────────────
:fail
echo.
echo  --------------------------------------------------
echo  Something went wrong. Read the error above.
echo  Fix it, then double-click start.bat again.
echo  --------------------------------------------------
echo.
cmd /k
