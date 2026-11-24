"""F1 acceptance — real content with Gemini disabled.

Runs the four demo generations through the live API and checks two things:

  1. the topic is actually covered (keywords that must appear), and
  2. none of the known fabricated-template phrases appear.

Usage (API must be running with EDUSENSE_DISABLE_PROVIDERS=gemini):

    python scripts/f1_acceptance.py http://127.0.0.1:8003
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
EMAIL, PASSWORD = "instructor@edusense.local", "Password123"

BANNED = [
    "architectural principles",
    "architectural abstractions",
    "enterprise case study",
    "production configuration pattern",
    "primary architectural finding",
    "operational mechanics",
    "primary optimization bottleneck",
]

CASES = [
    ("lesson EN  (Standard)", "/api/ai/lessons",
     {"topic": "Python variables", "prompt": "", "language": "English",
      "teaching_style": "Friendly", "detail_level": "Standard"},
     ["assign", "variable", "refer"]),
    ("lesson AR", "/api/ai/lessons",
     {"topic": "المتغيرات في بايثون", "prompt": "", "language": "Arabic",
      "teaching_style": "Friendly", "detail_level": "Standard"},
     ["بايثون", "متغير"]),
    ("quiz 5    (Photosynthesis)", "/api/ai/quizzes",
     {"topic": "Photosynthesis", "prompt": "", "difficulty": "Medium", "count": 5},
     ["photosynthesis", "light", "chlorophyll", "glucose"]),
    ("flashcards 8 (Photosynthesis)", "/api/ai/flashcards",
     {"topic": "Photosynthesis", "count": 8, "language": "English"},
     ["photosynthesis", "light", "chlorophyll", "glucose"]),
]


def call(path: str, payload: dict, token: str | None = None, timeout: int = 420):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(), time.time() - started
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), time.time() - started
    except Exception as e:  # timeout, connection reset
        return 0, str(e), time.time() - started


def flatten(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).lower()


def main() -> int:
    status, body, _ = call("/api/auth/login", {"email": EMAIL, "password": PASSWORD})
    if status != 200:
        print(f"LOGIN FAILED {status}: {body[:300]}")
        return 1
    token = json.loads(body)["access_token"]
    print(f"F1 acceptance against {BASE} (Gemini disabled by env)\n")
    print(f"{'case':32s} {'http':>5s} {'sec':>6s}  keywords          banned  note")
    print("-" * 104)

    failures = 0
    for label, path, payload, keywords in CASES:
        status, body, secs = call(path, payload, token)
        if status != 200:
            print(f"{label:32s} {status:5d} {secs:6.1f}  -                 -       {body[:60]}")
            failures += 1
            continue
        data = json.loads(body)
        text = flatten(data)
        hits = [k for k in keywords if k.lower() in text]
        banned = [b for b in BANNED if b in text]
        if path.endswith("flashcards"):
            count = len(data.get("cards") or [])
        elif path.endswith("quizzes"):
            count = len(data.get("questions") or [])
        else:
            count = len(data.get("sections") or [])
        note = f"items={count}"
        ok = len(hits) >= max(2, len(keywords) - 1) and not banned and count > 0
        if not ok:
            failures += 1
        print(f"{label:32s} {status:5d} {secs:6.1f}  {len(hits)}/{len(keywords):<13d} "
              f"{len(banned):<7d} {note}{'  FAIL' if not ok else ''}")
        if banned:
            print(f"    banned phrases: {banned}")
        print(f"    excerpt: {flatten(data)[:200]}")

    print("-" * 104)
    print("RESULT:", "PASS — all four generations are on-topic and free of template filler"
          if failures == 0 else f"FAIL — {failures} case(s) need attention")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
