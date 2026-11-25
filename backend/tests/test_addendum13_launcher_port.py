"""U16 regression: the launcher must never report a held port as free.

The visible symptom was a backend that printed "Port: 8000", then died with
WinError 10048 and moved the frontend to 8001. On Windows SO_REUSEADDR lets a
probe bind a port another process is still listening on, so `is_port_bindable`
returned True for a busy port.
"""
import socket

from app.tools import launcher


def _hold(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock


def test_held_port_is_not_reported_free():
    held = _hold(0)
    port = held.getsockname()[1]
    try:
        assert launcher.port_has_listener(port) is True
        assert launcher.is_port_bindable("127.0.0.1", port) is False
        assert launcher.port_is_free(port) is False
    finally:
        held.close()


def test_find_free_port_skips_an_occupied_port():
    held = _hold(0)
    port = held.getsockname()[1]
    try:
        picked = launcher.find_free_port(port, max_ports=5)
        assert picked != port
        assert launcher.port_is_free(picked)
    finally:
        held.close()


def test_port_resolution_is_one_fixed_port(monkeypatch):
    # Contract: EDUSENSE_PORT (backend/.env or process env) is the single port;
    # a bare inherited PORT is ignored (that is where PORT=0 came from), and an
    # invalid value falls back to 8000 instead of a random port.
    monkeypatch.setattr(launcher, "_dotenv_port", lambda: "")
    monkeypatch.setenv("PORT", "0")
    assert launcher.preferred_port() == 8000
    monkeypatch.setenv("PORT", "8100")
    assert launcher.preferred_port() == 8000  # bare PORT never changes the port

    monkeypatch.setenv("EDUSENSE_PORT", "0")
    assert launcher.preferred_port() == 8000
    monkeypatch.setenv("EDUSENSE_PORT", "-5")
    assert launcher.preferred_port() == 8000
    monkeypatch.setenv("EDUSENSE_PORT", "not-a-port")
    assert launcher.preferred_port() == 8000
    monkeypatch.setenv("EDUSENSE_PORT", "8100")
    assert launcher.preferred_port() == 8100
