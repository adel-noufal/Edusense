"""CLI diagnostic: python -m app.tools.llm_check [--probe]

Prints every configured (provider, key, model) combination with masked key,
quota group, cooldown state, and â€” with --probe â€” a live 1-token ping.
"""
import sys
import time
import json
import urllib.request
import urllib.error

import os
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import llm
from app.services.llm import PROVIDERS, router


def _probe(provider: str, key: str, model: str) -> str:
    spec = PROVIDERS[provider]
    try:
        if spec.kind == "gemini":
            url = f"{spec.base_url}/models/{model}:generateContent?key={key}"
            body = json.dumps({"contents": [{"parts": [{"text": "say ok"}]}],
                               "generationConfig": {"maxOutputTokens": 8}}).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        else:
            url = f"{spec.base_url}/chat/completions"
            body = json.dumps({"model": model, "max_tokens": 8,
                               "messages": [{"role": "user", "content": "say ok"}]}).encode()
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        return f"OK {round((time.time()-t0)*1000)}ms"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except Exception as e:
        return f"ERR {str(e)[:60]}"


def main():
    probe = "--probe" in sys.argv
    st = router.status()
    print(f"{'PROVIDER':<12} {'KEY':<16} {'GROUP':<6} {'MODEL':<42} {'STATE':<22} {'REQS':<6} {'LAST ERROR'}")
    print("-" * 130)
    for p in st["providers"]:
        for m in p["models"]:
            if m["disabled"]:
                state = "DISABLED(404)"
            elif m["cooling_down"]:
                state = f"COOLDOWN {m['cooldown_remaining_s']}s"
            else:
                state = "ready"
            live = ""
            if probe and state == "ready":
                key = router.provider_keys(p["provider"])[m["key_index"]]
                live = _probe(p["provider"], key, m["model"])
            print(f"{p['provider']:<12} {m['key_masked']:<16} {m['quota_group']:<6} {m['model']:<42} "
                  f"{state:<22} {m['requests']:<6} {m['last_error'][:40]} {live}")
    print("\nTask chains:")
    for task, chain in st["chains"].items():
        print(f"  {task:<15} {' -> '.join(chain[:8])}")


if __name__ == "__main__":
    main()
