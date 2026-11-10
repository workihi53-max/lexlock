"""Проверка порта и выбор порта в лаунчере: сеть только loopback, Ollama не нужна."""

from __future__ import annotations

import http.server
import importlib.util
import json
import socket
import threading
from pathlib import Path

import pytest

from lexlock import portcheck
from lexlock.config import load_config

_SPEC = importlib.util.spec_from_file_location(
    "launcher", Path(__file__).resolve().parent.parent / "scripts" / "launcher.py"
)
launcher = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(launcher)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def fake_server():
    """Поднимает на свободном порту сервер с заданным ответом /api/health."""
    started: list[http.server.HTTPServer] = []

    def start(payload: dict | str) -> int:
        body = (json.dumps(payload) if isinstance(payload, dict) else payload).encode()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", _free_port()), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append(srv)
        return srv.server_address[1]

    yield start
    for srv in started:
        srv.shutdown()
        srv.server_close()


def test_free_port_detected():
    assert portcheck.port_is_free(_free_port()) is True


def test_busy_port_detected(fake_server):
    assert portcheck.port_is_free(fake_server({})) is False


def test_is_lexlock_recognises_own_health(fake_server):
    port = fake_server({"ok": True, "model_installed": False, "offline": True, "workspace": "/w"})
    assert portcheck.is_lexlock(port) is True


def test_other_app_is_not_lexlock(fake_server):
    assert portcheck.is_lexlock(fake_server("<html>Карта MewNet</html>")) is False
    assert portcheck.is_lexlock(fake_server({"ok": True})) is False


def test_pick_free_port_skips_busy(fake_server):
    busy = fake_server({})
    picked = portcheck.pick_free_port(busy - 1, attempts=5)
    assert picked is not None and picked != busy


def test_launcher_keeps_port_when_free():
    import dataclasses

    config = dataclasses.replace(load_config(), port=_free_port())
    assert launcher._choose_port(config, True) is config


def test_launcher_moves_to_other_port_when_foreign_app(fake_server, monkeypatch):
    busy = fake_server("<html>чужое</html>")
    messages: list[str] = []
    monkeypatch.setattr(launcher, "_notify", messages.append)
    import dataclasses

    config = dataclasses.replace(load_config(), port=busy)
    chosen = launcher._choose_port(config, True)
    assert chosen is not None and chosen.port != busy
    assert messages and str(busy) in messages[0]


def test_launcher_does_not_start_second_copy(fake_server, monkeypatch):
    busy = fake_server({"ok": True, "model_installed": True, "offline": True, "workspace": "/w"})
    opened: list[str] = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    import dataclasses

    config = dataclasses.replace(load_config(), port=busy)
    assert launcher._choose_port(config, False) is None
    assert opened == [f"http://127.0.0.1:{busy}"]
