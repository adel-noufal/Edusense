"""Runtime checks for verify.bat: servers, logs, KB documents, MP4, dropdown.

Starts the backend itself when it is not answering, then checks:
1. /health answers
2. no Traceback in today's API logs
3. the knowledge base holds at least one document
4. the newest generated MP4 is valid per ffprobe
5. the model dropdown lists only discovered/working models
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "http://127.0.0.1:8000"
failures: list[str] = []


def http(path: str, token: str | None = None, timeout: float = 30):
    req = urllib.request.Request(API + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_until_up(seconds: int = 90) -> bool:
    for _ in range(seconds):
        try:
            http("/health", timeout=3)
            return True
        except Exception:
            time.sleep(1)
    return False


def ensure_backend() -> str | None:
    try:
        http("/health", timeout=3)
        print("[OK] backend already running")
    except Exception:
        print("[..] backend down, starting start-backend.bat")
        subprocess.Popen(["cmd", "/c", "start-backend.bat"], cwd=str(ROOT),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not wait_until_up(120):
            failures.append("backend did not answer /health within 120s")
            return None
        print("[OK] backend started by verify")
    try:
        login = urllib.request.Request(
            API + "/api/auth/login",
            data=json.dumps({"email": "instructor@edusense.local",
                             "password": "Password123"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(login, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")).get("access_token")
    except Exception as exc:
        failures.append(f"login failed: {exc}")
        return None


def check_logs() -> None:
    bad = []
    for log in sorted((ROOT / "logs").glob("api*.log")):
        if log.stat().st_mtime < time.time() - 6 * 3600:
            continue
        text = log.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"Traceback \(most recent call last\)", text):
            tail = text[match.start():match.start() + 240].splitlines()
            bad.append(f"{log.name}: {tail[-1] if tail else 'Traceback'}")
    if bad:
        failures.append("Traceback in logs: " + "; ".join(bad[:3]))
        for item in bad[:5]:
            print("[FAIL] traceback", item)
    else:
        print("[OK] no Traceback in recent API logs")


def check_kb(token: str | None) -> None:
    if not token:
        return
    try:
        sources = http("/api/rag/sources", token=token, timeout=60)
    except Exception as exc:
        failures.append(f"KB sources failed: {exc}")
        print(f"[FAIL] KB sources: {exc}")
        return
    count = len(sources) if isinstance(sources, list) else len(sources.get("sources") or [])
    if count <= 0:
        failures.append(f"knowledge base has {count} documents")
        print(f"[FAIL] KB documents: {count}")
    else:
        print(f"[OK] KB documents: {count}")


def check_mp4() -> None:
    from app.services.binaries import find_ffprobe
    videos = sorted((BACKEND / "app" / "static" / "videos").glob("video-*.mp4"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    videos = [v for v in videos if v.stat().st_size > 1024]
    ffprobe = find_ffprobe()
    if not videos:
        failures.append("no generated MP4 found")
        print("[FAIL] no generated MP4 found")
        return
    if not ffprobe:
        failures.append("ffprobe missing")
        print("[FAIL] ffprobe missing")
        return
    latest = videos[0]
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                          "format=duration", "-of", "json", str(latest)],
                         capture_output=True, text=True, timeout=60)
    try:
        duration = float(json.loads(out.stdout)["format"]["duration"])
    except Exception:
        duration = 0.0
    if duration <= 1:
        failures.append(f"{latest.name} failing ffprobe ({out.stderr[:120]})")
        print(f"[FAIL] ffprobe {latest.name}: {out.stderr[:160]}")
    else:
        print(f"[OK] ffprobe {latest.name}: {duration:.1f}s, {latest.stat().st_size // 1024} KB")


def check_dropdown(token: str | None) -> None:
    if not token:
        return
    try:
        data = http("/api/ai/available-models", token=token)
    except Exception as exc:
        failures.append(f"available-models failed: {exc}")
        return
    models = data.get("models") if isinstance(data, dict) else data
    names = [m.get("id") or m.get("name") or str(m) for m in (models or [])]
    dead = [n for n in names if any(k in n for k in (
        "llama-3.3-70b-versatile", "llama-3.1-8b-instant",
        "meta/llama-3.3-70b-instruct", "gemini-2.0-flash-exp",
        "deepseek-r1:free"))]
    if not names:
        failures.append("dropdown is empty")
        print("[FAIL] dropdown empty")
    elif dead:
        failures.append(f"dropdown lists dead models: {dead[:3]}")
        print(f"[FAIL] dropdown dead models: {dead[:3]}")
    else:
        print(f"[OK] dropdown: {len(names)} models, ollama_running={data.get('ollama_running')}")


def main() -> int:
    token = ensure_backend()
    check_logs()
    check_kb(token)
    check_mp4()
    check_dropdown(token)
    if failures:
        print("VERIFY EXTRAS FAILED")
        for item in failures:
            print(" -", item)
        return 1
    print("VERIFY EXTRAS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
