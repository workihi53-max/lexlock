"""Строгий офлайн-режим: сетевые сокеты — только на loopback."""

from __future__ import annotations

import socket

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"}
_enforced = False


def _is_loopback(host: str) -> bool:
    h = (host or "").strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h in _LOOPBACK_HOSTS


def enforce_offline() -> None:
    """Разрешает connect()/getaddrinfo() только для 127.0.0.1/localhost/::1.

    Иначе поднимает ConnectionError. Идемпотентно.
    """
    global _enforced
    if _enforced:
        return
    _enforced = True

    _orig_connect = socket.socket.connect
    _orig_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if not _is_loopback(host):
            raise ConnectionError(
                "Офлайн-режим: подключение разрешено только к 127.0.0.1/localhost"
            )
        return _orig_connect(self, address)

    def guarded_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host is not None and not _is_loopback(host):
            raise ConnectionError(
                "Офлайн-режим: DNS-разрешение доступно только для локальных адресов"
            )
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.socket.connect = guarded_connect
    socket.getaddrinfo = guarded_getaddrinfo
