"""Background warm-up state, reported by /health (Addendum #13 startup item).

The API must answer /health immediately; model probing, embedding warm-up and
the emotion detector run afterwards in a daemon thread. Their state is published
here so the UI (and verify scripts) can show "warming up" instead of a silent
wait.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.services.timefmt import iso_z

TASKS = ("model_discovery", "knowledge_base", "emotion_detector")

_lock = threading.Lock()
_state: dict[str, dict] = {name: {"status": "pending", "detail": ""} for name in TASKS}


def set_status(name: str, status: str, detail: str = "") -> None:
    with _lock:
        _state[name] = {
            "status": status,          # pending | warming | ready | failed
            "detail": detail,
            "updated_at": iso_z(datetime.now(timezone.utc)),
        }


def snapshot() -> dict:
    with _lock:
        pending = any(item["status"] in ("pending", "warming") for item in _state.values())
        failed = [name for name, item in _state.items() if item["status"] == "failed"]
        overall = "warming" if pending else ("degraded" if failed else "ready")
        return {"status": overall, "tasks": {name: dict(item) for name, item in _state.items()}}
