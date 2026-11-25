@echo off
setlocal enabledelayedexpansion
title EduSense - Start All
cd /d "%~dp0"

rem ── Offline switch ─────────────────────────────────────────────────────
rem An OFFLINE file next to this script (or EDUSENSE_OFFLINE=1) makes every
rem child window refuse downloads: Hugging Face and pip use only local files.
set "OFFLINE_MODE=0"
if exist "%~dp0OFFLINE" set "OFFLINE_MODE=1"
if /i "%EDUSENSE_OFFLINE%"=="1" set "OFFLINE_MODE=1"
if "!OFFLINE_MODE!"=="1" (
    set "HF_HUB_OFFLINE=1"
    set "TRANSFORMERS_OFFLINE=1"
    set "HF_HUB_DISABLE_TELEMETRY=1"
    echo [MODE] Offline: no package or model downloads will be attempted.
)

echo ============================================================
echo   EduSense AI Education Platform - one-click start
echo ============================================================
echo.

echo [1/7] Checking prerequisites...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.11+ is not on PATH. Install it from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH", then run this file again.
    pause
    exit /b 1
)
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js 18+ is not on PATH. Install it from https://nodejs.org/ then run this file again.
    pause
    exit /b 1
)
where curl >nul 2>&1
if errorlevel 1 (
    echo [ERROR] curl.exe is missing. It ships with Windows 10 1803+; update Windows.
    pause
    exit /b 1
)

set "PY=%~dp0backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [INFO] Creating the backend virtual environment...
    python -m venv "%~dp0backend\.venv"
    if errorlevel 1 (
        echo [ERROR] Could not create backend\.venv
        pause
        exit /b 1
    )
)

echo.
echo [2/7] Checking Python dependencies (pinned)...
rem Flat goto-based flow: delayed expansion inside nested ( ) blocks is what
rem produced ". was unexpected at this time" on this machine.
set "LOCK=%~dp0backend\requirements.lock"
if exist "%LOCK%" goto :deps_hash
set "LOCK=%~dp0backend\requirements.txt"
:deps_hash
set "STAMP=%~dp0backend\.venv\.deps-ok"
set "LOCK_HASH="
for /f "delims=" %%h in ('certutil -hashfile "%LOCK%" SHA256 ^| findstr /r /c:"^[0-9a-f][0-9a-f]*$"') do call :take_hash "%%h"
if not exist "%STAMP%" goto :deps_install
set "STAMPED="
set /p STAMPED=<"%STAMP%"
if /i "%STAMPED%"=="%LOCK_HASH%" goto :deps_skip

:deps_install
echo [INFO] Installing pinned Python packages (the first run needs internet)...
if "%OFFLINE_MODE%"=="1" set "PIP_NO_INDEX=1"
"%PY%" -m pip install -q --disable-pip-version-check -r "%LOCK%"
if not errorlevel 1 goto :deps_stamp
"%PY%" -c "import fastapi, uvicorn, sqlalchemy, chromadb" >nul 2>&1
if not errorlevel 1 goto :deps_warn
echo [ERROR] The backend packages are missing and could not be installed.
echo         Connect to the internet once and run start-all.bat again.
pause
exit /b 1
:deps_warn
echo [WARN] Could not update the packages (offline?). Using what backend\.venv already has.
goto :deps_done
:deps_stamp
if defined LOCK_HASH >"%STAMP%" echo %LOCK_HASH%
goto :deps_done
:deps_skip
echo [SKIP] Python packages already match requirements.lock (no pip run).
:deps_done

rem ── Cache the embedding model once so the Knowledge Base works offline ──
if "%OFFLINE_MODE%"=="1" goto :model_done
"%PY%" -c "from pathlib import Path; from sentence_transformers import SentenceTransformer; p=Path(r'%~dp0backend\data\models'); p.mkdir(parents=True, exist_ok=True); SentenceTransformer('all-MiniLM-L6-v2', cache_folder=str(p))" >nul 2>&1
if errorlevel 1 echo [WARN] Embedding model not cached yet; the Knowledge Base will ask for one online start.
:model_done

if not exist "%~dp0backend\.env" (
    copy "%~dp0backend\.env.example" "%~dp0backend\.env" >nul
    echo [INFO] Created backend\.env from .env.example ^(no API keys yet: AI uses Ollama if installed^).
)

echo.
echo [3/7] Preparing the database...
pushd "%~dp0backend"
"%PY%" -m alembic upgrade head
if errorlevel 1 (
    echo [WARN] Alembic reported an error. The app still seeds its schema on startup; check the message above.
)
"%PY%" -c "from app.db.seed import init_db; init_db(seed=True)"
if errorlevel 1 (
    echo [ERROR] Database seeding failed. The exact error is printed above.
    popd
    pause
    exit /b 1
)
popd

echo.
echo [4/7] Starting the API (fixed port 8000, see backend\.env EDUSENSE_PORT)...
start "EduSense API" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m app.tools.launcher"

set "PORT=8000"
if exist "%~dp0backend\.active_port" set /p PORT=<"%~dp0backend\.active_port"

echo.
echo [5/7] Waiting for the API to answer on port !PORT! (up to 90 s)...
set "HEALTH_OK=0"
for /l %%i in (1,1,90) do (
    if "!HEALTH_OK!"=="0" (
        curl.exe -s -o nul --max-time 2 http://127.0.0.1:!PORT!/health
        if "!ERRORLEVEL!"=="0" (
            set "HEALTH_OK=1"
        ) else (
            <nul set /p=.
            timeout /t 1 /nobreak >nul
        )
    )
)
echo.
if "!HEALTH_OK!"=="0" (
    echo [ERROR] The API did not answer within 90 seconds.
    echo         Read the "EduSense API" window: it prints the exact reason ^(busy port, DB error, ...^).
    pause
    exit /b 1
)
echo [OK] API healthy on http://127.0.0.1:!PORT!

echo.
echo [6/7] Starting the frontend...
pushd "%~dp0frontend"
if not exist "node_modules" (
    if "!OFFLINE_MODE!"=="1" (
        echo [ERROR] frontend\node_modules is missing and this run is offline.
        echo         Run start-all.bat once with internet to install it, then the app works offline.
        popd
        pause
        exit /b 1
    )
    echo [INFO] Installing frontend dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed. The exact error is printed above.
        popd
        pause
        exit /b 1
    )
)
if /i not "%EDUSENSE_NO_BROWSER%"=="1" (
    start "EduSense Frontend" cmd /k "npm run dev -- --host localhost --port 5173"
)
popd

echo.
echo [7/7] Waiting for the web app and opening your browser...
for /l %%i in (1,1,45) do (
    curl.exe -s -o nul --max-time 2 http://localhost:5173/
    if "!ERRORLEVEL!"=="0" goto :open_browser
    <nul set /p=.
    timeout /t 1 /nobreak >nul
)
echo.
echo [WARN] The frontend did not answer yet. Check the "EduSense Frontend" window.
goto :done

:open_browser
echo.
start "" http://localhost:5173

:take_hash
if defined LOCK_HASH exit /b 0
set "LOCK_HASH=%~1"
exit /b 0

:done
echo.
echo ============================================================
echo   EduSense is running
echo   Web app: http://localhost:5173
echo   API:     http://localhost:!PORT!/docs
echo   Logs:    backend\logs\edusense.log
echo   Stop:    close the "EduSense API" and "EduSense Frontend" windows
echo ============================================================
pause
