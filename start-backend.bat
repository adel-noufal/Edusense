@echo off
title EduSense Backend Server
echo ============================================
echo   EduSense AI Education Platform - Backend
echo ============================================
echo.

cd /d "%~dp0backend"

if not exist .env (
    echo [INFO] .env not found, copying from .env.example...
    copy .env.example .env
)

if not exist .venv (
    echo [INFO] Creating virtual environment and installing dependencies...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
    if not exist .venv\Scripts\uvicorn.exe (
        echo [INFO] Installing requirements...
        pip install -r requirements.txt
    )
)

set PORT=8000
netstat -ano | findstr ":%PORT% " | findstr LISTENING >nul 2>&1
if %ERRORLEVEL%==0 (
    echo [WARN] Port %PORT% is already in use. Trying port 8001...
    set PORT=8001
    netstat -ano | findstr ":%PORT% " | findstr LISTENING >nul 2>&1
    if %ERRORLEVEL%==0 (
        echo [ERROR] Port 8001 is also in use. Close other servers or run:
        echo        netstat -ano ^| findstr :8000
        echo        taskkill /PID ^<pid^> /F
        pause
        exit /b 1
    )
)

echo.
echo [OK] Backend:  http://localhost:%PORT%
echo [OK] API Docs: http://localhost:%PORT%/docs
echo [OK] Health:   http://localhost:%PORT%/health
if not "%PORT%"=="8000" (
    echo.
    echo [WARN] Using port %PORT%. Set VITE_API_URL in frontend/.env:
    echo        VITE_API_URL=http://localhost:%PORT%/api
)
echo.
echo [INFO] Server will auto-restart on file changes or crashes
echo.

:restart
.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port %PORT% --reload
echo [WARN] Server stopped, restarting in 3 seconds...
timeout /t 3 /nobreak >nul
goto restart
