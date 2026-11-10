"""Проверка порта перед запуском: чужая программа на 8765 не должна подменять ЛексЛок."""

from __future__ import annotations

import json
import socket
import urllib.request

LEXLOCK_KEYS = {"model_installed", "offline", "workspace"}


def port_is_free(port: int) -> bool:
    """True, если на loopback можно занять порт."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def is_lexlock(port: int) -> bool:
    """True, если на порту уже отвечает ЛексЛок (по форме ответа /api/health)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as resp:
            data = json.loads(resp.read(65536).decode("utf-8", errors="replace"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and LEXLOCK_KEYS <= data.keys()


def pick_free_port(start: int, attempts: int = 20) -> int | None:
    """Первый свободный порт после start или None."""
    for port in range(start + 1, start + 1 + attempts):
        if port_is_free(port):
            return port
    return None
