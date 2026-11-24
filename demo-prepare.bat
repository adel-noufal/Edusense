@echo off
REM demo-prepare.bat - one command before the demo.
REM   * starts backend + frontend (start-all.bat)
REM   * waits for /health
REM   * preloads the local Ollama models with keep_alive so the first question is fast
REM   * prints provider health
REM   * opens the login page
setlocal
cd /d "%~dp0"

echo [demo] starting services ...
call start-all.bat
if errorlevel 1 echo [demo] start-all reported a problem; continuing to health check.

echo [demo] waiting for the backend /health ...
powershell -NoProfile -Command ^
  "$ok=$false; for($i=0;$i -lt 60;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing http://localhost:8000/health -TimeoutSec 3; if($r.StatusCode -eq 200){ Write-Host ('[demo] /health 200 after ' + $i + 's'); $ok=$true; break } } catch {} ; Start-Sleep -Seconds 1 }; if(-not $ok){ Write-Host '[demo] /health did not answer in 60s'; exit 1 }"

echo [demo] preloading local models (keep_alive 30m) ...
for %%m in (llama3.2:latest qwen2.5:latest) do (
  curl -s -o nul -X POST http://localhost:11434/api/generate -d "{\"model\":\"%%m\",\"prompt\":\"hi\",\"stream\":false,\"options\":{\"num_predict\":1},\"keep_alive\":\"30m\"}"
  echo [demo]   %%m ready
)

echo [demo] provider status (masked) ...
cd backend
.venv\Scripts\python.exe scripts\llm_diagnostic.py --json 2>nul | .venv\Scripts\python.exe -c "import json,sys; d=json.load(sys.stdin); [print('  %-11s ready=%s cooling=%s' % (p['provider'], p.get('ready'), p.get('cooling_down'))) for p in d['providers']]"
cd ..

echo [demo] opening the login page ...
start "" http://localhost:5173/login

echo [demo] ready. Instructor: instructor@edusense.local / Password123
exit /b 0
