@echo off
setlocal
cd /d "%~dp0"

echo [1/5] Running backend diagnostic doctor...
cd backend
.venv\Scripts\python.exe -m app.tools.doctor
if errorlevel 1 exit /b 1

echo [2/5] Running backend tests...
.venv\Scripts\python.exe -m pytest -q -m "not live_provider"
if errorlevel 1 exit /b 1

echo [3/5] Running live layout and emotion Playwright check...
.venv\Scripts\python.exe tests/test_live_layout_emotion.py
if errorlevel 1 exit /b 1
cd ..

echo [4/5] Building frontend...
cd frontend
call npm run build
if errorlevel 1 exit /b 1
cd ..

echo [5/5] Scanning tracked files and worktree for credential patterns...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$patterns = '(AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,}|nvidia_[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,})'; $files = git --no-pager grep -n -i -E $patterns -- . ':!*.lock' ':!backend/test_*' ':!*.example' ':!.env' 2>$null; if ($LASTEXITCODE -eq 1) { exit 0 }; if ($files) { Write-Output $files; exit 1 }"
if errorlevel 1 exit /b 1

echo.
echo VERIFY PASSED
