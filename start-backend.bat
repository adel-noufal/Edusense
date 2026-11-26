@echo off
setlocal enabledelayedexpansion
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

if not exist .venv\Scripts\python.exe (
    echo [INFO] Creating virtual environment and installing dependencies...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
)

echo [INFO] Starting backend via launcher...
.venv\Scripts\python.exe -m app.tools.launcher

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Backend failed to start.
    echo Run: .venv\Scripts\python.exe -m app.tools.doctor to view diagnostic report.
    pause
    exit /b %ERRORLEVEL%
)
