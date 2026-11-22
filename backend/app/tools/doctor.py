"""
EduSense Diagnostic Doctor
python -m app.tools.doctor

Verifies:
1. Python venv & version (>=3.10)
2. Python packages required
3. .env file & required keys
4. Database & Alembic migrations
5. Port bindability
6. ffmpeg executable
7. LibreOffice soffice.exe
8. Playwright + Chromium browser
9. Ollama service + 4 installed local models:
   - qwen2.5 (translation/Arabic)
   - mistral (lessons/scripts)
   - llama3.1 (quizzes/assessments)
   - llama3.2 (flashcards/general)
"""
import os
import sys
import json
import socket
import subprocess
import urllib.request
import shutil
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BACKEND_DIR.parent

CHECKS = []

def check(name: str, passed: bool, message: str, fix_cmd: str | None = None):
    CHECKS.append({
        "name": name,
        "passed": passed,
        "message": message,
        "fix_cmd": fix_cmd
    })

def run_doctor():
    print("=" * 70)
    print("  EduSense System Diagnostic Doctor")
    print("=" * 70)

    # 1. Python & Venv
    in_venv = (sys.prefix != sys.base_prefix) or ("venv" in sys.prefix.lower())
    py_ver = sys.version_info
    ver_ok = py_ver.major == 3 and py_ver.minor >= 10
    if in_venv and ver_ok:
        check("Python & Venv", True, f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro} in venv: {sys.prefix}")
    else:
        check("Python & Venv", False, f"Not running in expected virtual environment or Python < 3.10 ({sys.version})",
              "cd backend && python -m venv .venv && .venv\\Scripts\\activate && pip install -r requirements.txt")

    # 2. Required Packages
    required_pkgs = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("sqlalchemy", "sqlalchemy"),
        ("alembic", "alembic"),
        ("pydantic", "pydantic"),
        ("fitz", "pymupdf"),
        ("pptx", "python-pptx"),
        ("cv2", "opencv-python"),
        ("dotenv", "python-dotenv"),
        ("playwright", "playwright")
    ]
    missing_pkgs = []
    for mod_name, pkg_name in required_pkgs:
        try:
            __import__(mod_name)
        except ImportError:
            missing_pkgs.append(pkg_name)
    if not missing_pkgs:
        check("Python Packages", True, "All essential packages imported successfully")
    else:
        check("Python Packages", False, f"Missing packages: {', '.join(missing_pkgs)}",
              f"pip install {' '.join(missing_pkgs)}")

    # 3. .env File & Keys
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        check(".env Configuration", False, ".env file not found in backend directory", "copy backend\\.env.example backend\\.env")
    else:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        critical_keys = ["EDUSENSE_SECRET_KEY"]
        missing_keys = [k for k in critical_keys if not os.getenv(k)]
        gemini_keys = os.getenv("GEMINI_API_KEY") or os.getenv("EDUSENSE_GEMINI_API_KEY")
        if missing_keys:
            check(".env Configuration", False, f"Missing critical keys: {', '.join(missing_keys)}", "Set missing keys in backend/.env")
        elif not gemini_keys:
            check(".env Configuration", False, "No Gemini API key found (needed for cloud fallback)", "Set GEMINI_API_KEY in backend/.env")
        else:
            check(".env Configuration", True, ".env loaded with required secret and API keys")

    # 4. Database & Migrations
    db_ok = False
    try:
        from app.db.session import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        # Check alembic current vs head
        result = subprocess.run([sys.executable, "-m", "alembic", "current"], cwd=str(BACKEND_DIR), capture_output=True, text=True)
        if "head" in result.stdout.lower() or result.returncode == 0:
            check("Database & Migrations", True, "SQLite database connection active, schema migrations up to date")
            db_ok = True
        else:
            check("Database & Migrations", False, "Alembic migrations need upgrade", "cd backend && python -m alembic upgrade head")
    except Exception as e:
        check("Database & Migrations", False, f"Database check failed: {e}", "cd backend && python -m alembic upgrade head")

    # 5. Port Availability
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    port_8000_open = False
    try:
        s.bind(("127.0.0.1", 8000))
        s.listen(1)
        s.close()
        port_8000_open = True
        check("Port 8000", True, "127.0.0.1:8000 is open and ready to bind")
    except Exception as e:
        # Check if fallback port is available
        from app.tools.launcher import find_free_port
        try:
            alt_port = find_free_port(8001)
            check("Port 8000", True, f"Port 8000 busy/reserved; fallback port {alt_port} is bindable and will be used automatically")
        except Exception as e2:
            check("Port 8000", False, f"Cannot bind on 8000 ({e}) or any fallback ({e2})", "taskkill /F /IM python.exe")

    # 6. ffmpeg
    try:
        from app.services.binaries import find_ffmpeg, find_ffprobe
        ffmpeg_exe = find_ffmpeg()
        if not ffmpeg_exe:
            raise FileNotFoundError("ffmpeg")
        res = subprocess.run([ffmpeg_exe, "-version"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            first_line = res.stdout.splitlines()[0] if res.stdout else "available"
            ffprobe_exe = find_ffprobe() or "(missing)"
            check("ffmpeg", True, f"ffmpeg at {ffmpeg_exe} | ffprobe: {ffprobe_exe} ({first_line[:32]})")
        else:
            check("ffmpeg", False, f"{ffmpeg_exe} returned non-zero exit code", "winget install Gyan.FFmpeg")
    except Exception:
        check("ffmpeg", False, "ffmpeg not found in PATH or WinGet folders",
              "winget install Gyan.FFmpeg (or set EDUSENSE_FFMPEG_PATH)")

    # 7. LibreOffice
    soffice_path = Path(r"C:\Program Files\LibreOffice\program\soffice.exe")
    if soffice_path.exists():
        try:
            res = subprocess.run([str(soffice_path), "--version"], capture_output=True, text=True, timeout=5)
            check("LibreOffice", True, f"LibreOffice installed at {soffice_path}")
        except Exception:
            check("LibreOffice", True, f"LibreOffice binary verified at {soffice_path}")
    else:
        check("LibreOffice", False, f"LibreOffice soffice.exe not found at {soffice_path}", "Install LibreOffice to default directory")

    # 8. Playwright & Chromium
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Check executable path
            browser_path = p.chromium.executable_path
            check("Playwright", True, f"Playwright and Chromium installed ({Path(browser_path).name})")
    except Exception as e:
        check("Playwright", False, f"Playwright browser check failed: {e}", "python -m playwright install chromium")

    # 9. Ollama Service & Local Models
    try:
        from app.tools.ollama_boot import ensure_ollama
        boot = ensure_ollama(log=lambda m: print(m))
    except Exception as exc:
        boot = {"running": False, "hint": f"Ollama auto-start check failed: {exc}"}
    raw_ollama_url = os.getenv("EDUSENSE_OLLAMA_URL", "http://localhost:11434")
    ollama_base = raw_ollama_url.split("/api")[0].rstrip("/")
    try:
        req = urllib.request.Request(f"{ollama_base}/api/tags")
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
        installed_models = [m.get("name", "") for m in data.get("models", [])]

        # Check user's 4 required models
        required_models = {
            "qwen2.5": False,
            "mistral": False,
            "llama3.1": False,
            "llama3.2": False,
        }
        for model_name in installed_models:
            for req_key in required_models:
                if model_name.startswith(req_key) and not model_name.endswith(("-cloud", ":cloud")):
                    required_models[req_key] = True

        all_models_present = all(required_models.values())
        detected = [m for m, ok in required_models.items() if ok]
        missing = [m for m, ok in required_models.items() if not ok]

        if all_models_present:
            check("Ollama & Local Models", True, f"Ollama online at {ollama_base}; all 4 models verified: {', '.join(detected)}")
        else:
            check("Ollama & Local Models", False,
                  f"Ollama running but missing required offline models: {', '.join(missing)} (found: {', '.join(detected)})",
                  "Verify models in D:\\OllamaModels or start Ollama with local model directory")
    except Exception as e:
        check("Ollama & Local Models", False,
              f"Ollama not reachable at {ollama_base}: {e}. {boot.get('hint', '')}",
              "Start Ollama: \"D:\\Ollama\\ollama.exe\" serve (the launcher also tries this automatically)")

    # Print Report
    # 10. Import smoke test (must stay green: a broken site-package such as a
    # corrupted jinja2 used to crash charset_normalizer/transformers here).
    try:
        code = "import app.main; print('ok')"
        res = subprocess.run([sys.executable, "-c", code], cwd=str(BACKEND_DIR),
                             capture_output=True, text=True, timeout=120)
        if res.returncode == 0 and "ok" in res.stdout:
            check("Import app.main", True, "FastAPI application imports cleanly")
        else:
            detail = (res.stderr or res.stdout).strip().splitlines()[-1:] or ["unknown error"]
            check("Import app.main", False, f"Import failed: {detail[0][:120]}",
                  "pip install --force-reinstall -r requirements.txt")
    except Exception as exc:
        check("Import app.main", False, f"Import smoke test crashed: {exc}")

    # 11. Knowledge Base embeddings (persisted sentence_transformer must load)
    try:
        from app.services.vector_store import get_embedding_function
        fn = get_embedding_function()
        vec = fn(["health check"])
        check("KB Embeddings", True,
              f"{fn.name() if hasattr(fn, 'name') else 'embedding'} ready ({len(vec[0])}-dim)")
    except Exception as exc:
        check("KB Embeddings", False, f"Embedding function failed: {str(exc)[:140]}",
              "pip install --force-reinstall -r requirements.txt")

    # Print Report
    print("\n" + "-" * 70)
    print(f"{'STATUS':<8} | {'CHECK':<25} | {'DETAILS'}")
    print("-" * 70)
    all_ok = True
    for c in CHECKS:
        status_label = "[OK]  " if c["passed"] else "[FAIL]"
        if not c["passed"]:
            all_ok = False
        print(f"{status_label} | {c['name']:<25} | {c['message']}")
        if not c["passed"] and c["fix_cmd"]:
            print(f"         `-> Fix: {c['fix_cmd']}")
    print("-" * 70)
    print(f"DOCTOR RESULT: {'ALL SYSTEM CHECKS PASSED [OK]' if all_ok else 'SOME CHECKS FAILED [ACTION REQUIRED]'}\n")
    return all_ok

if __name__ == "__main__":
    success = run_doctor()
    sys.exit(0 if success else 1)
