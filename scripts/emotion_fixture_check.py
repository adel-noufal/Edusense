"""Hit the real emotion endpoint with the local face fixtures and report what it says."""
import base64, json, sys, time, urllib.error, urllib.request
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:8000"
FIX = Path(__file__).resolve().parent.parent / "backend" / "tests" / "fixtures" / "faces"

def call(p, body=None, tok=None, m="POST", timeout=120):
    req = urllib.request.Request(BASE+p, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": "Bearer "+tok} if tok else {})}, method=m)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, str(e)[:200]

tok = call("/api/auth/login", {"email": "student@edusense.local", "password": "Password123"})[1]["access_token"]
print("consent:", call("/api/emotions/consent/give", {"consent_type": "emotion_detection", "granted": True}, tok)[0])
for name in ("smile-generated.jpg", "too-dark.jpg", "no-face-wall.jpg"):
    b64 = base64.b64encode((FIX / name).read_bytes()).decode()
    t0 = time.time()
    st, body = call("/api/emotions/analyze-trial", {"image": f"data:image/jpeg;base64,{b64}"}, tok)
    print(f"{name:22s} {st} {time.time()-t0:5.2f}s {json.dumps(body, ensure_ascii=False)[:220]}")
st, body = call("/api/emotions/analyze-trial", {"image": "data:image/jpeg;base64,bm90YW5pbWFnZQ=="}, tok)
print(f"{'garbage-bytes':22s} {st} {json.dumps(body, ensure_ascii=False)[:220]}")
