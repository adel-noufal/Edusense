@echo off
setlocal
cd /d "%~dp0"

echo [1/5] Running backend diagnostic doctor...
cd backend
.venv\Scripts\python.exe -m app.tools.doctor
if errorlevel 1 exit /b 1

echo [2/5] Running backend tests...
REM pytest.ini already sets -q; a second -q makes it -qq and hides the pass/fail summary.
.venv\Scripts\python.exe -m pytest -m "not live_provider"
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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$patterns = '(AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,}|nvidia_[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,})'; $files = git --no-pager grep -n -i -E $patterns -- . ':!*.lock' ':!backend/tests/*' ':!backend/test_*' ':!*.example' ':!.env' 2>$null; if ($LASTEXITCODE -eq 1) { exit 0 }; if ($files) { Write-Output $files; exit 1 }"
if errorlevel 1 exit /b 1

echo [6/9] Scanning all tracked files for UTF-8 mojibake...
backend\.venv\Scripts\python.exe scripts\mojibake_scan.py
if errorlevel 1 exit /b 1

echo [7/9] Checking pytest collection...
cd backend
.venv\Scripts\python.exe -m pytest --collect-only -q > ..\logs\pytest-collect.txt 2>&1
if errorlevel 1 (
  type ..\logs\pytest-collect.txt
  exit /b 1
)
cd ..

echo [8/9] Starting servers and checking logs, KB, ffprobe and the model dropdown...
backend\.venv\Scripts\python.exe scripts\verify_extras.py
if errorlevel 1 exit /b 1

echo [9/9] Walking through the instructor flow in a real browser (U1 modal, U2 UTC times)...
backend\.venv\Scripts\python.exe backend\tests\walkthrough_addendum13.py
if errorlevel 1 exit /b 1

echo.
echo VERIFY PASSED
