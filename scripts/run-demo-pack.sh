#!/bin/bash
cd "$(dirname "$0")/.."
# 1. API (fresh process on 8000 only if the port is free)
curl -s --max-time 3 -o /dev/null http://127.0.0.1:8000/api/health || {
  cd backend
  EDUSENSE_DISABLE_PROVIDERS=gemini .venv/Scripts/python.exe -u -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > ../logs/api-demo.log 2>&1 &
  cd ..
  for i in $(seq 1 40); do
    sleep 2
    curl -s --max-time 3 -o /dev/null http://127.0.0.1:8000/api/health && break
  done
}
echo "API health: $(curl -s --max-time 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/health)"
cd backend
.venv/Scripts/python.exe -u ../scripts/demo_pack.py http://127.0.0.1:8000 2>&1 | tee ../logs/demo-pack.log
.venv/Scripts/python.exe -u /tmp/mkvideo.py 2>&1 | tee ../logs/demo-video.log
echo "PACK DONE $(date +%H:%M:%S)"
