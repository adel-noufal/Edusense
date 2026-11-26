@echo off
title EduSense Frontend Server
echo ============================================
echo   EduSense AI Education Platform - Frontend
echo ============================================
echo.

cd /d "%~dp0frontend"

:: Install node_modules if missing
if not exist node_modules (
    echo [INFO] node_modules not found. Installing dependencies...
    npm install
)

echo.
echo [OK] Starting Vite dev server on http://localhost:5173
echo.
echo [INFO] Server will auto-restart on file changes or crashes
echo.

:restart
npm run dev
echo [WARN] Server stopped, restarting in 3 seconds...
timeout /t 3 /nobreak >nul
goto restart
