"""Detect and start the local Ollama daemon (no pulls, no installs)."""
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

CANDIDATES = [
    Path(r"D:\Ollama\ollama.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
    Path(r"C:\Program Files\Ollama\ollama.exe"),
]


def ollama_base() -> str:
    raw = os.environ.get("EDUSENSE_OLLAMA_URL", "http://localhost:11434")
    return raw.split("/api")[0].rstrip("/")


def is_running(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{ollama_base()}/api/tags", timeout=timeout) as resp:
            json.loads(resp.read().decode("utf-8"))
        return True
    except Exception:
        return False


def installed_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{ollama_base()}/api/tags", timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def find_ollama() -> str | None:
    """PATH first, then the usual Windows install folders."""
    found = shutil.which("ollama")
    if found:
        return found
    for path in CANDIDATES:
        if str(path) and path.is_file():
            return str(path)
    return None


def ensure_ollama(wait_seconds: float = 25.0, log=print) -> dict:
    """Return {running, started, binary, models, hint}. Starts 'ollama serve' if needed."""
    if is_running():
        return {"running": True, "started": False, "binary": find_ollama(),
                "models": installed_models(), "hint": ""}

    binary = find_ollama()
    if not binary:
        hint = ("Ollama is not installed or not on PATH. Install it from https://ollama.com/download "
                "or start D:\\Ollama\\ollama.exe, then reload.")
        log(f"[OLLAMA] not found (PATH, D:\\Ollama, %LOCALAPPDATA%\\Programs\\Ollama). {hint}")
        return {"running": False, "started": False, "binary": None, "models": [], "hint": hint}

    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen([binary, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
        log(f"[OLLAMA] started {binary} serve")
    except Exception as exc:
        hint = f"Could not start Ollama ({exc}). Run \"{binary} serve\" manually, then reload."
        log(f"[OLLAMA] {hint}")
        return {"running": False, "started": False, "binary": binary, "models": [], "hint": hint}

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if is_running(timeout=1.0):
            models = installed_models()
            log(f"[OLLAMA] online with {len(models)} local models")
            return {"running": True, "started": True, "binary": binary, "models": models, "hint": ""}
        time.sleep(1.0)

    hint = f"Ollama did not answer on {ollama_base()} within {int(wait_seconds)}s after start."
    log(f"[OLLAMA] {hint}")
    return {"running": False, "started": True, "binary": binary, "models": [], "hint": hint}
