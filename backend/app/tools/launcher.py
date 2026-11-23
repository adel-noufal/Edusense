"""EduSense Backend Launcher

- Terminates stray EduSense uvicorn servers from earlier runs (any port, including
  the legacy `--port 0` ones that bound a random port)
- Picks the first port that is genuinely free: exclusive bind on Windows plus a
  real connect() probe, because SO_REUSEADDR reports a busy port as free there
- Writes the active port to backend/.active_port and frontend/.env.local
- Launches uvicorn with the project venv python, retrying on a new port
"""
import os
import re
import subprocess
import sys
import time
import socket
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BACKEND_DIR.parent
PORT_FILE = BACKEND_DIR / ".active_port"
ENV_LOCAL_FILE = ROOT_DIR / "frontend" / ".env.local"
MAX_RETRIES = 3
SERVER_MODULE = "app.main:app"


def log(message: str) -> None:
    print(message, flush=True)


def run(cmd: list[str], timeout: float = 30.0) -> str:
    """Run a command without a shell, so Git Bash cannot rewrite `/FI` style args."""
    try:
        return subprocess.check_output(cmd, text=True, errors="ignore", timeout=timeout)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Process and port discovery
# ---------------------------------------------------------------------------

def is_port_bindable(host: str, port: int) -> bool:
    """Test if a socket can truly be bound and listened on.

    On Windows SO_REUSEADDR lets a probe bind a port another process is still
    listening on, so the old probe reported a busy port as free and uvicorn then
    died with WinError 10048. SO_EXCLUSIVEADDRUSE makes the probe refuse a port
    that is still held, which is what a server launch needs.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == "nt":
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
        s.listen(1)
        return True
    except OSError:
        return False
    finally:
        s.close()


def port_has_listener(port: int, host: str = "127.0.0.1") -> bool:
    """True when something accepts TCP connections on the port right now."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.4)
    try:
        return probe.connect_ex((host, port)) == 0
    finally:
        probe.close()


def port_is_free(port: int) -> bool:
    return not port_has_listener(port) and is_port_bindable("127.0.0.1", port)


