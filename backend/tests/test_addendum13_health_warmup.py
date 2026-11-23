"""U19: /health answers immediately and reports the background warm-up state.

The backend used to take minutes before /health answered, so the frontend showed
a dead server. The API now starts first and warms the heavy services in a daemon
thread; /health publishes what is still warming up.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.services import warmup


def test_health_reports_warmup_state():
    warmup.set_status("knowledge_base", "warming", "embedding model")
    # No context manager: the app's lifespan starts background warm-up threads
    # that race with Chroma's teardown. Only the /health payload is under test.
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert set(payload["warmup"]["tasks"]) == {"model_discovery", "knowledge_base", "emotion_detector"}
    assert payload["warmup"]["status"] in {"warming", "ready", "degraded"}
