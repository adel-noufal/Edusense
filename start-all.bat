@echo off
setlocal enabledelayedexpansion
title EduSense - Start All
cd /d "%~dp0"

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
echo [2/7] Installing Python dependencies (pinned)...
if exist "%~dp0backend\requirements.lock" (
    "%PY%" -m pip install -q --disable-pip-version-check -r "%~dp0backend\requirements.lock"
) else (
    "%PY%" -m pip install -q --disable-pip-version-check -r "%~dp0backend\requirements.txt"
)
if errorlevel 1 (
    echo [ERROR] Python dependency installation failed. The exact error is printed above.
    pause
    exit /b 1
)

if not exist "%~dp0backend\.env" (
    copy "%~dp0backend\.env.example" "%~dp0backend\.env" >nul
    echo [INFO] Created backend\.env from .env.example (no API keys yet: AI uses Ollama if installed).
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
    echo         Read the "EduSense API" window: it prints the exact reason (busy port, DB error, ...).
    pause
    exit /b 1
)
echo [OK] API healthy on http://127.0.0.1:!PORT!

echo.
echo [6/7] Starting the frontend...
pushd "%~dp0frontend"
if not exist "node_modules" (
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
