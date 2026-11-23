"""
EduSense Backend Launcher
- Detects and kills orphan/stale python processes on target port if any
- Tests real socket bind() starting from port 8000 up to 8020
- Automatically selects the first bindable port
- Writes active port to backend/.active_port and frontend/.env.local
- Launches uvicorn with explicit project venv python
- Maximum 3 retries with clear human-readable error messages on failure
"""
import os
import sys
import time
import socket
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BACKEND_DIR.parent
PORT_FILE = BACKEND_DIR / ".active_port"
ENV_LOCAL_FILE = ROOT_DIR / "frontend" / ".env.local"
MAX_RETRIES = 3


def is_port_bindable(host: str, port: int) -> bool:
    """Test if a socket can truly be bound and listened on."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
        s.listen(1)
        s.close()
        return True
    except Exception:
        return False


def kill_stale_process_on_port(port: int):
    """Find and kill any stale python process bound to port on Windows."""
    if os.name != "nt":
        return
    try:
        out = subprocess.check_output(f'netstat -ano | findstr ":{port} "', shell=True, text=True)
        pids = set()
        for line in out.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 5:
                pid = parts[-1]
                if pid.isdigit() and int(pid) > 0 and int(pid) != os.getpid():
                    pids.add(pid)
        for pid in pids:
            try:
                proc_info = subprocess.check_output(f"tasklist /FI \"PID eq {pid}\" /FO CSV /NH", shell=True, text=True)
                if "python" in proc_info.lower():
                    print(f"[LAUNCHER] Reclaiming port {port}: terminating orphaned python PID {pid}...")
                    subprocess.run(f"taskkill /PID {pid} /F", shell=True, capture_output=True)
                    time.sleep(1)
            except Exception:
                pass
    except Exception:
        pass


def find_free_port(start_port: int = 8000, max_ports: int = 20) -> int:
    """Find first free port starting at start_port."""
    # Port 0 means "let the OS choose" to bind(), which silently moved the API
    # to a random port and broke the frontend proxy and every verify step.
    if start_port <= 0:
        start_port = 8000
    for p in range(start_port, start_port + max_ports):
        kill_stale_process_on_port(p)
        if is_port_bindable("127.0.0.1", p):
            return p
    raise RuntimeError(f"Unable to find an open port in range {start_port}-{start_port + max_ports}")


def save_active_port(port: int):
    """Save active port to backend/.active_port and frontend/.env.local."""
    try:
        PORT_FILE.write_text(str(port).strip(), encoding="utf-8")
        print(f"[LAUNCHER] Active port saved to {PORT_FILE.name}: {port}")
    except Exception as e:
        print(f"[WARN] Failed to write {PORT_FILE}: {e}")

    try:
        ENV_LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        content = f"VITE_API_URL=http://localhost:{port}/api\nVITE_BACKEND_PORT={port}\n"
        ENV_LOCAL_FILE.write_text(content, encoding="utf-8")
        print(f"[LAUNCHER] Synced frontend configuration in {ENV_LOCAL_FILE.name}")
    except Exception as e:
        print(f"[WARN] Failed to write {ENV_LOCAL_FILE}: {e}")


def ensure_local_models():
    """Start Ollama if it is installed and not running so offline routing works."""
    try:
        from app.tools.ollama_boot import ensure_ollama
        info = ensure_ollama()
        if info["running"]:
            print(f"[LAUNCHER] Ollama online ({len(info['models'])} local models)")
        else:
            print(f"[LAUNCHER] Ollama offline: {info['hint']}")
    except Exception as exc:
        print(f"[LAUNCHER] Ollama check skipped: {exc}")


def run_server():
    os.chdir(BACKEND_DIR)
    ensure_local_models()

    # Ensure venv python is used
    venv_python = BACKEND_DIR / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if not venv_python.exists():
        venv_python = Path(sys.executable)

    try:
        preferred_port = int(os.environ.get("PORT", "8000") or 8000)
    except ValueError:
        preferred_port = 8000
    if preferred_port <= 0:
        preferred_port = 8000

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            port = find_free_port(preferred_port)
            save_active_port(port)

            print("=" * 60)
            print(f"  EduSense AI Education Platform - Backend")
            print(f"  Port:     http://localhost:{port}")
            print(f"  API Docs: http://localhost:{port}/docs")
            print(f"  Health:   http://localhost:{port}/health")
            print(f"  Python:   {venv_python}")
            print("=" * 60)

            # Use uvicorn directly
            cmd = [
                str(venv_python),
                "-m", "uvicorn",
                "app.main:app",
                "--host", "127.0.0.1",
                "--port", str(port),
            ]
            # If developer requested reload explicitly
            if os.environ.get("EDUSENSE_RELOAD", "").lower() in ("1", "true"):
                cmd.append("--reload")

            result = subprocess.run(cmd)
            if result.returncode == 0:
                print("[LAUNCHER] Server exited normally.")
                sys.exit(0)
            else:
                print(f"[LAUNCHER] Server exited with code {result.returncode} (Attempt {attempt}/{MAX_RETRIES})")
                time.sleep(2)
        except Exception as e:
            print(f"[LAUNCHER ERROR] Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            time.sleep(2)

    print("\n" + "!" * 60)
    print("FATAL: Backend server failed to start after 3 attempts.")
    print("Troubleshooting steps:")
    print("1. Check Windows Firewall or security software blocking python.exe socket bindings.")
    print("2. Run 'python -m app.tools.doctor' to diagnose environment, DB, and dependencies.")
    print("3. Check for zombie python processes: taskkill /F /IM python.exe")
    print("!" * 60)
    sys.exit(1)


if __name__ == "__main__":
    run_server()
