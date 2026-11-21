@echo off
setlocal enabledelayedexpansion
title EduSense Platform Launcher
echo ============================================
echo   EduSense AI Education Platform - Start All
echo ============================================
echo.

cd /d "%~dp0"

echo [STEP 1/4] Running diagnostic doctor...
cd backend
.venv\Scripts\python.exe -m app.tools.doctor
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARN] Doctor reported some warnings or issues. Proceeding with launch...
)
cd ..

echo.
echo [STEP 2/4] Starting backend server in separate window...
start "EduSense Backend" cmd /c "start-backend.bat"

echo.
echo [STEP 3/4] Waiting for backend to become healthy...
set PORT=8000
if exist "backend\.active_port" (
    set /p PORT=<backend\.active_port
)

set HEALTH_OK=0
for /l %%i in (1,1,25) do (
    if !HEALTH_OK!==0 (
        if exist "backend\.active_port" (
            set /p PORT=<backend\.active_port
        )
        curl.exe -s http://127.0.0.1:!PORT!/health >nul 2>&1
        if !ERRORLEVEL!==0 (
            set HEALTH_OK=1
            echo [OK] Backend is healthy on port !PORT!
        ) else (
            <nul set /p=.
            timeout /t 1 /nobreak >nul
        )
    )
)

if !HEALTH_OK!==0 (
    echo.
    echo [WARN] Backend did not respond within 25 seconds on port !PORT!. Check backend window.
)

echo.
echo [STEP 4/4] Starting frontend server...
cd frontend
if not exist node_modules (
    echo [INFO] Installing frontend dependencies...
    call npm install
)
start "EduSense Frontend" cmd /c "npm run dev"
cd ..

echo.
echo [INFO] Waiting 3 seconds for Vite server...
timeout /t 3 /nobreak >nul

echo [INFO] Opening EduSense in your browser...
start http://localhost:5173

echo.
echo ============================================
echo   EduSense is running!
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:!PORT!
echo ============================================
pause
