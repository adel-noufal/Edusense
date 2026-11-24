@echo off
REM rollback.bat - return the working tree to the last demo tag, safely.
REM
REM Never resets without a backup: the current work is first moved onto a
REM timestamped branch, then the tree is restored to the requested tag.
REM
REM   rollback.bat              -> roll back to the newest demo-* tag
REM   rollback.bat demo-step-2  -> roll back to a specific tag
setlocal enabledelayedexpansion

cd /d "%~dp0"

set TARGET=%~1
if "%TARGET%"=="" (
  for /f "delims=" %%t in ('git tag --list "demo-*" --sort=-creatordate') do (
    set TARGET=%%t
    goto :got
  )
)
:got
if "%TARGET%"=="" (
  echo [rollback] No demo-* tag found. Nothing to roll back to.
  exit /b 1
)

for /f "delims=" %%c in ('git rev-parse --short HEAD') do set HEAD_SHA=%%c
for /f "tokens=1-3 delims=/-. " %%a in ("%DATE%") do set D=%%c%%b%%a
for /f "tokens=1-2 delims=:." %%a in ("%TIME%") do set T=%%a%%b
set SAFE_BRANCH=backup-before-rollback-%D%-%T:-=%

echo [rollback] HEAD is %HEAD_SHA%, target tag is %TARGET%
git stash list >nul 2>&1
if not errorlevel 1 (
  git diff --quiet
  if errorlevel 1 (
    echo [rollback] Saving uncommitted changes to %SAFE_BRANCH%
    git checkout -b %SAFE_BRANCH%
    git add -A
    git commit -m "WIP saved by rollback.bat before returning to %TARGET%"
  )
)

echo [rollback] Switching to %TARGET% ...
git checkout -B demo-rollback %TARGET%
if errorlevel 1 (
  echo [rollback] Checkout failed. Your previous branch still has everything.
  exit /b 1
)

echo [rollback] Done. Tree now matches %TARGET%.
echo [rollback] Recover the pre-rollback state with: git checkout %SAFE_BRANCH%
exit /b 0