def wait_until_free(port: int, timeout: float = 10.0) -> bool:
    """A killed process releases its socket a moment later; wait for that."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_is_free(port):
            return True
        time.sleep(0.2)
    return False


def _listening_pids(port: int) -> set[int]:
    """PIDs in LISTENING state on the port, parsed from netstat in Python."""
    pids: set[int] = set()
    for line in run(["netstat", "-ano"]).splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[-1].isdigit():
            local, state, pid = parts[1], parts[3].upper(), int(parts[-1])
            if state != "LISTENING" or pid <= 0 or pid == os.getpid():
                continue
            if local.rsplit(":", 1)[-1] == str(port):
                pids.add(pid)
    return pids


def _image_name(pid: int) -> str:
    out = run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]).strip()
    if not out or out.upper().startswith("INFO:"):
        return ""
    return out.split(",")[0].strip('"').lower()


def project_server_pids() -> list[int]:
    """Every uvicorn process serving this project, whatever port it holds.

    netstat hides the owner PID for some listeners on this host, so the command
    line is the reliable signal. Launchers themselves are not matched.
    """
    if os.name != "nt":
        return []
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'app.main:app' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=45)
    pids = []
    for token in out.split():
        if token.strip().isdigit():
            pid = int(token.strip())
            if pid != os.getpid():
                pids.append(pid)
    return pids


def terminate_stale_project_servers() -> None:
    """Kill earlier EduSense API servers so exactly one binds the preferred port."""
    pids = project_server_pids()
    if not pids:
        return
    log(f"[LAUNCHER] Stopping {len(pids)} stale EduSense server process(es): {pids}")
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, text=True, errors="ignore")
    deadline = time.time() + 12.0
    while time.time() < deadline and project_server_pids():
        time.sleep(0.3)


def kill_stale_process_on_port(port: int) -> None:
    """Kill a python/uvicorn process still listening on the port; a foreign
    listener is left alone, and find_free_port moves on instead."""
    if os.name != "nt":
        return
    for pid in _listening_pids(port):
        if _image_name(pid) not in ("python.exe", "pythonw.exe", "uvicorn.exe"):
            continue
        log(f"[LAUNCHER] Reclaiming port {port}: terminating orphaned python PID {pid}...")
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, text=True, errors="ignore")
    wait_until_free(port, timeout=8.0)


def find_free_port(start_port: int = 8000, max_ports: int = 20, skip: set[int] | None = None) -> int:
    """First port that is free right now."""
    # Port 0 means "let the OS choose" to bind(), which silently moved the API
    # to a random port and broke the frontend proxy and every verify step.
    if start_port <= 0:
        start_port = 8000
    skip = skip or set()
    for p in range(start_port, start_port + max_ports):
        if p in skip:
            continue
        kill_stale_process_on_port(p)
        if port_is_free(p):
            return p
    raise RuntimeError(f"Unable to find an open port in range {start_port}-{start_port + max_ports}")


# ---------------------------------------------------------------------------
# Configuration hand-off
# ---------------------------------------------------------------------------

def save_active_port(port: int) -> None:
    """Save active port to backend/.active_port and frontend/.env.local."""
    try:
        PORT_FILE.write_text(str(port).strip(), encoding="utf-8")
        log(f"[LAUNCHER] Active port saved to {PORT_FILE.name}: {port}")
    except Exception as e:
        log(f"[WARN] Failed to write {PORT_FILE}: {e}")

    try:
        ENV_LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        content = f"VITE_API_URL=http://localhost:{port}/api\nVITE_BACKEND_PORT={port}\n"
        ENV_LOCAL_FILE.write_text(content, encoding="utf-8")
        log(f"[LAUNCHER] Synced frontend configuration in {ENV_LOCAL_FILE.name}")
    except Exception as e:
        log(f"[WARN] Failed to write {ENV_LOCAL_FILE}: {e}")


def ensure_local_models():
    """Start Ollama if it is installed and not running so offline routing works."""
    try:
        from app.tools.ollama_boot import ensure_ollama
        info = ensure_ollama()
        if info["running"]:
            log(f"[LAUNCHER] Ollama online ({len(info['models'])} local models)")
        else:
            log(f"[LAUNCHER] Ollama offline: {info['hint']}")
    except Exception as exc:
        log(f"[LAUNCHER] Ollama check skipped: {exc}")


def preferred_port() -> int:
    raw = (os.environ.get("PORT") or "8000").strip()
    if not re.fullmatch(r"\d+", raw):
        return 8000
    port = int(raw)
    return port if 1 <= port <= 65535 else 8000


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_server():
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    os.chdir(BACKEND_DIR)
    ensure_local_models()

    venv_python = BACKEND_DIR / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if not venv_python.exists():
        venv_python = Path(sys.executable)

    start_port = preferred_port()
    raw_port = (os.environ.get("PORT") or "").strip()
    if raw_port and (not raw_port.isdigit() or int(raw_port) <= 0):
        log(f"[LAUNCHER] Ignoring PORT={raw_port} (a random port broke the frontend); using {start_port}.")

    # One EduSense API server at a time: earlier runs (including the legacy
    # `--port 0` ones) are stopped before this one binds.
    terminate_stale_project_servers()

    tried: set[int] = set()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # A port that just failed to bind is not retried: a second attempt on
            # it only reproduces WinError 10048.
            port = find_free_port(start_port, skip=tried)
            tried.add(port)
            save_active_port(port)

            log("=" * 60)
            log("  EduSense AI Education Platform - Backend")
            log(f"  Port:     http://localhost:{port}")
            log(f"  API Docs: http://localhost:{port}/docs")
            log(f"  Health:   http://localhost:{port}/health")
            log(f"  Python:   {venv_python}")
            log("=" * 60)

            cmd = [
                str(venv_python), "-u", "-m", "uvicorn",
                SERVER_MODULE,
                "--host", "127.0.0.1",
                "--port", str(port),
            ]
            if os.environ.get("EDUSENSE_RELOAD", "").lower() in ("1", "true"):
                cmd.append("--reload")

            result = subprocess.run(cmd)
            if result.returncode == 0:
                log("[LAUNCHER] Server exited normally.")
                sys.exit(0)
            log(f"[LAUNCHER] Server exited with code {result.returncode} (Attempt {attempt}/{MAX_RETRIES})")
            time.sleep(2)
        except Exception as e:
            log(f"[LAUNCHER ERROR] Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            time.sleep(2)

    log("\n" + "!" * 60)
    log("FATAL: Backend server failed to start after 3 attempts.")
    log("Troubleshooting steps:")
    log("1. Check Windows Firewall or security software blocking python.exe socket bindings.")
    log("2. Run 'python -m app.tools.doctor' to diagnose environment, DB, and dependencies.")
    log("3. Check for zombie python processes: tasklist | findstr python")
    log("!" * 60)
    sys.exit(1)


if __name__ == "__main__":
    run_server()
